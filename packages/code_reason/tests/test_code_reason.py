# -*- coding: utf-8 -*-
"""Code mastery floor: read code structurally (comprehension), and the authorship VERIFIER is a
perfect oracle (passes correct code, rejects wrong code, can't be flattered)."""
from packages.code_reason.authorship_harness import (Task, evaluate, reference_generator,
                                                     seed_tasks, stub_generator)
from packages.code_reason.code_situation import answer, build

FUNC = '''
def scan(items, limit=10):
    """demo"""
    total = 0
    for it in items:
        if it < 0:
            raise ValueError("neg")
        total += it
        if total > limit:
            return scan(items[1:], limit)
    return total
'''


def test_comprehension_reads_structure_exactly():
    s = build(FUNC)
    assert s.name == "scan"
    assert answer("How many parameters does it take?", s) == "2"
    assert answer("Does it return a value?", s) == "yes"
    assert answer("Does it contain a loop?", s) == "yes"
    assert answer("Does it have a conditional branch?", s) == "yes"
    assert answer("Does it raise an exception?", s) == "yes"
    assert answer("Is it recursive?", s) == "yes"


def test_bare_reraise_counts_as_raising():
    s = build("def f():\n    try:\n        g()\n    except Exception:\n        raise\n")
    assert answer("Does it raise an exception?", s) == "yes"    # the gap the battery caught


def test_comprehension_abstains_when_ungrounded():
    s = build("def f(x):\n    return x\n")
    assert answer("What is the meaning of life?", s) is None    # never fabricates


def test_verifier_passes_correct_and_rejects_wrong_code():
    tasks = seed_tasks()
    assert evaluate(tasks, reference_generator)["authorship_rate"] == 1.0     # oracle accepts truth
    wrong = evaluate(tasks, lambda t: "return 999")                          # nonsense body
    assert wrong["authorship_rate"] == 0.0                                    # oracle rejects it
    # a candidate cannot cheat by returning a constant that happens to match ONE assert only
    assert wrong["authored_pass"] == 0


def test_stub_generator_is_honest_zero():
    tasks = seed_tasks()
    r = evaluate(tasks, stub_generator)
    assert r["authorship_rate"] == 0.0 and r["abstained"] == len(tasks)       # abstains, never fakes
