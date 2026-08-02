# -*- coding: utf-8 -*-
"""Sealed gates for the CO KEYSTONE — making the main frame_realizer knowledge answer a FIRST-CLASS
response-WORKSPACE bidder, so compose_response GOVERNS real knowledge traffic instead of being bypassed
by it (the one-model-not-modeswitch completion). Two pieces are proven here:

  1. packages/cgsr/cgsr/response_workspace.py:route_knowledge_answer — enters the finalized main answer
     into the workspace as an 'ATANOR Main' bidder (grounding = honest confidence, capped strictly below
     the verified reasoning lanes) carrying its grounded bones, and arbitrates it against every specialist.
  2. the NO-DROP safety gate (response_workspace._reshape_drops_content, enforced inside _fluency_surface)
     — the mechanism that makes routing the prose answer through the fluency pass SAFE: a bones reshape
     that would DROP the curated prose definition (a real degradation that still scores faithfulness 1.0)
     is rejected, and the LITERAL answer is preserved verbatim.

Gates:
  (a) knowledge battery: the real main answer wins the arbitration on ordinary knowledge questions, and
      its surface is EITHER byte-identical to today's OR a faithfulness-1.0 fluency improvement that drops
      NO fact — never a degradation, never a specialist side-lane hijack;
  (b) the fluency surface pass is wired over the workspace winner — it FIRES (adopts) on a bone-derived
      answer with faithfulness 1.0, and on today's curated-PROSE answers it ATTEMPTS and is safely
      rejected by the no-drop gate (the measured real-traffic fire-rate, reported honestly);
  (c) specialists still win on THEIR shapes — a verified deliberation (0.9) out-ranks the main answer,
      while a temporal projection (0.45) and every low lane can NEVER out-rank a solid knowledge answer
      (the anti-hijack the keystone guarantees);
  (d) the no-drop gate is a pure preservation gate — it rejects a definition-dropping reshape and keeps
      a lossless one, and route_knowledge_answer preserves the literal byte-for-byte when the main wins.

No new fact source, no new weights: the fluency package + the existing workspace are reused verbatim.
"""
from __future__ import annotations

import itertools

import pytest

import packages.cgsr.cgsr.response_workspace as rw
from packages.base_brain.zero_user_answer import answer_with_base_brain, english_answer_bones
from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import (
    Candidate,
    MAIN_ENGINE_NAME,
    MAIN_GROUNDING_CEILING,
    compose_response,
    route_knowledge_answer,
    _reshape_drops_content,
)
from packages.fluency.delex import Grounding
from packages.fluency.fluency_v1 import faithfulness, fluency_proxy, slot_copy_accuracy, tasks
from packages.realizer_struct import frame_realizer as fr

# The real frame_realizer knowledge answers (multi-fact prose from base_brain) this keystone governs.
_KNOWLEDGE_BATTERY = [
    "What is Kubernetes?",
    "What is Docker?",
    "Explain machine learning.",
    "What is GraphRAG?",
    "What is a neural network?",
    "What is Spring Boot?",
    "What is a semantic graph?",
    "What is a container?",
]


def _real_main_answer(query: str) -> tuple[str, str, float, list]:
    """Today's REAL main frame_realizer answer + its grounded bones — exactly what the live path emits
    for this knowledge question (no fixture prose)."""
    res = answer_with_base_brain(query, language="en")
    return (str(res["answer"]), str(res["answer_kind"]), float(res.get("confidence") or 0.0),
            english_answer_bones(query))


# ── GATE (a): the real main answer WINS ordinary knowledge, preserved-or-improved, never degraded ─────

@pytest.mark.parametrize("query", _KNOWLEDGE_BATTERY)
def test_gate_a_main_answer_wins_and_is_preserved_or_faithfully_improved(query):
    literal, kind, conf, bones = _real_main_answer(query)
    assert literal.strip(), query
    u = perceive(query, [])
    routed = route_knowledge_answer(literal, kind, conf, u, query, bones=bones)

    # the main knowledge answer WON the arbitration (ordinary knowledge -> specialists abstain)
    assert routed["won_by"] == "main", (query, routed["considered"])
    assert routed["engine_name"] == MAIN_ENGINE_NAME
    assert (MAIN_ENGINE_NAME, round(min(conf, MAIN_GROUNDING_CEILING), 2)) in routed["considered"]

    # the surface is EITHER byte-identical to today's OR a faithfulness-1.0 fluency improvement...
    if routed["answer"] != literal:
        assert routed["fluency"]["adopted"] is True, (query, routed["fluency"])
        assert routed["fluency"]["faithfulness"] == 1.0
        assert faithfulness(routed["answer"], Grounding.from_bones(bones))[0] == 1.0
    # ...and in NEITHER case does it drop a fact the literal carried (zero degradation, always)
    assert not _reshape_drops_content(literal, routed["answer"]), (query, routed["answer"])


def test_gate_a_no_answer_in_the_battery_is_degraded_across_the_whole_set():
    """Aggregate zero-degradation guarantee across the whole battery: every routed answer either equals
    today's answer or is a fact-preserving fluency improvement — nothing gets worse."""
    degraded = []
    for query in _KNOWLEDGE_BATTERY:
        literal, kind, conf, bones = _real_main_answer(query)
        routed = route_knowledge_answer(literal, kind, conf, perceive(query, []), query, bones=bones)
        preserved = routed["answer"] == literal
        improved = (routed["answer"] != literal and routed["fluency"].get("adopted")
                    and routed["fluency"].get("faithfulness") == 1.0
                    and not _reshape_drops_content(literal, routed["answer"]))
        if not (preserved or improved):
            degraded.append((query, literal, routed["answer"]))
    assert not degraded, degraded


# ── GATE (b): the fluency surface pass is WIRED over the workspace winner ──────────────────────────────

def test_gate_b_fluency_fires_on_a_bone_derived_winner_with_faithfulness_1():
    """The payoff mechanism is live: a bone-derived multi-fact winner routed through the workspace is
    re-surfaced MORE naturally (proxy up) at faithfulness 1.0 — proving fluency fires on the winner."""
    bones = [t for t in tasks() if t["id"] == "m_engine"][0]["bones"]
    literal = fr.realize(bones)                                   # a genuine bone-derived answer (no extra prose)
    u = perceive("Tell me about the engine.", [])
    routed = route_knowledge_answer(literal, "world_fact", 0.85, u, "Tell me about the engine.", bones=bones)
    assert routed["won_by"] == "main"
    assert routed["fluency"]["adopted"] is True, routed["fluency"]
    assert routed["answer"] != literal                           # the surface really changed
    assert fluency_proxy(routed["answer"])[0] > fluency_proxy(literal)[0]
    assert faithfulness(routed["answer"], Grounding.from_bones(bones))[0] == 1.0
    assert slot_copy_accuracy(bones, routed["answer"]) == 1.0
    assert not _reshape_drops_content(literal, routed["answer"])  # improvement dropped nothing


def test_gate_b_prose_answers_attempt_but_are_safely_kept_literal_measured_fire_rate():
    """On today's REAL curated-prose answers the pass ATTEMPTS (bones present) but the no-drop gate keeps
    the literal — so the measured real-traffic fire-rate is honestly reported, never faked by degrading."""
    attempted = adopted = 0
    for query in _KNOWLEDGE_BATTERY:
        literal, kind, conf, bones = _real_main_answer(query)
        if len([b for b in bones if b]) < 2:
            continue                                             # single-fact -> nothing to reshape (no-op)
        routed = route_knowledge_answer(literal, kind, conf, perceive(query, []), query, bones=bones)
        fl = routed["fluency"]
        if fl.get("attempted"):
            attempted += 1
        if fl.get("adopted"):
            adopted += 1
            # a real adoption (if any) must be faithful AND drop nothing
            assert fl.get("faithfulness") == 1.0 and not _reshape_drops_content(literal, routed["answer"])
        else:
            # the honest reason a prose answer is kept literal: its un-bone-able definition would be dropped
            assert routed["answer"] == literal
    assert attempted >= 1, "the fluency pass must run over real main-path traffic (it is wired)"
    # adopted is the measured fire-rate on curated prose; it may be 0 (definition-drop safely rejected) —
    # asserting <= attempted keeps the gate honest without manufacturing a fire by shipping a degradation
    assert adopted <= attempted


# ── GATE (c): specialists still win on THEIR shapes; low lanes never out-rank a solid knowledge answer ─

def _reach_grounding():
    """The genuine solved deliberation case (packages/deliberator/tests/test_deliberator.py) — a 3-hop
    verified chain whose facts are stated in the situation, bidding grounding 0.9."""
    return {
        "cross_question": "Can the ambulance cross the bridge?",
        "block_text": "The bridge was blocked by the flood.",
        "detour_query": "what is the length of the bypass?",
        "detour_facts": [("bypass", "length", 22)],
        "budget_expr": "{detour_len} <= 30",
        "compose": lambda b: ("arrives in time" if b["in_time"] else "too late"),
    }


def test_gate_c_verified_deliberation_outranks_the_main_answer_on_its_shape():
    reach_q = "Will the ambulance reach the hospital in time?"
    u = perceive(reach_q, [])
    u.deliberation_grounding = _reach_grounding()                 # a real verified 3-hop chain bids 0.9
    # the main answer competes at its ceiling 0.85; the verified deliberation (0.9) must WIN on its shape
    routed = route_knowledge_answer("An unrelated definitional blurb.", "base_brain_zero_user_data",
                                    0.85, u, reach_q, bones=[["x", "is_a", "y"], ["x", "uses", "z"]])
    assert routed["won_by"] == "specialist"
    assert routed["answer_kind"] == "deliberation"
    assert "arrives in time" in routed["answer"]


def test_gate_c_a_temporal_projection_never_hijacks_a_solid_knowledge_answer(monkeypatch):
    """The anti-hijack the keystone guarantees: on a temporal-shaped question the block-universe bidder
    fires (0.45), but a solid main knowledge answer (0.85) out-ranks it — the low lane cannot hijack."""
    from packages.temporal_reasoning.block_universe import BlockUniverse
    from packages.temporal_reasoning.precedence_field import PrecedenceField
    from packages.temporal_reasoning.unified_timeline import Timeline

    def _covered_bu(raw_question: str) -> BlockUniverse:
        tl = Timeline()
        tl.record("utterance", raw_question or "", who="user")
        return BlockUniverse(tl, PrecedenceField(
            phase={"plant": -0.9, "grow": -0.3, "harvest": 0.3, "eat": 0.9},
            seen={"plant": 5, "grow": 5, "harvest": 5, "eat": 5}))

    monkeypatch.setattr(rw, "_shared_block_universe", _covered_bu)
    fwd_q = "What typically comes after we grow the crops?"
    u = perceive(fwd_q, [])
    # sanity: WITHOUT the main answer, the temporal bidder really does fire here (0.45)
    bare = compose_response(u, fwd_q)
    assert bare is not None and bare["answer_kind"] == "temporal_projection"
    # WITH the solid main knowledge answer present, the main answer wins — temporal cannot hijack it
    routed = route_knowledge_answer("Crops are a kind of plant that people grow for food.",
                                    "base_brain_zero_user_data", 0.85, u, fwd_q,
                                    bones=[["crop", "is_a", "plant"], ["crop", "used_for", "food"]])
    assert routed["won_by"] == "main", routed["considered"]
    assert ("ATANOR Block-Universe", 0.45) in routed["considered"]     # it competed, and lost
    assert routed["confidence"] == MAIN_GROUNDING_CEILING


# ── GATE (d): the no-drop gate is a pure preservation gate; routing preserves the literal byte-for-byte ─

def test_gate_d_nodrop_rejects_a_definition_dropping_reshape():
    # a base-brain prose literal with a curated definition the relation bones cannot reconstruct
    literal = ("Kubernetes deploys, scales, and operates containers across machines. It is a kind of "
               "container orchestration system and manages a container.")
    bone_only_reshape = "Kubernetes is a container orchestration system. It manages a container."
    # the reshape kept the bones but DROPPED the definition (deploys/scales/operates/machines) -> reject
    assert _reshape_drops_content(literal, bone_only_reshape) is True


def test_gate_d_nodrop_accepts_a_lossless_regrouping():
    # the SAME facts, only regrouped/pronominalized (no content dropped) -> not a drop
    literal = "Engine is a machine, and can start, and can stop."
    regrouped = "Engine is a machine. It can start. It can stop."
    assert _reshape_drops_content(literal, regrouped) is False


def test_gate_d_route_preserves_the_literal_byte_for_byte_when_main_wins_and_reshape_is_unsafe():
    literal, kind, conf, bones = _real_main_answer("What is Kubernetes?")
    routed = route_knowledge_answer(literal, kind, conf, perceive("What is Kubernetes?", []),
                                    "What is Kubernetes?", bones=bones)
    assert routed["won_by"] == "main"
    assert routed["answer"] == literal                           # byte-for-byte, no degradation
    assert routed["changed"] is False
    assert routed["fluency"]["reason"] == "literal_content_dropped"   # the honest keep-literal reason


def test_gate_d_empty_answer_is_returned_unchanged():
    routed = route_knowledge_answer("", "base_brain_zero_user_data", 0.85, perceive("x", []), "x")
    assert routed["won_by"] == "main" and routed["answer"] == "" and routed["changed"] is False
