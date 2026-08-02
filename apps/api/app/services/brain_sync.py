from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.services.network_config import NetworkConfig


PrivacyLevel = Literal["public", "internal", "private"]
VerificationStatus = Literal["local_preview", "verified", "unverified", "rejected"]

PATCH_SCHEMA_VERSION = "atanor.graph-patch.v1"
FRAGMENT_SCHEMA_VERSION = "atanor.cloud-fragment.v1"

PRIVATE_FIELD_NAMES = {
    "raw_text",
    "text",
    "content",
    "body",
    "message",
    "messages",
    "chat",
    "chat_message",
    "local_path",
    "path",
    "file_path",
    "payload",
    "payload_text",
    "private_payload",
    "document",
    "source_text",
}

CALLER_AUTHORITY_FIELD_NAMES = {
    "authority",
    "checksum",
    "expires_at",
    "freshness",
    "freshness_score",
    "priority",
    "provenance_status",
    "server_bound_provenance",
    "signature",
    "source_bindings",
    "status",
    "trust_score",
    "ttl_seconds",
    "verification_status",
    "verified",
}

ATTACHMENT_RECORD_FIELDS = {
    "attached_at",
    "permanent_local_brain_write",
    "storage_layer",
}

PRIVATE_QUERY_HINTS = (
    "private",
    "personal",
    "secret",
    "diary",
    "local only",
    "air-gapped",
    "\uac1c\uc778",
    "\ube44\ubc00",
    "\uc77c\uae30",
    "\ub85c\uceec \uc804\uc6a9",
    "\ub0b4 ",
    "\ub098\uc758",
)


def _utc_seconds() -> int:
    return int(time.time())


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if math.isnan(value) or math.isinf(value):
        return minimum
    return max(minimum, min(maximum, value))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _fragment_checksum(fragment: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in fragment.items()
        if key != "checksum" and key not in ATTACHMENT_RECORD_FIELDS
    }
    return _sha256(payload)


def fragment_checksum_valid(fragment: dict[str, Any]) -> bool:
    supplied = str(fragment.get("checksum") or "")
    return bool(supplied) and hmac.compare_digest(_fragment_checksum(fragment), supplied)


def _safe_id(value: Any, fallback_prefix: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return f"{fallback_prefix}-{uuid.uuid4().hex[:12]}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    source = _safe_id(edge.get("source") or edge.get("source_id") or edge.get("source_hash"), "source")
    target = _safe_id(edge.get("target") or edge.get("target_id") or edge.get("target_hash"), "target")
    relation = str(edge.get("relation") or edge.get("predicate") or edge.get("type") or "related_to")
    return source, relation, target


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in PRIVATE_FIELD_NAMES:
                continue
            clean[str(key)] = sanitize_metadata(item)
        return clean
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def sanitize_untrusted_fragment_metadata(value: Any) -> Any:
    sanitized = sanitize_metadata(value)
    if isinstance(sanitized, dict):
        return {
            str(key): sanitize_untrusted_fragment_metadata(item)
            for key, item in sanitized.items()
            if str(key).strip().lower() not in CALLER_AUTHORITY_FIELD_NAMES
        }
    if isinstance(sanitized, list):
        return [sanitize_untrusted_fragment_metadata(item) for item in sanitized]
    return sanitized


def sanitize_patch_node(node: dict[str, Any]) -> dict[str, Any]:
    concept_id = _safe_id(node.get("concept_id") or node.get("id") or node.get("node_hash"), "concept")
    return {
        "concept_id": concept_id,
        "node_hash": str(node.get("node_hash") or hashlib.sha256(concept_id.encode("utf-8")).hexdigest()),
        "type": str(node.get("type") or "concept"),
        "confidence": round(_clamp(_safe_float(node.get("confidence"), 0.5)), 4),
    }


def sanitize_patch_edge(edge: dict[str, Any], *, include_weight: bool = True) -> dict[str, Any]:
    source, relation, target = _edge_key(edge)
    clean: dict[str, Any] = {
        "source_id": source,
        "relation": relation,
        "target_id": target,
        "confidence": round(_clamp(_safe_float(edge.get("confidence"), _safe_float(edge.get("weight"), 0.5))), 4),
    }
    if include_weight:
        clean["weight"] = round(_safe_float(edge.get("weight"), 0.0), 6)
    if edge.get("source_type"):
        clean["source_type"] = str(edge["source_type"])
    return clean


def classify_privacy(query: str | None = None, explicit: str | None = None) -> PrivacyLevel:
    if explicit in {"public", "internal", "private"}:
        return explicit  # type: ignore[return-value]
    normalized = (query or "").strip().lower()
    if any(hint in normalized for hint in PRIVATE_QUERY_HINTS):
        return "private"
    return "public"


@dataclass(frozen=True)
class PatchLimits:
    max_nodes: int = 512
    max_edges: int = 2048
    max_bytes: int = 512 * 1024


@dataclass(frozen=True)
class FragmentLimits:
    max_nodes: int = 128
    max_edges: int = 384
    max_bytes: int = 512 * 1024
    ttl_seconds: int = 900
    max_depth: int = 3
    allowed_source_types: tuple[str, ...] = ("public_web", "public_docs", "cloud_verified", "operator_seed")

    @classmethod
    def from_config(cls, config: NetworkConfig | None = None) -> "FragmentLimits":
        resolved = config or NetworkConfig.from_env()
        return cls(
            max_nodes=min(256, max(1, int(resolved.max_nodes))),
            max_edges=min(1024, max(1, int(resolved.max_edges))),
            max_bytes=min(1024 * 1024, max(32 * 1024, int(resolved.max_fragment_bytes))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_nodes": self.max_nodes,
            "max_edges": self.max_edges,
            "max_bytes": self.max_bytes,
            "ttl_seconds": self.ttl_seconds,
            "max_depth": self.max_depth,
            "allowed_source_types": list(self.allowed_source_types),
        }


@dataclass(frozen=True)
class FragmentDecision:
    local_weight: float
    cloud_weight: float
    local_confidence: float
    graph_density: float
    privacy_level: PrivacyLevel
    cloud_allowed: bool
    fragment_requested: bool
    fragment_reason: str
    runtime_mode: str
    limits: FragmentLimits

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_weight": round(self.local_weight, 3),
            "cloud_weight": round(self.cloud_weight, 3),
            "local_confidence": round(self.local_confidence, 3),
            "graph_density": round(self.graph_density, 3),
            "privacy_level": self.privacy_level,
            "cloud_allowed": self.cloud_allowed,
            "fragment_requested": self.fragment_requested,
            "fragment_reason": self.fragment_reason,
            "runtime_mode": self.runtime_mode,
            "limits": self.limits.to_dict(),
        }


class GraphDeltaCompressor:
    def __init__(self, limits: PatchLimits | None = None) -> None:
        self.limits = limits or PatchLimits()

    def compress(
        self,
        previous_snapshot: dict[str, Any] | None,
        current_snapshot: dict[str, Any],
        *,
        privacy_level: PrivacyLevel = "public",
        origin_brain_id: str = "local-brain",
        parent_snapshot_id: str | None = None,
        created_by_learning_run_id: str | None = None,
        source_type: str = "local_learning_run",
        trust_score: float = 0.6,
    ) -> dict[str, Any]:
        previous_nodes = {
            _safe_id(node.get("concept_id") or node.get("id") or node.get("node_hash"), "concept"): node
            for node in (previous_snapshot or {}).get("nodes", [])
            if isinstance(node, dict)
        }
        current_nodes = {
            _safe_id(node.get("concept_id") or node.get("id") or node.get("node_hash"), "concept"): node
            for node in current_snapshot.get("nodes", [])
            if isinstance(node, dict)
        }
        previous_edges = {
            _edge_key(edge): edge
            for edge in (previous_snapshot or {}).get("edges", [])
            if isinstance(edge, dict)
        }
        current_edges = {
            _edge_key(edge): edge
            for edge in current_snapshot.get("edges", [])
            if isinstance(edge, dict)
        }

        nodes_added = [
            sanitize_patch_node(node)
            for node_id, node in current_nodes.items()
            if node_id not in previous_nodes
        ][: self.limits.max_nodes]

        edges_added: list[dict[str, Any]] = []
        edges_strengthened: list[dict[str, Any]] = []
        edges_weakened: list[dict[str, Any]] = []
        for key, edge in current_edges.items():
            if key not in previous_edges:
                edges_added.append(sanitize_patch_edge(edge))
                continue
            previous_weight = _safe_float(previous_edges[key].get("weight"), _safe_float(previous_edges[key].get("confidence"), 0.0))
            current_weight = _safe_float(edge.get("weight"), _safe_float(edge.get("confidence"), previous_weight))
            delta = round(current_weight - previous_weight, 6)
            if delta > 0.000001:
                clean = sanitize_patch_edge(edge, include_weight=False)
                clean["weight_delta"] = delta
                edges_strengthened.append(clean)
            elif delta < -0.000001:
                clean = sanitize_patch_edge(edge, include_weight=False)
                clean["weight_delta"] = delta
                edges_weakened.append(clean)

        edges_added = edges_added[: self.limits.max_edges]
        remaining = max(0, self.limits.max_edges - len(edges_added))
        edges_strengthened = edges_strengthened[:remaining]
        remaining = max(0, self.limits.max_edges - len(edges_added) - len(edges_strengthened))
        edges_weakened = edges_weakened[:remaining]

        concepts_merged = sanitize_metadata(current_snapshot.get("concepts_merged") or [])
        aliases_added = [
            {"alias_hash": hashlib.sha256(str(alias).encode("utf-8")).hexdigest()}
            for alias in (current_snapshot.get("aliases_added") or [])
        ][:128]
        sources_quarantined = [
            {"source_hash": hashlib.sha256(str(source).encode("utf-8")).hexdigest()}
            for source in (current_snapshot.get("sources_quarantined") or [])
        ][:128]

        patch: dict[str, Any] = {
            "schema_version": PATCH_SCHEMA_VERSION,
            "patch_id": f"patch-{uuid.uuid4().hex}",
            "origin_brain_id": origin_brain_id,
            "created_at": _utc_seconds(),
            "parent_snapshot_id": parent_snapshot_id,
            "created_by_learning_run_id": created_by_learning_run_id,
            "privacy_level": privacy_level,
            "shareable": privacy_level == "public",
            "verification_status": "local_preview",
            "source_type": source_type,
            "source_hash": _sha256({"source_type": source_type, "parent_snapshot_id": parent_snapshot_id}),
            "trust_score": round(_clamp(trust_score), 4),
            "deltas": {
                "nodes_added": nodes_added,
                "edges_added": edges_added,
                "edges_strengthened": edges_strengthened,
                "edges_weakened": edges_weakened,
                "concepts_merged": concepts_merged,
                "aliases_added": aliases_added,
                "sources_quarantined": sources_quarantined,
                "confidence_delta": round(_safe_float(current_snapshot.get("confidence"), 0.0) - _safe_float((previous_snapshot or {}).get("confidence"), 0.0), 6),
                "trust_delta": round(_safe_float(current_snapshot.get("trust_score"), trust_score) - _safe_float((previous_snapshot or {}).get("trust_score"), trust_score), 6),
            },
            "limits": asdict(self.limits),
        }
        patch["patch_sha256"] = _sha256(patch)
        if len(_canonical_bytes(patch)) > self.limits.max_bytes:
            patch["deltas"]["edges_added"] = []
            patch["deltas"]["edges_strengthened"] = []
            patch["deltas"]["edges_weakened"] = []
            patch["truncated"] = True
            patch["patch_sha256"] = _sha256(patch)
        assert_patch_safe(patch)
        return patch


class FragmentOrchestrator:
    def __init__(self, limits: FragmentLimits | None = None) -> None:
        self.limits = limits or FragmentLimits.from_config()

    def decide(
        self,
        *,
        query: str,
        local_confidence: float = 0.0,
        graph_density: float = 0.0,
        evidence_available: bool = False,
        runtime_mode: str = "normal",
        ram_pressure: float = 0.0,
        cloud_allowed: bool = True,
        privacy_level: PrivacyLevel | None = None,
    ) -> FragmentDecision:
        privacy = classify_privacy(query, privacy_level)
        confidence = _clamp(local_confidence)
        density = _clamp(graph_density)
        pressure = _clamp(ram_pressure)
        allowed = bool(cloud_allowed) and privacy != "private"

        if not allowed:
            cloud_weight = 0.0
            reason = "private_query_local_only" if privacy == "private" else "cloud_disabled_by_policy"
        else:
            cloud_weight = _clamp(0.7 - density * 0.7, 0.0, 0.7)
            cloud_weight *= 1.0 - confidence * 0.75
            if evidence_available and confidence >= 0.55:
                cloud_weight *= 0.45
            if confidence >= 0.90:
                cloud_weight = min(cloud_weight, 0.08)
            if pressure >= 0.75 or runtime_mode in {"low_memory_brain", "survival_brain"}:
                cloud_weight *= 0.35
            cloud_weight = _clamp(cloud_weight, 0.0, 0.7)
            if cloud_weight <= 0.03:
                reason = "local_brain_sufficient"
            elif confidence < 0.25 and density < 0.30:
                reason = "cold_start_public_fragment"
            elif pressure >= 0.75:
                reason = "resource_pressure_small_hint_only"
            else:
                reason = "bounded_public_fragment_assist"

        return FragmentDecision(
            local_weight=round(1.0 - cloud_weight, 3),
            cloud_weight=round(cloud_weight, 3),
            local_confidence=confidence,
            graph_density=density,
            privacy_level=privacy,
            cloud_allowed=allowed,
            fragment_requested=cloud_weight > 0.05,
            fragment_reason=reason,
            runtime_mode=runtime_mode,
            limits=self.limits,
        )


class BoundedFragmentAssembler:
    def __init__(self, limits: FragmentLimits | None = None) -> None:
        self.limits = limits or FragmentLimits.from_config()

    def assemble(
        self,
        *,
        concept_ids: list[str],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        evidence_summaries: list[dict[str, Any]] | None = None,
        source_metadata: dict[str, Any] | None = None,
        trust_score: float = 0.5,
        origin_brain_id: str = "cloud-brain",
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        try:
            requested_ttl = int(ttl_seconds) if ttl_seconds is not None else self.limits.ttl_seconds
        except (TypeError, ValueError):
            requested_ttl = self.limits.ttl_seconds
        ttl = max(1, min(self.limits.ttl_seconds, requested_ttl))
        fragment = {
            "schema_version": FRAGMENT_SCHEMA_VERSION,
            "fragment_id": f"fragment-{uuid.uuid4().hex}",
            "origin_brain_id": origin_brain_id,
            "created_at": _utc_seconds(),
            "expires_at": _utc_seconds() + max(1, ttl),
            "privacy_level": "public",
            "verification_status": "unverified",
            "trust_score": round(_clamp(trust_score), 4),
            "priority": "cloud_unverified",
            "server_bound_provenance": False,
            "authority": "none",
            "concept_ids": [str(item) for item in concept_ids[: self.limits.max_nodes]],
            "nodes": [sanitize_patch_node(node) for node in nodes[: self.limits.max_nodes]],
            "edges": [sanitize_patch_edge(edge) for edge in edges[: self.limits.max_edges]],
            "evidence_summaries": sanitize_untrusted_fragment_metadata(evidence_summaries or [])[:32],
            "source_metadata": sanitize_untrusted_fragment_metadata(source_metadata or {}),
            "limits": self.limits.to_dict(),
            "attach_policy": "working_memory_only",
            "promotion_required": True,
            "checksum_authority": "integrity_only",
        }
        fragment["checksum"] = _fragment_checksum(fragment)
        if len(_canonical_bytes(fragment)) > self.limits.max_bytes:
            fragment["evidence_summaries"] = []
            fragment["truncated"] = True
            fragment["checksum"] = _fragment_checksum(fragment)
        return fragment


class WorkingMemoryFragmentStore:
    def __init__(self, limits: FragmentLimits | None = None) -> None:
        self.limits = limits or FragmentLimits.from_config()
        self._assembler = BoundedFragmentAssembler(self.limits)
        self._fragments: dict[str, dict[str, Any]] = {}

    def attach(self, fragment: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(fragment, dict):
            raise ValueError("fragment must be an object")
        schema_version = str(fragment.get("schema_version") or "")
        if schema_version != FRAGMENT_SCHEMA_VERSION:
            raise ValueError("unsupported fragment schema")

        concept_ids = fragment.get("concept_ids") or []
        nodes = fragment.get("nodes") or []
        edges = fragment.get("edges") or []
        evidence_summaries = fragment.get("evidence_summaries") or []
        source_metadata = fragment.get("source_metadata") or {}
        if not isinstance(concept_ids, list):
            raise ValueError("fragment concept_ids must be a list")
        if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
            raise ValueError("fragment nodes must be a list of objects")
        if not isinstance(edges, list) or not all(isinstance(edge, dict) for edge in edges):
            raise ValueError("fragment edges must be a list of objects")
        if not isinstance(evidence_summaries, list):
            raise ValueError("fragment evidence_summaries must be a list")
        if not isinstance(source_metadata, dict):
            raise ValueError("fragment source_metadata must be an object")
        if len(concept_ids) > self.limits.max_nodes or len(nodes) > self.limits.max_nodes:
            raise ValueError("fragment nodes exceed server limit")
        if len(edges) > self.limits.max_edges:
            raise ValueError("fragment edges exceed server limit")
        try:
            inbound_size = len(_canonical_bytes(fragment))
        except (TypeError, ValueError) as exc:
            raise ValueError("fragment must be canonically serializable") from exc
        if inbound_size > self.limits.max_bytes:
            raise ValueError("fragment exceeds max_bytes")
        if not fragment_checksum_valid(fragment):
            raise ValueError("invalid fragment checksum")

        now = _utc_seconds()
        requested_ttl = self.limits.ttl_seconds
        if fragment.get("expires_at") is not None:
            try:
                supplied_expiry = int(fragment["expires_at"])
            except (TypeError, ValueError) as exc:
                raise ValueError("fragment expires_at must be an integer") from exc
            if supplied_expiry <= now:
                raise ValueError("fragment has expired")
            requested_ttl = supplied_expiry - now
        elif fragment.get("ttl_seconds") is not None:
            try:
                requested_ttl = int(fragment["ttl_seconds"])
            except (TypeError, ValueError) as exc:
                raise ValueError("fragment ttl_seconds must be an integer") from exc

        canonical = self._assembler.assemble(
            concept_ids=[str(item) for item in concept_ids],
            nodes=nodes,
            edges=edges,
            evidence_summaries=evidence_summaries,
            source_metadata=source_metadata,
            trust_score=0.0,
            origin_brain_id="public-api",
            ttl_seconds=max(1, min(self.limits.ttl_seconds, requested_ttl)),
        )
        submitted_id = str(fragment.get("fragment_id") or "").strip()
        if submitted_id and submitted_id not in self._fragments and fragment_checksum_valid(fragment):
            # A valid self-checksum may preserve a correlation ID, but never
            # verification, trust, priority, expiry, or provenance authority.
            canonical["fragment_id"] = submitted_id
            canonical["checksum"] = _fragment_checksum(canonical)
        if len(_canonical_bytes(canonical)) > self.limits.max_bytes:
            raise ValueError("canonical fragment exceeds max_bytes")
        if not fragment_checksum_valid(canonical):  # pragma: no cover - internal invariant
            raise ValueError("canonical fragment checksum failed")

        record = {
            **canonical,
            "attached_at": _utc_seconds(),
            "storage_layer": "working_memory",
            "permanent_local_brain_write": False,
        }
        self._fragments[str(record["fragment_id"])] = record
        self.prune_expired()
        return record

    def prune_expired(self) -> int:
        now = _utc_seconds()
        expired = [key for key, value in self._fragments.items() if int(value.get("expires_at") or 0) <= now]
        for key in expired:
            self._fragments.pop(key, None)
        return len(expired)

    def active(self) -> list[dict[str, Any]]:
        self.prune_expired()
        return list(self._fragments.values())


def assert_patch_safe(patch: dict[str, Any]) -> None:
    serialized = json.dumps(patch, ensure_ascii=False).lower()
    for field_name in PRIVATE_FIELD_NAMES:
        if f'"{field_name}"' in serialized:
            raise ValueError(f"private field leaked into graph patch: {field_name}")


def resolve_conflict(local_record: dict[str, Any], cloud_record: dict[str, Any]) -> dict[str, Any]:
    """Fail closed for raw records without independently bound provenance.

    Both arguments are caller-controlled dictionaries on the public API.
    Fields such as ``priority``, ``verified``, or
    ``server_bound_provenance`` therefore cannot authenticate themselves.
    """
    return {
        "winner": None,
        "authoritative_winner": False,
        "reason": "no_server_bound_provenance",
        "local_priority": 0,
        "cloud_priority": 0,
        "selected": None,
        "caller_priority_ignored": True,
    }


graph_delta_compressor = GraphDeltaCompressor()
fragment_orchestrator = FragmentOrchestrator()
bounded_fragment_assembler = BoundedFragmentAssembler()
working_memory_fragments = WorkingMemoryFragmentStore()
