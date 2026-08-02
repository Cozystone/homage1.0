from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


TargetCollection = Literal[
    "preferences",
    "personal_facts",
    "project_context",
    "corrections",
    "task_goals",
    "relationships",
    "sensitive_hold",
]


@dataclass(frozen=True)
class LocalMemoryWriteCandidate:
    write_id: str
    source_memory_candidate_id: str
    memory_type: str
    normalized_summary: str
    target_collection: TargetCollection
    source_refs: list[dict[str, Any]]
    sensitivity: str
    write_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.write_id or not self.source_memory_candidate_id:
            raise ValueError("write candidate requires ids")
        if not self.normalized_summary.strip():
            raise ValueError("write candidate requires normalized_summary")
        if self.write_allowed:
            raise ValueError("write candidates are dry-run only and cannot be write_allowed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LocalMemoryWriteCandidate":
        return cls(**payload)


@dataclass(frozen=True)
class LocalMemoryWritePlan:
    plan_id: str
    source_manifest_id: str
    local_brain_hash_before: str | None
    writes: list[LocalMemoryWriteCandidate]
    skipped: list[dict[str, Any]]
    backup_plan_id: str
    rollback_plan_id: str
    apply_enabled: bool = False
    local_brain_write: bool = False
    local_brain_mutated: bool = False
    requires_user_approval: bool = True

    def __post_init__(self) -> None:
        if not self.plan_id or not self.source_manifest_id:
            raise ValueError("write plan requires ids")
        if self.apply_enabled or self.local_brain_write or self.local_brain_mutated:
            raise ValueError("write plan cannot apply or mutate Local Brain")
        if not self.requires_user_approval:
            raise ValueError("write plan requires user approval")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["writes"] = [write.to_dict() for write in self.writes]
        return payload


@dataclass(frozen=True)
class LocalMemoryBackupPlan:
    backup_plan_id: str
    target_paths: list[str]
    backup_required: bool = True
    backup_path: str | None = None
    backup_created: bool = False
    dry_run_only: bool = True

    def __post_init__(self) -> None:
        if not self.backup_plan_id:
            raise ValueError("backup plan requires id")
        if not self.backup_required:
            raise ValueError("backup is required before future memory writes")
        if self.backup_created:
            raise ValueError("dry-run backup plan cannot create backup")
        if not self.dry_run_only:
            raise ValueError("backup plan must remain dry-run only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalMemoryRollbackPlan:
    rollback_plan_id: str
    backup_plan_id: str
    rollback_available: bool
    rollback_steps: list[str]
    rollback_executed: bool = False
    dry_run_only: bool = True

    def __post_init__(self) -> None:
        if not self.rollback_plan_id or not self.backup_plan_id:
            raise ValueError("rollback plan requires ids")
        if self.rollback_executed:
            raise ValueError("dry-run rollback plan cannot execute rollback")
        if not self.dry_run_only:
            raise ValueError("rollback plan must remain dry-run only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalMemoryWriteValidation:
    valid: bool
    errors: list[str]
    warnings: list[str]
    apply_enabled: bool
    local_brain_write: bool
    required_gates: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
