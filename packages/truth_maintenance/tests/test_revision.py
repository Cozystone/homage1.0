# -*- coding: utf-8 -*-
"""AGM belief revision (1985) with entrenchment = tier order.

Required test (d): promoting a fact that conflicts with a single-source belief
drops the single-source one; promoting one that conflicts with an operator fact
is REJECTED (operator never dropped).

Plus AGM postulate checks (consistency + minimal change / inclusion + success +
vacuity) as tests.
"""
from __future__ import annotations

from packages.truth_maintenance.revision import (
    BeliefBase, Fact, OPERATOR, CONSENSUS, SINGLE_SOURCE, NEURAL,
)


def test_d_conflict_with_single_source_drops_it():
    base = BeliefBase([Fact("france", "capital_of", "lyon", SINGLE_SOURCE)])
    # a better-entrenched (consensus) fact conflicts on the functional predicate
    result = base.promote(Fact("france", "capital_of", "paris", CONSENSUS))
    assert result.accepted is True
    assert [f.object for f in result.dropped] == ["lyon"]          # single-source dropped
    objs = {(f.subject, f.object) for f in base.facts()}
    assert ("france", "paris") in objs
    assert ("france", "lyon") not in objs


def test_d_conflict_with_operator_is_rejected():
    base = BeliefBase([Fact("france", "capital_of", "paris", OPERATOR)])
    # a lower-tier fact conflicts with the operator core -> REJECTED, core kept
    result = base.promote(Fact("france", "capital_of", "berlin", CONSENSUS))
    assert result.accepted is False
    assert "operator" in result.rejected_reason
    # operator belief never dropped; incoming never added
    objs = {f.object for f in base.facts()}
    assert objs == {"paris"}


def test_incoming_less_entrenched_than_existing_is_rejected():
    base = BeliefBase([Fact("x", "capital_of", "a", CONSENSUS)])
    result = base.promote(Fact("x", "capital_of", "b", NEURAL))   # neural < consensus
    assert result.accepted is False
    assert base.facts()[0].object == "a"


def test_equal_entrenchment_ties_reject_incoming_default_deny():
    base = BeliefBase([Fact("x", "capital_of", "a", CONSENSUS)])
    result = base.promote(Fact("x", "capital_of", "b", CONSENSUS))
    assert result.accepted is False
    assert "tie" in result.rejected_reason


# ---- AGM postulate checks --------------------------------------------------
def test_revision_consistency_postulate():
    # K * p is consistent whenever p is consistent.
    base = BeliefBase([Fact("france", "capital_of", "lyon", SINGLE_SOURCE)])
    base.promote(Fact("france", "capital_of", "paris", OPERATOR))
    assert base.is_consistent()


def test_revision_inclusion_postulate():
    # K * p  subset of  K + p  (revision adds no more than expansion would).
    start = [Fact("france", "capital_of", "lyon", SINGLE_SOURCE)]
    base = BeliefBase(list(start))
    incoming = Fact("france", "capital_of", "paris", OPERATOR)
    base.promote(incoming)
    expansion = {f.key() for f in start} | {incoming.key()}
    assert {f.key() for f in base.facts()} <= expansion


def test_revision_success_when_not_screened():
    # p in K * p  when p is not screened off by a higher/equal-entrenched belief.
    base = BeliefBase([Fact("france", "capital_of", "lyon", SINGLE_SOURCE)])
    incoming = Fact("france", "capital_of", "paris", OPERATOR)
    base.promote(incoming)
    assert base.contains(incoming)


def test_contraction_success_and_inclusion_and_vacuity():
    f = Fact("france", "capital_of", "paris", OPERATOR)
    base = BeliefBase([f, Fact("italy", "capital_of", "rome", OPERATOR)])
    before = {x.key() for x in base.facts()}
    res = base.contract(f)
    assert res.accepted
    # success: p not in K - p
    assert not base.contains(f)
    # inclusion: K - p subset K
    assert {x.key() for x in base.facts()} <= before
    # vacuity: contracting an absent fact leaves K unchanged
    keys_now = {x.key() for x in base.facts()}
    res2 = base.contract(f)   # already gone
    assert res2.accepted is False and res2.rejected_reason == "vacuous_not_present"
    assert {x.key() for x in base.facts()} == keys_now


def test_no_conflict_is_plain_expansion():
    base = BeliefBase([Fact("france", "capital_of", "paris", OPERATOR)])
    res = base.promote(Fact("italy", "capital_of", "rome", CONSENSUS))
    assert res.accepted and res.dropped == ()
    assert len(base.facts()) == 2
