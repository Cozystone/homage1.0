from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.brain_graph_state import build_brain_graph_states
from knowledge_bakery import daemon_status, memory_status
from seed_research import current_viewer_export
from seed_research.cloud_fragment_alignment import align_public_candidate_fragments
from seed_research.prove_cloud_fragment_alignment import write_cloud_fragment_alignment_proof
from seed_research.runtime_anchor import resolve_seed_concepts


router = APIRouter(prefix="/api/seed-research", tags=["seed-research"])


class RuntimeTraceRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


def _local_brain_state() -> dict[str, Any]:
    daemon = daemon_status()
    memory = memory_status()
    states = build_brain_graph_states(daemon=daemon, memory=memory)
    local = states.get("local", {})
    return {
        "local_brain_initialized": bool(local.get("local_brain_initialized")),
        "local_total_nodes": int(local.get("local_total_nodes") or 0),
        "local_total_edges": int(local.get("local_total_relations") or local.get("local_total_edges") or 0),
    }


def _alignment_summary_from_proof(proof: dict[str, Any] | None, *, proof_exists: bool) -> dict[str, Any]:
    summary = (proof or {}).get("summary", {}) if isinstance(proof, dict) else {}
    claims = (proof or {}).get("claims", {}) if isinstance(proof, dict) else {}
    alignment = (proof or {}).get("alignment", {}) if isinstance(proof, dict) else {}
    return {
        "proof_exists": proof_exists,
        "candidate_fragments_checked": int(summary.get("candidate_fragments_checked") or 0),
        "public_fragments_checked": int(summary.get("public_fragments_checked") or 0),
        "rejected_private_fragments": int(summary.get("rejected_private_fragments") or 0),
        "fragments_aligned_to_seed": int(summary.get("fragments_aligned_to_seed") or 0),
        "concepts_aligned_total": int(summary.get("concepts_aligned_total") or 0),
        "edges_aligned_total": int(summary.get("edges_aligned_total") or 0),
        "matched_fragment_ids": alignment.get("matched_fragment_ids", []),
        "local_brain_state": _local_brain_state(),
        "external_llm_used": bool(claims.get("external_llm_used", False)),
        "external_sllm_used": bool(claims.get("external_sllm_used", False)),
        "rule_based_answer_engine": bool(claims.get("rule_based_answer_engine", False)),
        "final_answer_generation_claimed": bool(claims.get("final_answer_generation_claimed", False)),
        "claim": "Public Cloud candidate fragments can align to Seed Graph concepts and relations as retrieval/verification anchors.",
    }


def _latest_alignment_summary() -> dict[str, Any]:
    path = Path("data/seed_research/current/cloud_fragment_seed_alignment_proof.json")
    if not path.exists():
        return _alignment_summary_from_proof(None, proof_exists=False)
    try:
        proof = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _alignment_summary_from_proof(None, proof_exists=False)
    return _alignment_summary_from_proof(proof, proof_exists=True)


def _matches_text(node: dict[str, Any], search: str) -> bool:
    if not search:
        return True
    needle = search.casefold()
    haystack = [
        node.get("label"),
        (node.get("labels") or {}).get("ko") if isinstance(node.get("labels"), dict) else None,
        (node.get("labels") or {}).get("en") if isinstance(node.get("labels"), dict) else None,
        *(((node.get("aliases") or {}).get("ko") or []) if isinstance(node.get("aliases"), dict) else []),
        *(((node.get("aliases") or {}).get("en") or []) if isinstance(node.get("aliases"), dict) else []),
    ]
    return any(needle in str(value).casefold() for value in haystack if value)


@router.get("/viewer")
def seed_research_viewer(
    search: str = Query(default=""),
    relation_type: str = Query(default="all"),
    trust_state: str = Query(default="all"),
) -> dict[str, Any]:
    """Read-only Seed Graph projection.

    This endpoint reads only data/seed_research/current/viewer_export.json.
    It does not read or mutate Local Brain memory, Payload Vault records, or
    user-private graph state.
    """

    export = current_viewer_export()
    nodes = [node for node in export.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in export.get("edges", []) if isinstance(edge, dict)]

    filtered_nodes = [
        node for node in nodes
        if _matches_text(node, search)
        and (trust_state == "all" or node.get("trust_state") == trust_state)
    ]
    node_ids = {node.get("id") for node in filtered_nodes}
    filtered_edges = [
        edge for edge in edges
        if edge.get("source") in node_ids
        and edge.get("target") in node_ids
        and (relation_type == "all" or edge.get("relation") == relation_type)
        and (trust_state == "all" or edge.get("trust_state") == trust_state)
    ]
    visible_ids = {edge.get("source") for edge in filtered_edges} | {edge.get("target") for edge in filtered_edges}
    if relation_type != "all":
        filtered_nodes = [node for node in filtered_nodes if node.get("id") in visible_ids]

    return {
        **export,
        "nodes": filtered_nodes,
        "edges": filtered_edges,
        "visible_concept_count": len(filtered_nodes),
        "visible_relation_count": len(filtered_edges),
        "query": {
            "search": search,
            "relation_type": relation_type,
            "trust_state": trust_state,
        },
        "local_brain_isolation": {
            "reads_local_brain": False,
            "writes_local_brain": False,
            "source_file": "data/seed_research/current/viewer_export.json",
        },
    }


def _runtime_trace(query: str) -> dict[str, Any]:
    local_state = _local_brain_state()
    local_nodes = local_state["local_total_nodes"]
    local_edges = local_state["local_total_edges"]
    local_initialized = local_state["local_brain_initialized"]

    resolved = resolve_seed_concepts(query)
    cloud_alignment = align_public_candidate_fragments()
    return {
        "query": query,
        "local_graph_state": {
            "local_brain_initialized": local_initialized,
            "local_total_nodes": local_nodes,
            "local_total_edges": local_edges,
            "local_evidence_sufficient": local_initialized and local_nodes > 0,
            "seed_written_to_local_brain": False,
            "seed_counted_as_learned_memory": False,
        },
        "seed_anchor_trace": {
            "seed_anchor_ready": bool(resolved.get("seed_anchor_ready")),
            "seed_used": bool(resolved.get("matched_seed_concepts")),
            "matched_seed_concepts": resolved.get("matched_seed_concepts", []),
            "matched_seed_edges": resolved.get("matched_seed_edges", []),
            "anchor_role": "retrieval_verification_alignment",
            "final_answer_generation_claimed": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_engine": False,
        },
        "cloud_alignment_trace": {
            "cloud_checked": True,
            "candidate_fragments_checked": cloud_alignment.get("candidate_fragments_checked", 0),
            "public_fragments_checked": cloud_alignment.get("public_fragments_checked", 0),
            "fragments_aligned_to_seed": cloud_alignment.get("fragments_aligned_to_seed", 0),
            "matched_fragment_ids": cloud_alignment.get("matched_fragment_ids", []),
            "matched_seed_concepts": cloud_alignment.get("matched_seed_concepts", []),
            "matched_seed_edges": cloud_alignment.get("matched_seed_edges", []),
            "alignment_ready": True,
            "writes_to_local_brain": False,
        },
        "runtime_claim": (
            "Seed Graph participated as a retrieval/verification anchor only. "
            "No final answer generation quality, autonomous Cloud Brain growth, or sLLM replacement is claimed."
        ),
    }


@router.get("/runtime-trace")
def seed_runtime_trace(q: str = Query(min_length=1, max_length=500)) -> dict[str, Any]:
    return _runtime_trace(q)


@router.post("/runtime-trace")
def seed_runtime_trace_post(request: RuntimeTraceRequest) -> dict[str, Any]:
    return _runtime_trace(request.query)


@router.get("/cloud-fragment-alignment")
def cloud_fragment_alignment_summary() -> dict[str, Any]:
    return _latest_alignment_summary()


@router.post("/cloud-fragment-alignment/run")
def run_cloud_fragment_alignment_proof() -> dict[str, Any]:
    result = write_cloud_fragment_alignment_proof("data/seed_research", "data/cloud_brain/inbox")
    return _alignment_summary_from_proof(result["proof"], proof_exists=True)
