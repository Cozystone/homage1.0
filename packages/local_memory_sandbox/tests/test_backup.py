from __future__ import annotations

from packages.local_memory_sandbox.backup import backup_sandbox_store
from packages.local_memory_sandbox.store import compute_store_hash, init_sandbox_store, write_collection


def test_backup_copies_temp_sandbox_and_hashes_match(tmp_path) -> None:
    sandbox = init_sandbox_store(tmp_path / "sandbox")
    write_collection(sandbox, "preferences", {"normalized_summary": "prefers short answers", "sensitivity": "personal"})
    backup = backup_sandbox_store(sandbox, tmp_path / "backup")

    assert backup.backup_created is True
    assert backup.real_local_brain_write is False
    assert backup.store_hash_before == compute_store_hash(sandbox)
    assert backup.backup_hash == compute_store_hash(tmp_path / "backup")
