from __future__ import annotations

import networkx as nx

from rhfc.graph_spectral import laplacian_diffusion, propagate


def test_ppr_scores_decay_with_distance_on_path_graph() -> None:
    graph = nx.path_graph(20)
    scores = propagate(graph, [10], alpha=0.85)
    assert scores[10] > scores[9] > scores[7] > scores[3]


def test_laplacian_diffusion_is_normalized() -> None:
    graph = nx.path_graph(12)
    scores = laplacian_diffusion(graph, [3], tau=0.5)
    assert abs(sum(scores.values()) - 1.0) < 1e-9
    assert scores[3] > scores[8]
