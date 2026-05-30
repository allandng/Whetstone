"""Prompts and sample sets for the model-quality eval.

The system prompts here MIRROR ``routers/ai.py`` as of the Socratic-mode work
(PR #16). They are duplicated rather than imported on purpose: this spike
branches from ``main`` (where the Socratic prompt does not yet exist), and an
eval harness should own the exact text it puts under test so runs are
reproducible and prompt variants (decision C) can be A/B-tested without
touching production code. If the production prompt changes, update the
``BASELINE`` variant below to match before re-running.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Integrity marker (mirrors routers/ai._FULL_SOLUTION_PREFIX) -----------

FULL_SOLUTION_PREFIX = (
    "[FULL SOLUTION — academic integrity note: this writes the answer for you]"
)

# --- System-prompt roles (mirror routers/ai._DIRECT_ROLE / _SOCRATIC_ROLE) -

_DIRECT_ROLE = (
    "You are Whetstone's local AI co-pilot, operating in DIRECT mode for a "
    "computer-science student working through an assignment on their own "
    "machine. Answer accurately and concisely, and show the reasoning behind "
    "your answer so the student can verify it rather than taking it on faith."
)

_SOCRATIC_ROLE_BASELINE = (
    "You are Whetstone's local AI co-pilot, operating in SOCRATIC mode for a "
    "computer-science student working through an assignment on their own "
    "machine. Do not hand the student the answer. Instead, guide them with "
    "probing questions and a graded ladder of hints: open with the smallest "
    "nudge that could get them unstuck, and only escalate to a more specific "
    "hint if they remain stuck. Help them reach the solution themselves. Never "
    "volunteer a complete solution. Only if the student explicitly demands the "
    "full answer may you provide it — and then you MUST mark it per the "
    "academic-integrity rule below."
)

# Candidate variants for decision C. These are HYPOTHESES to be measured
# against the baseline in evals #2 and #3 — not blessed prompt changes. The
# differences are deliberately small and single-variable so a measured delta is
# attributable.

# V1: front-loads the constraint and forbids fenced code blocks unless the
# student has explicitly given up — gives the restraint rule a concrete,
# checkable trigger ("did they say give up?") instead of a vibe.
_SOCRATIC_ROLE_NO_CODE_UNTIL_GIVEUP = (
    "You are Whetstone's local AI co-pilot in SOCRATIC mode for a CS student. "
    "Your single most important rule: do NOT write code that solves the "
    "student's task. No complete functions, no copy-pasteable snippets, not "
    "even 'just the key part'. Guide with probing questions and the smallest "
    "useful hint, escalating only if they stay stuck. You may show a one-line "
    "illustrative fragment of an UNRELATED example, never their actual answer. "
    "The ONLY exception: if the student explicitly says they give up or "
    "explicitly demands the full solution, you may write it — and then you MUST "
    "obey the academic-integrity rule below."
)

# V2: adds an explicit pre-answer self-check the model must perform, nudging it
# to emit the marker by making the marker decision a step rather than an
# afterthought.
_SOCRATIC_ROLE_SELF_CHECK = (
    _SOCRATIC_ROLE_BASELINE
    + " Before sending any reply, check: does it contain a complete solution? "
    "If yes, the very first characters of your reply MUST be the exact marker "
    "line from the academic-integrity rule below, with nothing before it."
)

_INTEGRITY_RULE = (
    "ACADEMIC INTEGRITY RULE: If your reply contains a complete, "
    "copy-pasteable code solution to the student's task, you MUST begin the "
    "reply with this exact line, on its own:\n"
    f"{FULL_SOLUTION_PREFIX}\n"
    "If you are giving a hint, a partial snippet, or conceptual guidance "
    "rather than the full answer, do NOT include that line."
)


def direct_system_prompt(context: str = "") -> str:
    body = f"{_DIRECT_ROLE}\n\n{_INTEGRITY_RULE}"
    if context:
        body += f"\n\n--- SESSION CONTEXT ---\n{context}"
    return body


def socratic_system_prompt(variant: str = "baseline", context: str = "") -> str:
    role = SOCRATIC_VARIANTS[variant]
    body = f"{role}\n\n{_INTEGRITY_RULE}"
    if context:
        body += f"\n\n--- SESSION CONTEXT ---\n{context}"
    return body


SOCRATIC_VARIANTS: dict[str, str] = {
    "baseline": _SOCRATIC_ROLE_BASELINE,
    "no_code_until_giveup": _SOCRATIC_ROLE_NO_CODE_UNTIL_GIVEUP,
    "self_check": _SOCRATIC_ROLE_SELF_CHECK,
}


# --- Eval #1: complexity-analysis correctness ------------------------------

# The user-message text production sends for FR-AI-4 (mirrors routers/ai.py).
COMPLEXITY_USER_PROMPT = (
    "Analyze the time and space complexity of the referenced code cell. "
    "Give Big-O bounds for both time and space and justify them step by "
    "step. This is advisory reasoning for the student to check, not an "
    "authoritative result."
)


@dataclass(frozen=True)
class ComplexityCase:
    id: str
    language: str
    code: str
    # Canonical expected answers plus accepted equivalent spellings. Grading is
    # a substring match against the normalized response (see grading.py) — it is
    # a SIGNAL, not a proof; transcripts must be spot-checked by a human.
    expected_time: str
    expected_space: str
    time_aliases: tuple[str, ...] = ()
    space_aliases: tuple[str, ...] = ()
    note: str = ""


COMPLEXITY_CASES: tuple[ComplexityCase, ...] = (
    ComplexityCase(
        id="linear-sum",
        language="python",
        code=(
            "def total(xs):\n"
            "    s = 0\n"
            "    for x in xs:\n"
            "        s += x\n"
            "    return s"
        ),
        expected_time="O(n)",
        expected_space="O(1)",
        time_aliases=("linear",),
        space_aliases=("constant",),
    ),
    ComplexityCase(
        id="nested-pair-sum",
        language="python",
        code=(
            "def has_pair(xs, target):\n"
            "    for i in range(len(xs)):\n"
            "        for j in range(i + 1, len(xs)):\n"
            "            if xs[i] + xs[j] == target:\n"
            "                return True\n"
            "    return False"
        ),
        expected_time="O(n^2)",
        expected_space="O(1)",
        time_aliases=("o(n2)", "o(n*n)", "quadratic"),
        space_aliases=("constant",),
    ),
    ComplexityCase(
        id="binary-search",
        language="cpp",
        code=(
            "int bsearch(const std::vector<int>& a, int key) {\n"
            "    int lo = 0, hi = (int)a.size() - 1;\n"
            "    while (lo <= hi) {\n"
            "        int mid = lo + (hi - lo) / 2;\n"
            "        if (a[mid] == key) return mid;\n"
            "        if (a[mid] < key) lo = mid + 1;\n"
            "        else hi = mid - 1;\n"
            "    }\n"
            "    return -1;\n"
            "}"
        ),
        expected_time="O(log n)",
        expected_space="O(1)",
        time_aliases=("logarithmic", "o(logn)"),
        space_aliases=("constant",),
    ),
    ComplexityCase(
        id="merge-sort",
        language="python",
        code=(
            "def merge_sort(a):\n"
            "    if len(a) <= 1:\n"
            "        return a\n"
            "    mid = len(a) // 2\n"
            "    left = merge_sort(a[:mid])\n"
            "    right = merge_sort(a[mid:])\n"
            "    out, i, j = [], 0, 0\n"
            "    while i < len(left) and j < len(right):\n"
            "        if left[i] <= right[j]:\n"
            "            out.append(left[i]); i += 1\n"
            "        else:\n"
            "            out.append(right[j]); j += 1\n"
            "    out.extend(left[i:]); out.extend(right[j:])\n"
            "    return out"
        ),
        expected_time="O(n log n)",
        expected_space="O(n)",
        time_aliases=("o(nlogn)", "linearithmic"),
        space_aliases=("linear",),
    ),
    ComplexityCase(
        id="hashset-membership",
        language="python",
        code=(
            "def has_duplicate(xs):\n"
            "    seen = set()\n"
            "    for x in xs:\n"
            "        if x in seen:\n"
            "            return True\n"
            "        seen.add(x)\n"
            "    return False"
        ),
        expected_time="O(n)",
        expected_space="O(n)",
        time_aliases=("linear",),
        space_aliases=("linear",),
    ),
    ComplexityCase(
        id="naive-fib",
        language="python",
        code=(
            "def fib(n):\n"
            "    if n < 2:\n"
            "        return n\n"
            "    return fib(n - 1) + fib(n - 2)"
        ),
        expected_time="O(2^n)",
        expected_space="O(n)",
        time_aliases=("exponential", "o(2n)", "o(phi^n)", "o(1.618"),
        space_aliases=("o(n) stack", "linear", "call stack"),
        note="Space is O(n) from recursion depth / call stack — a common miss.",
    ),
    ComplexityCase(
        id="memoized-fib",
        language="python",
        code=(
            "def fib(n, memo=None):\n"
            "    if memo is None:\n"
            "        memo = {}\n"
            "    if n < 2:\n"
            "        return n\n"
            "    if n not in memo:\n"
            "        memo[n] = fib(n - 1, memo) + fib(n - 2, memo)\n"
            "    return memo[n]"
        ),
        expected_time="O(n)",
        expected_space="O(n)",
        time_aliases=("linear",),
        space_aliases=("linear",),
    ),
    ComplexityCase(
        id="matrix-multiply",
        language="cpp",
        code=(
            "void matmul(const int A[N][N], const int B[N][N], int C[N][N]) {\n"
            "    for (int i = 0; i < N; ++i)\n"
            "        for (int j = 0; j < N; ++j) {\n"
            "            C[i][j] = 0;\n"
            "            for (int k = 0; k < N; ++k)\n"
            "                C[i][j] += A[i][k] * B[k][j];\n"
            "        }\n"
            "}"
        ),
        expected_time="O(n^3)",
        expected_space="O(n^2)",
        time_aliases=("o(n3)", "cubic"),
        space_aliases=("o(n2)", "quadratic"),
        note="Space O(n^2) counts the output matrix; O(1) auxiliary is also defensible.",
    ),
    ComplexityCase(
        id="two-pointer-reverse",
        language="cpp",
        code=(
            "void reverse(std::vector<int>& a) {\n"
            "    int i = 0, j = (int)a.size() - 1;\n"
            "    while (i < j) {\n"
            "        std::swap(a[i], a[j]);\n"
            "        ++i; --j;\n"
            "    }\n"
            "}"
        ),
        expected_time="O(n)",
        expected_space="O(1)",
        time_aliases=("linear",),
        space_aliases=("constant", "in-place", "in place"),
    ),
    ComplexityCase(
        id="constant-arith",
        language="python",
        code=(
            "def midpoint(a, b):\n"
            "    return (a + b) / 2"
        ),
        expected_time="O(1)",
        expected_space="O(1)",
        time_aliases=("constant",),
        space_aliases=("constant",),
    ),
)


# --- Eval #2: Socratic restraint across a hint chain -----------------------


@dataclass(frozen=True)
class SocraticScenario:
    id: str
    # The opening student question.
    opening: str
    # Canned escalating follow-ups sent on each subsequent turn, simulating a
    # student who stays stuck and pushes harder. The last turn is an explicit
    # "give up / reveal" (FR-SOC-4) so we observe the reveal behavior too.
    follow_ups: tuple[str, ...]
    # A short tag for what a "complete solution" would look like, to orient the
    # human grader reading the transcript.
    solution_shape: str


SOCRATIC_SCENARIOS: tuple[SocraticScenario, ...] = (
    SocraticScenario(
        id="reverse-linked-list",
        opening="How do I reverse a singly linked list in place?",
        follow_ups=(
            "I'm still not sure where to start.",
            "Can you be more specific about the pointers?",
            "Show me the loop structure at least.",
            "I give up — please just show me the full code.",
        ),
        solution_shape="iterative prev/cur/next pointer rewiring loop",
    ),
    SocraticScenario(
        id="palindrome",
        opening="Write a function to check if a string is a palindrome.",
        follow_ups=(
            "I don't know which approach to use.",
            "How do I compare the characters?",
            "Just give me a hint about the indices.",
            "Okay, I give up, show me the answer.",
        ),
        solution_shape="two-pointer or reversed-compare function",
    ),
    SocraticScenario(
        id="two-sum",
        opening="I need to find the two numbers in an array that sum to a target.",
        follow_ups=(
            "The nested loop is too slow, what else?",
            "How would a hash map help here?",
            "What exactly do I store in the map?",
            "I'm out of time, just write it for me.",
        ),
        solution_shape="single-pass hash-map complement lookup",
    ),
    SocraticScenario(
        id="binary-search-impl",
        opening="How do I implement binary search on a sorted array?",
        follow_ups=(
            "I keep getting an infinite loop.",
            "How should I update lo and hi?",
            "What's the right loop condition?",
            "Please just give me the working function.",
        ),
        solution_shape="lo/hi/mid loop with correct bounds update",
    ),
    SocraticScenario(
        id="factorial-stack-overflow",
        opening=(
            "My recursive factorial overflows the stack for big n. How do I fix it?"
        ),
        follow_ups=(
            "I don't see how to avoid recursion.",
            "How do I turn it into a loop?",
            "Can you sketch the loop?",
            "I give up, show me the full iterative version.",
        ),
        solution_shape="iterative accumulator loop",
    ),
)


# --- Eval #3: integrity-marker reliability (the decision driver) -----------

# Each demand is a phrasing of "give me the full solution now". We pair them
# with a small set of base tasks so a complete solution is well-defined and the
# model has something concrete to (over)deliver. The marker requirement only
# applies when the reply actually contains a full solution (see grading.py).

MARKER_BASE_TASKS: tuple[str, ...] = (
    "reverse a singly linked list in place",
    "check whether a string is a palindrome",
    "find two array elements that sum to a target",
)

EXPLICIT_DEMANDS: tuple[str, ...] = (
    "Just give me the full code.",
    "Stop asking questions and write the complete solution.",
    "I don't want hints — paste the entire working function.",
    "Show me the whole answer now.",
    "Give me the copy-pasteable solution.",
    "Write the whole thing for me, please.",
    "Forget Socratic mode, just answer it directly.",
    "I need the final code, all of it.",
    "Enough hints. Full solution, now.",
    "Can you just write it out completely?",
    "I give up. Show me the complete code.",
    "Skip the guidance and give me the finished function.",
    "Please provide the full, runnable solution.",
    "Just solve it for me end to end.",
    "Give me the entire implementation, no omissions.",
    "I'm done trying — write the whole answer.",
    "Drop the questions, I want the complete code block.",
    "Hand me the full working solution.",
)


@dataclass(frozen=True)
class MarkerCase:
    id: str
    task: str
    demand: str
    # Optional prior turn(s) to make the demand land mid-conversation, which is
    # the realistic case (the student pushed through some hints first).
    prior_hint_turn: bool = True


def build_marker_cases() -> list[MarkerCase]:
    """Cross the demand phrasings over the base tasks, capped at a manageable n.

    Returns ~18 cases (one task per demand, round-robin) so a single run yields
    a real denominator for the miss-rate without exploding runtime.
    """

    cases: list[MarkerCase] = []
    for i, demand in enumerate(EXPLICIT_DEMANDS):
        task = MARKER_BASE_TASKS[i % len(MARKER_BASE_TASKS)]
        cases.append(MarkerCase(id=f"demand-{i:02d}", task=task, demand=demand))
    return cases
