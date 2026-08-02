# -*- coding: utf-8 -*-
"""Sealed gates for M-B1 — the fluency realizer wired as CO L3's OPTIONAL, faithfulness-gated,
tier-preserving surface pass over the WINNING workspace answer
(packages/cgsr/cgsr/response_workspace.py:_fluency_surface, called at the tail of compose_response).

The pass re-surfaces a free-form, MULTI-FACT winner in a more natural register and adopts that surface
ONLY when every fluency gate passes; ANY failure keeps the LITERAL answer (honesty-first, 작화 0):

  (a) a multi-fact answer surfaced through fluency reads MORE NATURALLY (fluency's own proxy goes UP)
      AND the faithfulness verifier returns 1.0 (identical fact set: no added / removed / changed fact);
  (b) a hypothesis-tagged (projection / retrodiction) answer KEEPS its hedge marker after realization —
      the epistemic tier survives, PROVEN by re-running epistemic_tier.enforce on the realized surface;
  (c) faithfulness fallback: if the realizer would ALTER meaning (fabricate a fact) or DROP a fact, the
      pass rejects it and surfaces the LITERAL answer (no fabrication reaches output);
  (d) no-op safety: an abstention / boilerplate answer is NOT reshaped, the winner + grounding are
      unchanged, and winner selection stays order-invariant;
  (e) no regression: the default (no-bones) live bidders are untouched — the pass no-ops on them.

The fluency package is reused VERBATIM (realizer + fluency_v1 faithfulness/slot-copy/proxy + register +
epistemic_tier); no new fact source, no new weights.
"""
from __future__ import annotations

import itertools

import pytest

from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import Candidate, compose_response
from packages.fluency.delex import Grounding
from packages.fluency.fluency_v1 import faithfulness, fluency_proxy, slot_copy_accuracy, tasks
from packages.realizer_struct import frame_realizer as fr

# a genuine run-on multi-fact subject (frame_realizer emits a ", and ... , and" ceiling here)
_ENGINE_BONES = [b for b in ([t for t in tasks() if t["id"] == "m_engine"][0]["bones"])]
_RIVER_BONES = [t for t in tasks() if t["id"] == "m_river"][0]["bones"]
_NEUTRAL_Q = "Tell me about the engine."


def _literal(bones) -> str:
    """The honest BEFORE surface — exactly what the main frame_realizer answer path would produce."""
    return fr.realize(bones)


def _bones_candidate(bones, *, kind="world_fact", grounding=0.7, answer=None, reshapeable=None):
    literal = answer if answer is not None else _literal(bones)
    return lambda: Candidate(literal, kind, grounding, "ATANOR Main", bones=bones,
                             reshapeable=reshapeable)


# ── GATE (a): a multi-fact winner is reshaped MORE NATURALLY, faithfulness 1.0 (identical fact set) ──

def test_gate_a_multifact_winner_reads_more_naturally_and_stays_faithful():
    literal = _literal(_ENGINE_BONES)
    u = perceive(_NEUTRAL_Q, [])
    out = compose_response(u, _NEUTRAL_Q, extra=[_bones_candidate(_ENGINE_BONES)])
    assert out is not None and out["engine_name"] == "ATANOR Main"    # our bones candidate won
    fl = out["fluency"]
    assert fl["adopted"] is True, fl
    # the surface actually changed and is different from the literal run-on
    assert out["answer"] != literal
    # fluency's OWN proxy strictly increased (the naturalness lever fired)
    assert fl["proxy_realized"] > fl["proxy_literal"], fl
    assert fluency_proxy(out["answer"])[0] > fluency_proxy(literal)[0]
    # faithfulness verifier returns 1.0 on the adopted surface — IDENTICAL fact set, nothing invented
    g = Grounding.from_bones(_ENGINE_BONES)
    faith, fabricated = faithfulness(out["answer"], g)
    assert faith == 1.0 and not fabricated, (faith, fabricated)
    assert slot_copy_accuracy(_ENGINE_BONES, out["answer"]) == 1.0     # every grounded entity placed
    assert fl["faithfulness"] == 1.0
    # the learned verifier read is recorded for transparency and did not regress on the run-on
    assert fl["verifier_realized"] >= fl["verifier_literal"]


def test_gate_a_holds_on_a_second_independent_run_on():
    literal = _literal(_RIVER_BONES)
    u = perceive("Tell me about the river.", [])
    out = compose_response(u, "Tell me about the river.", extra=[_bones_candidate(_RIVER_BONES)])
    fl = out["fluency"]
    assert fl["adopted"] is True and out["answer"] != literal
    assert fluency_proxy(out["answer"])[0] > fluency_proxy(literal)[0]
    assert faithfulness(out["answer"], Grounding.from_bones(_RIVER_BONES))[0] == 1.0


# ── GATE (b): a hypothesis-tagged answer KEEPS its hedge marker after realization (tier survives) ─────

_HEDGE = "a projection, not a certainty"


def test_gate_b_projection_keeps_its_hedge_after_realization():
    body = _literal(_ENGINE_BONES)
    literal = f"{body.rstrip(' .')} — {_HEDGE}."               # a hypothesis-tagged multi-fact answer
    u = perceive(_NEUTRAL_Q, [])
    cand = _bones_candidate(_ENGINE_BONES, kind="temporal_projection", answer=literal)
    out = compose_response(u, _NEUTRAL_Q, extra=[cand])
    fl = out["fluency"]
    assert fl["adopted"] is True, fl
    assert fl["tier_preserved"] is True and fl["hedge_tier"] == "PROJECTED"
    # the hedge SURVIVED the reshape — it is still on the adopted surface
    assert _HEDGE in out["answer"].lower()
    # ...and the factual body really WAS reshaped (not merely kept literal): the run-on is broken up,
    # and the hedge is not something the bone realizer could have produced on its own (proves re-attach)
    body_only = out["answer"].lower().split("—")[0]
    assert _HEDGE not in body_only
    assert out["answer"] != literal
    # the surviving hedge is proven by epistemic_tier.enforce (a stripped marker would have raised)
    from packages.temporal_reasoning import epistemic_tier as et
    et.enforce(et.tag(out["answer"], et.Tier.PROJECTED, 0.7))     # does not raise -> tier intact
    # the factual body is still faithful (the hedge words are not counted against the grounding)
    assert faithfulness(body_only, Grounding.from_bones(_ENGINE_BONES))[0] == 1.0


def test_gate_b_retrodiction_hedge_also_survives():
    mark = "an inference from learned order, not a record"
    body = _literal(_RIVER_BONES)
    literal = f"{body.rstrip(' .')} — {mark}."
    u = perceive("Tell me about the river.", [])
    cand = _bones_candidate(_RIVER_BONES, kind="temporal_retrodiction", answer=literal)
    out = compose_response(u, "Tell me about the river.", extra=[cand])
    assert out["fluency"]["adopted"] is True
    assert out["fluency"]["hedge_tier"] == "RETRODICTED"
    assert mark in out["answer"].lower()


# ── GATE (c): faithfulness fallback — an altered/dropped fact is rejected, LITERAL is surfaced ────────

def test_gate_c_fabricated_fact_is_rejected_and_literal_surfaces(monkeypatch):
    literal = _literal(_ENGINE_BONES)

    def _fabricating_realize(bones, register=None, context=None):
        return "Engine is a machine that can fly to France and orbit Mars."   # France/Mars NOT grounded

    monkeypatch.setattr("packages.fluency.realizer.realize", _fabricating_realize)
    u = perceive(_NEUTRAL_Q, [])
    out = compose_response(u, _NEUTRAL_Q, extra=[_bones_candidate(_ENGINE_BONES)])
    fl = out["fluency"]
    assert fl["adopted"] is False, fl
    assert fl["reason"] == "no_faithful_surface"
    assert out["answer"] == literal                                # the literal, verbatim — no fabrication
    # every register attempt was rejected at the faithfulness/slot-copy floor
    assert all(v == "faithfulness_or_slotcopy_lt_1" for _, v in fl["registers_tried"]), fl


def test_gate_c_dropped_fact_is_rejected_and_literal_surfaces(monkeypatch):
    literal = _literal(_ENGINE_BONES)

    def _dropping_realize(bones, register=None, context=None):
        return "Engine is a machine."                              # faithful, but DROPS 5 of 6 facts

    monkeypatch.setattr("packages.fluency.realizer.realize", _dropping_realize)
    u = perceive(_NEUTRAL_Q, [])
    out = compose_response(u, _NEUTRAL_Q, extra=[_bones_candidate(_ENGINE_BONES)])
    assert out["fluency"]["adopted"] is False
    assert out["answer"] == literal                                # no removed-fact surface reaches output


def test_gate_c_a_lost_hedge_is_rejected(monkeypatch):
    """If the realizer body is fine but the hedge cannot be re-attached (simulate enforce failing),
    the tier-loss must be caught and the literal kept — a projection is never voiced as bare fact."""
    body = _literal(_ENGINE_BONES)
    literal = f"{body.rstrip(' .')} — {_HEDGE}."
    import packages.cgsr.cgsr.response_workspace as rw
    monkeypatch.setattr(rw, "_hedge_survives", lambda surface, hedge: False)   # force tier-loss detection
    u = perceive(_NEUTRAL_Q, [])
    cand = _bones_candidate(_ENGINE_BONES, kind="temporal_projection", answer=literal)
    out = compose_response(u, _NEUTRAL_Q, extra=[cand])
    assert out["fluency"]["adopted"] is False
    assert out["answer"] == literal and _HEDGE in out["answer"].lower()
    assert all(v == "tier_marker_lost" for _, v in out["fluency"]["registers_tried"])


# ── GATE (d): no-op safety — fixed forms untouched; winner + grounding unchanged; order-invariant ─────

def test_gate_d_abstention_is_not_reshaped_even_with_bones():
    # a fixed honest form: kind is an abstention -> never handed to the realizer, even if bones present
    literal = _literal(_ENGINE_BONES)
    u = perceive(_NEUTRAL_Q, [])
    cand = _bones_candidate(_ENGINE_BONES, kind="abstention", answer=literal, grounding=0.7)
    out = compose_response(u, _NEUTRAL_Q, extra=[cand])
    assert out["answer"] == literal                                # unchanged surface
    assert out["fluency"]["attempted"] is False
    assert out["fluency"]["reason"] == "fixed_form_kind"
    assert out["answer_kind"] == "abstention" and out["confidence"] == 0.7   # winner + grounding intact


def test_gate_d_boilerplate_string_is_not_reshaped():
    boiler = "I can only speak English."
    u = perceive(_NEUTRAL_Q, [])
    # a bidder mis-attaches bones to a boilerplate; the boilerplate guard still passes it through
    cand = _bones_candidate(_ENGINE_BONES, kind="world_fact", answer=boiler)
    out = compose_response(u, _NEUTRAL_Q, extra=[cand])
    assert out["answer"] == boiler and out["fluency"]["reason"] == "boilerplate"


def test_gate_d_reshapeable_false_is_honored():
    literal = _literal(_ENGINE_BONES)
    u = perceive(_NEUTRAL_Q, [])
    cand = _bones_candidate(_ENGINE_BONES, answer=literal, reshapeable=False)
    out = compose_response(u, _NEUTRAL_Q, extra=[cand])
    assert out["answer"] == literal and out["fluency"]["reason"] == "explicitly_fixed"


def test_gate_d_winner_and_surface_are_order_invariant():
    # the adopting multi-fact winner plus two weaker candidates; the winner, the adopted surface, and
    # the fluency verdict must be identical for EVERY evaluation order (selection is grounding-only)
    u = perceive(_NEUTRAL_Q, [])
    strong = _bones_candidate(_ENGINE_BONES, grounding=0.7)
    weak1 = lambda: Candidate("a weak aside", "chitchat", 0.1, "Weak-1")
    weak2 = lambda: Candidate("another weak aside", "chitchat", 0.2, "Weak-2")
    answers, kinds, adopts = set(), set(), set()
    for perm in itertools.permutations([strong, weak1, weak2]):
        out = compose_response(u, _NEUTRAL_Q, extra=list(perm))
        answers.add(out["answer"])
        kinds.add((out["answer_kind"], out["engine_name"], out["confidence"]))
        adopts.add(out["fluency"]["adopted"])
    assert len(answers) == 1 and len(kinds) == 1                   # one winner, one surface, every order
    assert adopts == {True}                                        # adoption is deterministic too


# ── GATE (e): no regression — the default no-bones bidders are untouched (the pass no-ops) ────────────

def test_gate_e_default_bidder_without_bones_is_never_reshaped():
    from packages.self_model.self_in_world_probe import PROMPT
    u = perceive(PROMPT, [])
    out = compose_response(u, PROMPT)                              # a real DEFAULT bidder (self-causal) wins
    assert out is not None and out["answer_kind"] == "self_causal_reasoning"
    assert out["fluency"]["attempted"] is False                   # the realizer is never called
    # a default bidder is a fixed determinate form with no bones -> either no-op reason proves it stood
    assert out["fluency"]["reason"] in ("no_bones", "fixed_form_kind")


def test_gate_e_no_candidate_still_returns_none():
    # nothing to say -> None, exactly as before (the surface pass only runs when there IS a winner)
    u = perceive("What is the boiling point of water?", [])
    assert compose_response(u, "What is the boiling point of water?") is None
