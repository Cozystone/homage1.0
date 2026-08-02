from __future__ import annotations

from packages.atlas_router.dijkstra import find_lowest_trust_cost_path
from packages.atlas_router.models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy


def _nodes() -> list[TrustRouteNode]:
    return [
        TrustRouteNode("a", "local_brain", "A", 1, "private"),
        TrustRouteNode("b", "working_memory", "B", 1, "restricted"),
        TrustRouteNode("c", "cloud_brain", "C", 0.9, "public"),
        TrustRouteNode("d", "atlas_peer", "D", 0.5, "public"),
    ]


def _edge(edge_id: str, source: str, target: str, trust: float = 0.01, privacy: float = 0.0, license_risk: float = 0.0) -> TrustRouteEdge:
    return TrustRouteEdge(edge_id, source, target, 10, 0.1, trust, license_risk, privacy, 0.0, 0.1, 0.0)


def test_dijkstra_returns_lowest_safe_cost_path() -> None:
    result = find_lowest_trust_cost_path(
        _nodes(),
        [_edge("ab", "a", "b"), _edge("bc", "b", "c"), _edge("ad", "a", "d", trust=0.8), _edge("dc", "d", "c", trust=0.8)],
        "a",
        "c",
        TrustRoutePolicy(require_public_only=False),
    )
    assert result.path == ["a", "b", "c"]
    assert result.edge_ids == ["ab", "bc"]
    assert result.safe_to_attach_to_working_memory is True
    assert result.safe_to_write_local_brain is False


def test_dijkstra_returns_no_route_when_all_blocked() -> None:
    result = find_lowest_trust_cost_path(
        _nodes(),
        [_edge("ad", "a", "d", privacy=0.9), _edge("dc", "d", "c", license_risk=0.9)],
        "a",
        "c",
        TrustRoutePolicy(require_public_only=False, max_privacy_risk=0.1, max_license_risk=0.1),
    )
    assert result.path == []
    assert result.reasons == ["no_route"]
    assert len(result.blocked_edges) == 2
    assert result.safe_to_write_local_brain is False


def test_dijkstra_tie_break_is_deterministic() -> None:
    result = find_lowest_trust_cost_path(
        _nodes(),
        [_edge("ab2", "a", "b"), _edge("ab1", "a", "b"), _edge("bc", "b", "c")],
        "a",
        "c",
        TrustRoutePolicy(require_public_only=False),
    )
    assert result.edge_ids == ["ab1", "bc"]

