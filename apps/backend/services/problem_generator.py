"""Prompt construction and response parsing for generated practice problems.

The practice feature's "more like this" flow: when the user struggles on a
problem, the local model writes a *new* problem that exercises the same
pattern with a different surface story, so they can re-attempt the idea
without memorizing the original. This module owns the two pure pieces —
building the chat messages and parsing the model's reply into a problem
dict — so the router stays thin and the tests can hit them directly.

Small local models are unreliable JSON emitters: they wrap output in
markdown fences, add prose before/after, or drop fields. ``parse_generated_
problem`` therefore extracts the first balanced JSON object from anywhere
in the text and validates/coerces the fields, returning ``None`` (rather
than raising) when nothing usable is found.
"""

from __future__ import annotations

import json

from models import Problem, ProblemDifficulty

# Hard ceilings so a runaway model reply can't bloat the database row or the
# practice UI. Generously above what a real problem needs.
_MAX_TEXT_CHARS = 8000
_MAX_LIST_ITEMS = 6

_GENERATOR_ROLE = (
    "You are Whetstone's practice-problem author. You write ORIGINAL coding "
    "interview practice problems for a student, exercising a specific "
    "algorithmic pattern. You never copy a known problem verbatim; you "
    "change the story, the variable names, and the surface details while "
    "keeping the underlying pattern the same."
)

_OUTPUT_CONTRACT = (
    "Reply with ONLY a single JSON object — no markdown fences, no prose "
    "before or after — with exactly these fields:\n"
    "{\n"
    '  "title": "short evocative title",\n'
    '  "difficulty": "easy" | "medium" | "hard",\n'
    '  "prompt": "full problem statement: the story, the precise task, '
    'input/output format, and constraints",\n'
    '  "examples": [{"input": "...", "output": "...", "explanation": "..."}],\n'
    '  "hints": ["smallest nudge", "bigger hint", "near-spoiler"],\n'
    '  "starter_code": "runnable Python: a function stub plus 2-3 print() '
    'checks with expected values in comments"\n'
    "}\n"
    "Give 2 examples and exactly 3 graded hints. The starter_code must be "
    "plain Python (no external packages) and must run as-is."
)


def build_generation_messages(
    source: Problem, struggle_note: str | None, user_code: str | None
) -> list[dict]:
    """Build the chat messages asking the model for a variant of ``source``.

    ``struggle_note`` is the user's own words about what tripped them up;
    ``user_code`` is their (possibly wrong) attempt. Both are optional and,
    when present, steer the variant toward the part they found hard.
    """

    parts = [
        f"Write a NEW practice problem exercising the **{source.pattern}** "
        f"pattern, at **{source.difficulty.value}** difficulty.",
        "It must teach the same algorithmic move as this problem, but with a "
        "completely different story and surface details:\n\n"
        f"--- SOURCE PROBLEM: {source.title} ---\n{source.prompt}",
    ]
    if struggle_note and struggle_note.strip():
        parts.append(
            "The student said this about why they struggled — design the "
            f"variant so practicing it targets exactly that:\n{struggle_note.strip()}"
        )
    if user_code and user_code.strip():
        parts.append(
            "The student's attempt at the source problem (it may be wrong "
            "or incomplete):\n```python\n"
            f"{user_code.strip()}\n```"
        )
    parts.append(_OUTPUT_CONTRACT)

    return [
        {"role": "system", "content": _GENERATOR_ROLE},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def parse_generated_problem(text: str) -> dict | None:
    """Parse the model's reply into a validated problem dict, or ``None``.

    Tolerates fenced/prose-wrapped replies by extracting the first balanced
    ``{...}`` object. Returns a dict with keys ``title``, ``difficulty``
    (a :class:`ProblemDifficulty`), ``prompt``, ``examples`` (list of
    dicts), ``hints`` (list of str), ``starter_code`` — or ``None`` when
    the reply has no usable object (missing/empty title or prompt).
    """

    obj = _first_json_object(text)
    if not isinstance(obj, dict):
        return None

    title = _clean_str(obj.get("title"))
    prompt = _clean_str(obj.get("prompt"))
    if not title or not prompt:
        return None

    return {
        "title": title[:200],
        "difficulty": _coerce_difficulty(obj.get("difficulty")),
        "prompt": prompt,
        "examples": _coerce_examples(obj.get("examples")),
        "hints": _coerce_hints(obj.get("hints")),
        "starter_code": _clean_str(obj.get("starter_code")) or "",
    }


def _first_json_object(text: str):
    """Return the first balanced top-level JSON object decoded from ``text``.

    Scans for ``{`` and tracks brace depth (string- and escape-aware) to find
    the matching ``}``, then attempts ``json.loads`` on that span. Moves on
    to the next ``{`` on a decode failure, so a stray brace in leading prose
    doesn't sink the parse.
    """

    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def _clean_str(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:_MAX_TEXT_CHARS]


def _coerce_difficulty(value) -> ProblemDifficulty:
    if isinstance(value, str):
        try:
            return ProblemDifficulty(value.strip().lower())
        except ValueError:
            pass
    return ProblemDifficulty.medium


def _coerce_examples(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    examples = []
    for item in value[:_MAX_LIST_ITEMS]:
        if not isinstance(item, dict):
            continue
        example = {
            "input": _clean_str(item.get("input")),
            "output": _clean_str(item.get("output")),
            "explanation": _clean_str(item.get("explanation")),
        }
        if example["input"] or example["output"]:
            examples.append(example)
    return examples


def _coerce_hints(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        _clean_str(item) for item in value[:_MAX_LIST_ITEMS] if _clean_str(item)
    ]
