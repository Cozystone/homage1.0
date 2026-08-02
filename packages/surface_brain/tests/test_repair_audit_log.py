from __future__ import annotations

from packages.surface_brain.audit_log import append_repair_audit_event, list_repair_audit_events
from packages.surface_brain.repair_rules import RepairRule
from packages.surface_brain.review_queue import approve_repair_candidate, enqueue_repair_candidates, reject_repair_candidate
from packages.surface_brain.rule_registry import rollback_rule


def test_audit_log_records_state_transitions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    append_repair_audit_event("candidate_created", candidate_id="manual")
    rule = RepairRule(
        rule_id="audit_rule",
        name="audit_rule",
        description="Audit rule.",
        trigger_terms=["AUDIT_TOKEN"],
        mode_scope="default_only",
        action="replace",
        replacement="근거",
        severity="high",
        source="proof",
    )
    candidate = enqueue_repair_candidates([rule], source_run_id="run-audit")[0]
    approve_repair_candidate(candidate["candidate_id"], reviewer="tester")
    rollback_rule("audit_rule", actor="tester")

    rejected = enqueue_repair_candidates([rule], source_run_id="run-audit-reject")[0]
    reject_repair_candidate(rejected["candidate_id"], reviewer="tester")

    event_types = [row["event_type"] for row in list_repair_audit_events(limit=20)]
    assert "candidate_created" in event_types
    assert "candidate_approved" in event_types
    assert "candidate_rejected" in event_types
    assert "rule_rolled_back" in event_types
