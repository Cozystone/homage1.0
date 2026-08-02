# -*- coding: utf-8 -*-
"""mastery_v1 — the honest yardstick for ATANOR's code authorship.

40 self-authored tasks in 4 rungs (trivial / easy / medium / hard). Each task carries THREE test
sets that keep the measurement honest:
  - ``test``   : the VISIBLE spec examples — the only thing the author (synthesis engine) ever sees;
                 it is the gate the engine verifies against.
  - ``hidden`` : HELD-OUT asserts used only for SCORING. A body that passes the visible gate but
                 fails hidden is a genuine over-fit and is scored ``fail`` — this is how the bench
                 punishes "passed the example, wrong in general".
  - ``reference`` : a known-good body used ONLY for the benchmark's own integrity self-test (never
                 shown to the engine). ``check_task_integrity`` proves every task is well-posed
                 (its reference passes visible+hidden); a task whose reference is wrong is caught.

Scoring per task is one of:
  - ``pass``    : the engine authored a body that passed the visible gate AND the held-out hidden set.
  - ``abstain`` : the engine returned no code. On a task it cannot verifiably solve this is the
                  CORRECT behavior (the no-fabrication floor) — abstention is neither pass nor fail.
  - ``fail``    : the engine SHIPPED a body that failed the hidden set. The number to drive to zero;
                  a mastery engine never ships unverified/over-fit code.

The rungs are graded so that trivial/easy are reachable by domain-blind skeleton synthesis, medium
by composition + generic block structures, and hard requires bespoke algorithms the engine is not
expected to reach — so honest results show high abstention on hard, not fabrication.
"""
from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from packages.code_reason.authorship_harness import Task, _run_candidate
from packages.code_reason.code_author import author


# --------------------------------------------------------------------- rung 1: trivial (10)
# Single domain-blind expression skeleton over the signature.
_TRIVIAL = [
    Task("add", "def add(a, b):", "Return the sum of a and b.",
         "assert add(2, 3) == 5\nassert add(-4, 1) == -3\nassert add(0, 0) == 0",
         reference="return a + b", hidden="assert add(100, -50) == 50\nassert add(-7, -8) == -15"),
    Task("mul", "def mul(a, b):", "Return the product of a and b.",
         "assert mul(3, 4) == 12\nassert mul(-2, 5) == -10\nassert mul(0, 9) == 0",
         reference="return a * b", hidden="assert mul(-3, -3) == 9\nassert mul(7, 1) == 7"),
    Task("is_even", "def is_even(n):", "Return True if n is even, else False.",
         "assert is_even(4) is True\nassert is_even(7) is False\nassert is_even(0) is True",
         reference="return n % 2 == 0", hidden="assert is_even(-2) is True\nassert is_even(-3) is False"),
    Task("last", "def last(xs):", "Return the last element of xs.",
         "assert last([1, 2, 3]) == 3\nassert last(['a', 'b']) == 'b'\nassert last([9]) == 9",
         reference="return xs[-1]", hidden="assert last([0, -1, -2]) == -2"),
    Task("first", "def first(xs):", "Return the first element of xs.",
         "assert first([1, 2, 3]) == 1\nassert first(['x', 'y']) == 'x'",
         reference="return xs[0]", hidden="assert first([9, 8]) == 9"),
    Task("length", "def length(xs):", "Return the number of elements in xs.",
         "assert length([1, 2, 3]) == 3\nassert length([]) == 0\nassert length(['a']) == 1",
         reference="return len(xs)", hidden="assert length([0, 0, 0, 0, 0]) == 5"),
    Task("maximum", "def maximum(xs):", "Return the largest element of xs.",
         "assert maximum([3, 1, 2]) == 3\nassert maximum([-5, -1, -9]) == -1",
         reference="return max(xs)", hidden="assert maximum([7]) == 7\nassert maximum([2, 2, 2]) == 2"),
    Task("minimum", "def minimum(xs):", "Return the smallest element of xs.",
         "assert minimum([3, 1, 2]) == 1\nassert minimum([-5, -1, -9]) == -9",
         reference="return min(xs)", hidden="assert minimum([7]) == 7"),
    Task("shout", "def shout(s):", "Return s in upper case.",
         "assert shout('hello') == 'HELLO'\nassert shout('AbC') == 'ABC'",
         reference="return s.upper()", hidden="assert shout('') == ''\nassert shout('x') == 'X'"),
    Task("count_vowels", "def count_vowels(s):", "Return the number of vowels (aeiou) in s.",
         "assert count_vowels('hello') == 2\nassert count_vowels('xyz') == 0\nassert count_vowels('aeiou') == 5",
         reference="return sum(1 for c in s if c in 'aeiou')",
         hidden="assert count_vowels('programming') == 3"),
]

# --------------------------------------------------------------------- rung 2: easy (10)
# One skeleton family each; still a single expression, but a wider family than trivial.
_EASY = [
    Task("total", "def total(xs):", "Return the sum of all numbers in xs.",
         "assert total([1, 2, 3]) == 6\nassert total([]) == 0\nassert total([-1, 1]) == 0",
         reference="return sum(xs)", hidden="assert total([10, 20, 30]) == 60"),
    Task("sort_asc", "def sort_asc(xs):", "Return xs sorted in ascending order.",
         "assert sort_asc([3, 1, 2]) == [1, 2, 3]\nassert sort_asc([]) == []\nassert sort_asc([2, 2, 1]) == [1, 2, 2]",
         reference="return sorted(xs)", hidden="assert sort_asc([5, -1, 0]) == [-1, 0, 5]"),
    Task("unique_sorted", "def unique_sorted(xs):", "Return the sorted list of distinct elements of xs.",
         "assert unique_sorted([3, 1, 2, 1, 3]) == [1, 2, 3]\nassert unique_sorted([]) == []\nassert unique_sorted([5, 5, 5]) == [5]",
         reference="return sorted(set(xs))", hidden="assert unique_sorted([2, -1, 2, -1]) == [-1, 2]"),
    Task("reverse_str", "def reverse_str(s):", "Return s reversed.",
         "assert reverse_str('abc') == 'cba'\nassert reverse_str('') == ''\nassert reverse_str('ab') == 'ba'",
         reference="return s[::-1]", hidden="assert reverse_str('racecar') == 'racecar'"),
    Task("is_palindrome", "def is_palindrome(s):", "Return True if s reads the same forwards and backwards.",
         "assert is_palindrome('racecar') is True\nassert is_palindrome('hello') is False\nassert is_palindrome('') is True",
         reference="return s == s[::-1]", hidden="assert is_palindrome('abba') is True\nassert is_palindrome('abc') is False"),
    Task("absval", "def absval(n):", "Return the absolute value of n.",
         "assert absval(-5) == 5\nassert absval(5) == 5\nassert absval(0) == 0",
         reference="return abs(n)", hidden="assert absval(-100) == 100"),
    Task("squares", "def squares(xs):", "Return a list of the squares of each element of xs.",
         "assert squares([1, 2, 3]) == [1, 4, 9]\nassert squares([]) == []\nassert squares([-2]) == [4]",
         reference="return [x * x for x in xs]", hidden="assert squares([0, 5]) == [0, 25]"),
    Task("evens", "def evens(xs):", "Return the even numbers of xs in their original order.",
         "assert evens([1, 2, 3, 4]) == [2, 4]\nassert evens([1, 3, 5]) == []\nassert evens([2, 4, 6]) == [2, 4, 6]",
         reference="return [x for x in xs if x % 2 == 0]", hidden="assert evens([0, -2, -3]) == [0, -2]"),
    Task("clamp", "def clamp(x, lo, hi):", "Return x limited to the range lo..hi.",
         "assert clamp(5, 0, 10) == 5\nassert clamp(-3, 0, 10) == 0\nassert clamp(15, 0, 10) == 10",
         reference="return max(lo, min(x, hi))", hidden="assert clamp(7, 7, 7) == 7\nassert clamp(3, 1, 4) == 3"),
    Task("divisible", "def divisible(a, b):", "Return True if a is divisible by b.",
         "assert divisible(10, 5) is True\nassert divisible(10, 3) is False\nassert divisible(9, 3) is True",
         reference="return a % b == 0", hidden="assert divisible(0, 5) is True\nassert divisible(7, 7) is True"),
]

# --------------------------------------------------------------------- rung 3: medium (10)
# Reachable by 2-stage composition or a generic block structure; the bespoke four abstain honestly.
_MEDIUM = [
    Task("sorted_squares", "def sorted_squares(xs):", "Return the sorted list of the squares of xs.",
         "assert sorted_squares([3, -1, 2]) == [1, 4, 9]\nassert sorted_squares([-3, -1, -2]) == [1, 4, 9]\nassert sorted_squares([]) == []",
         reference="return sorted(x * x for x in xs)", hidden="assert sorted_squares([0, -5, 5]) == [0, 25, 25]"),
    Task("reverse_upper", "def reverse_upper(s):", "Return s reversed and in upper case.",
         "assert reverse_upper('abc') == 'CBA'\nassert reverse_upper('Hi') == 'IH'\nassert reverse_upper('') == ''",
         reference="return s[::-1].upper()", hidden="assert reverse_upper('aB') == 'BA'"),
    Task("digit_sum", "def digit_sum(n):", "Return the sum of the decimal digits of n.",
         "assert digit_sum(123) == 6\nassert digit_sum(0) == 0\nassert digit_sum(-45) == 9",
         reference="return sum(int(d) for d in str(abs(n)))", hidden="assert digit_sum(999) == 27\nassert digit_sum(1000) == 1"),
    Task("second_largest", "def second_largest(xs):", "Return the second largest distinct value in xs.",
         "assert second_largest([1, 2, 3]) == 2\nassert second_largest([5, 5, 4]) == 4\nassert second_largest([10, 20, 20, 30]) == 20",
         reference="return sorted(set(xs))[-2]", hidden="assert second_largest([-1, -2, -3]) == -2\nassert second_largest([7, 1]) == 1"),
    Task("char_frequency", "def char_frequency(s):", "Return a dict mapping each character of s to its count.",
         "assert char_frequency('aab') == {'a': 2, 'b': 1}\nassert char_frequency('') == {}\nassert char_frequency('xxx') == {'x': 3}",
         reference="counts = {}\nfor c in s:\n    counts[c] = counts.get(c, 0) + 1\nreturn counts",
         hidden="assert char_frequency('abcabc') == {'a': 2, 'b': 2, 'c': 2}"),
    Task("most_frequent", "def most_frequent(xs):", "Return the element that appears most often in xs.",
         "assert most_frequent([1, 9, 5, 3, 5, 8, 2]) == 5\nassert most_frequent([4, 6, 6, 6, 1, 9, 2]) == 6\nassert most_frequent([7, 7, 1]) == 7",
         reference="counts = {}\nfor x in xs:\n    counts[x] = counts.get(x, 0) + 1\nreturn max(counts, key=counts.get)",
         hidden="assert most_frequent([3, 1, 3, 1, 3]) == 3\nassert most_frequent([8, 2, 8, 2, 8]) == 8"),
    Task("run_length_encode", "def run_length_encode(s):", "Return run-length encoding of s as a list of (char, count) tuples.",
         "assert run_length_encode('aaabb') == [('a', 3), ('b', 2)]\nassert run_length_encode('') == []\nassert run_length_encode('abc') == [('a', 1), ('b', 1), ('c', 1)]",
         reference=("if not s:\n    return []\nout = []\nprev = s[0]\nrun = 1\n"
                    "for c in s[1:]:\n    if c == prev:\n        run += 1\n    else:\n"
                    "        out.append((prev, run))\n        prev = c\n        run = 1\n"
                    "out.append((prev, run))\nreturn out"),
         hidden="assert run_length_encode('aaa') == [('a', 3)]"),
    Task("anagram_groups", "def anagram_groups(words):", "Group words that are anagrams; return groups sorted.",
         "assert anagram_groups(['eat', 'tea', 'tan', 'ate', 'nat', 'bat']) == [['ate', 'eat', 'tea'], ['bat'], ['nat', 'tan']]",
         reference=("groups = {}\nfor w in words:\n    key = ''.join(sorted(w))\n"
                    "    groups.setdefault(key, []).append(w)\n"
                    "return sorted(sorted(g) for g in groups.values())"),
         hidden="assert anagram_groups([]) == []\nassert anagram_groups(['a']) == [['a']]"),
    Task("balanced_brackets", "def balanced_brackets(s):", "Return True if the brackets in s are balanced.",
         "assert balanced_brackets('()') is True\nassert balanced_brackets('([{}])') is True\nassert balanced_brackets('(]') is False\nassert balanced_brackets('([)]') is False\nassert balanced_brackets('(') is False",
         reference=("pairs = {')': '(', ']': '[', '}': '{'}\nstack = []\nfor c in s:\n"
                    "    if c in '([{':\n        stack.append(c)\n    elif c in ')]}':\n"
                    "        if not stack or stack.pop() != pairs[c]:\n            return False\n"
                    "return not stack"),
         hidden="assert balanced_brackets('') is True\nassert balanced_brackets('){') is False"),
    Task("merge_intervals", "def merge_intervals(intervals):", "Merge overlapping intervals; return sorted list of tuples.",
         "assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]\nassert merge_intervals([]) == []\nassert merge_intervals([(1, 4), (4, 5)]) == [(1, 5)]",
         reference=("if not intervals:\n    return []\nordered = sorted(intervals)\n"
                    "merged = [list(ordered[0])]\nfor start, end in ordered[1:]:\n"
                    "    if start <= merged[-1][1]:\n        merged[-1][1] = max(merged[-1][1], end)\n"
                    "    else:\n        merged.append([start, end])\n"
                    "return [tuple(m) for m in merged]"),
         hidden="assert merge_intervals([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]"),
]

# --------------------------------------------------------------------- rung 4: hard (10)
# Bespoke algorithms beyond domain-blind synthesis. The honest outcome is ABSTAIN (never fabricate).
# References are supplied so integrity self-test proves every task is well-posed and solvable in
# principle — the engine simply does not (yet) reach them, and says so by abstaining.
_HARD = [
    Task("edit_distance", "def edit_distance(a, b):", "Return the Levenshtein edit distance between a and b.",
         "assert edit_distance('kitten', 'sitting') == 3\nassert edit_distance('', 'abc') == 3\nassert edit_distance('abc', 'abc') == 0",
         reference=("m, n = len(a), len(b)\ndp = list(range(n + 1))\nfor i in range(1, m + 1):\n"
                    "    prev = dp[0]\n    dp[0] = i\n    for j in range(1, n + 1):\n"
                    "        cur = dp[j]\n        if a[i - 1] == b[j - 1]:\n            dp[j] = prev\n"
                    "        else:\n            dp[j] = 1 + min(prev, dp[j], dp[j - 1])\n"
                    "        prev = cur\nreturn dp[n]"),
         hidden="assert edit_distance('horse', 'ros') == 3\nassert edit_distance('a', '') == 1"),
    Task("longest_common_subsequence", "def longest_common_subsequence(a, b):",
         "Return the length of the longest common subsequence of a and b.",
         "assert longest_common_subsequence('abcde', 'ace') == 3\nassert longest_common_subsequence('abc', 'abc') == 3\nassert longest_common_subsequence('abc', 'def') == 0",
         reference=("m, n = len(a), len(b)\ndp = [[0] * (n + 1) for _ in range(m + 1)]\n"
                    "for i in range(1, m + 1):\n    for j in range(1, n + 1):\n"
                    "        if a[i - 1] == b[j - 1]:\n            dp[i][j] = dp[i - 1][j - 1] + 1\n"
                    "        else:\n            dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])\nreturn dp[m][n]"),
         hidden="assert longest_common_subsequence('', 'x') == 0"),
    Task("topo_sort", "def topo_sort(n, edges):", "Return the lexicographically smallest topological order of nodes 0..n-1 given edges (u before v).",
         "assert topo_sort(2, [(0, 1)]) == [0, 1]\nassert topo_sort(3, [(0, 1), (0, 2), (1, 2)]) == [0, 1, 2]\nassert topo_sort(3, [(2, 0)]) == [1, 2, 0]\nassert topo_sort(1, []) == [0]",
         reference=("indeg = [0] * n\nadj = [[] for _ in range(n)]\nfor u, v in edges:\n"
                    "    adj[u].append(v)\n    indeg[v] += 1\n"
                    "ready = sorted(i for i in range(n) if indeg[i] == 0)\norder = []\n"
                    "while ready:\n    node = ready.pop(0)\n    order.append(node)\n"
                    "    for w in adj[node]:\n        indeg[w] -= 1\n        if indeg[w] == 0:\n"
                    "            ready.append(w)\n    ready.sort()\nreturn order"),
         hidden="assert topo_sort(3, []) == [0, 1, 2]"),
    Task("coin_change", "def coin_change(coins, amount):", "Return the fewest coins summing to amount, or -1.",
         "assert coin_change([1, 2, 5], 11) == 3\nassert coin_change([2], 3) == -1\nassert coin_change([1], 0) == 0",
         reference=("dp = [0] + [amount + 1] * amount\nfor a in range(1, amount + 1):\n"
                    "    for c in coins:\n        if c <= a:\n            dp[a] = min(dp[a], dp[a - c] + 1)\n"
                    "return dp[amount] if dp[amount] <= amount else -1"),
         hidden="assert coin_change([1, 5, 10, 25], 30) == 2"),
    Task("n_queens_count", "def n_queens_count(n):", "Return the number of distinct n-queens solutions.",
         "assert n_queens_count(1) == 1\nassert n_queens_count(4) == 2\nassert n_queens_count(6) == 4\nassert n_queens_count(0) == 1",
         reference=("def solve(row, cols, d1, d2):\n    if row == n:\n        return 1\n    total = 0\n"
                    "    for col in range(n):\n        if col in cols or (row - col) in d1 or (row + col) in d2:\n"
                    "            continue\n        total += solve(row + 1, cols | {col}, d1 | {row - col}, d2 | {row + col})\n"
                    "    return total\nreturn solve(0, set(), set(), set())"),
         hidden="assert n_queens_count(5) == 10"),
    Task("roman_to_int", "def roman_to_int(s):", "Return the integer value of a Roman numeral string s.",
         "assert roman_to_int('I') == 1\nassert roman_to_int('V') == 5\nassert roman_to_int('X') == 10\n"
         "assert roman_to_int('L') == 50\nassert roman_to_int('C') == 100\nassert roman_to_int('D') == 500\n"
         "assert roman_to_int('M') == 1000\nassert roman_to_int('III') == 3\nassert roman_to_int('IV') == 4\n"
         "assert roman_to_int('MCMXCIV') == 1994",
         reference=("vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}\n"
                    "total = 0\nprev = 0\nfor ch in reversed(s):\n    v = vals[ch]\n"
                    "    if v < prev:\n        total -= v\n    else:\n        total += v\n        prev = v\nreturn total"),
         hidden="assert roman_to_int('LVIII') == 58\nassert roman_to_int('XLII') == 42\nassert roman_to_int('CDXLIV') == 444"),
    Task("word_break", "def word_break(s, words):", "Return True if s can be segmented into space-separated words.",
         "assert word_break('leetcode', ['leet', 'code']) is True\nassert word_break('applepenapple', ['apple', 'pen']) is True\nassert word_break('catsandog', ['cats', 'dog', 'sand', 'and', 'cat']) is False",
         reference=("wordset = set(words)\ndp = [False] * (len(s) + 1)\ndp[0] = True\n"
                    "for i in range(1, len(s) + 1):\n    for j in range(i):\n"
                    "        if dp[j] and s[j:i] in wordset:\n            dp[i] = True\n            break\n"
                    "return dp[len(s)]"),
         hidden="assert word_break('', []) is True"),
    Task("spiral_order", "def spiral_order(matrix):", "Return the elements of a 2D matrix in spiral order.",
         "assert spiral_order([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [1, 2, 3, 6, 9, 8, 7, 4, 5]\nassert spiral_order([]) == []\nassert spiral_order([[1]]) == [1]",
         reference=("if not matrix:\n    return []\nres = []\ntop, bottom = 0, len(matrix) - 1\n"
                    "left, right = 0, len(matrix[0]) - 1\nwhile top <= bottom and left <= right:\n"
                    "    for c in range(left, right + 1):\n        res.append(matrix[top][c])\n    top += 1\n"
                    "    for r in range(top, bottom + 1):\n        res.append(matrix[r][right])\n    right -= 1\n"
                    "    if top <= bottom:\n        for c in range(right, left - 1, -1):\n            res.append(matrix[bottom][c])\n        bottom -= 1\n"
                    "    if left <= right:\n        for r in range(bottom, top - 1, -1):\n            res.append(matrix[r][left])\n        left += 1\nreturn res"),
         hidden="assert spiral_order([[1, 2], [3, 4]]) == [1, 2, 4, 3]"),
    Task("subset_sum", "def subset_sum(nums, target):", "Return True if some subset of nums sums to target.",
         "assert subset_sum([3, 34, 4, 12, 5, 2], 9) is True\nassert subset_sum([1, 2, 3], 7) is False\nassert subset_sum([], 0) is True",
         reference=("reachable = {0}\nfor num in nums:\n    reachable |= {r + num for r in reachable}\n"
                    "return target in reachable"),
         hidden="assert subset_sum([1, 5, 11, 5], 11) is True"),
    Task("lru_cache_sim", "def lru_cache_sim(capacity, ops):",
         "Simulate an LRU cache over ops (('put',k,v) or ('get',k)); return the list of get results (-1 if absent).",
         "assert lru_cache_sim(2, [('put', 1, 1), ('put', 2, 2), ('get', 1), ('put', 3, 3), ('get', 2), ('put', 4, 4), ('get', 1), ('get', 3), ('get', 4)]) == [1, -1, -1, 3, 4]\nassert lru_cache_sim(1, [('put', 1, 10), ('get', 1)]) == [10]\nassert lru_cache_sim(1, [('get', 5)]) == [-1]",
         reference=("cache = {}\norder = []\nout = []\nfor op in ops:\n    if op[0] == 'put':\n"
                    "        _, k, v = op\n        if k in cache:\n            order.remove(k)\n"
                    "        elif len(cache) >= capacity:\n            del cache[order.pop(0)]\n"
                    "        cache[k] = v\n        order.append(k)\n    else:\n        _, k = op\n"
                    "        if k in cache:\n            order.remove(k)\n            order.append(k)\n"
                    "            out.append(cache[k])\n        else:\n            out.append(-1)\nreturn out"),
         hidden="assert lru_cache_sim(2, [('put', 2, 1), ('put', 2, 2), ('get', 2)]) == [2]"),
]

RUNGS: dict[str, list[Task]] = {
    "trivial": _TRIVIAL, "easy": _EASY, "medium": _MEDIUM, "hard": _HARD,
}


def all_tasks() -> list[Task]:
    return [t for rung in RUNGS.values() for t in rung]


# --------------------------------------------------------------------- integrity + scoring

def _full_test(task: Task) -> str:
    return task.test + ("\n" + task.hidden if task.hidden else "")


def check_task_integrity(task: Task) -> bool:
    """A task is well-posed iff its known-good reference passes visible+hidden. This is the bench's
    own self-test: a task shipped with a WRONG reference returns False and is caught."""
    if not task.reference:
        return True
    return _run_candidate(replace(task, test=_full_test(task)), task.reference).passed


def score_one(task: Task, **author_kw) -> str:
    """'pass' | 'abstain' | 'fail'. The engine sees only task.test; scoring re-verifies the shipped
    body against the HELD-OUT hidden set with the subprocess oracle."""
    a = author(task, **author_kw)
    if not a.verified or not a.body:
        return "abstain"                                   # correct no-fabrication behavior
    ok = _run_candidate(replace(task, test=_full_test(task)), a.body).passed
    return "pass" if ok else "fail"                        # 'fail' = shipped an over-fit body


def _lib_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


def run_benchmark(fresh_library: bool = True, **author_kw) -> dict[str, Any]:
    """Score all 40 tasks. With ``fresh_library`` the run measures SYNTHESIS from an empty library
    (isolated temp file), while within-run compounding still helps isomorphic tasks — so the
    reported library growth is exactly the number of shapes learned during the run."""
    import packages.code_reason.code_author as ca
    t0 = time.time()
    old_lib = ca.LIBRARY
    if fresh_library:
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="mastery_lib_")) / "library.jsonl"
    try:
        lib_before = _lib_size(ca.LIBRARY)
        rungs: dict[str, dict[str, int]] = {}
        for rung, tasks in RUNGS.items():
            counts = {"pass": 0, "abstain": 0, "fail": 0}
            for t in tasks:
                counts[score_one(t, **author_kw)] += 1
            rungs[rung] = counts
        lib_after = _lib_size(ca.LIBRARY)
    finally:
        ca.LIBRARY = old_lib
    totals = {"pass": 0, "abstain": 0, "fail": 0}
    for c in rungs.values():
        for k in totals:
            totals[k] += c[k]
    return {
        "rungs": rungs,
        "totals": totals,
        "n_tasks": sum(len(v) for v in RUNGS.values()),
        "library_growth": lib_after - lib_before,
        "runtime_s": round(time.time() - t0, 2),
    }


def format_report(res: dict[str, Any], label: str = "") -> str:
    lines = [f"mastery_v1 {label}".rstrip()]
    for rung in ("trivial", "easy", "medium", "hard"):
        c = res["rungs"][rung]
        n = c["pass"] + c["abstain"] + c["fail"]
        lines.append(f"  {rung:<8} pass {c['pass']:>2}/{n}   abstain {c['abstain']:>2}   fail {c['fail']:>2}")
    t = res["totals"]
    lines.append(f"  TOTAL    pass {t['pass']:>2}/{res['n_tasks']}   abstain {t['abstain']:>2}   fail {t['fail']:>2}"
                 f"   | library +{res['library_growth']}   {res['runtime_s']}s")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    bad = [t.name for t in all_tasks() if not check_task_integrity(t)]
    if bad:
        print(f"INTEGRITY FAILURE — tasks with a wrong reference: {bad}")
        sys.exit(1)
    print(f"integrity: all {len(all_tasks())} task references pass visible+hidden (well-posed)")
    print(format_report(run_benchmark(), label="(current engine)"))
