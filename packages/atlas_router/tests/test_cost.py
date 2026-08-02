from __future__ import annotations

from packages.atlas_router.cost import edge_cost
from packages.atlas_router.models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy


def _edge(**kwargs) -> TrustRouteEdge:
    values = {
        "edge_id": "e",
        "source_id": "a",
        "target_id": "b",
        "latency_ms": 10,
        "bandwidth_cost": 0.1,
        "trust_penalty": 0.1,
        "license_risk": 0.0,
        "privacy_risk": 0.0,
        "stale_data_risk": 0.1,
        "compute_cost": 0.1,
        "failure_risk": 0.0,
    }
    values.update(kwargs)
    return TrustRouteEdge(**values)


def test_cost_non_negative() -> None:
    result = edge_cost(_edge(), TrustRoutePolicy(require_public_only=False))
    assert result.allowed
    assert result.cost is not None
    assert result.cost >= 0


def test_privacy_gate_blocks_edge() -> None:
    result = edge_cost(_edge(privacy_risk=0.8), TrustRoutePolicy(require_public_only=False, max_privacy_risk=0.1))
    assert not result.allowed
    assert "privacy_risk" in str(result.reason)


def test_license_gate_blocks_edge() -> None:
    result = edge_cost(_edge(license_risk=0.8), TrustRoutePolicy(require_public_only=False, max_license_risk=0.1))
    assert not result.allowed
    assert "license_risk" in str(result.reason)


def test_target_node_gate_blocks_private_node() -> None:
    target = TrustRouteNode("b", "cloud_brain", "Private Cloud", 0.8, "private")
    result = edge_cost(_edge(), TrustRoutePolicy(require_public_only=False, allow_private_nodes=False), target_node=target)
    assert not result.allowed
    assert "private_node" in str(result.reason)

