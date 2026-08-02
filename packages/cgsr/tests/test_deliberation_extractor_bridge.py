# -*- coding: utf-8 -*-
"""Sealed gates for the SITUATION-FACT EXTRACTOR — the last-mile bridge that lets ATANOR's System-2
deliberator fire on RAW natural language, not only on hand-attached grounding.

V1 wired the deliberator as a grounded workspace bidder, but nothing populated
``understanding.deliberation_grounding`` on real free-text questions, so the deliberator bid None in
production (it only fired in tests where the grounding was hand-attached). This vertebra adds
``packages.situation_model.deliberation_extractor``: a grounded reader that turns a user's
question/passage into the deliberator's OWN typed grounding shape — WITHOUT fabrication — and attaches
it inside the single comprehension pass (packages/cgsr/cgsr/comprehension.py:perceive).

Shape bridged (ONE, end-to-end): the "… reach/arrive/deliver … in time?" family the decomposer
already recognizes as [mechanism(blocked path) -> relational(detour magnitude) -> arithmetic(magnitude
vs budget)]. No new reasoning shape is invented.

Every string below is HELD-OUT phrasing — none is copied from
packages/cgsr/tests/test_deliberator_workspace_bidder.py or packages/deliberator/tests/test_deliberator.py
(no ambulance / bridge / flood / bypass / hospital / "length of the bypass" / 30). If the win were a
memorized fixture rather than genuine extraction+reasoning, these novel words would break it.

The four sealed gates:
  (a) held-out phrasing end-to-end: perceive -> compose_response -> the deliberator WINS with a
      certificated 3-hop answer, and the bound value provably FLOWS across hops (relational -> arithmetic);
  (b) fabrication rejection: same shape, the detour magnitude is simply NOT in the text -> the
      extractor invents no number -> the relational hop abstains mid-chain -> workspace emits None;
  (c) no world-fact smuggling: EVERY fact in the grounding maps to a verbatim span of the input, and a
      question needing an external world fact (a magnitude given only by reference) -> abstain;
  (d) contextual: a simple/conversational question attaches no grounding -> the deliberator bids None
      (V1 behavior preserved), and a bare reach-in-time question with NO passage also abstains.
"""
from __future__ import annotations

from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import compose_response, _deliberation_candidate
from packages.situation_model.deliberation_extractor import extract, extract_grounding
from packages.deliberator.controller import Deliberation, deliberate, single_shot
from packages.deliberator.steps import decompose


# ── held-out situations (novel vocabulary; passage + question in one message, the live shape) ──────
REACH_OK = ("The causeway was sealed off by the storm surge. The ring road is 12 km long. "
            "The crew must arrive within 20 km. Will the fire engine reach the depot in time?")
REACH_NEG = ("The causeway was sealed off by the storm surge. The ring road is 12 km long. "
             "The crew must get there in under 8 km. Will the fire engine reach the depot in time?")
# NOTE (D2 distractor-guard fix, 2026-07-22): the original phrasing measured "the service lane",
# whose own name does NOT mark it as the detour/alternate around the blockage — a service lane is an
# access lane, not inherently the way around an obstructed tunnel; the text left the detour-linkage
# to reader inference (underspecified). Under the tightened extractor (which trusts a magnitude as the
# detour only when the measured entity's own NP carries a detour cue) an unlinked measurement abstains.
# Rephrased to name the detour explicitly ("the alternate route"). This does NOT weaken the gate: it
# still proves domain-blindness (courier / parcel / miles, distinct from the fire-engine / km scenario)
# end-to-end; it only removes an accidental reliance on an UNLINKED measurement (6 <= 9 -> in time).
REACH_2 = ("The tunnel was obstructed by a stalled lorry. The alternate route is 6 miles long. "
           "The courier may cover at most 9 miles. Will the courier deliver the parcel on time?")
MISSING_MAGNITUDE = ("The causeway was sealed off by the storm surge. The ring road is quite long "
                     "and winding. The crew must arrive within 20 km. "
                     "Will the fire engine reach the depot in time?")
WORLD_FACT_NEEDED = ("The pass was barricaded by fallen rock. The detour is as long as the Nile. "
                     "The convoy must arrive within 40 minutes. Will the convoy reach the base in time?")


def _facts_span_traced(g: dict, text: str) -> list[str]:
    """Return a list of grounding facts that do NOT map to a verbatim span of ``text``. Empty list
    means every fact is span-traced (relation LABELS are surface-layer and intentionally exempt)."""
    low = text.lower()
    bad: list[str] = []
    if g["block_text"].lower() not in low:
        bad.append(f"block_text!span:{g['block_text']!r}")
    for (subj, _pred, obj) in g["detour_facts"]:
        if str(subj).lower() not in low:
            bad.append(f"subject!span:{subj!r}")
        if str(obj).lower() not in low:                    # the VALUE must be a span, never smuggled
            bad.append(f"object!span:{obj!r}")
    # the budget threshold literal must appear verbatim in the text
    thr = g["budget_expr"].split()[-1]
    if thr not in text:
        bad.append(f"threshold!span:{thr!r}")
    # and every recorded provenance entry must round-trip to its offset
    for role, s in g["_provenance"].items():
        if s["start"] >= 0 and text[s["start"]:s["end"]] != s["span"]:
            bad.append(f"prov[{role}]!offset")
    return bad


# ── GATE (a): held-out phrasing -> live path -> certificated multi-hop WIN, value flows across hops ─

def test_gate_a_held_out_phrasing_wins_via_deliberator_on_the_live_path():
    u = perceive(REACH_OK, [])                             # dual_brain.py:5433 (question, context)
    assert u.deliberation_grounding is not None, "the extractor should ground this reasoning shape"
    out = compose_response(u, REACH_OK)                    # dual_brain.py:5449
    assert out is not None
    assert out["answer_kind"] == "deliberation"
    assert out["engine_name"] == "ATANOR Deliberator"
    assert out["answer"] == "arrives in time"
    assert ("ATANOR Deliberator", 0.9) in out["considered"]


def test_gate_a_a_second_held_out_domain_also_fires_proving_domain_blindness():
    """A totally different domain (courier/parcel/service-lane/miles) grounds through the SAME
    mechanism — the bridge is domain-blind, not tuned to one scenario."""
    u = perceive(REACH_2, [])
    out = compose_response(u, REACH_2)
    assert out and out["answer_kind"] == "deliberation" and out["answer"] == "arrives in time"


def test_gate_a_bound_value_really_flows_across_hops_not_a_lookup():
    """Skeptic's check: the win is a genuine 3-hop VERIFIED chain, and the arithmetic hop evaluates
    the value the relational hop bound (12), it is not a canned phrase — flipping the budget to 8
    flips the verified verdict to negative."""
    g = extract_grounding(REACH_OK)
    plan = decompose(REACH_OK, g)
    assert [sg.organ for sg in plan] == ["mechanism", "relational", "arithmetic"]
    res = deliberate(Deliberation(REACH_OK, plan, g["compose"]))
    assert res.abstained is False and res.hops == 3
    steps = {s.organ: s for s in res.steps}
    assert steps["relational"].bind_value == "12"          # the magnitude extracted from the passage
    assert steps["arithmetic"].certificate["expression"] == "12 <= 20"   # flowed into the comparison
    assert steps["arithmetic"].answer is True
    gtee = res.certificate["guarantees"]
    assert gtee["every_executed_step_verified"] and gtee["composed_only_from_verified_steps"]
    assert gtee["fabricated_facts"] is False
    # the non-decomposing baseline provably cannot answer -> the chain is load-bearing
    assert single_shot(Deliberation(REACH_OK, plan, g["compose"])).abstained is True

    # same extraction, budget flipped to 8 -> the SAME machinery computes the opposite verified verdict
    gneg = extract_grounding(REACH_NEG)
    rneg = deliberate(Deliberation(REACH_NEG, decompose(REACH_NEG, gneg), gneg["compose"]))
    assert rneg.abstained is False
    assert {s.organ: s for s in rneg.steps}["arithmetic"].certificate["expression"] == "12 < 8"
    assert rneg.answer == "does not arrive in time"
    # and end-to-end the workspace surfaces that verified negative (not an abstention, not a guess)
    un = perceive(REACH_NEG, [])
    assert compose_response(un, REACH_NEG)["answer"] == "does not arrive in time"


# ── GATE (b): a required fact is simply not in the text -> abstain, NEVER invent it ────────────────

def test_gate_b_missing_magnitude_is_never_invented_workspace_abstains():
    u = perceive(MISSING_MAGNITUDE, [])
    g = u.deliberation_grounding
    assert g is not None                                   # the shape is recognized (block + budget present)
    # the extractor did NOT invent a length: the detour edge is a NON-length note, and its object is
    # a span of the text, not a fabricated number
    preds = {p for (_s, p, _o) in g["detour_facts"]}
    assert "length" not in preds                           # no length edge was manufactured
    assert not any(str(o).strip().replace(".", "").isdigit() for (_s, _p, o) in g["detour_facts"])
    # -> the relational hop cannot ground -> the whole workspace emits None (honest abstain)
    assert _deliberation_candidate(u, MISSING_MAGNITUDE) is None
    assert compose_response(u, MISSING_MAGNITUDE) is None


def test_gate_b_underlying_chain_abstains_midchain_without_fabricating():
    """The None above is the honest projection of a real mid-chain abstention: hop 0 (mechanism)
    grounds, hop 1 (detour length) cannot, hop 2 never runs, the answer stays None — nothing bridged."""
    g = extract_grounding(MISSING_MAGNITUDE)
    res = deliberate(Deliberation(MISSING_MAGNITUDE, decompose(MISSING_MAGNITUDE, g), g["compose"]))
    assert res.abstained is True
    assert res.answer is None                              # NOT fabricated
    assert res.certificate["ungrounded_step"]["organ"] == "relational"
    assert res.certificate["guarantees"]["fabricated_facts"] is False
    assert res.certificate["guarantees"]["abstained_rather_than_bridge"] is True


# ── GATE (c): no world-fact smuggling — every grounding fact is a span; external facts -> abstain ──

def test_gate_c_every_grounding_fact_maps_to_a_span_of_the_input():
    g = extract_grounding(REACH_OK)
    assert _facts_span_traced(g, REACH_OK) == []           # no fact escapes the passage
    # the two magnitudes are literally present (nothing was numerically invented)
    assert "12" in REACH_OK and "20" in REACH_OK
    # provenance covers each fact and round-trips to its exact offset
    prov = g["_provenance"]
    assert {"blocked_path", "detour_entity", "detour_length", "budget_threshold"} <= set(prov)
    for role, s in prov.items():
        if s["start"] >= 0:
            assert REACH_OK[s["start"]:s["end"]] == s["span"], role


def test_gate_c_a_magnitude_given_only_by_world_reference_is_not_smuggled():
    """'as long as the Nile' needs an EXTERNAL world fact (the Nile's length). The extractor refuses
    to resolve it: no number enters the grounding, the detour edge stays a span-traced note, and the
    workspace abstains rather than smuggle the world magnitude."""
    u = perceive(WORLD_FACT_NEEDED, [])
    g = u.deliberation_grounding
    assert g is not None
    # nothing numeric was smuggled for the detour, and every stored object is a span of the text
    assert not any(str(o).strip().replace(".", "").isdigit() for (_s, _p, o) in g["detour_facts"])
    assert _facts_span_traced(g, WORLD_FACT_NEEDED) == []
    assert _deliberation_candidate(u, WORLD_FACT_NEEDED) is None
    assert compose_response(u, WORLD_FACT_NEEDED) is None


# ── GATE (d): contextual — a non-reasoning input attaches no grounding (V1 behavior preserved) ─────

def test_gate_d_conversational_and_factoid_questions_attach_no_grounding():
    for q in ("How is your afternoon going so far?", "what's a ferret?",
              "what is the boiling point of water?", "hello there, friend"):
        u = perceive(q, [])
        assert u.deliberation_grounding is None, q          # not a reasoning shape -> nothing attached
        assert _deliberation_candidate(u, q) is None, q
        out = compose_response(u, q)
        assert out is None or out["answer_kind"] != "deliberation", q


def test_gate_d_bare_reach_question_without_a_passage_abstains_preserving_v1():
    """A reach-in-time question with NO situation stated (the exact V1 gate-(a) step-1 case) still
    attaches no grounding — absence of the facts is honored, not filled from priors."""
    bare = "Will the fire engine reach the depot in time?"
    u = perceive(bare, [])
    assert u.deliberation_grounding is None                 # no block / detour / budget in the text
    assert compose_response(u, bare) is None


def test_gate_d_shape_gate_is_the_decomposers_own_regex_not_a_private_keyword_list():
    """Anti-mode-switch: the extractor's shape gate is imported from the decomposer, so what the
    reader targets can never drift from what decompose() actually recognizes."""
    from packages.situation_model import deliberation_extractor as dx
    from packages.deliberator import steps as dsteps
    assert dx._REACH_IN_TIME is dsteps._REACH_IN_TIME


def test_gate_d_extractor_returns_none_note_explains_each_abstention():
    """The extractor is honest about WHY it abstains (useful for audit; also proves absence handling
    is explicit, not accidental)."""
    assert extract("How are you today?").note.startswith("not a reach")
    assert "no blocked-path" in extract("Will the shuttle reach the gate in time?").note
    # block present, but neither detour nor budget stated -> abstain on the first missing fact
    assert extract("The lane was sealed off. Will the van reach the yard in time?").grounding is None


# ── NEW sealed gates: DISTRACTOR / AMBIGUITY guard — a mis-binding is worse than an honest abstain ──
#
# Code review of the D2 extractor found a real correctness gap: _find_detour returned the FIRST
# measured entity that was not the blocked path, so a DISTRACTOR measurement of an UNRELATED entity
# ("the river is 100 km long") was mis-bound as "the detour magnitude" and the deliberator produced a
# WRONG verified answer (100 <= 20 -> "does not arrive in time"). This does not fabricate (100 is in
# the text) but it violates the deeper doctrine: when the detour entity is unlinked/ambiguous, ABSTAIN,
# do not guess. The fix trusts a magnitude as the detour ONLY when the measured entity's own noun
# phrase carries a detour/alternate cue; else it abstains. It only ever abstains MORE (linked ⊆ any).
#
# PHRASING NB (honest, load-bearing): the mechanism organ (packages/situation_model/mechanism.py:43)
# recognizes blocked|obstructed|barricaded|"sealed off" as block cues but NOT "closed". The review's
# literal repro ("The bridge is closed …") therefore abstains UPSTREAM (no block detected) and never
# reaches _find_detour — masking the bug. We phrase the block with a RECOGNIZED verb so the assertion
# actually exercises the distractor path; test (a) also pins the "closed" wording's upstream abstain.

DISTRACTOR_MEASURE = ("The bridge was sealed off by the flood. The river is 100 km long. "
                      "A bypass is available. Will the truck arrive within 20 km?")
TWO_DETOURS_AMBIGUOUS = ("The bridge was sealed off by the flood. The detour is 15 km long. "
                         "The alternate route is 22 km long. Will the truck arrive within 20 km?")
CLEAN_DETOUR_LINKED = ("The bridge was sealed off by the flood. The bypass is 12 km long. "
                       "Will the truck arrive within 20 km?")


def test_gate_new_a_distractor_measurement_is_not_mis_bound_extractor_abstains():
    """(a) A measured DISTRACTOR (the river) is present but the real detour (the bypass) has NO stated
    magnitude. The extractor must not bind river=100 as the detour: it abstains, names why, and the
    deliberator therefore does not answer (the pre-fix bug produced 'does not arrive in time')."""
    ex = extract(DISTRACTOR_MEASURE)
    assert ex.grounding is None                                    # no grounding emitted -> honest abstain
    assert "not linked" in ex.note                                 # abstains for the RIGHT reason (unlinked)
    # nothing downstream can manufacture the wrong verified answer: no plan, no candidate, no response
    assert extract_grounding(DISTRACTOR_MEASURE) is None
    assert decompose(DISTRACTOR_MEASURE, extract_grounding(DISTRACTOR_MEASURE)) is None
    u = perceive(DISTRACTOR_MEASURE, [])
    assert u.deliberation_grounding is None
    assert _deliberation_candidate(u, DISTRACTOR_MEASURE) is None
    out = compose_response(u, DISTRACTOR_MEASURE)
    assert out is None or out["answer_kind"] != "deliberation"
    # the literal review wording ("is closed") ALSO yields no answer — but via an orthogonal UPSTREAM
    # (no-block) abstain in the mechanism organ, not the linkage guard (documented, distinct safety)
    closed = extract(DISTRACTOR_MEASURE.replace("was sealed off", "is closed"))
    assert closed.grounding is None and "no blocked-path" in closed.note


def test_gate_new_b_two_detour_linked_magnitudes_are_ambiguous_extractor_abstains():
    """(b) Two DISTINCT detour-linked measurements (detour=15, alternate route=22) are genuine
    ambiguity. The extractor abstains rather than silently pick the first-matched one."""
    ex = extract(TWO_DETOURS_AMBIGUOUS)
    assert ex.grounding is None
    assert "ambiguous" in ex.note
    u = perceive(TWO_DETOURS_AMBIGUOUS, [])
    assert u.deliberation_grounding is None
    assert _deliberation_candidate(u, TWO_DETOURS_AMBIGUOUS) is None
    out = compose_response(u, TWO_DETOURS_AMBIGUOUS)
    assert out is None or out["answer_kind"] != "deliberation"


def test_gate_new_c_clean_detour_linked_single_measurement_still_fires_not_over_abstaining():
    """(c) The tightening must not over-abstain: a single, clearly detour-linked measurement (the
    bypass) still grounds and yields the correct VERIFIED answer (12 <= 20 -> arrives in time)."""
    ex = extract(CLEAN_DETOUR_LINKED)
    assert ex.grounding is not None                                # detour-linkage recognized -> fires
    assert ex.grounding["detour_facts"] == [("bypass", "length", 12)]
    g = ex.grounding
    plan = decompose(CLEAN_DETOUR_LINKED, g)
    assert [sg.organ for sg in plan] == ["mechanism", "relational", "arithmetic"]
    res = deliberate(Deliberation(CLEAN_DETOUR_LINKED, plan, g["compose"]))
    assert res.abstained is False and res.hops == 3
    assert {s.organ: s for s in res.steps}["arithmetic"].certificate["expression"] == "12 <= 20"
    assert res.answer == "arrives in time"
    assert res.certificate["guarantees"]["fabricated_facts"] is False
    # end-to-end on the live path it surfaces the same verified answer (not an abstain, not a guess)
    u = perceive(CLEAN_DETOUR_LINKED, [])
    out = compose_response(u, CLEAN_DETOUR_LINKED)
    assert out and out["answer_kind"] == "deliberation" and out["answer"] == "arrives in time"
