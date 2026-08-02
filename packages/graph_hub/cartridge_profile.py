from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


InspectionStatus = Literal["passed", "rejected", "review_required"]
TrialState = Literal["active", "exhausted", "detached", "expired", "failed"]


@dataclass(frozen=True)
class LODChunkFingerprint:
    chunk_id: str
    node_count: int
    relation_count: int
    routing_hash: str
    is_graph_node: bool = False


@dataclass(frozen=True)
class CartridgeCentroid:
    label: str
    degree: int
    risk: str = "normal"


@dataclass(frozen=True)
class GraphSoundnessIssue:
    issue_id: str
    severity: Literal["info", "review", "blocker"]
    message: str


@dataclass(frozen=True)
class PhaseRoutingProbe:
    query: str
    visited_nodes: int
    max_depth: int
    terminated_by_attenuation: bool
    pair_edges_sent: int = 0


@dataclass(frozen=True)
class CartridgeProfile:
    cartridge_id: str
    namespace: str
    name: str
    version: str
    domain: str
    node_count: int
    relation_count: int
    chunk_count: int
    centroid_nodes: list[dict[str, Any]]
    semantic_tags: list[str]
    structural_toc: list[str]
    sqc_dictionary_hash: str
    phase_index_hash: str
    merkle_root: str
    signature_status: str
    read_only: bool
    created_at: str


@dataclass(frozen=True)
class ProfilerReport:
    cartridge_id: str
    inspection_status: InspectionStatus
    ontology_tags: list[str]
    centroid_summary: list[dict[str, Any]]
    structural_toc: list[str]
    soundness_score: float
    topology_health_score: float
    malicious_pattern_risk: float
    issues: list[dict[str, Any]]
    simulated_queries: list[dict[str, Any]]
    pair_edges_sent: int
    full_load_performed: bool
    recommendation: str


@dataclass(frozen=True)
class SynergyMatchResult:
    local_fingerprint_hash: str
    cartridge_fingerprint_hash: str
    constructive_interference_pct: float
    conflict_node_pct: float
    overlap_score: float
    novelty_score: float
    predicted_latency_ms: int
    recommended_active_chunks: int
    risk_flags: list[str]
    explanation: str
    safe_to_trial: bool


@dataclass(frozen=True)
class WorkingMemoryOverlayRef:
    overlay_id: str
    temporary: bool
    local_write: bool
    cloud_merge: bool


@dataclass(frozen=True)
class TrialAttachment:
    cartridge_id: str
    attached_chunks: list[dict[str, Any]]
    working_memory_overlay_id: str
    local_write: bool
    cloud_merge: bool
    pair_edges_sent: int


@dataclass(frozen=True)
class SandboxQueryResult:
    query: str
    answer: str
    materialized_nodes: int
    materialized_edges: int
    remaining_queries: int
    local_write: bool
    cloud_merge: bool
    pair_edges_sent: int
    latency_ms: float


@dataclass(frozen=True)
class SandboxTrialSession:
    session_id: str
    cartridge_id: str
    user_local_fingerprint_hash: str
    remaining_queries: int
    attached_chunks: list[dict[str, Any]]
    working_memory_overlay_id: str
    state: TrialState
    local_write: bool
    cloud_merge: bool
    started_at: str
    expires_at: str
    query_results: list[dict[str, Any]]
    cleanup_status: str


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
