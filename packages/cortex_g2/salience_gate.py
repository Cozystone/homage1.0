from __future__ import annotations

import hashlib
from typing import Any

from .models import GlobalWorkspaceFrame
from .storage import DEFAULT_CORTEX_ROOT, append_jsonl, bounded_float, ensure_cortex_dirs, now_iso

try:
    from packages.q_cortex.salience_optimizer import optimize_salience_workspace
except Exception:  # pragma: no cover - q_cortex is optional for CORTEX-G2 fallback behavior.
    optimize_salience_workspace = None  # type: ignore[assignment]


def _frame_id(query: str) -> str:
    return f"gwf_{hashlib.sha256(f'{query}:{now_iso()}'.encode('utf-8')).hexdigest()[:18]}"


def _score_node(node: dict[str, Any]) -> float:
    activation = bounded_float(node.get("activation"))
    salience = bounded_float(node.get("salience"))
    trust = bounded_float(node.get("trust"), 0.5)
    novelty = bounded_float(node.get("novelty"))
    inhibition = bounded_float(node.get("inhibition"))
    source_bonus = 0.08 if node.get("source_scope") == "seed" else 0.04 if node.get("source_scope") == "cloud" else 0.02
    temporary_penalty = 0.04 if node.get("temporary") and node.get("source_scope") == "cloud" else 0.0
    return bounded_float((activation * 0.42) + (salience * 0.26) + (trust * 0.2) + novelty + source_bonus - inhibition * 0.16 - temporary_penalty)


def _score_edge(edge: dict[str, Any]) -> float:
    weight = bounded_float(edge.get("weight"))
    trust = bounded_float(edge.get("trust"), 0.5)
    penalty = 0.18 if edge.get("inhibitory") else 0.0
    return bounded_float(weight * 0.62 + trust * 0.28 - penalty)


def _q_cortex_seed(query: str) -> int:
    return int(hashlib.sha256(query.encode("utf-8")).hexdigest()[:8], 16)


def _q_cortex_candidates(activation_result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in [row for row in activation_result.get("activated_nodes", []) if isinstance(row, dict)]:
        node_id = str(node.get("node_id") or node.get("id") or "")
        if not node_id:
            continue
        candidates.append(
            {
                "id": node_id,
                "kind": "node",
                "layer": node.get("layer", "working_memory"),
                "query_relevance": bounded_float(node.get("salience"), bounded_float(node.get("activation"))),
                "activation": bounded_float(node.get("activation")),
                "trust": bounded_float(node.get("trust"), 0.5),
                "novelty": bounded_float(node.get("novelty")),
                "user_goal_fit": bounded_float(node.get("salience"), bounded_float(node.get("activation"))),
                "risk": bounded_float(node.get("prediction_error")),
                "fatigue": bounded_float(node.get("fatigue")),
                "source_id": node.get("source_scope", "unknown"),
                "concept_id": node_id,
                "temporary": bool(node.get("temporary")),
            }
        )
    for edge in [row for row in activation_result.get("activated_edges", []) if isinstance(row, dict)]:
        edge_id = str(edge.get("edge_id") or edge.get("id") or f"{edge.get('source')}->{edge.get('target')}")
        candidates.append(
            {
                "id": edge_id,
                "kind": "edge",
                "layer": "working_memory",
                "query_relevance": bounded_float(edge.get("weight")),
                "activation": bounded_float(edge.get("recent_use"), bounded_float(edge.get("weight"))),
                "trust": bounded_float(edge.get("trust"), 0.5),
                "novelty": bounded_float(edge.get("plasticity")),
                "user_goal_fit": bounded_float(edge.get("weight")),
                "risk": bounded_float(edge.get("prediction_error")),
                "fatigue": 0.0,
                "source_id": edge.get("source"),
                "concept_id": edge.get("relation", edge_id),
                "temporary": bool(edge.get("temporary")),
            }
        )
    return candidates


def select_global_workspace(
    activation_result: dict[str, Any],
    top_k_nodes: int = 128,
    top_k_edges: int = 256,
    use_q_cortex: bool = True,
) -> dict[str, Any]:
    ensure_cortex_dirs()
    top_k_nodes = max(1, min(int(top_k_nodes), 512))
    top_k_edges = max(0, min(int(top_k_edges), 1024))
    raw_nodes = [row for row in activation_result.get("activated_nodes", []) if isinstance(row, dict)]
    raw_edges = [row for row in activation_result.get("activated_edges", []) if isinstance(row, dict)]
    q_cortex_trace: dict[str, Any] = {
        "enabled": False,
        "reason": "not_requested" if not use_q_cortex else "unavailable",
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "real_quantum_hardware_used": False,
    }
    selected_node_ids: set[str] = set()
    selected_edge_ids: set[str] = set()
    if use_q_cortex and optimize_salience_workspace is not None:
        try:
            q_result = optimize_salience_workspace(
                _q_cortex_candidates(activation_result),
                max_nodes=top_k_nodes,
                max_edges=top_k_edges,
                seed=_q_cortex_seed(str(activation_result.get("query") or "")),
            )
            for item in q_result.get("selected_items") or []:
                item_id = str(item.get("id") or "")
                if item.get("kind") == "edge":
                    selected_edge_ids.add(item_id)
                else:
                    selected_node_ids.add(item_id)
            q_cortex_trace = {
                "enabled": True,
                "run_id": q_result.get("run_id"),
                "problem_type": q_result.get("problem_type"),
                "solver_name": q_result.get("solver_name"),
                "input_count": q_result.get("input_count"),
                "selected_count": q_result.get("selected_count"),
                "objective_value": q_result.get("objective_value"),
                "baseline_delta": (q_result.get("trace") or {}).get("baseline_delta"),
                "real_quantum_hardware_used": False,
                "quantum_inspired_only": True,
                "local_brain_write": False,
                "external_llm_used": False,
                "external_sllm_used": False,
            }
        except Exception as exc:
            q_cortex_trace = {
                **q_cortex_trace,
                "enabled": False,
                "reason": "fallback_to_heuristic",
                "error": str(exc),
            }
    ranked_nodes = sorted(raw_nodes, key=_score_node, reverse=True)
    if selected_node_ids:
        nodes = [row for row in ranked_nodes if str(row.get("node_id") or row.get("id")) in selected_node_ids][:top_k_nodes]
        if not nodes:
            nodes = ranked_nodes[:top_k_nodes]
    else:
        nodes = ranked_nodes[:top_k_nodes]
    node_ids = {str(node.get("node_id")) for node in nodes}
    edges = [
        edge for edge in sorted(
            raw_edges,
            key=_score_edge,
            reverse=True,
        )
        if str(edge.get("source")) in node_ids
        and str(edge.get("target")) in node_ids
        and (not selected_edge_ids or str(edge.get("edge_id") or edge.get("id") or f"{edge.get('source')}->{edge.get('target')}") in selected_edge_ids)
    ][:top_k_edges]
    seed_anchors = [node for node in nodes if node.get("layer") == "seed_anchor"]
    cloud_attached = [node for node in nodes if node.get("layer") == "cloud_attached"]
    frame = GlobalWorkspaceFrame(
        frame_id=_frame_id(str(activation_result.get("query") or "")),
        query=str(activation_result.get("query") or ""),
        active_nodes=nodes,
        active_edges=edges,
        seed_anchors=seed_anchors,
        cloud_attached_nodes=cloud_attached,
        salience_top_k=[{**node, "salience_score": _score_node(node)} for node in nodes[: min(24, len(nodes))]],
        local_write=False,
        external_llm_used=False,
        external_sllm_used=False,
    ).to_dict()
    frame["bounded"] = True
    frame["node_budget"] = top_k_nodes
    frame["edge_budget"] = top_k_edges
    frame["q_cortex"] = q_cortex_trace
    append_jsonl(DEFAULT_CORTEX_ROOT / "salience_decisions.jsonl", {**frame, "recorded_at": now_iso()})
    return frame
