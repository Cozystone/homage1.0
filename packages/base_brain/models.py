from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


BASE_BRAIN_ROOT = Path("data/base_brain")
SEED_PATH = BASE_BRAIN_ROOT / "seed" / "seed_graph_v2.json"
SEMANTIC_PATH = BASE_BRAIN_ROOT / "semantic_packs" / "general_semantic_v0.json"
SURFACE_PATH = BASE_BRAIN_ROOT / "surface_packs" / "general_surface_v0.json"
PACK_PATH = BASE_BRAIN_ROOT / "packs" / "atanor_base_brain_v0.json"
BENCHMARK_PATH = BASE_BRAIN_ROOT / "benchmark" / "zero_user_general_v0.json"
PROOF_JSON_PATH = BASE_BRAIN_ROOT / "proofs" / "base_brain_proof.json"
PROOF_MD_PATH = BASE_BRAIN_ROOT / "proofs" / "base_brain_proof.md"

Language = Literal["ko", "en"]
AudienceLevel = Literal["beginner", "intermediate", "expert"]
AnswerMode = Literal["default", "trace", "research"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_base_dirs() -> None:
    for path in [
        BASE_BRAIN_ROOT / "seed",
        BASE_BRAIN_ROOT / "semantic_packs",
        BASE_BRAIN_ROOT / "surface_packs",
        BASE_BRAIN_ROOT / "packs",
        BASE_BRAIN_ROOT / "proofs",
        BASE_BRAIN_ROOT / "benchmark",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def honesty_flags() -> dict[str, bool]:
    return {
        "local_user_brain_used": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "external_web_used": False,
        "cloud_decoder_used": False,
    }


@dataclass(slots=True)
class SemanticRelation:
    source: str
    relation: str
    target: str
    confidence: float = 0.75
    source_type: str = "curated_base_pack"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SemanticConcept:
    concept_id: str
    canonical_name: str
    aliases: list[str]
    short_description: str
    relations: list[SemanticRelation] = field(default_factory=list)
    confidence: float = 0.75
    source_type: str = "curated_base_pack"
    provenance: str = "ATANOR Base Brain v0"
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["relations"] = [relation.to_dict() for relation in self.relations]
        return payload


@dataclass(slots=True)
class SurfaceConstruction:
    construction_id: str
    language: Language
    function: str
    abstract_shape: str
    allowed_discourse_moves: list[str]
    tone: str
    audience_level: AudienceLevel
    slot_types: list[str]
    prior_weight: float
    avoid_repetition_group: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BaseBrainPack:
    pack_id: str
    version: str
    metadata: dict[str, Any]
    seed_graph: dict[str, Any]
    semantic_graph: dict[str, Any]
    surface_graph: dict[str, Any]
    benchmark: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
