# -*- coding: utf-8 -*-
"""The light vector: particle field <-> turbovec-quantized field state.

This is the encode/decode edge of the SPLATRA world-model pipeline (design
docs/ATANOR_vjepa_fusion.md sec 9):

    state --encode--> turbovec z_t --JEPA--> z_hat_{t+1} --decode--> per-particle delta

We do NOT reimplement a codec. We import the proven per-field Lloyd-Max quantizer from
``packages.splatra_turbovec.field_quantizer`` (fit_field / quantize_field /
dequantize_field) and apply it to the DYNAMIC field columns the world model reasons
over: per-particle position (x, y, z) and velocity (vx, vy, vz).

The "light vector" (가벼운 벡터) is the flattened, data-calibrated, quantized field.
It is lighter than raw float32 particles (reported compression ratio) and it lives in
the turbovec representation, not in pixels and not in raw floats. JEPA predicts in an
embedding OF this light vector (jepa.py) -- exactly V-JEPA's "predict in latent".

Deterministic, numpy, CPU, No-LLM. A storage/representation codec only: it never
invents field state and carries an explicit per-field distortion.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Read-only import of the existing turbovec codec (design sec 9: "import, don't reimplement").
from packages.splatra_turbovec.field_quantizer import (
    FieldCodebook,
    dequantize_field,
    fit_field,
    quantize_field,
)

# The six DYNAMIC fields the world model tracks per particle (position + velocity).
# (splatra_turbovec.models.Particle already carries vx, vy, vz -- a physics-ready state.)
FIELD_NAMES: tuple[str, ...] = ("x", "y", "z", "vx", "vy", "vz")

# Bit budget per field. Position needs the most precision; velocity is small-magnitude.
# 3*10 + 3*8 = 54 bits = 6.75 B/particle vs float32 6*4 = 24 B/particle -> ~3.56x.
DEFAULT_FIELD_BITS: dict[str, int] = {"x": 10, "y": 10, "z": 10, "vx": 8, "vy": 8, "vz": 8}

_FLOAT32_BYTES_PER_PARTICLE = 4 * len(FIELD_NAMES)


@dataclass
class FieldState:
    """A particle field's dynamic state: positions (N,3) and velocities (N,3)."""

    pos: np.ndarray  # (N, 3)
    vel: np.ndarray  # (N, 3)

    @property
    def n(self) -> int:
        return int(self.pos.shape[0])

    def columns(self) -> dict[str, np.ndarray]:
        return {
            "x": self.pos[:, 0], "y": self.pos[:, 1], "z": self.pos[:, 2],
            "vx": self.vel[:, 0], "vy": self.vel[:, 1], "vz": self.vel[:, 2],
        }

    def copy(self) -> "FieldState":
        return FieldState(self.pos.copy(), self.vel.copy())


@dataclass
class TurbovecFieldCodec:
    """Data-calibrated per-field quantizer over the dynamic particle field.

    Wraps ``splatra_turbovec.field_quantizer`` Lloyd-Max codebooks. ``fit`` calibrates to
    the empirical training distribution (the turbovec principle); ``encode`` maps a field
    to its flat light vector; ``decode`` dequantizes a light vector back to a field.
    """

    bits: dict[str, int]
    codebooks: dict[str, FieldCodebook]

    # ---- construction -----------------------------------------------------------------
    @classmethod
    def fit(cls, states: list[FieldState], bits: dict[str, int] | None = None,
            iters: int = 12) -> "TurbovecFieldCodec":
        """Fit one Lloyd-Max codebook per field on the pooled training states."""
        bits = dict(bits or DEFAULT_FIELD_BITS)
        pooled: dict[str, np.ndarray] = {f: [] for f in FIELD_NAMES}
        for st in states:
            cols = st.columns()
            for f in FIELD_NAMES:
                pooled[f].append(np.asarray(cols[f], dtype=np.float64).ravel())
        codebooks = {
            f: fit_field(np.concatenate(pooled[f]) if pooled[f] else np.zeros(1),
                         bits[f], iters=iters)
            for f in FIELD_NAMES
        }
        return cls(bits=bits, codebooks=codebooks)

    # ---- light-vector round trip ------------------------------------------------------
    @property
    def bits_per_particle(self) -> int:
        return sum(self.bits[f] for f in FIELD_NAMES)

    @property
    def compression_ratio(self) -> float:
        return _FLOAT32_BYTES_PER_PARTICLE / (self.bits_per_particle / 8.0)

    def light_vector_dim(self, n_particles: int) -> int:
        return n_particles * len(FIELD_NAMES)

    def encode(self, state: FieldState) -> np.ndarray:
        """Field -> flat light vector (quantized-then-dequantized field, in centroids).

        The returned vector is the turbovec representation the JEPA embeds. Values are the
        codebook centroids (the lossy-compressed field), interleaved per particle as
        [x, y, z, vx, vy, vz, x, y, z, ...] so a particle's state stays contiguous.
        """
        cols = state.columns()
        recon = {f: dequantize_field(self.codebooks[f], quantize_field(self.codebooks[f], cols[f]))
                 for f in FIELD_NAMES}
        # (N, 6) then flatten row-major -> per-particle contiguous.
        stacked = np.stack([recon[f] for f in FIELD_NAMES], axis=1)
        return stacked.reshape(-1).astype(np.float64)

    def decode(self, light: np.ndarray, n_particles: int) -> FieldState:
        """Flat light vector -> FieldState (already dequantized; this reshapes)."""
        arr = np.asarray(light, dtype=np.float64).reshape(n_particles, len(FIELD_NAMES))
        return FieldState(pos=arr[:, 0:3].copy(), vel=arr[:, 3:6].copy())

    def distortion(self, state: FieldState) -> dict[str, float]:
        """Per-field RMSE of the round trip, normalized by field spread (honest error)."""
        return self.distortion_pooled([state])

    def distortion_pooled(self, states: list[FieldState]) -> dict[str, float]:
        """Per-field normalized RMSE pooled over states -- avoids the artifact of measuring
        on a single (e.g. initial) state whose velocity spread is ~0."""
        pooled: dict[str, list[np.ndarray]] = {f: [] for f in FIELD_NAMES}
        for st in states:
            cols = st.columns()
            for f in FIELD_NAMES:
                pooled[f].append(np.asarray(cols[f], dtype=np.float64).ravel())
        out: dict[str, float] = {}
        for f in FIELD_NAMES:
            orig = np.concatenate(pooled[f]) if pooled[f] else np.zeros(1)
            rec = dequantize_field(self.codebooks[f], quantize_field(self.codebooks[f], orig))
            scale = max(float(orig.std()), 1e-9)
            out[f] = float(np.sqrt(np.mean((orig - rec) ** 2)) / scale)
        return out
