from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import EdgeNeuralState, NodeNeuralState
from .storage import DEFAULT_CORTEX_ROOT, append_jsonl, bounded_float, ensure_cortex_dirs, now_iso


TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣_]+")
MAX_ACTIVATION_NODES = 512
MAX_ACTIVATION_EDGES = 1024


def _run_id(query: str) -> str:
    digest = hashlib.sha256(f"{query}:{now_iso()}".encode("utf-8")).hexdigest()[:18]
    return f"act_{digest}"


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(text or "") if len(token) > 1}


def _node_id(node: dict[str, Any], index: int) -> str:
    return str(node.get("id") or node.get("node_id") or node.get("cloud_node_id") or f"node_{index}")


def _edge_id(edge: dict[str, Any], index: int) -> str:
    return str(edge.get("id") or edge.get("edge_id") or edge.get("cloud_edge_id") or f"edge_{index}")


def _layer_for_node(node: dict[str, Any]) -> tuple[str, str, bool]:
    source_type = str(node.get("source_type") or node.get("visual_layer") or node.get("type") or "")
    source_scope = str(node.get("source_scope") or "")
    if "seed" in source_type or source_scope == "seed":
        return "seed_anchor", "seed", True
    if "cloud" in source_type or source_scope == "cloud":
        return "cloud_attached", "cloud", True
    if node.get("temporary"):
        return "working_memory", source_scope if source_scope in {"local", "seed", "cloud"} else "cloud", True
    return "local_persistent", "local", False


def _trust_for_node(node: dict[str, Any], layer: str) -> float:
    trust_state = str(node.get("trust_state") or node.get("verification_state") or "")
    if layer == "seed_anchor":
        return 0.86
    if "verified" in trust_state:
        return 0.82
    if "seed_aligned" in trust_state:
        return 0.72
    if layer == "cloud_attached":
        return 0.62
    return 0.58


def _collect_nodes(graph_payload: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for key in ("local_nodes", "seed_anchor_nodes", "cloud_attached_nodes"):
        value = graph_payload.get(key)
        if isinstance(value, list):
            nodes.extend(row for row in value if isinstance(row, dict))
    if not nodes and isinstance(graph_payload.get("nodes"), list):
        nodes = [row for row in graph_payload["nodes"] if isinstance(row, dict)]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        node_id = _node_id(node, index)
        if node_id in seen:
            continue
        seen.add(node_id)
        unique.append(node)
    return unique[:MAX_ACTIVATION_NODES]


def _collect_edges(graph_payload: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for key in ("local_edges", "cloud_attached_edges"):
        value = graph_payload.get(key)
        if isinstance(value, list):
            edges.extend(row for row in value if isinstance(row, dict))
    if not edges and isinstance(graph_payload.get("edges"), list):
        edges = [row for row in graph_payload["edges"] if isinstance(row, dict)]
    return edges[:MAX_ACTIVATION_EDGES]


def run_graph_activation(query: str, graph_payload: dict[str, Any]) -> dict[str, Any]:
    """Run bounded activation across the supplied visible/working graph payload.

    This function never loads a wider graph store. It activates only the graph
    fragment supplied by the caller, keeping Local Brain writes disabled.
    """

    ensure_cortex_dirs()
    query_terms = _tokens(query)
    nodes = _collect_nodes(graph_payload)
    edges = _collect_edges(graph_payload)
    node_index = {_node_id(node, index): node for index, node in enumerate(nodes)}
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for index, edge in enumerate(edges):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        adjacency.setdefault(source, []).append(edge)
        adjacency.setdefault(target, []).append(edge)

    neural_nodes: list[dict[str, Any]] = []
    inhibited_nodes: list[dict[str, Any]] = []
    activation_by_id: dict[str, float] = {}
    for index, node in enumerate(nodes):
        node_id = _node_id(node, index)
        label = " ".join(str(node.get(key) or "") for key in ("label", "concept_id", "type", "relation"))
        node_terms = _tokens(label)
        overlap = len(query_terms & node_terms)
        layer, source_scope, temporary = _layer_for_node(node)
        trust = _trust_for_node(node, layer)
        novelty = 0.22 if temporary else 0.08
        fatigue = 0.04 if layer == "seed_anchor" else 0.02
        base = 0.18 + min(0.48, overlap * 0.18)
        if layer == "seed_anchor":
            base += 0.24
        if layer == "cloud_attached":
            base += 0.12
        activation = bounded_float((base * trust) + novelty - fatigue)
        inhibition = bounded_float(0.28 - activation + (0.16 if trust < 0.5 else 0.0))
        state = NodeNeuralState(
            node_id=node_id,
            layer=layer,  # type: ignore[arg-type]
            activation=activation,
            inhibition=inhibition,
            salience=bounded_float((activation * 0.68) + (trust * 0.22) + novelty - (inhibition * 0.12)),
            novelty=novelty,
            fatigue=fatigue,
            prediction_error=0.0,
            trust=trust,
            source_scope=source_scope,  # type: ignore[arg-type]
            temporary=temporary,
        ).to_dict()
        state["label"] = str(node.get("label") or node.get("concept_id") or node_id)
        neural_nodes.append(state)
        activation_by_id[node_id] = activation
        if inhibition > activation:
            inhibited_nodes.append(state)

    neural_edges: list[dict[str, Any]] = []
    strengthened: set[str] = set()
    for index, edge in enumerate(edges):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        relation = str(edge.get("relation") or "related_to")
        edge_id = _edge_id(edge, index)
        source_activation = activation_by_id.get(source, 0.0)
        target_activation = activation_by_id.get(target, 0.0)
        relation_is_inhibitory = relation in {"contradicts", "rejects", "blocks", "conflicts"}
        edge_trust = 0.76 if str(edge.get("source_type") or "").startswith("cloud") else 0.64
        weight = bounded_float(((source_activation + target_activation) / 2.0) * edge_trust)
        state = EdgeNeuralState(
            edge_id=edge_id,
            source=source,
            relation=relation,
            target=target,
            weight=weight,
            excitatory=not relation_is_inhibitory,
            inhibitory=relation_is_inhibitory,
            plasticity=bounded_float(weight * 0.18),
            recent_use=weight,
            trust=edge_trust,
            prediction_error=0.0 if weight > 0.12 else 0.34,
            consolidation_state="transient",
        ).to_dict()
        neural_edges.append(state)
        if weight > 0.2:
            strengthened.add(edge_id)

    active_nodes = sorted(neural_nodes, key=lambda row: (row["activation"], row["salience"]), reverse=True)[:128]
    active_node_ids = {row["node_id"] for row in active_nodes}
    active_edges = [edge for edge in neural_edges if edge["source"] in active_node_ids and edge["target"] in active_node_ids][:256]
    result = {
        "activation_run_id": _run_id(query),
        "query": query,
        "activated_nodes": active_nodes,
        "activated_edges": active_edges,
        "inhibited_nodes": inhibited_nodes[:64],
        "strengthened_edge_ids": sorted(strengthened),
        "activation_budget_used": {
            "nodes_seen": len(nodes),
            "edges_seen": len(edges),
            "node_budget": MAX_ACTIVATION_NODES,
            "edge_budget": MAX_ACTIVATION_EDGES,
        },
        "local_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }
    append_jsonl(DEFAULT_CORTEX_ROOT / "activation_events.jsonl", {**result, "recorded_at": now_iso()})
    return result
