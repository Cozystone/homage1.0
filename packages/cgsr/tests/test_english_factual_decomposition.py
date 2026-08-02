from __future__ import annotations

import json
from pathlib import Path

from cgsr.english.factual_decomposition import decompose_english_fact


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "english_factual_sentences.json"


def _fixtures() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_sentences_decompose_to_expected_frames() -> None:
    for row in _fixtures():
        result = decompose_english_fact(str(row["sentence"]), evidence_id="ev:test")
        assert result.frame is not None, row["sentence"]
        assert result.frame.subject == row["expected_subject"]
        assert result.frame.predicate == row["expected_predicate"]
        assert result.frame.object == row["expected_object"]
        assert result.frame.relation_type == row["expected_relation_type"]
        assert result.frame.evidence_id == "ev:test"
        assert result.frame.unsupported_claims == []
        assert result.frame.false_confident == 0


def test_definition_sentence_extracts_purpose_and_domain() -> None:
    result = decompose_english_fact(
        "Kubernetes is an open-source system for automating deployment, scaling, and management of containerized applications."
    )

    assert result.frame is not None
    assert result.frame.complement == "open-source system"
    assert result.frame.purpose == "automating deployment, scaling, and management of containerized applications"
    assert result.frame.domain == "containerized applications"


def test_comparison_sentence_has_compared_to_and_dimension() -> None:
    result = decompose_english_fact("Spring Boot provides more built-in enterprise conventions than Express.")

    assert result.frame is not None
    assert result.frame.compared_to == "Express"
    assert result.frame.dimension == "built-in enterprise conventions"


def test_cause_effect_sentence_has_effect_and_mechanism() -> None:
    result = decompose_english_fact("Caching reduces latency by avoiding repeated computation.")

    assert result.frame is not None
    assert result.frame.effect == "latency"
    assert result.frame.mechanism == "avoiding repeated computation"


def test_temporal_sentence_preserves_subject_and_object() -> None:
    result = decompose_english_fact("Python 3.11 introduced performance improvements.")

    assert result.frame is not None
    assert result.frame.subject == "Python 3.11"
    assert result.frame.object == "performance improvements"


def test_unsupported_sentence_abstains_without_false_confidence() -> None:
    result = decompose_english_fact("Maybe this is interesting, but who knows?")

    assert result.abstained is True
    assert result.frame is None
    assert result.reason == "not_fact_statement_shape"
    assert result.quality.unsupported_claim_penalty == 0.0
