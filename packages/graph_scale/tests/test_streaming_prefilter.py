# -*- coding: utf-8 -*-
"""Streaming predictive-coding prefilter: prime the field from in-progress text,
NEVER answer, intersect concepts, and (with a cue) mask conversation time-regions.
"""
import numpy as np


def _inject(monkeypatch, terms):
    from packages.graph_scale import phase_space
    rng = np.random.default_rng(3)
    phases = rng.uniform(0, 2 * np.pi, size=(len(terms), phase_space.DIM)).astype(np.float32)
    phase_space._SPACE["phases"] = phases
    phase_space._SPACE["terms"] = terms
    phase_space._SPACE["idx"] = {t: i for i, t in enumerate(terms)}
    monkeypatch.setattr(phase_space, "_load", lambda: True)


def test_primes_focus_but_never_answers(monkeypatch):
    _inject(monkeypatch, ["사과", "엽록체", "광합성", "햇빛", "안토시아닌", "무관어", "잡음"])
    from packages.graph_scale.streaming_prefilter import prime
    r = prime("사과가 빨간 이유는 엽록체 때문일까 아니면")
    assert "answer" not in r                      # THE invariant: priming, not answering
    assert r["primed"] is True
    assert "사과" in r["focus"] and "엽록체" in r["focus"]   # both typed concepts caught
    # two focus concepts -> the intersection lens runs
    assert isinstance(r["intersection"], list)
    assert 0.0 <= r["narrowed_fraction"] <= 1.0


def test_unknown_only_text_primes_nothing(monkeypatch):
    _inject(monkeypatch, ["사과", "엽록체"])
    from packages.graph_scale.streaming_prefilter import prime
    r = prime("플린지블랏 크왁스 즐가")            # nothing known -> nothing primed
    assert r["primed"] is False and r["focus"] == [] and r["branches"] == []


def test_particle_stripping_resolves_concept_head(monkeypatch):
    _inject(monkeypatch, ["자동차", "박람회"])
    from packages.graph_scale.streaming_prefilter import prime
    r = prime("자동차는")
    assert "자동차" in r["focus"]


def test_temporal_mask_only_with_cue_and_returns_real_history(monkeypatch):
    _inject(monkeypatch, ["자동차", "박람회", "커피"])
    from packages.graph_scale.streaming_prefilter import prime
    history = [
        {"text": "우리 자동차 박람회 갔었잖아", "at": "2026-06-01T10:00:00"},
        {"text": "그날 커피도 마셨지", "at": "2026-06-01T11:00:00"},
    ]
    # no cue -> no temporal mask even with history
    assert prime("자동차", history=history)["temporal"] is None

    r = prime("우리 그때 자동차", history=history)
    assert r["temporal"] is not None
    regions = r["temporal"]["regions"]
    assert any("자동차" in reg["matched"] for reg in regions)

    assert any("박람회" in reg["concepts"] for reg in regions)
