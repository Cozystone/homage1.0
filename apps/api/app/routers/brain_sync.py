from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.brain_sync import (
    BoundedFragmentAssembler,
    FragmentOrchestrator,
    GraphDeltaCompressor,
    PrivacyLevel,
    bounded_fragment_assembler,
    fragment_orchestrator,
    graph_delta_compressor,
    resolve_conflict,
    working_memory_fragments,
)


router = APIRouter(prefix="/api/brain-sync", tags=["brain-sync"])


class PatchPreviewRequest(BaseModel):
    previous_snapshot: dict[str, Any] | None = None
    current_snapshot: dict[str, Any] = Field(default_factory=dict)
    privacy_level: PrivacyLevel = "public"
    origin_brain_id: str = "local-brain"
    parent_snapshot_id: str | None = None
    created_by_learning_run_id: str | None = None
    source_type: str = "local_learning_run"
    trust_score: float = 0.6


class OrchestrateRequest(BaseModel):
    query: str
    local_confidence: float = 0.0
    graph_density: float = 0.0
    evidence_available: bool = False
    runtime_mode: str = "normal"
    ram_pressure: float = 0.0
    cloud_allowed: bool = True
    privacy_level: PrivacyLevel | None = None


class FragmentAssembleRequest(BaseModel):
    concept_ids: list[str] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summaries: list[dict[str, Any]] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    trust_score: float = 0.5
    origin_brain_id: str = "cloud-brain"
    ttl_seconds: int | None = None


class ConflictRequest(BaseModel):
    local_record: dict[str, Any] = Field(default_factory=dict)
    cloud_record: dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
def brain_sync_status() -> dict[str, Any]:
    limits = bounded_fragment_assembler.limits.to_dict()
    local_brain_initialized = os.getenv("ATANOR_LOCAL_BRAIN_INITIALIZED", "").strip().lower() in {"1", "true", "yes", "on"}
    standby_decision = fragment_orchestrator.decide(
        query="public ontology status",
        local_confidence=0.72 if local_brain_initialized else 0.0,
        graph_density=0.75 if local_brain_initialized else 0.0,
        evidence_available=local_brain_initialized,
        runtime_mode="normal",
        cloud_allowed=True,
    ).to_dict()
    return {
        "state": "ready",
        "architecture": "local_first_patch_sync",
        "orchestrator_state": "standby",
        **standby_decision,
        "external_llm_answer_generation": False,
        "local_brain_initialized": local_brain_initialized,
        "local_brain_primary": True,
        "cloud_brain_role": "bounded_public_fragment_assist",
        "uploads_raw_private_payloads": False,
        "uploads_full_local_graph": False,
        "fragment_attach_layer": "working_memory",
        "promotion_requires_snapshot": True,
        "conflict_priority": [
            "local_private",
            "local_verified",
            "local_repeated_memory",
            "cloud_verified",
            "cloud_unverified",
        ],
        "conflict_priority_requires_server_bound_provenance": True,
        "caller_priority_honored": False,
        "default_fragment_limits": limits,
        "active_working_memory_fragments": len(working_memory_fragments.active()),
        "status_lines": [
            "Local Brain remains the primary brain.",
            "Cloud Brain can only provide bounded public fragments.",
            "Graph patches contain safe deltas, not private payloads.",
            "Cloud fragments attach to Working Memory before any promotion.",
        ],
    }


@router.post("/patch/preview")
def preview_graph_patch(request: PatchPreviewRequest) -> dict[str, Any]:
    compressor = GraphDeltaCompressor()
    return compressor.compress(
        request.previous_snapshot,
        request.current_snapshot,
        privacy_level=request.privacy_level,
        origin_brain_id=request.origin_brain_id,
        parent_snapshot_id=request.parent_snapshot_id,
        created_by_learning_run_id=request.created_by_learning_run_id,
        source_type=request.source_type,
        trust_score=request.trust_score,
    )


@router.post("/orchestrate")
def orchestrate_fragment_request(request: OrchestrateRequest) -> dict[str, Any]:
    orchestrator = FragmentOrchestrator()
    decision = orchestrator.decide(
        query=request.query,
        local_confidence=request.local_confidence,
        graph_density=request.graph_density,
        evidence_available=request.evidence_available,
        runtime_mode=request.runtime_mode,
        ram_pressure=request.ram_pressure,
        cloud_allowed=request.cloud_allowed,
        privacy_level=request.privacy_level,
    )
    return decision.to_dict()


@router.post("/fragment/assemble")
def assemble_fragment(request: FragmentAssembleRequest) -> dict[str, Any]:
    assembler = BoundedFragmentAssembler()
    return assembler.assemble(
        concept_ids=request.concept_ids,
        nodes=request.nodes,
        edges=request.edges,
        evidence_summaries=request.evidence_summaries,
        source_metadata=request.source_metadata,
        trust_score=0.0,
        origin_brain_id="public-api",
        ttl_seconds=request.ttl_seconds,
    )


@router.post("/fragment/attach")
def attach_fragment(fragment: dict[str, Any]) -> dict[str, Any]:
    try:
        attached = working_memory_fragments.attach(fragment)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "state": "attached",
        "storage_layer": attached["storage_layer"],
        "permanent_local_brain_write": attached["permanent_local_brain_write"],
        "fragment_id": attached["fragment_id"],
        "active_working_memory_fragments": len(working_memory_fragments.active()),
    }


@router.post("/conflict/resolve")
def resolve_fragment_conflict(request: ConflictRequest) -> dict[str, Any]:
    return resolve_conflict(request.local_record, request.cloud_record)
