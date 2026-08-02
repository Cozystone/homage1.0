from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.compare import compare_construction_retrieval
from packages.construction_bank.extractor import extract_one
from packages.construction_bank.models import ConstructionBank


def test_compare_reports_hand_authored_and_self_grown_paths() -> None:
    candidate = extract_one(
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 선택 기능입니다. 준비되지 않으면 텍스트로 먼저 답합니다.",
            "source_refs": ["test"],
            "grounding_quality": "high",
        }
    )
    bank = ConstructionBank({candidate.candidate_id: replace(candidate, status="reviewed")})

    payload = compare_construction_retrieval("Fish2 소리 상태 알려줘", mode="lab", bank=bank)

    assert payload["route"]["route_type"] == "voice_status"
    assert payload["hand_authored_answer"]
    assert payload["self_grown_candidate_answer"]
    assert payload["chosen_answer"] == payload["self_grown_candidate_answer"]
    assert payload["metadata"]["production_active"] is False
    assert payload["metadata"]["self_grown_construction_used"] is True
