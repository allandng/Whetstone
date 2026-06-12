"""Integration tests for the Practice feature (course + DSA problem bank).

Same harness as ``test_integration.py``: the FastAPI app under TestClient,
a throwaway SQLite database, and llama-server mocked at the LLMClient
singleton boundary. The lifespan seeds the built-in problem bank, so every
test starts from a populated bank.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

# --- Bootstrap: path + test database, before importing any app module --------

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Always force a throwaway database, exactly like test_integration.py does.
# A presence check would be a footgun: a developer with WHETSTONE_DATABASE_URL
# exported to their real database who runs this file alone would have fresh_db
# drop every table in it. When the whole suite runs, whichever test module is
# imported first wins the engine binding — both candidates are temp files.
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["WHETSTONE_DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import db as db_module  # noqa: E402
import routers.ai as ai_router  # noqa: E402
import routers.practice as practice_router  # noqa: E402
from content.course import COURSE_LESSONS  # noqa: E402
from content.problems import PATTERN_LABELS, SEED_PROBLEMS  # noqa: E402
from main import app  # noqa: E402
from models import Problem, ProblemDifficulty  # noqa: E402
from services.llm_client import LLMUnavailableError  # noqa: E402
from services.problem_generator import (  # noqa: E402
    build_generation_messages,
    parse_generated_problem,
)


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def fresh_db():
    """Drop and recreate every table so each test starts from empty."""

    SQLModel.metadata.drop_all(db_module.engine)
    SQLModel.metadata.create_all(db_module.engine)
    yield
    SQLModel.metadata.drop_all(db_module.engine)


@pytest.fixture
def client(fresh_db):
    """A TestClient with the app lifespan active (seeds the problem bank)."""

    with TestClient(app) as test_client:
        yield test_client


def _ask_yielding(*chunks: str):
    """An ``LLMClient.ask`` replacement that yields the given text chunks."""

    async def _ask(messages, stream=False, thinking=False):
        for chunk in chunks:
            yield chunk

    return _ask


def _ask_unavailable(message: str = "llama-server is not reachable"):
    """An ``LLMClient.ask`` replacement that fails like a dead llama-server."""

    async def _ask(messages, stream=False, thinking=False):
        raise LLMUnavailableError(message)
        yield  # unreachable; makes this an async generator function

    return _ask


_GENERATED = {
    "title": "Conveyor Belt Duplicates",
    "difficulty": "easy",
    "prompt": "Parcels roll past a scanner; return the first tracking code seen twice, else -1.",
    "examples": [
        {"input": "codes = [1, 2, 1]", "output": "1", "explanation": "1 repeats first."},
        {"input": "codes = [4]", "output": "-1", "explanation": "No repeats."},
    ],
    "hints": ["One pass.", "Remember what you saw.", "Use a set; return on hit."],
    "starter_code": "def first_repeat(codes):\n    return -1\n\nprint(first_repeat([1, 2, 1]))  # expect 1\n",
}


# --- Problem bank ------------------------------------------------------------


def test_problem_bank_seeded_and_ordered(client):
    problems = client.get("/practice/problems").json()
    assert len(problems) == len(SEED_PROBLEMS)
    assert {p["slug"] for p in problems} == {s["slug"] for s in SEED_PROBLEMS}

    # Patterns appear in curriculum order (PATTERN_LABELS insertion order),
    # not alphabetically — DP must come last, not third.
    seen_patterns = list(dict.fromkeys(p["pattern"] for p in problems))
    curriculum = [slug for slug in PATTERN_LABELS if slug in set(seen_patterns)]
    assert seen_patterns == curriculum

    # Within one pattern, easy sorts before medium.
    by_pattern: dict[str, list[str]] = {}
    for p in problems:
        by_pattern.setdefault(p["pattern"], []).append(p["difficulty"])
    rank = {"easy": 0, "medium": 1, "hard": 2}
    for difficulties in by_pattern.values():
        assert difficulties == sorted(difficulties, key=rank.__getitem__)

    # Examples and hints arrive decoded, and every problem starts untouched.
    sample = problems[0]
    assert isinstance(sample["examples"], list) and sample["examples"]
    assert isinstance(sample["hints"], list) and len(sample["hints"]) == 3
    assert all(p["status"] == "not_started" for p in problems)
    assert all(p["pattern_label"] for p in problems)


def test_seeding_is_idempotent(client):
    practice_router.seed_builtin_problems()
    problems = client.get("/practice/problems").json()
    assert len(problems) == len(SEED_PROBLEMS)


def test_problem_filters(client):
    easy = client.get("/practice/problems", params={"difficulty": "easy"}).json()
    assert easy and all(p["difficulty"] == "easy" for p in easy)

    stack = client.get("/practice/problems", params={"pattern": "stack"}).json()
    assert {p["pattern"] for p in stack} == {"stack"}

    none = client.get("/practice/problems", params={"status": "solved"}).json()
    assert none == []


def test_problem_detail_and_status_update(client):
    listed = client.get("/practice/problems").json()
    pid = listed[0]["id"]

    detail = client.get(f"/practice/problems/{pid}")
    assert detail.status_code == 200
    assert detail.json()["slug"] == listed[0]["slug"]

    updated = client.patch(
        f"/practice/problems/{pid}", json={"status": "struggled"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "struggled"
    assert (
        client.get(f"/practice/problems/{pid}").json()["status"] == "struggled"
    )


def test_problem_404s(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/practice/problems/{missing}").status_code == 404
    assert (
        client.patch(
            f"/practice/problems/{missing}", json={"status": "solved"}
        ).status_code
        == 404
    )
    assert client.post(f"/practice/problems/{missing}/start").status_code == 404
    assert client.post(f"/practice/problems/{missing}/similar").status_code == 404


# --- Start-in-workspace -------------------------------------------------------


def test_start_problem_creates_workspace_session(client):
    problem = client.get("/practice/problems").json()[0]

    started = client.post(f"/practice/problems/{problem['id']}/start")
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    spec_id = started.json()["spec_id"]

    # The session exists, carries the spec, and is titled after the problem.
    session = client.get(f"/sessions/{session_id}").json()
    assert session["spec_id"] == spec_id
    assert problem["title"] in session["title"]

    # The starter cell is in place and runnable-shaped.
    cells = client.get(f"/sessions/{session_id}/cells").json()
    assert len(cells) == 1
    assert cells[0]["language"] == problem["language"]
    assert problem["starter_code"] in cells[0]["content"]

    # The checklist landed as requirement items.
    requirements = client.get(f"/specs/{spec_id}/requirements").json()
    texts = [r["text"] for r in requirements]
    assert len(texts) == 4
    assert any(problem["title"] in t for t in texts)

    # The timeline opens with the practice_start event.
    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert timeline["events"][0]["event_type"] == "practice_start"
    assert timeline["events"][0]["payload"]["problem_id"] == problem["id"]

    # Starting an untouched problem marks it attempted.
    assert (
        client.get(f"/practice/problems/{problem['id']}").json()["status"]
        == "attempted"
    )


def test_tutor_context_includes_problem_statement(client, monkeypatch):
    """The AI tutor on a practice session must see the actual problem.

    The statement lives in Spec.raw_text (the checklist items are generic),
    so _assemble_context must surface it — otherwise the tutor answers blind.
    """

    captured: dict = {}

    async def _capture_ask(messages, stream=False, thinking=False):
        captured["messages"] = messages
        yield "Looks like an off-by-one."

    monkeypatch.setattr(ai_router.llm_client, "ask", _capture_ask)

    problem = client.get("/practice/problems").json()[0]
    started = client.post(f"/practice/problems/{problem['id']}/start").json()
    cell = client.get(f"/sessions/{started['session_id']}/cells").json()[0]

    resp = client.post(
        "/ai/explain-error",
        json={"cell_id": cell["id"], "error_text": "IndexError: list index out of range"},
    )
    assert resp.status_code == 200

    system = captured["messages"][0]["content"]
    # A distinctive slice of the statement, not just the title.
    assert problem["prompt"][:60] in system


def test_delete_session_garbage_collects_practice_spec(client):
    """Deleting a practice session must not strand its per-session spec."""

    problem = client.get("/practice/problems").json()[0]
    started = client.post(f"/practice/problems/{problem['id']}/start").json()

    assert (
        client.get(f"/specs/{started['spec_id']}/requirements").status_code == 200
    )
    assert (
        client.delete(f"/sessions/{started['session_id']}").status_code == 200
    )
    # Spec and its requirement items are gone with their only session.
    assert (
        client.get(f"/specs/{started['spec_id']}/requirements").status_code == 404
    )


def test_generation_prompt_caps_user_inputs():
    """A pasted novel must not swamp the local model's context window."""

    source = Problem(
        slug="s",
        title="T",
        pattern="stack",
        difficulty=ProblemDifficulty.easy,
        prompt="P",
    )
    messages = build_generation_messages(source, "n" * 50_000, "c" * 50_000)
    user = messages[1]["content"]
    assert len(user) < 20_000
    assert user.count("…[truncated]") == 2


def test_start_does_not_downgrade_status(client):
    problem = client.get("/practice/problems").json()[0]
    client.patch(f"/practice/problems/{problem['id']}", json={"status": "solved"})
    client.post(f"/practice/problems/{problem['id']}/start")
    assert (
        client.get(f"/practice/problems/{problem['id']}").json()["status"]
        == "solved"
    )


# --- Generation ----------------------------------------------------------------


def test_generate_similar_problem(client, monkeypatch):
    monkeypatch.setattr(
        practice_router.llm_client, "ask", _ask_yielding(json.dumps(_GENERATED))
    )
    source = client.get("/practice/problems").json()[0]

    resp = client.post(
        f"/practice/problems/{source['id']}/similar",
        json={"note": "I always forget what to store in the set", "code": "def f(): pass"},
    )
    assert resp.status_code == 200
    variant = resp.json()
    assert variant["title"] == _GENERATED["title"]
    assert variant["source"] == "generated"
    assert variant["parent_problem_id"] == source["id"]
    assert variant["pattern"] == source["pattern"]  # pattern is inherited
    assert variant["slug"].startswith(source["slug"] + "-variant-")
    assert len(variant["examples"]) == 2
    assert len(variant["hints"]) == 3

    # The variant is persisted and shows up in the bank.
    listed = client.get("/practice/problems").json()
    assert len(listed) == len(SEED_PROBLEMS) + 1


def test_generate_tolerates_fenced_and_prose_wrapped_json(client, monkeypatch):
    reply = (
        "Sure! Here is a fresh problem for you:\n\n"
        "```json\n" + json.dumps(_GENERATED) + "\n```\n\nGood luck!"
    )
    monkeypatch.setattr(practice_router.llm_client, "ask", _ask_yielding(reply))
    source = client.get("/practice/problems").json()[0]

    resp = client.post(f"/practice/problems/{source['id']}/similar", json={})
    assert resp.status_code == 200
    assert resp.json()["title"] == _GENERATED["title"]


def test_generate_unparseable_reply_is_502(client, monkeypatch):
    monkeypatch.setattr(
        practice_router.llm_client,
        "ask",
        _ask_yielding("I'm sorry, I can only chat about the weather."),
    )
    source = client.get("/practice/problems").json()[0]
    resp = client.post(f"/practice/problems/{source['id']}/similar", json={})
    assert resp.status_code == 502


def test_generate_with_llm_down_is_503(client, monkeypatch):
    monkeypatch.setattr(practice_router.llm_client, "ask", _ask_unavailable())
    source = client.get("/practice/problems").json()[0]
    resp = client.post(f"/practice/problems/{source['id']}/similar", json={})
    assert resp.status_code == 503


def test_parse_generated_problem_edge_cases():
    # Missing required fields -> None.
    assert parse_generated_problem(json.dumps({"title": "x"})) is None
    assert parse_generated_problem("") is None
    # A stray brace in leading prose doesn't sink the parse.
    text = "weird {not json} preamble " + json.dumps(_GENERATED)
    parsed = parse_generated_problem(text)
    assert parsed is not None and parsed["title"] == _GENERATED["title"]
    # Unknown difficulty coerces to medium; junk examples/hints are dropped.
    messy = dict(_GENERATED, difficulty="brutal", examples="nope", hints=[1, " ok "])
    parsed = parse_generated_problem(json.dumps(messy))
    assert parsed["difficulty"].value == "medium"
    assert parsed["examples"] == []
    assert parsed["hints"] == ["ok"]


# --- Course --------------------------------------------------------------------


def test_course_lessons_and_progress(client):
    lessons = client.get("/practice/course").json()
    assert len(lessons) == len(COURSE_LESSONS)
    assert [l["id"] for l in lessons] == [l["id"] for l in COURSE_LESSONS]
    assert all(not l["completed"] for l in lessons)
    assert all(l["exercise"]["starter_code"] for l in lessons)

    first = lessons[0]["id"]
    done = client.patch(f"/practice/course/{first}", json={"completed": True})
    assert done.status_code == 200 and done.json()["completed"] is True

    refreshed = client.get("/practice/course").json()
    assert refreshed[0]["completed"] is True
    assert not any(l["completed"] for l in refreshed[1:])

    undone = client.patch(f"/practice/course/{first}", json={"completed": False})
    assert undone.json()["completed"] is False


def test_lesson_404s(client):
    assert (
        client.patch(
            "/practice/course/no-such-lesson", json={"completed": True}
        ).status_code
        == 404
    )
    assert client.post("/practice/course/no-such-lesson/start").status_code == 404


def test_start_lesson_creates_workspace_session(client):
    lesson = client.get("/practice/course").json()[0]

    started = client.post(f"/practice/course/{lesson['id']}/start")
    assert started.status_code == 200
    session_id = started.json()["session_id"]

    session = client.get(f"/sessions/{session_id}").json()
    assert lesson["title"] in session["title"]

    cells = client.get(f"/sessions/{session_id}/cells").json()
    assert len(cells) == 1
    assert cells[0]["language"] == "python"
    assert lesson["exercise"]["starter_code"] in cells[0]["content"]

    requirements = client.get(
        f"/specs/{started.json()['spec_id']}/requirements"
    ).json()
    assert len(requirements) == 3

    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert timeline["events"][0]["event_type"] == "practice_start"
    assert timeline["events"][0]["payload"]["lesson_id"] == lesson["id"]
