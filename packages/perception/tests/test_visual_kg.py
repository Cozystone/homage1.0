# -*- coding: utf-8 -*-
"""Visual-KG anchoring + instance matching — measured-only, honest verdicts."""

from __future__ import annotations

import packages.perception.visual_kg as vkg
from packages.perception.visual_kg import (
    anchor_visual_triples, match_instance, signature_similarity)


def _sig(bands, lum=0.5, edge=0.1):
    return {"bands": bands, "palette": [bands[0]], "luminance": lum, "edge_energy": edge}


def test_similarity_identity_and_contrast():
    sea = _sig([[0.6, 0.7, 0.8], [0.3, 0.5, 0.7], [0.2, 0.4, 0.6]], lum=0.55, edge=0.08)
    assert signature_similarity(sea, sea) == 1.0
    lava = _sig([[0.9, 0.2, 0.05], [0.8, 0.3, 0.1], [0.3, 0.05, 0.02]], lum=0.4, edge=0.3)
    assert signature_similarity(sea, lava) < 0.7


def test_match_instance_unknown_without_memory(monkeypatch):
    import packages.perception.visual_memory as vm
    monkeypatch.setattr(vm, "_load", lambda c: None)
    out = match_instance("물병A", "물병B")
    assert out["verdict"] == "unknown"
    assert out["score"] is None


def test_match_instance_same_kind(monkeypatch):
    import packages.perception.visual_memory as vm
    bottle = {"signature": _sig([[0.7, 0.75, 0.8]] * 3, lum=0.6, edge=0.05),
              "images_measured": 3}
    bottle2 = {"signature": _sig([[0.72, 0.74, 0.79]] * 3, lum=0.58, edge=0.06),
               "images_measured": 2}
    monkeypatch.setattr(vm, "_load",
                        lambda c: bottle if c == "집물병" else bottle2)
    out = match_instance("집물병", "마트물병")
    assert out["verdict"] == "same_kind"
    assert out["score"] > 0.86
    assert "honest_scope" in out  # never claims instance identity


class _FakeStore:
    def __init__(self):
        self.rows = []
        self.flushed = False

    def intern_source(self, name, url_pattern=""):
        return 7

    def add(self, s, p, o, source=None):
        self.rows.append((s, p, o, source))
        return True

    def flush(self):
        self.flushed = True


def test_anchor_writes_sourced_triples_from_measurement():
    scene = {"bands": [[0.6, 0.7, 0.9]] * 3, "palette": [[0.2, 0.35, 0.85]],
             "luminance": 0.7, "drift": 0.2,
             "sources": ["http://a/1.jpg", "http://a/2.jpg"]}
    store = _FakeStore()
    out = anchor_visual_triples("바다", scene=scene, store=store)
    assert out["stored"] == 3
    preds = {p for _, p, _ in out["triples"]}
    assert preds == {"주조색", "시각_밝기", "시각_질감"}
    trip = {(s, p, o) for s, p, o, _ in store.rows}
    assert ("바다", "주조색", "파랑") in trip
    assert ("바다", "시각_밝기", "밝음") in trip
    assert store.flushed


def test_anchor_refuses_without_measurement(monkeypatch):
    import packages.perception.visual_memory as vm
    monkeypatch.setattr(vm, "recall_scene", lambda c: None)
    out = anchor_visual_triples("유니콘")
    assert out["stored"] == 0 and out["triples"] == []  # nothing invented
