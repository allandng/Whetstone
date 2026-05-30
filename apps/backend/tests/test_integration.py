"""End-to-end integration tests for the Whetstone backend.

Exercises all six phases of the backend through the FastAPI app with
``TestClient`` — no live subprocesses. Psirver (code execution) and
llama-server (LLM inference) are mocked at the client-singleton boundary so
every code path that *would* make a loopback HTTP call runs against a
deterministic stand-in instead.

The whole suite runs against a throwaway SQLite file: ``WHETSTONE_DATABASE_URL``
is set before any app module is imported, so the cached settings and the
module-global engine in ``db`` (used by both the ``get_session`` request
dependency *and* the ``session_scope`` writes done by AI/spec background work)
all bind to the test database.
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

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["WHETSTONE_DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel import Session as DBSession  # noqa: E402
from sqlmodel import select  # noqa: E402

import db as db_module  # noqa: E402
import routers.ai as ai_router  # noqa: E402
import routers.cells as cells_router  # noqa: E402
import routers.spec as spec_router  # noqa: E402
from main import app  # noqa: E402
from models import Cell, Event, SourceType, Spec  # noqa: E402
from services.llm_client import LLMUnavailableError  # noqa: E402
from services.stt_client import STTUnavailableError  # noqa: E402


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
    """A TestClient with the app lifespan active (depends on a fresh DB)."""

    with TestClient(app) as test_client:
        yield test_client


# --- Mock factories ---------------------------------------------------------


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


def _stt_returning(text: str):
    """An ``STTClient.transcribe`` replacement that returns a fixed transcript."""

    async def _transcribe(audio, language="en"):
        return text

    return _transcribe


def _stt_unavailable(message: str = "whisper-server is not reachable"):
    """An ``STTClient.transcribe`` replacement that fails like a dead server."""

    async def _transcribe(audio, language="en"):
        raise STTUnavailableError(message)

    return _transcribe


def _psirver_ok(stdout="42\n", stderr="", exit_code=0, status="COMPLETED"):
    """Return (submit, poll) stand-ins for a Psirver job that terminates."""

    captured: dict = {}

    async def _submit(language, source):
        captured["language"] = language
        captured["source"] = source
        return "job-1"

    async def _poll(job_id):
        return {
            "job_id": job_id,
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }

    return _submit, _poll, captured


def _psirver_down():
    """A ``submit_job`` stand-in that fails like an unreachable Psirver."""

    async def _submit(language, source):
        raise httpx.ConnectError("connection refused")

    return _submit


def _mock_psirver(monkeypatch, submit, poll=None):
    monkeypatch.setattr(cells_router.psirver_client, "submit_job", submit)
    if poll is not None:
        monkeypatch.setattr(cells_router.psirver_client, "poll_job", poll)


# --- Helpers ----------------------------------------------------------------


def _db() -> DBSession:
    return DBSession(db_module.engine)


def _parse_sse(text: str) -> list[dict]:
    """Decode the ``data:`` JSON lines from an SSE response body."""

    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))
    return events


def _new_session(client, title="Test session") -> str:
    resp = client.post("/sessions", json={"title": title})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _new_cell(client, session_id, *, cell_type="code", language="python", content="") -> dict:
    resp = client.post(
        "/cells",
        json={
            "session_id": session_id,
            "cell_type": cell_type,
            "language": language,
            "content": content,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _minimal_pdf(text: str = "Hello Whetstone") -> bytes:
    """Build a single-page PDF with one text line and a valid xref table."""

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream_text = ("BT /F1 24 Tf 72 720 Td (%s) Tj ET" % text).encode("latin-1")
    objects[3] = b"<< /Length %d >>\nstream\n%s\nendstream" % (
        len(stream_text),
        stream_text,
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(out)
    n = len(objects) + 1
    out += b"xref\n0 %d\n" % n
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        n,
        xref_pos,
    )
    return bytes(out)


# === Health =================================================================


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_ok_when_psirver_unreachable(client, monkeypatch):
    """Backend liveness is independent of subprocesses (RUNNING.md): /health
    stays ok even with Psirver down — the failure surfaces per-request, not
    here."""

    _mock_psirver(monkeypatch, _psirver_down())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# === CORS ===================================================================

# The Tauri dev origin must be in the allowed list (config default) or the
# running app's every request fails with an opaque CORS error.
_ALLOWED_ORIGIN = "http://localhost:1420"
_DISALLOWED_ORIGIN = "http://evil.example"


def test_cors_allowed_origin_gets_credentialed_access(client):
    resp = client.get("/health", headers={"Origin": _ALLOWED_ORIGIN})
    assert resp.status_code == 200
    # The specific origin is echoed (never "*"), and credentials are permitted.
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_allowed_origin_preflight_succeeds(client):
    resp = client.options(
        "/sessions",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_disallowed_origin_denied_credentialed_access(client):
    resp = client.get("/health", headers={"Origin": _DISALLOWED_ORIGIN})
    # CORS is browser-enforced, so the response body still arrives. The gate is
    # ``Access-Control-Allow-Origin``: without it echoing the caller's origin
    # the browser refuses to expose a credentialed response. It must be absent
    # for a disallowed origin (and never the wildcard "*").
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin != _DISALLOWED_ORIGIN
    assert allow_origin != "*"
    assert allow_origin is None


def test_cors_disallowed_origin_preflight_rejected(client):
    resp = client.options(
        "/sessions",
        headers={
            "Origin": _DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )
    # A preflight from a disallowed origin is rejected outright, and never
    # echoes the origin back as allowed.
    assert resp.status_code == 400
    assert resp.headers.get("access-control-allow-origin") != _DISALLOWED_ORIGIN


# === Global error handling ==================================================


def test_global_exception_handler_returns_structured_error(fresh_db, monkeypatch):
    """An unexpected error returns a clean JSON shape, not a stack trace.

    ``raise_server_exceptions=False`` makes the TestClient surface the response
    the client would actually receive rather than re-raising the error
    in-process. The non-HTTPException path is triggered by making the LLM client
    raise a plain ``RuntimeError`` (not the typed ``LLMUnavailableError`` the
    endpoint knows how to map to a 503).
    """

    def _boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(ai_router.llm_client, "ask", _boom)

    with TestClient(app, raise_server_exceptions=False) as c:
        session_id = c.post("/sessions", json={"title": "t"}).json()["id"]
        cell = c.post(
            "/cells", json={"session_id": session_id, "content": "x = 1"}
        ).json()
        resp = c.post("/ai/complexity", json={"cell_id": cell["id"]})

    assert resp.status_code == 500
    # Structured, parseable shape matching the rest of the API ({"detail": ...}).
    assert resp.json() == {"detail": "Internal Server Error"}
    # No internals leak: not the exception type, its message, or a traceback.
    assert "RuntimeError" not in resp.text
    assert "secret internal detail" not in resp.text
    assert "Traceback" not in resp.text


# === Session CRUD ===========================================================


def test_session_crud_create_list_get(client):
    created = client.post("/sessions", json={"title": "Assignment 1"})
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]
    assert created.json()["title"] == "Assignment 1"
    assert created.json()["spec_id"] is None

    listed = client.get("/sessions")
    assert listed.status_code == 200
    assert any(s["id"] == session_id for s in listed.json())

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session_id

    missing = client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_session_delete_cascades_cells_and_events(client, monkeypatch):
    submit, poll, _ = _psirver_ok()
    _mock_psirver(monkeypatch, submit, poll)

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, content="print(42)")
    # Running the cell writes cell_run + cell_result events for this session.
    run = client.post(f"/cells/{cell['id']}/run")
    assert run.status_code == 200

    with _db() as db:
        import uuid as _uuid

        sid = _uuid.UUID(session_id)
        assert db.exec(select(Cell).where(Cell.session_id == sid)).all()
        assert db.exec(select(Event).where(Event.session_id == sid)).all()

    deleted = client.delete(f"/sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    assert client.get(f"/sessions/{session_id}").status_code == 404
    assert client.get(f"/sessions/{session_id}/timeline").status_code == 404

    with _db() as db:
        import uuid as _uuid

        sid = _uuid.UUID(session_id)
        assert db.exec(select(Cell).where(Cell.session_id == sid)).all() == []
        assert db.exec(select(Event).where(Event.session_id == sid)).all() == []


# === Cell CRUD ==============================================================


def test_cell_crud_create_update_delete(client):
    session_id = _new_session(client)

    cell = _new_cell(client, session_id, content="x = 1")
    cell_id = cell["id"]
    assert cell["cell_type"] == "code"
    assert cell["content"] == "x = 1"

    updated = client.put(
        f"/cells/{cell_id}",
        json={"content": "x = 2", "language": "python"},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "x = 2"
    assert updated.json()["language"] == "python"

    deleted = client.delete(f"/cells/{cell_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    # Gone: running it now 404s.
    assert client.post(f"/cells/{cell_id}/run").status_code == 404


def test_cell_create_order_index_auto_append(client):
    session_id = _new_session(client)

    first = _new_cell(client, session_id, content="a")
    second = _new_cell(client, session_id, content="b")
    assert first["order_index"] == 0
    assert second["order_index"] == 1

    # Explicit order_index is respected.
    explicit = client.post(
        "/cells",
        json={"session_id": session_id, "content": "c", "order_index": 5},
    )
    assert explicit.status_code == 200
    assert explicit.json()["order_index"] == 5

    # Auto-append continues after the current max.
    after = _new_cell(client, session_id, content="d")
    assert after["order_index"] == 6


# === Cell run ===============================================================


def test_cell_run_python_emits_events_and_writes_output(client, monkeypatch):
    submit, poll, captured = _psirver_ok(stdout="42\n", exit_code=0)
    _mock_psirver(monkeypatch, submit, poll)

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, language="python", content="print(42)")

    run = client.post(f"/cells/{cell['id']}/run")
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "ok"
    assert body["last_output"] == "42\n"
    assert captured["language"] == "python"

    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert "cell_run" in timeline["groups"]
    assert "cell_result" in timeline["groups"]
    result_payload = timeline["groups"]["cell_result"][0]["payload"]
    assert result_payload["status"] == "ok"
    assert result_payload["output"] == "42\n"


def test_cell_run_cpp_emits_events_and_writes_output(client, monkeypatch):
    submit, poll, captured = _psirver_ok(stdout="hello from c++\n", exit_code=0)
    _mock_psirver(monkeypatch, submit, poll)

    session_id = _new_session(client)
    cpp_src = '#include <iostream>\nint main(){std::cout<<"hello from c++\\n";}'
    cell = _new_cell(client, session_id, language="cpp", content=cpp_src)

    run = client.post(f"/cells/{cell['id']}/run")
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "ok"
    assert body["language"] == "cpp"
    assert body["last_output"] == "hello from c++\n"
    # The C++ language is what got forwarded to the executor.
    assert captured["language"] == "cpp"

    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert "cell_run" in timeline["groups"]
    assert "cell_result" in timeline["groups"]


def test_notes_cell_run_rejected_400(client):
    session_id = _new_session(client)
    note = _new_cell(
        client, session_id, cell_type="notes", language=None, content="a thought"
    )
    run = client.post(f"/cells/{note['id']}/run")
    assert run.status_code == 400
    assert "code cells" in run.json()["detail"]


def test_cell_run_psirver_unreachable_returns_error(client, monkeypatch):
    _mock_psirver(monkeypatch, _psirver_down())

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, language="python", content="print(1)")

    run = client.post(f"/cells/{cell['id']}/run")
    # Does not raise: the run is recorded as an error with the failure as output.
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "error"
    assert "Could not reach the execution service" in body["last_output"]

    # The failed run is still on the timeline.
    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert "cell_run" in timeline["groups"]
    assert timeline["groups"]["cell_result"][0]["payload"]["status"] == "error"


# === Session cells (list) ===================================================


def test_list_session_cells_empty(client):
    session_id = _new_session(client)

    resp = client.get(f"/sessions/{session_id}/cells")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_list_session_cells_unknown_session_404(client):
    resp = client.get("/sessions/00000000-0000-0000-0000-000000000000/cells")
    assert resp.status_code == 404


def test_list_session_cells_stable_order_by_order_index(client):
    session_id = _new_session(client)

    # Create out of order, with explicit order_index, to prove the listing is
    # sorted by order_index rather than insertion order.
    for content, order_index in [("b", 1), ("c", 2), ("a", 0)]:
        resp = client.post(
            "/cells",
            json={"session_id": session_id, "content": content, "order_index": order_index},
        )
        assert resp.status_code == 200, resp.text

    listed = client.get(f"/sessions/{session_id}/cells")
    assert listed.status_code == 200, listed.text
    cells = listed.json()
    assert [c["content"] for c in cells] == ["a", "b", "c"]
    assert [c["order_index"] for c in cells] == [0, 1, 2]


def test_list_session_cells_includes_last_output_after_run(client, monkeypatch):
    submit, poll, _ = _psirver_ok(stdout="42\n", exit_code=0)
    _mock_psirver(monkeypatch, submit, poll)

    session_id = _new_session(client)
    ran = _new_cell(client, session_id, language="python", content="print(42)")
    fresh = _new_cell(client, session_id, language="python", content="print(7)")

    run = client.post(f"/cells/{ran['id']}/run")
    assert run.status_code == 200, run.text

    listed = client.get(f"/sessions/{session_id}/cells")
    assert listed.status_code == 200, listed.text
    by_id = {c["id"]: c for c in listed.json()}

    # The cell that ran carries its terminal output and status...
    assert by_id[ran["id"]]["last_output"] == "42\n"
    assert by_id[ran["id"]]["status"] == "ok"
    # ...while a never-run cell has no output and its default status.
    assert by_id[fresh["id"]]["last_output"] is None
    assert by_id[fresh["id"]]["status"] == "idle"


# === Timeline ===============================================================


def test_timeline_chronological_grouped_decoded(client, monkeypatch):
    submit, poll, _ = _psirver_ok(stdout="out\n")
    _mock_psirver(monkeypatch, submit, poll)
    monkeypatch.setattr(
        ai_router.llm_client, "ask", _ask_yielding("Likely a NameError.")
    )

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, content="print('x')")
    client.post(f"/cells/{cell['id']}/run")
    client.post(
        "/ai/explain-error",
        json={"cell_id": cell["id"], "error_text": "NameError: name 'y'"},
    )

    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    events = timeline["events"]

    # Chronological: timestamps are non-decreasing.
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)

    # Grouped by event_type, and the groups partition the flat list.
    assert set(timeline["groups"]) == {"cell_run", "cell_result", "ai_exchange"}
    assert sum(len(v) for v in timeline["groups"].values()) == len(events)

    # Payloads are decoded from JSON into dicts.
    for event in events:
        assert isinstance(event["payload"], dict)
    assert timeline["groups"]["ai_exchange"][0]["payload"]["kind"] == "explain_error"


# === Spec import & requirement extraction ===================================


def test_spec_import_raw_text_returns_extracting(client, monkeypatch):
    monkeypatch.setattr(spec_router.llm_client, "ask", _ask_yielding("[]"))

    resp = client.post("/specs/import", data={"raw_text": "Implement a stack."})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "extracting"
    assert "spec_id" in body


def test_spec_import_pdf_uses_pdfplumber(client, monkeypatch):
    # No requirements needed here; we are verifying the PDF extraction path.
    monkeypatch.setattr(spec_router.llm_client, "ask", _ask_yielding("[]"))

    pdf_bytes = _minimal_pdf("Hello Whetstone")
    resp = client.post(
        "/specs/import",
        files={"file": ("assignment.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    spec_id = resp.json()["spec_id"]

    import uuid as _uuid

    with _db() as db:
        spec = db.get(Spec, _uuid.UUID(spec_id))
        assert spec is not None
        assert spec.source_type == SourceType.pdf
        assert "Hello Whetstone" in spec.raw_text


def test_spec_import_txt_file_multipart(client, monkeypatch):
    monkeypatch.setattr(
        spec_router.llm_client, "ask", _ask_yielding('["Parse the input file."]')
    )

    resp = client.post(
        "/specs/import",
        files={"file": ("spec.txt", b"Parse the input file.", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    spec_id = resp.json()["spec_id"]

    import uuid as _uuid

    with _db() as db:
        spec = db.get(Spec, _uuid.UUID(spec_id))
        assert spec is not None
        assert spec.source_type == SourceType.text
        assert spec.raw_text == "Parse the input file."

    # Background extraction ran and produced the checklist item.
    reqs = client.get(f"/specs/{spec_id}/requirements").json()
    assert [r["text"] for r in reqs] == ["Parse the input file."]


@pytest.mark.parametrize(
    "reply",
    [
        '["Read input", "Sort values", "Print result"]',
        '```json\n["Read input", "Sort values", "Print result"]\n```',
        'Sure! Here are the requirements:\n'
        '["Read input", "Sort values", "Print result"]\nLet me know if that helps.',
    ],
    ids=["bare", "fenced", "prose"],
)
def test_requirement_extraction_parses_formats(client, monkeypatch, reply):
    monkeypatch.setattr(spec_router.llm_client, "ask", _ask_yielding(reply))

    resp = client.post("/specs/import", data={"raw_text": "Some spec text."})
    assert resp.status_code == 200, resp.text
    spec_id = resp.json()["spec_id"]

    reqs = client.get(f"/specs/{spec_id}/requirements").json()
    assert [r["text"] for r in reqs] == ["Read input", "Sort values", "Print result"]


def test_get_requirements_returns_items(client, monkeypatch):
    monkeypatch.setattr(
        spec_router.llm_client, "ask", _ask_yielding('["Item one", "Item two"]')
    )
    resp = client.post("/specs/import", data={"raw_text": "spec"})
    spec_id = resp.json()["spec_id"]

    reqs = client.get(f"/specs/{spec_id}/requirements")
    assert reqs.status_code == 200
    texts = [r["text"] for r in reqs.json()]
    assert texts == ["Item one", "Item two"]
    assert all(r["status"] == "not_started" for r in reqs.json())

    # Unknown spec id 404s.
    assert (
        client.get(
            "/specs/00000000-0000-0000-0000-000000000000/requirements"
        ).status_code
        == 404
    )


def test_patch_requirement_updates_status_and_text(client, monkeypatch):
    monkeypatch.setattr(spec_router.llm_client, "ask", _ask_yielding('["Original"]'))
    resp = client.post("/specs/import", data={"raw_text": "spec"})
    spec_id = resp.json()["spec_id"]
    req_id = client.get(f"/specs/{spec_id}/requirements").json()[0]["id"]

    patched = client.patch(
        f"/requirements/{req_id}",
        json={"status": "done", "text": "Rewritten requirement"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "done"
    assert patched.json()["text"] == "Rewritten requirement"


def test_attach_spec_to_session(client, monkeypatch):
    monkeypatch.setattr(spec_router.llm_client, "ask", _ask_yielding("[]"))
    session_id = _new_session(client)
    spec_id = client.post(
        "/specs/import", data={"raw_text": "spec"}
    ).json()["spec_id"]

    attached = client.post(f"/sessions/{session_id}/spec", json={"spec_id": spec_id})
    assert attached.status_code == 200, attached.text
    assert attached.json()["spec_id"] == spec_id

    # Reflected on subsequent reads.
    assert client.get(f"/sessions/{session_id}").json()["spec_id"] == spec_id


# === AI co-pilot (Direct mode) ==============================================


def test_ai_explain_error_returns_plain_language_and_emits_event(client, monkeypatch):
    explanation = "This means a variable was used before it was defined."
    monkeypatch.setattr(ai_router.llm_client, "ask", _ask_yielding(explanation))

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, content="print(y)")

    resp = client.post(
        "/ai/explain-error",
        json={"cell_id": cell["id"], "error_text": "NameError: name 'y'"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["explanation"] == explanation

    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert "ai_exchange" in timeline["groups"]
    exchange = timeline["groups"]["ai_exchange"][0]["payload"]
    assert exchange["kind"] == "explain_error"
    assert exchange["response"] == explanation


def test_ai_ask_direct_streams_tokens_and_emits_event(client, monkeypatch):
    monkeypatch.setattr(
        ai_router.llm_client, "ask", _ask_yielding("Here ", "is ", "a hint.")
    )

    session_id = _new_session(client)
    resp = client.post(
        "/ai/ask",
        json={"session_id": session_id, "question": "How do I start?"},
    )
    assert resp.status_code == 200, resp.text

    events = _parse_sse(resp.text)
    deltas = [e["delta"] for e in events if "delta" in e]
    assert "".join(deltas) == "Here is a hint."
    assert any(e.get("done") is True for e in events)

    # The exchange was appended to the event log after streaming finished.
    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert "ai_exchange" in timeline["groups"]
    assert timeline["groups"]["ai_exchange"][0]["payload"]["kind"] == "ask"


def test_ai_ask_full_solution_includes_fr_ai_6_flag(client, monkeypatch):
    full = ai_router._FULL_SOLUTION_PREFIX + "\ndef solve():\n    return 42\n"
    monkeypatch.setattr(ai_router.llm_client, "ask", _ask_yielding(full))

    session_id = _new_session(client)
    resp = client.post(
        "/ai/ask",
        json={"session_id": session_id, "question": "Just give me the answer."},
    )
    assert resp.status_code == 200, resp.text

    deltas = [e["delta"] for e in _parse_sse(resp.text) if "delta" in e]
    streamed = "".join(deltas)
    assert ai_router._FULL_SOLUTION_PREFIX in streamed


def test_ai_complexity_includes_verify_disclaimer(client, monkeypatch):
    # Model reply omits the disclaimer; the endpoint must append it (FR-AI-4).
    monkeypatch.setattr(
        ai_router.llm_client,
        "ask",
        _ask_yielding("Time is O(n), space is O(1)."),
    )

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, content="for x in a: pass")

    resp = client.post("/ai/complexity", json={"cell_id": cell["id"]})
    assert resp.status_code == 200, resp.text
    assert ai_router._VERIFY_LINE in resp.json()["analysis"]


def test_ai_ask_socratic_streams_tokens_and_logs_mode(client, monkeypatch):
    monkeypatch.setattr(
        ai_router.llm_client, "ask", _ask_yielding("What ", "have ", "you tried?")
    )

    session_id = _new_session(client)
    resp = client.post(
        "/ai/ask",
        json={
            "session_id": session_id,
            "question": "How do I start?",
            "mode": "socratic",
        },
    )
    assert resp.status_code == 200, resp.text

    events = _parse_sse(resp.text)
    deltas = [e["delta"] for e in events if "delta" in e]
    assert "".join(deltas) == "What have you tried?"
    assert any(e.get("done") is True for e in events)

    # Logged to the event log like any exchange, tagged with the Socratic mode.
    timeline = client.get(f"/sessions/{session_id}/timeline").json()
    assert "ai_exchange" in timeline["groups"]
    exchange = timeline["groups"]["ai_exchange"][0]["payload"]
    assert exchange["kind"] == "ask"
    assert exchange["mode"] == "socratic"


def test_ai_ask_socratic_explicit_answer_uses_full_solution_marker(client, monkeypatch):
    # FR-AI-6: when the student demands the answer, a volunteered full solution
    # carries the same marker Direct mode uses — no second marker is invented.
    full = ai_router._FULL_SOLUTION_PREFIX + "\ndef solve():\n    return 42\n"
    monkeypatch.setattr(ai_router.llm_client, "ask", _ask_yielding(full))

    session_id = _new_session(client)
    resp = client.post(
        "/ai/ask",
        json={
            "session_id": session_id,
            "question": "Stop asking questions and just give me the code.",
            "mode": "socratic",
        },
    )
    assert resp.status_code == 200, resp.text

    streamed = "".join(e["delta"] for e in _parse_sse(resp.text) if "delta" in e)
    assert ai_router._FULL_SOLUTION_PREFIX in streamed


def test_ai_ask_socratic_no_longer_returns_501(client, monkeypatch):
    # Regression: Socratic asks used to 501; they must now stream like Direct.
    monkeypatch.setattr(ai_router.llm_client, "ask", _ask_yielding("A small nudge."))

    session_id = _new_session(client)
    resp = client.post(
        "/ai/ask",
        json={"session_id": session_id, "question": "anything", "mode": "socratic"},
    )
    assert resp.status_code != 501
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("endpoint", ["explain-error", "complexity"])
def test_ai_non_streaming_llm_unreachable_503(client, monkeypatch, endpoint):
    monkeypatch.setattr(ai_router.llm_client, "ask", _ask_unavailable())

    session_id = _new_session(client)
    cell = _new_cell(client, session_id, content="print(1)")

    if endpoint == "explain-error":
        resp = client.post(
            "/ai/explain-error",
            json={"cell_id": cell["id"], "error_text": "boom"},
        )
    else:
        resp = client.post("/ai/complexity", json={"cell_id": cell["id"]})

    # Fails loudly with a clear status rather than returning a silent empty reply.
    assert resp.status_code == 503
    assert "reachable" in resp.json()["detail"].lower()


def test_ai_ask_llm_unreachable_streams_error(client, monkeypatch):
    monkeypatch.setattr(ai_router.llm_client, "ask", _ask_unavailable())

    session_id = _new_session(client)
    resp = client.post(
        "/ai/ask",
        json={"session_id": session_id, "question": "hello"},
    )
    # The stream itself carries the error; it does not silently complete.
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert any("error" in e for e in events)
    assert not any(e.get("done") is True for e in events)


# === Voice input (transcription) ============================================


def test_ai_transcribe_returns_transcript(client, monkeypatch):
    monkeypatch.setattr(
        ai_router.stt_client, "transcribe", _stt_returning("hello from voice")
    )

    resp = client.post(
        "/ai/transcribe",
        files={"audio": ("clip.webm", b"\x00\x01\x02fake-audio", "audio/webm")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["transcript"] == "hello from voice"


def test_ai_transcribe_stt_unreachable_returns_503_not_500(client, monkeypatch):
    monkeypatch.setattr(ai_router.stt_client, "transcribe", _stt_unavailable())

    resp = client.post(
        "/ai/transcribe",
        files={"audio": ("clip.webm", b"\x00\x01\x02fake-audio", "audio/webm")},
    )
    # A dead whisper-server is a clean 503, not a 500 stack trace.
    assert resp.status_code == 503, resp.text
    assert "reachable" in resp.json()["detail"].lower()
