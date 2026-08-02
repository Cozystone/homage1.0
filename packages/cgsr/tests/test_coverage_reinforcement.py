from __future__ import annotations

from cgsr.coverage_reinforcement import (
    build_domain_relevant_candidates,
    build_domain_relevant_candidates_fixture_only_diagnostic,
    strict_predicate_inventory,
)
from cgsr.rhfc_bridge import normalize_predicate


def test_domain_relevant_candidates_skip_lexicalization_issues() -> None:
    strict = [
        {
            "family_id": "f1",
            "row": {"canonical_form": "TOPIC OBJ PREDICATE:사용하다"},
        }
    ]
    cases = [
        {
            "case": {"concept": "GraphRAG", "object": "근거 문서", "predicate": "검증한다"},
            "awkwardness_bucket": "ok",
        },
        {
            "case": {"concept": "svg", "object": "웹", "predicate": "지내다"},
            "awkwardness_bucket": "c_lexicalization_realizer",
        },
        {
            "case": {"concept": "민주당", "object": "소속", "predicate": "지내다"},
            "awkwardness_bucket": "ok",
        },
        {
            "case": {"concept": "도구", "object": "문서", "predicate": "사용한다"},
            "awkwardness_bucket": "ok",
        },
    ]

    generated = build_domain_relevant_candidates(cases, strict)

    assert [row["row"]["canonical_form"] for row in generated] == [
        "TOPIC OBJ HEAD:문서 PREDICATE:검증하다"
    ]
    assert generated[0]["destination"] == "diagnostic_only"
    assert generated[0]["diagnostic_only"] is True
    assert "사용하다" in strict_predicate_inventory(strict)


def test_fixture_only_builder_matches_compatibility_alias() -> None:
    cases = [
        {
            "case": {"concept": "GraphRAG", "object": "근거 문서", "predicate": "검증한다"},
            "awkwardness_bucket": "ok",
        }
    ]

    assert build_domain_relevant_candidates(cases, []) == build_domain_relevant_candidates_fixture_only_diagnostic(cases, [])
