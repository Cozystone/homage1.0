from __future__ import annotations

import hashlib
import json

from .models import LocalMemoryBackupPlan, LocalMemoryRollbackPlan


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def create_rollback_plan(backup_plan: LocalMemoryBackupPlan) -> LocalMemoryRollbackPlan:
    """Create rollback metadata only; no rollback is executable in this slice."""

    rollback_available = backup_plan.backup_created is True and backup_plan.backup_path is not None
    steps = [
        "Stop future Local Brain writer.",
        "Verify operator confirmation and target Local Brain hash.",
        "Restore files from backup snapshot.",
        "Recompute Local Brain hash and compare with pre-write hash.",
        "Resume only after user confirmation.",
    ]
    if not rollback_available:
        steps.insert(0, "Rollback unavailable in dry-run because no backup snapshot was created.")
    return LocalMemoryRollbackPlan(
        rollback_plan_id=_stable_id("local_memory_rollback", {"backup_plan_id": backup_plan.backup_plan_id}),
        backup_plan_id=backup_plan.backup_plan_id,
        rollback_available=rollback_available,
        rollback_steps=steps,
        rollback_executed=False,
        dry_run_only=True,
    )
