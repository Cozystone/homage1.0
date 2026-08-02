from __future__ import annotations

from .models import LocalMemoryRollbackResult, LocalMemorySandboxBackup, LocalMemoryTransaction
from .store import ensure_sandbox_path


def validate_sandbox_cycle(
    backup: LocalMemorySandboxBackup,
    transaction: LocalMemoryTransaction,
    rollback: LocalMemoryRollbackResult,
) -> dict[str, object]:
    errors: list[str] = []
    ensure_sandbox_path(backup.sandbox_path)
    ensure_sandbox_path(transaction.sandbox_path)
    ensure_sandbox_path(rollback.sandbox_path)
    if backup.store_hash_before != transaction.store_hash_before:
        errors.append("backup_hash_does_not_match_transaction_before")
    if backup.backup_hash != backup.store_hash_before:
        errors.append("backup_copy_hash_mismatch")
    if transaction.store_hash_before == transaction.store_hash_after:
        errors.append("transaction_hash_did_not_change")
    if not rollback.sandbox_rollback_verified:
        errors.append("rollback_not_verified")
    if rollback.store_hash_after_rollback != transaction.store_hash_before:
        errors.append("rollback_hash_not_restored")
    if backup.real_local_brain_write or transaction.real_local_brain_write or rollback.real_local_brain_write:
        errors.append("real_local_brain_write_detected")
    return {
        "valid": not errors,
        "errors": errors,
        "real_local_brain_write": False,
        "sandbox_local_brain_write": transaction.applied,
        "sandbox_rollback_verified": rollback.sandbox_rollback_verified,
    }
