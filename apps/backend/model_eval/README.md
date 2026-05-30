# model_eval — model-quality evaluation harness

A **manual** evaluation harness for the SRS §9.3 open questions and the
Phase 2 integrity-marker concern. It is intentionally **not** part of the
application or the default `pytest` run:

- It lives outside the `test_*.py` naming convention, so `pytest` does not
  collect it.
- Every measurement needs a **live `llama-server`**; there is nothing to run
  in CI.

See [`docs/model-eval.md`](../../../docs/model-eval.md) for the methodology,
results, and the decisions this harness informs.

## What it measures

1. **Complexity correctness** — sends ~10 cells with known time/space bounds
   and checks whether the model's Big-O appears in its analysis (a substring
   *signal*; confirm against saved transcripts).
2. **Socratic restraint** — runs each of 5 assignment prompts as a 4–5 turn
   escalating conversation and flags whether a full solution leaked *before*
   the student gave up.
3. **Integrity-marker reliability** — issues ~18 explicit "give me the full
   answer" demands and computes the **marker miss-rate**: of the replies that
   actually contained a full solution, how many failed to begin with the exact
   `FULL_SOLUTION_PREFIX` line the UI matches on. This number drives the
   marker-architecture decision (B).

## Running it

```sh
cd apps/backend
# 1. Start llama-server with the model under test (see ../../RUNNING.md),
#    e.g. gemma-4-e4b on 127.0.0.1:8081.
# 2. Run all three evals, tagging the run with the model name:
python -m model_eval.run --model-label "gemma-4-e4b" --only all

# Test the recommended stronger model the same way:
python -m model_eval.run --model-label "gemma-26b-a4b" --only all

# A/B a Socratic prompt variant for decision C:
python -m model_eval.run --model-label "gemma-4-e4b" --variant self_check --only marker
```

Raw per-item results (including full transcripts) are written to
`model_eval/results/<model>-<variant>-<timestamp>.json`. A paste-ready
markdown summary — including the miss-rate as a number — is printed to stdout
for dropping into `docs/model-eval.md`.

## Validating the harness without a model

The grading classifiers are pure functions and can be checked offline:

```sh
cd apps/backend
python -m model_eval.run --self-check
```

This exercises the marker classifier, the full-solution detector, the Big-O
normalizer, and the miss-rate aggregator against hand-written fixtures. It
needs no `llama-server`.

## Keeping prompts in sync

`datasets.py` embeds copies of the Direct/Socratic system prompts and the
`FULL_SOLUTION_PREFIX` marker that mirror `routers/ai.py`. They are duplicated
so the harness is self-contained and can A/B-test prompt variants. **If the
production prompt changes, update the `baseline` variant here before
re-running**, or the eval will be measuring a stale prompt.
