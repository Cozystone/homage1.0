from __future__ import annotations

from packages.atlas_router.models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy
from packages.atlas_router.router import AtlasTrustRouter


def test_router_facade_routes_without_mutation() -> None:
    nodes = [
        TrustRouteNode("source", "public_source", "Source", 1.0, "public"),
        TrustRouteNode("wm", "working_memory", "Working Memory", 1.0, "restricted"),
    ]
    edges = [
        TrustRouteEdge("edge", "source", "wm", 10, 0.1, 0.01, 0, 0, 0, 0.1, 0),
    ]
    router = AtlasTrustRouter.from_iterables(nodes, edges)
    result = router.route("source", "wm", TrustRoutePolicy(require_public_only=False))
    assert result.path == ["source", "wm"]
    assert result.safe_to_attach_to_working_memory is True
    assert result.safe_to_write_local_brain is False

