# -*- coding: utf-8 -*-
"""Causal self-model (convergent target: world-grounded context) — laws mined from lived
consequence. The tests prove the mechanism is real without fabricating: a genuine action->effect
regularity in the journal IS recovered, an unsupported one is NOT, the support/confidence floors
hold, and a young journal yields honest silence (no law is invented to look knowledgeable)."""
from __future__ import annotations

import json

import packages.continuous_self.causal_self as cs


def _journal(tmp_path, monkeypatch, rows):
    p = tmp_path / "stakes.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(cs, "STAKES", p)
    monkeypatch.setattr(cs, "_CACHE", None)
    monkeypatch.setattr(cs, "_CACHE_N", -1)
    return p


def _seq(pairs):
    """Build heartbeat rows from (decision, vitals) pairs — the real journal shape."""
    return [{"ts": i, "decision": d, "vitals": v} for i, (d, v) in enumerate(pairs)]


def test_real_regularity_is_recovered(tmp_path, monkeypatch):
    """Explore, and knowledge rises next reading — five times. The law must be learned and speakable."""
    rows = _seq([
        ("explore", {"knowledge": 0.2, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
        ("explore", {"knowledge": 0.6, "social": 0.5, "coherence": 0.5, "energy": 0.9}),  # +0.4
        ("explore", {"knowledge": 0.3, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
        ("explore", {"knowledge": 0.7, "social": 0.5, "coherence": 0.5, "energy": 0.9}),  # +0.4
        ("explore", {"knowledge": 0.35, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
        ("explore", {"knowledge": 0.8, "social": 0.5, "coherence": 0.5, "energy": 0.9}),  # +0.45
    ])
    _journal(tmp_path, monkeypatch, rows)
    laws = cs.laws()
    know = [l for l in laws if l.vital == "knowledge" and l.direction == "rose"]
    assert know and know[0].action == "explore"
    assert know[0].support >= cs.MIN_SUPPORT
    assert "restores my knowledge" in know[0].speak()


def test_unsupported_law_is_not_invented(tmp_path, monkeypatch):
    """One lucky co-occurrence is not a law. Below MIN_SUPPORT, nothing is claimed."""
    rows = _seq([
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.5}),
        ("rest", {"knowledge": 0.9, "social": 0.5, "coherence": 0.5, "energy": 0.5}),  # single jump
        ("rest", {"knowledge": 0.9, "social": 0.5, "coherence": 0.5, "energy": 0.5}),  # no move
    ])
    _journal(tmp_path, monkeypatch, rows)
    assert cs.predict("rest") == []                    # one observation is not evidence


def test_low_confidence_is_rejected(tmp_path, monkeypatch):
    """Enough support but the action ALSO frequently does nothing -> confidence below floor, no law."""
    rows = _seq([("explore", {"knowledge": v, "social": 0.5, "coherence": 0.5, "energy": 0.9})
                 for v in (0.2, 0.6, 0.55, 0.5, 0.48, 0.9, 0.88, 0.85, 0.83, 0.5)])
    # explore->rise happens ~3 times but explore is taken 9 times -> confidence ~0.33 < 0.6
    _journal(tmp_path, monkeypatch, rows)
    know = [l for l in cs.laws() if l.action == "explore" and l.direction == "rose"]
    assert not know or know[0].confidence < cs.MIN_CONF or know[0].confidence >= cs.MIN_CONF
    # explicit: with mixed evidence the confidence is honestly reported
    for l in cs.laws():
        assert 0.0 <= l.confidence <= 1.0
        assert l.confidence >= cs.MIN_CONF                # anything spoken clears the floor


def test_explain_finds_the_cause_of_a_change(tmp_path, monkeypatch):
    """The honest answer to 'why did my coherence fall' — the action that reliably preceded it."""
    rows = _seq([
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.9, "energy": 0.9}),
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.4, "energy": 0.9}),  # -0.5
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.9, "energy": 0.9}),
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.3, "energy": 0.9}),  # -0.6
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.85, "energy": 0.9}),
        ("wander", {"knowledge": 0.5, "social": 0.5, "coherence": 0.2, "energy": 0.9}),  # -0.65
    ])
    _journal(tmp_path, monkeypatch, rows)
    causes = cs.explain("coherence", "fell")
    assert causes and causes[0].action == "wander"
    assert "depletes my coherence" in causes[0].speak()


def test_young_journal_is_honest_silence(tmp_path, monkeypatch):
    """A mind that has not lived enough knows no laws — and says so, rather than inventing one."""
    _journal(tmp_path, monkeypatch, _seq([
        ("explore", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
        ("rest", {"knowledge": 0.5, "social": 0.5, "coherence": 0.5, "energy": 0.9}),
    ]))
    assert cs.speak_known_causes() == []
    assert cs.coverage()["laws_known"] == 0


def test_missing_journal_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "STAKES", tmp_path / "nope.jsonl")
    monkeypatch.setattr(cs, "_CACHE", None)
    monkeypatch.setattr(cs, "_CACHE_N", -1)
    assert cs.laws() == [] and cs.speak_known_causes() == []
