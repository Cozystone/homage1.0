from __future__ import annotations

import app.services.chained_reasoner as ch


def test_detect_chain_variants():
    p1 = ch.detect_chain("프랑스의 수도의 인구는?")
    assert p1 == {"base": "프랑스", "relation": "capital", "attribute": "인구"}
    p2 = ch.detect_chain("프랑스의 수도는?")
    assert p2 and p2["base"] == "프랑스" and p2["attribute"] is None
    p3 = ch.detect_chain("일본 수도의 면적은 얼마야?")
    assert p3 and p3["base"] == "일본" and p3["attribute"] == "면적"
    assert ch.detect_chain("아인슈타인이 누구야") is None


def test_extract_capital():
    assert ch._extract_capital("프랑스의 수도는 파리이다.") == "파리"
    assert ch._extract_capital("일본의 수도이자 최대 도시인 도쿄") == "도쿄"
    assert ch._extract_capital("거기엔 산이 많다.") is None


def test_one_hop_capital(monkeypatch):
    monkeypatch.setattr(ch, "_lookup", lambda e, lang="ko": {
        "title": "프랑스", "snippet": "프랑스는 유럽의 국가로 수도는 파리이다.", "url": "u_fr"})
    out = ch.answer_chain("프랑스의 수도는?", "ko")
    assert out and "파리" in out["answer"] and "프랑스" in out["answer"]
    assert out["reasoning_certificate"]["derivation_kind"] == "deterministic_chained_reasoning"


def test_two_hop_capital_population(monkeypatch):
    db = {
        "프랑스": {"title": "프랑스", "snippet": "프랑스는 유럽의 국가로 수도는 파리이다.", "url": "u_fr"},
        "파리": {"title": "파리", "snippet": "파리는 프랑스의 수도로 인구는 약 210만 명이다.", "url": "u_paris"},
    }
    monkeypatch.setattr(ch, "_lookup", lambda e, lang="ko": db.get(e))
    out = ch.answer_chain("프랑스의 수도의 인구는?", "ko")
    assert out is not None
    assert "파리" in out["answer"] and "210" in out["answer"].replace(",", "")
    assert out["reasoning_certificate"]["guarantees"]["multi_hop"] is True
    assert len(out["sources"]) == 2
    assert out["reasoning_certificate"]["steps"][-1]["type"] == "chain"


def test_abstains_when_capital_missing(monkeypatch):
    monkeypatch.setattr(ch, "_lookup", lambda e, lang="ko": {
        "title": "X", "snippet": "X는 어떤 나라인데 수도 정보가 없다.", "url": "u"})
    assert ch.answer_chain("X의 수도의 인구는?", "ko") is None
