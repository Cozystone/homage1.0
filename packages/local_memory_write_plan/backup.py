from __future__ import annotations

import hashlib
import json
from typing import Iterable

from .models import LocalMemoryBackupPlan


DEFAULT_LOCAL_BRAIN_TARGETS = [
    "data/memory/homage.db",
    "data/memory/events.jsonl",
    "data/memory/checkpoints/",
]


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def create_backup_plan(
    *,
    source_manifest_id: str,
    target_paths: Iterable[str] | None = None,
    backup_path: str | None = None,
) -> LocalMemoryBackupPlan:
    """Create dry-run backup metadata only; no filesystem copy is performed."""

    targets = list(target_paths) if target_paths is not None else list(DEFAULT_LOCAL_BRAIN_TARGETS)
    return LocalMemoryBackupPlan(
        backup_plan_id=_stable_id("local_memory_backup", {"manifest": source_manifest_id, "targets": targets, "backup_path": backup_path}),
        target_paths=targets,
        backup_required=True,
        backup_path=backup_path,
        backup_created=False,
        dry_run_only=True,
    )
