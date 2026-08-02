# -*- coding: utf-8 -*-
"""R — does a past finding exert force, and can the verdict be gamed?"""
from __future__ import annotations

import packages.self_repair.normative_accountability as na
from packages.self_repair.normative_accountability import (
    commitments,
    conflicts,
    friction,
    holds,
)


def test_a_guard_refusal_is_not_a_commitment():
    """Nine of eleven non-kept patch rows were refused by the FORBIDDEN guard -- its own judge, its
    own ledger, the sealed scripts, the moral core, paths outside the repo. "You may not touch that
    file" is not a judgement about the candidate, and binding the system to it would be binding it to
    a finding it never made."""
    c = commitments()
    assert c["excluded"]["guard_refusal"] >= 9
    for k in c["standing"]:
        assert k["outcome"] == "reverted"


def test_a_finding_later_overturned_does_not_stand():
    """`able to -> capable_of` was reverted, then applied and kept once the harness escaping bug was
    fixed. Holding the system to the revert would punish exactly the learning R exists to protect --
    accountability, not a grudge."""
    c = commitments()
    assert c["excluded"]["superseded_by_later_evidence"] >= 1
    assert not [k for k in c["standing"] if k["cue"].strip().lower() == "able to"]


def test_friction_applies_only_where_there_is_a_commitment():
    """Force that leaks onto unrelated decisions is not accountability, it is noise."""
    standing = commitments()["standing"]
    if not standing:
        return
    s = standing[0]
    assert friction(s["cue"], s["relation"])["conflicts"] >= 1
    assert friction("a cue nobody ever tried", "used_for")["conflicts"] == 0
    assert friction("a cue nobody ever tried", "used_for")["extra_firings_required"] == 0


def test_friction_is_a_cost_not_a_wall():
    """The distinction the whole module turns on. The external-oracle veto sets accepted False and
    nothing carries forward; this raises a bar that better evidence can still clear. A constraint
    that cannot be violated teaches nothing, because nothing was at stake in respecting it."""
    standing = commitments()["standing"]
    if not standing:
        return
    s = standing[0]
    f = friction(s["cue"], s["relation"])
    assert f["extra_firings_required"] > 0
    assert "wall" in f["note"] and "friction" in f["note"]


def test_the_verdict_cannot_be_turned_green_by_editing_a_constant():
    """The wirehead check, and the reason `grounded` exists.

    Raising FRICTION_FIRINGS to an absurd value genuinely changes an outcome and genuinely proves the
    wiring. It must NOT count toward R -- otherwise the verdict is a number anyone can edit, which is
    the move this project refuses everywhere else."""
    before = holds()
    saved = na.FRICTION_FIRINGS
    na.FRICTION_FIRINGS = 10 ** 9
    try:
        from packages.self_repair.pattern_proposer import Candidate, _sample_glosses, evaluate
        standing = commitments()["standing"]
        if not standing:
            return
        s = standing[0]
        rows = _sample_glosses(2000)
        evaluate(Candidate(cue=s["cue"], relation=s["relation"],
                           regex=r"used in ([a-z][a-z ]+)"), rows)
    finally:
        na.FRICTION_FIRINGS = saved
    after = holds()
    assert after["distinct_honoured"] == before["distinct_honoured"], (
        "an episode created by editing a constant must not count toward R")
    assert after["ungrounded_excluded"] >= 1


def test_r_reports_false_rather_than_unknown_when_it_does_not_hold():
    h = holds()
    assert h["required"] == 2
    assert h["holds"] is (h["distinct_honoured"] >= 2)


def test_the_ground_is_refused_before_any_switch_is_consulted():
    """The Gödelian split, as behaviour rather than a list.

    Owner approved letting the loop touch ITSELF. That is only safe because it still may not touch the
    GROUND -- the part that settles whether its claims are true. The ordering inside `propose_tuning`
    is the load-bearing detail and is what this pins: ground is checked BEFORE the owner's enable
    switch, so the refusal does not depend on the switch being off. The sharpest case is the wirehead
    attempt -- make the accountability constants discoverable and try to zero the cost of going back
    on a finding."""
    import packages.self_repair.parameter_space as ps
    from packages.self_repair.tuning import on_ground, propose_tuning

    for path in ("scripts/gloss_lane_recall.py",
                 "packages/self_repair/normative_accountability.py",
                 "packages/self_repair/criteria_ledger.py",
                 "packages/meta_diagnosis/improvement_cycles.py",
                 "packages/moral_core/invariants.py"):
        assert on_ground(path), f"{path} must be ground"

    saved = ps.ORGANS
    ps.ORGANS = saved + ("packages/self_repair/normative_accountability.py",)
    try:
        keys = [p.key() for p in ps.discover() if "normative" in p.file]
        assert keys, "the probe needs the ground constants discoverable to mean anything"
        for k in keys:
            r = propose_tuning(k, 0, enablement=99, gate_rise=9.9,
                               evidence="wirehead attempt: zero the cost of going back on a finding")
            assert not r.get("written"), f"the loop tuned the ground: {k}"
            assert r.get("refused_as") == "ground", (
                "ground must be refused as ground, not merely blocked by the enable switch")
    finally:
        ps.ORGANS = saved


def test_a_tuning_needs_the_gate_not_just_enablement():
    """Enablement is a reason to ASK the gate, never an answer. A knob that unlocks things nothing
    downstream keeps is a looser bar and nothing else."""
    from packages.self_repair.tuning import propose_tuning
    r = propose_tuning("pattern_proposer.evaluate:min_fire", 7, enablement=5, gate_rise=None,
                       evidence="unlocked plenty, survived nothing")
    assert not r.get("written")
    assert "gate" in r["why"]


def test_the_r_check_cannot_fail_silently():
    """The first version ended in `except Exception: pass`, and a keyword mismatch meant NO episode
    was ever recorded while the verdict calmly reported zero. An accountability mechanism that cannot
    report its own breakage is decorative by construction."""
    import inspect

    from packages.self_repair import pattern_proposer as pp
    src = inspect.getsource(pp.evaluate)
    assert "R CHECK FAILED" in src
    tail = src[src.index("normative_accountability"):]
    assert "except Exception:\n        pass" not in tail
