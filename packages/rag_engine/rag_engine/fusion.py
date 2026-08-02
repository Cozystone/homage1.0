from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


PRIVATE_QUERY_PATTERNS = (
    r"\bmy\b",
    r"\bprivate\b",
    r"\bpersonal\b",
    r"\bdiary\b",
    r"\bsecret\b",
    r"\blocal\s+only\b",
    r"\bair[- ]?gapped\b",
    r"내\s",
    r"나의",
    r"개인",
    r"비밀",
    r"일기",
    r"로컬\s*전용",
)


@dataclass(frozen=True)
class LocalBrainSignals:
    local_density_score: float = 0.0
    evidence_score: float = 0.0
    edge_confidence_score: float = 0.0
    repeated_use_score: float = 0.0
    lexical_overlap_score: float = 0.0
    temporal_freshness_score: float = 0.0
    matched_local_nodes: int = 0
    matched_local_edges: int = 0
    evidence_document_count: int = 0
    local_answer_confidence: float = 0.0
    query_is_private: bool = False
    relevant_local_facts_validated: bool = False
    cloud_fragment_valid: bool = True
    runtime_mode: str = "normal"


@dataclass(frozen=True)
class CloudFragmentLimits:
    cloud_max_nodes: int
    cloud_max_edges: int
    max_bytes: int

    def to_dict(self) -> dict[str, int]:
        return {
            "cloud_max_nodes": self.cloud_max_nodes,
            "cloud_max_edges": self.cloud_max_edges,
            "max_bytes": self.max_bytes,
        }


@dataclass(frozen=True)
class FusionRatio:
    local_weight: float
    cloud_weight: float
    reason: str
    local_brain_strength_score: float
    cloud_fragment_policy: str
    stage: str
    cloud_fragment_limits: CloudFragmentLimits

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_weight": round(self.local_weight, 3),
            "cloud_weight": round(self.cloud_weight, 3),
            "local": round(self.local_weight, 3),
            "cloud": round(self.cloud_weight, 3),
            "reason": self.reason,
            "stage": self.stage,
            "local_brain_strength_score": round(self.local_brain_strength_score, 3),
            "cloud_fragment_policy": self.cloud_fragment_policy,
            "cloud_fragment_limits": self.cloud_fragment_limits.to_dict(),
        }


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if math.isnan(value) or math.isinf(value):
        return minimum
    return max(minimum, min(maximum, value))


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^0-9A-Za-z가-힣_-]+", text.lower()) if len(token) > 1}


def is_private_query(query: str) -> bool:
    normalized = query.strip().lower()
    return any(re.search(pattern, normalized) for pattern in PRIVATE_QUERY_PATTERNS)


def local_density_score(
    nodes: list[dict[str, Any]] | None,
    edges: list[dict[str, Any]] | None,
    evidence_docs: list[dict[str, Any]] | None,
) -> float:
    nodes = nodes or []
    edges = edges or []
    evidence_docs = evidence_docs or []
    node_density = min(1.0, len(nodes) / 32)
    edge_density = min(1.0, len(edges) / 96)
    evidence_density = min(1.0, len(evidence_docs) / 8)
    return round(_clamp(node_density * 0.3 + edge_density * 0.45 + evidence_density * 0.25), 3)


def _confidence_score(edges: list[dict[str, Any]]) -> float:
    values = []
    for edge in edges:
        value = edge.get("confidence", edge.get("weight", edge.get("score")))
        if isinstance(value, (int, float)):
            values.append(_clamp(float(value)))
    return _avg(values)


def _repeated_use_score(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> float:
    counts = []
    for item in [*nodes, *edges]:
        value = item.get("count", item.get("usage_count", item.get("memory_weight", item.get("weight"))))
        if isinstance(value, (int, float)):
            counts.append(float(value))
    if not counts:
        return 0.0
    normalized = [min(1.0, math.log1p(max(0.0, count)) / math.log1p(80.0)) for count in counts]
    return _avg(normalized)


def _lexical_overlap_score(query: str, docs: list[dict[str, Any]]) -> float:
    query_tokens = _tokens(query)
    if not query_tokens or not docs:
        return 0.0
    doc_tokens: set[str] = set()
    for doc in docs:
        doc_tokens |= _tokens(str(doc.get("text") or doc.get("snippet") or doc.get("raw_text") or ""))
    if not doc_tokens:
        return 0.0
    return len(query_tokens & doc_tokens) / max(1, len(query_tokens))


def _temporal_freshness_score(docs: list[dict[str, Any]]) -> float:
    weights = []
    for doc in docs:
        temporal = doc.get("temporal") if isinstance(doc.get("temporal"), dict) else {}
        value = temporal.get("combined_weight") or temporal.get("freshness") or doc.get("temporal_weight") or doc.get("score")
        if isinstance(value, (int, float)):
            weights.append(_clamp(float(value) / 1.5))
    return max(weights) if weights else 0.0


def local_brain_signals_from_context(
    *,
    query: str,
    matched_nodes: list[dict[str, Any]] | None = None,
    matched_edges: list[dict[str, Any]] | None = None,
    evidence_docs: list[dict[str, Any]] | None = None,
    local_answer_confidence: float = 0.0,
    runtime_mode: str = "normal",
    cloud_fragment_valid: bool = True,
    relevant_local_facts_validated: bool = False,
) -> LocalBrainSignals:
    nodes = matched_nodes or []
    edges = matched_edges or []
    docs = evidence_docs or []
    return LocalBrainSignals(
        local_density_score=local_density_score(nodes, edges, docs),
        evidence_score=min(1.0, len(docs) / 6),
        edge_confidence_score=_confidence_score(edges),
        repeated_use_score=_repeated_use_score(nodes, edges),
        lexical_overlap_score=_lexical_overlap_score(query, docs),
        temporal_freshness_score=_temporal_freshness_score(docs),
        matched_local_nodes=len(nodes),
        matched_local_edges=len(edges),
        evidence_document_count=len(docs),
        local_answer_confidence=_clamp(float(local_answer_confidence or 0.0)),
        query_is_private=is_private_query(query),
        relevant_local_facts_validated=relevant_local_facts_validated,
        cloud_fragment_valid=cloud_fragment_valid,
        runtime_mode=runtime_mode,
    )


def compute_local_brain_strength_score(signals: LocalBrainSignals) -> float:
    score = (
        _clamp(signals.local_density_score) * 0.25
        + _clamp(signals.evidence_score) * 0.20
        + _clamp(signals.edge_confidence_score) * 0.20
        + _clamp(signals.repeated_use_score) * 0.15
        + _clamp(signals.lexical_overlap_score) * 0.10
        + _clamp(signals.temporal_freshness_score) * 0.10
    )
    if signals.relevant_local_facts_validated:
        score += 0.05
    if signals.local_answer_confidence:
        score = score * 0.75 + _clamp(signals.local_answer_confidence) * 0.25
    if signals.matched_local_nodes == 0 and signals.matched_local_edges == 0 and signals.evidence_document_count == 0:
        score = min(score, 0.05)
    return round(_clamp(score), 3)


def _stage_for_strength(strength: float, cloud_weight: float) -> tuple[str, str]:
    if cloud_weight == 0.0 and strength >= 0.97:
        return "sovereign_local_brain", "sovereign_local_confidence"
    if strength < 0.18:
        return "cold_start", "cold_start_local_sparse"
    if strength < 0.40:
        return "early_local_brain", "early_local_growth"
    if strength < 0.70:
        return "growing_local_brain", "moderate_local_density"
    if strength < 0.92:
        return "mature_local_brain", "strong_local_density"
    return "sovereign_local_brain", "high_local_confidence"


def _fragment_limits(stage: str, runtime_mode: str) -> CloudFragmentLimits:
    mode = runtime_mode.strip().lower()
    if mode == "survival_brain":
        return CloudFragmentLimits(32, 96, 128 * 1024)
    if mode == "low_memory_brain":
        return CloudFragmentLimits(64, 192, 256 * 1024)
    if stage == "mature_local_brain" or stage == "sovereign_local_brain":
        return CloudFragmentLimits(32, 64, 128 * 1024)
    if stage == "growing_local_brain":
        return CloudFragmentLimits(96, 256, 384 * 1024)
    return CloudFragmentLimits(128, 384, 512 * 1024)


def compute_adaptive_fusion_ratio(signals: LocalBrainSignals) -> FusionRatio:
    strength = compute_local_brain_strength_score(signals)
    cloud_weight = _clamp(1.0 - strength, 0.0, 0.9)

    if signals.query_is_private:
        cloud_weight = 0.0
    if not signals.cloud_fragment_valid:
        cloud_weight = 0.0
    if signals.local_answer_confidence > 0.97:
        cloud_weight = 0.0
    elif signals.local_answer_confidence > 0.90:
        cloud_weight = min(cloud_weight, 0.10)

    stage, reason = _stage_for_strength(strength, cloud_weight)
    if signals.query_is_private:
        reason = "private_query_local_only"
    elif not signals.cloud_fragment_valid:
        reason = "cloud_fragment_validation_failed"

    runtime_mode = signals.runtime_mode.strip().lower()
    if cloud_weight <= 0:
        policy = "disabled"
    elif runtime_mode == "survival_brain":
        policy = "tiny_metadata_summary_fragments_only"
    elif runtime_mode == "low_memory_brain":
        policy = "bounded_low_memory_fragments_only"
    else:
        policy = "temporary_working_memory_only"

    local_weight = 1.0 - cloud_weight
    return FusionRatio(
        local_weight=round(local_weight, 3),
        cloud_weight=round(cloud_weight, 3),
        reason=reason,
        local_brain_strength_score=strength,
        cloud_fragment_policy=policy,
        stage=stage,
        cloud_fragment_limits=_fragment_limits(stage, runtime_mode),
    )


def route_ratio(local_density: float, **kwargs: Any) -> dict[str, Any]:
    signals = LocalBrainSignals(local_density_score=_clamp(float(local_density)), **kwargs)
    return compute_adaptive_fusion_ratio(signals).to_dict()


def fusion_ratio_from_context(
    *,
    query: str,
    matched_nodes: list[dict[str, Any]] | None = None,
    matched_edges: list[dict[str, Any]] | None = None,
    evidence_docs: list[dict[str, Any]] | None = None,
    local_answer_confidence: float = 0.0,
    runtime_mode: str = "normal",
    cloud_fragment_valid: bool = True,
    relevant_local_facts_validated: bool = False,
) -> dict[str, Any]:
    signals = local_brain_signals_from_context(
        query=query,
        matched_nodes=matched_nodes,
        matched_edges=matched_edges,
        evidence_docs=evidence_docs,
        local_answer_confidence=local_answer_confidence,
        runtime_mode=runtime_mode,
        cloud_fragment_valid=cloud_fragment_valid,
        relevant_local_facts_validated=relevant_local_facts_validated,
    )
    return compute_adaptive_fusion_ratio(signals).to_dict()


def _doc_key(doc: dict[str, Any], fallback_rank: int) -> str:
    return str(doc.get("chunk_id") or doc.get("id") or doc.get("url") or doc.get("path") or f"doc-{fallback_rank}")


def _priority_score(doc: dict[str, Any], source: str) -> int:
    if source == "local" and doc.get("private"):
        return 50
    if source == "local" and doc.get("validated"):
        return 40
    if source == "local" and float(doc.get("count") or doc.get("usage_count") or 0) > 1:
        return 30
    if source == "cloud" and doc.get("validated"):
        return 20
    if source == "cloud":
        return 10
    return 0


def weighted_rrf(
    local_docs: list[dict[str, Any]] | None,
    cloud_docs: list[dict[str, Any]] | None,
    ratio: dict[str, Any] | FusionRatio | None,
    *,
    k: int = 60,
    limit: int = 8,
) -> list[dict[str, Any]]:
    local_docs = local_docs or []
    cloud_docs = cloud_docs or []
    ratio_dict = ratio.to_dict() if isinstance(ratio, FusionRatio) else (ratio or {"local_weight": 1.0, "cloud_weight": 0.0})
    weights = {
        "local": _clamp(float(ratio_dict.get("local_weight", ratio_dict.get("local", 1.0)))),
        "cloud": _clamp(float(ratio_dict.get("cloud_weight", ratio_dict.get("cloud", 0.0)))),
    }
    scored: dict[str, dict[str, Any]] = {}

    for source, docs in (("local", local_docs), ("cloud", cloud_docs)):
        weight = weights[source]
        if weight <= 0:
            continue
        for rank, doc in enumerate(docs, start=1):
            key = _doc_key(doc, rank)
            rrf = weight / (k + rank)
            confidence_bonus = _clamp(float(doc.get("confidence") or doc.get("score") or 0.0)) * 0.002
            priority = _priority_score(doc, source)
            score = rrf + confidence_bonus + priority
            current = scored.get(key)
            if current is None or score > float(current["fusion_score"]):
                fused = dict(doc)
                fused["fusion_score"] = round(score, 6)
                fused["fusion_source"] = source
                fused["fusion_priority"] = priority
                fused["fusion_ratio"] = {"local": round(weights["local"], 3), "cloud": round(weights["cloud"], 3)}
                scored[key] = fused

    return sorted(scored.values(), key=lambda item: (-float(item.get("fusion_score") or 0), str(_doc_key(item, 0))))[:limit]


def epistemic_uncertainty(local_density: float) -> float:
    return round(1.0 - _clamp(float(local_density)), 3)
