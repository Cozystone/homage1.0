from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from .models import LocalMemorySandboxBackup
from .store import compute_store_hash, ensure_sandbox_path, init_sandbox_store


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def backup_sandbox_store(sandbox_path: Path | str, backup_path: Path | str) -> LocalMemorySandboxBackup:
    sandbox = init_sandbox_store(sandbox_path)
    backup = ensure_sandbox_path(backup_path)
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(sandbox, backup)
    store_hash = compute_store_hash(sandbox)
    backup_hash = compute_store_hash(backup)
    return LocalMemorySandboxBackup(
        backup_id=_stable_id("local_memory_sandbox_backup", {"sandbox": str(sandbox), "backup": str(backup), "hash": store_hash}),
        sandbox_path=str(sandbox),
        backup_path=str(backup),
        store_hash_before=store_hash,
        backup_hash=backup_hash,
        backup_created=True,
        real_local_brain_write=False,
    )
