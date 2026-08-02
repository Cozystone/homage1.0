from __future__ import annotations

import pytest

from packages.construction_bank.models import ConstructionBank, ConstructionCandidate


def _candidate(**overrides):
    data = {
        "candidate_id": "construction_abc",
        "source_type": "operator_example",
        "language": "ko",
        "route_type": "voice_status",
        "act": "voice_question",
        "construction_family": "voice_status.voice_question.state_grounded_fact",
        "discourse_moves": ("acknowledge", "state_grounded_fact"),
        "slot_schema": ("VOICE_STATUS",),
        "lexical_patterns": ("Fish", "음성"),
        "forbidden_phrases": ("chain of thought",),
        "example_text": "Fish 직접 합성은 아직 연결 전입니다.",
        "source_refs": ("docs/voice.md",),
        "content_hash": "hash",
        "novelty_score": 0.7,
        "usefulness_score": 0.8,
        "naturalness_score": 0.8,
        "grounding_score": 0.6,
        "template_risk": 0.1,
        "safety_risk": 0.0,
    }
    data.update(overrides)
    return ConstructionCandidate(**data)


def test_candidate_cannot_be_production_active() -> None:
    with pytest.raises(ValueError):
        _candidate(production_active=True)


def test_bank_dedupes_by_hash_and_reports_invariants() -> None:
    bank = ConstructionBank()
    first = bank.add(_candidate())
    second = bank.add(_candidate(candidate_id="construction_other"))
    assert first is second
    status = bank.status()
    assert status["total_candidates"] == 1
    assert status["production_active_count"] == 0
    assert status["construction_auto_promoted"] is False
