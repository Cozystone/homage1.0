"""Minimal cellular-sheaf consistency checks for edge-local claims."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import networkx as nx
import numpy as np
from numpy.typing import NDArray


def _matrix(raw: Any, dim: int) -> NDArray[np.float64]:
    if raw is None:
        return np.eye(dim, dtype=np.float64)
    arr = np.asarray(raw, dtype=np.float64)
    if arr.shape != (dim, dim):
        raise ValueError(f"restriction map must have shape {(dim, dim)}, got {arr.shape}")
    return arr


def consistency_score(graph: nx.Graph, node_states: dict[Hashable, NDArray[np.floating]]) -> dict[tuple[Hashable, Hashable], float]:
    """Compute edge inconsistency using simple sheaf restriction maps.

    Each edge may define ``restriction_u`` and ``restriction_v`` matrices. A
    contradiction is high when projected endpoint states disagree.
    """

    scores: dict[tuple[Hashable, Hashable], float] = {}
    for u, v, data in graph.edges(data=True):
        if u not in node_states or v not in node_states:
            continue
        u_state = np.asarray(node_states[u], dtype=np.float64)
        v_state = np.asarray(node_states[v], dtype=np.float64)
        if u_state.shape != v_state.shape or u_state.ndim != 1:
            raise ValueError("node states must be one-dimensional and share dimension")
        dim = int(u_state.size)
        raw_ru = data["restriction_u"] if "restriction_u" in data else data.get("restriction")
        raw_rv = data["restriction_v"] if "restriction_v" in data else data.get("restriction")
        ru = _matrix(raw_ru, dim)
        rv = _matrix(raw_rv, dim)
        projected_u = ru @ u_state
        projected_v = rv @ v_state
        denom = max(float(np.linalg.norm(projected_u) + np.linalg.norm(projected_v)), 1e-12)
        scores[(u, v)] = float(np.linalg.norm(projected_u - projected_v) / denom)
    return scores


def flag_contradictions(scores: dict[tuple[Hashable, Hashable], float], threshold: float = 0.35) -> list[tuple[Hashable, Hashable]]:
    """Return edges whose sheaf inconsistency exceeds threshold."""

    return [edge for edge, score in scores.items() if float(score) >= float(threshold)]
