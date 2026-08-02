# -*- coding: utf-8 -*-
"""Phase-coherent flow: geometry orders facts and picks connectives — content
never changes, and everything degrades to the static path without a space."""
import packages.grounded_composer.phase_flow as pf


def _fake_space(pairs):
    def resonance(a, b):
        return pairs.get((a, b), pairs.get((b, a)))
    return resonance


def test_flow_order_walks_nearest_first(monkeypatch):

    monkeypatch.setattr(pf, "_resonance", _fake_space({
        ("음료", "카페인"): 0.9, ("음료", "브라질"): 0.2, ("카페인", "브라질"): 0.1,
    }))
    lead = ("커피", "defined_as", "음료")
    rest = [("커피", "원산지", "브라질"), ("커피", "성분", "카페인")]
    out = pf.flow_order(lead, rest)
    assert [f[2] for f in out] == ["카페인", "브라질"]
    assert set(out) == set(rest)          # content untouched, order only


def test_flow_order_without_space_keeps_original(monkeypatch):
    monkeypatch.setattr(pf, "_resonance", lambda a, b: None)
    lead = ("커피", "defined_as", "음료")
    rest = [("커피", "원산지", "브라질"), ("커피", "성분", "카페인")]
    assert pf.flow_order(lead, rest) == rest


def test_connective_hint_bands(monkeypatch):
    monkeypatch.setattr(pf, "_resonance", _fake_space({
        ("a", "near"): 0.8, ("a", "far"): 0.0, ("a", "mid"): 0.35,
    }))
    assert pf.connective_hint("a", "near") == "near"
    assert pf.connective_hint("a", "far") == "far"
    assert pf.connective_hint("a", "mid") is None
    assert pf.connective_hint("a", "unknown") is None
