from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _unit_interval(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class SandboxPeer:
    peer_id: str
    role: str
    trust_score: float
    privacy_grade: str
    online: bool
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.peer_id:
            raise ValueError("peer_id is required")
        object.__setattr__(self, "trust_score", _unit_interval("trust_score", self.trust_score))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SandboxCartridge:
    cartridge_id: str
    content_hash: str
    public_only: bool
    privacy_grade: str
    license_hint: str
    semantic_tags: list[str]
    payload_summary: str
    raw_payload_included: bool = False

    def __post_init__(self) -> None:
        if not self.cartridge_id:
            raise ValueError("cartridge_id is required")
        if not self.content_hash:
            raise ValueError("content_hash is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExchangeResult:
    accepted: bool
    rejected_reason: str | None
    routed_by: str
    safe_for_working_memory: bool
    safe_for_local_brain: bool = False
    real_p2p_used: bool = False
    raw_private_data_exported: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.safe_for_local_brain:
            raise ValueError("sandbox exchange cannot write Local Brain")
        if self.real_p2p_used:
            raise ValueError("sandbox exchange cannot use real P2P")
        if self.raw_private_data_exported:
            raise ValueError("sandbox exchange cannot export raw private data")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
