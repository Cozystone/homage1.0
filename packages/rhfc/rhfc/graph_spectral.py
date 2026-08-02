"""Graph spectral and Personalized PageRank propagation."""

from __future__ import annotations

from typing import Hashable

import networkx as nx
import numpy as np
from scipy.linalg import expm


def propagate(graph: nx.Graph, seed_nodes: list[Hashable], alpha: float = 0.85, max_iter: int = 100, tol: float = 1e-9) -> dict[Hashable, float]:
    """Run Personalized PageRank activation propagation.

    Scores should decay with graph distance on simple connected graphs while
    still respecting degree-normalized random-walk structure.
    """

    if graph.number_of_nodes() == 0:
        return {}
    seeds = [node for node in seed_nodes if node in graph]
    if not seeds:
        raise ValueError("at least one seed node must exist in graph")
    personalization = {node: 0.0 for node in graph.nodes}
    for node in seeds:
        personalization[node] = 1.0 / len(seeds)
    return nx.pagerank(graph, alpha=alpha, personalization=personalization, max_iter=max_iter, tol=tol)


def laplacian_diffusion(graph: nx.Graph, seed_nodes: list[Hashable], tau: float = 1.0) -> dict[Hashable, float]:
    """Diffuse activation with exp(-tau * L) over the graph Laplacian."""

    nodes = list(graph.nodes)
    if not nodes:
        return {}
    index = {node: i for i, node in enumerate(nodes)}
    seeds = [node for node in seed_nodes if node in index]
    if not seeds:
        raise ValueError("at least one seed node must exist in graph")
    lap = nx.laplacian_matrix(graph, nodelist=nodes).astype(float).toarray()
    signal = np.zeros(len(nodes), dtype=np.float64)
    for node in seeds:
        signal[index[node]] = 1.0 / len(seeds)
    diffused = expm(-float(tau) * lap) @ signal
    total = float(np.sum(diffused))
    if total > 1e-12:
        diffused = diffused / total
    return {node: float(diffused[index[node]]) for node in nodes}
