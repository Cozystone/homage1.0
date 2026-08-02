# -*- coding: utf-8 -*-
"""Causal fuel — the intake that cures the HOT-3 belief-formation starvation, proven honest.

The tests pin the no-fabrication doctrine on the promotion machinery:
  * a candidate with >= MIN_SUPPORT INDEPENDENT corroboration PROMOTES with a certificate naming its
    evidence — via lived transitions, via >= MIN_SUPPORT distinct wild-web domains, and via the two
    COMBINING;
  * a single-source candidate does NOT promote (one lived observation; one wild-web domain) — it stays
    a hypothesis;
  * a support-below-threshold candidate (2 distinct domains, MIN_SUPPORT=3) does NOT promote;
  * a lived tendency with enough support but NO dominant direction is NOT claimed as a law;
  * every promoted law's certificate support equals its real evidence count — no bridge is invented;
  * coverage() now reports the held laws so the HOT-3 loop is fed, and stays 0 on a young journal.
"""
from __future__ import annotations

import json

import packages.continuous_self.causal_self as cs
import packages.continuous_self.causal_fuel as cf
from packages.wild_web import store as wild_store


# ──────────────────────────────────────────────────────────────────── fixtures
def _lived(tmp_path, monkeypatch, pairs):
    """Write a stakes journal from (decision, vitals) pairs and point causal_self at it."""
    rows = [{"ts": i, "decision": d, "vitals": v} for i, (d, v) in enumerate(pairs)]
    p = tmp_path / "stakes.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(cs, "STAKES", p)
    monkeypatch.setattr(cs, "_CACHE", None)
    monkeypatch.setattr(cs, "_CACHE_N", -1)
    return p


def _wildweb(tmp_path, monkeypatch, edges):
    """Isolate wild_web persistence to a tmp dir and seed causal candidates.
    edges: list of (cause, effect, source_url)."""
    d = tmp_path / "wild"
    monkeypatch.setattr(wild_store, "DATA_DIR", d)
    for cause, effect, url in edges:
        wild_store.add_causal(cause, effect, url)
    return d


def _empty_wildweb(tmp_path, monkeypatch):
    monkeypatch.setattr(wild_store, "DATA_DIR", tmp_path / "wild_empty")


# ──────────────────────────────────────────────────────────────────── lived route
def test_lived_regularity_promotes_with_certificate(tmp_path, monkeypatch):
    """Conversing depletes energy, five moves, always downward -> a held law with a lived certificate."""
    _empty_wildweb(tmp_path, monkeypatch)
    # converse always precedes an energy DROP; the recovery happens on a different action ('rest'),
    # so converse's own transitions are cleanly downward (the shape the real journal has at scale).
    _lived(tmp_path, monkeypatch, [
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.55}),      # converse -0.35
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),  # rest +0.35
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.52}),      # converse -0.38
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),  # rest +0.38
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),      # converse -0.40
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),  # rest +0.40
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.53}),      # converse -0.37
    ])
    laws = cf.promoted_laws()
    e = [c for c in laws if c.cause == "converse" and c.direction == "fell"]
    assert e, "a strong lived directional regularity must be promoted"
    law = e[0]
    assert law.support >= cf.MIN_SUPPORT
    assert law.evidence_type == "lived"
    assert "depletes my energy" in law.speak()
    cert = law.certificate()
    assert cert["cause"] == "converse" and cert["effect"] == "energy fell"
    assert cert["support"] == law.support
    assert cert["sources"] and cert["sources"][0]["type"] == "lived"
    assert cert["directional_confidence"] >= cf.MIN_CONF


def test_single_lived_observation_does_not_promote(tmp_path, monkeypatch):
    """One lucky co-occurrence is not a law (support 1 < MIN_SUPPORT) -> stays a hypothesis."""
    _empty_wildweb(tmp_path, monkeypatch)
    _lived(tmp_path, monkeypatch, [
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.5}),
        ("rest", {"knowledge": 0.9, "social": 0.5, "coherence": 0.5, "energy": 0.5}),   # single jump
        ("rest", {"knowledge": 0.9, "social": 0.5, "coherence": 0.5, "energy": 0.5}),   # no move
    ])
    assert not [c for c in cf.promoted_laws() if c.cause == "rest"]
    pend = [c for c in cf.pending_hypotheses() if c.cause == "rest"]
    assert pend and pend[0].support < cf.MIN_SUPPORT


def test_non_directional_tendency_is_not_claimed(tmp_path, monkeypatch):
    """Enough moves but no dominant direction (rises == falls) -> no law is invented."""
    _empty_wildweb(tmp_path, monkeypatch)
    _lived(tmp_path, monkeypatch, [
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.50, "energy": 0.9}),
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.90, "energy": 0.9}),  # +0.40
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.50, "energy": 0.9}),  # -0.40
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.90, "energy": 0.9}),  # +0.40
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.50, "energy": 0.9}),  # -0.40
    ])
    assert not [c for c in cf.promoted_laws() if c.cause == "wander"]


# ──────────────────────────────────────────────────────────────────── wild-web route
def test_wildweb_promotes_only_on_min_support_distinct_domains(tmp_path, monkeypatch):
    """The SAME normalized cause->effect from MIN_SUPPORT distinct domains -> promoted (external
    convergence); the sources are the distinct domains, no lived component, no fabrication."""
    _lived(tmp_path, monkeypatch, [("idle", {"knowledge": 0.5, "social": 0.5,
                                             "coherence": 0.5, "energy": 0.5})])  # no lived laws
    _wildweb(tmp_path, monkeypatch, [
        ("heavy rain", "flooding", "https://a-weather.com/x"),
        ("heavy rain", "flooding", "https://b-news.org/y"),
        ("Heavy rain.", "Flooding", "https://c-forum.net/z"),   # normalizes to the same edge
    ])
    laws = cf.promoted_laws()
    e = [c for c in laws if c.cause == "heavy rain" and c.effect == "flooding"]
    assert e, "an edge attested by >= MIN_SUPPORT distinct domains must promote"
    law = e[0]
    assert law.evidence_type == "wild_web"
    assert len(law.wild_domains) >= cf.MIN_SUPPORT
    cert = law.certificate()
    assert cert["support"] == len(law.wild_domains)
    assert all(s["type"] == "wild_web" for s in cert["sources"])


def test_single_domain_wildweb_stays_hypothesis(tmp_path, monkeypatch):
    """One domain repeated (even many times / many URLs) is ONE source — never a fact by itself."""
    _lived(tmp_path, monkeypatch, [("idle", {"knowledge": 0.5, "social": 0.5,
                                             "coherence": 0.5, "energy": 0.5})])
    _wildweb(tmp_path, monkeypatch, [
        ("secret trick", "instant success", "https://oneblog.com/a"),
        ("secret trick", "instant success", "https://oneblog.com/b"),
        ("secret trick", "instant success", "https://oneblog.com/c"),
    ])
    assert not cf.promoted_laws(), "a single-domain hypothesis must not promote"
    pend = cf.pending_hypotheses()
    assert pend and pend[0].support == 1 and len(pend[0].wild_domains) == 1


def test_two_domains_below_threshold_do_not_promote(tmp_path, monkeypatch):
    """Two distinct domains (support 2) is below MIN_SUPPORT=3 -> stays hypothesis (no fabrication)."""
    _lived(tmp_path, monkeypatch, [("idle", {"knowledge": 0.5, "social": 0.5,
                                             "coherence": 0.5, "energy": 0.5})])
    _wildweb(tmp_path, monkeypatch, [
        ("late nights", "fatigue", "https://one.com/x"),
        ("late nights", "fatigue", "https://two.org/y"),
    ])
    assert not cf.promoted_laws()
    pend = [c for c in cf.pending_hypotheses() if c.cause == "late nights"]
    assert pend and pend[0].support == 2


# ──────────────────────────────────────────────────────────────────── combined corroboration
def test_lived_plus_wildweb_combine_to_promote(tmp_path, monkeypatch):
    """Two lived observations + one independent wild-web domain = 3 independent observations -> the
    unified count clears the bar, and the certificate names BOTH evidence types (corroborated)."""
    _lived(tmp_path, monkeypatch, [
        ("exercise", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),
        ("exercise", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),  # +0.40
        ("exercise", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),
        ("exercise", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.88}),  # +0.38
    ])  # lived_support = 2 (two rises), directionally consistent, but < MIN_SUPPORT on its own
    assert not [c for c in cf.promoted_laws() if c.cause == "exercise"], "2 lived alone must not promote"
    _wildweb(tmp_path, monkeypatch, [("exercise", "energy rose", "https://fitness-site.com/p")])
    laws = cf.promoted_laws()
    e = [c for c in laws if c.cause == "exercise"]
    assert e, "2 lived + 1 distinct domain must reach MIN_SUPPORT and promote"
    law = e[0]
    assert law.support == 3
    assert law.evidence_type == "corroborated"
    types = {s["type"] for s in law.certificate()["sources"]}
    assert types == {"lived", "wild_web"}


# ──────────────────────────────────────────────────────────────────── no-fabrication invariant
def test_no_promoted_law_exceeds_its_evidence(tmp_path, monkeypatch):
    """Every promoted law's support equals the real count of its sources — nothing is bridged."""
    _lived(tmp_path, monkeypatch, [
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.5}),   # converse fell
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),  # rest rose
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.5}),   # converse fell
        ("converse", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),  # rest rose
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.5}),   # converse fell
    ])
    _wildweb(tmp_path, monkeypatch, [
        ("heavy rain", "flooding", "https://a.com/x"),
        ("heavy rain", "flooding", "https://b.com/y"),
        ("heavy rain", "flooding", "https://c.com/z"),
    ])
    for law in cf.promoted_laws():
        cert = law.certificate()
        lived = sum(s.get("observations", 0) for s in cert["sources"] if s["type"] == "lived")
        domains = len({s["domain"] for s in cert["sources"] if s["type"] == "wild_web"})
        assert cert["support"] == lived + domains, cert
        assert cert["support"] >= cf.MIN_SUPPORT
        assert law.promotes()


def test_all_real_wildweb_candidates_stay_hypotheses(tmp_path, monkeypatch):
    """Against the REAL wild-web data (single-domain, all distinct sourdough edges) nothing promotes —
    the honest baseline: wild-web hypotheses alone are correctly un-promoted."""
    _lived(tmp_path, monkeypatch, [("idle", {"knowledge": 0.5, "social": 0.5,
                                             "coherence": 0.5, "energy": 0.5})])
    # do NOT monkeypatch wild_store.DATA_DIR -> reads the real repo candidates
    for law in cf.promoted_laws():
        assert law.evidence_type != "wild_web", f"a wild-web-only law promoted unexpectedly: {law.certificate()}"


# ──────────────────────────────────────────────────────────────────── coverage / HOT-3 wiring
def test_coverage_reports_held_laws_from_fuel(tmp_path, monkeypatch):
    """coverage() feeds the HOT-3 loop: a strong lived regularity makes laws_known > 0."""
    _empty_wildweb(tmp_path, monkeypatch)
    # run always precedes an energy RISE; the fall-back happens on 'rest' -> run's transitions are
    # cleanly upward (support 4, directional confidence 1.0).
    _lived(tmp_path, monkeypatch, [
        ("run", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),   # run +0.40
        ("run", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),    # rest -0.40
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.92}),   # run +0.42
        ("run", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),    # rest -0.42
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.91}),   # run +0.41
        ("run", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.50}),    # rest -0.41
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.90}),   # run +0.40
    ])
    cov = cs.coverage()
    assert cov["transitions_observed"] > 0
    assert cov["laws_known"] > 0
    assert cov["laws_known"] == cov["laws_promoted"]
    assert cov["promoted_from_lived"] >= 1
    assert cs.speak_held_laws(), "held laws should be speakable"


def test_coverage_young_journal_holds_no_law(tmp_path, monkeypatch):
    """A mind that has not lived enough holds no law — laws_known stays 0 (honest silence)."""
    _empty_wildweb(tmp_path, monkeypatch)
    _lived(tmp_path, monkeypatch, [
        ("explore", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
    ])
    cov = cs.coverage()
    assert cov["laws_known"] == 0
    assert cf.promoted_laws() == []
    assert cs.speak_held_laws() == []
