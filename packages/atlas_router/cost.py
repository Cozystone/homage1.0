from __future__ import annotations

from dataclasses import dataclass

from .models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy


TRUST_WEIGHT = 3.0
PRIVACY_WEIGHT = 5.0
LICENSE_WEIGHT = 2.0
STALE_WEIGHT = 1.5
COMPUTE_WEIGHT = 1.0
LATENCY_WEIGHT = 1.0


@dataclass(frozen=True)
class EdgeCost:
    allowed: bool
    cost: float | None
    reason: str | None = None


def edge_cost(
    edge: TrustRouteEdge,
    policy: TrustRoutePolicy,
    *,
    target_node: TrustRouteNode | None = None,
) -> EdgeCost:
    """Return deterministic policy-gated cost for an edge.

    The router is proof-only and never approves Local Brain writes. This function
    only evaluates whether a temporary route edge can be considered.
    """

    if policy.require_public_only and edge.privacy_risk > 0.0:
        return EdgeCost(False, None, "privacy_risk:public_only_policy")
    if edge.privacy_risk > policy.max_privacy_risk:
        return EdgeCost(False, None, "privacy_risk:above_policy_limit")
    if edge.license_risk > policy.max_license_risk:
        return EdgeCost(False, None, "license_risk:above_policy_limit")
    if target_node is not None:
        if target_node.privacy_level == "private" and not policy.allow_private_nodes:
            return EdgeCost(False, None, "private_node:not_allowed")
        if target_node.node_type == "atlas_peer" and not policy.allow_atlas_peers:
            return EdgeCost(False, None, "atlas_peer:not_allowed")
        if target_node.node_type == "cloud_brain" and not policy.allow_cloud_brain:
            return EdgeCost(False, None, "cloud_brain:not_allowed")
        if target_node.node_type == "graph_hub" and not policy.allow_graph_hub:
            return EdgeCost(False, None, "graph_hub:not_allowed")

    latency_component = (edge.latency_ms / 1000.0) * LATENCY_WEIGHT
    cost = (
        latency_component
        + edge.bandwidth_cost
        + (edge.compute_cost * COMPUTE_WEIGHT)
        + (edge.stale_data_risk * STALE_WEIGHT)
        + edge.failure_risk
        + (edge.license_risk * LICENSE_WEIGHT)
        + (edge.privacy_risk * PRIVACY_WEIGHT)
        + (edge.trust_penalty * TRUST_WEIGHT)
    )
    if policy.prefer_local and target_node is not None and target_node.node_type in {"local_brain", "working_memory"}:
        cost *= 0.9
    return EdgeCost(True, round(max(0.0, cost), 9), None)

