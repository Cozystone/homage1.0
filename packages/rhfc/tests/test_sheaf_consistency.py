from __future__ import annotations

import networkx as nx
import numpy as np

from rhfc.sheaf_consistency import consistency_score, flag_contradictions


def test_sheaf_scores_contradiction_higher_than_consistency() -> None:
    graph = nx.Graph()
    graph.add_edge("consistent_a", "consistent_b")
    graph.add_edge("claim_a", "claim_b")
    states = {
        "consistent_a": np.array([1.0, 0.0]),
        "consistent_b": np.array([0.95, 0.05]),
        "claim_a": np.array([1.0, 0.0]),
        "claim_b": np.array([-1.0, 0.0]),
    }
    scores = consistency_score(graph, states)
    assert scores[("claim_a", "claim_b")] > scores[("consistent_a", "consistent_b")]
    assert ("claim_a", "claim_b") in flag_contradictions(scores, threshold=0.5)


def test_sheaf_custom_restriction_maps() -> None:
    graph = nx.Graph()
    graph.add_edge("a", "b", restriction_u=np.eye(2), restriction_v=np.array([[0.0, 1.0], [1.0, 0.0]]))
    scores = consistency_score(graph, {"a": np.array([1.0, 0.0]), "b": np.array([0.0, 1.0])})
    assert scores[("a", "b")] < 1e-9
