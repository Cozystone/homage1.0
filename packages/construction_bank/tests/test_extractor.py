from __future__ import annotations

from packages.construction_bank.extractor import extract_construction_candidates


def test_extractor_builds_candidate_without_private_payload() -> None:
    candidates = extract_construction_candidates(
        [
            {
                "source_type": "asm_output",
                "language": "ko",
                "route_type": "voice_status",
                "act": "voice_question",
                "answer": "Fish 음성은 준비 중입니다. api_key=SECRET 텍스트 대화는 가능합니다.",
                "source_refs": ["asm:test"],
                "grounding_quality": "medium",
            }
        ]
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_type == "asm_output"
    assert "SECRET" not in candidate.example_text
    assert candidate.production_active is False
    assert candidate.status == "candidate"
