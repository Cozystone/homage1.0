# -*- coding: utf-8 -*-
"""The nonconformity adapter, tested against REAL ATANOR signal objects (not stubs).

Proves the WIRED signals are genuinely read from the real modules:
  - graph_scale.spreading_activation.spread -> ActivatedSubgraph
  - reasoning_vm.epistemic_memory.EpistemicGraph.answer
  - knowledge_acquisition.consensus.ConsensusTally/Result
  - cgsr.cgsr.referent_resonance.resonance
and that the aggregate is monotone (more doubt -> higher nonconformity), never fabricates,
and abstains on an empty signal set.
"""
from __future__ import annotations

import numpy as np

from packages.conformal_gate.nonconformity import (
    RUNG_DOUBT, SignalVector, WIRING_STATUS, from_activated_subgraph, from_cleanup_sims,
    from_consensus, from_epistemic_answer, from_referent_resonance, nonconformity,
)


def test_empty_signals_abstain_max_nonconformity():
    assert nonconformity(SignalVector()) == 1.0     # no evidence -> max doubt -> abstain


def test_recognition_ladder_is_monotone_doubt():
    order = ["KNOWN", "INHERITED", "INFERRED", "SCHEMA", "ANALOGIZED", "GUESSED", "UNKNOWN"]
    vals = [RUNG_DOUBT[r] for r in order]
    assert vals == sorted(vals)                     # strictly non-decreasing doubt up the ladder
    # nonconformity of a lone-rung signal follows the ladder
    ncs = [nonconformity(SignalVector(epistemic_rung=r)) for r in order]
    assert ncs == sorted(ncs)
    assert nonconformity(SignalVector(epistemic_rung="KNOWN")) < \
        nonconformity(SignalVector(epistemic_rung="GUESSED"))


def test_from_real_spread_object():
    """Read a REAL ActivatedSubgraph from graph_scale.spreading_activation.spread."""
    from packages.graph_scale.spreading_activation import spread
    rich = {"dog": [("dog", "is_a", "mammal"), ("dog", "is_a", "pet"), ("dog", "has_a", "tail")],
            "mammal": [("mammal", "is_a", "animal")], "pet": [("pet", "is_a", "companion")]}
    poor = {"widget": []}
    sv_rich = from_activated_subgraph(spread("dog", lambda t: rich.get(t, [])))
    sv_poor = from_activated_subgraph(spread("widget", lambda t: poor.get(t, [])))
    assert sv_rich.support_path_count > 0 and sv_rich.activation_mass > 0.0
    assert sv_poor.support_path_count == 0 and sv_poor.activation_mass == 0.0
    # richer subgraph => lower nonconformity than a dead-end anchor
    assert nonconformity(sv_rich) < nonconformity(sv_poor)


def test_from_real_epistemic_answer():
    """Read REAL EpistemicGraph.answer results across the ladder (KNOWN vs UNKNOWN)."""
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    g = EpistemicGraph(spreading=False)
    g.add_fact("dog", "sound", "bark", sources=5)      # strong KNOWN
    g.add_isa("poodle", "dog")                          # poodle inherits dog.sound
    known = from_epistemic_answer(g.answer("dog", "sound"))
    inherited = from_epistemic_answer(g.answer("poodle", "sound"))
    unknown = from_epistemic_answer(g.answer("aardvark", "sound"))
    assert known.epistemic_rung == "KNOWN" and known.graded_confidence > 0.9
    assert inherited.epistemic_rung == "INHERITED"
    assert unknown.epistemic_rung == "UNKNOWN" and unknown.graded_confidence == 0.0
    # nonconformity ordering follows epistemic quality
    assert nonconformity(known) < nonconformity(inherited) < nonconformity(unknown)


def test_from_real_consensus_object():
    """Read a REAL ConsensusResult from knowledge_acquisition.consensus.ConsensusTally."""
    from packages.knowledge_acquisition.consensus import ConsensusTally
    corroborated = ConsensusTally()
    corroborated.add("Paris", "https://en.wikipedia.org/wiki/France")
    corroborated.add("Paris", "https://www.britannica.com/place/France")
    corroborated.add("Paris", "https://data.gov/x")
    single = ConsensusTally()
    single.add("Atlantis", "https://one-blog.example/post")
    sv_multi = from_consensus(corroborated.resolve())
    sv_single = from_consensus(single.resolve())           # resolve() -> None below floor
    assert sv_multi.consensus_domains >= 2 and sv_multi.corroborated is True
    assert sv_single.consensus_domains == 0 and sv_single.corroborated is False
    assert nonconformity(sv_multi) < nonconformity(sv_single)


def test_from_real_referent_resonance():
    """Read REAL cgsr referent_resonance: same-type ~1 (low doubt) vs cross-type ~0."""
    from packages.cgsr.cgsr.referent_resonance import resonance
    same = from_referent_resonance(resonance("person", "person"))
    cross = from_referent_resonance(resonance("person", "city"))
    assert same.referent_resonance > cross.referent_resonance
    assert nonconformity(same) < nonconformity(cross)


def test_from_cleanup_sims_margin():
    """VSA cleanup: a confident decode (one high sim, rest low) -> low doubt; an ambiguous
    decode (two near-equal top sims) -> high doubt via the shrunk margin."""
    confident = from_cleanup_sims(np.array([0.95, 0.10, 0.05, -0.2]))
    ambiguous = from_cleanup_sims(np.array([0.60, 0.58, 0.10, 0.0]))
    assert confident.cleanup_margin > ambiguous.cleanup_margin
    assert nonconformity(confident) < nonconformity(ambiguous)


def test_merge_overlays_present_fields_only():
    a = SignalVector(activation_mass=1.0, support_path_count=2)
    b = SignalVector(epistemic_rung="KNOWN", support_path_count=9)
    m = a.merge(b)
    assert m.activation_mass == 1.0            # kept from a
    assert m.epistemic_rung == "KNOWN"          # added from b
    assert m.support_path_count == 9            # b overrides a (non-None)
    assert set(m.present().keys()) == {"activation_mass", "support_path_count", "epistemic_rung"}


def test_weighted_aggregation_respects_weights():
    sv = SignalVector(epistemic_rung="GUESSED", graded_confidence=0.99)
    hi_conf = nonconformity(sv, weights={"graded_confidence": 100.0, "rung": 0.0})
    hi_rung = nonconformity(sv, weights={"graded_confidence": 0.0, "rung": 100.0})
    assert hi_conf < 0.1        # dominated by the high confidence
    assert hi_rung > 0.7        # dominated by the GUESSED rung


def test_wiring_status_is_documented():
    # honesty artifact: the production answer path is explicitly marked wiring-pending
    assert "WIRING-PENDING" in WIRING_STATUS["PRODUCTION_ANSWER_PATH"]
    assert all(k.startswith("from_") or k.isupper() for k in WIRING_STATUS)


def test_subject_coverage_doubt_is_one_minus_coverage():
    """define-lane signal (membrane fix #1): subject_coverage in [0,1] (1=fully covered) contributes
    doubt = 1 - coverage, so a wrong-referent define (coverage 0.5) reads MORE doubtful than a good
    define (coverage 1.0). This is the signal that separates 'black hole' -> 'Black is a color' from
    'photosynthesis' -> 'photosynthesis is ...', which the near-constant confidence cannot."""
    full = nonconformity(SignalVector(subject_coverage=1.0))
    partial = nonconformity(SignalVector(subject_coverage=0.5))
    none = nonconformity(SignalVector(subject_coverage=0.0))
    assert full == 0.0                        # fully covered subject -> no coverage doubt
    assert abs(partial - 0.5) < 1e-9          # half covered -> 0.5 doubt
    assert none == 1.0                        # nothing covered -> max doubt
    assert full < partial < none              # monotone: less coverage = more doubt
    # a wrong-referent define (high confidence, but half the subject uncovered) is MORE doubtful
    # than a good define (high confidence, fully covered) even though confidence is identical.
    good = nonconformity(SignalVector(graded_confidence=0.9, subject_coverage=1.0))
    wrong = nonconformity(SignalVector(graded_confidence=0.9, subject_coverage=0.5))
    assert wrong > good
