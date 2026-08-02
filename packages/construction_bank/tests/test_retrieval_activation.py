from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.extractor import extract_one
from packages.construction_bank.models import ConstructionBank
from packages.construction_bank.retriever import retrieve_constructions


def _bank_with(status: str) -> ConstructionBank:
    candidate = extract_one(
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 선택 기능이고, 준비되지 않으면 텍스트로 이어갑니다.",
            "source_refs": ["test"],
            "grounding_quality": "high",
        }
    )
    return ConstructionBank({candidate.candidate_id: replace(candidate, status=status)})  # type: ignore[arg-type]


def test_lab_retrieves_candidate_but_does_not_use_unreviewed_candidate() -> None:
    payload = retrieve_constructions(route_type="voice_status", language="ko", audience="lab", bank=_bank_with("candidate"))

    assert payload["retrieved_self_grown_construction"] is True
    assert payload["self_grown_construction_used"] is False
    assert payload["hand_authored_fallback_used"] is True
    assert "candidate_preview_only" in payload["rejection_reasons"]


def test_lab_uses_reviewed_candidate() -> None:
    payload = retrieve_constructions(route_type="voice_status", language="ko", audience="lab", bank=_bank_with("reviewed"))

    assert payload["self_grown_construction_used"] is True
    assert payload["candidate_status"] == "reviewed"
    assert payload["production_active"] is False
    assert payload["candidate_answer"]


def test_product_uses_only_promoted_draft_candidate() -> None:
    reviewed = retrieve_constructions(route_type="voice_status", language="ko", audience="product", bank=_bank_with("reviewed"))
    promoted = retrieve_constructions(route_type="voice_status", language="ko", audience="product", bank=_bank_with("promoted_draft"))

    assert reviewed["self_grown_construction_used"] is False
    assert promoted["self_grown_construction_used"] is True
    assert promoted["production_construction_activation"] is False
