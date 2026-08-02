# -*- coding: utf-8 -*-
from packages.autonomy_kernel import goals as G


def test_goal_forms_from_recurring_deficit_and_tracks_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "_GOALS", tmp_path / "goals.json")

    seq = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(G, "_read_metric", lambda name: next(seq, 300.0))
    G.update({"speech_weak"})               # recurring deficit → goal formed
    G.update({"speech_weak"})
    book = G.update({"speech_weak"})
    g = book["speech_weak"]
    assert g["metric"] == "discourse_sentences" and g["target"] == 300
    assert len(g["history"]) == 3
    assert g["status"] == "achieved"         # hit the target → the self knows it


def test_metacognition_reports_focus_and_stays_honest(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "_GOALS", tmp_path / "goals.json")
    monkeypatch.setattr(G, "_read_metric", lambda name: 0.5)  # below the 0.75 router target
    G.update({"router_immature"})
    m = G.metacognition()
    assert m["self_report"] and "focus_now" in m
    # never overclaims — the honest note explicitly denies consciousness
    assert "의식이 아니라" in m["honest_note"]


def test_regressing_metric_is_caught(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "_GOALS", tmp_path / "goals.json")
    seq = iter([200.0, 180.0, 150.0, 120.0, 100.0])  # moving AWAY from 300
    monkeypatch.setattr(G, "_read_metric", lambda name: next(seq, 100.0))
    for _ in range(5):
        G.update({"speech_weak"})
    assert G._load()["speech_weak"]["status"] == "regressing"  # the self notices it's slipping
