from __future__ import annotations

from .activation_engine import run_graph_activation
from .salience_gate import select_global_workspace


def build_global_workspace(query: str, graph_payload: dict, *, top_k_nodes: int = 128, top_k_edges: int = 256) -> dict:
    activation = run_graph_activation(query, graph_payload)
    workspace = select_global_workspace(activation, top_k_nodes=top_k_nodes, top_k_edges=top_k_edges)
    return {"activation": activation, "workspace": workspace}
