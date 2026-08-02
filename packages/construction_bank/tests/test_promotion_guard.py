from __future__ import annotations

from packages.construction_bank.extractor import extract_construction_candidates
from packages.construction_bank.promotion_guard import assert_no_production_activation, can_activate_in_production, promotion_requirements


def test_promotion_guard_blocks_v0_production_activation() -> None:
    candidate = extract_construction_candidates([
        {"source_type": "operator_example", "language": "ko", "route_type": "voice_status", "act": "voice_question", "text": "Fish 음성은 로컬 fallback으로 먼저 말합니다.", "source_refs": ["test"]}
    ])[0]
    assert_no_production_activation(candidate)
    assert can_activate_in_production(candidate) is False
    assert promotion_requirements()["requires_future_signed_manifest"] is True
