from __future__ import annotations

from cgsr.family_analysis import analyze_family_distribution
from cgsr.induction import induce_constructions
from cgsr.retrieval import retrieve_construction


def test_family_analysis_splits_structural_and_paraphrase_like() -> None:
    corpus = [
        "쉽게 말하면 쿠버네티스는 컨테이너를 관리하는 시스템입니다.",
        "간단히 말해 쿠버네티스는 컨테이너를 관리하는 플랫폼입니다.",
        "쉽게는 쿠버네티스는 컨테이너 운영을 돕는 도구입니다.",
        "그래프는 근거를 연결합니다.",
        "문서는 근거를 제공합니다.",
    ]
    raw = induce_constructions(corpus, min_frequency=1, dedupe=False)
    deduped = induce_constructions(corpus, min_frequency=1, dedupe=True)

    result = analyze_family_distribution(raw, deduped)

    assert result["total_families"] > 0
    assert "reduction_by_group" in result
    assert "top_families" in result
