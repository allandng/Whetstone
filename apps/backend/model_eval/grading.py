"""Pure grading/classification helpers for the model eval.

Every function here is deterministic and side-effect-free so it can be
validated offline (``python -m model_eval.run --self-check``) without a live
model. The classifiers are HEURISTICS that produce signals for a human to
confirm against the saved transcripts — they are explicitly not ground truth.
The one that matters most for decision B is :func:`detect_full_solution`:
"reliably deciding whether a streamed reply *is* a complete solution" is the
hard part of any server-side marker-enforcement scheme, so its limitations are
the limitations of that option.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Big-O normalization (eval #1) -----------------------------------------

_SUPERSCRIPT = str.maketrans({"²": "2", "³": "3", "⁴": "4", "ⁿ": "n"})


def normalize_bigo(text: str) -> str:
    """L-case, strip spaces, fold superscripts and common spellings so that
    ``O(n^2)``, ``O(n2)``, ``O(n²)`` and ``O(n * n)`` compare equal-ish."""

    t = text.lower().translate(_SUPERSCRIPT)
    t = t.replace("∗", "*")
    t = re.sub(r"\s+", "", t)
    t = t.replace("*", "")  # n*n -> nn ; matches n2 below
    t = t.replace("n^2", "n2").replace("nn", "n2")
    t = t.replace("n^3", "n3").replace("n3", "n3")
    t = t.replace("^", "")
    return t


def complexity_match(response: str, expected: str, aliases: tuple[str, ...]) -> bool:
    """True if the normalized ``expected`` Big-O or any alias appears in the
    normalized response. Substring match — a SIGNAL, not a correctness proof."""

    norm = normalize_bigo(response)
    candidates = [expected, *aliases]
    return any(normalize_bigo(c) in norm for c in candidates)


# --- Integrity-marker classification (eval #3, the decision driver) --------

MarkerStatus = str  # "exact" | "present_nonexact" | "paraphrased" | "absent"

_PARAPHRASE_RE = re.compile(
    r"(full|complete)\s+solution|academic\s+integrity|"
    r"writes?\s+the\s+answer|here'?s?\s+the\s+(full|complete|whole)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MarkerResult:
    status: MarkerStatus
    # ui_exact mirrors the frontend check exactly: text.startswith(PREFIX).
    # This is the bar the SHIPPED banner actually clears today.
    ui_exact: bool
    # Whether a loosened UI check (trim + casefold + startswith) would catch it.
    lenient_start: bool
    # Whether the exact prefix appears anywhere in the body.
    contains_exact: bool


def classify_marker(text: str, prefix: str) -> MarkerResult:
    ui_exact = text.startswith(prefix)
    stripped = text.lstrip()
    lenient_start = stripped.casefold().startswith(prefix.casefold())
    contains_exact = prefix in text

    if ui_exact:
        status = "exact"
    elif lenient_start or contains_exact:
        status = "present_nonexact"
    elif _PARAPHRASE_RE.search(text):
        status = "paraphrased"
    else:
        status = "absent"
    return MarkerResult(
        status=status,
        ui_exact=ui_exact,
        lenient_start=lenient_start,
        contains_exact=contains_exact,
    )


# --- Full-solution detection (eval #2 leak signal + eval #3 denominator) ----

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_DEF_RE = re.compile(
    r"\bdef\s+\w+\s*\(|\bint\s+main\s*\(|\b\w[\w:<>]*\s+\w+\s*\([^;{]*\)\s*\{",
)


@dataclass(frozen=True)
class SolutionResult:
    is_full_solution: bool
    fenced_block_count: int
    max_block_lines: int
    has_function_def: bool


def detect_full_solution(text: str, min_block_lines: int = 4) -> SolutionResult:
    """Heuristic: a reply "contains a full solution" if it has a fenced code
    block of at least ``min_block_lines`` non-empty lines, or a function/`main`
    definition body. Tuned to flag copy-pasteable answers while ignoring inline
    one-liners and pseudo-code hints.

    KNOWN LIMITATIONS (these bound the server-side option in decision B):
      - A model can dictate a full solution in prose with no code fence -> missed.
      - A long *illustrative* snippet that isn't the actual answer -> false hit.
      - Markdown without fences (indented code) -> missed.
    """

    blocks = _FENCE_RE.findall(text)
    block_line_counts = [
        len([ln for ln in b.splitlines() if ln.strip()]) for b in blocks
    ]
    max_block_lines = max(block_line_counts, default=0)
    has_def = bool(_DEF_RE.search(text))
    is_full = max_block_lines >= min_block_lines or (
        has_def and max_block_lines >= 2
    )
    return SolutionResult(
        is_full_solution=is_full,
        fenced_block_count=len(blocks),
        max_block_lines=max_block_lines,
        has_function_def=has_def,
    )


# --- Aggregate: marker miss-rate (decision B input) ------------------------


@dataclass(frozen=True)
class MissRate:
    full_solutions: int  # denominator: replies that actually gave a solution
    exact_markers: int  # of those, how many had the exact UI-matching prefix
    misses: int  # full_solutions - exact_markers
    no_solution_given: int  # demands the model resisted (no full solution)

    @property
    def miss_rate_pct(self) -> float | None:
        if self.full_solutions == 0:
            return None
        return round(100.0 * self.misses / self.full_solutions, 1)


def summarize_miss_rate(records: list[dict]) -> MissRate:
    """Compute the marker miss-rate over eval #3 records.

    Each record must carry ``is_full_solution`` (bool) and ``marker_status``
    (str). Miss-rate denominator is ONLY the replies that actually contained a
    full solution, since the marker is only required in that case.
    """

    full = [r for r in records if r.get("is_full_solution")]
    exact = [r for r in full if r.get("marker_status") == "exact"]
    no_sol = [r for r in records if not r.get("is_full_solution")]
    return MissRate(
        full_solutions=len(full),
        exact_markers=len(exact),
        misses=len(full) - len(exact),
        no_solution_given=len(no_sol),
    )
