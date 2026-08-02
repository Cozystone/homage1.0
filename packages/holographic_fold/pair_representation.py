"""PHFE v0.2 — Pair Representation.

Second milestone of the Phase Holographic Folding Engine
(docs/ATANOR_PHASE_HOLOGRAPHIC_FOLDING_ENGINE_v0.md §3).

Given a v0.1 `StateField`, this builds the multi-channel pair representation for
every active pair. The CENTRAL force channel is the wave interference, exactly
the live model's signal generalized to all active pairs:

    interference = Re(w_i · conj(w_j)) · edge_gain
                 = (re_i·re_j + im_i·im_j) · edge_gain     # Complex::dot, rust parity

Sign of the interference = the folding force sign in v0.3:
    interference > 0  -> constructive (attraction)
    interference < 0  -> destructive  (repulsion)

The other channels (phase_alignment, edge_gain, relation_type, confidence,
source_type, uncertainty, distance_prior) ride alongside as the full pair
representation; v0.3 weights them into the force model. No folding here — this
is pure, deterministic, read-only structure analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .state_field import StateField, StateNode


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _normalize_edge_gain(raw: dict[str, Any]) -> float:
    """Edge strength -> gain in [0, 1]. Accepts 0..63 (rust style) or 0..1."""

    if "edge_gain" in raw and raw["edge_gain"] is not None:
        return _clamp(float(raw["edge_gain"]), 0.0, 1.0)
    strength = float(raw.get("strength", 0.0) or 0.0)
    if strength > 1.0:
        strength = strength / 63.0
    return _clamp(strength, 0.0, 1.0)


def _pair_signal(node_i: StateNode, node_j: StateNode, edge_gain: float) -> tuple[float, float]:
    """Return (interference_energy, phase_alignment) for an ordered pair.

    interference_energy = Re(w_i · conj(w_j)) · edge_gain  (central force channel)
    phase_alignment     = cos(phase_i - phase_j) in [-1, 1]
    Both are symmetric in (i, j).
    """

    dot = node_i.wave_re * node_j.wave_re + node_i.wave_im * node_j.wave_im
    interference = dot * edge_gain
    denom = node_i.amplitude * node_j.amplitude
    if denom > 1e-12:
        phase_alignment = _clamp(dot / denom, -1.0, 1.0)
    else:
        phase_alignment = _clamp(math.cos(node_i.phase - node_j.phase), -1.0, 1.0)
    return interference, phase_alignment


@dataclass(frozen=True)
class NodePair:
    """The multi-channel pair representation for one active pair (i, j)."""

    i: str
    j: str
    interference_energy: float  # central force channel (signed)
    phase_alignment: float
    edge_gain: float
    relation_type: str | None
    confidence: float           # min(c_i, c_j)
    source_pair: tuple[str, str]
    uncertainty: float
    distance_prior: float       # deterministic affinity prior in [0, 1]
    has_edge: bool

    @property
    def constructive(self) -> bool:
        # Aligned phase => constructive. With a real edge this matches the sign
        # of interference_energy; for edge-free pairs it is the latent signal.
        return self.phase_alignment > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "i": self.i,
            "j": self.j,
            "interference_energy": self.interference_energy,
            "phase_alignment": self.phase_alignment,
            "edge_gain": self.edge_gain,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "source_pair": list(self.source_pair),
            "uncertainty": self.uncertainty,
            "distance_prior": self.distance_prior,
            "has_edge": self.has_edge,
            "constructive": self.constructive,
        }


@dataclass(frozen=True)
class PairRepresentation:
    pairs: tuple[NodePair, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"pairs": [pair.to_dict() for pair in self.pairs], "metadata": dict(self.metadata)}


def _distance_prior(node_i: StateNode, node_j: StateNode) -> float:
    same_domain = 1.0 if node_i.domain == node_j.domain else 0.0
    hop_term = 1.0 / (1.0 + abs(node_i.hop_depth - node_j.hop_depth))
    return _clamp(0.5 * same_domain + 0.5 * hop_term, 0.0, 1.0)


def build_pair_representation(
    field: StateField,
    *,
    edges: Iterable[dict[str, Any]] | None = None,
) -> PairRepresentation:
    """Build the multi-channel pair representation over the field's active set.

    `edges` are read-only relation descriptors between field nodes:
    {source|i, target|j, strength (0..63 or 0..1) or edge_gain (0..1), relation}.
    Pairs without an edge get edge_gain 0 (interference channel 0) but still
    carry phase_alignment and the other channels. Pure and deterministic;
    mutates nothing.
    """

    nodes = list(field.nodes)
    index = {node.node_id: node for node in nodes}

    edge_map: dict[frozenset, tuple[float, str | None]] = {}
    for raw in edges or []:
        source = str(raw.get("source") or raw.get("i") or "").strip()
        target = str(raw.get("target") or raw.get("j") or "").strip()
        if not source or not target or source == target:
            continue
        if source not in index or target not in index:
            continue
        gain = _normalize_edge_gain(raw)
        relation = raw.get("relation")
        key = frozenset((source, target))
        prev = edge_map.get(key)
        if prev is None or gain > prev[0]:
            edge_map[key] = (gain, relation if relation is not None else (prev[1] if prev else None))

    pairs: list[NodePair] = []
    constructive_count = 0
    destructive_count = 0
    constructive_energy = 0.0
    destructive_energy = 0.0
    edged_pairs = 0

    for a in range(len(nodes)):
        for b in range(a + 1, len(nodes)):
            node_i, node_j = nodes[a], nodes[b]
            key = frozenset((node_i.node_id, node_j.node_id))
            edge = edge_map.get(key)
            has_edge = edge is not None
            edge_gain = edge[0] if edge else 0.0
            relation = edge[1] if edge else None
            interference, phase_alignment = _pair_signal(node_i, node_j, edge_gain)
            confidence = min(node_i.confidence, node_j.confidence)
            pairs.append(
                NodePair(
                    i=node_i.node_id,
                    j=node_j.node_id,
                    interference_energy=interference,
                    phase_alignment=phase_alignment,
                    edge_gain=edge_gain,
                    relation_type=relation,
                    confidence=confidence,
                    source_pair=(node_i.source_type, node_j.source_type),
                    uncertainty=1.0 - confidence,
                    distance_prior=_distance_prior(node_i, node_j),
                    has_edge=has_edge,
                )
            )
            if has_edge:
                edged_pairs += 1
                if interference >= 0.0:
                    constructive_count += 1
                    constructive_energy += interference
                else:
                    destructive_count += 1
                    destructive_energy += interference

    metadata = {
        "fold_stage": "pair_representation_v0_2",
        "active_node_count": len(nodes),
        "pair_count": len(pairs),
        "edged_pair_count": edged_pairs,
        "constructive_count": constructive_count,
        "destructive_count": destructive_count,
        "constructive_energy_total": round(constructive_energy, 6),
        "destructive_energy_total": round(destructive_energy, 6),
        "deterministic": True,
        "fold_full_store_scan": False,
        "original_brain_state_mutated": False,
        "external_llm_used": False,
        "local_brain_write": False,
        "candidate_promotion": False,
    }
    return PairRepresentation(pairs=tuple(pairs), metadata=metadata)
