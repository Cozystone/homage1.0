# -*- coding: utf-8 -*-
"""Sealed gates for the COMPOSED register — the CLAUSE-COMBINING lever (R4 next lever).

The conversational register improved the fluency SURFACE (contractions, discourse markers), but the
binding constraint on DEEPER fluency is delex+copy's clause-per-bone STRUCTURE: the flat planner emits
one clause per fact with is_a always the copular head ("X is a Y. It is made of Z. It can W."), so the
"It … It … It …" parallel signature and a flat clause count are its ceiling. The composed register adds
the missing capability — it re-packages a subject's bones into VARIED syntax (apposition, coordination,
relative subordination) while a wrong combination is worse than a flat clause, so EVERY combined sentence
is FAITHFULNESS-GATED against the flat baseline and rejected -> flat on any failure.

Gates (deterministic fixtures):
  (a) OUTPUT variety up  — on HELD-OUT multi-fact bones, combining measurably raises syntactic variety
      (combination/subordination rate up, sentence count down, TTR up-or-flat) vs the flat baseline.
  (b) Faithfulness 1.0   — every combined output preserves the EXACT fact set (faithfulness/slot-copy
      1.0, content multiset == flat); a meaning-altering combination is rejected -> flat (constructed).
  (c) No over-combining  — sparse / verb-less (purely taxonomic) bones are NOT forced into combinations;
      the readability bound is respected.
  (d) No surface leak    — the flat registers gain no combining; composed is never auto-routed from a
      query string.
"""
from __future__ import annotations

import re

import packages.fluency.realizer as R
from packages.fluency import register_metrics as RM
from packages.fluency.delex import Grounding
from packages.fluency.fluency_v1 import faithfulness, slot_copy_accuracy
from packages.fluency.realizer import realize, realize_with_trace
from packages.fluency.register import default_registers, load_registers, select_register

# ── HELD-OUT bones (subjects absent from fluency_v1.tasks) ─────────────────────────────────────────
# RICH multi-fact: every one carries a promotable predicate (capable_of / has_a) -> combinable.
_MULTI = [
    [["otter", "is_a", "mammal"], ["otter", "has_property", "playful"], ["otter", "located_in", "rivers"],
     ["otter", "capable_of", "swim"], ["otter", "has_a", "thick coat"]],
    [["kettle", "is_a", "vessel"], ["kettle", "made_of", "steel"], ["kettle", "used_for", "boiling water"],
     ["kettle", "capable_of", "whistle"], ["kettle", "has_a", "spout"]],
    [["glacier", "is_a", "mass"], ["glacier", "made_of", "ice"], ["glacier", "capable_of", "flow"],
     ["glacier", "used_for", "storing freshwater"], ["glacier", "has_a", "crevasse"],
     ["glacier", "has_property", "ancient"]],
    [["printer", "is_a", "device"], ["printer", "made_of", "plastic"], ["printer", "used_for", "printing"],
     ["printer", "capable_of", "scan"], ["printer", "has_a", "tray"]],
    [["lighthouse", "is_a", "tower"], ["lighthouse", "made_of", "stone"], ["lighthouse", "located_in", "harbors"],
     ["lighthouse", "used_for", "guiding ships"], ["lighthouse", "capable_of", "rotate"],
     ["lighthouse", "has_a", "lamp"]],
    [["tractor", "is_a", "machine"], ["tractor", "made_of", "steel"], ["tractor", "used_for", "farming"],
     ["tractor", "capable_of", "tow"], ["tractor", "has_a", "engine"]],
    [["canyon", "is_a", "valley"], ["canyon", "made_of", "rock"], ["canyon", "has_property", "deep"],
     ["canyon", "used_for", "hiking"], ["canyon", "has_a", "river"]],
    [["sparrows", "is_a", "bird"], ["sparrows", "has_property", "small"], ["sparrows", "located_in", "hedgerows"],
     ["sparrows", "capable_of", "fly"]],
    [["espresso", "is_a", "coffee"], ["espresso", "has_property", "Italian"], ["espresso", "made_of", "beans"],
     ["espresso", "used_for", "waking up"], ["espresso", "has_a", "crema"]],
    [["penguins", "is_a", "bird"], ["penguins", "has_property", "flightless"],
     ["penguins", "located_in", "Antarctica"], ["penguins", "capable_of", "swim"]],
]
# the clean relative-clause niche: is_a (+ adjective) + a single capability, nothing else combinable.
_RELATIVE = [
    [["mice", "is_a", "rodent"], ["mice", "has_property", "small"], ["mice", "capable_of", "climb"]],
    [["salmon", "is_a", "fish"], ["salmon", "has_property", "pink"], ["salmon", "capable_of", "swim"]],
    [["sparrow", "is_a", "bird"], ["sparrow", "capable_of", "fly"]],
]
# VERB-LESS: is_a + only descriptive/reduced facts (located_in / made_of) — NO predicate to promote.
_VERBLESS = [
    [["kyushu", "is_a", "island"], ["kyushu", "located_in", "Japan"]],
    [["basalt", "is_a", "rock"], ["basalt", "made_of", "lava"], ["basalt", "has_property", "dark"]],
    [["delta", "is_a", "landform"], ["delta", "located_in", "rivermouth"], ["delta", "made_of", "sediment"]],
]
_SPARSE = [[["almond", "is_a", "seed"]], [["harbor", "is_a", "port"], ["harbor", "located_in", "coast"]]]

_ENGINE = [["engine", "is_a", "machine"], ["engine", "made_of", "metal"], ["engine", "used_for", "propulsion"],
           ["engine", "capable_of", "burn fuel"], ["engine", "has_a", "piston"],
           ["engine", "capable_of", "generate power"]]


def _texts(tasks, reg):
    return [realize(bones, register=reg) for bones in tasks]


def _fire(tasks, reg="composed"):
    from collections import Counter
    labels = []
    for bones in tasks:
        labels += realize_with_trace(bones, register=reg)[1]
    return Counter(labels)


# ── GATE (a): the OUTPUT syntactic variety measurably rises ────────────────────────────────────────
def test_gate_a_output_variety_rises_vs_simple():
    """On held-out multi-fact bones, composed raises combination/subordination rate and drops sentence
    count vs the flat 'simple' baseline, while TTR stays up-not-down (per-feature delta)."""
    d = RM.syntactic_feature_delta(_texts(_MULTI, "simple"), _texts(_MULTI, "composed"))
    assert d["combination_rate"]["delta"] > 0.2, d["combination_rate"]      # markedly more combining
    assert d["subordination_rate"]["after"] > 0.3, d["subordination_rate"]  # subordination the flat lacks
    assert d["subordination_rate"]["before"] == 0.0, d["subordination_rate"]
    assert d["appositive_rate"]["delta"] > 0.2, d["appositive_rate"]
    assert d["sentence_count"]["delta"] < 0.0, d["sentence_count"]          # clause-count reduction
    assert d["type_token_ratio"]["delta"] >= -0.01, d["type_token_ratio"]   # TTR up-or-flat, not down


def test_gate_a_kills_parallel_it_opener_signature():
    """The stiff 'It … It … It …' parallel opener signature falls: opener variety rises."""
    before = RM.mean_features(_texts(_MULTI, "simple"))
    after = RM.mean_features(_texts(_MULTI, "composed"))
    assert after["opener_variety"] > before["opener_variety"]


def test_gate_a_adds_subordination_beyond_neutral():
    """The gain is not merely 'simple was extra-flat': composed adds SUBORDINATION (apposition/relative)
    that the coordinating 'neutral' register does not produce."""
    d = RM.syntactic_feature_delta(_texts(_MULTI, "neutral"), _texts(_MULTI, "composed"))
    assert d["subordination_rate"]["before"] == 0.0
    assert d["subordination_rate"]["after"] > 0.3, d["subordination_rate"]


# ── GATE (b): faithfulness 1.0 — exact fact set; meaning-altering combinations rejected -> flat ─────
def test_gate_b_every_composed_output_is_faithful():
    """Every composed output over held-out bones is faithful and copy-complete (nothing invented)."""
    for bones in _MULTI + _RELATIVE + _VERBLESS + _SPARSE:
        comp = realize(bones, register="composed")
        g = Grounding.from_bones(bones)
        faith, fab = faithfulness(comp, g)
        assert faith == 1.0 and not fab, (bones[0][0], fab, comp)
        assert slot_copy_accuracy(bones, comp) == 1.0, (bones[0][0], comp)


def test_gate_b_content_multiset_identical_to_flat():
    """A combined surface carries the EXACT same fact set as the flat baseline — no fact added/dropped
    (the combining changes HOW, never WHAT)."""
    for bones in _MULTI + _RELATIVE:
        comp = realize(bones, register="composed")
        flat = realize(bones, register="simple")
        assert R._content_multiset(comp) == R._content_multiset(flat), bones[0][0]


def test_gate_b_gate_rejects_a_dropped_fact():
    """A constructed combination that DROPS a fact (its content multiset differs from the flat baseline)
    is rejected by the faithfulness gate."""
    bones = _MULTI[1]                                      # kettle
    g = Grounding.from_bones(bones)
    flat = realize(bones, register="simple")
    good = realize(bones, register="composed")
    assert R._accept_combined(good, flat, g) is True      # the real combined surface passes
    dropped = "Kettle, a vessel made of steel, can whistle. It is used for boiling water."   # 'spout' gone
    assert R._accept_combined(dropped, flat, g) is False   # a dropped fact -> rejected


def test_gate_b_gate_rejects_a_fabricated_word():
    """A constructed combination that FABRICATES an ungrounded content word is rejected (faithfulness
    reads < 1.0), even though the rest of the sentence is grounded."""
    bones = _MULTI[1]
    g = Grounding.from_bones(bones)
    flat = realize(bones, register="simple")
    fabricated = "Kettle, a copper vessel, can whistle and has a spout. It is used for boiling water."
    assert R._accept_combined(fabricated, flat, g) is False   # 'copper' is not grounded -> rejected


def test_gate_b_rejected_combination_falls_back_to_flat(monkeypatch):
    """WIRING: when the faithfulness gate rejects (here forced), the realizer falls back to the flat
    clause — the combined surface is never emitted unchecked."""
    bones = _MULTI[0]                                      # otter
    combined = realize(bones, register="composed")
    assert RM.appositive_rate(combined) > 0.0             # normally an appositive is adopted
    monkeypatch.setattr(R, "_accept_combined", lambda *a, **k: False)
    fell_back = realize(bones, register="composed")
    assert RM.appositive_rate(fell_back) == 0.0           # rejected -> no appositive (flat clause stands)
    assert faithfulness(fell_back, Grounding.from_bones(bones))[0] == 1.0
    assert fell_back.strip()                               # and it still answers (never empty)


def test_gate_b_never_role_swaps_subject_and_object():
    """By construction the appositive is always the subject's own is_a nominal and copy_fill preserves
    each bone's s/o roles — so the subject stays the grammatical subject, never swapped with an object."""
    comp = realize(_MULTI[1], register="composed")        # kettle / vessel
    assert comp.startswith("Kettle,")                     # kettle is the subject, vessel the appositive
    assert "a vessel" in comp and not comp.lower().startswith("vessel")


# ── GATE (c): no over-combining — sparse/verb-less answers are not forced; readability held ─────────
def test_gate_c_verbless_bones_fall_back_to_flat():
    """Purely taxonomic/descriptive bones (is_a + located_in/made_of, no promotable predicate) are NOT
    forced into a combination — they fall back to the flat clause. This is the binding constraint:
    apposition needs an action/possession predicate to promote to the main clause."""
    c = _fire(_VERBLESS)
    assert c.get("apposition", 0) == 0 and c.get("relative", 0) == 0, c
    for bones in _VERBLESS:
        comp = realize(bones, register="composed")
        assert RM.appositive_rate(comp) == 0.0 and RM.relative_clause_rate(comp) == 0.0, comp
        assert faithfulness(comp, Grounding.from_bones(bones))[0] == 1.0


def test_gate_c_sparse_answers_not_combined():
    """Single / two-fact answers are not marshalled into combinations (nothing to combine)."""
    c = _fire(_SPARSE)
    assert c.get("apposition", 0) == 0 and c.get("relative", 0) == 0, c
    assert realize([["almond", "is_a", "seed"]], register="composed") == "Almond is a seed."


def test_gate_c_readability_bound_respected():
    """No composed sentence runs on: every sentence stays within the readability word bound."""
    for bones in _MULTI + _RELATIVE + _VERBLESS + _SPARSE:
        comp = realize(bones, register="composed")
        for s in R._sentences(comp):
            assert len(re.findall(r"[A-Za-z0-9]+", s)) <= R._COMBINE_MAX_SENTENCE_WORDS, (comp, s)


def test_gate_c_fire_rate_is_measured_and_bounded():
    """Combining FIRES on rich bones and FALLS BACK on thin bones — the honest fire-rate boundary."""
    rich = _fire(_MULTI)
    combined_rich = rich.get("apposition", 0) + rich.get("relative", 0)
    assert combined_rich == sum(rich.values())            # 100% of rich multi-fact bones combine
    thin = _fire(_VERBLESS + _SPARSE)
    assert thin.get("apposition", 0) + thin.get("relative", 0) == 0   # 0% of thin bones combine


def test_gate_c_relative_clause_fires_on_its_niche():
    """The relative-clause structure is live (not dead code) on its clean niche, and stays faithful."""
    c = _fire(_RELATIVE)
    assert c.get("relative", 0) >= 2, c
    assert realize(_RELATIVE[0], register="composed") == "Mice are small rodents that can climb."
    for bones in _RELATIVE:
        assert faithfulness(realize(bones, register="composed"), Grounding.from_bones(bones))[0] == 1.0


# ── GATE (d): no surface leak — the flat registers do not combine; composed is never auto-routed ───
def test_gate_d_only_composed_has_combining_enabled():
    specs = load_registers()
    for rid in ("simple", "neutral", "explanatory", "conversational"):
        assert specs[rid].combine is False, rid
    assert specs["composed"].combine is True
    assert specs["composed"].appose_is_a is True and specs["composed"].relativize is True


def test_gate_d_flat_registers_produce_no_appositive_or_relative():
    for reg in ("simple", "neutral", "explanatory", "conversational"):
        for bones in (_MULTI[0], _MULTI[1], _ENGINE):
            t = realize(bones, register=reg)
            assert RM.appositive_rate(t) == 0.0, (reg, t)
            assert RM.relative_clause_rate(t) == 0.0, (reg, t)


def test_gate_d_composed_not_reachable_from_a_query_string():
    """The workspace surface pass passes only {"query": ...}; it must never land on composed (or any
    non-flat re-shaping register) by accident — composed is reachable only by an explicit register id."""
    specs = load_registers()
    assert select_register({"query": "Tell me about the kettle."}, specs) == "simple"
    assert select_register({"query": "explain how a heart works"}, specs) == "explanatory"
    assert select_register({"register": "composed"}, specs) == "composed"   # explicit request works


def test_gate_d_composed_register_is_data_and_round_trips():
    """composed is DATA: its combining knobs survive the default -> dict -> spec round trip."""
    spec = default_registers()["composed"]
    assert spec.combine and spec.appose_is_a and spec.relativize
    assert spec.combine_max_main == 2
