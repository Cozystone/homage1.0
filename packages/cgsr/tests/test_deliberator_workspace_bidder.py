# -*- coding: utf-8 -*-
"""Sealed gates for wiring the DELIBERATOR (System-2 multi-hop reasoner) into the live answer path as
a GROUNDED WORKSPACE BIDDER — not a keyword-toggled second engine, not a post-hoc override lane.

The pathology this fixes (measured wiring audit): packages/deliberator/controller.py was proven
(20/20 multi-hop, fail 0) but UNWIRED — in apps/api/app/routers/dual_brain.py the token "deliberat"
appeared only in a comment. So a hard multi-hop question never reached ATANOR's own System-2 engine.

The fix makes the deliberator a 4th DEFAULT builder in packages/cgsr/cgsr/response_workspace.py, the
same workspace dual_brain.py:5449 already calls live. Selection stays max-by-grounding, so:
  (a) a hard multi-hop question the current lanes abstain on now gets a DELIBERATOR-grounded answer;
  (b) a simple/conversational question -> the deliberator bids None (contextual, not always-on);
  (c) shuffling candidate order never changes the winner (grounding decides, not position);
  (d) when a required hop cannot be grounded, NO answer is emitted (honest abstain, 작화 0).

The grounding used here is the deliberator's OWN designed input contract: passage/situation-scoped
facts (from _reach_in_time in packages/deliberator/tests/test_deliberator.py — a genuine solved case),
attached to the shared Understanding. The deliberation itself is a real 3-hop verified chain
(mechanism -> relational -> arithmetic) that single-shot provably cannot answer.
"""
from __future__ import annotations

import itertools

from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import (
    Candidate,
    compose_response,
    _self_causal_candidate,
    _hypothesis_candidate,
    _discourse_candidate,
    _deliberation_candidate,
)

REACH_Q = "Will the ambulance reach the hospital in time?"


def _reach_grounding(detour_len: int = 22):
    """The genuine solved case from packages/deliberator/tests/test_deliberator.py (_reach_in_time):
    a 3-hop chain whose facts are stated IN the situation, never smuggled world facts."""
    return {
        "cross_question": "Can the ambulance cross the bridge?",
        "block_text": "The bridge was blocked by the flood.",
        "detour_query": "what is the length of the bypass?",
        "detour_facts": [("bypass", "length", detour_len)],
        "budget_expr": "{detour_len} <= 30",
        "compose": lambda b: ("arrives in time" if b["in_time"] else "too late"),
    }


def _ungrounded_bridge_grounding():
    """The deliberator's OWN proven abstention case: the store holds NO length edge for the bypass, so
    hop 2 (relational) cannot ground -> the whole chain abstains mid-way and fabricates nothing."""
    return {
        "cross_question": "Can the ambulance cross the bridge?",
        "block_text": "The bridge was blocked by the flood.",
        "detour_query": "what is the length of the bypass?",
        "detour_facts": [("bypass", "surface", "gravel")],   # no 'length' edge -> ungrounded hop
        "budget_expr": "{detour_len} <= 30",
        "compose": lambda b: "unreachable",
    }


def _perceive_with_grounding(q: str, grounding: dict):
    u = perceive(q, [])
    u.deliberation_grounding = grounding          # what an upstream organ / situation client attaches
    return u


# ── GATE (a): a hard multi-hop question the current path abstains on now gets a DELIBERATOR answer ──

def test_gate_a_hard_multihop_the_current_path_abstains_on_is_now_answered_by_deliberator():
    # 1) the CURRENT lanes (self-causal, hypothesis, discourse) each have nothing to say here
    u_none = perceive(REACH_Q, [])
    assert _self_causal_candidate(REACH_Q) is None
    assert _hypothesis_candidate(REACH_Q) is None
    assert _discourse_candidate(u_none) is None
    # ...so the workspace, WITHOUT situation grounding, abstains (returns None) on this question
    assert compose_response(u_none, REACH_Q) is None

    # 2) attach the deliberator's own situation grounding -> the deliberator now bids and WINS
    u = _perceive_with_grounding(REACH_Q, _reach_grounding())
    out = compose_response(u, REACH_Q)
    assert out is not None, "the workspace should now produce a grounded answer"
    assert out["answer_kind"] == "deliberation"
    assert out["engine_name"] == "ATANOR Deliberator"
    assert "arrives in time" in out["answer"]
    # the deliberator competed and won on grounding (it is present in 'considered')
    assert ("ATANOR Deliberator", 0.9) in out["considered"]


def test_gate_a_win_is_a_real_verified_multihop_chain_not_shallow_retrieval():
    """Skeptic's check: prove the gate-(a) win is a genuine 3-hop VERIFIED chain (mechanism ->
    relational -> arithmetic), each hop certificated, composed only from verified steps — and that the
    non-decomposing single-shot baseline provably CANNOT answer the composite goal."""
    from packages.deliberator.controller import Deliberation, deliberate, single_shot
    from packages.deliberator.steps import decompose

    plan = decompose(REACH_Q, _reach_grounding())
    assert plan is not None
    assert [sg.organ for sg in plan] == ["mechanism", "relational", "arithmetic"]

    res = deliberate(Deliberation(REACH_Q, plan, _reach_grounding()["compose"]))
    assert res.abstained is False
    assert res.hops == 3                                        # three real hops, not one lookup
    g = res.certificate["guarantees"]
    assert g["every_executed_step_verified"] is True
    assert g["composed_only_from_verified_steps"] is True
    assert g["fabricated_facts"] is False
    # the chain genuinely flows a bound value between hops (relational -> arithmetic), not a bag
    steps = {s.organ: s for s in res.steps}
    assert steps["relational"].bind_value == "22"
    assert steps["arithmetic"].answer is True                  # 22 <= 30 evaluated, not assumed

    # single-shot (no decomposition) cannot answer the composite goal -> the chain is load-bearing
    base = single_shot(Deliberation(REACH_Q, plan, _reach_grounding()["compose"]))
    assert base.abstained is True and base.answer is None


# ── GATE (b): a simple/conversational question -> the deliberator bids None (contextual, not always-on)

def test_gate_b_simple_and_conversational_questions_get_no_deliberator_bid():
    for q in ("how are you?", "what's a cat?", "what is a cat", "hello there",
              "what is the boiling point of water?"):
        u = perceive(q, [])
        # no situation grounding present -> the deliberator has nothing to reason over
        assert _deliberation_candidate(u, q) is None, q
        # and even the full workspace never returns a 'deliberation' answer for these
        out = compose_response(u, q)
        assert out is None or out["answer_kind"] != "deliberation", q


def test_gate_b_contextual_even_when_grounding_present_but_shape_is_not_a_reasoning_question():
    """Prove the bid is CONTEXTUAL, not merely 'grounding attached => fire': a conversational question
    whose shape the structural decomposer does not recognize gets None even if a grounding dict rides
    along (the decomposer returns None -> no plan -> no bid). It is understanding, not a keyword."""
    u = _perceive_with_grounding("how are you today?", _reach_grounding())
    assert _deliberation_candidate(u, "how are you today?") is None


# ── GATE (c): order-invariance — shuffling candidate order does not change the winner ───────────────

def test_gate_c_winner_is_by_grounding_not_by_candidate_order():
    u = _perceive_with_grounding(REACH_Q, _reach_grounding())     # deliberation bids 0.9 (a default builder)
    decoys = [
        lambda: Candidate("a weak aside", "chitchat", 0.10, "Weak"),
        lambda: Candidate("a middling note", "aside", 0.50, "Mid"),
        lambda: Candidate("another low bid", "aside", 0.20, "Low"),
    ]
    # every ordering of the competing candidates yields the SAME winner: the deliberator, on grounding
    for perm in itertools.permutations(decoys):
        out = compose_response(u, REACH_Q, extra=list(perm))
        assert out["engine_name"] == "ATANOR Deliberator"
        assert out["answer_kind"] == "deliberation"


def test_gate_c_a_higher_grounded_offer_beats_the_deliberator_regardless_of_position():
    """The deliberator runs FIRST among the default builders. If order decided, it would always win.
    It does not: a candidate with higher grounding beats it in every permutation — position is inert,
    grounding decides."""
    u = _perceive_with_grounding(REACH_Q, _reach_grounding())
    stronger = [
        lambda: Candidate("a better-supported offer", "stronger", 0.95, "Stronger"),
        lambda: Candidate("a weak aside", "chitchat", 0.10, "Weak"),
    ]
    for perm in itertools.permutations(stronger):
        out = compose_response(u, REACH_Q, extra=list(perm))
        assert out["engine_name"] == "Stronger"           # 0.95 > 0.9, beats the first-run deliberator


# ── GATE (d): no fabrication — an ungroundable required hop yields abstain, never a guess ───────────

def test_gate_d_ungrounded_hop_abstains_and_emits_no_answer():
    u = _perceive_with_grounding(REACH_Q, _ungrounded_bridge_grounding())
    # the deliberator refuses to bid (it cannot ground the bypass-length hop) -> None, not a guess
    assert _deliberation_candidate(u, REACH_Q) is None
    # and since the other lanes also have nothing to say, the workspace abstains honestly (None)
    assert _self_causal_candidate(REACH_Q) is None
    assert _hypothesis_candidate(REACH_Q) is None
    assert _discourse_candidate(u) is None
    assert compose_response(u, REACH_Q) is None


def test_gate_d_underlying_deliberation_really_abstains_midchain_without_fabricating():
    """The bidder's None in gate (d) is the honest projection of a real mid-chain abstention, not a
    silent drop: hop 0 grounds, hop 1 (bypass length) cannot, hop 2 never runs, answer stays None."""
    from packages.deliberator.controller import Deliberation, deliberate
    from packages.deliberator.steps import decompose

    plan = decompose(REACH_Q, _ungrounded_bridge_grounding())
    res = deliberate(Deliberation(REACH_Q, plan, lambda b: "unreachable"))
    assert res.abstained is True
    assert res.answer is None                                   # NOT fabricated
    assert res.certificate["ungrounded_step"]["organ"] == "relational"
    assert res.certificate["guarantees"]["abstained_rather_than_bridge"] is True
    assert res.certificate["guarantees"]["fabricated_facts"] is False
