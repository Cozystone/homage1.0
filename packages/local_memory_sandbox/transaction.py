from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packages.local_memory_write_plan.models import LocalMemoryWritePlan

from .models import LocalMemoryTransaction
from .store import compute_store_hash, ensure_sandbox_path, init_sandbox_store, write_collection


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def _write_item(write) -> dict[str, object]:
    return {
        "write_id": write.write_id,
        "source_memory_candidate_id": write.source_memory_candidate_id,
        "memory_type": write.memory_type,
        "normalized_summary": write.normalized_summary,
        "source_refs": write.source_refs,
        "sensitivity": write.sensitivity,
        "sandbox_only": True,
    }


def apply_write_plan_to_sandbox(
    write_plan: LocalMemoryWritePlan,
    sandbox_path: Path | str,
    *,
    backup_path: Path | str | None = None,
) -> LocalMemoryTransaction:
    sandbox = init_sandbox_store(sandbox_path)
    if not write_plan.requires_user_approval:
        raise ValueError("source write plan must require user approval")
    if write_plan.apply_enabled or write_plan.local_brain_write or write_plan.local_brain_mutated:
        raise ValueError("source write plan cannot already be applying or mutating")
    if backup_path is not None:
        ensure_sandbox_path(backup_path)
    store_hash_before = compute_store_hash(sandbox)
    for write in write_plan.writes:
        write_collection(sandbox, write.target_collection, _write_item(write))
    store_hash_after = compute_store_hash(sandbox)
    return LocalMemoryTransaction(
        transaction_id=_stable_id(
            "local_memory_sandbox_tx",
            {"plan": write_plan.plan_id, "sandbox": str(sandbox), "before": store_hash_before, "after": store_hash_after},
        ),
        sandbox_path=str(sandbox),
        source_write_plan_id=write_plan.plan_id,
        store_hash_before=store_hash_before,
        store_hash_after=store_hash_after,
        backup_path=str(Path(backup_path).resolve()) if backup_path is not None else "",
        applied=True,
        rolled_back=False,
        real_local_brain_write=False,
    )


def validate_transaction(transaction: LocalMemoryTransaction) -> dict[str, object]:
    ensure_sandbox_path(transaction.sandbox_path)
    errors: list[str] = []
    if transaction.real_local_brain_write:
        errors.append("real_local_brain_write_must_be_false")
    if not transaction.applied:
        errors.append("transaction_not_applied")
    if transaction.store_hash_before == transaction.store_hash_after:
        errors.append("store_hash_did_not_change")
    if not transaction.backup_path:
        errors.append("backup_path_missing")
    return {
        "valid": not errors,
        "errors": errors,
        "real_local_brain_write": False,
        "sandbox_local_brain_write": transaction.applied,
    }
