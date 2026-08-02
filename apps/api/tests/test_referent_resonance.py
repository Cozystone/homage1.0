"""Referent-type resonance: the systemic fix that replaced a dozen string-anchor
patches. A 'who' question expects a PERSON; evidence about a fly / website / film
destructively interferes (different type chord) and is suppressed."""
from __future__ import annotations

from packages.cgsr.cgsr.referent_resonance import (
    CONCEPT,
    ORG,
    ORGANISM,
    PERSON,
    WORK,
    infer_evidence_type,
    query_expected_type,
    resonance,
    select_resonant_facts,
)


def test_type_inference_uses_head_category_not_mentions():

    assert infer_evidence_type("이름은 2016년 신카이 마코토 감독의 일본 장편 애니메이션 영화이다") == WORK
    assert infer_evidence_type("윌리엄 헨리 게이츠 3세는 미국의 마이크로소프트 설립자이자 기업인이다") == PERSON
    assert infer_evidence_type("빌게이츠꽃등에는 코스타리카 고유종인 꽃등에로 빌 게이츠의 이름을 따") == ORGANISM
    assert infer_evidence_type("X(소셜 네트워크). 3억 3천만 명에 육박했다") == ORG
    assert infer_evidence_type("파이썬은 1991년 귀도 반 로섬이 발표한 고급 프로그래밍 언어로") == CONCEPT


def test_resonance_is_constructive_for_same_type_destructive_for_others():
    assert resonance(PERSON, PERSON) == 1.0
    assert resonance(PERSON, ORGANISM) < 0.45  # fly suppressed for a 'who' question
    assert resonance(PERSON, ORG) < 0.45
    assert resonance(PERSON, WORK) < 0.45


def test_who_question_expects_person():
    assert query_expected_type("빌게이츠가 누구야") == PERSON
    assert query_expected_type("엔비디아 창립자가 누구야") == PERSON

    assert query_expected_type("파이썬이 뭐야") == "unknown"


def test_gate_suppresses_trap_keeps_person():
    facts = [
        ("빌게이츠꽃등에는 코스타리카 고유종인 꽃등에로", "definition", 0, 1),
        ("빌 게이츠. 윌리엄 헨리 게이츠 3세는 미국의 기업인이다", "definition", 1, 1),
    ]
    kept, expected = select_resonant_facts("빌게이츠가 누구야", facts)
    assert expected == PERSON
    kept_text = [f[0] for f in kept]
    assert any("기업인" in t for t in kept_text)  # the person survives
    assert all("꽃등에" not in t for t in kept_text)  # the fly is suppressed
