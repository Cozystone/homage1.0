# -*- coding: utf-8 -*-
"""The two baselines the JEPA-over-turbovec predictor is measured against (design sec 9).

Both predict the SAME target as the JEPA -- the next per-particle positions -- from the
SAME inputs (the turbovec light vector + the action), so the comparison is apples-to-apples
and isolates the mechanism (nonlinear latent prediction) from the representation.

  (a) PersistenceBaseline -- the no-model baseline: predict next = current (zero motion).
  (b) LinearForwardMap    -- a strong linear baseline: a single global ridge-regression map
      from [light_vector, action, 1] to the per-particle displacement. It can represent the
      LINEAR part of the dynamics exactly; it provably cannot represent the ground-contact
      nonlinearity -- that gap is what the mechanism proof looks for.

Deterministic, numpy, CPU, No-LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class PersistenceBaseline:
    """No-model: predicted next positions == current positions."""

    def predict_next_positions(self, light_t: np.ndarray, action: np.ndarray,
                               cur_pos: np.ndarray) -> np.ndarray:
        return np.asarray(cur_pos, dtype=np.float64).copy()


@dataclass
class LinearForwardMap:
    """Global linear forward map delta ~= W @ [light, action, 1], fit by ridge least squares."""

    W: np.ndarray          # (3N, d_light + d_action + 1)
    n_particles: int
    ridge: float = 1e-3

    @classmethod
    def fit(cls, light: np.ndarray, action: np.ndarray, delta: np.ndarray,
            ridge: float = 1e-3) -> "LinearForwardMap":
        light = np.asarray(light, dtype=np.float64)
        action = np.asarray(action, dtype=np.float64)
        delta = np.asarray(delta, dtype=np.float64)
        n_samples, n3 = delta.shape[0], delta.shape[1] * delta.shape[2]
        X = np.concatenate([light, action, np.ones((n_samples, 1))], axis=1)  # (S, F)
        Y = delta.reshape(n_samples, n3)                                      # (S, 3N)
        f = X.shape[1]
        # ridge closed form: W = (X^T X + lam I)^-1 X^T Y  -> then transpose to (3N, F)
        A = X.T @ X + ridge * np.eye(f)
        B = X.T @ Y
        W_ft = np.linalg.solve(A, B)      # (F, 3N)
        return cls(W=W_ft.T.copy(), n_particles=delta.shape[1], ridge=ridge)

    def predict_next_positions(self, light_t: np.ndarray, action: np.ndarray,
                               cur_pos: np.ndarray) -> np.ndarray:
        x = np.concatenate([np.asarray(light_t, dtype=np.float64).ravel(),
                            np.asarray(action, dtype=np.float64).ravel(),
                            [1.0]])
        delta = (self.W @ x).reshape(self.n_particles, 3)
        return np.asarray(cur_pos, dtype=np.float64) + delta
