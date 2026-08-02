from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from packages.cortex_g2.activation_engine import run_graph_activation
from packages.cortex_g2.creative_walk import run_creative_walk
from packages.cortex_g2.crystal_store import list_crystals, reuse_crystal
from packages.cortex_g2.dream_loop import run_self_dream_cycle
from packages.cortex_g2.pipeline import run_cortex_cycle, summarize_cortex_cycle
from packages.cortex_g2.predictive_engine import compare_predictions_to_evidence, generate_prediction_paths
from packages.cortex_g2.proof import write_living_neuromorphic_loop_proof
from packages.cortex_g2.salience_gate import select_global_workspace
from packages.cortex_g2.storage import DEFAULT_CORTEX_ROOT, read_jsonl


router = APIRouter(prefix="/api/cortex", tags=["cortex-g2"])


class CortexGraphRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    graph_payload: dict[str, Any] = Field(default_factory=dict)
    top_k_nodes: int = Field(default=128, ge=1, le=512)
    top_k_edges: int = Field(default=256, ge=0, le=1024)


class CortexActivationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    graph_payload: dict[str, Any] = Field(default_factory=dict)


class CortexWorkspaceRequest(BaseModel):
    activation_result: dict[str, Any] = Field(default_factory=dict)
    top_k_nodes: int = Field(default=128, ge=1, le=512)
    top_k_edges: int = Field(default=256, ge=0, le=1024)


class CortexPredictRequest(BaseModel):
    workspace: dict[str, Any] = Field(default_factory=dict)


class CortexDreamRequest(BaseModel):
    max_questions: int = Field(default=10, ge=0, le=50)


class CortexCreativeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    mode: str = "far_walk"


class CortexReuseRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


def _standard_flags() -> dict[str, Any]:
    return {
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "final_answer_generation_claimed": False,
    }


@router.post("/activation")
def cortex_activation(request: CortexActivationRequest) -> dict[str, Any]:
    return {**run_graph_activation(request.query, request.graph_payload), **_standard_flags()}


@router.post("/workspace")
def cortex_workspace(request: CortexWorkspaceRequest) -> dict[str, Any]:
    return {
        **select_global_workspace(request.activation_result, top_k_nodes=request.top_k_nodes, top_k_edges=request.top_k_edges),
        **_standard_flags(),
    }


@router.post("/predict")
def cortex_predict(request: CortexPredictRequest) -> dict[str, Any]:
    predictions = generate_prediction_paths(request.workspace)
    trace = compare_predictions_to_evidence(predictions, request.workspace)
    return {"predictions": predictions, "prediction_trace": trace, **_standard_flags()}


@router.post("/cycle")
def cortex_cycle(request: CortexGraphRequest) -> dict[str, Any]:
    cycle = run_cortex_cycle(request.query, request.graph_payload, top_k_nodes=request.top_k_nodes, top_k_edges=request.top_k_edges)
    return {**cycle, "summary": summarize_cortex_cycle(cycle), **_standard_flags()}


@router.get("/crystals")
def cortex_crystals() -> dict[str, Any]:
    return {**list_crystals(), **_standard_flags()}


@router.post("/crystals/reuse")
def cortex_reuse_crystal(request: CortexReuseRequest) -> dict[str, Any]:
    return {**reuse_crystal(request.query), **_standard_flags()}


@router.post("/dream/run")
def cortex_dream_run(request: CortexDreamRequest) -> dict[str, Any]:
    return {**run_self_dream_cycle(max_questions=request.max_questions), **_standard_flags()}


@router.get("/dream/questions")
def cortex_dream_questions() -> dict[str, Any]:
    return {"questions": read_jsonl(DEFAULT_CORTEX_ROOT / "dream_questions.jsonl", limit=100), **_standard_flags()}


@router.post("/creative/run")
def cortex_creative_run(request: CortexCreativeRequest) -> dict[str, Any]:
    return {**run_creative_walk(request.prompt, request.mode), **_standard_flags()}


@router.post("/proof/living-loop")
def cortex_living_loop_proof() -> dict[str, Any]:
    result = write_living_neuromorphic_loop_proof()
    return {**result, **_standard_flags()}


@router.get("/status")
def cortex_status() -> dict[str, Any]:
    root = Path(DEFAULT_CORTEX_ROOT)
    activations = read_jsonl(root / "activation_events.jsonl", limit=1000)
    predictions = read_jsonl(root / "prediction_traces.jsonl", limit=1000)
    activation_count = len(activations)
    prediction_count = len(predictions)
    dream_count = len(read_jsonl(root / "dream_questions.jsonl", limit=1000))
    creative_count = len(read_jsonl(root / "creative_candidates.jsonl", limit=1000))
    crystals = list_crystals()
    last_activation = activations[-1] if activations else {}
    last_prediction = predictions[-1] if predictions else {}
    last_cycle = None
    if last_activation or last_prediction:
        last_cycle = {
            "enabled": True,
            "activation_run_id": last_activation.get("activation_run_id"),
            "activated_nodes": len(last_activation.get("activated_nodes") or []),
            "activated_edges": len(last_activation.get("activated_edges") or []),
            "inhibited_nodes": len(last_activation.get("inhibited_nodes") or []),
            "prediction_trace_id": last_prediction.get("trace_id"),
            "prediction_paths": len(last_prediction.get("expected_paths") or []),
            "observed_paths": len(last_prediction.get("observed_paths") or []),
            "prediction_error": float(last_prediction.get("mean_prediction_error") or 0.0),
            "knowledge_crystal_candidate": False,
            "local_brain_write": False,
            "external_llm_used": False,
            "external_sllm_used": False,
        }
    return {
        "state": "active",
        "architecture": "CORTEX-G2",
        "label": "Cortical Graph Resonance with Predictive Crystallization",
        "activation_events": activation_count,
        "prediction_traces": prediction_count,
        "dream_questions": dream_count,
        "creative_runs": creative_count,
        "knowledge_crystals": crystals["count"],
        "bounded": True,
        "claims": {
            "functional_neuromorphic_graph_loop": True,
            "consciousness": False,
            "sentience": False,
            "unrestricted_self_learning": False,
            "global_cloud_brain": False,
        },
        "last_cycle": last_cycle,
        **_standard_flags(),
    }
