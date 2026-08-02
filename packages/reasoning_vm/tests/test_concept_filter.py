# -*- coding: utf-8 -*-
"""concept_filter mechanics tests — the parts E10-D1 did NOT refute.

D1 refuted trusting the symbolic contradiction scorer over lexically-retrieved passages
(triple red; see module docstring). It did not refute the INTERFACE mechanics these tests
pin down: verdict plumbing, negated-stem inversion, unknown-domain silence, open-world
protection. The E9 encoder drops into eliminate() behind this same tested surface.
"""
from __future__ import annotations

from packages.reasoning_vm.concept_filter import (Verdict, apply_verdicts, contradiction_reasons,
                                                  eliminate, expected_category, stem_is_negated)


def test_unknown_domain_is_silent_not_fabricated():
    """No evidence + no graph → every option no-verdict → action 'none' (honest fallback)."""
    ch = {"A": "quantum flux widgets", "B": "temporal shear pumps", "C": "x", "D": "y"}
    verd = eliminate("Which frobnicator stabilises the manifold?", ch, [])
    assert all(not v.eliminated for v in verd.values())
    assert apply_verdicts("Which frobnicator stabilises the manifold?", ch, verd)["action"] == "none"


def test_polarity_flip_detected_and_negation_folds_in():
    # evidence says A INCREASES B; the option claims the flip via explicit negation
    rs = contradiction_reasons("caffeine does not increase heart rate",
                               "Caffeine increases heart rate in most adults.")
    assert any("polarity" in r for r in rs)
    # agreeing statement → no polarity reason
    assert not any("polarity" in r for r in
                   contradiction_reasons("caffeine increases heart rate",
                                         "Caffeine increases heart rate in most adults."))


def test_number_mismatch_detected():
    rs = contradiction_reasons("humans have 46 pairs of chromosomes",
                               "Humans have 23 pairs of chromosomes.")
    assert any("number" in r for r in rs)


def test_negated_stem_inverts_single_contradiction_into_pick():
    """'Which is NOT …' + exactly one contradicted option → that option IS the answer."""
    stem = "Which of the following is NOT true about caffeine?"
    assert stem_is_negated(stem)
    ch = {"A": "opt a", "B": "opt b", "C": "opt c", "D": "opt d"}
    verd = {k: Verdict(key=k) for k in ch}
    verd["C"].eliminated, verd["C"].reasons = True, ["polarity flip vs evidence"]
    act = apply_verdicts(stem, ch, verd)
    assert act["action"] == "pick" and act["choice_key"] == "C" and act["mode"] == "eliminated"


def test_sole_survivor_pick_and_restrict():
    stem = "Which of the following describes the process?"
    ch = {"A": "a", "B": "b", "C": "c"}
    verd = {k: Verdict(key=k) for k in ch}
    verd["A"].eliminated, verd["A"].reasons = True, ["number mismatch (1 vs 2)"]
    act = apply_verdicts(stem, ch, verd)                    # one eliminated → restrict
    assert act["action"] == "restrict" and sorted(act["survivors"]) == ["B", "C"]
    verd["B"].eliminated, verd["B"].reasons = True, ["role transposition (x/y reversed)"]
    act2 = apply_verdicts(stem, ch, verd)                   # two eliminated → sole survivor
    assert act2["action"] == "pick" and act2["choice_key"] == "C"
    verd["C"].eliminated = True                             # everything contradicted = noise
    assert apply_verdicts(stem, ch, verd)["action"] == "none"


def test_graph_positive_protection_open_world():
    """A graph-CONFIRMED category match protects an option; graph silence never eliminates."""
    stem = "Which of the following is a mammal, according to the passage?"
    assert expected_category(stem) == "mammal"
    ch = {"A": "whale shark species", "B": "blue whale species"}
    evidence = ["Blue whale species never live on land."]   # would trip polarity on B
    verd = eliminate(stem, ch, evidence,
                     facts_about=lambda t: [],
                     verify=lambda s, p, o, fa: s == "blue whale species" and o == "mammal")
    assert verd["B"].protected and not verd["B"].eliminated
