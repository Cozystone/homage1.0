from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LocalMemorySandboxBackup:
    backup_id: str
    sandbox_path: str
    backup_path: str
    store_hash_before: str
    backup_hash: str
    backup_created: bool
    real_local_brain_write: bool = False

    def __post_init__(self) -> None:
        if not self.backup_created:
            raise ValueError("sandbox backup proof requires created temp backup")
        if self.real_local_brain_write:
            raise ValueError("sandbox backup cannot write real Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalMemoryTransaction:
    transaction_id: str
    sandbox_path: str
    source_write_plan_id: str
    store_hash_before: str
    store_hash_after: str
    backup_path: str
    applied: bool
    rolled_back: bool
    real_local_brain_write: bool = False

    def __post_init__(self) -> None:
        if not self.transaction_id or not self.sandbox_path or not self.source_write_plan_id:
            raise ValueError("transaction requires ids and sandbox path")
        if self.real_local_brain_write:
            raise ValueError("sandbox transaction cannot write real Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalMemoryRollbackResult:
    transaction_id: str
    sandbox_path: str
    backup_path: str
    store_hash_before: str
    store_hash_after_rollback: str
    rollback_executed: bool
    sandbox_rollback_verified: bool
    real_local_brain_write: bool = False

    def __post_init__(self) -> None:
        if self.real_local_brain_write:
            raise ValueError("sandbox rollback cannot write real Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
