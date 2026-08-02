# -*- coding: utf-8 -*-
"""Predictive attention gate — the biological answer to "how does a brain take near-infinite
sensory input without overload, slowdown, or overflow?"

The owner's own observation is the design: a brain is not fast because it processes everything;
it is fast because it *ignores* almost everything. Two facts drive this module:

 1. The retina has ~100M photoreceptors but the optic nerve carries only ~1M fibres — the eye
 COMPRESSES by ~100x before the brain ever sees a signal. So we reduce every incoming frame
 to a tiny code first (`frame_signature`), throwing away most pixels at the "sensor".
 2. The cortex is a prediction machine: it predicts the scene and spends expensive processing
 only on the PREDICTION ERROR — the part that violated the prediction. So we run the heavy
 open-vocabulary detector ONLY when the scene meaningfully changes and then settles, plus a
 slow periodic refresh. A static scene costs almost nothing.

Net effect: the compute floor is set by CHANGE, not by frame rate. This is ", " —
the detector still fires exactly when the scene changes (no loss), but idles the rest of the time.

Pure numpy, No-LLM, deterministic — the gate decision is unit-testable without any model.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

# retinal downsample: a frame -> _GRID x _GRID grayscale code. Small enough that comparing two
# codes costs microseconds; large enough to notice a person moving, a cup appearing, a hand raised.
_GRID = 32

# prediction-error thresholds on the [0,1] mean-abs-difference of two codes.
_CHANGE_HI = 0.045   # above this the scene is actively MOVING (frame is mid-change / motion-blurred)
_CHANGE_LO = 0.018   # below this the scene has SETTLED / is static

# even a perfectly static scene gets one refresh detection at least this often — the brain's
# occasional involuntary re-check (micro-saccade). Guards against slow drift the deltas missed.
_MAX_SKIP_S = 6.0

# suggested client poll cadences (seconds) the gate hands back, so the browser can slow down when
# nothing is happening and speed up when it is — attention allocation, not a fixed timer.
_CADENCE_MOVING = 0.4
_CADENCE_SETTLE = 1.0
_CADENCE_IDLE = 1.8

# Seam A (V-JEPA fusion, docs/ATANOR_vjepa_fusion.md §4): a threshold on the STANDARDIZED latent
# surprise (a z-score the latent predictor's OnlineLatentSurprise hands in). Above it the scene changed
# SEMANTICALLY -> run the expensive detector; below it the change was predicted (or is mere
# lighting/noise the pixel delta false-fires on) -> idle. This gates on prediction error in LATENT
# space instead of raw retinal delta. It is purely additive: when no latent surprise is supplied
# (latent_surprise=None: cold start / pre-training) the cheap pixel-delta path below runs unchanged.
_LATENT_HI = 1.5


def frame_signature(rgb) -> np.ndarray:
    """Compress a frame to a small normalized grayscale code — the 'retina' step. Most pixels are
    discarded here, before any expensive model runs. Robust to odd frame sizes."""
    a = np.asarray(rgb, dtype=np.float32)
    if a.size == 0:
        return np.zeros(_GRID * _GRID, dtype=np.float32)
    if a.ndim == 3:
        a = a.mean(axis=2)                      # RGB -> grayscale
    h, w = a.shape[:2]
    if h < _GRID or w < _GRID:                  # tiny frame: coarse resize fallback
        a2 = np.resize(a, (_GRID, _GRID))
    else:
        hh, ww = (h // _GRID) * _GRID, (w // _GRID) * _GRID
        a2 = a[:hh, :ww].reshape(_GRID, hh // _GRID, _GRID, ww // _GRID).mean(axis=(1, 3))
    return (a2 / 255.0).astype(np.float32).reshape(-1)


def change_energy(a: np.ndarray, b: np.ndarray) -> float:
    """Prediction error between two retinal codes: mean absolute difference in [0,1].
    0.0 = identical (perfectly predicted), higher = more of the scene changed."""
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    return float(np.mean(np.abs(a - b)))


@dataclass
class AttentionState:
    """Engine-process-lifetime memory for one camera stream."""
    last_sig: np.ndarray | None = None   # signature of the last frame we actually DETECTED on
    last_detect_t: float = 0.0           # when that detection happened
    moving: bool = False                 # currently inside a motion burst (waiting for it to settle)


def new_state() -> AttentionState:
    return AttentionState()


def decide(state: AttentionState, sig: np.ndarray, now: float | None = None,
           latent_surprise: float | None = None) -> dict:
    """Given the new frame's signature, decide whether the expensive detector should run.

    Returns {run: bool, reason: str, energy: float, next_interval_s: float}. The caller runs the
    detector iff run is True, then calls `commit`. On run=False it should reuse the last read.

    `latent_surprise` (Seam A) is the STANDARDIZED latent surprise from the latent predictor (a
    z-score; see packages.perception.latent_predictor.OnlineLatentSurprise.push -> 'norm'). When
    supplied the gate fires on SEMANTIC change (latent prediction error) and idles through the
    lighting/noise the pixel delta false-fires on. When None (cold start / pre-training) the original
    pixel-delta path runs unchanged — the cheap, always-available fallback."""
    now = time.time() if now is None else now

    if state.last_sig is None:
        return {"run": True, "reason": "cold_start", "energy": 1.0, "next_interval_s": _CADENCE_SETTLE}

    energy = change_energy(sig, state.last_sig)
    since = now - state.last_detect_t

    # Periodic refresh: even a static scene is re-read occasionally so slow/quiet drift can't
    # accumulate unseen. This is the safety net beneath both the latent and the delta logic.
    if since >= _MAX_SKIP_S:
        return {"run": True, "reason": "refresh", "energy": energy, "next_interval_s": _CADENCE_IDLE}

    # Seam A — latent-surprise gate (V-JEPA). Prediction error in LATENT space, not pixels: fire the
    # expensive detector on genuine semantic change, idle when the frame was predicted (or is only
    # lighting/noise). Preserves the pixel path below as the cold-start fallback.
    if latent_surprise is not None:
        if latent_surprise >= _LATENT_HI:
            return {"run": True, "reason": "latent_change", "energy": energy,
                    "latent_surprise": float(latent_surprise), "next_interval_s": _CADENCE_SETTLE}
        return {"run": False, "reason": "latent_idle", "energy": energy,
                "latent_surprise": float(latent_surprise), "next_interval_s": _CADENCE_IDLE}

    # Scene actively changing -> do NOT detect yet; a mid-motion frame is blurry and yields a bad
    # read. Mark that we are in a motion burst and wait for it to settle.
    if energy >= _CHANGE_HI:
        state.moving = True
        return {"run": False, "reason": "moving_wait", "energy": energy, "next_interval_s": _CADENCE_MOVING}

    # Motion just ended (was moving, now quiet) -> THIS is the informative frame. Detect now.
    if state.moving and energy < _CHANGE_LO:
        return {"run": True, "reason": "settled", "energy": energy, "next_interval_s": _CADENCE_SETTLE}

    # Static / negligible drift -> the scene is predicted. Skip the detector, spend nothing.
    return {"run": False, "reason": "predicted", "energy": energy, "next_interval_s": _CADENCE_IDLE}


def commit(state: AttentionState, sig: np.ndarray, now: float | None = None) -> None:
    """Record that a detection just ran on this frame — it becomes the new prediction baseline."""
    state.last_sig = sig
    state.last_detect_t = time.time() if now is None else now
    state.moving = False
