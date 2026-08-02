"""Regression: " X /?" must yield the PERSON, never a definition
or a fabricated fragment. Korean is SOV, so subject and verb are separated by the
object — the extractor must capture the name, not the surrounding text.
"""
from __future__ import annotations

from app.routers.dual_brain import _detect_attribution_relation, _extract_attribution


def test_detects_founder_markers():
    assert _detect_attribution_relation("엔비디아 창립자가 누구야?")[0] == "founded"
    assert _detect_attribution_relation("애플 창업자가 누구야?")[0] == "founded"
    assert _detect_attribution_relation("전화기를 발명한 사람은 누구야?")[0] == "invented"
    # a plain definition question is NOT an attribution question
    assert _detect_attribution_relation("엔비디아가 뭐야?") is None


def test_extracts_person_not_definition():
    # comma-separated co-founders, year-anchored
    assert _extract_attribution(
        "엔비디아 창립자가 누구야?",
        ["엔비디아는 미국 기업이다. 1993년 4월 5일 젠슨 황, 크리스 말라초스키, 커티스 프리엠이 설립하였다."],
    ) == "젠슨 황, 크리스 말라초스키, 커티스 프리엠"


    assert _extract_attribution(
        "전화기를 발명한 사람은 누구야?",
        ["전화기는 음성을 전기신호로 바꾼다. 1876년 알렉산더 그레이엄 벨이 전화기를 발명하였다."],
    ) == "알렉산더 그레이엄 벨"


    assert _extract_attribution(
        "모나리자를 그린 사람은 누구야?",
        ["《모나리자》는 16세기 르네상스 시대에 레오나르도 다 빈치가 그린 초상화이다. 현재 프랑스 파리에 있다."],
    ) == "레오나르도 다 빈치"


def test_no_fabrication_on_definitions():


    assert _extract_attribution(
        "모나리자를 그린 사람은 누구야?",
        ["모나리자는 초상화이다. 현재 프랑스 파리 루브르 박물관에 전시되어 있다."],
    ) is None
