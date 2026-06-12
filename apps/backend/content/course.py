"""The beginner "Learn to Code" course.

A fixed, ordered list of lessons. Each lesson is a short read followed by a
hands-on exercise the user can open in the Workspace (the exercise becomes a
runnable Python cell there). Only completion state is stored in the database
(:class:`models.LessonProgress`, keyed by ``id``); the content itself ships
with the app so it works fully offline.

Lesson shape::

    {
        "id": str,        # stable slug; progress is keyed by this
        "title": str,
        "summary": str,   # one line shown in the lesson list
        "body": str,      # the lesson text (markdown-lite: headings, code blocks)
        "exercise": {
            "description": str,
            "starter_code": str,
            "language": "python",
        },
    }
"""

from __future__ import annotations

COURSE_LESSONS: list[dict] = [
    {
        "id": "01-values-and-variables",
        "title": "Values and variables",
        "summary": "Store information in named boxes and print it back out.",
        "body": (
            "Programs work with values: numbers like 42, text like \"hello\" "
            "(called a *string*), and True/False flags (called *booleans*).\n\n"
            "A **variable** is a name you attach to a value so you can use it "
            "later:\n\n"
            "```python\n"
            "age = 19\n"
            "name = \"Sam\"\n"
            "print(name, \"is\", age)\n"
            "```\n\n"
            "Three things to notice:\n"
            "- `=` means \"assign\", not \"equals\". It stores the right side "
            "under the name on the left.\n"
            "- Variables can be reassigned: `age = age + 1` reads the current "
            "value, adds one, and stores it back.\n"
            "- `print(...)` writes values to the screen — it is how your "
            "program talks to you while you learn.\n\n"
            "Run code early and often. The fastest way to learn is to guess "
            "what a line will print, run it, and check yourself."
        ),
        "exercise": {
            "description": (
                "Create variables for your name and birth year, compute your "
                "age this year, and print a sentence using all three."
            ),
            "starter_code": (
                "# 1. Store your name and birth year in variables.\n"
                "# 2. Compute your age in 2026 in a third variable.\n"
                "# 3. Print one sentence that uses all three.\n\n"
                "name = \"Sam\"\n"
                "birth_year = 2007\n"
                "age = 0  # replace this with a calculation\n\n"
                "print(name, \"was born in\", birth_year, \"and turns\", age, \"this year\")\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "02-types-and-arithmetic",
        "title": "Numbers, strings, and types",
        "summary": "Why 2 + 2 is 4 but \"2\" + \"2\" is \"22\".",
        "body": (
            "Every value has a **type**, and the type decides what operations "
            "mean:\n\n"
            "```python\n"
            "print(2 + 2)        # 4        (int: whole number)\n"
            "print(\"2\" + \"2\")    # 22       (str: + glues strings together)\n"
            "print(7 / 2)        # 3.5      (float: division gives decimals)\n"
            "print(7 // 2)       # 3        (floor division: drop the remainder)\n"
            "print(7 % 2)        # 1        (modulo: just the remainder)\n"
            "```\n\n"
            "`%` (modulo) looks obscure but you will use it constantly: "
            "`x % 2 == 0` tests evenness, `x % 10` grabs the last digit.\n\n"
            "You can convert between types with `int(...)`, `float(...)`, and "
            "`str(...)`. A classic beginner crash is mixing them: "
            "`\"age: \" + 19` is an error, while `\"age: \" + str(19)` works.\n\n"
            "Use `type(value)` whenever you are unsure what you are holding."
        ),
        "exercise": {
            "description": (
                "Given a total number of seconds, print it as minutes and "
                "seconds using // and %."
            ),
            "starter_code": (
                "total_seconds = 754\n\n"
                "# Compute minutes and leftover seconds with // and %.\n"
                "minutes = 0   # replace\n"
                "seconds = 0   # replace\n\n"
                "print(total_seconds, \"seconds is\", minutes, \"minutes and\", seconds, \"seconds\")\n"
                "# Expected: 754 seconds is 12 minutes and 34 seconds\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "03-conditionals",
        "title": "Making decisions with if",
        "summary": "Run different code depending on a condition.",
        "body": (
            "An `if` statement chooses a path through your program:\n\n"
            "```python\n"
            "temperature = 31\n"
            "if temperature > 30:\n"
            "    print(\"hot\")\n"
            "elif temperature > 15:\n"
            "    print(\"mild\")\n"
            "else:\n"
            "    print(\"cold\")\n"
            "```\n\n"
            "The condition is any expression that is True or False: "
            "`x == y` (equal), `x != y` (not equal), `x < y`, `x >= y`. "
            "Combine conditions with `and`, `or`, and `not`.\n\n"
            "**Indentation is the syntax.** Everything indented under the `if` "
            "belongs to it; the first unindented line is back outside. Python "
            "checks the branches top to bottom and runs only the first one "
            "whose condition is true — order your checks from most to least "
            "specific."
        ),
        "exercise": {
            "description": (
                "Classify a number as 'fizz' (divisible by 3), 'buzz' "
                "(divisible by 5), 'fizzbuzz' (both), or the number itself."
            ),
            "starter_code": (
                "n = 15\n\n"
                "# Print 'fizzbuzz' if n is divisible by both 3 and 5,\n"
                "# 'fizz' for just 3, 'buzz' for just 5, else print n.\n"
                "# Hint: check the 'both' case first — why?\n\n"
                "if n % 3 == 0:\n"
                "    print(\"fizz\")\n"
                "else:\n"
                "    print(n)\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "04-loops",
        "title": "Repeating work with loops",
        "summary": "Do something for every item, or until a condition changes.",
        "body": (
            "A `for` loop runs its body once per item:\n\n"
            "```python\n"
            "for i in range(5):      # i = 0, 1, 2, 3, 4\n"
            "    print(i * i)\n"
            "```\n\n"
            "`range(5)` counts 0 through 4 — starting at zero and stopping "
            "*before* the end is everywhere in programming, so internalize it "
            "now.\n\n"
            "A very common shape is the **accumulator**: start with an empty "
            "result and fold each item into it.\n\n"
            "```python\n"
            "total = 0\n"
            "for price in [4, 9, 2]:\n"
            "    total = total + price\n"
            "print(total)            # 15\n"
            "```\n\n"
            "`while` loops repeat as long as a condition holds — use them when "
            "you don't know how many steps you need. If your while loop never "
            "changes its condition, it runs forever; the runner will cut it "
            "off with a timeout, which is itself a useful clue."
        ),
        "exercise": {
            "description": (
                "Sum the even numbers from 1 to 100 inclusive using a loop "
                "and an accumulator."
            ),
            "starter_code": (
                "# Sum every even number from 1 to 100 (inclusive).\n"
                "# Expected answer: 2550\n\n"
                "total = 0\n"
                "for n in range(1, 101):\n"
                "    pass  # replace: add n to total only when n is even\n\n"
                "print(total)\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "05-functions",
        "title": "Functions: naming a piece of work",
        "summary": "Package logic behind a name, with inputs and an output.",
        "body": (
            "A **function** wraps some logic so you can run it on different "
            "inputs without copying the code:\n\n"
            "```python\n"
            "def area(width, height):\n"
            "    return width * height\n\n"
            "print(area(3, 4))    # 12\n"
            "print(area(10, 2))   # 20\n"
            "```\n\n"
            "- `def` defines the function; `width` and `height` are "
            "**parameters** — placeholder variables filled in at each call.\n"
            "- `return` hands a value back to the caller and ends the "
            "function. A function with no `return` gives back `None`.\n"
            "- `return` is not `print`: returning produces a value your "
            "program can keep computing with; printing only displays it.\n\n"
            "Functions are also how interview problems are phrased — "
            "\"write a function that ...\" — so from here on, the exercises "
            "use them."
        ),
        "exercise": {
            "description": (
                "Write is_palindrome(text) that returns True when text reads "
                "the same forwards and backwards."
            ),
            "starter_code": (
                "def is_palindrome(text):\n"
                "    # Hint: text[::-1] is the string reversed.\n"
                "    return False  # replace\n\n\n"
                "print(is_palindrome(\"racecar\"))  # expect True\n"
                "print(is_palindrome(\"rocket\"))   # expect False\n"
                "print(is_palindrome(\"a\"))        # expect True\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "06-lists",
        "title": "Lists: ordered collections",
        "summary": "Hold many values in order; index, slice, append, iterate.",
        "body": (
            "A **list** holds values in order:\n\n"
            "```python\n"
            "scores = [88, 92, 79]\n"
            "print(scores[0])       # 88   (positions start at 0)\n"
            "print(scores[-1])      # 79   (negative counts from the end)\n"
            "print(len(scores))     # 3\n"
            "scores.append(95)      # add to the end\n"
            "```\n\n"
            "Loop over items directly (`for s in scores:`) when you only need "
            "values, or over positions (`for i in range(len(scores)):`) when "
            "you need the index too.\n\n"
            "**Slicing** copies a sub-range: `scores[1:3]` is items 1 and 2 "
            "(the end index is excluded, just like `range`).\n\n"
            "Lists + loops + accumulators are the workhorse trio: find the "
            "max, count matches, build a new filtered list. Most early "
            "interview problems are exactly this in disguise."
        ),
        "exercise": {
            "description": (
                "Write largest_gap(nums) returning the difference between "
                "the largest and smallest values — without min() or max()."
            ),
            "starter_code": (
                "def largest_gap(nums):\n"
                "    # Track the smallest and largest seen so far in one pass.\n"
                "    # Do not use min() or max() — build the logic yourself.\n"
                "    return 0  # replace\n\n\n"
                "print(largest_gap([3, 10, 4, 1, 7]))   # expect 9\n"
                "print(largest_gap([5]))                # expect 0\n"
                "print(largest_gap([-2, -9, -4]))       # expect 7\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "07-dictionaries",
        "title": "Dictionaries: lookups by key",
        "summary": "Map keys to values for instant lookup — the hash map.",
        "body": (
            "A **dictionary** (dict) maps keys to values:\n\n"
            "```python\n"
            "stock = {\"apple\": 4, \"pear\": 0}\n"
            "print(stock[\"apple\"])          # 4\n"
            "stock[\"plum\"] = 7              # insert\n"
            "print(\"pear\" in stock)         # True  (membership test)\n"
            "print(stock.get(\"kiwi\", 0))    # 0     (default when missing)\n"
            "```\n\n"
            "The superpower: looking up a key takes the same tiny amount of "
            "time no matter how big the dict is. A list makes you scan; a "
            "dict answers instantly.\n\n"
            "The counting pattern appears everywhere:\n\n"
            "```python\n"
            "counts = {}\n"
            "for ch in \"banana\":\n"
            "    counts[ch] = counts.get(ch, 0) + 1\n"
            "# {'b': 1, 'a': 3, 'n': 2}\n"
            "```\n\n"
            "In interviews this is the \"hash map\" — the single most useful "
            "tool for turning a slow nested-loop solution into a fast "
            "single-pass one."
        ),
        "exercise": {
            "description": (
                "Write most_common(words) returning the word that appears "
                "most often in a list."
            ),
            "starter_code": (
                "def most_common(words):\n"
                "    # 1. Build a dict of word -> count.\n"
                "    # 2. Loop over the dict to find the key with the biggest count.\n"
                "    return \"\"  # replace\n\n\n"
                "print(most_common([\"cat\", \"dog\", \"cat\", \"bird\", \"cat\"]))  # expect cat\n"
                "print(most_common([\"a\", \"b\", \"b\"]))                      # expect b\n"
            ),
            "language": "python",
        },
    },
    {
        "id": "08-putting-it-together",
        "title": "Putting it together",
        "summary": "Solve a multi-step problem with everything so far.",
        "body": (
            "Real problems rarely say which tool to use. The craft is "
            "decomposing them:\n\n"
            "1. **Restate the problem** in your own words, with a tiny example "
            "you can check by hand.\n"
            "2. **Pick representations**: is the data a list? a dict? counts? "
            "positions?\n"
            "3. **Write the skeleton**: function signature, an obvious loop, "
            "an accumulator, then fill in the logic.\n"
            "4. **Test with the example**, then with edge cases: empty input, "
            "one item, ties, negatives.\n\n"
            "When you are stuck, shrink the problem: solve it for a list of "
            "one item, then two. Print intermediate values shamelessly — "
            "the print statement is a debugger you already know how to use.\n\n"
            "After this lesson, head to the **DSA Practice** tab: the problems "
            "there are grouped by pattern (hash maps, two pointers, sliding "
            "windows...), and Whetstone's local model can generate fresh "
            "variants of any problem that gives you trouble."
        ),
        "exercise": {
            "description": (
                "Class gradebook: given (name, score) pairs, print each "
                "student's average, then the top student."
            ),
            "starter_code": (
                "entries = [\n"
                "    (\"ana\", 90), (\"ben\", 72), (\"ana\", 76),\n"
                "    (\"cal\", 88), (\"ben\", 94), (\"ana\", 92),\n"
                "]\n\n"
                "# 1. Build name -> list of scores (dict of lists).\n"
                "# 2. Print each student's average, e.g. 'ana 86.0'.\n"
                "# 3. Print the student with the highest average.\n"
                "#    Expected top student: ana\n\n"
                "scores = {}\n"
                "for name, score in entries:\n"
                "    pass  # replace: append score to that student's list\n"
            ),
            "language": "python",
        },
    },
]


def lesson_by_id(lesson_id: str) -> dict | None:
    """Return the lesson dict for ``lesson_id``, or None if unknown."""

    for lesson in COURSE_LESSONS:
        if lesson["id"] == lesson_id:
            return lesson
    return None
