from __future__ import annotations

from packages.surface_brain.repair_rules import RepairRule
from packages.surface_brain.review_queue import (
    approve_repair_candidate,
    enqueue_repair_candidates,
    get_repair_candidate,
    list_repair_candidates,
    reject_repair_candidate,
)
from packages.surface_brain.rule_registry import load_production_rules


def _rule(rule_id: str = "test_review_queue_rule") -> RepairRule:
    return RepairRule(
        rule_id=rule_id,
        name=rule_id,
        description="Move a proof leak to trace.",
        trigger_terms=["TEST_INTERNAL_LEAK"],
        mode_scope="default_only",
        action="move_to_trace",
        severity="high",
        source="proof",
    )


def test_enqueue_creates_pending_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    queued = enqueue_repair_candidates([_rule()], source_run_id="run-a")

    assert len(queued) == 1
    assert queued[0]["status"] == "pending"
    assert list_repair_candidates(status="pending")
    assert get_repair_candidate(queued[0]["candidate_id"])["candidate_id"] == queued[0]["candidate_id"]
    assert load_production_rules() == []


def test_approve_creates_production_rule_and_reject_does_not(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    first = enqueue_repair_candidates([_rule("approved_rule")], source_run_id="run-b")[0]
    production = approve_repair_candidate(first["candidate_id"], reviewer="tester", comment="safe")

    assert production["rule_id"] == "approved_rule"
    assert production["enabled"] is True
    assert get_repair_candidate(first["candidate_id"])["status"] == "approved"

    second = enqueue_repair_candidates([_rule("rejected_rule")], source_run_id="run-b")[0]
    rejected = reject_repair_candidate(second["candidate_id"], reviewer="tester", comment="not safe")

    assert rejected["status"] == "rejected"
    assert {row["rule_id"] for row in load_production_rules()} == {"approved_rule"}
