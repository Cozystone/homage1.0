# -*- coding: utf-8 -*-
"""Code authorship harness — the verifier-gated loop that makes code the IDEAL No-LLM generative
domain. A task is (spec, failing test); a candidate is a function body; the VERIFIER runs the test.
The test is a perfect oracle — it does not lie, cannot be flattered, and gives a binary truth. That
is the AlphaGeometry shape (propose → verify) with a verifier prose could never have.

Honesty is structural here:
  - The generator is PLUGGABLE and starts as a stub that abstains (ATANOR cannot author code yet).
    The measured authorship rate therefore starts near 0 — the number the curriculum ratchets up,
    reported truthfully, never simulated.
  - A candidate that does not pass the test is REJECTED. There is no partial credit for plausible-
    looking code. So a hallucinated body cannot score — the verifier is the hallucination floor.
  - Verification runs the test in a subprocess with a timeout (untrusted candidate code is never
    exec'd in-process), and only the function body is substituted — the surrounding harness/spec is
    fixed, so a candidate cannot rewrite the test to pass itself.

This module is the MEASUREMENT + VERIFIER. It does not pretend to author. When a real code generator
exists (or the advisor drafts one), it plugs in as `generator` and the same harness scores it.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]


@dataclass
class Task:
    name: str
    signature: str                 # e.g. "def add(a, b):"
    docstring: str                 # the spec
    test: str                      # asserts referencing the function by name; must raise on failure
    reference: str = ""            # a known-good body (for harness self-test only, never shown to gen)
    hidden: str = ""               # held-out asserts for benchmark scoring (never shown to gen either)


@dataclass
class Attempt:
    task: str
    passed: bool
    abstained: bool
    error: str = ""


# ---- generators (pluggable). The default is the honest stub. ----

def stub_generator(task: Task) -> str | None:
    """ATANOR cannot author code yet -> abstain. Returns a body, or None to abstain."""
    return None


def reference_generator(task: Task) -> str | None:
    """Harness self-test only: returns the known-good body so we can prove the VERIFIER works."""
    return task.reference or None


# ---- the verifier (perfect oracle) ----

def _run_candidate(task: Task, body: str, timeout_s: int = 10) -> Attempt:
    prog = f"{task.signature}\n{textwrap.indent(textwrap.dedent(body).strip(), '    ')}\n\n{task.test}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(prog)
        path = f.name
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True,
                              timeout=timeout_s, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            return Attempt(task.name, passed=True, abstained=False)
        return Attempt(task.name, passed=False, abstained=False,
                       error=(proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "fail")
    except subprocess.TimeoutExpired:
        return Attempt(task.name, passed=False, abstained=False, error="timeout")
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass


def evaluate(tasks: list[Task], generator: Callable[[Task], str | None]) -> dict:
    attempts: list[Attempt] = []
    for t in tasks:
        body = generator(t)
        if body is None:
            attempts.append(Attempt(t.name, passed=False, abstained=True))
            continue
        attempts.append(_run_candidate(t, body))
    passed = sum(a.passed for a in attempts)
    abstained = sum(a.abstained for a in attempts)
    return {
        "n_tasks": len(tasks),
        "authored_pass": passed,
        "authorship_rate": round(passed / max(1, len(tasks)), 4),
        "abstained": abstained,
        "attempts": [a.__dict__ for a in attempts],
    }


# ---- a tiny seed suite of trivial tasks (the first rung) ----

def seed_tasks() -> list[Task]:
    return [
        Task("add", "def add(a, b):", "Return the sum of a and b.",
             "assert add(2, 3) == 5\nassert add(-1, 1) == 0", reference="return a + b"),
        Task("is_even", "def is_even(n):", "Return True if n is even, else False.",
             "assert is_even(4) is True\nassert is_even(7) is False", reference="return n % 2 == 0"),
        Task("last", "def last(xs):", "Return the last element of a non-empty list.",
             "assert last([1,2,3]) == 3\nassert last(['a']) == 'a'", reference="return xs[-1]"),
        Task("count_vowels", "def count_vowels(s):", "Return the number of vowels (aeiou) in s.",
             "assert count_vowels('hello') == 2\nassert count_vowels('xyz') == 0",
             reference="return sum(1 for c in s if c in 'aeiou')"),
    ]


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    tasks = seed_tasks()
    stub = evaluate(tasks, stub_generator)
    ref = evaluate(tasks, reference_generator)
    print(f"ATANOR authorship rate (stub, honest): {stub['authorship_rate']} "
          f"({stub['authored_pass']}/{stub['n_tasks']}, abstained {stub['abstained']})")
    print(f"VERIFIER self-test (reference bodies): {ref['authorship_rate']} "
          f"({ref['authored_pass']}/{ref['n_tasks']}) — proves the oracle passes correct code")
