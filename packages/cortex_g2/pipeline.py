from __future__ import annotations

from typing import Any

from .activation_engine import run_graph_activation
from .crystal_store import maybe_create_crystal
from .predictive_engine import compare_predictions_to_evidence, generate_prediction_paths
from .salience_gate import select_global_workspace


def run_cortex_cycle(query: str, graph_payload: dict[str, Any], *, top_k_nodes: int = 128, top_k_edges: int = 256) -> dict[str, Any]:
    activation = run_graph_activation(query, graph_payload)
    workspace = select_global_workspace(activation, top_k_nodes=top_k_nodes, top_k_edges=top_k_edges)
    predictions = generate_prediction_paths(workspace)
    trace = compare_predictions_to_evidence(predictions, workspace)
    crystal = maybe_create_crystal(trace, workspace)
    q_cortex_trace = workspace.get("q_cortex") or {
        "enabled": False,
        "reason": "not_available",
        "real_quantum_hardware_used": False,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }
    return {
        "enabled": True,
        "activation": activation,
        "workspace": workspace,
        "predictions": predictions,
        "prediction_trace": trace,
        "knowledge_crystal": crystal,
        "retrieval_trace": {
            "cortex_g2": {
                "enabled": True,
                "activation_run_id": activation.get("activation_run_id"),
                "global_workspace_frame_id": workspace.get("frame_id"),
                "prediction_trace_id": trace.get("trace_id"),
                "knowledge_crystal_candidate": bool(crystal.get("created")),
                "self_generated_truth_saved": False,
                "local_brain_write": False,
                "external_llm_used": False,
                "external_sllm_used": False,
            },
            "q_cortex": q_cortex_trace,
        },
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "final_answer_generation_claimed": False,
    }


def summarize_cortex_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    activation = cycle.get("activation", {})
    workspace = cycle.get("workspace", {})
    trace = cycle.get("prediction_trace", {})
    crystal = cycle.get("knowledge_crystal", {})
    q_cortex = workspace.get("q_cortex") or {}
    return {
        "enabled": bool(cycle.get("enabled")),
        "activation_run_id": activation.get("activation_run_id"),
        "activated_nodes": len(activation.get("activated_nodes") or []),
        "activated_edges": len(activation.get("activated_edges") or []),
        "inhibited_nodes": len(activation.get("inhibited_nodes") or []),
        "global_workspace_frame_id": workspace.get("frame_id"),
        "salience_nodes": len(workspace.get("active_nodes") or []),
        "salience_edges": len(workspace.get("active_edges") or []),
        "prediction_trace_id": trace.get("trace_id"),
        "prediction_paths": len(trace.get("expected_paths") or []),
        "observed_paths": len(trace.get("observed_paths") or []),
        "prediction_error": trace.get("mean_prediction_error", 0),
        "knowledge_crystal_candidate": bool(crystal.get("created")),
        "q_cortex_enabled": bool(q_cortex.get("enabled")),
        "q_cortex_run_id": q_cortex.get("run_id"),
        "q_cortex_solver": q_cortex.get("solver_name"),
        "q_cortex_quantum_hardware_used": False,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }
