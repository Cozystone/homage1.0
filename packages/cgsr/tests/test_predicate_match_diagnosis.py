from __future__ import annotations

from cgsr.predicate_match_diagnosis import classify_predicate_case, diagnose_predicate_matches


def test_classify_coverage_absent_when_candidate_bank_lacks_predicate() -> None:
    row = classify_predicate_case(
        {"predicate": "검증하다"},
        "ADVL:에 OBJ PREDICATE:사용하다",
        {"사용하다"},
    )

    assert row["category"] == "c_candidate_coverage_absent"


def test_classify_query_encoding_when_predicate_is_covered_but_not_retrieved() -> None:
    row = classify_predicate_case(
        {"predicate": "검증하다"},
        "ADVL:에 OBJ PREDICATE:사용하다",
        {"검증하다", "사용하다"},
    )

    assert row["category"] == "d_query_encoding_weight"


def test_diagnose_predicate_matches_counts_categories() -> None:
    candidates = [
        {"row": {"canonical_form": "ADVL:에 OBJ PREDICATE:사용하다"}},
        {"row": {"canonical_form": "ADVL:에 OBJ PREDICATE:평가하다"}},
    ]
    report = diagnose_predicate_matches(
        [{"predicate": "사용한다"}, {"predicate": "검증하다"}],
        [
            {"canonical_form": "ADVL:에 OBJ PREDICATE:사용하다"},
            {"canonical_form": "ADVL:에 OBJ PREDICATE:평가하다"},
        ],
        candidates,
    )

    assert report["category_counts"]["matched"] == 1
    assert report["category_counts"]["c_candidate_coverage_absent"] == 1
