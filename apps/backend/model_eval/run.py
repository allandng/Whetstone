"""Model-quality eval runner (SRS §9.3 spike). Requires a live llama-server.

Usage (from apps/backend, with llama-server running on the configured port)::

    python -m model_eval.run --model-label "gemma-4-e4b" --only all
    python -m model_eval.run --model-label "gemma-26b-a4b" --variant baseline
    python -m model_eval.run --self-check          # offline; validates grading

Results are written as JSON under model_eval/results/ and a paste-ready
markdown summary is printed to stdout for docs/model-eval.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import datasets as ds
from . import grading as g

# LLMClient is imported lazily inside the async path so that --self-check works
# even if the backend package or its deps aren't importable in some checkout.

_RESULTS_DIR = Path(__file__).parent / "results"


# --- LLM transport ---------------------------------------------------------


async def _ask(client, messages: list[dict], thinking: bool) -> str:
    """Collect a full (non-streamed) reply. Mirrors how routers/ai.py calls the
    client: ask() uses thinking=False, complexity() uses thinking=True."""

    chunks = [c async for c in client.ask(messages, stream=False, thinking=thinking)]
    return "".join(chunks)


async def _probe(client) -> None:
    from services.llm_client import LLMUnavailableError  # local import

    try:
        await _ask(client, [{"role": "user", "content": "Reply with: ok"}], False)
    except LLMUnavailableError as exc:
        print(f"\nllama-server is not reachable — cannot run live evals.\n  {exc}\n", file=sys.stderr)
        raise SystemExit(2) from exc


# --- Eval #1: complexity correctness ---------------------------------------


async def run_complexity(client, variant: str) -> list[dict]:
    records: list[dict] = []
    for case in ds.COMPLEXITY_CASES:
        context = (
            f"Referenced cell (type=code, language={case.language}):\n"
            f"```\n{case.code}\n```"
        )
        messages = [
            {"role": "system", "content": ds.direct_system_prompt(context)},
            {"role": "user", "content": ds.COMPLEXITY_USER_PROMPT},
        ]
        reply = await _ask(client, messages, thinking=True)
        time_ok = g.complexity_match(reply, case.expected_time, case.time_aliases)
        space_ok = g.complexity_match(reply, case.expected_space, case.space_aliases)
        records.append(
            {
                "case_id": case.id,
                "expected_time": case.expected_time,
                "expected_space": case.expected_space,
                "time_match": time_ok,
                "space_match": space_ok,
                "both_match": time_ok and space_ok,
                "reply": reply,
            }
        )
        print(f"  [#1 complexity] {case.id}: time={time_ok} space={space_ok}")
    return records


# --- Eval #2: Socratic restraint across a hint chain -----------------------


async def run_socratic(client, variant: str) -> list[dict]:
    records: list[dict] = []
    for sc in ds.SOCRATIC_SCENARIOS:
        system = ds.socratic_system_prompt(variant)
        messages: list[dict] = [{"role": "system", "content": system}]
        turns: list[dict] = []
        student_turns = [sc.opening, *sc.follow_ups]
        for turn_idx, student in enumerate(student_turns):
            messages.append({"role": "user", "content": student})
            reply = await _ask(client, messages, thinking=False)
            messages.append({"role": "assistant", "content": reply})
            sol = g.detect_full_solution(reply)
            marker = g.classify_marker(reply, ds.FULL_SOLUTION_PREFIX)
            is_giveup_turn = turn_idx == len(student_turns) - 1
            turns.append(
                {
                    "turn": turn_idx,
                    "is_giveup_turn": is_giveup_turn,
                    "student": student,
                    "is_full_solution": sol.is_full_solution,
                    "max_block_lines": sol.max_block_lines,
                    "marker_status": marker.status,
                    # A leak = handed over a full solution BEFORE the give-up turn.
                    "leaked_early": sol.is_full_solution and not is_giveup_turn,
                    "reply": reply,
                }
            )
            print(
                f"  [#2 socratic] {sc.id} t{turn_idx}: "
                f"full_sol={sol.is_full_solution} leaked_early="
                f"{sol.is_full_solution and not is_giveup_turn} marker={marker.status}"
            )
        records.append({"scenario_id": sc.id, "variant": variant, "turns": turns})
    return records


# --- Eval #3: integrity-marker reliability ---------------------------------


async def run_marker(client, variant: str) -> list[dict]:
    records: list[dict] = []
    for case in ds.build_marker_cases():
        system = ds.socratic_system_prompt(variant)
        messages: list[dict] = [{"role": "system", "content": system}]
        if case.prior_hint_turn:
            messages.append(
                {"role": "user", "content": f"Help me {case.task}."}
            )
            first = await _ask(client, messages, thinking=False)
            messages.append({"role": "assistant", "content": first})
        messages.append({"role": "user", "content": case.demand})
        reply = await _ask(client, messages, thinking=False)
        sol = g.detect_full_solution(reply)
        marker = g.classify_marker(reply, ds.FULL_SOLUTION_PREFIX)
        records.append(
            {
                "case_id": case.id,
                "task": case.task,
                "demand": case.demand,
                "is_full_solution": sol.is_full_solution,
                "marker_status": marker.status,
                "ui_exact": marker.ui_exact,
                "lenient_start": marker.lenient_start,
                "max_block_lines": sol.max_block_lines,
                "reply": reply,
            }
        )
        print(
            f"  [#3 marker] {case.id}: full_sol={sol.is_full_solution} "
            f"marker={marker.status} ui_exact={marker.ui_exact}"
        )
    return records


# --- Summary + persistence -------------------------------------------------


def _summarize(model_label: str, variant: str, results: dict) -> str:
    lines = [
        f"### Run: {model_label} (variant: {variant})",
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_",
        "",
    ]
    if "complexity" in results:
        recs = results["complexity"]
        both = sum(r["both_match"] for r in recs)
        t_ok = sum(r["time_match"] for r in recs)
        s_ok = sum(r["space_match"] for r in recs)
        n = len(recs)
        lines += [
            "**#1 Complexity correctness** (substring signal; spot-check transcripts)",
            f"- both time+space correct: {both}/{n}",
            f"- time correct: {t_ok}/{n} · space correct: {s_ok}/{n}",
            "",
        ]
    if "socratic" in results:
        recs = results["socratic"]
        leaks = sum(
            any(t["leaked_early"] for t in r["turns"]) for r in recs
        )
        revealed_on_giveup = sum(
            any(t["is_giveup_turn"] and t["is_full_solution"] for t in r["turns"])
            for r in recs
        )
        n = len(recs)
        lines += [
            "**#2 Socratic restraint** (per-scenario; read transcripts to confirm)",
            f"- scenarios that leaked a full solution BEFORE give-up: {leaks}/{n}",
            f"- scenarios that revealed on the give-up turn (FR-SOC-4): {revealed_on_giveup}/{n}",
            "",
        ]
    if "marker" in results:
        mr = g.summarize_miss_rate(results["marker"])
        pct = "n/a" if mr.miss_rate_pct is None else f"{mr.miss_rate_pct}%"
        lines += [
            "**#3 Integrity-marker reliability** (decision driver)",
            f"- explicit demands run: {len(results['marker'])}",
            f"- replies that actually contained a full solution: {mr.full_solutions}",
            f"- of those, exact UI-matching marker: {mr.exact_markers}",
            f"- **marker miss-rate: {pct}** ({mr.misses}/{mr.full_solutions} missed)",
            f"- demands the model resisted (no full solution): {mr.no_solution_given}",
            "",
        ]
    return "\n".join(lines)


def _persist(model_label: str, variant: str, results: dict) -> Path:
    _RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = model_label.replace("/", "_").replace(" ", "-")
    path = _RESULTS_DIR / f"{safe}-{variant}-{stamp}.json"
    path.write_text(
        json.dumps(
            {"model_label": model_label, "variant": variant, "results": results},
            indent=2,
        )
    )
    return path


# --- Offline self-check (no server) ----------------------------------------


def self_check() -> int:
    """Validate the grading classifiers against hand-written fixtures. Runs with
    no llama-server so the harness logic can be verified in any environment."""

    p = ds.FULL_SOLUTION_PREFIX
    failures: list[str] = []

    def expect(name: str, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # classify_marker
    expect("exact", g.classify_marker(p + "\ncode here", p).status, "exact")
    expect("exact.ui", g.classify_marker(p + "\nx", p).ui_exact, True)
    expect(
        "nonexact.leading-space",
        g.classify_marker("  " + p + "\nx", p).status,
        "present_nonexact",
    )
    expect(
        "nonexact.midbody",
        g.classify_marker("Sure!\n" + p + "\nx", p).status,
        "present_nonexact",
    )
    expect(
        "paraphrased",
        g.classify_marker("Here's the complete solution:\n```\n...\n```", p).status,
        "paraphrased",
    )
    expect("absent", g.classify_marker("Here is a small hint.", p).status, "absent")
    expect(
        "nonexact.not-ui-exact",
        g.classify_marker("  " + p + "\nx", p).ui_exact,
        False,
    )
    expect(
        "nonexact.lenient-catches",
        g.classify_marker("  " + p + "\nx", p).lenient_start,
        True,
    )

    # detect_full_solution
    big = "```python\n" + "\n".join(f"line{i} = {i}" for i in range(6)) + "\n```"
    expect("full.codeblock", g.detect_full_solution(big).is_full_solution, True)
    expect(
        "full.def",
        g.detect_full_solution("```\ndef f(x):\n    return x\n```").is_full_solution,
        True,
    )
    expect(
        "notfull.hint",
        g.detect_full_solution("Think about two pointers. What invariant holds?").is_full_solution,
        False,
    )
    expect(
        "notfull.oneliner",
        g.detect_full_solution("Try `x in seen` for the check.").is_full_solution,
        False,
    )

    # complexity_match (normalization)
    expect("cx.caret", g.complexity_match("This is O(n^2).", "O(n^2)", ()), True)
    expect("cx.super", g.complexity_match("It is O(n²) time.", "O(n^2)", ()), True)
    expect("cx.alias", g.complexity_match("quadratic time", "O(n^2)", ("quadratic",)), True)
    expect("cx.miss", g.complexity_match("This is O(n).", "O(n^2)", ("quadratic",)), False)
    expect("cx.nlogn", g.complexity_match("runs in O(n log n)", "O(n log n)", ()), True)

    # summarize_miss_rate
    sample = [
        {"is_full_solution": True, "marker_status": "exact"},
        {"is_full_solution": True, "marker_status": "absent"},
        {"is_full_solution": True, "marker_status": "paraphrased"},
        {"is_full_solution": False, "marker_status": "absent"},
    ]
    mr = g.summarize_miss_rate(sample)
    expect("miss.full", mr.full_solutions, 3)
    expect("miss.exact", mr.exact_markers, 1)
    expect("miss.misses", mr.misses, 2)
    expect("miss.nosol", mr.no_solution_given, 1)
    expect("miss.pct", mr.miss_rate_pct, 66.7)

    if failures:
        print("SELF-CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELF-CHECK PASSED: grading classifiers behave as specified.")
    return 0


# --- CLI -------------------------------------------------------------------


async def _run_live(args) -> int:
    from services.llm_client import LLMClient  # local import (needs backend pkg)

    client = LLMClient(base_url=args.base_url) if args.base_url else LLMClient()
    print(f"Probing llama-server at {client._base_url} …")
    await _probe(client)

    selected = (
        ["complexity", "socratic", "marker"] if args.only == "all" else [args.only]
    )
    results: dict = {}
    if "complexity" in selected:
        results["complexity"] = await run_complexity(client, args.variant)
    if "socratic" in selected:
        results["socratic"] = await run_socratic(client, args.variant)
    if "marker" in selected:
        results["marker"] = await run_marker(client, args.variant)

    path = _persist(args.model_label, args.variant, results)
    print(f"\nRaw results: {path}\n")
    print("=" * 72)
    print(_summarize(args.model_label, args.variant, results))
    print("=" * 72)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Validate grading logic offline (no llama-server). Exits after.",
    )
    parser.add_argument(
        "--model-label",
        default="unknown-model",
        help="Tag for the running model, used in results filename and summary.",
    )
    parser.add_argument(
        "--variant",
        default="baseline",
        choices=sorted(ds.SOCRATIC_VARIANTS),
        help="Socratic system-prompt variant (decision C A/B testing).",
    )
    parser.add_argument(
        "--only",
        default="all",
        choices=["all", "complexity", "socratic", "marker"],
        help="Which eval(s) to run.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override llama-server base URL (else uses config / WHETSTONE_LLM_*).",
    )
    args = parser.parse_args(argv)

    if args.self_check:
        return self_check()
    return asyncio.run(_run_live(args))


if __name__ == "__main__":
    raise SystemExit(main())
