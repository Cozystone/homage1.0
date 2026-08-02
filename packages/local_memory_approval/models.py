from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


SourceType = Literal[
    "user_text",
    "voice_transcript",
    "selfhood_runtime_proposal",
    "morning_brief",
    "project_fact",
    "preference",
    "correction",
]
MemoryType = Literal[
    "preference",
    "personal_fact",
    "project_context",
    "correction",
    "task_goal",
    "relationship",
    "sensitive",
    "unknown",
]
Sensitivity = Literal["public", "personal", "sensitive", "secret"]
MemoryDecision = Literal[
    "approve_for_future_memory_manifest",
    "reject",
    "defer",
    "edit_required",
    "sensitive_block",
]
SessionStatus = Literal["draft", "in_review", "completed", "blocked"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    source_type: SourceType
    raw_text: str
    normalized_summary: str
    memory_type: MemoryType
    sensitivity: Sensitivity
    confidence: float
    source_refs: list[dict[str, Any]]
    created_at: str
    requires_user_approval: bool = True
    local_brain_write: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("memory candidate requires candidate_id")
        if not self.raw_text.strip() or not self.normalized_summary.strip():
            raise ValueError("memory candidate requires text and summary")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.requires_user_approval:
            raise ValueError("memory candidates must require user approval")
        if self.local_brain_write:
            raise ValueError("memory candidates cannot write Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryCandidate":
        return cls(**payload)


@dataclass(frozen=True)
class MemoryApprovalDecision:
    decision_id: str
    candidate_id: str
    decision: MemoryDecision
    reviewer: str = "user"
    edited_summary: str | None = None
    notes: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    applied_to_local_brain: bool = False

    def __post_init__(self) -> None:
        if not self.decision_id or not self.candidate_id:
            raise ValueError("memory approval decision requires decision_id and candidate_id")
        if self.applied_to_local_brain:
            raise ValueError("memory approval decisions cannot be applied to Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryApprovalDecision":
        return cls(**payload)


@dataclass(frozen=True)
class MemoryApprovalSession:
    session_id: str
    candidates: list[MemoryCandidate]
    decisions: list[MemoryApprovalDecision] = field(default_factory=list)
    status: SessionStatus = "draft"
    local_brain_mutated: bool = False
    production_store_mutated: bool = False

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("memory approval session requires session_id")
        if self.local_brain_mutated or self.production_store_mutated:
            raise ValueError("memory approval sessions cannot mutate Local Brain or production")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        payload["decisions"] = [decision.to_dict() for decision in self.decisions]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryApprovalSession":
        data = dict(payload)
        data["candidates"] = [MemoryCandidate.from_dict(item) for item in data.get("candidates", [])]
        data["decisions"] = [MemoryApprovalDecision.from_dict(item) for item in data.get("decisions", [])]
        return cls(**data)


@dataclass(frozen=True)
class MemoryManifestDraft:
    manifest_id: str
    source_session_id: str
    approved_candidate_ids: list[str]
    rejected_candidate_ids: list[str]
    deferred_candidate_ids: list[str]
    local_brain_hash_before: str | None
    created_at: str
    canonical_hash: str
    approved_memory_summaries: dict[str, str] = field(default_factory=dict)
    signed: bool = False
    signature: str | None = None
    signer_id: str | None = None
    ready_for_memory_write: bool = False
    apply_enabled: bool = False
    local_brain_write: bool = False

    def __post_init__(self) -> None:
        if not self.manifest_id or not self.source_session_id:
            raise ValueError("memory manifest draft requires ids")
        if self.ready_for_memory_write or self.apply_enabled or self.local_brain_write:
            raise ValueError("memory manifest draft cannot be ready, apply-enabled, or writing")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryManifestDraft":
        return cls(**payload)
