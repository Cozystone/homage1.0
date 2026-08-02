"""PHFE v0.3 — Folding / Recycling optimizer.

Third milestone of the Phase Holographic Folding Engine
(docs/ATANOR_PHASE_HOLOGRAPHIC_FOLDING_ENGINE_v0.md §4).

Takes a v0.1 `StateField` (+ optional edges), realizes the v0.2 wave
interference as a force field, and folds the active set into a stable 3D
structure with AlphaFold-style recycling. Everything happens on a temporary
working copy — the original state field/nodes are never mutated.

Force model (spec §3):
  F_pair(i)    = k_pair    · Σ_j interference_ij · unit(x_j - x_i)   # attract/repel
  F_exclude(i) = k_exclude · Σ_j (short-range repulsion)             # anti-collapse
  F_conf(i)    = −k_conf   · stabilize(source_type_i, c_i) · x̂_i     # verified→center
Recycling: after each relaxation sweep, re-derive phase from the new geometry
(close neighbours align), recompute waves, re-fold.

Deterministic (no RNG), CPU, vectorized with numpy. Hidden trace only — does
NOT influence answers (that is v0.4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from .state_field import StateField
from .pair_representation import _normalize_edge_gain


# Source-type radial stabilization (spec §3): positive -> pulled toward center,
# negative -> pushed outward. Verified knowledge stabilizes at the core;
# candidates float at the periphery; emotion/policy barely hold a position.
_SOURCE_STABILIZE = {
    "cloud_verified": 1.0,
    "local_brain": 0.8,
    "user_input": 0.5,
    "inner_voice": 0.45,
    "policy": 0.15,
    "emotion": 0.1,
    "cloud_candidate": -0.45,
    "web_candidate": -0.55,
}


@dataclass(frozen=True)
class FoldedNode:
    node_id: str
    source_type: str
    position: tuple[float, float, float]
    radius: float
    coherence: float
    amplitude: float
    phase: float
    confidence: float
    frequency: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "source_type": self.source_type,
            "position": list(self.position),
            "radius": self.radius,
            "coherence": self.coherence,
            "amplitude": self.amplitude,
            "phase": self.phase,
            "confidence": self.confidence,
            "frequency": self.frequency,
        }


@dataclass(frozen=True)
class FoldedState:
    query: str
    nodes: tuple[FoldedNode, ...]
    metadata: dict[str, Any]
    trajectory: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "nodes": [node.to_dict() for node in self.nodes],
            "metadata": dict(self.metadata),
            "trajectory": [dict(frame) for frame in self.trajectory],
        }


def _edge_gain_matrix(field: StateField, edges: Iterable[dict[str, Any]] | None) -> np.ndarray:
    ids = [node.node_id for node in field.nodes]
    pos = {node_id: i for i, node_id in enumerate(ids)}
    n = len(ids)
    gain = np.zeros((n, n), dtype=np.float64)
    for raw in edges or []:
        source = str(raw.get("source") or raw.get("i") or "").strip()
        target = str(raw.get("target") or raw.get("j") or "").strip()
        if source not in pos or target not in pos or source == target:
            continue
        g = _normalize_edge_gain(raw)
        a, b = pos[source], pos[target]
        gain[a, b] = max(gain[a, b], g)
        gain[b, a] = max(gain[b, a], g)
    return gain


def fold_state(
    field: StateField,
    *,
    edges: Iterable[dict[str, Any]] | None = None,
    recycles: int = 3,
    inner_steps: int = 48,
    dt: float = 0.05,
    damping: float = 0.85,
    k_pair: float = 0.9,
    k_exclude: float = 0.06,
    k_conf: float = 0.5,
    exclude_radius: float = 0.25,
    capture_trajectory: bool = False,
    trajectory_frames: int = 48,
) -> FoldedState:
    """Fold the field's active set into a stable 3D structure (read-only).

    With ``capture_trajectory`` the folding records ~``trajectory_frames``
    position snapshots across the whole recycle process, so a renderer can
    replay the actual fold (the "wave interference rotating -> structure
    bending" animation). Off by default to keep the per-answer path lean.
    """

    started = time.perf_counter()
    nodes = list(field.nodes)
    n = len(nodes)
    if n == 0:
        return FoldedState(query=field.query, nodes=(), metadata={
            "fold_stage": "folding_v0_3", "active_node_count": 0, "fold_timing_ms": 0.0,
            "global_coherence": 0.0, "coherence_per_recycle": [], "converged": True,
            "fold_driver_mode": "trace_only", "fold_full_store_scan": False,
            "original_brain_state_mutated": False, "deterministic": True,
            "external_llm_used": False, "local_brain_write": False, "candidate_promotion": False,
        })

    # --- working-layer copies (originals never touched) ---
    pos = np.array([node.seed_position for node in nodes], dtype=np.float64)
    amp = np.array([node.amplitude for node in nodes], dtype=np.float64)
    phase = np.array([node.phase for node in nodes], dtype=np.float64)
    conf = np.array([node.confidence for node in nodes], dtype=np.float64)
    s = np.array([_SOURCE_STABILIZE.get(node.source_type, 0.0) for node in nodes], dtype=np.float64)
    # confidence scales inward pull for stabilizing sources; outward stays as-is
    s = np.where(s > 0, s * (0.3 + 0.7 * conf), s)
    gain = _edge_gain_matrix(field, edges)

    eps = 1e-9
    coherence_per_recycle: list[float] = []
    last_interference = np.zeros((n, n), dtype=np.float64)
    tail_start = max(1, int(round(0.75 * max(1, inner_steps))))
    node_coherence = np.zeros(n, dtype=np.float64)

    # trajectory capture (for the fold animation): sample ~trajectory_frames
    # position snapshots across the whole recycle process.
    trajectory: list[dict[str, Any]] = []
    total_steps = max(1, recycles) * max(1, inner_steps)
    sample_every = max(1, total_steps // max(1, trajectory_frames)) if capture_trajectory else 0
    global_step = 0

    for r in range(max(1, recycles)):
        re = amp * np.cos(phase)
        im = amp * np.sin(phase)
        # interference matrix M_ij = (re_i re_j + im_i im_j) * gain_ij  (force sign)
        interference = (np.outer(re, re) + np.outer(im, im)) * gain
        np.fill_diagonal(interference, 0.0)
        last_interference = interference

        # Each recycle is a fresh settle from the current geometry + updated
        # phases (velocity reset). As phases converge, the equilibrium shifts
        # less each round, so the tail movement shrinks -> coherence rises.
        vel = np.zeros((n, 3), dtype=np.float64)
        pos_tail_ref = pos.copy()
        for step in range(max(1, inner_steps)):
            if step == tail_start:
                pos_tail_ref = pos.copy()
            diff = pos[None, :, :] - pos[:, None, :]          # diff[i,j] = x_j - x_i
            dist = np.sqrt(np.sum(diff * diff, axis=2))
            dist_safe = np.where(dist > eps, dist, 1.0)
            unit = diff / dist_safe[:, :, None]

            f_pair = k_pair * np.sum(interference[:, :, None] * unit, axis=1)

            near = (dist < exclude_radius) & (dist > eps)
            rep_mag = np.where(near, k_exclude * (exclude_radius - dist) / exclude_radius, 0.0)
            f_exclude = np.sum((-unit) * rep_mag[:, :, None], axis=1)

            radius = np.sqrt(np.sum(pos * pos, axis=1))
            radhat = pos / np.where(radius > eps, radius, 1.0)[:, None]
            f_conf = -k_conf * s[:, None] * radhat

            force = f_pair + f_exclude + f_conf
            vel = vel * damping + force * dt
            pos = pos + vel * dt

            if sample_every and (global_step % sample_every == 0):
                trajectory.append({"r": r, "step": global_step, "positions": np.round(pos, 4).tolist()})
            global_step += 1

        # per-recycle coherence: tail settling + CONSTRUCTIVE support + confidence.
        # Use positive (constructive) interference only: recycling that resolves
        # destructive conflict into constructive agreement raises support, the way
        # AlphaFold recycling raises confidence.
        tail_movement = np.sqrt(np.sum((pos - pos_tail_ref) ** 2, axis=1))
        stability = 1.0 / (1.0 + tail_movement)
        energy = np.sum(np.maximum(interference, 0.0), axis=1)
        energy_norm = energy / (np.max(energy) if np.max(energy) > eps else 1.0)
        node_coherence = 0.4 * stability + 0.3 * energy_norm + 0.3 * conf
        coherence_per_recycle.append(float(np.mean(node_coherence)))

        # --- recycling: re-derive phase from geometry (close neighbours align) ---
        if r < recycles - 1:
            diff = pos[None, :, :] - pos[:, None, :]
            dist = np.sqrt(np.sum(diff * diff, axis=2))
            close_w = 1.0 / (1.0 + dist) ** 2  # weight close neighbours sharply
            np.fill_diagonal(close_w, 0.0)
            nbr_sin = close_w @ np.sin(phase)
            nbr_cos = close_w @ np.cos(phase)
            nbr_norm = np.sqrt(nbr_sin ** 2 + nbr_cos ** 2)
            nbr_norm = np.where(nbr_norm > eps, nbr_norm, 1.0)
            alpha = 0.2  # gentle realignment so recycling refines, not re-disturbs
            blend_x = (1 - alpha) * np.cos(phase) + alpha * (nbr_cos / nbr_norm)
            blend_y = (1 - alpha) * np.sin(phase) + alpha * (nbr_sin / nbr_norm)
            phase = np.mod(np.arctan2(blend_y, blend_x), 2 * np.pi)

    radius_final = np.sqrt(np.sum(pos * pos, axis=1))
    coherence_final = node_coherence

    if capture_trajectory:
        final_frame = {"r": max(1, recycles) - 1, "step": total_steps, "positions": np.round(pos, 4).tolist()}
        if not trajectory or trajectory[-1]["step"] != final_frame["step"]:
            trajectory.append(final_frame)

    folded_nodes = tuple(
        FoldedNode(
            node_id=node.node_id,
            source_type=node.source_type,
            position=(float(pos[i, 0]), float(pos[i, 1]), float(pos[i, 2])),
            radius=float(radius_final[i]),
            coherence=float(coherence_final[i]),
            amplitude=float(amp[i]),
            phase=float(phase[i]),
            confidence=float(conf[i]),
            frequency=float(getattr(node, "frequency_bin", 0)),
        )
        for i, node in enumerate(nodes)
    )

    # --- diagnostics: structure semantics + source separation (acceptance tests) ---
    diff = pos[None, :, :] - pos[:, None, :]
    dist = np.sqrt(np.sum(diff * diff, axis=2))
    iu, ju = np.triu_indices(n, k=1)
    pair_dist = dist[iu, ju]
    pair_intf = last_interference[iu, ju]
    constructive_mask = pair_intf > 0
    destructive_mask = pair_intf < 0
    mean_dist_constructive = float(np.mean(pair_dist[constructive_mask])) if np.any(constructive_mask) else None
    mean_dist_destructive = float(np.mean(pair_dist[destructive_mask])) if np.any(destructive_mask) else None

    radii_by_source: dict[str, float] = {}
    for src in {node.source_type for node in nodes}:
        idx = [i for i, node in enumerate(nodes) if node.source_type == src]
        radii_by_source[src] = float(np.mean(radius_final[idx]))

    converged = all(
        coherence_per_recycle[i] <= coherence_per_recycle[i + 1] + 1e-9
        for i in range(len(coherence_per_recycle) - 1)
    )

    metadata = {
        "fold_stage": "folding_v0_3",
        "active_node_count": n,
        "recycles": max(1, recycles),
        "inner_steps": max(1, inner_steps),
        "fold_timing_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "global_coherence": float(np.mean(coherence_final)),
        "coherence_per_recycle": coherence_per_recycle,
        "converged": bool(converged),
        "mean_dist_constructive": mean_dist_constructive,
        "mean_dist_destructive": mean_dist_destructive,
        "mean_radius_by_source": radii_by_source,
        "fold_driver_mode": "trace_only",
        "fold_full_store_scan": False,
        "original_brain_state_mutated": False,
        "deterministic": True,
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "mock_growth": False,
        "trajectory_frame_count": len(trajectory),
    }
    return FoldedState(query=field.query, nodes=folded_nodes, metadata=metadata, trajectory=tuple(trajectory))
