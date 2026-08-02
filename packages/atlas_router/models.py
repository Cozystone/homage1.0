from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


NodeType = Literal[
    "local_brain",
    "working_memory",
    "cloud_brain",
    "graph_hub",
    "cartridge",
    "atlas_peer",
    "broker",
    "public_source",
]

PrivacyLevel = Literal["public", "restricted", "private"]


def _validate_unit_interval(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


def _validate_non_negative(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return numeric


@dataclass(frozen=True)
class TrustRouteNode:
    node_id: str
    node_type: NodeType
    label: str
    trust_score: float
    privacy_level: PrivacyLevel
    region: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if not self.label:
            raise ValueError("label is required")
        object.__setattr__(self, "trust_score", _validate_unit_interval("trust_score", self.trust_score))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrustRouteEdge:
    edge_id: str
    source_id: str
    target_id: str
    latency_ms: float
    bandwidth_cost: float
    trust_penalty: float
    license_risk: float
    privacy_risk: float
    stale_data_risk: float
    compute_cost: float
    failure_risk: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.edge_id:
            raise ValueError("edge_id is required")
        if not self.source_id or not self.target_id:
            raise ValueError("source_id and target_id are required")
        object.__setattr__(self, "latency_ms", _validate_non_negative("latency_ms", self.latency_ms))
        object.__setattr__(self, "bandwidth_cost", _validate_non_negative("bandwidth_cost", self.bandwidth_cost))
        object.__setattr__(self, "compute_cost", _validate_non_negative("compute_cost", self.compute_cost))
        for name in ("trust_penalty", "license_risk", "privacy_risk", "stale_data_risk", "failure_risk"):
            object.__setattr__(self, name, _validate_unit_interval(name, getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrustRoutePolicy:
    max_privacy_risk: float = 0.2
    max_license_risk: float = 0.2
    require_public_only: bool = True
    prefer_local: bool = True
    allow_atlas_peers: bool = True
    allow_cloud_brain: bool = True
    allow_graph_hub: bool = True
    allow_private_nodes: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_privacy_risk", _validate_unit_interval("max_privacy_risk", self.max_privacy_risk))
        object.__setattr__(self, "max_license_risk", _validate_unit_interval("max_license_risk", self.max_license_risk))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrustRouteResult:
    source_id: str
    target_id: str
    path: list[str]
    edge_ids: list[str]
    total_cost: float
    blocked_edges: list[dict[str, Any]]
    reasons: list[str]
    policy: dict[str, Any]
    safe_to_attach_to_working_memory: bool
    safe_to_write_local_brain: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "total_cost", _validate_non_negative("total_cost", self.total_cost))
        object.__setattr__(self, "safe_to_write_local_brain", False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

