# -*- coding: utf-8 -*-
"""The symbolic membrane in 3D: physics-truth VERIFY + quarantine.

Design docs/ATANOR_vjepa_fusion.md sec 9 / [[realcity-physics-truth-gate]]:

    JEPA *proposes* dynamics (neural, a light vector); PBD / physics *verifies* (symbolic);
    a predicted deformation that breaks a physics invariant is QUARANTINED, not trained on.

The 3DGS/turbovec layer RENDERS -- it is never the truth signal. This gate is the truth
check the decoded per-particle deformation must pass before it is advanced or learned from.

Invariants checked on a candidate next field (given the previous field + the action):
  1. GROUND (no floor interpenetration): no particle may sit below ``_GROUND_Y`` (from
     embodiment.splatra_body, imported via forward_model.ground_y()).
  2. NO IMPLOSION (self-interpenetration proxy): the field's spread about its centroid may
     not collapse toward a point -- distinct particles must not all crash together.
  3. MOMENTUM / ENERGY SANITY: no per-particle teleport (displacement bounded) and no
     kinetic-energy explosion (summed squared displacement bounded vs the physical budget).

Deterministic, numpy, CPU, No-LLM. Cheap O(N) checks (no O(N^2) all-pairs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .forward_model import ground_y
from .turbovec_field import FieldState


@dataclass
class PhysicsVerdict:
    ok: bool
    violations: dict[str, float]  # name -> the offending magnitude (empty if ok)

    def as_reason(self) -> str:
        if self.ok:
            return "physical"
        return "; ".join(f"{k}={v:.4g}" for k, v in self.violations.items())


@dataclass
class PhysicsTruthGate:
    """Verifies a candidate next field against physics invariants and quarantines failures."""

    ground_tol: float = 1e-3         # allowed slack below the floor before it is a violation
    max_disp: float = 1.5            # max plausible per-particle displacement in one step
    implosion_frac: float = 0.25     # spread may not fall below this fraction of the previous
    energy_factor: float = 6.0       # summed sq-displacement cap vs a physical budget

    @property
    def ground_plane(self) -> float:
        return ground_y()

    def verify(self, prev: FieldState, action: np.ndarray,
               candidate: FieldState) -> PhysicsVerdict:
        """Return a verdict for one predicted transition prev --action--> candidate."""
        v: dict[str, float] = {}
        gy = self.ground_plane
        cand_pos = np.asarray(candidate.pos, dtype=np.float64)
        prev_pos = np.asarray(prev.pos, dtype=np.float64)

        # 1. ground: deepest penetration below the floor
        depth = float((gy - cand_pos[:, 1]).max())
        if depth > self.ground_tol:
            v["ground_penetration"] = depth

        # 2. no implosion: spread (mean distance to centroid) vs previous
        prev_spread = float(np.linalg.norm(prev_pos - prev_pos.mean(0), axis=1).mean())
        cand_spread = float(np.linalg.norm(cand_pos - cand_pos.mean(0), axis=1).mean())
        if prev_spread > 1e-9 and cand_spread < self.implosion_frac * prev_spread:
            v["implosion"] = cand_spread / prev_spread

        # 3a. teleport: worst per-particle displacement
        disp = np.linalg.norm(cand_pos - prev_pos, axis=1)
        worst = float(disp.max())
        if worst > self.max_disp:
            v["teleport"] = worst

        # 3b. energy: summed squared displacement vs a physical budget (N * max_disp^2 scaled)
        budget = self.energy_factor * cand_pos.shape[0] * (self.max_disp ** 2)
        energy = float((disp ** 2).sum())
        if energy > budget:
            v["energy_explosion"] = energy / max(budget, 1e-9)

        return PhysicsVerdict(ok=(len(v) == 0), violations=v)

    def filter_transitions(self, items: Iterable) -> "QuarantineResult":
        """Split (prev, action, candidate)-bearing items into learnable vs quarantined.

        Each item must expose ``.pos``/``.delta``/``.action`` sufficient to rebuild the
        candidate; we accept generic objects with a ``physics_fields()`` -> (prev, action,
        candidate) method, or a 3-tuple. This is where "violates => never learned" happens.
        """
        kept: list = []
        quarantined: list = []
        reasons: list[str] = []
        for it in items:
            prev, action, candidate = _physics_fields(it)
            verdict = self.verify(prev, action, candidate)
            if verdict.ok:
                kept.append(it)
            else:
                quarantined.append(it)
                reasons.append(verdict.as_reason())
        return QuarantineResult(kept=kept, quarantined=quarantined, reasons=reasons)


@dataclass
class QuarantineResult:
    kept: list
    quarantined: list
    reasons: list[str] = field(default_factory=list)

    @property
    def n_kept(self) -> int:
        return len(self.kept)

    @property
    def n_quarantined(self) -> int:
        return len(self.quarantined)


def _physics_fields(item):
    """Adapt an item to (prev_field, action, candidate_field)."""
    if hasattr(item, "physics_fields"):
        return item.physics_fields()
    prev, action, candidate = item
    return prev, action, candidate
