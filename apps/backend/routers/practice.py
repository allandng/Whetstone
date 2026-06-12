"""Routes for the Practice area: the beginner course and the DSA problem bank.

Two halves, one feature: *learn to code* (a fixed beginner course served
from :mod:`content.course`, with per-lesson completion stored in
:class:`models.LessonProgress`) and *DSA practice* (a bank of
pattern-organized problems in :class:`models.Problem`, seeded from
:mod:`content.problems` and grown by the local model).

- ``GET    /practice/problems``               - list, with optional filters.
- ``GET    /practice/problems/{id}``          - one problem.
- ``PATCH  /practice/problems/{id}``          - update progress status.
- ``POST   /practice/problems/{id}/start``    - open it in the Workspace.
- ``POST   /practice/problems/{id}/similar``  - generate a variant (local LLM).
- ``GET    /practice/course``                 - lessons merged with progress.
- ``PATCH  /practice/course/{lesson_id}``     - mark a lesson (in)complete.
- ``POST   /practice/course/{lesson_id}/start`` - open its exercise in the Workspace.

The "start" routes reuse the existing workspace machinery rather than
duplicating it: they create a Session whose Spec carries the statement,
whose RequirementItems form a working checklist, and whose first Cell is
the starter code — so running code (Psirver), the AI tutor, and the
timeline all work on practice sessions with zero new plumbing.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession
from sqlmodel import select

from content.course import COURSE_LESSONS, lesson_by_id
from content.problems import PATTERN_LABELS, SEED_PROBLEMS
from db import get_session, session_scope
from events import emit_event
from models import (
    Cell,
    CellType,
    LessonProgress,
    Problem,
    ProblemDifficulty,
    ProblemSource,
    ProblemStatus,
    RequirementItem,
    RequirementStatus,
    Session as SessionModel,
    SourceType,
    Spec,
)
from schemas import (
    GenerateSimilarRequest,
    LessonProgressUpdate,
    LessonRead,
    PracticeStartResponse,
    ProblemRead,
    ProblemUpdate,
)
from services.llm_client import LLMClient, LLMUnavailableError
from services.problem_generator import (
    build_generation_messages,
    parse_generated_problem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["practice"])

llm_client = LLMClient()

_DIFFICULTY_RANK = {
    ProblemDifficulty.easy: 0,
    ProblemDifficulty.medium: 1,
    ProblemDifficulty.hard: 2,
}


def seed_builtin_problems() -> None:
    """Insert any built-in problems not already in the database.

    Idempotent (keyed by ``slug``), so it runs on every startup: a fresh
    database gets the full bank, an existing one gets only newly shipped
    problems, and user edits to progress status are never touched.
    """

    with session_scope() as db:
        existing = set(db.exec(select(Problem.slug)).all())
        added = 0
        for spec in SEED_PROBLEMS:
            if spec["slug"] in existing:
                continue
            db.add(
                Problem(
                    slug=spec["slug"],
                    title=spec["title"],
                    pattern=spec["pattern"],
                    difficulty=ProblemDifficulty(spec["difficulty"]),
                    prompt=spec["prompt"],
                    examples=json.dumps(spec["examples"]),
                    hints=json.dumps(spec["hints"]),
                    starter_code=spec["starter_code"],
                    language="python",
                    source=ProblemSource.builtin,
                )
            )
            added += 1
        if added:
            db.commit()
            logger.info("Seeded %d built-in practice problems.", added)


# --- Problems ----------------------------------------------------------------


@router.get("/problems", response_model=list[ProblemRead])
async def list_problems(
    pattern: str | None = None,
    difficulty: ProblemDifficulty | None = None,
    status: ProblemStatus | None = None,
    db: DBSession = Depends(get_session),
) -> list[ProblemRead]:
    """List problems, optionally filtered, in pattern/difficulty order."""

    query = select(Problem)
    if pattern is not None:
        query = query.where(Problem.pattern == pattern)
    if difficulty is not None:
        query = query.where(Problem.difficulty == difficulty)
    if status is not None:
        query = query.where(Problem.status == status)

    rows = list(db.exec(query).all())
    # Difficulty has a semantic order (easy < medium < hard) that the enum's
    # alphabetical SQL ordering would scramble, so sort in Python.
    rows.sort(
        key=lambda p: (
            p.pattern,
            _DIFFICULTY_RANK.get(p.difficulty, 99),
            p.created_at,
        )
    )
    return [_to_read(row) for row in rows]


@router.get("/problems/{problem_id}", response_model=ProblemRead)
async def get_problem(
    problem_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> ProblemRead:
    """Fetch a single problem by id."""

    return _to_read(_require_problem(db, problem_id))


@router.patch("/problems/{problem_id}", response_model=ProblemRead)
async def update_problem(
    problem_id: uuid.UUID,
    body: ProblemUpdate,
    db: DBSession = Depends(get_session),
) -> ProblemRead:
    """Update the user's progress status on a problem."""

    problem = _require_problem(db, problem_id)
    problem.status = body.status
    db.add(problem)
    db.commit()
    db.refresh(problem)
    return _to_read(problem)


@router.post("/problems/{problem_id}/start", response_model=PracticeStartResponse)
async def start_problem(
    problem_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> PracticeStartResponse:
    """Create a workspace session seeded with this problem.

    The problem statement becomes the session's Spec, a working checklist
    becomes its RequirementItems, and the starter code becomes the first
    cell. Also bumps a never-touched problem to ``attempted``.
    """

    problem = _require_problem(db, problem_id)

    checklist = [
        "Restate the problem in your own words and work the examples by hand",
        f"Implement: {problem.title} ({_pattern_label(problem.pattern)} pattern)",
        "Run your solution against the example checks in the starter code",
        "State the time and space complexity of your solution",
    ]
    header = (
        f"# {problem.title} — {_pattern_label(problem.pattern)}, "
        f"{problem.difficulty.value}\n"
        "# Full statement and hints: Practice tab. Checklist: left pane.\n\n"
    )
    response = _start_session(
        db,
        title=f"Practice: {problem.title}",
        spec_text=problem.prompt,
        checklist=checklist,
        cell_language=problem.language,
        cell_content=header + problem.starter_code,
        event_payload={
            "kind": "problem",
            "problem_id": str(problem.id),
            "title": problem.title,
        },
    )

    if problem.status == ProblemStatus.not_started:
        problem.status = ProblemStatus.attempted
        db.add(problem)
        db.commit()

    return response


@router.post("/problems/{problem_id}/similar", response_model=ProblemRead)
async def generate_similar(
    problem_id: uuid.UUID,
    body: GenerateSimilarRequest | None = None,
    db: DBSession = Depends(get_session),
) -> ProblemRead:
    """Have the local model write a fresh variant of this problem.

    The variant exercises the same pattern with a new story, optionally
    steered by the user's note about what they struggled with and their
    attempted code. A dead llama-server is a 503; a reply we cannot parse
    into a problem is a 502 (the model spoke, but not usably).
    """

    source = _require_problem(db, problem_id)
    body = body or GenerateSimilarRequest()

    messages = build_generation_messages(source, body.note, body.code)
    try:
        chunks = [
            chunk
            async for chunk in llm_client.ask(messages, stream=False, thinking=False)
        ]
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    parsed = parse_generated_problem("".join(chunks))
    if parsed is None:
        raise HTTPException(
            status_code=502,
            detail=(
                "The local model's reply could not be parsed into a problem. "
                "Try again — small models occasionally drop the format."
            ),
        )

    variant = Problem(
        slug=f"{source.slug}-variant-{uuid.uuid4().hex[:8]}",
        title=parsed["title"],
        pattern=source.pattern,
        difficulty=parsed["difficulty"],
        prompt=parsed["prompt"],
        examples=json.dumps(parsed["examples"]),
        hints=json.dumps(parsed["hints"]),
        starter_code=parsed["starter_code"],
        language=source.language,
        source=ProblemSource.generated,
        parent_problem_id=source.id,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return _to_read(variant)


# --- Course ------------------------------------------------------------------


@router.get("/course", response_model=list[LessonRead])
async def list_course(db: DBSession = Depends(get_session)) -> list[LessonRead]:
    """Return the course lessons in order, merged with completion state."""

    completed = {
        row.lesson_id
        for row in db.exec(
            select(LessonProgress).where(LessonProgress.completed == True)  # noqa: E712
        ).all()
    }
    return [
        _to_lesson_read(lesson, lesson["id"] in completed)
        for lesson in COURSE_LESSONS
    ]


@router.patch("/course/{lesson_id}", response_model=LessonRead)
async def update_lesson_progress(
    lesson_id: str,
    body: LessonProgressUpdate,
    db: DBSession = Depends(get_session),
) -> LessonRead:
    """Mark a lesson complete or incomplete (upsert keyed by lesson id)."""

    lesson = lesson_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    progress = db.get(LessonProgress, lesson_id)
    if progress is None:
        progress = LessonProgress(lesson_id=lesson_id)
    progress.completed = body.completed
    db.add(progress)
    db.commit()
    return _to_lesson_read(lesson, body.completed)


@router.post("/course/{lesson_id}/start", response_model=PracticeStartResponse)
async def start_lesson(
    lesson_id: str, db: DBSession = Depends(get_session)
) -> PracticeStartResponse:
    """Create a workspace session seeded with this lesson's exercise."""

    lesson = lesson_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    exercise = lesson["exercise"]
    checklist = [
        f"Read the lesson: {lesson['title']}",
        f"Exercise: {exercise['description']}",
        "Run your code and check the output against the expectations",
    ]
    header = (
        f"# Lesson: {lesson['title']}\n"
        f"# {exercise['description']}\n\n"
    )
    return _start_session(
        db,
        title=f"Course: {lesson['title']}",
        spec_text=f"{lesson['title']}\n\n{lesson['body']}",
        checklist=checklist,
        cell_language=exercise.get("language", "python"),
        cell_content=header + exercise["starter_code"],
        event_payload={
            "kind": "lesson",
            "lesson_id": lesson_id,
            "title": lesson["title"],
        },
    )


# --- Helpers -----------------------------------------------------------------


def _require_problem(db: DBSession, problem_id: uuid.UUID) -> Problem:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found.")
    return problem


def _pattern_label(pattern: str) -> str:
    return PATTERN_LABELS.get(pattern, pattern.replace("-", " ").title())


def _to_read(problem: Problem) -> ProblemRead:
    """Build a :class:`ProblemRead`, decoding the JSON-string columns."""

    return ProblemRead(
        id=problem.id,
        slug=problem.slug,
        title=problem.title,
        pattern=problem.pattern,
        pattern_label=_pattern_label(problem.pattern),
        difficulty=problem.difficulty,
        prompt=problem.prompt,
        examples=_decode_list(problem.examples),
        hints=_decode_list(problem.hints),
        starter_code=problem.starter_code,
        language=problem.language,
        source=problem.source,
        parent_problem_id=problem.parent_problem_id,
        status=problem.status,
        created_at=problem.created_at,
    )


def _decode_list(raw: str) -> list:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def _to_lesson_read(lesson: dict, completed: bool) -> LessonRead:
    return LessonRead(
        id=lesson["id"],
        title=lesson["title"],
        summary=lesson["summary"],
        body=lesson["body"],
        exercise=lesson["exercise"],
        completed=completed,
    )


def _start_session(
    db: DBSession,
    *,
    title: str,
    spec_text: str,
    checklist: list[str],
    cell_language: str,
    cell_content: str,
    event_payload: dict,
) -> PracticeStartResponse:
    """Create the Spec + RequirementItems + Session + starter Cell bundle.

    This is the bridge from Practice into the existing workspace: everything
    it creates is ordinary workspace data, so cell runs, the tutor, and the
    timeline need no special cases. A ``practice_start`` event opens the
    session's timeline so replay shows where the session came from.
    """

    spec = Spec(source_type=SourceType.text, raw_text=spec_text)
    db.add(spec)
    db.commit()
    db.refresh(spec)

    for text in checklist:
        db.add(
            RequirementItem(
                spec_id=spec.id,
                text=text,
                status=RequirementStatus.not_started,
            )
        )

    session = SessionModel(title=title, spec_id=spec.id)
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add(
        Cell(
            session_id=session.id,
            cell_type=CellType.code,
            language=cell_language,
            content=cell_content,
            order_index=0,
        )
    )
    db.commit()

    emit_event(
        db,
        session_id=session.id,
        event_type="practice_start",
        payload=event_payload,
    )

    return PracticeStartResponse(session_id=session.id, spec_id=spec.id)
