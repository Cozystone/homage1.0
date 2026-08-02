from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Layer = Literal["local_persistent", "seed_anchor", "cloud_attached", "working_memory"]
SourceScope = Literal["local", "seed", "cloud"]
ConsolidationState = Literal["transient", "candidate", "crystal", "persistent"]
CrystalType = Literal["explanation", "planning", "analogy", "debug", "product_strategy"]
VerificationState = Literal["candidate", "verified", "rejected"]
SelfQuestionStatus = Literal["pending", "answered_with_evidence", "rejected_no_evidence"]
SelfQuestionSource = Literal["uncertainty", "contradiction", "weak_edge", "missing_evidence", "novelty_gap"]


@dataclass
class NodeNeuralState:
    node_id: str
    layer: Layer
    activation: float = 0.0
    inhibition: float = 0.0
    salience: float = 0.0
    novelty: float = 0.0
    fatigue: float = 0.0
    prediction_error: float = 0.0
    trust: float = 0.0
    source_scope: SourceScope = "local"
    temporary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EdgeNeuralState:
    edge_id: str
    source: str
    relation: str
    target: str
    weight: float = 0.0
    excitatory: bool = True
    inhibitory: bool = False
    plasticity: float = 0.0
    recent_use: float = 0.0
    decay_rate: float = 0.02
    trust: float = 0.0
    prediction_error: float = 0.0
    consolidation_state: ConsolidationState = "transient"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GlobalWorkspaceFrame:
    frame_id: str
    query: str
    active_nodes: list[dict[str, Any]] = field(default_factory=list)
    active_edges: list[dict[str, Any]] = field(default_factory=list)
    seed_anchors: list[dict[str, Any]] = field(default_factory=list)
    cloud_attached_nodes: list[dict[str, Any]] = field(default_factory=list)
    salience_top_k: list[dict[str, Any]] = field(default_factory=list)
    local_write: bool = False
    external_llm_used: bool = False
    external_sllm_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PredictionTrace:
    trace_id: str
    query: str
    expected_paths: list[dict[str, Any]] = field(default_factory=list)
    observed_paths: list[dict[str, Any]] = field(default_factory=list)
    prediction_errors: list[dict[str, Any]] = field(default_factory=list)
    strengthened_edges: list[dict[str, Any]] = field(default_factory=list)
    weakened_edges: list[dict[str, Any]] = field(default_factory=list)
    unverified_hypotheses: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeCrystal:
    crystal_id: str
    crystal_type: CrystalType
    trigger_concepts: list[str] = field(default_factory=list)
    reasoning_path: list[dict[str, Any]] = field(default_factory=list)
    source_trace: list[dict[str, Any]] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    reuse_score: float = 0.0
    verification_state: VerificationState = "candidate"
    created_from_self_generated_output: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SelfQuestion:
    question_id: str
    question: str
    generated_from: SelfQuestionSource
    related_concepts: list[str] = field(default_factory=list)
    requires_evidence: bool = True
    status: SelfQuestionStatus = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
