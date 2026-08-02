# -*- coding: utf-8 -*-
"""Qualia seeds 3-7/3-8 — sensory interference reception + grounded metaphor."""

from __future__ import annotations

import packages.continuous_self.sensory_interference as si
import packages.graph_scale.metaphor as met
from packages.continuous_self.self_state import SelfState


def _scene(lum=0.7, drift=0.2, palette=None):
    return {"bands": [[0.6, 0.7, 0.8]] * 3, "palette": palette or [[0.2, 0.4, 0.8]],
            "luminance": lum, "drift": drift, "measured_from": 3,
            "sources": ["http://a/1.jpg"]}


# ---- 3-7 sensory interference -------------------------------------------------
def test_impression_requires_measurement(monkeypatch):
    import packages.perception.visual_memory as vm
    monkeypatch.setattr(vm, "recall_scene", lambda c: None)
    assert si.impression_from_visual("유니콘") is None  # no wave, no impression


def test_impression_reads_wave_and_field(monkeypatch):
    import packages.perception.visual_memory as vm
    import packages.graph_scale.phase_space as ps
    monkeypatch.setattr(vm, "recall_scene", lambda c: _scene())
    monkeypatch.setattr(ps, "neighbors",
                        lambda c, k=20: [("하늘", 0.78), ("바닷물", 0.7), ("먼지", 0.2)])
    out = si.impression_from_visual("바다")
    assert out["tone"] == "차가운" and out["brightness"] == "밝은"
    evoked = [e["term"] for e in out["evoked"]]
    assert "하늘" in evoked and "먼지" not in evoked  # band-gated
    assert "바다" not in evoked
    assert "하늘" in out["felt"]  # the field answers inside the inner speech


def test_aesthetic_strike_nudges_dopamine_boundedly(monkeypatch):
    import packages.perception.visual_memory as vm
    import packages.graph_scale.phase_space as ps
    monkeypatch.setattr(vm, "recall_scene", lambda c: _scene())
    monkeypatch.setattr(ps, "neighbors", lambda c, k=20: [("하늘", 0.9)])
    s = SelfState()
    out = si.impression_from_visual("바다", state=s)
    assert out["arousal"] == 0.15
    assert s.hormones["dopamine"] == 0.15  # sensory channel only, bounded


# ---- 3-8 grounded metaphor ----------------------------------------------------
def test_metaphor_picks_cross_domain_band(monkeypatch):
    monkeypatch.setattr(met, "_kg_connected", lambda a, b: False)
    import packages.graph_scale.phase_space as ps
    monkeypatch.setattr(ps, "neighbors", lambda c, k=40: [
        ("바다거북", 0.95),   # same family (substring) -> excluded
        ("소금물", 0.94),     # above band -> synonym, excluded
        ("하늘", 0.72),       # the metaphor
        ("모래", 0.5),
    ])
    m = met.metaphor("바다")
    assert m and m["vehicle"] == "하늘" and m["resonance"] == 0.72
    assert "공명" in m["surface"]


def test_metaphor_excludes_kg_relatives_and_stays_silent(monkeypatch):
    import packages.graph_scale.phase_space as ps
    monkeypatch.setattr(ps, "neighbors", lambda c, k=40: [("하늘", 0.72)])
    monkeypatch.setattr(met, "_kg_connected", lambda a, b: True)  # taxonomic fact
    assert met.metaphor("바다") is None  # a fact is not a metaphor

    monkeypatch.setattr(ps, "neighbors", lambda c, k=40: [])
    assert met.metaphor("무명개념") is None  # unknown -> silence
