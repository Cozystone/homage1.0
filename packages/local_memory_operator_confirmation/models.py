from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


ConfirmationStatus = Literal["draft", "pending_confirmation", "confirmed", "rejected", "expired", "blocked"]
ConfirmationDecision = Literal["confirm", "reject", "defer"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OperatorConfirmationRequest:
    request_id: str
    source_memory_manifest_id: str
    source_write_plan_id: str
    source_sandbox_transaction_id: str | None
    local_brain_hash_before: str | None
    required_phrase: str
    risk_summary: list[str]
    safety_requirements: dict[str, Any]
    created_at: str
    expires_at: str | None
    status: ConfirmationStatus = "draft"

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("operator confirmation request requires request_id")
        if not self.source_memory_manifest_id:
            raise ValueError("operator confirmation request requires source_memory_manifest_id")
        if not self.source_write_plan_id:
            raise ValueError("operator confirmation request requires source_write_plan_id")
        if not self.required_phrase.strip():
            raise ValueError("operator confirmation request requires required_phrase")
        if self.safety_requirements.get("real_local_brain_write") is not False:
            raise ValueError("real_local_brain_write must remain false")
        if self.safety_requirements.get("memory_apply_enabled") is not False:
            raise ValueError("memory_apply_enabled must remain false")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OperatorConfirmationRequest":
        return cls(**payload)


@dataclass(frozen=True)
class OperatorConfirmationDecision:
    decision_id: str
    request_id: str
    decision: ConfirmationDecision
    typed_phrase: str | None
    phrase_matches: bool
    reviewer: str = "operator"
    notes: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.decision_id or not self.request_id:
            raise ValueError("operator confirmation decision requires ids")
        if self.decision == "confirm" and not self.typed_phrase:
            raise ValueError("confirm decision requires typed_phrase")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OperatorConfirmationDecision":
        return cls(**payload)


@dataclass(frozen=True)
class OperatorConfirmationGateResult:
    request_id: str
    allowed_to_prepare_real_write: bool
    reasons: list[str]
    required_next_gates: list[str]
    allowed_to_apply_real_write: bool = False
    apply_enabled: bool = False
    local_brain_write: bool = False

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("operator confirmation gate result requires request_id")
        if self.allowed_to_apply_real_write or self.apply_enabled or self.local_brain_write:
            raise ValueError("operator confirmation never enables real apply in this slice")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OperatorConfirmationGateResult":
        return cls(**payload)
