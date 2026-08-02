from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Language = Literal["ko", "en", "mixed", "unknown"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8", errors="ignore")).hexdigest()


def detect_language(text: str) -> Language:
    has_ko = bool(re.search(r"[\uac00-\ud7a3]", text or ""))
    has_en = bool(re.search(r"[A-Za-z]", text or ""))
    if has_ko and has_en:
        return "mixed"
    if has_ko:
        return "ko"
    if has_en:
        return "en"
    return "unknown"


def honesty_flags() -> dict[str, bool]:
    return {
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "real_quantum_hardware_used": False,
        "quantum_inspired_only": True,
        "surface_graph_overrides_semantic_truth": False,
    }


@dataclass(slots=True)
class SourceSentence:
    source_id: str
    source_hash: str
    text: str
    language: Language
    url: str | None = None
    title: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)
    license: str = "unknown"
    usage_allowed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_text_stored: bool = False
    raw_text_policy: str = "hash_only"

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        source_id: str | None = None,
        url: str | None = None,
        title: str | None = None,
        license: str = "unknown",
        usage_allowed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "SourceSentence":
        normalized = normalize_text(text)
        source_hash = hash_text(normalized)
        return cls(
            source_id=source_id or f"src_{source_hash[:16]}",
            source_hash=source_hash,
            text=normalized,
            language=detect_language(normalized),
            url=url,
            title=title,
            license=license,
            usage_allowed=usage_allowed,
            metadata=metadata or {},
        )

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_text:
            payload.pop("text", None)
        return payload


@dataclass(slots=True)
class SemanticProjection:
    projection_id: str
    source_hash: str
    concepts: list[str]
    entities: list[str]
    claims: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    trust_score: float
    extraction_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SurfaceProjection:
    projection_id: str
    source_hash: str
    language: Language
    discourse_moves: list[str]
    constructions: list[str]
    phrase_patterns: list[str]
    lemma_choices: dict[str, list[str]]
    style_features: dict[str, Any]
    register: str
    tone: str
    sentence_shape: str
    repair_patterns: list[str]
    extraction_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConstructionCandidate:
    construction_id: str
    language: Language
    pattern_family: str
    abstract_form: str
    semantic_function: str
    slots: list[str]
    examples_hashes: list[str] = field(default_factory=list)
    fit_score: float = 0.5
    style_score: float = 0.5
    language_score: float = 0.5
    repetition_penalty: float = 0.0
    prior_success_weight: float = 0.5
    user_preference_weight: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SurfacePlan:
    plan_id: str
    intent: str
    language: Language
    audience_level: str
    message_order: list[str]
    selected_discourse_moves: list[str]
    selected_constructions: list[dict[str, Any]]
    selected_lemma_choices: dict[str, str]
    style_profile: dict[str, Any]
    q_cortex_used: bool
    q_cortex_run_id: str | None
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RealizedAnswer:
    answer: str
    language: Language
    surface_plan_id: str
    semantic_sources: list[str]
    surface_sources: list[str]
    confidence: float
    trace_summary: dict[str, Any]
    repair: dict[str, Any] = field(default_factory=dict)
    honesty: dict[str, bool] = field(default_factory=honesty_flags)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
