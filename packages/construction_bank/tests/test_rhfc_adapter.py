from __future__ import annotations

from packages.construction_bank.extractor import extract_construction_candidates
from packages.construction_bank.rhfc_adapter import cleanup_score


def test_cleanup_score_penalizes_route_mismatch() -> None:
    candidate = extract_construction_candidates([
        {"source_type": "operator_example", "language": "ko", "route_type": "voice_status", "act": "voice_question", "text": "Fish 음성은 로컬 fallback으로 먼저 말합니다.", "source_refs": ["test"]}
    ])[0]
    matched = cleanup_score(candidate, route_type="voice_status")
    mismatched = cleanup_score(candidate, route_type="splatra_request")
    assert matched.score > mismatched.score
    assert "route_mismatch" in mismatched.penalties
