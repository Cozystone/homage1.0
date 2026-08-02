from __future__ import annotations

import app.services.comparison_reasoner as cr


def test_detect_korean_comparison():
    plan = cr.detect_comparison("아인슈타인과 뉴턴 중 누가 먼저 태어났어?")
    assert plan and plan["a"] == "아인슈타인" and plan["b"] == "뉴턴"
    assert plan["attribute"] == "birth_year" and plan["direction"] == "min"


def test_detect_english_comparison():
    plan = cr.detect_comparison("which is older, Einstein or Newton")
    assert plan and plan["attribute"] == "birth_year" and plan["direction"] == "min"
    assert {plan["a"].lower(), plan["b"].lower()} == {"einstein", "newton"}


def test_non_comparison_returns_none():
    assert cr.detect_comparison("아인슈타인이 누구야") is None
    assert cr.detect_comparison("중력이 뭐야") is None


def test_birth_year_extraction():
    assert cr._extract_birth_year("아인슈타인(1879년 3월 14일 ~ 1955년)은 물리학자이다.") == 1879
    assert cr._extract_birth_year("Isaac Newton (4 January 1643 – 31 March 1727) was a physicist.") == 1643


def test_answer_comparison_born_first(monkeypatch):
    fixtures = {
        "아인슈타인": {"title": "알베르트 아인슈타인", "snippet": "알베르트 아인슈타인(1879년 3월 14일~1955년)은 이론물리학자이다.", "url": "https://ko.wikipedia.org/wiki/x"},
        "뉴턴": {"title": "아이작 뉴턴", "snippet": "아이작 뉴턴(1643년 1월 4일~1727년)은 물리학자이다.", "url": "https://ko.wikipedia.org/wiki/y"},
    }
    monkeypatch.setattr(cr, "_rich_extract", lambda *a, **k: "")
    monkeypatch.setattr(cr, "wikipedia_search", lambda e, count=2: [fixtures[e]] if e in fixtures else [])
    out = cr.answer_comparison("아인슈타인과 뉴턴 중 누가 먼저 태어났어?", "ko")
    assert out is not None
    assert "뉴턴" in out["answer"] and "1643" in out["answer"]
    assert out["reasoning_certificate"]["guarantees"]["multi_hop"] is True
    assert len(out["sources"]) == 2


def test_detect_and_extract_height():
    plan = cr.detect_comparison("에베레스트와 K2 중 뭐가 더 높아?")
    assert plan and plan["attribute"] == "height_m" and plan["direction"] == "max"
    assert cr._extract_height_m("에베레스트는 해발 8,848 m의 산이다.") == 8848.0
    assert cr._extract_height_m("Burj Khalifa is 828 m tall.") == 828.0
    assert cr._extract_height_m("It was built in 1879 with no height given.") is None


def test_answer_height_comparison(monkeypatch):
    fixtures = {
        "에베레스트": {"title": "에베레스트산", "snippet": "에베레스트산은 해발 8,848 m로 세계에서 가장 높은 산이다.", "url": "u1"},
        "한라산": {"title": "한라산", "snippet": "한라산은 제주특별자치도에 있는 해발 1,947 m의 산으로 대한민국에서 가장 높은 산이다.", "url": "u2"},
    }
    monkeypatch.setattr(cr, "_rich_extract", lambda *a, **k: "")
    monkeypatch.setattr(cr, "wikipedia_search", lambda e, count=2: [fixtures[e]] if e in fixtures else [])
    out = cr.answer_comparison("에베레스트와 한라산 중 뭐가 더 높아?", "ko")
    assert out is not None
    assert "에베레스트산" in out["answer"] and "8848" in out["answer"].replace(",", "")
    assert out["reasoning_certificate"]["guarantees"]["multi_hop"] is True


def test_extract_population_and_area():
    assert cr._extract_population("서울의 인구는 약 950만 명이다.") == 9_500_000
    assert cr._extract_population("New York has a population of 8,336,817 people.") == 8_336_817
    assert cr._extract_area_km2("서울의 면적은 605.21 km²이다.") == 605.21
    assert cr._extract_area_km2("일본의 면적은 37만 7,973km²이다.") == 377973
    assert cr._extract_population("아무 숫자도 없는 도시 설명.") is None


def test_answer_population_comparison(monkeypatch):
    fixtures = {
        "서울": {"title": "서울특별시", "snippet": "서울특별시는 대한민국의 수도로 인구는 약 950만 명이다.", "url": "u1"},
        "부산": {"title": "부산광역시", "snippet": "부산광역시는 대한민국 제2의 도시로 인구는 약 330만 명이다.", "url": "u2"},
    }
    monkeypatch.setattr(cr, "_rich_extract", lambda *a, **k: "")
    monkeypatch.setattr(cr, "wikipedia_search", lambda e, count=2: [fixtures[e]] if e in fixtures else [])
    out = cr.answer_comparison("서울과 부산 중 어디가 인구가 더 많아?", "ko")
    assert out is not None and "서울특별시" in out["answer"]
    assert out["reasoning_certificate"]["steps"][2]["fact"].startswith("population")


def test_area_cue_routes_to_area(monkeypatch):
    plan = cr.detect_comparison("서울과 부산 중 어디가 면적이 더 넓어?")
    assert plan and plan["attribute"] == "area_km2" and plan["direction"] == "max"


def test_abstains_when_year_missing(monkeypatch):
    fixtures = {
        "A": {"title": "A", "snippet": "A is a thing with no dates mentioned here at all.", "url": "u"},
        "B": {"title": "B", "snippet": "B (1900년) is a person.", "url": "v"},
    }
    monkeypatch.setattr(cr, "_rich_extract", lambda *a, **k: "")
    monkeypatch.setattr(cr, "wikipedia_search", lambda e, count=2: [fixtures[e]] if e in fixtures else [])
    assert cr.answer_comparison("A와 B 중 누가 먼저 태어났어?", "ko") is None
