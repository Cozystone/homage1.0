"""Semantic-neighbourhood gathering: probabilistic synthesis can answer from the
CONSTELLATION of related grounded facts (no exact concept), staying on-topic and never
dragging in an off-topic concept via a weak incidental match."""
from __future__ import annotations

from packages.base_brain.neighborhood import gather_neighborhood, _expand_query_terms, _strip_ko_tail


CONCEPTS = [
    {"concept_id": "ai_training", "canonical_name": "AI model training", "labels": {"ko": "AI 모델 학습"},
     "short_description": "AI 모델 학습은 데이터를 보며 모델 내부 기준을 조정하는 과정입니다."},
    {"concept_id": "ai_inference", "canonical_name": "AI inference", "labels": {"ko": "AI 추론"},
     "short_description": "AI 추론은 이미 만들어진 모델이 새 입력을 보고 출력을 계산하는 과정입니다."},
    {"concept_id": "nn", "canonical_name": "신경망",
     "short_description": "신경망은 가중치로 연결된 층 구조로 데이터의 표현을 학습하는 모델입니다."},
    {"concept_id": "jeju", "canonical_name": "제주특별자치도",
     "short_description": "제주특별자치도는 대한민국 남쪽의 섬 도(道)입니다."},
    {"concept_id": "cell", "canonical_name": "세포",
     "short_description": "세포는 모든 생물체의 기본 단위이다."},
]


def test_particle_stripping():
    assert _strip_ko_tail("인공지능이") == "인공지능"
    assert _strip_ko_tail("컴퓨터에") == "컴퓨터"
    assert _strip_ko_tail("우주란") == "우주"


def test_bridge_finds_english_concepts_for_korean_query():
    """'' (no literal match anywhere) reaches the AI concepts via the domain
 bridge — the cross-lingual reach that plain token retrieval lacks."""
    terms, _ = _expand_query_terms("인공지능이 뭐야?")
    assert "인공지능" in terms and ("ai" in terms or "신경망" in terms)
    neigh = gather_neighborhood("인공지능이 뭐야?", CONCEPTS, limit=6)
    names = {c["canonical_name"] for c in neigh}
    assert "AI model training" in names and "신경망" in names
    assert "제주특별자치도" not in names           # off-topic never pulled in
    assert "세포" not in names


def test_thin_or_unrelated_query_gathers_nothing():
    assert gather_neighborhood("제주도 여행", [c for c in CONCEPTS if c["concept_id"] != "jeju"]) == []


def test_neighbourhood_requires_a_primary_hit_not_incidental():
    """A concept joins only on a PRIMARY (query/bridge) term — an incidental 2-gram in a
    description never drags in something off-topic."""
    neigh = gather_neighborhood("신경망이 뭐야?", CONCEPTS, limit=6)
    names = {c["canonical_name"] for c in neigh}
    assert "신경망" in names
    assert "제주특별자치도" not in names
