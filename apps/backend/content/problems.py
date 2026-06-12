"""The built-in DSA practice problem bank.

Original problems (not lifted from any question site) organized by the
interview *pattern* they teach — the point is recognizing the shape of a
problem, not memorizing specific questions. Two problems per pattern: one
to learn the move, one to stretch it.

Seeded into the :class:`models.Problem` table on startup, keyed by ``slug``
so reseeding is idempotent (see ``seed_builtin_problems`` in
:mod:`routers.practice`). Generated variants reference these via
``parent_problem_id`` but live only in the database.

Problem shape::

    {
        "slug": str,
        "title": str,
        "pattern": str,        # e.g. "arrays-hashing", "two-pointers"
        "difficulty": str,     # "easy" | "medium" | "hard"
        "prompt": str,         # full statement (markdown-lite)
        "examples": [ {"input": str, "output": str, "explanation": str} ],
        "hints": [str, ...],   # graded: smallest nudge first
        "starter_code": str,   # runnable Python with sample checks
    }
"""

from __future__ import annotations

SEED_PROBLEMS: list[dict] = [
    # --- Arrays & hashing ----------------------------------------------------
    {
        "slug": "festival-wristbands",
        "title": "Festival Wristbands",
        "pattern": "arrays-hashing",
        "difficulty": "easy",
        "prompt": (
            "Scanners at a festival gate record the wristband ID of each "
            "person who walks in. A duplicated ID means a counterfeit band.\n\n"
            "Given a list of integers `ids` in scan order, return the **first "
            "ID that appears a second time**. If every ID is unique, return "
            "-1.\n\n"
            "Constraints: 1 <= len(ids) <= 10^5. Aim for a single pass."
        ),
        "examples": [
            {
                "input": "ids = [7, 3, 9, 3, 7]",
                "output": "3",
                "explanation": (
                    "Both 3 and 7 repeat, but 3 is the first to be scanned a "
                    "second time (position 3, before 7's repeat at position 4)."
                ),
            },
            {
                "input": "ids = [1, 2, 3]",
                "output": "-1",
                "explanation": "No ID repeats.",
            },
        ],
        "hints": [
            "Checking every pair of scans works but is O(n^2). What could you remember as you walk the list once?",
            "A set answers 'have I seen this before?' in constant time.",
            "Walk the list; if the ID is already in your seen-set, return it immediately, else add it. Return -1 after the loop.",
        ],
        "starter_code": (
            "def first_counterfeit(ids):\n"
            "    # Return the first ID scanned a second time, or -1.\n"
            "    return -1\n\n\n"
            "print(first_counterfeit([7, 3, 9, 3, 7]))  # expect 3\n"
            "print(first_counterfeit([1, 2, 3]))        # expect -1\n"
            "print(first_counterfeit([5, 5]))           # expect 5\n"
        ),
    },
    {
        "slug": "potion-pairs",
        "title": "Potion Pairs",
        "pattern": "arrays-hashing",
        "difficulty": "medium",
        "prompt": (
            "An alchemist's shelf holds potions with integer strengths "
            "(possibly negative — some potions are curses). Mixing two "
            "potions adds their strengths.\n\n"
            "Given a list `strengths` and a target value `goal`, return the "
            "**indices** of two different potions whose strengths sum to "
            "exactly `goal`, as a list `[i, j]` with `i < j`. Exactly one "
            "such pair exists.\n\n"
            "Constraints: 2 <= len(strengths) <= 10^5. The shelf is NOT "
            "sorted, and you may not sort it (the indices matter). Aim for "
            "O(n) time."
        ),
        "examples": [
            {
                "input": "strengths = [4, -1, 9, 6], goal = 5",
                "output": "[1, 3]",
                "explanation": "strengths[1] + strengths[3] = -1 + 6 = 5.",
            },
            {
                "input": "strengths = [3, 3], goal = 6",
                "output": "[0, 1]",
                "explanation": "The two equal potions form the pair — watch this case.",
            },
        ],
        "hints": [
            "For each potion you look at, what one number would complete the pair?",
            "Store strength -> index in a dict as you scan, and look up `goal - strength` before inserting.",
            "Looking up the complement *before* inserting the current potion handles the duplicate-strength case ([3, 3], goal 6) for free.",
        ],
        "starter_code": (
            "def potion_pair(strengths, goal):\n"
            "    # Return [i, j] with i < j and strengths[i] + strengths[j] == goal.\n"
            "    return []\n\n\n"
            "print(potion_pair([4, -1, 9, 6], 5))   # expect [1, 3]\n"
            "print(potion_pair([3, 3], 6))          # expect [0, 1]\n"
            "print(potion_pair([2, 7, 11, 15], 9))  # expect [0, 1]\n"
        ),
    },
    # --- Two pointers ---------------------------------------------------------
    {
        "slug": "telescope-alignment",
        "title": "Telescope Alignment",
        "pattern": "two-pointers",
        "difficulty": "easy",
        "prompt": (
            "An observatory's telescopes are mounted along a rail at fixed, "
            "**sorted** angle settings. Two telescopes can be paired to track "
            "one satellite if their angles sum to exactly the satellite's "
            "bearing.\n\n"
            "Given a sorted list `angles` (strictly increasing) and an "
            "integer `bearing`, return True if any two distinct telescopes "
            "sum to `bearing`, else False.\n\n"
            "Constraints: 2 <= len(angles) <= 10^5. Aim for O(n) time and "
            "O(1) extra space — the sortedness is the whole point."
        ),
        "examples": [
            {
                "input": "angles = [10, 25, 40, 55, 70], bearing = 95",
                "output": "True",
                "explanation": "25 + 70 = 95.",
            },
            {
                "input": "angles = [10, 25, 40], bearing = 90",
                "output": "False",
                "explanation": "No pair reaches 90.",
            },
        ],
        "hints": [
            "You could use the hash-map trick, but the list is sorted — there is an O(1)-space approach.",
            "Put one finger on the smallest angle and one on the largest. What does their sum tell you?",
            "If the sum is too small, only moving the left finger right can help; too big, move the right finger left. Stop when they meet.",
        ],
        "starter_code": (
            "def can_align(angles, bearing):\n"
            "    # angles is sorted ascending. Two pointers, O(1) space.\n"
            "    return False\n\n\n"
            "print(can_align([10, 25, 40, 55, 70], 95))  # expect True\n"
            "print(can_align([10, 25, 40], 90))          # expect False\n"
            "print(can_align([1, 2], 3))                 # expect True\n"
        ),
    },
    {
        "slug": "shrinking-the-moat",
        "title": "Shrinking the Moat",
        "pattern": "two-pointers",
        "difficulty": "medium",
        "prompt": (
            "A castle moat is being rebuilt. Vertical stone walls of various "
            "heights stand at positions 0, 1, 2, ... along a line; you must "
            "pick **two walls** and flood the space between them. The water "
            "level is capped by the *shorter* wall, and the volume is\n\n"
            "    min(height[i], height[j]) * (j - i)\n\n"
            "Given `heights`, return the **maximum volume** any pair of "
            "walls can hold.\n\n"
            "Constraints: 2 <= len(heights) <= 10^5, heights are "
            "non-negative. O(n^2) brute force is too slow at the top end — "
            "aim for one pass."
        ),
        "examples": [
            {
                "input": "heights = [1, 8, 6, 2, 5, 4, 8, 3, 7]",
                "output": "49",
                "explanation": "Walls at indices 1 and 8: min(8, 7) * (8 - 1) = 49.",
            },
            {
                "input": "heights = [4, 4]",
                "output": "4",
                "explanation": "min(4, 4) * 1 = 4.",
            },
        ],
        "hints": [
            "Start with the widest possible pair: the two ends. The width only shrinks from there, so what must improve to beat the current best?",
            "Only a taller limiting wall can compensate for lost width. Which pointer is the limiting one?",
            "Always move the pointer at the *shorter* wall inward — moving the taller one can never increase the volume. Track the best seen.",
        ],
        "starter_code": (
            "def max_moat_volume(heights):\n"
            "    # Two pointers from both ends; move the shorter wall inward.\n"
            "    return 0\n\n\n"
            "print(max_moat_volume([1, 8, 6, 2, 5, 4, 8, 3, 7]))  # expect 49\n"
            "print(max_moat_volume([4, 4]))                       # expect 4\n"
            "print(max_moat_volume([1, 2, 1]))                    # expect 2\n"
        ),
    },
    # --- Sliding window ---------------------------------------------------------
    {
        "slug": "best-streaming-week",
        "title": "Best Streaming Week",
        "pattern": "sliding-window",
        "difficulty": "easy",
        "prompt": (
            "A streamer's analytics page shows daily viewer counts. They want "
            "to find their best stretch of exactly `k` consecutive days to "
            "feature on their channel page.\n\n"
            "Given a list `viewers` of daily counts and an integer `k`, "
            "return the **maximum total viewers over any k consecutive "
            "days**.\n\n"
            "Constraints: 1 <= k <= len(viewers) <= 10^5. Re-summing every "
            "window is O(n*k); aim for O(n) by reusing the previous "
            "window's sum."
        ),
        "examples": [
            {
                "input": "viewers = [40, 10, 60, 25, 30, 80], k = 2",
                "output": "110",
                "explanation": "Days 4 and 5 (30 + 80) = 110.",
            },
            {
                "input": "viewers = [5, 5, 5], k = 3",
                "output": "15",
                "explanation": "Only one window exists.",
            },
        ],
        "hints": [
            "When the window slides one day to the right, most of the sum is unchanged. What enters and what leaves?",
            "next_sum = current_sum + viewers[right] - viewers[left].",
            "Sum the first k days once, then slide: add the new day, subtract the dropped day, track the max.",
        ],
        "starter_code": (
            "def best_week(viewers, k):\n"
            "    # Fixed-size sliding window: reuse the previous sum.\n"
            "    return 0\n\n\n"
            "print(best_week([40, 10, 60, 25, 30, 80], 2))  # expect 110\n"
            "print(best_week([5, 5, 5], 3))                 # expect 15\n"
            "print(best_week([9], 1))                       # expect 9\n"
        ),
    },
    {
        "slug": "longest-unrepeated-melody",
        "title": "Longest Unrepeated Melody",
        "pattern": "sliding-window",
        "difficulty": "medium",
        "prompt": (
            "A composer considers a melody fragment *fresh* if no note "
            "repeats inside it. Given a string `notes` where each character "
            "is one note (e.g. \"abcabcbb\"), return the **length of the "
            "longest fresh fragment** (contiguous substring with no repeated "
            "character).\n\n"
            "Constraints: 0 <= len(notes) <= 10^5. Aim for O(n) with a "
            "window that grows on the right and shrinks on the left."
        ),
        "examples": [
            {
                "input": 'notes = "abcabcbb"',
                "output": "3",
                "explanation": '"abc" is the longest fragment with no repeats.',
            },
            {
                "input": 'notes = "ededed"',
                "output": "2",
                "explanation": 'Any "ed" or "de" pair; adding a third note always repeats.',
            },
        ],
        "hints": [
            "Maintain a window [left, right] that never contains a repeat. What breaks when you extend right by one note?",
            "If the new note is already in the window, slide `left` forward until the older copy is evicted.",
            "Keep a set (or last-seen-index dict) of notes in the window. Evict from the left while the new note is present, then extend and update the best length.",
        ],
        "starter_code": (
            "def longest_fresh(notes):\n"
            "    # Variable-size window; a set of the notes currently inside.\n"
            "    return 0\n\n\n"
            "print(longest_fresh(\"abcabcbb\"))  # expect 3\n"
            "print(longest_fresh(\"ededed\"))    # expect 2\n"
            "print(longest_fresh(\"\"))          # expect 0\n"
            "print(longest_fresh(\"qqqq\"))      # expect 1\n"
        ),
    },
    # --- Stack -------------------------------------------------------------------
    {
        "slug": "balanced-spellbook",
        "title": "Balanced Spellbook",
        "pattern": "stack",
        "difficulty": "easy",
        "prompt": (
            "Spells in an ancient book wrap their incantations in three kinds "
            "of enclosures: `()`, `[]`, and `{}`. A spell is *stable* if "
            "every opener is closed by the matching closer in the correct "
            "order — `([])` is stable, `([)]` is not.\n\n"
            "Given a string `spell` containing only those six characters, "
            "return True if it is stable.\n\n"
            "Constraints: 0 <= len(spell) <= 10^5. The empty spell is stable."
        ),
        "examples": [
            {
                "input": 'spell = "{[()]}"',
                "output": "True",
                "explanation": "Every bracket closes in last-opened-first-closed order.",
            },
            {
                "input": 'spell = "([)]"',
                "output": "False",
                "explanation": "The ( is closed while [ is still open.",
            },
        ],
        "hints": [
            "Read left to right. When you hit a closer, which opener must it match?",
            "The most recently opened, not-yet-closed one — that's last-in-first-out, i.e. a stack (a Python list with append/pop).",
            "Push openers. On a closer, the stack must be non-empty and its top must be the matching opener; pop it. At the end the stack must be empty.",
        ],
        "starter_code": (
            "def is_stable(spell):\n"
            "    # A list used as a stack: append to push, pop to pop.\n"
            "    return False\n\n\n"
            "print(is_stable(\"{[()]}\"))  # expect True\n"
            "print(is_stable(\"([)]\"))    # expect False\n"
            "print(is_stable(\"\"))        # expect True\n"
            "print(is_stable(\"(((\"))     # expect False\n"
        ),
    },
    {
        "slug": "warmer-days",
        "title": "Warmer Days Ahead",
        "pattern": "stack",
        "difficulty": "medium",
        "prompt": (
            "A meteorologist has the daily high temperature forecast. For "
            "each day they want to print: *how many days until a strictly "
            "warmer day?*\n\n"
            "Given a list `temps`, return a list `wait` of the same length "
            "where `wait[i]` is the number of days until the next strictly "
            "warmer temperature, or 0 if no warmer day ever comes.\n\n"
            "Constraints: 1 <= len(temps) <= 10^5. The nested-loop scan is "
            "O(n^2); aim for O(n) — every day is pushed and popped at most "
            "once."
        ),
        "examples": [
            {
                "input": "temps = [73, 74, 75, 71, 69, 72, 76, 73]",
                "output": "[1, 1, 4, 2, 1, 1, 0, 0]",
                "explanation": "Day 2 (75) waits 4 days for 76; the last two days never see warmer.",
            },
            {
                "input": "temps = [50, 40, 30]",
                "output": "[0, 0, 0]",
                "explanation": "It only gets colder.",
            },
        ],
        "hints": [
            "Walking forward and scanning ahead repeats work. What if you keep the days that are still *waiting* for a warm day?",
            "Keep a stack of indices whose answer is unknown. A new warmer day resolves some of them — which ones, and in what order?",
            "For each day i: while the stack's top index has a colder temp, pop it and set wait[top] = i - top. Then push i. Days left on the stack stay 0.",
        ],
        "starter_code": (
            "def days_until_warmer(temps):\n"
            "    # Monotonic stack of indices still waiting for a warmer day.\n"
            "    return [0] * len(temps)\n\n\n"
            "print(days_until_warmer([73, 74, 75, 71, 69, 72, 76, 73]))\n"
            "# expect [1, 1, 4, 2, 1, 1, 0, 0]\n"
            "print(days_until_warmer([50, 40, 30]))  # expect [0, 0, 0]\n"
        ),
    },
    # --- Binary search -------------------------------------------------------------
    {
        "slug": "guess-the-page",
        "title": "Guess the Page",
        "pattern": "binary-search",
        "difficulty": "easy",
        "prompt": (
            "A librarian keeps a ledger of the catalog numbers shelved in one "
            "aisle, in **sorted** order. Given the sorted list `catalog` and "
            "a number `wanted`, return the index where `wanted` sits, or -1 "
            "if it is not in this aisle.\n\n"
            "Constraints: 0 <= len(catalog) <= 10^5. A linear scan is O(n); "
            "you must do it in O(log n) — each comparison should eliminate "
            "half of the remaining shelf.\n\n"
            "Careful: the classic bugs here are off-by-one in the loop "
            "condition (`<` vs `<=`) and how you move `lo`/`hi`."
        ),
        "examples": [
            {
                "input": "catalog = [2, 5, 8, 12, 16, 23], wanted = 12",
                "output": "3",
                "explanation": "catalog[3] == 12.",
            },
            {
                "input": "catalog = [2, 5, 8], wanted = 7",
                "output": "-1",
                "explanation": "7 is not shelved here.",
            },
        ],
        "hints": [
            "Compare `wanted` to the middle entry. What does the comparison tell you about which half to keep?",
            "Maintain lo and hi as the inclusive bounds of where the answer could still be; loop while lo <= hi.",
            "mid = (lo + hi) // 2. If catalog[mid] < wanted, the answer is right of mid: lo = mid + 1. If greater: hi = mid - 1. Else return mid.",
        ],
        "starter_code": (
            "def find_page(catalog, wanted):\n"
            "    # Binary search: O(log n), inclusive lo/hi bounds.\n"
            "    return -1\n\n\n"
            "print(find_page([2, 5, 8, 12, 16, 23], 12))  # expect 3\n"
            "print(find_page([2, 5, 8], 7))               # expect -1\n"
            "print(find_page([], 4))                      # expect -1\n"
            "print(find_page([9], 9))                     # expect 0\n"
        ),
    },
    {
        "slug": "minimum-reading-speed",
        "title": "Minimum Reading Speed",
        "pattern": "binary-search",
        "difficulty": "medium",
        "prompt": (
            "A student has a stack of reading packets and `hours` hours "
            "before an exam. Each hour they pick ONE packet and read up to "
            "`speed` pages of it; a packet shorter than `speed` still burns "
            "the whole hour (no splitting an hour across packets).\n\n"
            "Given `packets` (pages per packet) and `hours` "
            "(`hours >= len(packets)`), return the **minimum integer speed** "
            "(pages/hour) that finishes everything in time.\n\n"
            "Constraints: 1 <= len(packets) <= 10^4, pages up to 10^9. "
            "Trying speeds 1, 2, 3, ... is too slow — binary search the "
            "answer space instead. Hours for one packet at speed s: "
            "ceil(pages / s)."
        ),
        "examples": [
            {
                "input": "packets = [3, 6, 7, 11], hours = 8",
                "output": "4",
                "explanation": "At 4 pages/hour: 1 + 2 + 2 + 3 = 8 hours. Speed 3 needs 10.",
            },
            {
                "input": "packets = [30], hours = 5",
                "output": "6",
                "explanation": "ceil(30/6) = 5 hours exactly.",
            },
        ],
        "hints": [
            "You are not searching the list — you are searching speeds. For a given speed, can you cheaply check feasibility?",
            "Feasibility is monotonic: if speed s works, every speed above s works too. That yes/no boundary is binary-searchable.",
            "Search lo=1, hi=max(packets). If total hours at mid <= hours, try slower (hi = mid); else faster (lo = mid + 1). ceil without floats: (p + s - 1) // s.",
        ],
        "starter_code": (
            "def min_reading_speed(packets, hours):\n"
            "    # Binary search on the answer (speed), not the list.\n"
            "    return 1\n\n\n"
            "print(min_reading_speed([3, 6, 7, 11], 8))  # expect 4\n"
            "print(min_reading_speed([30], 5))           # expect 6\n"
            "print(min_reading_speed([1, 1, 1], 3))      # expect 1\n"
        ),
    },
    # --- Trees ----------------------------------------------------------------------
    {
        "slug": "deepest-catacomb",
        "title": "Deepest Catacomb",
        "pattern": "trees",
        "difficulty": "easy",
        "prompt": (
            "Catacombs branch underground: each chamber has up to two "
            "passages leading deeper (left and right). The depth of the "
            "catacombs is the number of chambers on the longest path from "
            "the entrance down to a dead end.\n\n"
            "Given the entrance `Chamber` (a binary-tree node with `left` "
            "and `right`, possibly None for an empty catacomb), return the "
            "**maximum depth**.\n\n"
            "The starter code defines the Chamber class and builds a sample "
            "catacomb. Think recursively: the depth at a chamber is defined "
            "by the depths of its sub-catacombs."
        ),
        "examples": [
            {
                "input": "entrance -> (left -> leaf), (right -> chamber -> leaf)",
                "output": "3",
                "explanation": "Longest path: entrance, right chamber, its leaf = 3 chambers.",
            },
            {
                "input": "entrance = None",
                "output": "0",
                "explanation": "No catacomb at all.",
            },
        ],
        "hints": [
            "What is the depth of an empty catacomb (None)? That's your base case.",
            "If you somehow knew the depths of the left and right sub-catacombs, what is the depth at this chamber?",
            "depth(None) = 0; depth(c) = 1 + max(depth(c.left), depth(c.right)). Three lines.",
        ],
        "starter_code": (
            "class Chamber:\n"
            "    def __init__(self, left=None, right=None):\n"
            "        self.left = left\n"
            "        self.right = right\n\n\n"
            "def max_depth(entrance):\n"
            "    # Recursive: 1 + the deeper of the two sub-catacombs.\n"
            "    return 0\n\n\n"
            "# entrance with a left leaf, and a right passage two chambers deep\n"
            "sample = Chamber(left=Chamber(), right=Chamber(left=Chamber()))\n"
            "print(max_depth(sample))    # expect 3\n"
            "print(max_depth(None))      # expect 0\n"
            "print(max_depth(Chamber())) # expect 1\n"
        ),
    },
    {
        "slug": "richest-catacomb-level",
        "title": "Richest Catacomb Level",
        "pattern": "trees",
        "difficulty": "medium",
        "prompt": (
            "The same catacombs, but now every chamber holds `gold`. "
            "Archaeologists excavate one *level* at a time: the entrance is "
            "level 1, its children level 2, and so on.\n\n"
            "Given the entrance chamber, return the **level number with the "
            "highest total gold**. If several levels tie, return the "
            "shallowest. The entrance is never None.\n\n"
            "This is a breadth-first traversal: process the tree level by "
            "level using a queue, not chamber by chamber."
        ),
        "examples": [
            {
                "input": "gold: level 1 = [5], level 2 = [3, 4], level 3 = [10]",
                "output": "3",
                "explanation": "Totals are 5, 7, 10 — level 3 is richest.",
            },
            {
                "input": "gold: level 1 = [9], level 2 = [4, 5]",
                "output": "1",
                "explanation": "Totals are 9 and 9 — a tie, which goes to the shallower level 1.",
            },
        ],
        "hints": [
            "Depth-first recursion makes per-level sums awkward. What order does a queue (collections.deque) give you?",
            "Snapshot trick: len(queue) at the start of each round is exactly how many chambers are on the current level.",
            "Pop that many, sum their gold, push their children; compare against the best with strict > so ties keep the shallowest level.",
        ],
        "starter_code": (
            "from collections import deque\n\n\n"
            "class Chamber:\n"
            "    def __init__(self, gold, left=None, right=None):\n"
            "        self.gold = gold\n"
            "        self.left = left\n"
            "        self.right = right\n\n\n"
            "def richest_level(entrance):\n"
            "    # BFS with a deque; process one full level per outer step.\n"
            "    return 1\n\n\n"
            "sample = Chamber(5, left=Chamber(3, left=Chamber(10)), right=Chamber(4))\n"
            "print(richest_level(sample))                                  # expect 3\n"
            "print(richest_level(Chamber(9, Chamber(4), Chamber(5))))      # expect 1\n"
        ),
    },
    # --- Dynamic programming -----------------------------------------------------------
    {
        "slug": "lantern-staircase",
        "title": "The Lantern Staircase",
        "pattern": "dynamic-programming",
        "difficulty": "easy",
        "prompt": (
            "A temple staircase has `n` steps. Pilgrims climb taking either "
            "1 or 2 steps at a time, and tradition says no two pilgrims may "
            "climb the same *sequence* of steps in one festival.\n\n"
            "Given `n`, return **how many distinct climbing sequences** "
            "exist.\n\n"
            "Constraints: 1 <= n <= 90 (the answer overflows 64 bits beyond "
            "that — fine in Python, fatal in C++; worth knowing). Naive "
            "recursion recomputes the same sub-staircases exponentially "
            "many times; build the answer bottom-up instead."
        ),
        "examples": [
            {
                "input": "n = 3",
                "output": "3",
                "explanation": "1+1+1, 1+2, 2+1.",
            },
            {
                "input": "n = 5",
                "output": "8",
                "explanation": "The counts go 1, 2, 3, 5, 8 — recognize the sequence?",
            },
        ],
        "hints": [
            "Stand on step n. Your last move was either a 1-step from n-1 or a 2-step from n-2. What does that say about the count?",
            "ways(n) = ways(n-1) + ways(n-2), with ways(1) = 1, ways(2) = 2 — Fibonacci in disguise.",
            "You only ever need the previous two values: two variables and a loop, O(n) time, O(1) space. No recursion required.",
        ],
        "starter_code": (
            "def climbing_sequences(n):\n"
            "    # Bottom-up: each step's count comes from the previous two.\n"
            "    return 0\n\n\n"
            "print(climbing_sequences(3))   # expect 3\n"
            "print(climbing_sequences(5))   # expect 8\n"
            "print(climbing_sequences(1))   # expect 1\n"
            "print(climbing_sequences(10))  # expect 89\n"
        ),
    },
    {
        "slug": "museum-night-heist",
        "title": "Museum Night Heist",
        "pattern": "dynamic-programming",
        "difficulty": "medium",
        "prompt": (
            "A row of museum display cases holds exhibits worth "
            "`values[i]` each. The pressure sensors connect **adjacent** "
            "cases: opening two cases that sit next to each other trips the "
            "alarm, but any non-adjacent set is safe.\n\n"
            "Given `values`, return the **maximum total value** obtainable "
            "without opening two adjacent cases.\n\n"
            "Constraints: 1 <= len(values) <= 10^4, values non-negative. "
            "Greedy (always grab the biggest) fails — find a counterexample "
            "for yourself, then think about what choice you face at each "
            "case."
        ),
        "examples": [
            {
                "input": "values = [2, 7, 9, 3, 1]",
                "output": "12",
                "explanation": "Cases 0, 2, 4: 2 + 9 + 1 = 12.",
            },
            {
                "input": "values = [5, 100, 5, 5]",
                "output": "105",
                "explanation": "Open cases 1 and 3 (100 + 5). Skipping the first case beats grabbing it.",
            },
        ],
        "hints": [
            "At case i you either open it (and must skip case i-1) or leave it (keeping whatever was best through i-1).",
            "best(i) = max(best(i-1), best(i-2) + values[i]). What are best(0) and best(1)?",
            "Like the staircase, only the last two 'best' values matter: two rolling variables, one pass, O(1) space.",
        ],
        "starter_code": (
            "def max_heist(values):\n"
            "    # take = best ending with this case opened; skip = best without it.\n"
            "    return 0\n\n\n"
            "print(max_heist([2, 7, 9, 3, 1]))   # expect 12\n"
            "print(max_heist([5, 100, 5, 5]))    # expect 105\n"
            "print(max_heist([7]))               # expect 7\n"
        ),
    },
]


# Human-readable labels for the pattern slugs, used by the frontend filter UI
# (served alongside the problems so the list stays in one place).
PATTERN_LABELS: dict[str, str] = {
    "arrays-hashing": "Arrays & Hashing",
    "two-pointers": "Two Pointers",
    "sliding-window": "Sliding Window",
    "stack": "Stack",
    "binary-search": "Binary Search",
    "trees": "Trees",
    "dynamic-programming": "Dynamic Programming",
}
