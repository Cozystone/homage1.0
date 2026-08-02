from __future__ import annotations

import pytest

from packages.local_memory_write_plan.models import (
    LocalMemoryBackupPlan,
    LocalMemoryRollbackPlan,
    LocalMemoryWriteCandidate,
    LocalMemoryWritePlan,
)


def test_write_candidate_rejects_write_allowed() -> None:
    with pytest.raises(ValueError, match="dry-run only"):
        LocalMemoryWriteCandidate(
            write_id="w1",
            source_memory_candidate_id="m1",
            memory_type="preference",
            normalized_summary="short answers",
            target_collection="preferences",
            source_refs=[{"ref": "local"}],
            sensitivity="personal",
            write_allowed=True,
        )


def test_write_plan_rejects_apply_enabled() -> None:
    with pytest.raises(ValueError, match="cannot apply"):
        LocalMemoryWritePlan(
            plan_id="p1",
            source_manifest_id="m1",
            local_brain_hash_before=None,
            writes=[],
            skipped=[],
            backup_plan_id="b1",
            rollback_plan_id="r1",
            apply_enabled=True,
        )


def test_backup_and_rollback_remain_dry_run() -> None:
    with pytest.raises(ValueError, match="cannot create backup"):
        LocalMemoryBackupPlan("b1", [], backup_created=True)
    with pytest.raises(ValueError, match="cannot execute rollback"):
        LocalMemoryRollbackPlan("r1", "b1", rollback_available=True, rollback_steps=[], rollback_executed=True)
