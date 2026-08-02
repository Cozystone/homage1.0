from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DEVICE_ROLES = {"main_brain", "mobile_window", "tablet_window", "relay_node", "archive_node", "test_peer"}
PRIVACY_GRADES = {"public", "synthetic", "private_local_only"}
TOPIC_STATUSES = {"proposed", "deliberating", "synthesized", "blocked", "review_required"}
SPEAKER_ROLES = {"skeptic", "builder", "privacy_guard", "router", "domain_expert", "synthesis_chair"}
CHECKOUT_REASONS = {"predicted_shutdown", "manual_checkout", "backup", "test_only"}
MERGE_MODES = {"metadata_only", "proposal_only", "rejected"}
SYNC_STATUSES = {"idle", "checkout_ready", "checked_out", "checkin_available", "syncing", "conflict", "blocked"}


def _require_range(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def _require_choice(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}")


@dataclass(frozen=True)
class EgoDevice:
    device_id: str
    label: str
    device_role: str
    trust_level: float
    online: bool
    last_seen_at: str | None
    capabilities: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_choice("device_role", self.device_role, DEVICE_ROLES)
        _require_range("trust_level", self.trust_level)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SeedIdentity:
    did: str
    public_fingerprint: str
    seed_phrase_hash: str
    created_at: str
    proof_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EgoCartridge:
    cartridge_id: str
    owner_did: str
    content_hash: str
    version: int
    size_bytes: int
    created_at: str
    world_model_hash: str
    self_model_hash: str
    privacy_grade: str
    raw_private_data_included: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be >= 0")
        _require_choice("privacy_grade", self.privacy_grade, PRIVACY_GRADES)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MidnightCongressTopic:
    topic_id: str
    title: str
    deficit_type: str
    source_deficit_ids: list[str]
    public_only: bool
    privacy_grade: str
    status: str

    def __post_init__(self) -> None:
        _require_choice("privacy_grade", self.privacy_grade, PRIVACY_GRADES)
        _require_choice("status", self.status, TOPIC_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CongressArgument:
    argument_id: str
    topic_id: str
    speaker_role: str
    claim: str
    evidence_refs: list[str]
    confidence: float
    objections: list[str]

    def __post_init__(self) -> None:
        _require_choice("speaker_role", self.speaker_role, SPEAKER_ROLES)
        _require_range("confidence", self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CongressSynthesis:
    synthesis_id: str
    topic_id: str
    summary: str
    recommendations: list[str]
    proposed_cartridge_id: str | None
    requires_user_approval: bool = True
    mutates_production: bool = False
    mutates_local_brain: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckoutRequest:
    request_id: str
    owner_did: str
    device_id: str
    cartridge_id: str
    target_relay: str
    reason: str
    dry_run: bool = True

    def __post_init__(self) -> None:
        _require_choice("reason", self.reason, CHECKOUT_REASONS)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckinResult:
    result_id: str
    owner_did: str
    local_device_id: str
    remote_cartridge_id: str
    merged: bool
    merge_mode: str
    local_brain_mutated: bool = False
    production_mutated: bool = False
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_choice("merge_mode", self.merge_mode, MERGE_MODES)
        if self.local_brain_mutated or self.production_mutated:
            raise ValueError("proof checkin cannot mutate Local Brain or production")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConstellationState:
    owner_did: str
    devices: list[EgoDevice]
    latest_cartridge_hash: str | None
    sync_status: str
    conflicts: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_choice("sync_status", self.sync_status, SYNC_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
