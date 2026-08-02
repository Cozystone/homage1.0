from cgsr.evaluation import classify_minimal_generation


def test_bare_numeric_object_is_not_ok() -> None:
    bucket, reason = classify_minimal_generation(
        {"concept": "카터", "object": "100", "predicate": "살다"},
        "카터는 100을 삽니다.",
        retrieval_tier="exact",
    )

    assert bucket == "c_lexicalization_realizer"
    assert "numeric" in reason


def test_intransitive_object_is_not_ok() -> None:
    bucket, reason = classify_minimal_generation(
        {"concept": "카터", "object": "조지아주", "predicate": "태어나다"},
        "카터는 조지아주를 태어납니다.",
        retrieval_tier="exact",
    )

    assert bucket == "c_lexicalization_realizer"
    assert "intransitive" in reason


def test_clean_transitive_case_stays_ok() -> None:
    bucket, _ = classify_minimal_generation(
        {"concept": "GraphRAG", "object": "근거 문서", "predicate": "검증하다"},
        "GraphRAG은 근거 문서를 검증합니다.",
        retrieval_tier="exact",
    )

    assert bucket == "ok"


def test_noisy_subject_takes_priority_over_matching_failure() -> None:
    bucket, reason = classify_minimal_generation(
        {"concept": "svg", "object": "웹", "predicate": "지내다"},
        "svg은 웹을 지냅니다.",
        retrieval_tier="fallback",
    )

    assert bucket == "c_lexicalization_realizer"
    assert "noisy subject" in reason


def test_fixed_numeric_age_output_is_ok() -> None:
    bucket, _ = classify_minimal_generation(
        {"concept": "카터", "object": "100", "predicate": "살다"},
        "카터는 100세까지 삽니다.",
        retrieval_tier="exact",
    )

    assert bucket == "ok"


def test_fixed_intransitive_location_output_is_ok() -> None:
    bucket, _ = classify_minimal_generation(
        {"concept": "카터", "object": "조지아주", "predicate": "태어나다"},
        "카터는 조지아주에서 태어납니다.",
        retrieval_tier="exact",
    )

    assert bucket == "ok"


def test_fixed_year_object_output_is_ok() -> None:
    bucket, _ = classify_minimal_generation(
        {"concept": "케네디", "object": "1980", "predicate": "물리치다"},
        "케네디는 1980년에 물리칩니다.",
        retrieval_tier="exact",
    )

    assert bucket == "ok"
