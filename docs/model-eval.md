# Whetstone — Model-Quality Evaluation (SRS §9.3 spike)

**Type:** evaluation spike. The output is *decisions*, not shipped code. The
companion harness lives at [`apps/backend/model_eval/`](../apps/backend/model_eval/).

> ## ⚠️ Status: numbers PENDING a live run
>
> This spike requires a live `llama-server` with the model(s) under test. **The
> environment this document was authored in had no `llama-server` binary, no
> GGUF model files, and no reachable inference server**, so the empirical cells
> below are marked `PENDING` rather than filled with invented figures.
>
> What *is* verified here:
> - The harness is committed and runnable.
> - Its grading logic passes an offline self-check
>   (`python -m model_eval.run --self-check` → *SELF-CHECK PASSED*), so once a
>   server is available the three measurements — including the marker
>   miss-rate as a number — are produced automatically.
>
> **To complete the spike:** start `llama-server` (see [`RUNNING.md`](../RUNNING.md)),
> then for each model run `python -m model_eval.run --model-label <name> --only all`
> from `apps/backend/` and paste the printed summary into §3. The decisions in
> §4 are written as *frameworks with explicit thresholds* plus a provisional
> lean; confirm or flip them against the measured numbers.

---

## 1. Scope

§9.3 lists four open questions. This is a *model-quality* spike, so it resolves
the two that are about model behavior, plus the Phase-2 marker concern:

| Question | Covered by | Status |
|---|---|---|
| Q1 — Is Gemma 4 E4B's complexity analysis reliable enough? | Eval #1 | method ready, numbers PENDING |
| Q2 — Can the Socratic prompt hold restraint across a hint chain; how to tune give-up/reveal (FR-SOC-4)? | Eval #2 | method ready, numbers PENDING |
| Integrity-marker reliability (FR-AI-6 / FR-SOC-5), flagged in Phase 2 | Eval #3 | method ready, **miss-rate PENDING** |

**Out of scope for this spike** (the remaining §9.3 items are not model-quality
questions and are flagged here so they aren't lost):

- *Psirver v1.0 security floor for AI-generated code* — a sandbox/resource-limit
  decision, independent of model quality. Belongs to the execution-hardening
  track (NFR-SEC-1).
- *Event ordering relies on timestamp only* — a data-model fix (add a monotonic
  sequence column); independent of the model.

---

## 2. Method

All three evals talk to `llama-server` through the production `LLMClient`, with
prompts that mirror `routers/ai.py` (embedded in `model_eval/datasets.py` so the
harness is self-contained and prompt variants are A/B-testable). Grading is a
set of pure, offline-tested heuristics — **signals for a human to confirm
against the saved transcripts, not ground truth.**

### #1 — Complexity-analysis correctness
- **Inputs:** ~10 cells with known time/space bounds (`COMPLEXITY_CASES`),
  spanning O(1) → O(2^n), including two classic traps: recursion-depth space in
  naive Fibonacci and output-matrix space in matrix-multiply.
- **Call:** Direct-mode system prompt + the FR-AI-4 user prompt, `thinking=True`
  (matches `complexity()`).
- **Grade:** does the model's normalized response contain the expected Big-O (or
  an accepted alias: `quadratic`, `linear`, superscript/`^`/`n*n` spellings)?
  Recorded per-axis (time, space) and as both-correct.
- **Caveat:** substring matching can't tell a *justified* correct answer from a
  lucky token. Confirm the both-correct cases against transcripts.

### #2 — Socratic restraint across a hint chain
- **Inputs:** 5 assignment prompts (`SOCRATIC_SCENARIOS`), each run as a 4–5 turn
  escalating conversation: an opening question, three "still stuck / be more
  specific" pushes, and a final explicit **give-up** turn (exercises FR-SOC-4).
- **Call:** Socratic system prompt, `thinking=False`, full conversation history
  replayed each turn.
- **Grade per turn:** `is_full_solution` (see detector below) and
  `marker_status`; a **leak** = a full solution handed over *before* the give-up
  turn. Also recorded: did the model actually reveal on the give-up turn?
- **Caveat:** "graded hint ladder" quality is qualitative — read the transcripts.

### #3 — Integrity-marker reliability *(the decision driver)*
- **Inputs:** ~18 explicit "give me the full answer" demands of varied phrasing
  (`EXPLICIT_DEMANDS`), each after one prior hint turn so the demand lands
  mid-conversation (the realistic case).
- **Grade:** classify each reply's marker as `exact` / `present_nonexact` /
  `paraphrased` / `absent`, where **`exact` mirrors the shipped UI check**
  (`text.startsWith(FULL_SOLUTION_PREFIX)`).
- **Miss-rate** = of the replies that *actually contained a full solution*, the
  fraction whose marker was not `exact`. The denominator excludes replies where
  the model resisted (no full solution → no marker required).

**Full-solution detector** (`grading.detect_full_solution`): a reply counts as a
full solution if it has a fenced code block ≥ 4 non-blank lines, or a
function/`main` definition with a body. Documented blind spots — they bound the
server-side option in §4.B: prose-dictated solutions with no fence (missed),
long *illustrative* snippets that aren't the answer (false hit), indented code
without fences (missed).

---

## 3. Results

> Run the harness and paste its printed summary blocks here, one per model. The
> structure below matches what `run.py` prints.

### Gemma 4 E4B — `PENDING`

| Eval | Metric | Result |
|---|---|---|
| #1 Complexity | both time+space correct | `PENDING` / 10 |
| #1 Complexity | time correct · space correct | `PENDING` / 10 · `PENDING` / 10 |
| #2 Socratic | scenarios that leaked before give-up | `PENDING` / 5 |
| #2 Socratic | scenarios that revealed on give-up (FR-SOC-4) | `PENDING` / 5 |
| #3 Marker | full-solution replies (denominator) | `PENDING` |
| #3 Marker | **marker miss-rate** | **`PENDING` %** |
| #3 Marker | demands resisted (no full solution) | `PENDING` |

### Gemma 26B A4B — `PENDING (if available)`

_Same table; run with `--model-label gemma-26b-a4b`._

---

## 4. Decisions

### A. Minimum viable model — E4B floor, 26B recommended (provisional)

The SRS already posits *"E4B as the minimum, 26B A4B as the recommended
upgrade."* This spike should confirm or revise that, driven by Eval #1 (and #2):

- **Keep E4B as the floor regardless** — it is the only model most target
  machines can run, and it's selectable per FR-AI-7.
- **Decision rule for complexity (FR-AI-4):**
  - If E4B both-correct ≥ ~70% → E4B is adequate; keep the "verify this"
    framing as-is.
  - If E4B both-correct is ~40–70% → keep E4B but **lean harder on the
    "verify this yourself" framing** in the UI for complexity, and surface the
    26B recommendation contextually on that feature.
  - If E4B both-correct < ~40% → **recommend 26B specifically for complexity**
    and consider gating/labelling the feature on E4B as low-confidence.
- The recursion-depth and matrix-output-space traps in the dataset are the
  cases most likely to separate E4B from 26B; weight them when judging.

**Provisional position:** E4B floor + strong "verify this" framing + 26B as the
documented upgrade. Flip toward "26B recommended for complexity" only if E4B's
both-correct rate lands in the bottom band above.

### B. Integrity-marker strategy — *recommend moving the guarantee server-side* (provisional, pending miss-rate)

The shipped banner fires only when the model's reply *begins with an exact magic
string*. Asking a 4B model to emit a verbatim sentinel as the literal first
characters of a reply is exactly the kind of instruction small models comply
with unreliably. The miss-rate (Eval #3) sets the **urgency**; the **direction**
is already well-supported on first principles and by a precedent in this
codebase.

Threshold mapping:

- **Miss-rate low (< ~10%):** keep model-emits-marker, but **loosen the UI
  detection** to absorb minor drift — trim leading whitespace, casefold, and
  accept the prefix anywhere near the top rather than a strict `startsWith`.
  (The harness shows a `lenient_start` check already catches leading-whitespace
  and case variants the current UI misses — a cheap, high-leverage change.)
- **Miss-rate non-trivial (≥ ~10–15%):** **move the guarantee server-side.**
- **Neither reliable** (server classifier also weak — see below): document the
  banner as **best-effort on a small model**, a known v1.0 limitation, and rely
  on the always-on "verify this / integrity" framing instead.

**Feasibility of the server-side option (the crux the task flags):** "reliably
classifying a streamed response as a complete solution" is genuinely non-trivial
— but two design points make it the better bet:

1. **Don't prepend; emit a signal.** The response is streamed via SSE. Buffering
   the whole reply to prepend a marker would kill the incremental-display UX
   that SSE exists for (and a slow local model makes that worse). Instead, run
   `detect_full_solution` over the *accumulating* buffer as chunks arrive and,
   when it latches true, emit a dedicated event (e.g. `data: {"integrity":
   "full_solution"}`). The UI renders the banner off that event, **decoupling it
   from string-matching the model's prose entirely.** This is strictly more
   robust than the current scheme and preserves streaming.
2. **Precedent:** `_VERIFY_LINE` for complexity is *already* appended
   server-side, unconditionally, "regardless of what a small model emits." The
   marker is the conditional sibling — the new cost over the verify-line is
   exactly the classifier, nothing else architecturally.
3. **Residual risk, stated plainly:** the classifier inherits the FP/FN blind
   spots documented in §2 (prose-only solutions, indented code, long
   illustrative snippets). So server-side enforcement is *"more reliable and
   under our control,"* not *"perfect."* It also moves the guarantee to
   something we can tune over time, which the model's compliance is not.

**Provisional position:** plan for the server-emitted-signal approach; if the
measured miss-rate comes in genuinely low, the cheap UI-loosening may suffice
for v1.0 and the server signal becomes a fast-follow. **Do not implement here —
this spike informs the fix.**

### C. Socratic prompt tweaks (hypotheses to measure, fold winner into Phase 2)

Two single-variable variants are embedded for A/B testing against `baseline`
(run e.g. `--variant self_check --only marker` / `--only socratic`). Do **not**
edit the production prompt on this branch — record the winner for Phase 2.

- **`no_code_until_giveup`** — replaces the soft "never volunteer a complete
  solution" with a hard, *checkable* rule ("do NOT write code that solves the
  task… the ONLY exception is an explicit give-up/demand"). Hypothesis: a
  concrete trigger reduces early leaks (Eval #2) more than an aspirational one.
- **`self_check`** — appends a pre-send self-check ("does this contain a
  complete solution? if so the first characters MUST be the marker"). Hypothesis:
  making the marker a *step* rather than an afterthought raises the `exact`
  rate (Eval #3).

Fold a variant into the Phase 2 prompt only if it shows a **measurable**
improvement on its target metric without regressing the other (e.g.
`no_code_until_giveup` must not make the model refuse the legitimate give-up
reveal). If neither beats baseline, that itself is the finding — leave the
prompt and rely on decision B's server-side enforcement.

---

## 5. Known limitation — reload resets the co-pilot mode

Captured from Phase 2 (not part of the eval, recorded here so it's decided
during session-persistence work):

A full page reload / app relaunch resets the co-pilot mode to its default
(**Direct**). A student who was in Socratic mode is silently dropped back into
the answer-giving mode — the more harmful direction for academic integrity, and
easy to not notice. The mode lives only in React component state
(`useState("direct")` in `WorkspaceLayout`), with no persistence.

**Decision to make during session persistence (pick one):**

- **Persist mode per session** — store the active tutor mode on the session and
  restore it on load. Most faithful to the student's intent; preferred.
- **Make the reset visible** — if not persisted, surface the reset (e.g. a
  one-time toast: "Reset to Direct mode") so it's never silent.

Either is acceptable; silently defaulting to Direct is not.

---

## 6. Reproducing / completing this doc

```sh
cd apps/backend
python -m model_eval.run --self-check                       # offline logic check
python -m model_eval.run --model-label "gemma-4-e4b" --only all
python -m model_eval.run --model-label "gemma-26b-a4b" --only all   # if available
```

Paste each run's printed summary into §3, fill the decision bands in §4 against
the measured numbers, and note the §4.C A/B winner. See
[`apps/backend/model_eval/README.md`](../apps/backend/model_eval/README.md).
