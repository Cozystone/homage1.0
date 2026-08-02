from __future__ import annotations

import pytest

from packages.atlas_router.models import TrustRouteEdge, TrustRouteNode, TrustRouteResult


def test_node_validation() -> None:
    node = TrustRouteNode("wm", "working_memory", "Working Memory", 0.9, "restricted")
    assert node.to_dict()["node_id"] == "wm"
    with pytest.raises(ValueError):
        TrustRouteNode("bad", "cloud_brain", "Bad", 1.1, "public")


def test_edge_validation() -> None:
    edge = TrustRouteEdge("e", "a", "b", 10, 0.1, 0.1, 0, 0, 0.1, 0.1, 0)
    assert edge.to_dict()["edge_id"] == "e"
    with pytest.raises(ValueError):
        TrustRouteEdge("e", "a", "b", -1, 0, 0, 0, 0, 0, 0, 0)


def test_result_never_allows_local_brain_write() -> None:
    result = TrustRouteResult("a", "b", ["a", "b"], ["e"], 1.0, [], [], {}, True, True)
    assert result.safe_to_write_local_brain is False

