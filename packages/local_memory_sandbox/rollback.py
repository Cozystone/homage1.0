from __future__ import annotations

from pathlib import Path
import shutil

from .models import LocalMemoryRollbackResult, LocalMemoryTransaction
from .store import compute_store_hash, ensure_sandbox_path


def rollback_sandbox_store(transaction: LocalMemoryTransaction) -> LocalMemoryRollbackResult:
    sandbox = ensure_sandbox_path(transaction.sandbox_path)
    backup = ensure_sandbox_path(transaction.backup_path)
    if not backup.exists():
        raise FileNotFoundError(f"missing sandbox backup: {backup}")
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(backup, sandbox)
    restored_hash = compute_store_hash(sandbox)
    return LocalMemoryRollbackResult(
        transaction_id=transaction.transaction_id,
        sandbox_path=str(sandbox),
        backup_path=str(backup),
        store_hash_before=transaction.store_hash_before,
        store_hash_after_rollback=restored_hash,
        rollback_executed=True,
        sandbox_rollback_verified=restored_hash == transaction.store_hash_before,
        real_local_brain_write=False,
    )
