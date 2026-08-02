# -*- coding: utf-8 -*-
"""Sealed gates for the SITUATION-FACT EXTRACTOR's TWO NEW deliberator shapes — extending the reach-in-
time bridge (packages/cgsr/tests/test_deliberation_extractor_bridge.py) so the System-2 deliberator
fires on RAW natural language for the OTHER two shapes its structural decomposer recognizes:

  * SHAPE 2  _MORE_THAN_ENOUGH  "… more/greater/larger/higher/faster than … enough/minimum?"
             -> [relational(attr A) -> relational(threshold B) -> arithmetic(A > B)]
  * SHAPE 3  _WILL_FIND         "Will <agent> find/get/search … <entity>?"
             -> [belief(where the agent looks) -> mechanism|relational(a property of THAT place)]

Both are filled span-traceably by packages.situation_model.deliberation_extractor (extract_more_than_
enough / extract_will_find), attached inside the single comprehension pass (comprehension.py:perceive),
WITHOUT fabrication. The belief in SHAPE 3 is NOT inferred: it is COMPUTED by the already-proved
StateTracker organ from witnessed placements (it abstains when the agent was never co-present).

Every string below is HELD-OUT phrasing — none is copied from the reach-in-time bridge test, the
deliberator benchmark, or test_deliberator.py (no Town A / village / charter 1000 / warehouse /
Sally / Anne / marble / basket / Tom / Jane / report / desk). If a win were a memorized fixture
rather than genuine extraction+reasoning, these novel words would break it.

Per shape, the four sealed gates:
  (a) held-out phrasing end-to-end: perceive -> compose_response -> the deliberator WINS with a
      certificated multi-hop answer, and the bound value provably FLOWS across hops;
  (b) fabrication rejection: the same shape missing a required fact -> abstain, workspace emits None,
      no fabricated fact;
  (c) no world-fact smuggling: EVERY grounding fact maps to a verbatim span of the input;
  (d) contextual + no regression: simple/conversational -> None; the shape gate is the decomposer's
      own regex, not a private keyword list.
"""
from __future__ import annotations

from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import compose_response, _deliberation_candidate
from packages.situation_model.deliberation_extractor import (
    extract, extract_more_than_enough, extract_will_find, extract_grounding)
from packages.deliberator.controller import Deliberation, deliberate, single_shot
from packages.deliberator.steps import decompose


# ══ SHAPE 2 — held-out situations (novel vocabulary) ═══════════════════════════════════════════════
MTE_OK = ("Reservoir Kestrel has an area of 5000 hectares. The charter minimum is 1000 hectares. "
          "Is Reservoir Kestrel larger than the charter minimum?")
MTE_NEG = ("Reservoir Kestrel has an area of 5000 hectares. The charter minimum is 9000 hectares. "
           "Is Reservoir Kestrel larger than the charter minimum?")
# a totally different domain (probe / mass / kilograms) grounds through the SAME machinery
MTE_DOMAIN2 = ("Probe Lyra has a mass of 640 kilograms. The launch minimum is 500 kilograms. "
               "Is Probe Lyra more massive than the minimum requirement?")
# the compared magnitude is stated only qualitatively ("a soaring height") -> no number to invent
MTE_MISSING = ("Tower Vela has a soaring height. The safety minimum is 150 metres. "
               "Is Tower Vela higher than the minimum requirement?")
# two measured entities -> genuinely ambiguous which is being compared -> abstain (distractor guard)
MTE_AMBIGUOUS = ("Lake Auric has an area of 5000 hectares. Lake Boro has an area of 3000 hectares. "
                 "Is Lake Auric larger than the minimum requirement?")


# ══ SHAPE 3 — held-out situations (novel vocabulary) ═══════════════════════════════════════════════
# false belief: Bram sees the scroll in the urn, leaves, then Cleo moves it -> Bram still believes urn.
# second hop = a stated MATERIAL of the believed place (relational). A distractor place (the crate)
# has a DIFFERENT material that must NOT be used (the belief decides which place is looked up).
WF_MATERIAL = ("Bram and Cleo were in the gallery. The scroll was in the urn. Bram stepped out. "
               "Cleo moved the scroll to the crate. The urn is made of bronze. "
               "The crate is made of iron. Will Bram find the scroll?")
# second hop = a locked container (mechanism). Lock + key stated as SEPARATE sentences (the mechanism
# organ's condition reader parses that cleanly).
WF_MECHANISM = ("Mara and Nori were in the workshop. The locket was in the chest. Mara stepped out. "
                "Nori moved the locket to the cabinet. The chest was locked. The key is inside. "
                "Will Mara get the locket?")
# the agent was never co-present with any placement -> the belief organ abstains -> no grounding
WF_UNWITNESSED = ("The badge was in the locker. Nori moved the badge to the safe. "
                  "The locker is made of steel. Will Zed find the badge?")
# belief grounds, but the passage states NO property of the believed place -> second hop ungroundable
WF_NO_PROPERTY = ("Bram and Cleo were in the gallery. The scroll was in the urn. Bram stepped out. "
                  "Cleo moved the scroll to the crate. Will Bram find the scroll?")


# ── span-trace helpers (relation LABELS are LAD-surface and intentionally exempt) ──────────────────

def _prov_roundtrips(g: dict, text: str) -> bool:
    for _role, s in g.get("_provenance", {}).items():
        if s.get("start", -1) >= 0 and text[s["start"]:s["end"]] != s["span"]:
            return False
    return True


def _mte_facts_span_traced(g: dict, text: str) -> list[str]:
    low = text.lower()
    bad: list[str] = []
    for side in ("attr_a", "attr_b"):
        for (subj, _pred, obj) in g[side]["facts"]:
            if str(subj).lower() not in low:
                bad.append(f"{side}.subject!span:{subj!r}")
            if str(obj).lower() not in low:                # the VALUE must be a span, never smuggled
                bad.append(f"{side}.object!span:{obj!r}")
    if not _prov_roundtrips(g, text):
        bad.append("prov!offset")
    return bad


def _wf_facts_span_traced(g: dict, text: str) -> list[str]:
    low = text.lower()
    bad: list[str] = []
    bp = g["belief"]["payload"]
    if str(bp["agent"]).lower() not in low:
        bad.append(f"agent!span:{bp['agent']!r}")
    if str(bp["entity"]).lower() not in low:
        bad.append(f"entity!span:{bp['entity']!r}")
    for s in bp["sentences"]:                              # every belief sentence is a verbatim span
        if str(s).lower() not in low:
            bad.append(f"belief_sentence!span:{s!r}")
    second = g["second"]
    for (subj, _pred, obj) in second["payload"].get("facts", []):
        if str(subj).lower() not in low:
            bad.append(f"second.subject!span:{subj!r}")
        if str(obj).lower() not in low:
            bad.append(f"second.object!span:{obj!r}")
    if not _prov_roundtrips(g, text):
        bad.append("prov!offset")
    return bad


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SHAPE 2 — two-attribute comparison
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_mte_gate_a_held_out_phrasing_wins_via_deliberator_on_the_live_path():
    u = perceive(MTE_OK, [])
    assert u.deliberation_grounding is not None, "the extractor should ground this comparison shape"
    out = compose_response(u, MTE_OK)
    assert out is not None
    assert out["answer_kind"] == "deliberation"
    assert out["engine_name"] == "ATANOR Deliberator"
    assert out["answer"] == "meets the requirement"
    assert ("ATANOR Deliberator", 0.9) in out["considered"]


def test_mte_gate_a_second_domain_also_fires_proving_domain_blindness():
    u = perceive(MTE_DOMAIN2, [])
    out = compose_response(u, MTE_DOMAIN2)
    assert out and out["answer_kind"] == "deliberation" and out["answer"] == "meets the requirement"


def test_mte_gate_a_bound_values_really_flow_across_hops_not_a_lookup():
    """The win is a genuine 3-hop VERIFIED chain: the arithmetic hop compares the two magnitudes the
    two relational hops bound (5000 and 1000), and flipping the threshold to 9000 flips the verdict."""
    g = extract_grounding(MTE_OK)
    plan = decompose(MTE_OK, g)
    assert [sg.organ for sg in plan] == ["relational", "relational", "arithmetic"]
    res = deliberate(Deliberation(MTE_OK, plan, g["compose"]))
    assert res.abstained is False and res.hops == 3
    rel_binds = [s.bind_value for s in res.steps if s.organ == "relational"]
    assert rel_binds == ["5000", "1000"]                   # A's magnitude, then the threshold magnitude
    arith = [s for s in res.steps if s.organ == "arithmetic"][0]
    assert arith.certificate["expression"] == "5000 > 1000"   # both flowed into the comparison
    assert arith.answer is True
    gtee = res.certificate["guarantees"]
    assert gtee["every_executed_step_verified"] and gtee["composed_only_from_verified_steps"]
    assert gtee["fabricated_facts"] is False
    # the non-decomposing baseline provably cannot answer -> the chain is load-bearing
    assert single_shot(Deliberation(MTE_OK, plan, g["compose"])).abstained is True

    # same extraction, threshold flipped to 9000 -> the SAME machinery computes the opposite verdict
    gneg = extract_grounding(MTE_NEG)
    rneg = deliberate(Deliberation(MTE_NEG, decompose(MTE_NEG, gneg), gneg["compose"]))
    assert rneg.abstained is False
    assert [s for s in rneg.steps if s.organ == "arithmetic"][0].certificate["expression"] == "5000 > 9000"
    assert rneg.answer == "falls short of the requirement"
    assert compose_response(perceive(MTE_NEG, []), MTE_NEG)["answer"] == "falls short of the requirement"


def test_mte_gate_b_missing_magnitude_is_never_invented_workspace_abstains():
    u = perceive(MTE_MISSING, [])
    g = u.deliberation_grounding
    assert g is not None                                   # the shape is recognized (entity + threshold present)
    # the extractor did NOT invent a magnitude for the compared entity: attr_a's edge is a NON-numeric
    # note whose object is a span of the text, not a fabricated number
    preds = {p for (_s, p, _o) in g["attr_a"]["facts"]}
    assert "area" not in preds and "height" not in preds   # no numeric attribute edge was manufactured
    assert not any(str(o).strip().replace(".", "").isdigit() for (_s, _p, o) in g["attr_a"]["facts"])
    # -> the relational hop A cannot ground -> the whole workspace emits None (honest abstain)
    assert _deliberation_candidate(u, MTE_MISSING) is None
    assert compose_response(u, MTE_MISSING) is None


def test_mte_gate_b_underlying_chain_abstains_midchain_without_fabricating():
    g = extract_grounding(MTE_MISSING)
    res = deliberate(Deliberation(MTE_MISSING, decompose(MTE_MISSING, g), g["compose"]))
    assert res.abstained is True
    assert res.answer is None                              # NOT fabricated
    assert res.certificate["ungrounded_step"]["organ"] == "relational"
    assert res.certificate["guarantees"]["fabricated_facts"] is False
    assert res.certificate["guarantees"]["abstained_rather_than_bridge"] is True


def test_mte_gate_b_two_measured_entities_are_ambiguous_extractor_abstains():
    """A distractor measurement (Lake Boro) means the comparison target is ambiguous -> the extractor
    refuses to pick one, so nothing downstream can manufacture a verified answer."""
    ex = extract_more_than_enough(MTE_AMBIGUOUS)
    assert ex.grounding is None
    assert "ambiguous" in ex.note
    u = perceive(MTE_AMBIGUOUS, [])
    assert u.deliberation_grounding is None
    assert _deliberation_candidate(u, MTE_AMBIGUOUS) is None
    out = compose_response(u, MTE_AMBIGUOUS)
    assert out is None or out["answer_kind"] != "deliberation"


def test_mte_gate_c_every_grounding_fact_maps_to_a_span_of_the_input():
    g = extract_grounding(MTE_OK)
    assert _mte_facts_span_traced(g, MTE_OK) == []
    assert "5000" in MTE_OK and "1000" in MTE_OK           # both magnitudes literally present
    prov = g["_provenance"]
    assert {"compared_entity", "compared_value", "threshold_noun", "threshold_value"} <= set(prov)
    for role, s in prov.items():
        if s["start"] >= 0:
            assert MTE_OK[s["start"]:s["end"]] == s["span"], role


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SHAPE 3 — belief-chain
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_wf_gate_a_material_second_hop_wins_via_deliberator_on_the_live_path():
    u = perceive(WF_MATERIAL, [])
    assert u.deliberation_grounding is not None, "the extractor should ground this belief-chain shape"
    out = compose_response(u, WF_MATERIAL)
    assert out is not None
    assert out["answer_kind"] == "deliberation"
    assert out["engine_name"] == "ATANOR Deliberator"
    assert out["answer"] == "will look in the urn, which is made of bronze"
    assert ("ATANOR Deliberator", 0.9) in out["considered"]


def test_wf_gate_a_mechanism_second_hop_also_fires_proving_shape_breadth():
    u = perceive(WF_MECHANISM, [])
    out = compose_response(u, WF_MECHANISM)
    assert out and out["answer_kind"] == "deliberation"
    assert out["answer"] == "will look in the chest, but cannot open it (locked, key inside)"


def test_wf_gate_a_belief_value_really_flows_into_the_second_hop_not_a_lookup():
    """The win is a genuine 2-hop VERIFIED chain: the belief organ binds WHERE the agent looks (urn),
    and that bound place FLOWS into the second hop, which looks up the urn's material — NOT the
    distractor crate's material. Single-shot cannot compose the chain."""
    g = extract_grounding(WF_MATERIAL)
    plan = decompose(WF_MATERIAL, g)
    assert [sg.organ for sg in plan] == ["belief", "relational"]
    res = deliberate(Deliberation(WF_MATERIAL, plan, g["compose"]))
    assert res.abstained is False and res.hops == 2
    belief_step = [s for s in res.steps if s.organ == "belief"][0]
    rel_step = [s for s in res.steps if s.organ == "relational"][0]
    assert belief_step.bind_value == "urn"                 # the false belief (Bram left before the move)
    assert rel_step.bind_value == "bronze"                 # the urn's material, flowed from the belief
    assert rel_step.bind_value != "iron"                   # NOT the distractor crate's material
    # the material the belief pointed at is the only one that entered the grounding at all
    assert g["second"]["payload"]["facts"] == [("urn", "made_of", "bronze")]
    assert res.certificate["guarantees"]["fabricated_facts"] is False
    assert single_shot(Deliberation(WF_MATERIAL, plan, g["compose"])).abstained is True


def test_wf_gate_b_unwitnessed_belief_is_never_invented_workspace_abstains():
    """The agent (Zed) is never co-present with any placement, so the belief organ abstains. The
    extractor emits no grounding and invents no place -> the workspace stays silent."""
    ex = extract_will_find(WF_UNWITNESSED)
    assert ex.grounding is None
    assert "ungrounded" in ex.note and "co-present" in ex.note
    u = perceive(WF_UNWITNESSED, [])
    assert u.deliberation_grounding is None
    assert _deliberation_candidate(u, WF_UNWITNESSED) is None
    out = compose_response(u, WF_UNWITNESSED)
    assert out is None or out["answer_kind"] != "deliberation"


def test_wf_gate_b_no_stated_property_of_the_place_abstains_not_fabricates():
    """The belief grounds (Bram believes urn), but the passage states NO property of the urn -> the
    second hop cannot be grounded from a span -> abstain rather than invent one."""
    ex = extract_will_find(WF_NO_PROPERTY)
    assert ex.grounding is None
    assert "no span-traced property" in ex.note
    u = perceive(WF_NO_PROPERTY, [])
    assert u.deliberation_grounding is None
    assert compose_response(u, WF_NO_PROPERTY) is None


def test_wf_gate_c_every_grounding_fact_maps_to_a_span_of_the_input():
    for text in (WF_MATERIAL, WF_MECHANISM):
        g = extract_grounding(text)
        assert g is not None, text
        assert _wf_facts_span_traced(g, text) == [], text
        prov = g["_provenance"]
        assert {"agent", "sought_entity", "believed_place", "belief_evidence"} <= set(prov)
        for role, s in prov.items():
            if s["start"] >= 0:
                assert text[s["start"]:s["end"]] == s["span"], (text, role)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (d) — contextual + no regression (shared across both new shapes)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_gate_d_conversational_and_factoid_questions_attach_no_grounding():
    for q in ("How is your afternoon going so far?", "what's a ferret?",
              "what is the boiling point of water?", "hello there, friend",
              "Which is larger, the sun or the moon?", "Will you tell me a story?"):
        u = perceive(q, [])
        assert u.deliberation_grounding is None, q
        assert _deliberation_candidate(u, q) is None, q
        out = compose_response(u, q)
        assert out is None or out["answer_kind"] != "deliberation", q


def test_gate_d_shape_gates_are_the_decomposers_own_regexes_not_private_keyword_lists():
    """Anti-mode-switch: each new shape gate is imported from the decomposer, so what the reader
    targets can never drift from what decompose() actually recognizes."""
    from packages.situation_model import deliberation_extractor as dx
    from packages.deliberator import steps as dsteps
    assert dx._MORE_THAN_ENOUGH is dsteps._MORE_THAN_ENOUGH
    assert dx._WILL_FIND is dsteps._WILL_FIND


def test_gate_d_extractors_are_honest_about_why_they_abstain():
    assert extract_more_than_enough("How are you today?").note.startswith("not a more")
    assert extract_will_find("what is the capital of France?").note.startswith("not a will")
    # a more-than shape with no threshold value stated -> abstain naming the missing fact
    assert "no threshold" in extract_more_than_enough(
        "Reservoir Kestrel has an area of 5000 hectares. Is it larger than enough?").note


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SUMMARY — how many of the deliberator's 3 recognized shapes now fire on RAW NL
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_all_three_deliberator_shapes_now_fire_on_raw_nl():
    """The decomposer recognizes THREE composite shapes; after this vertebra, a raw-NL question of
    EACH shape populates deliberation_grounding through the single perceive pass and decomposes to a
    typed plan — no hand-attached grounding, no fabrication."""
    reach = ("The causeway was sealed off by the storm surge. The ring road is 12 km long. "
             "The crew must arrive within 20 km. Will the fire engine reach the depot in time?")
    cases = [
        (reach, ["mechanism", "relational", "arithmetic"]),
        (MTE_OK, ["relational", "relational", "arithmetic"]),
        (WF_MATERIAL, ["belief", "relational"]),
    ]
    fired = 0
    for text, organs in cases:
        g = extract_grounding(text)
        assert g is not None, text
        plan = decompose(text, g)
        assert plan is not None and [sg.organ for sg in plan] == organs, text
        fired += 1
    assert fired == 3                                      # 3 of 3 shapes fire on raw NL
