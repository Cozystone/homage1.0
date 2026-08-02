from __future__ import annotations

from datetime import datetime, timedelta, timezone

from packages.local_memory_operator_confirmation.validator import validate_preconditions


def test_valid_preconditions_keep_apply_locked() -> None:
    validation = validate_preconditions(
        memory_manifest_id="manifest",
        write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id="rollback",
        sandbox_transaction_id="sandbox",
    )

    assert validation.valid is True
    assert validation.to_dict()["apply_enabled"] is False
    assert validation.to_dict()["local_brain_write"] is False


def test_missing_rollback_blocks() -> None:
    validation = validate_preconditions(
        memory_manifest_id="manifest",
        write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id=None,
        sandbox_transaction_id="sandbox",
    )

    assert validation.valid is False
    assert "rollback_plan_required" in validation.errors


def test_missing_sandbox_blocks_by_default() -> None:
    validation = validate_preconditions(
        memory_manifest_id="manifest",
        write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id="rollback",
        sandbox_transaction_id=None,
    )

    assert validation.valid is False
    assert "sandbox_transaction_proof_required" in validation.errors


def test_expired_request_blocks() -> None:
    expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    validation = validate_preconditions(
        memory_manifest_id="manifest",
        write_plan_id="plan",
        backup_plan_id="backup",
        rollback_plan_id="rollback",
        sandbox_transaction_id="sandbox",
        expires_at=expires_at,
    )

    assert validation.valid is False
    assert "operator_confirmation_request_expired" in validation.errors
