from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


BRAIN_GRAPH_ROOT = Path("data/brain_graph")
PROOF_ROOT = BRAIN_GRAPH_ROOT / "proofs"
PROOF_JSON_PATH = PROOF_ROOT / "tab_aware_brain_graph_proof.json"
PROOF_MD_PATH = PROOF_ROOT / "tab_aware_brain_graph_proof.md"

BrainGraphView = Literal["local", "cloud"]

LOCAL_LAYERS = [
    "local_user",
    "working_memory_local",
    "local_base",
    "seed",
    "local_memory_candidate",
]

CLOUD_LAYERS = [
    "semantic_cloud",
    "cloud_attached",
    "graph_cartridge",
    "contributor",
    "working_memory_cloud",
    "surface_trace_summary",
]

DEFAULT_LOCAL_LAYERS = ["local_user", "working_memory_local", "local_base"]
DEFAULT_CLOUD_LAYERS = ["cloud_attached", "graph_cartridge", "working_memory_cloud", "semantic_cloud", "surface_trace_summary"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_brain_graph_dirs() -> None:
    for path in [BRAIN_GRAPH_ROOT, PROOF_ROOT, BRAIN_GRAPH_ROOT / "renders", BRAIN_GRAPH_ROOT / "status"]:
        path.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class RenderableBrainNode:
    id: str
    label: str
    layer: str
    source_scope: str
    persistent: bool
    temporary: bool
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    kind: str = "concept"
    trust_state: str = "unknown"
    verification_state: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Manual dict (not dataclasses.asdict): asdict deep-recurses into metadata and was
        # ~46% of aggregate_brain_graph. This is a read-only serialization path, so the
        # metadata dict is referenced, not deep-copied. ~10x faster per node.
        return {
            "id": self.id, "label": self.label, "layer": self.layer,
            "source_scope": self.source_scope, "persistent": self.persistent,
            "temporary": self.temporary, "x": self.x, "y": self.y, "z": self.z,
            "kind": self.kind, "trust_state": self.trust_state,
            "verification_state": self.verification_state, "metadata": self.metadata,
        }


@dataclass(slots=True)
class RenderableBrainEdge:
    id: str
    source: str
    target: str
    relation: str
    layer: str
    source_scope: str
    persistent: bool
    temporary: bool
    weight: float = 1.0
    trust_state: str = "unknown"
    verification_state: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "source": self.source, "target": self.target,
            "relation": self.relation, "layer": self.layer, "source_scope": self.source_scope,
            "persistent": self.persistent, "temporary": self.temporary, "weight": self.weight,
            "trust_state": self.trust_state, "verification_state": self.verification_state,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class LayerResult:
    layer: str
    available: bool
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    side_panel: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    missing_reason: str | None = None
    partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        # nodes/edges are already plain dicts; reference them (asdict deep-copied every one).
        return {
            "layer": self.layer, "available": self.available, "nodes": self.nodes,
            "edges": self.edges, "side_panel": self.side_panel, "stats": self.stats,
            "missing_reason": self.missing_reason, "partial": self.partial,
        }
