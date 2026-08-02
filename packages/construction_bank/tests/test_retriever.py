from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.extractor import extract_construction_candidates
from packages.construction_bank.models import ConstructionBank
from packages.construction_bank.retriever import retrieve_constructions


def test_product_retrieval_previews_but_falls_back_for_unpromoted_candidates() -> None:
    bank = ConstructionBank()
    candidate = extract_construction_candidates([
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 로컬 fallback으로 먼저 말합니다.",
            "source_refs": ["test"],
            "grounding_quality": "high",
        }
    ])[0]
    bank.add(candidate)

    product = retrieve_constructions(route_type="voice_status", act="voice_question", language="ko", audience="product", bank=bank)

    assert product["retrieved_self_grown_construction"] is True
    assert product["self_grown_construction_used"] is False
    assert product["hand_authored_fallback_used"] is True
    assert "product_requires_promoted_draft_not_candidate" in product["rejection_reasons"]


def test_product_retrieval_uses_promoted_draft_without_production_activation() -> None:
    bank = ConstructionBank()
    candidate = extract_construction_candidates([
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 로컬 fallback으로 먼저 말합니다.",
            "source_refs": ["test"],
            "grounding_quality": "high",
        }
    ])[0]
    bank.add(replace(candidate, status="promoted_draft"))

    product = retrieve_constructions(route_type="voice_status", act="voice_question", language="ko", audience="product", bank=bank)

    assert product["self_grown_construction_used"] is True
    assert product["production_active"] is False
    assert product["production_construction_activation"] is False
