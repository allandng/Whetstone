"""Spec parsing helpers: PDF text extraction and requirement extraction.

The router (:mod:`routers.spec`) owns the request/response and background-task
orchestration; this module holds the two pieces of logic worth isolating:

- :func:`extract_pdf_text`        - pull plain text out of an uploaded PDF.
- :func:`build_extraction_messages` / :func:`parse_requirements` - the LLM
  prompt for turning a spec into a checklist, and a tolerant parser for the
  model's reply.

The extraction prompt asks the model for a bare JSON array of strings, but a
small local model often wraps it in prose or a markdown fence, so
:func:`parse_requirements` recovers the array rather than trusting the reply to
be clean JSON.
"""

from __future__ import annotations

import io
import json
import re

# FR-SPEC-2: one concrete, testable obligation per checklist item. Verbatim per
# the product spec so the extraction behavior is auditable.
_EXTRACTION_SYSTEM_PROMPT = (
    "You are parsing a CS assignment spec. Extract every discrete, testable "
    "requirement as a JSON array of strings. Each item should be one concrete "
    "obligation. Return only the JSON array, no commentary."
)


def extract_pdf_text(data: bytes) -> str:
    """Return the concatenated text of every page in a PDF byte string.

    ``pdfplumber`` is imported lazily so the backend still boots (and non-PDF
    imports still work) on an environment where the optional native deps are
    missing; the import only matters when a PDF is actually uploaded.
    """

    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()


def build_extraction_messages(raw_text: str) -> list[dict]:
    """Build the chat messages that ask the LLM to extract requirements."""

    return [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": raw_text},
    ]


def parse_requirements(text: str) -> list[str]:
    """Parse the model's reply into a list of requirement strings.

    Tolerates a leading/trailing prose or a ```json fence: each balanced
    ``[...]`` span is tried in turn and the first that decodes to a JSON list
    wins, so brackets appearing in prose before the real array don't derail
    parsing. Non-string entries are coerced to ``str``; empty/whitespace items
    are dropped. Returns ``[]`` if no JSON array is found.
    """

    text = _strip_code_fence(text)
    for array_text in _iter_json_arrays(text):
        try:
            parsed = json.loads(array_text)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue
        requirements: list[str] = []
        for item in parsed:
            value = item if isinstance(item, str) else json.dumps(item)
            value = value.strip()
            if value:
                requirements.append(value)
        return requirements
    return []


def _iter_json_arrays(text: str):
    """Yield each balanced ``[...]`` substring, outermost first, left to right.

    String contents are skipped so brackets inside quoted strings don't affect
    nesting depth.
    """

    i = 0
    n = len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth = 0
        in_string = False
        escaped = False
        for j in range(i, n):
            ch = text[j]
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
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    yield text[i : j + 1]
                    break
        i += 1


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```/```json markdown fence if present."""

    fenced = re.match(r"\s*```[a-zA-Z]*\n(.*?)```\s*$", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    return text
