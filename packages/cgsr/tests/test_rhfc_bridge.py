from __future__ import annotations

from cgsr.rhfc_bridge import (
    argument_compatibility,
    argument_roles_from_canonical,
    check_near_duplicate_confusion,
    encode_construction,
    encode_query_skeleton,
    exact_recall_accuracy,
    store_constructions,
)


def _family(family_id: str, canonical: str, members: int = 8) -> dict[str, object]:
    return {
        "family_id": family_id,
        "priority_score": 80.0,
        "row": {
            "family_id": family_id,
            "canonical_form": canonical,
            "member_count": members,
            "sample_examples": ["GraphRAG은 근거 문서를 검증한다."],
        },
    }


def test_encode_construction_is_deterministic() -> None:
    family = _family("f1", "TOPIC OBJ PREDICATE:검증하다")

    first = encode_construction(family)
    second = encode_construction(family)

    assert first.dim == 512
    assert (first.values == second.values).all()


def test_store_constructions_exact_recall() -> None:
    store = store_constructions(
        [
            _family("f1", "TOPIC OBJ PREDICATE:검증하다"),
            _family("f2", "ADVL:에 OBJ PREDICATE:사용하다"),
            _family("f3", "ADVL:로 SUBJ PREDICATE:구성하다"),
        ],
        shard_count=2,
    )
    accuracy = exact_recall_accuracy(store)

    assert store.storage_metrics()["record_count"] == 3
    assert accuracy["accuracy"] == 1.0


def test_query_skeleton_can_retrieve_a_related_construction() -> None:
    store = store_constructions(
        [
            _family("f1", "TOPIC OBJ HEAD:문서 PREDICATE:검증하다"),
            _family("f2", "ADVL:에 OBJ PREDICATE:사용하다"),
        ],
        shard_count=2,
    )
    result = store.retrieve_by_vector(
        encode_query_skeleton({"concept": "GraphRAG", "object": "근거 문서", "predicate": "검증하다"})
    )

    assert result["family_id"] in {"f1", "f2"}
    assert result["score"] > 0.0


def test_rank_by_vector_can_filter_to_query_predicate() -> None:
    store = store_constructions(
        [
            _family("f1", "TOPIC OBJ HEAD:document PREDICATE:verify"),
            _family("f2", "TOPIC OBJ HEAD:document PREDICATE:compare"),
        ],
        shard_count=2,
    )

    ranked = store.rank_by_vector(
        encode_query_skeleton({"concept": "GraphRAG", "object": "document", "predicate": "verify"}),
        predicate="verify",
    )

    assert ranked
    assert {row["predicate"] for row in ranked} == {"verify"}


def test_checked_retrieval_abstains_on_predicate_mismatch() -> None:
    store = store_constructions(
        [
            _family("f1", "TOPIC OBJ HEAD:문서 PREDICATE:검증하다"),
            _family("f2", "TOPIC OBJ HEAD:문서 PREDICATE:사용하다"),
        ],
        shard_count=2,
    )

    result = store.retrieve_skeleton_checked(
        {"concept": "GraphRAG", "object": "근거 문서", "predicate": "비교하다"}
    )

    assert result["matched"] is False
    assert result["reason"] == "predicate_not_in_rhfc_store"
    assert "top_candidates" in result


def test_checked_retrieval_reports_margin_for_confident_match() -> None:
    store = store_constructions(
        [
            _family("f1", "TOPIC OBJ HEAD:문서 PREDICATE:검증하다"),
            _family("f2", "ADVL:에 OBJ PREDICATE:사용하다"),
        ],
        shard_count=2,
    )

    result = store.retrieve_skeleton_checked(
        {"concept": "GraphRAG", "object": "근거 문서", "predicate": "검증하다"},
        min_margin=0.0,
    )

    assert result["matched"] is True
    assert result["retrieved_predicate"] == "검증하다"
    assert "margin" in result
    assert len(result["top_candidates"]) >= 1
    assert result["argument_check"]["compatible"] is True


def test_argument_compatibility_uses_broad_case_roles() -> None:
    assert argument_roles_from_canonical("TOPIC ADVL:에 PREDICATE:대응하다") == {"TOPIC", "ADVL"}

    compatible = argument_compatibility(
        {"concept": "아프가니스탄", "object": "침공", "predicate": "대응한다"},
        "TOPIC ADVL:에 PREDICATE:대응하다",
    )
    concept_as_adverbial = argument_compatibility(
        {"concept": "정치", "object": "회고록", "predicate": "이르다"},
        "ADVL:에 OBJ PREDICATE:이르다",
    )
    incompatible = argument_compatibility(
        {"concept": "아프가니스탄", "object": "침공", "predicate": "대응한다"},
        "TOPIC PREDICATE:대응하다",
    )

    assert compatible["compatible"] is True
    assert compatible["strict_exact_match"] is False
    assert concept_as_adverbial["compatible"] is True
    assert incompatible["compatible"] is False


def test_near_duplicate_confusion_reports_pair_results() -> None:
    store = store_constructions(
        [
            _family("f1", "TOPIC OBJ PREDICATE:사용하다"),
            _family("f2", "ADVL:에 OBJ PREDICATE:사용하다"),
            _family("f3", "ADVL:로 OBJ PREDICATE:사용하다"),
        ],
        shard_count=2,
    )
    result = check_near_duplicate_confusion(store, limit=2)

    assert result["pair_count"] >= 1
    assert "confusion_rate" in result
