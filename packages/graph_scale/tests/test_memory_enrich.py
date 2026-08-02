# -*- coding: utf-8 -*-
"""Faint glasses memory + live web = rich recall, with remembered≠confirmed honesty."""
from packages.graph_scale.memory_enrich import enrich, _build_query


def _stub_search(query, count):
    return [
        {"title": "제네시스 G90 2026 신형 공개", "url": "https://auto.example.com/g90",
         "content": "제네시스가 신형 G90를 공개했다.", "image": "https://img.example.com/g90.jpg"},
        {"title": "모터쇼 하이라이트", "url": "https://www.news.example.com/motorshow",
         "content": "..."},
    ]


def test_enrich_fuses_faint_label_with_web_and_stays_honest():
    r = enrich("신형 제네시스", ["모터쇼", "자동차"], search=_stub_search)
    assert r["enriched"] is True
    assert r["remembered_label"] == "신형 제네시스"        # the faint part is preserved
    assert r["web_candidates"][0]["domain"] == "auto.example.com"
    assert "g90.jpg" in r["image_candidates"][0]
    assert r["render_hint"]["engine"] == "splatra"

    assert "희미하게" in r["framing"] and "확인해보니" in r["framing"]


def test_no_web_result_does_not_fabricate():
    r = enrich("존재하지않는모델", search=lambda q, c: [])
    assert r["enriched"] is False and r["web_candidates"] == []
    assert "특정하진" in r["framing"]                      # honest 'couldn't pin it down'


def test_query_uses_context_to_sharpen():
    assert "모터쇼" in _build_query("제네시스", ["모터쇼", "자동차"])
    assert _build_query("제네시스", None) == "제네시스"
