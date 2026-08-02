# -*- coding: utf-8 -*-
"""Viability (B6, intentionality v0): worry grounded in what can actually be lost — the referential
grounding that makes wanting ABOUT something, measured now, never invented."""
import json

from packages.live_selfhood_cycle.viability import (
    _memory_integrity, sense_viability, viability_concerns)


def test_every_signal_is_measured_with_evidence():
    sigs = sense_viability()
    keys = {s["signal"] for s in sigs}
    assert {"memory_of_living", "knowledge_substrate", "ability_to_act",
            "room_to_live", "capability_selfhood"} <= keys
    for s in sigs:
        assert 0.0 <= s["threat"] <= 1.0 and s["evidence"]     # a real reason, not a label


def test_corrupt_memory_raises_a_real_threat(tmp_path, monkeypatch):
    import packages.live_selfhood_cycle.viability as v
    bad = tmp_path / "life.jsonl"
    bad.write_text("\n".join(["{\"ok\": 1}"] * 5 + ["{not json"] * 10), encoding="utf-8")
    monkeypatch.setattr(v, "LIFE_STREAM", bad)
    m = v._memory_integrity()
    assert m["threat"] > 0.3 and "corrupt" in m["evidence"]     # worry names the real failure


def test_concerns_are_sorted_worst_first_and_thresholded():
    cs = viability_concerns(min_threat=0.0)
    threats = [c["threat"] for c in cs]
    assert threats == sorted(threats, reverse=True)


def test_it_becomes_a_survival_concern_in_the_beat(tmp_path, monkeypatch):
    """A viability threat enters the living beat as a high-urgency concern that moves cortisol
    (survival stress) — not a self-improvement wish."""
    import packages.live_selfhood_cycle.viability as v
    monkeypatch.setattr(v, "LIFE_STREAM", tmp_path / "missing.jsonl")   # -> memory threat
    from packages.live_selfhood_cycle.living_beat import _interoception
    from packages.temporal_reasoning.unified_timeline import Timeline
    concerns = _interoception(Timeline(path=tmp_path / "tl.jsonl"))
    viab = [c for c in concerns if c.meta.get("viability_threat")]
    assert viab and viab[0].urgency >= 0.55
    assert "lose" in viab[0].content
