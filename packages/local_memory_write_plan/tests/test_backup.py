from __future__ import annotations

from packages.local_memory_write_plan.backup import create_backup_plan


def test_backup_plan_is_metadata_only() -> None:
    plan = create_backup_plan(source_manifest_id="manifest-1")

    assert plan.backup_required is True
    assert plan.backup_created is False
    assert plan.dry_run_only is True
    assert "data/memory/homage.db" in plan.target_paths


def test_backup_plan_can_use_unknown_targets() -> None:
    plan = create_backup_plan(source_manifest_id="manifest-1", target_paths=[])

    assert plan.target_paths == []
    assert plan.backup_created is False
