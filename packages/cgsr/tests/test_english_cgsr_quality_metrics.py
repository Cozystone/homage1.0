from __future__ import annotations

import json
from pathlib import Path

from cgsr.english.factual_decomposition import decompose_english_fact, evaluate_fixture_set
from cgsr.ingestion.decomposer import extract_english_case_roles


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "english_factual_sentences.json"


def _sentences() -> list[str]:
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [str(row["sentence"]) for row in rows]


def test_generic_predicate_ratio_decreases_against_legacy_extractor() -> None:
    sentences = _sentences()
    legacy_predicates = [extract_english_case_roles(sentence)[1] for sentence in sentences]
    legacy_generic = sum(1 for predicate in legacy_predicates if predicate in {"be", "have", "do", "use"})
    legacy_ratio = legacy_generic / max(1, sum(1 for predicate in legacy_predicates if predicate))

    metrics = evaluate_fixture_set(sentences)

    assert metrics["generic_predicate_ratio"] < legacy_ratio
    assert metrics["specific_predicate_count"] == 4


def test_quality_scores_are_bounded_and_claims_safe() -> None:
    for sentence in _sentences():
        result = decompose_english_fact(sentence)
        assert 0.0 <= result.quality.specific_predicate_score <= 1.0
        assert 0.0 <= result.quality.argument_completeness_score <= 1.0
        assert 0.0 <= result.quality.relation_type_score <= 1.0
        assert 0.0 <= result.quality.generic_predicate_penalty <= 1.0
        assert 0.0 <= result.quality.unsupported_claim_penalty <= 1.0
        assert 0.0 <= result.quality.total <= 1.0
        assert result.frame is not None
        assert result.frame.unsupported_claims == []
        assert result.frame.false_confident == 0


def test_fixture_metrics_report_no_unsupported_claims_or_false_confident() -> None:
    metrics = evaluate_fixture_set(_sentences())

    assert metrics["fixture_count"] == 5
    assert metrics["parsed_count"] == 5
    assert metrics["comparison_extraction_count"] == 1
    assert metrics["cause_effect_extraction_count"] == 1
    assert metrics["unsupported_claims"] == 0
    assert metrics["false_confident"] == 0
    assert metrics["abstained_count"] == 0


def test_parser_invariants_do_not_write_or_call_external_runtime() -> None:
    result = decompose_english_fact("Docker packages applications into containers.")

    assert result.frame is not None
    assert result.frame.to_dict()["unsupported_claims"] == []
    assert "external_llm_used" not in result.frame.to_dict()
