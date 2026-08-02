# -*- coding: utf-8 -*-
"""Sealed gates for V2.1 — wiring the block-universe temporal reasoner into the live answer path as a
LOW-grounding, ALWAYS-hypothesis-tagged workspace BIDDER (not a keyword-toggled second engine, not an
override lane).

The bidder (packages/cgsr/cgsr/response_workspace.py:_temporal_candidate) is a 5th DEFAULT builder in
the same workspace dual_brain.py already calls live. It reuses block_universe.project_forward /
infer_backward over the learned precedence field, tags every output with epistemic_tier (PROJECTED /
RETRODICTED), and is capped at grounding 0.45 — strictly below every verified lane. So:
  (a) a temporal question whose tokens the field COVERS -> a hypothesis-tagged candidate flows through
      the live compose_response, carrying the "not a certainty" / "not a record" hedge;
  (b) a temporal question whose tokens the field does NOT cover -> bids None (abstain, no invention);
  (c) a verified higher-grounding candidate present -> it wins regardless of order (low cap proven);
  (d) a simple/factual/conversational question -> None (contextual, not always-on);
  (e) PROJECTED / RETRODICTED outputs are 100% hypothesis-tagged; a stripped tag fails.

The field is injected as a tiny LEARNED-shaped toy (plant<grow<harvest<eat) via the module's
_shared_block_universe seam, so the gates are deterministic without depending on the trained artifact —
exactly the shape block_universe's own tests use.
"""
from __future__ import annotations

import itertools

import pytest

import packages.cgsr.cgsr.response_workspace as rw
from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import Candidate, compose_response
from packages.temporal_reasoning.block_universe import BlockUniverse
from packages.temporal_reasoning.epistemic_tier import Tier, is_hypothesis
from packages.temporal_reasoning.precedence_field import PrecedenceField
from packages.temporal_reasoning.unified_timeline import Timeline

FWD_Q = "What typically comes after we grow the crops?"
BWD_Q = "What typically led to the harvest?"


def _toy_field() -> PrecedenceField:
    # a tiny learned-shaped field: plant < grow < harvest < eat (phases ascending), real evidence each
    return PrecedenceField(phase={"plant": -0.9, "grow": -0.3, "harvest": 0.3, "eat": 0.9},
                           seen={"plant": 5, "grow": 5, "harvest": 5, "eat": 5})


def _covered_bu(raw_question: str) -> BlockUniverse:
    """The seam's covered stand-in: the toy field over a question-scoped timeline (so forward
    projection anchors on the question's own event, just like the production seam)."""
    tl = Timeline()
    tl.record("utterance", raw_question or "", who="user")
    return BlockUniverse(tl, _toy_field())


@pytest.fixture
def covered(monkeypatch):
    monkeypatch.setattr(rw, "_shared_block_universe", _covered_bu)


# ── GATE (a): a covered temporal question -> a hypothesis-tagged candidate flows through compose_response

def test_gate_a_forward_projection_flows_through_live_compose_response(covered):
    u = perceive(FWD_Q, [])
    out = compose_response(u, FWD_Q)                        # the DEFAULT builder fires (no `extra`)
    assert out is not None, "the covered field should let block-universe bid"
    assert out["answer_kind"] == "temporal_projection"
    assert out["engine_name"] == "ATANOR Block-Universe"
    # the surface carries the PROJECTED hedge in block_universe.render_human's own voice
    assert "a projection, not a certainty" in out["answer"]
    # it walked the LEARNED order (grow -> harvest -> eat), not a hardcoded answer
    assert "harvest" in out["answer"]
    # it competed at its low cap and is present in 'considered'
    assert ("ATANOR Block-Universe", 0.45) in out["considered"]
    assert is_hypothesis(Tier.PROJECTED)


def test_gate_a_backward_retrodiction_flows_through_and_is_hedged(covered):
    u = perceive(BWD_Q, [])
    out = compose_response(u, BWD_Q)
    assert out is not None and out["answer_kind"] == "temporal_retrodiction"
    assert "an inference from learned order, not a record" in out["answer"]
    assert "harvest" in out["answer"]                      # traced back FROM the harvest anchor
    assert is_hypothesis(Tier.RETRODICTED)


# ── GATE (b): a temporal question the field does NOT cover -> bids None (abstain, no invented projection)

def test_gate_b_uncovered_field_abstains_not_invents(covered):
    # a well-formed FORWARD temporal question, but its anchor tokens are outside the toy field
    q = "What comes after the quarterly earnings call?"
    u = perceive(q, [])
    assert rw._temporal_candidate(u, q) is None            # fail-closed: no coverage -> abstain
    out = compose_response(u, q)
    assert out is None or out["answer_kind"] != "temporal_projection"


def test_gate_b_uncovered_backward_also_abstains(covered):
    q = "What led to the merger announcement?"             # 'merger'/'announcement' not in the toy field
    u = perceive(q, [])
    assert rw._temporal_candidate(u, q) is None


def test_gate_b_no_substrate_at_all_abstains(monkeypatch):
    # if the block-universe substrate is unavailable entirely, the bidder abstains (never guesses)
    monkeypatch.setattr(rw, "_shared_block_universe", lambda q: None)
    u = perceive(FWD_Q, [])
    assert rw._temporal_candidate(u, FWD_Q) is None


# ── GATE (c): order-invariance + non-override — a verified higher-grounding candidate always wins ─────

def test_gate_c_verified_lane_beats_temporal_regardless_of_order(covered):
    u = perceive(FWD_Q, [])                                 # temporal genuinely bids here (covered)
    verified = [
        lambda: Candidate("a verified multi-hop answer", "deliberation", 0.9, "ATANOR Deliberator"),
        lambda: Candidate("a weak aside", "chitchat", 0.10, "Weak"),
    ]
    for perm in itertools.permutations(verified):
        out = compose_response(u, FWD_Q, extra=list(perm))
        assert out["engine_name"] == "ATANOR Deliberator", "0.9 verified must beat the 0.45 projection"
        assert out["answer_kind"] == "deliberation"
    # and the temporal bidder really competed (present at its capped 0.45), it just lost
    out = compose_response(u, FWD_Q, extra=[verified[0]])
    assert ("ATANOR Block-Universe", 0.45) in out["considered"]


def test_gate_c_even_the_lowest_verified_lane_outranks_the_projection(covered):
    # discourse (0.6) is the lowest verified lane; still strictly above the temporal cap (0.45)
    u = perceive(FWD_Q, [])
    lowest = lambda: Candidate("a grounded discourse turn", "discourse_participation", 0.6, "ATANOR Discourse")
    for extra in ([lowest], [lowest, lambda: Candidate("x", "y", 0.1, "Z")]):
        out = compose_response(u, FWD_Q, extra=extra)
        assert out["engine_name"] == "ATANOR Discourse"


# ── GATE (d): contextual — a simple/factual/conversational question -> None (not always-on) ───────────

def test_gate_d_non_temporal_questions_get_no_temporal_bid():
    for q in ("how are you?", "what's a cat?", "what is a cat", "hello there",
              "what is the boiling point of water?", "who wrote this book?",
              "define entropy", "translate this into French"):
        u = perceive(q, [])
        assert rw._temporal_candidate(u, q) is None, q
        out = compose_response(u, q)
        assert out is None or out["answer_kind"] not in ("temporal_projection", "temporal_retrodiction"), q


def test_gate_d_a_temporal_word_without_an_inference_frame_does_not_fire(covered):
    # 'next' / 'before' appear, but these are NOT inference requests -> no bid (shape, not keyword)
    for q in ("Add your next contribution.", "I have seen this before.",
              "Please follow the instructions below."):
        u = perceive(q, [])
        assert rw._temporal_candidate(u, q) is None, q


# ── GATE (e): tier integrity — PROJECTED/RETRODICTED outputs are 100% hypothesis-tagged ──────────────

def test_gate_e_every_bidder_output_carries_its_hypothesis_marker(covered):
    cf = rw._temporal_candidate(perceive(FWD_Q, []), FWD_Q)
    assert cf is not None
    assert cf.answer_kind == "temporal_projection" and cf.grounding == 0.45
    assert "a projection, not a certainty" in cf.answer   # PROJECTED -> hedged, never bare fact

    cb = rw._temporal_candidate(perceive(BWD_Q, []), BWD_Q)
    assert cb is not None
    assert cb.answer_kind == "temporal_retrodiction"
    assert "an inference from learned order, not a record" in cb.answer


def test_gate_e_a_stripped_marker_can_never_be_surfaced(covered, monkeypatch):
    """If the render step ever produced an UNMARKED projection, the epistemic-tier enforcement must
    turn it into an abstention, not a bare-fact answer. Simulate a stripped hedge and prove the bidder
    refuses to surface it (the tag cannot be silently dropped)."""
    from packages.temporal_reasoning import epistemic_tier as et

    def _stripped_render(self, projections=None, backward=None):
        return "The harvest will happen next."          # a projection with its hedge stripped away

    monkeypatch.setattr(BlockUniverse, "render_human", _stripped_render)
    assert rw._temporal_candidate(perceive(FWD_Q, []), FWD_Q) is None   # refused, not surfaced

    # and the enforcement itself raises on the stripped surface (the mechanism behind the abstention)
    with pytest.raises(et.EpistemicViolation):
        et.enforce(et.tag("The harvest will happen next.", Tier.PROJECTED, 0.7))
