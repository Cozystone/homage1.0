from __future__ import annotations

import heapq
from math import inf
from typing import Iterable

from .cost import edge_cost
from .models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy, TrustRouteResult


def _node_map(nodes: Iterable[TrustRouteNode]) -> dict[str, TrustRouteNode]:
    result = {node.node_id: node for node in nodes}
    if len(result) == 0:
        raise ValueError("nodes must not be empty")
    return result


def find_lowest_trust_cost_path(
    nodes: Iterable[TrustRouteNode],
    edges: Iterable[TrustRouteEdge],
    source_id: str,
    target_id: str,
    policy: TrustRoutePolicy,
) -> TrustRouteResult:
    """Find the lowest allowed trust-cost path using deterministic Dijkstra."""

    node_by_id = _node_map(nodes)
    edge_list = sorted(list(edges), key=lambda edge: (edge.source_id, edge.target_id, edge.edge_id))
    if source_id not in node_by_id:
        raise ValueError(f"unknown source_id: {source_id}")
    if target_id not in node_by_id:
        raise ValueError(f"unknown target_id: {target_id}")

    adjacency: dict[str, list[TrustRouteEdge]] = {node_id: [] for node_id in node_by_id}
    blocked_edges: list[dict] = []
    for edge in edge_list:
        if edge.source_id not in node_by_id or edge.target_id not in node_by_id:
            blocked_edges.append({"edge_id": edge.edge_id, "reason": "unknown_endpoint"})
            continue
        target_node = node_by_id[edge.target_id]
        cost = edge_cost(edge, policy, target_node=target_node)
        if not cost.allowed:
            blocked_edges.append({"edge_id": edge.edge_id, "source_id": edge.source_id, "target_id": edge.target_id, "reason": cost.reason})
            continue
        adjacency[edge.source_id].append(edge)

    for source_edges in adjacency.values():
        source_edges.sort(key=lambda edge: (edge.target_id, edge.edge_id))

    distances: dict[str, float] = {node_id: inf for node_id in node_by_id}
    previous: dict[str, tuple[str, TrustRouteEdge]] = {}
    distances[source_id] = 0.0
    heap: list[tuple[float, str]] = [(0.0, source_id)]

    while heap:
        current_cost, current_id = heapq.heappop(heap)
        if current_cost > distances[current_id]:
            continue
        if current_id == target_id:
            break
        for edge in adjacency.get(current_id, []):
            target_node = node_by_id[edge.target_id]
            cost = edge_cost(edge, policy, target_node=target_node)
            if not cost.allowed or cost.cost is None:
                continue
            next_cost = round(current_cost + cost.cost, 9)
            previous_record = previous.get(edge.target_id)
            should_replace = next_cost < distances[edge.target_id]
            if next_cost == distances[edge.target_id] and previous_record is not None:
                should_replace = (current_id, edge.edge_id) < (previous_record[0], previous_record[1].edge_id)
            if should_replace:
                distances[edge.target_id] = next_cost
                previous[edge.target_id] = (current_id, edge)
                heapq.heappush(heap, (next_cost, edge.target_id))

    if distances[target_id] == inf:
        return TrustRouteResult(
            source_id=source_id,
            target_id=target_id,
            path=[],
            edge_ids=[],
            total_cost=0.0,
            blocked_edges=blocked_edges,
            reasons=["no_route"],
            policy=policy.to_dict(),
            safe_to_attach_to_working_memory=False,
            safe_to_write_local_brain=False,
        )

    path = [target_id]
    edge_ids: list[str] = []
    cursor = target_id
    while cursor != source_id:
        prior_id, edge = previous[cursor]
        edge_ids.append(edge.edge_id)
        path.append(prior_id)
        cursor = prior_id
    path.reverse()
    edge_ids.reverse()
    safe_to_attach = "working_memory" in {node_by_id[node_id].node_type for node_id in path}
    return TrustRouteResult(
        source_id=source_id,
        target_id=target_id,
        path=path,
        edge_ids=edge_ids,
        total_cost=round(distances[target_id], 9),
        blocked_edges=blocked_edges,
        reasons=["route_found"],
        policy=policy.to_dict(),
        safe_to_attach_to_working_memory=safe_to_attach,
        safe_to_write_local_brain=False,
    )

