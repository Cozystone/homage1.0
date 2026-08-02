from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .dijkstra import find_lowest_trust_cost_path
from .models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy, TrustRouteResult


@dataclass(frozen=True)
class AtlasTrustRouter:
    """Small proof-only router facade."""

    nodes: tuple[TrustRouteNode, ...]
    edges: tuple[TrustRouteEdge, ...]

    @classmethod
    def from_iterables(
        cls,
        nodes: Iterable[TrustRouteNode],
        edges: Iterable[TrustRouteEdge],
    ) -> "AtlasTrustRouter":
        return cls(tuple(nodes), tuple(edges))

    def route(self, source_id: str, target_id: str, policy: TrustRoutePolicy) -> TrustRouteResult:
        return find_lowest_trust_cost_path(self.nodes, self.edges, source_id, target_id, policy)

