# -*- coding: utf-8 -*-
import importlib
from types import SimpleNamespace


def _fresh(tmp_path, monkeypatch):
    import packages.continuous_self.self_relevance as sr
    importlib.reload(sr)
    monkeypatch.setattr(sr, "_LEDGER", tmp_path / "identity_genesis.jsonl")
    return sr


def test_relevance_needs_all_three_factors(tmp_path, monkeypatch):
    sr = _fresh(tmp_path, monkeypatch)
    # a shock on ONE axis alone stays low; all three high scores high
    low = sr.compute_relevance(delta_topology=5.0, dwell=0.0, valence=0.0)
    high = sr.compute_relevance(delta_topology=3.0, dwell=3.0, valence=1.5)
    assert low < 0.1
    assert high > low
    assert high > 0.3


def test_prediction_error_raises_topology(tmp_path, monkeypatch):
    sr = _fresh(tmp_path, monkeypatch)
    calm = sr.delta_topology_from_graph(new_edges=2, touched_hub_degree=1.0, prediction_error=0.0)
    surprised = sr.delta_topology_from_graph(new_edges=2, touched_hub_degree=1.0, prediction_error=2.0)
    assert surprised > calm  # a violated expectation shakes the world model more


def test_relative_gate_and_genesis(tmp_path, monkeypatch):
    sr = _fresh(tmp_path, monkeypatch)
    state = SimpleNamespace(self_model=[])
    # a big, effortful, affect-laden event should promote and write a genesis entry
    out = sr.consider_for_self(state, label="한국어 기하학 87k", statement="위상공간 오류를 바로잡았다",
                               topic="epistemic", new_edges=87000, touched_hub_degree=40.0,
                               dwell=5.0, valence=0.9, prediction_error=1.5)
    assert out["promoted"] is True
    nar = sr.narrative()
    assert nar["count"] == 1
    assert "87k" in nar["entries"][0]["label"]
    # trivia (no effort, no affect, isolated) must NOT become part of the self
    out2 = sr.consider_for_self(state, label="수크레는 볼리비아 수도", statement="수도 사실",
                                topic="world", new_edges=1, touched_hub_degree=0.0,
                                dwell=0.1, valence=0.0)
    assert out2["promoted"] is False
