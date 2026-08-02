from __future__ import annotations

from cgsr.review_queue_analysis import analyze_manual_review_items, cluster_review_item


def _item(canonical: str, *, members: int = 12, reason: str = "valency_frame_review") -> dict[str, object]:
    return {
        "family_id": "family_test",
        "priority_score": 70.0,
        "reason": reason,
        "row": {
            "canonical_form": canonical,
            "member_count": members,
            "sample_examples": ["GraphRAG은 근거 문서를 검증한다."],
        },
    }


def test_cluster_review_item_detects_broad_core_case_frame() -> None:
    cluster, reason = cluster_review_item(_item("TOPIC OBJ PREDICATE:검증하다"))

    assert cluster == "broad_core_case_frame"
    assert "case frame" in reason


def test_cluster_review_item_detects_generic_predicate() -> None:
    cluster, reason = cluster_review_item(_item("ADVL:에 SUBJ PREDICATE:있다"))

    assert cluster == "generic_predicate"
    assert "broad" in reason


def test_analyze_manual_review_items_counts_upgradeable_clusters() -> None:
    summary = analyze_manual_review_items(
        [
            _item("TOPIC OBJ PREDICATE:검증하다"),
            _item("TOPIC OBJ PREDICATE:정렬하다", members=6),
            _item("ADVL:에 SUBJ PREDICATE:있다"),
        ]
    )

    assert summary["total_manual_review"] == 3
    assert summary["cluster_counts"]["broad_core_case_frame"] == 1
    assert summary["cluster_counts"]["frequency_below_auto"] == 1
    assert summary["upgradeable_estimate"]["count"] == 2
