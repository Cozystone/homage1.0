"""PHFE v0.1 — Node State Field builder + active working-set selector.

This is the first milestone of the Phase Holographic Folding Engine
(docs/ATANOR_PHASE_HOLOGRAPHIC_FOLDING_ENGINE_v0.md). It does ONE thing:
project ATANOR's real internal state into a bounded, deterministic field of
`StateNode`s — the substrate that v0.2 (pair representation) and v0.3 (folding)
will operate on.

Hard guarantees (acceptance tests in tests/test_state_field.py):
- Deterministic: same input -> identical field. No RNG; all derivations are
  SHA-256-seeded, matching the live wave model's style.
- Grounded: every node carries a non-empty `provenance` and a known
  `source_type`; a raw node missing either is rejected (no fabricated nodes).
- Bounded: the active set is capped at `n_max` (<= hard cap), never the whole
  brain. `metadata.full_store_scan` is always False.
- Read-only: building a field never mutates any store
  (`metadata.original_brain_state_mutated` is always False).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Iterable

TAU = math.pi * 2.0

# Mirrors the relation/domain codes used by the live wave model
# (packages/core_proof/three_core_answer_path.py) so the pair-interference
# channel in v0.2 stays consistent with the existing engine.
RELATION_CODES = {
    "is_a": 1,
    "used_for": 2,
    "compares": 3,
    "explains": 4,
    "requires_evidence": 5,
    "denies": 6,
    "relates_to": 7,
}
DOMAIN_CODES = {
    "general": 1,
    "technical": 2,
    "atanor": 3,
    "privacy": 4,
    "reasoning": 5,
    "language": 6,
}

# Source-type taxonomy (spec §2/§3). The folding force in v0.3 treats these
# differently (verified -> center, candidate -> periphery, private -> gated).
SOURCE_TYPES = frozenset(
    {
        "local_brain",
        "cloud_verified",
        "cloud_candidate",
        "web_candidate",
        "inner_voice",
        "emotion",
        "policy",
        "user_input",
    }
)

N_MAX_DEFAULT = 128
N_MAX_HARD_CAP = 256


def _hash_int(text: str, bits: int) -> int:
    """Deterministic SHA-256 derived integer (no RNG). Matches the live model."""

    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[: max(1, bits // 4)], 16) & ((1 << bits) - 1)


def _hash_unit(text: str) -> float:
    """Deterministic float in [0, 1)."""

    return _hash_int(text, 32) / float(1 << 32)


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _rotate_left_u32(value: int, shift: int) -> int:
    value &= 0xFFFFFFFF
    return ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF


def _packed_u32(subject_id: int, relation_code: int, energy_level: int, domain_code: int) -> int:
    # [subject:14][relation:5][energy:7][domain:6] — same bitfield as the live SQC.
    return (
        ((subject_id & 0x3FFF) << 18)
        | ((relation_code & 0x1F) << 13)
        | ((energy_level & 0x7F) << 6)
        | (domain_code & 0x3F)
    )


def _derive_frequency_bin(subject_id: int, packed: int, depth: int, branch_index: int) -> int:
    mixed = (
        subject_id
        ^ _rotate_left_u32(packed, 7)
        ^ ((depth & 0xFFFF) << 9)
        ^ ((branch_index & 0xFF) << 4)
    )
    return mixed & 0x03FF


def _derive_amplitude(energy_level: int, depth: int) -> float:
    base = _clamp(energy_level / 63.0, 0.01, 1.0)
    depth_decay = 1.0 / (1.0 + depth * 0.18)
    return base * depth_decay


def _derive_phase(frequency_bin: int, domain_code: int, relation_code: int) -> float:
    raw = (
        frequency_bin * 0.013_671_875
        + domain_code * 0.618_033_988_75
        + relation_code * 0.414_213_562_37
    )
    return raw % TAU


def _seed_position(node_id: str, confidence: float) -> tuple[float, float, float]:
    """Deterministic seed coordinate on a shell (folding refines it in v0.3).

    Direction is hash-derived; the seed radius leans inward for higher
    confidence so the *initial* layout already hints the intended geometry
    (verified inward, uncertain outward). This is only a seed — the folding
    optimizer, not this function, produces the final structure.
    """

    theta = _hash_unit(f"{node_id}:theta") * TAU
    z = _hash_unit(f"{node_id}:z") * 2.0 - 1.0
    r_xy = math.sqrt(max(0.0, 1.0 - z * z))
    radius = 1.2 - 0.4 * _clamp(confidence, 0.0, 1.0)
    return (
        radius * r_xy * math.cos(theta),
        radius * r_xy * math.sin(theta),
        radius * z,
    )


@dataclass(frozen=True)
class StateNode:
    """One ATANOR state element projected into the holographic field."""

    node_id: str
    source_type: str
    label: str
    provenance: str
    importance: float
    confidence: float
    polarity: float
    hop_depth: int
    domain: str
    relation: str
    # derived (deterministic) wave attributes — consumed by v0.2 interference
    subject_id: int
    energy_level: int
    frequency_bin: int
    amplitude: float
    phase: float
    wave_re: float
    wave_im: float
    seed_position: tuple[float, float, float]
    relevance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "source_type": self.source_type,
            "label": self.label,
            "provenance": self.provenance,
            "importance": self.importance,
            "confidence": self.confidence,
            "polarity": self.polarity,
            "hop_depth": self.hop_depth,
            "domain": self.domain,
            "relation": self.relation,
            "subject_id": self.subject_id,
            "energy_level": self.energy_level,
            "frequency_bin": self.frequency_bin,
            "amplitude": self.amplitude,
            "phase": self.phase,
            "wave_re": self.wave_re,
            "wave_im": self.wave_im,
            "seed_position": list(self.seed_position),
            "relevance": self.relevance,
        }


@dataclass(frozen=True)
class StateField:
    """A bounded, deterministic projection of ATANOR's active state."""

    query: str
    nodes: tuple[StateNode, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "nodes": [node.to_dict() for node in self.nodes],
            "metadata": dict(self.metadata),
        }


def _query_tokens(text: str) -> set[str]:
    import re

    latin = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,}", str(text or ""))
    korean = re.findall(r"[가-힣]{2,}", str(text or ""))
    return {token.casefold() for token in (*latin, *korean)}


def _label_tokens(text: str) -> set[str]:
    return _query_tokens(text)


def _relevance(raw: dict[str, Any], query_tokens: set[str]) -> float:
    importance = _clamp(float(raw.get("importance", 0.0) or 0.0), 0.0, 1.0)
    hop_depth = int(raw.get("hop_depth", 0) or 0)
    overlap = len(_label_tokens(raw.get("label", "")) & query_tokens)
    match = 1.0 if overlap else 0.0
    depth_term = 1.0 / (1.0 + max(0, hop_depth))
    # Fixed deterministic weights (no learning).
    return 0.55 * importance + 0.30 * match + 0.15 * depth_term


def _validate(raw: dict[str, Any]) -> tuple[str, str, str]:
    node_id = str(raw.get("node_id") or raw.get("id") or "").strip()
    if not node_id:
        raise ValueError("state-field node missing node_id")
    source_type = str(raw.get("source_type") or "").strip()
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            f"node {node_id!r} has unknown source_type {source_type!r}; "
            f"must be one of {sorted(SOURCE_TYPES)}"
        )
    provenance = str(raw.get("provenance") or "").strip()
    if not provenance:
        # No provenance => not a real ATANOR node. The field never fabricates.
        raise ValueError(f"node {node_id!r} ({source_type}) has no provenance; refusing to fabricate")
    return node_id, source_type, provenance


def build_state_field(
    query: str,
    raw_nodes: Iterable[dict[str, Any]],
    *,
    n_max: int = N_MAX_DEFAULT,
) -> StateField:
    """Project real ATANOR state nodes into a bounded holographic state field.

    `raw_nodes` are read-only descriptors of real nodes; each MUST carry
    `node_id` (or `id`), a known `source_type`, and a non-empty `provenance`.
    Optional: label, importance (0..1), confidence (0..1), polarity (-1..1),
    hop_depth, domain, relation. The function is pure and deterministic and
    mutates nothing.
    """

    n_max = max(1, min(int(n_max), N_MAX_HARD_CAP))
    query_tokens = _query_tokens(query)

    # Deduplicate by node_id, keeping the highest-importance descriptor.
    best: dict[str, dict[str, Any]] = {}
    for raw in raw_nodes:
        node_id, source_type, provenance = _validate(raw)
        existing = best.get(node_id)
        if existing is None or float(raw.get("importance", 0.0) or 0.0) > float(
            existing.get("importance", 0.0) or 0.0
        ):
            best[node_id] = {**raw, "node_id": node_id, "source_type": source_type, "provenance": provenance}

    scored = [(raw, _relevance(raw, query_tokens)) for raw in best.values()]
    # Deterministic ordering: relevance desc, then node_id asc for stable ties.
    scored.sort(key=lambda item: (-item[1], item[0]["node_id"]))
    selected = scored[:n_max]

    nodes: list[StateNode] = []
    source_counts: dict[str, int] = {}
    for raw, relevance in selected:
        node_id = raw["node_id"]
        source_type = raw["source_type"]
        label = str(raw.get("label") or node_id)
        importance = _clamp(float(raw.get("importance", 0.0) or 0.0), 0.0, 1.0)
        confidence = _clamp(float(raw.get("confidence", 0.0) or 0.0), 0.0, 1.0)
        polarity = _clamp(float(raw.get("polarity", 0.0) or 0.0), -1.0, 1.0)
        hop_depth = max(0, int(raw.get("hop_depth", 0) or 0))
        domain = str(raw.get("domain") or "general")
        relation = str(raw.get("relation") or "relates_to")
        domain_code = DOMAIN_CODES.get(domain, DOMAIN_CODES["general"])
        relation_code = RELATION_CODES.get(relation, RELATION_CODES["relates_to"])

        subject_id = _hash_int(node_id.casefold(), 14)
        energy_level = int(round(importance * 63))
        branch_index = _hash_int(f"{node_id}:branch", 8)
        packed = _packed_u32(subject_id, relation_code, energy_level, domain_code)
        frequency_bin = _derive_frequency_bin(subject_id, packed, hop_depth, branch_index)
        amplitude = _derive_amplitude(energy_level, hop_depth)
        phase = _derive_phase(frequency_bin, domain_code, relation_code)
        wave_re = amplitude * math.cos(phase)
        wave_im = amplitude * math.sin(phase)
        seed_position = _seed_position(node_id, confidence)

        nodes.append(
            StateNode(
                node_id=node_id,
                source_type=source_type,
                label=label,
                provenance=raw["provenance"],
                importance=importance,
                confidence=confidence,
                polarity=polarity,
                hop_depth=hop_depth,
                domain=domain,
                relation=relation,
                subject_id=subject_id,
                energy_level=energy_level,
                frequency_bin=frequency_bin,
                amplitude=amplitude,
                phase=phase,
                wave_re=wave_re,
                wave_im=wave_im,
                seed_position=seed_position,
                relevance=relevance,
            )
        )
        source_counts[source_type] = source_counts.get(source_type, 0) + 1

    metadata = {
        "phase_holographic_fold_used": True,
        "fold_stage": "state_field_v0_1",
        "fold_active_node_count": len(nodes),
        "fold_candidates_considered": len(best),
        "n_max": n_max,
        "fold_full_store_scan": False,
        "original_brain_state_mutated": False,
        "fold_driver_mode": "trace_only",
        "source_type_counts": source_counts,
        "deterministic": True,
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "mock_growth": False,
    }
    return StateField(query=query, nodes=tuple(nodes), metadata=metadata)
