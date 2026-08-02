from __future__ import annotations

from cgsr.ingestion.quality import corroboration_report, near_duplicate_report, quality_decision, quality_gate


def _frame(predicate: str = "관리하다", *, source: str = "s1", language: str = "ko", head: str = "컨테이너"):
    return {
        "frame_id": f"f_{source}_{head}",
        "language": language,
        "predicate": predicate,
        "case_roles": [
            {"role": "TOPIC", "marker": "는", "head": "쿠버네티스"},
            {"role": "OBJ", "marker": "를", "head": head},
        ],
        "canonical_form": f"OBJ:를:{head} TOPIC:는:쿠버네티스 PREDICATE:{predicate}",
        "source_hash": source,
        "dedupe_key": f"k_{source}_{head}",
        "provenance": {
            "source_id": source,
            "source_hash": source,
            "source_type": "wikipedia",
            "license": "CC BY-SA 4.0",
            "collected_at": "2026-06-20T00:00:00Z",
            "ingest_run_id": "test",
        },
        "verification": {
            "status": "verified",
            "checked_at": "2026-06-20T00:00:00Z",
            "method": "unit",
            "rejection_reason": "",
        },
    }


def test_quality_decision_accepts_reusable_korean_case_frame() -> None:
    decision = quality_decision(_frame())
    assert decision.label == "Yes"
    assert decision.score >= 0.72


def test_quality_decision_rejects_mock_signal() -> None:
    frame = _frame("AtanorSeedConcept9")
    decision = quality_decision(frame)
    assert decision.label == "No"
    assert "mock_signal" in decision.reasons


def test_near_duplicate_report_counts_structural_duplicates() -> None:
    report = near_duplicate_report([_frame(source="s1", head="컨테이너"), _frame(source="s2", head="문서")])
    assert report["exact_duplicate_rate"] == 0.0
    assert report["structural_duplicate_rate"] == 0.5


def test_corroboration_report_counts_independent_sources() -> None:
    report = corroboration_report([_frame(source="s1"), _frame(source="s2")])
    assert report["multi_source_exact_ratio"] == 1.0


def test_quality_gate_blocks_low_quality_batch() -> None:
    good = _frame()
    bad = _frame(language="en")
    bad["case_roles"] = []
    bad["canonical_form"] = "PREDICATE:관리하다"
    gate = quality_gate([good, bad], min_yes_ratio=0.75)
    assert not gate["passed"]
