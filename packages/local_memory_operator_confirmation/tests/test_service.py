from __future__ import annotations

from packages.local_memory_operator_confirmation.service import (
    create_confirmation_request,
    evaluate_gate,
    get_confirmation_request,
    list_confirmation_requests,
    submit_confirmation_decision,
)


def test_service_records_confirmation_metadata_only(tmp_path) -> None:
    created = create_confirmation_request(
        source_memory_manifest_id="manifest",
        source_write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id="rollback",
        source_sandbox_transaction_id="sandbox",
        root=tmp_path,
    )
    request = created["request"]

    assert request["status"] == "pending_confirmation"
    assert created["gate"]["allowed_to_prepare_real_write"] is False
    assert created["gate"]["allowed_to_apply_real_write"] is False
    assert created["gate"]["apply_enabled"] is False
    assert created["gate"]["local_brain_write"] is False

    loaded = get_confirmation_request(request["request_id"], root=tmp_path)
    assert loaded["request"]["request_id"] == request["request_id"]
    assert list_confirmation_requests(root=tmp_path)[0]["local_brain_write"] is False


def test_wrong_then_correct_phrase_allows_prepare_only(tmp_path) -> None:
    created = create_confirmation_request(
        source_memory_manifest_id="manifest",
        source_write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id="rollback",
        source_sandbox_transaction_id="sandbox",
        root=tmp_path,
    )
    request = created["request"]

    wrong = submit_confirmation_decision(
        request["request_id"],
        decision="confirm",
        typed_phrase="wrong",
        root=tmp_path,
    )
    correct = submit_confirmation_decision(
        request["request_id"],
        decision="confirm",
        typed_phrase=request["required_phrase"],
        root=tmp_path,
    )

    assert wrong["gate"]["allowed_to_prepare_real_write"] is False
    assert correct["gate"]["allowed_to_prepare_real_write"] is True
    assert correct["gate"]["allowed_to_apply_real_write"] is False
    assert evaluate_gate(request["request_id"], root=tmp_path)["apply_enabled"] is False


def test_missing_rollback_creates_blocked_request(tmp_path) -> None:
    created = create_confirmation_request(
        source_memory_manifest_id="manifest",
        source_write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id=None,
        source_sandbox_transaction_id="sandbox",
        root=tmp_path,
    )

    assert created["request"]["status"] == "blocked"
    assert "rollback_plan_required" in created["preconditions"]["errors"]
