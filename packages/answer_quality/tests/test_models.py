from __future__ import annotations

from packages.answer_quality.models import AnswerCandidate, AnswerQualityPrompt, honesty_flags


def test_models_serialize_and_honesty_flags_are_local_only() -> None:
    prompt = AnswerQualityPrompt("p1", "general", "쿠버네티스가 뭐야?", "ko")
    candidate = AnswerCandidate("c1", "p1", "surface_brain", "쿠버네티스는 컨테이너 관리 시스템입니다.")

    assert prompt.to_dict()["language"] == "ko"
    assert candidate.to_dict()["generator"] == "surface_brain"
    assert honesty_flags()["external_llm_judge_used"] is False
    assert honesty_flags()["auto_promoted_feedback"] is False

