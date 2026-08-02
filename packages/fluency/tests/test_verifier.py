# -*- coding: utf-8 -*-
"""The fluency VERIFIER — a calibrated naturalness judge that is honestly a PROXY, designed against
Goodharting.

These tests pin the four load-bearing claims:
  * the LEARNED discriminator separates natural from stiff/template on a held-out split (>= 0.8; an
    HONEST proxy number, not a human-truth number);
  * the STRUCTURAL hard-checks (agreement / run-on / repetition / punctuation) fire and cap the score;
  * the FROZEN human anchor ranks better>worse (>= 0.9), and CATCHES a proxy-gaming candidate whose
    learned number would rise while human agreement falls (Goodharting);
  * the verifier is registered in the neuro ledger as a tiny, not-a-fact-source organ within budget.
"""
from __future__ import annotations

import json

import pytest

from packages.fluency import verifier as V


# ── the learned discriminator (HONEST PROXY) ──────────────────────────────────────────────────────
def test_discriminator_holdout_at_least_0_8_honest_proxy():
    """Holdout accuracy on the deterministic content-hash split is a PROXY (natural vs stiff FEATURES,
    not human truth) and must clear 0.8. Reported honestly by train_and_save."""
    rep = V.train_and_save(save=True)
    assert rep["holdout_accuracy"] >= 0.8, rep
    assert "PROXY" in rep["proxy_caveat"]
    assert rep["n_holdout"] >= 20                     # the holdout is not a token handful


def test_training_is_deterministic():
    """No RNG / no shuffling — the same corpus yields identical weights, so the audit and the anchor
    contract are reproducible."""
    V.train_and_save(save=True)
    m1 = V.load_model(force_reload=True)
    V.train_and_save(save=True)
    m2 = V.load_model(force_reload=True)
    assert m1.weights == m2.weights and m1.bias == m2.bias


def test_natural_outscores_stiff_on_the_learned_layer():
    natural = "The bridge was closed for repairs, so we took the long way around the lake."
    stiff = "The river is a waterway, and can flow, and is used for transport, and has a current."
    assert V.learned_score(natural) > V.learned_score(stiff)
    assert V.learned_score(natural) >= 0.5 > V.learned_score(stiff)


def test_score_is_bounded_and_empty_is_zero():
    for s in ("The soup needs an hour and almost no attention.",
              V.GAMED_SENTENCE, "Iron is a metal. Iron is hard.", "x"):
        assert 0.0 <= V.score(s) <= 1.0
    assert V.score("") == 0.0
    assert V.score("   ") == 0.0


# ── the structural hard-checks (rule floor) ───────────────────────────────────────────────────────
def test_structural_check_fires_on_run_on():
    runon = ("The design is elegant and efficient, but powerful, so fast, yet robust, "
             "while scalable, and cheap.")
    chk = V.structural_checks(runon)
    assert "run_on" in chk["violations"] and chk["no_run_on"] is False
    assert V.structural_multiplier(runon) < 1.0


def test_structural_check_fires_on_immediate_repetition():
    chk = V.structural_checks("The the engine hums quietly at night.")
    assert "immediate_repetition" in chk["violations"]
    assert chk["no_immediate_repetition"] is False


def test_structural_check_fires_on_agreement_error():
    chk = V.structural_checks("They is a group of birds.")
    assert "agreement" in chk["violations"] and chk["agreement_ok"] is False


def test_structural_check_fires_on_unclosed_punctuation():
    chk = V.structural_checks("the engine hums quietly at night")   # no terminal punctuation
    assert "unclosed_punctuation" in chk["violations"]
    assert chk["closed_punctuation"] is False


def test_clean_natural_sentence_passes_every_structural_check():
    chk = V.structural_checks("The garden needs weeding, but the tomatoes are finally red.")
    assert chk["ok"] is True and chk["violations"] == []
    assert V.structural_multiplier("The garden needs weeding, but the tomatoes are finally red.") == 1.0


def test_structural_floor_caps_a_high_learned_score():
    """A run-on can score high on the learned layer, but the structural floor multiplies it down —
    the 0-clamp doctrine: structure caps the proxy."""
    runon = V.GAMED_SENTENCE
    assert V.learned_score(runon) > V.score(runon)           # the gate strictly reduced it
    assert V.score(runon) <= V.structural_multiplier(runon) * V.learned_score(runon) + 1e-9


# ── the frozen human anchor (anti-Goodhart tether) ────────────────────────────────────────────────
def test_anchor_has_twenty_frozen_pairs():
    assert len(V.ANCHOR_PAIRS) >= 20
    for better, worse in V.ANCHOR_PAIRS:
        assert isinstance(better, str) and isinstance(worse, str) and better != worse


def test_anchor_ranking_agreement_at_least_0_9():
    res = V.verify_against_anchor()
    assert res["agreement"] >= 0.9, res["mismatches"]
    assert res["passes_floor"] is True
    assert res["n_pairs"] == len(V.ANCHOR_PAIRS)


def test_anchor_catches_a_proxy_gaming_candidate():
    """THE Goodhart guard at the anchor layer: a candidate scorer that games a naive proxy ('more
    connectives = more fluent') scores the stiff run-on WORSE items above the natural BETTER items, so
    its anchor agreement collapses below the floor. Doctrine: reject such a retrain, never promote it —
    even if its learned proxy number went up."""
    def gaming_candidate(s: str) -> float:
        # rewards raw connective count — exactly the metric a run-on template maximizes
        return min(1.0, len(V._connectives_in(s)) / 5.0)

    gamed = V.verify_against_anchor(gaming_candidate)
    honest = V.verify_against_anchor()               # the real verifier
    assert gamed["agreement"] < V.ANCHOR_AGREEMENT_FLOOR
    assert gamed["passes_floor"] is False
    assert honest["agreement"] >= V.ANCHOR_AGREEMENT_FLOOR      # the real one still tracks humans


# ── the proxy-gaming SENTENCE is caught even though it fools the learned score ─────────────────────
def test_gamed_sentence_fools_learned_but_is_caught():
    """Task-critical: a keyword/connective-stuffed sentence FOOLS the learned score (>= 0.5) yet is
    CAUGHT — the structural run-on floor drops the final verdict below the fluent threshold."""
    g = V.GAMED_SENTENCE
    assert V.learned_score(g) >= 0.5                 # fools the learned discriminator
    assert "run_on" in V.structural_checks(g)["violations"]     # structural catch fires
    assert V.score(g) < 0.5                          # final verdict is low despite the high learned score


def test_goodhart_guard_demo_reports_caught():
    demo = V.goodhart_guard_demo()
    assert demo["caught"] is True
    assert demo["learned_score"] >= 0.5              # was fooled
    assert demo["final_score"] < 0.5                 # but the final verdict is low
    assert demo["final_score"] < demo["natural_final_score"]    # ranked below the honest counterpart
    assert "run_on" in demo["structural_violations"]


# ── weights persistence ───────────────────────────────────────────────────────────────────────────
def test_weights_persist_as_json_floats():
    V.train_and_save(save=True)
    assert V.WEIGHTS_PATH.exists()
    data = json.loads(V.WEIGHTS_PATH.read_text(encoding="utf-8"))
    for key in ("weights", "bias", "mean", "std", "feature_names"):
        assert key in data
    assert len(data["weights"]) == len(V.FEATURE_NAMES)
    assert data["feature_names"] == list(V.FEATURE_NAMES)


# ── self-evolution integration surface (importable; does NOT edit self_evolution) ─────────────────
def test_evolution_descriptor_flags_proxy_evolvable_anchored():
    d = V.evolution_descriptor()
    assert d["domain"] == "fluency"
    assert d["status"] == "proxy-evolvable-anchored"
    assert d["is_autonomous_safe"] is False          # naturalness has no ground-truth oracle
    assert d["needs_human_anchor"] is True
    assert d["anchor_agreement_floor"] == V.ANCHOR_AGREEMENT_FLOOR


def test_exposed_verifier_callables_resolve_by_dotted_ref():
    """The descriptor names its verifier as 'pkg.mod:attr' strings; those must import (this is exactly
    what the self_evolution registry's attr-probe would resolve, without us editing that file)."""
    import importlib
    d = V.evolution_descriptor()
    for ref in (d["verifier"], d["anchor_verifier"], d["structural_verifier"]):
        mod, _, attr = ref.partition(":")
        m = importlib.import_module(mod)
        assert callable(getattr(m, attr)), ref


def test_module_level_flags_are_honest():
    assert V.IS_AUTONOMOUS_SAFE is False
    assert V.NEEDS_HUMAN_ANCHOR is True
    assert V.EVOLVED_STATUS == "proxy-evolvable-anchored"


# ── neuro ledger registration within budget ───────────────────────────────────────────────────────
def test_verifier_registered_in_neuro_ledger_within_budget():
    from packages.neuro_ledger.ledger import load_ledger, measure_params, SINGLE_ORGAN_MAX
    organ = {o.id: o for o in load_ledger()}.get("fluency_verifier")
    assert organ is not None, "fluency_verifier not registered in the neuro ledger"
    assert organ.fact_source is False                # a learned organ is never a fact source
    m = measure_params(organ)
    assert 0 < m["params"] <= SINGLE_ORGAN_MAX       # tiny, within the single-organ cap
    assert m["params"] < 1000                        # a genuinely small logistic (not an LLM)


def test_neuro_ledger_audit_stays_green_with_the_verifier():
    from packages.neuro_ledger.audit import run_audit
    card = run_audit(write=False)
    assert card["green"] is True, card["violations"]
    ids = {o["id"] for o in card["organs"]}
    assert "fluency_verifier" in ids
