# -*- coding: utf-8 -*-
"""Sealed gates for the CONVERSATIONAL register — the GENERATOR-side fluency lever.

Tonight's register-acquisition experiment proved the fluency JUDGE already rates conversational prose
~0.95; feeding it corpus barely moved the proxy. The bottleneck is what the realizer PRODUCES. This
register adds the missing generator capability — copula/aux CONTRACTIONS ("it is" -> "it's") and a
BOUNDED set of discourse-marker openers ("So, …", "Now, …") — governed by register-spec DATA, never by
fabricating content. The gates measure the OUTPUT with explicit register FEATURES (packages/fluency/
register_metrics.py), NOT the discriminator score (which is ~0.95 and uninformative here):

  (a) OUTPUT register shift — on HELD-OUT bones (subjects absent from fluency_v1), the conversational
      output measurably raises conversational features vs the current 'simple' realizer.
  (b) Faithfulness 1.0    — every conversational output preserves the EXACT fact set (faithfulness and
      slot-copy == 1.0); a meaning-altering surface is still caught by the (contraction-aware) scorer.
  (c) Bounded / honest    — markers are never stuffed: a sparse answer gets none, a multi-fact answer
      at most two, never one-per-sentence; no fabrication.
  (d) No-surface-leak      — the plain registers (simple/neutral/explanatory) gain NO contraction or
      marker, and a factual query never routes to conversational (the workspace path is insulated).
"""
from __future__ import annotations

from packages.fluency.conversational import contract, expand_contractions
from packages.fluency.delex import Grounding
from packages.fluency.fluency_v1 import faithfulness, slot_copy_accuracy
from packages.fluency import register_metrics as RM
from packages.fluency.realizer import realize
from packages.fluency.register import (
    APPROVED_DISCOURSE_MARKERS,
    load_registers,
    select_register,
)

_MARKERS = frozenset(m.lower() for m in APPROVED_DISCOURSE_MARKERS)

# ── HELD-OUT bones: subjects that do NOT appear in fluency_v1.tasks() ──────────────────────────────
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
    [["trombone", "is_a", "instrument"], ["trombone", "made_of", "brass"], ["trombone", "used_for", "music"],
     ["trombone", "capable_of", "slide"], ["trombone", "has_a", "mouthpiece"]],
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
]

_SPARSE = [
    [["almond", "is_a", "seed"]],
    [["harbor", "is_a", "port"], ["harbor", "located_in", "coast"]],
]

_ENGINE = [["engine", "is_a", "machine"], ["engine", "made_of", "metal"], ["engine", "used_for", "propulsion"],
           ["engine", "capable_of", "burn fuel"], ["engine", "has_a", "piston"],
           ["engine", "capable_of", "generate power"]]


def _texts(tasks, reg):
    return [realize(bones, register=reg) for bones in tasks]


def _marker_openers(text):
    return sum(1 for s in RM._sentences(text) if RM._opener_token(s) in _MARKERS)


def _content_multiset(text):
    """The multiset of CONTENT tokens (function words + discourse markers removed, contractions
    expanded) — the 'fact carriers'. Register changes function-word FORM, so this must be identical."""
    toks = [w.lower() for w in RM._PLAIN.findall(expand_contractions(text))]
    return sorted(w for w in toks if w not in RM.FUNCTION_WORDS and w not in _MARKERS)


# ── GATE (a): the OUTPUT register measurably shifts conversational ────────────────────────────────
def test_gate_a_output_register_shift_on_heldout():
    before = _texts(_MULTI, "simple")           # the CURRENT realizer
    after = _texts(_MULTI, "conversational")
    d = RM.feature_delta(before, after)

    # contractions: none before, essentially all contractible sites collapsed after
    assert d["contraction_rate"]["before"] == 0.0
    assert d["contraction_rate"]["after"] >= 0.9, d["contraction_rate"]
    assert d["contraction_count"]["before"] == 0.0
    assert d["contraction_count"]["after"] >= 1.5, d["contraction_count"]

    # discourse markers: none before, present after (bounded, so a fraction — not 1.0)
    assert d["discourse_marker_rate"]["before"] == 0.0
    assert d["discourse_marker_rate"]["after"] >= 0.2, d["discourse_marker_rate"]

    # opener variety and function-word ratio rise; lexical diversity stays ~flat (entities are fixed by
    # the bones + copy gate, so the register cannot manufacture new lexical types)
    assert d["opener_variety"]["delta"] > 0.0, d["opener_variety"]
    assert d["function_word_ratio"]["delta"] > 0.0, d["function_word_ratio"]
    assert abs(d["type_token_ratio"]["delta"]) < 0.1, d["type_token_ratio"]


def test_gate_a_shift_holds_against_neutral_too():
    """The shift is not an artifact of comparing only to 'simple': conversational contraction/marker
    features also exceed the 'neutral' register's."""
    d = RM.feature_delta(_texts(_MULTI, "neutral"), _texts(_MULTI, "conversational"))
    assert d["contraction_rate"]["delta"] > 0.5
    assert d["discourse_marker_rate"]["delta"] > 0.0


# ── GATE (b): faithfulness 1.0, exact fact set; the scorer still catches a real fabrication ────────
def test_gate_b_every_conversational_output_is_faithful():
    for bones in _MULTI + _SPARSE:
        conv = realize(bones, register="conversational")
        g = Grounding.from_bones(bones)
        faith, fab = faithfulness(conv, g)
        assert faith == 1.0 and not fab, (bones[0][0], fab, conv)
        assert slot_copy_accuracy(bones, conv) == 1.0, (bones[0][0], conv)


def test_gate_b_factset_identical_to_literal():
    """Register changes HOW, never WHAT: the content-token multiset of the conversational surface equals
    the plain 'simple' surface's — no fact added, dropped, or changed."""
    for bones in _MULTI + _SPARSE:
        assert _content_multiset(realize(bones, register="conversational")) == \
               _content_multiset(realize(bones, register="simple")), bones[0][0]


def test_gate_b_demonym_capital_survives_conversational():
    conv = realize(_MULTI[-1], register="conversational")     # espresso / Italian
    assert "Italian" in conv                                  # demonym capital preserved, not fabricated
    assert faithfulness(conv, Grounding.from_bones(_MULTI[-1]))[0] == 1.0


def test_gate_b_contraction_aware_scorer_still_catches_fabrication():
    """The faithfulness scorer expands contractions before scoring; prove that did NOT blind it — an
    ungrounded CONTENT word in a contracted sentence is still flagged."""
    g = Grounding.from_bones([["coffee", "is_a", "beverage"]])
    faith, fab = faithfulness("It's a beverage, and it's made of cheese.", g)
    assert faith < 1.0 and "cheese" in fab


# ── GATE (c): bounded / honest — markers are never stuffed ─────────────────────────────────────────
def test_gate_c_sparse_answers_get_no_markers():
    for bones in _SPARSE:
        conv = realize(bones, register="conversational")
        assert RM.discourse_marker_present(conv) is False, conv     # short answers are not marker-stuffed
        assert faithfulness(conv, Grounding.from_bones(bones))[0] == 1.0


def test_gate_c_markers_are_bounded_on_multifact():
    for bones in _MULTI:
        conv = realize(bones, register="conversational")
        n_sents = len(RM._sentences(conv))
        marked = _marker_openers(conv)
        assert marked <= 2, (conv, marked)                          # at most two per subject block
        assert marked < n_sents, (conv, marked, n_sents)            # never one-on-every-sentence


def test_gate_c_single_fact_only_contracts_where_it_fits():
    conv = realize([["almond", "is_a", "seed"]], register="conversational")
    assert conv == "Almond's a seed."                               # one natural contraction, no marker


# ── GATE (d): no surface leak into the plain registers; factual queries never route here ───────────
def test_gate_d_plain_registers_get_no_contraction_or_marker():
    for reg in ("simple", "neutral", "explanatory"):
        t = realize(_ENGINE, register=reg)
        assert "'" not in t, (reg, t)                               # no contraction clitic
        assert _marker_openers(t) == 0, (reg, t)                    # no conversational marker opener


def test_gate_d_conversational_not_reachable_from_a_query_string():
    specs = load_registers()
    # the workspace surface pass passes only {"query": ...}; it must never land on conversational
    assert select_register({"query": "Tell me about the engine."}, specs) == "simple"
    assert select_register({"query": "explain how a heart works"}, specs) == "explanatory"
    # conversational is reachable only by an explicit casual audience/intent
    assert select_register({"audience": "friend"}, specs) == "conversational"
    assert select_register({"intent": "chat"}, specs) == "conversational"


def test_contract_touches_only_function_words():
    """contract() rewrites function words only, so expand(contract(x)) restores the content exactly."""
    for bones in _MULTI:
        plain = realize(bones, register="simple")
        assert _content_multiset(plain) == _content_multiset(contract(plain))


# ── the register is DATA-driven, and the closed-vocabulary gate filters unapproved markers ─────────
def test_conversational_register_is_data_and_gated():
    specs = load_registers()
    assert "conversational" in specs
    conv = specs["conversational"]
    assert conv.contractions is True
    assert conv.aggregate_reduced is False
    assert set(conv.discourse_marker_pool) <= set(APPROVED_DISCOURSE_MARKERS)
    # the closed-vocab gate strips an unapproved marker (register data cannot inject free text)
    from packages.fluency.register import RegisterSpec
    smuggled = RegisterSpec(id="x", description="", discourse_marker_pool=("So", "OBVIOUSLY_FAKE"))
    assert smuggled.filtered().discourse_marker_pool == ("So",)
