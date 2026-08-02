from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from packages.cloud_brain.cloud_node_attachment import detach_bundle, graph_overlay
from packages.cloud_brain.semantic_attach import attach_semantic_cloud_for_query


FRONTIER_ROOT = Path("data/working_memory/predictive_frontier")


def _now() -> float:
    return time.time()


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for token in query.replace("?", " ").replace("!", " ").replace(",", " ").split():
        cleaned = token.strip().lower()
        if len(cleaned) >= 2 and cleaned not in terms:
            terms.append(cleaned)
    return terms[:8]


def build_local_graph_request(query: str, *, max_chunks: int = 1, max_latency_ms: int = 800) -> dict[str, Any]:
    terms = _query_terms(query)
    return {
        "request_id": _stable_id("lgr", query, max_chunks, max_latency_ms),
        "query": query,
        "intent": "answer_context",
        "local_context_hash": _stable_id("local_ctx", "empty_private_brain_v0"),
        "needed_concepts": terms,
        "missing_concepts": terms,
        "privacy_level": "private_query_public_chunk_allowed",
        "max_chunks": max(1, int(max_chunks)),
        "max_latency_ms": max(100, int(max_latency_ms)),
        "state": "local_miss",
        "local_write": False,
    }


def _cloud_chunk_from_attach(query: str, attach_result: dict[str, Any], expires_at: float) -> dict[str, Any] | None:
    nodes = list(attach_result.get("attached_nodes") or [])
    edges = list(attach_result.get("attached_edges") or [])
    if not nodes:
        return None
    query_lower = query.lower()
    terms = _query_terms(query)
    relevant = False
    for node in nodes:
        label = str(node.get("label") or node.get("concept_id") or node.get("id")).lower().strip()
        if any(term == label or (len(label) >= 4 and term.startswith(label)) for term in terms):
            relevant = True
            break
        if any(len(term) >= 4 and term in label for term in terms):
            relevant = True
            break
    if not relevant:
        return None
    chunk_id = str(attach_result.get("bundle_id") or _stable_id("cgch", query, len(nodes), len(edges)))
    authoritative_for_answer = bool(nodes) and all(
        isinstance(node, dict)
        and node.get("authoritative_for_answer") is True
        and node.get("independent_source_attestation") is True
        for node in nodes
    )
    return {
        "chunk_id": chunk_id,
        "source": "cloud_brain",
        "semantic_nodes": nodes,
        "relations": edges,
        "evidence_refs": sorted({str(node.get("source_hash") or node.get("source_text_hash") or "") for node in nodes if node.get("source_hash") or node.get("source_text_hash")}),
        "confidence": 0.72,
        "expires_at": expires_at,
        "temporary": True,
        "local_write": False,
        "is_semantic_node": False,
        "represents_node_count": len(nodes),
        "verification_state": "temporary_working_memory",
        "independent_source_attestation": authoritative_for_answer,
        "authoritative_for_answer": authoritative_for_answer,
    }


def _empty_evidence_bundle(query: str, source: str = "web") -> dict[str, Any]:
    return {
        "bundle_id": _stable_id("evb", source, query),
        "source": source,
        "urls": [],
        "source_ids": [],
        "snippets": [],
        "fetched_at": _now(),
        "trust_score": 0.0,
        "extraction_status": "not_configured",
        "temporary": True,
        "verified": False,
        "attached_to_working_memory": False,
        "local_write": False,
    }


def _candidate_from_evidence(evidence_bundle: dict[str, Any]) -> dict[str, Any] | None:
    if not evidence_bundle.get("snippets"):
        return None
    return {
        "fragment_id": _stable_id("cand", evidence_bundle.get("bundle_id")),
        "source_bundle_id": evidence_bundle.get("bundle_id"),
        "proposed_nodes": [],
        "proposed_relations": [],
        "verification_status": "pending",
        "not_promoted_by_default": True,
        "local_write": False,
    }


def _write_frontier_tasks(query: str, concepts: list[str], ttl_seconds: int = 900) -> list[dict[str, Any]]:
    FRONTIER_ROOT.mkdir(parents=True, exist_ok=True)
    expires_at = _now() + ttl_seconds
    tasks: list[dict[str, Any]] = []
    for concept in concepts[:6]:
        task = {
            "task_id": _stable_id("pf", query, concept),
            "query": query,
            "concept": concept,
            "state": "prepared_pending_evidence",
            "temporary": True,
            "verified": False,
            "expires_at": expires_at,
            "is_semantic_node": False,
            "local_write": False,
        }
        tasks.append(task)
    if tasks:
        path = FRONTIER_ROOT / f"frontier_{_stable_id('run', query)}.jsonl"
        path.write_text("\n".join(json.dumps(task, ensure_ascii=False, sort_keys=True) for task in tasks), encoding="utf-8")
    return tasks


def run_local_cloud_exchange(
    query: str,
    *,
    pin_context: bool = False,
    allow_web: bool = False,
    max_chunks: int = 1,
    max_latency_ms: int = 800,
    ttl_seconds: int = 1800,
) -> dict[str, Any]:
    started = _now()
    local_request = build_local_graph_request(query, max_chunks=max_chunks, max_latency_ms=max_latency_ms)
    expires_at = started + ttl_seconds
    states = ["local_miss"]
    attach_result = attach_semantic_cloud_for_query(query, limit=max(1, max_chunks * 8))
    cloud_chunk = _cloud_chunk_from_attach(query, attach_result, expires_at)
    bundle_id = str(attach_result.get("bundle_id") or "")
    if cloud_chunk:
        overlay_after_attach = graph_overlay()
        states.extend(["cloud_hit", "working_memory_attached"])
    else:
        if bundle_id:
            detach_bundle(bundle_id)
        overlay_after_attach = graph_overlay()
        states.append("cloud_miss")

    evidence_bundle = None
    candidate_fragment = None
    if not cloud_chunk and allow_web:
        evidence_bundle = _empty_evidence_bundle(query, source="web")
        states.append("web_evidence_unavailable")
        candidate_fragment = _candidate_from_evidence(evidence_bundle)
        if candidate_fragment:
            states.append("candidate_pending")

    concepts = [
        str(node.get("label") or node.get("concept_id") or node.get("id"))
        for node in (cloud_chunk or {}).get("semantic_nodes", [])
        if node
    ] or local_request["missing_concepts"]
    frontier_tasks = _write_frontier_tasks(query, concepts)

    detach_result = None
    if cloud_chunk and bundle_id and not pin_context:
        detach_result = detach_bundle(bundle_id)
        states.append("auto_detached")
    elif cloud_chunk and bundle_id:
        states.append("pinned")

    overlay_final = graph_overlay()
    return {
        "exchange_id": _stable_id("lcx", query, started),
        "query": query,
        "states": states,
        "local_graph_request": local_request,
        "cloud_graph_chunk": cloud_chunk,
        "evidence_bundle": evidence_bundle,
        "candidate_fragment": candidate_fragment,
        "predictive_frontier": {
            "tasks": frontier_tasks,
            "count": len(frontier_tasks),
            "ttl_seconds": 900,
            "creates_permanent_nodes": False,
        },
        "working_memory": {
            "overlay_after_attach": overlay_after_attach,
            "overlay_final": overlay_final,
            "auto_detached": bool(detach_result),
            "pinned": bool(bundle_id and pin_context),
            "temporary_context_count": int((overlay_after_attach.get("working_memory_overlay") or {}).get("cloud_attached_nodes") or 0),
            "local_write": False,
        },
        "promotion": {
            "cloud_promotion": "manual_required",
            "verified_cloud_fragment": False,
            "candidate_pending": candidate_fragment is not None,
        },
        "truth": {
            "fake_nodes": False,
            "fake_counts": False,
            "full_store_scan": False,
            "pair_edges_sent": 0,
            "candidate_pairs_implicit": True,
            "local_brain_write": False,
            "web_results_faked": False,
        },
        "duration_ms": round((_now() - started) * 1000, 2),
    }
