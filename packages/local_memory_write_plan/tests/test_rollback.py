from __future__ import annotations

from packages.local_memory_write_plan.backup import create_backup_plan
from packages.local_memory_write_plan.rollback import create_rollback_plan


def test_rollback_is_not_available_without_created_backup() -> None:
    backup = create_backup_plan(source_manifest_id="manifest-1")
    rollback = create_rollback_plan(backup)

    assert rollback.rollback_available is False
    assert rollback.rollback_executed is False
    assert rollback.dry_run_only is True
    assert "Rollback unavailable" in rollback.rollback_steps[0]
