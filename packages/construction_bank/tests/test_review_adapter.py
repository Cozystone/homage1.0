from __future__ import annotations

from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.construction_bank.extractor import extract_construction_candidates
from packages.construction_bank.review_adapter import export_to_review_queue


def test_review_adapter_creates_construction_candidate_item_without_mutation() -> None:
    candidate = extract_construction_candidates([
        {"source_type": "operator_example", "language": "ko", "route_type": "voice_status", "act": "voice_question", "text": "Fish 음성은 로컬 fallback으로 먼저 말합니다.", "source_refs": ["test"]}
    ])[0]
    item = export_to_review_queue(candidate, ReviewQueue())
    assert item["item_type"] == "construction_candidate"
    assert item["status"] == "pending"
    assert item["content_hash"] == candidate.content_hash
