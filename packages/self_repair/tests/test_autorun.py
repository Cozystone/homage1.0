# -*- coding: utf-8 -*-
"""The loop on a schedule — and the two properties that stop a scheduled loop becoming noise.

A loop that fires repeatedly and re-reports the same finding trains its reader to stop reading, and
an unread ledger is worse than no ledger: unexamined claims accumulate and look like progress. So
these pin deduplication and plateau detection, which are the whole difference between a scheduled
loop and a spammer.
"""
from __future__ import annotations

from packages.self_repair.autorun import PLATEAU_AFTER, _fingerprint, status


def test_the_same_claim_fingerprints_the_same_across_runs():
    """Counts drift between runs on the same corpus. Hashing the whole record would make every run
    look novel, which is exactly how a ledger becomes unreadable."""
    a = {"cue": "consisting of", "relation": "HasA", "pairs": 266, "checkable": 14}
    b = {"cue": "consisting of", "relation": "HasA", "pairs": 271, "checkable": 15}
    c = {"cue": "consisting of", "relation": "PartOf", "pairs": 266, "checkable": 14}
    assert _fingerprint(a) == _fingerprint(b)      # same claim, drifted counts
    assert _fingerprint(a) != _fingerprint(c)      # different relation is a different claim


def test_status_reports_a_plateau_as_a_finding():
    """The property that matters most. Today the loop hit its own ceiling inside a day -- 24 proposed,
    0 queued -- and the escape was a NEW KIND of proposal, which took a person to notice. Consecutive
    empty runs are the measurable version of that noticing, and a plateau says CHANGE WHAT YOU ARE
    DOING rather than do more of it."""
    s = status()
    assert "plateaued" in s and "consecutive_runs_with_nothing_new" in s
    if s.get("runs"):
        assert s["plateaued"] == (s["consecutive_runs_with_nothing_new"] >= PLATEAU_AFTER)
        assert "reading" in s


def test_autonomy_covers_measuring_and_not_changing():
    """Autonomy over MEASURING is a different act from autonomy over CHANGING. The patcher -- the only
    thing that writes code -- must not be reachable from the scheduled path.

    The first version of this test searched the SOURCE TEXT for the word, and failed on the module's
    own docstring explaining that the patcher is unreachable. A test that a correct implementation
    fails because it documents itself is testing prose, not behaviour. What matters is the IMPORT
    GRAPH, so that is what is checked."""
    import ast
    import inspect

    import packages.self_repair.autorun as ar

    tree = ast.parse(inspect.getsource(ar))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    # THE BOUNDARY MOVED, DELIBERATELY, AND THIS TEST NOW ENCODES WHERE IT MOVED TO.
    #
    # It used to assert that the patcher was unreachable from the scheduled path at all. That was the
    # right invariant while `tick()` was the whole of autonomy -- and it is why every cycle on record
    # showed exactly one human touch: a person read the queue, wrote the patch, ran the gate. To make
    # `human_touches` honestly zero, `unattended_cycle` was given the patcher.
    #
    # So the invariant is now narrower and still real: the ONLY route by which autorun changes code is
    # `provisional.try_patch`, which refuses its own judge, its own ledger, the sealed scripts, the
    # moral core and anything outside the repository -- verified behaviourally, six probes, all
    # refused. What must never appear is a direct write to a source file, which would go around the
    # guard entirely.
    #
    # `tick()` itself still applies nothing; that is what makes the two levels of autonomy separable.
    src = inspect.getsource(ar)
    changing = [m for m in imported if "provisional" in m]
    assert changing == ["packages.self_repair.provisional"], (
        f"the only permitted route to changing code is the guarded patcher, found: {changing}")
    # `tick` still applies nothing, and says so in what it RETURNS rather than in prose -- which is
    # the claim a caller can actually act on. That is what keeps the two levels of autonomy separable:
    # measuring stayed where it was when changing moved.
    assert '"measures and queues; applies nothing"' in inspect.getsource(ar.tick)

    # no route around the guard: nothing here may write a .py path itself
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name in {"write_text", "unlink", "rename", "replace"}:
                raise AssertionError(f"autorun writes files directly via {name}(); "
                                     f"every code change must go through try_patch")
