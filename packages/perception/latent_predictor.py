# -*- coding: utf-8 -*-
"""Latent predictive coder — ATANOR's fusion of the V-JEPA 2 *principle* into the perception lane
(design: docs/ATANOR_vjepa_fusion.md, 2026-07-24). NOT a model port (V-JEPA 2 is ~1B params over 1M+
hours of video, far outside our N1-N3 neuro-budget); we adopt the three claims at our scale:

  1. Predict in LATENT space, not pixels — reconstructing pixels wastes capacity on unpredictable
     detail (lighting, noise, texture). Predicting the *representation* of the next/masked region
     keeps only what is semantically predictable.
  2. Non-generative, collapse-safe world model — context encoder f_theta + predictor g_phi + an EMA
     (stop-gradient) target encoder f_xi; representational collapse is prevented architecturally, with
     NO pixel decoder anywhere in the loop.
  3. Prediction error is the signal — latent surprise s_t = ||z_hat_{t+1} - z_{t+1}|| drives learning,
     attention (Seam A), and doubt (Seam B / the conformal nonconformity read, Seam C).

This organ sits on the retinal-code stream that ``attention.frame_signature`` already produces (no new
sensor). It is a NEURAL organ, which is legal under the No-LLM doctrine as a *runtime* property: its
output is DATA / a proposal, never enshrined as fact — the symbolic membrane verifies (a latent
prediction is a flagged hypothesis, see Seam B in ``video_events.py``).

Deliberately tiny and pure-numpy (no torch): an MLP encoder + a small window-MLP predictor over the
1024-d retinal code. Torch-free on purpose so the light perception organs that consume s_t
(``attention.py``, ``video_events.py``) never drag a heavy framework into their microsecond paths, and
so the whole thing stays deterministic and unit-testable without any model. Manual backprop is
gradient-checked against finite differences (``LatentPredictiveCoder.grad_check``).

Budget: report the actual trainable-parameter count with ``param_count()`` — the ceiling is 25M and we
expect ~0.15M (three orders of magnitude under).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# retinal code length that attention.frame_signature emits (_GRID*_GRID = 32*32).
_RETINA_DIM = 1024

_STD_EPS = 1e-6      # per-frame standardization floor (a flat frame -> ~0 code, so lighting cancels)
_VAR_EPS = 1e-4      # VICReg variance floor inside the sqrt
_VAR_GAMMA = 1.0     # VICReg target per-dimension std (hinge target): z must not shrink below this


@dataclass
class CoderConfig:
    """Shape + optimisation knobs. Defaults are the tiny 'mechanism-proof' size."""
    input_dim: int = _RETINA_DIM
    enc_hidden: int = 128
    latent_dim: int = 32
    pred_hidden: int = 128
    history_k: int = 4          # predictor context window: predict z_t from the k preceding latents
    ema_decay: float = 0.99     # target encoder f_xi = EMA of online encoder f_theta
    lambda_var: float = 5.0     # VICReg variance weight (anti-collapse; kept high on purpose)
    lambda_cov: float = 0.5     # VICReg covariance weight (decorrelate latent dims)
    lr: float = 3e-3
    seed: int = 0


def _standardize(x: np.ndarray) -> np.ndarray:
    """Per-frame standardization of the retinal code: subtract the frame mean, divide by its std.

    This is where GLOBAL lighting/contrast invariance is bought cheaply and honestly: adding a constant
    to every pixel (a lighting shift) leaves the standardized code unchanged, so the encoder never sees
    it. Nuisance the encoder should be invariant to is removed at the input; the pixel baseline
    (``attention.change_energy``) does NOT do this, which is exactly why it false-fires on lighting."""
    x = np.asarray(x, dtype=np.float64)
    mu = x.mean(axis=-1, keepdims=True)
    sd = x.std(axis=-1, keepdims=True)
    return (x - mu) / (sd + _STD_EPS)


def _glorot(rng: np.random.Generator, out_dim: int, in_dim: int) -> np.ndarray:
    lim = np.sqrt(6.0 / (out_dim + in_dim))
    return rng.uniform(-lim, lim, size=(out_dim, in_dim))


class LatentPredictiveCoder:
    """f_theta (context encoder) + g_phi (predictor) + f_xi (EMA target encoder), pure numpy.

    Weight layout: every W is [out, in]; a forward is ``X @ W.T + b`` for a batch X of rows. tanh
    hidden units, linear latent read-out (no L2-normalization of z — anti-collapse is the VICReg
    variance term's job, not a normalization crutch)."""

    def __init__(self, config: CoderConfig | None = None):
        self.cfg = config or CoderConfig()
        rng = np.random.default_rng(self.cfg.seed)
        c = self.cfg
        # online encoder f_theta
        self.We1 = _glorot(rng, c.enc_hidden, c.input_dim)
        self.be1 = np.zeros(c.enc_hidden)
        self.We2 = _glorot(rng, c.latent_dim, c.enc_hidden)
        self.be2 = np.zeros(c.latent_dim)
        # predictor g_phi: input = k latents concatenated + 1 dt feature
        pred_in = c.history_k * c.latent_dim + 1
        self.Wp1 = _glorot(rng, c.pred_hidden, pred_in)
        self.bp1 = np.zeros(c.pred_hidden)
        self.Wp2 = _glorot(rng, c.latent_dim, c.pred_hidden)
        self.bp2 = np.zeros(c.latent_dim)
        # target encoder f_xi = EMA copy of f_theta (stop-gradient); starts identical
        self._sync_target()
        # Adam state
        self._m: dict[str, np.ndarray] = {}
        self._v: dict[str, np.ndarray] = {}
        self._t = 0

    # ---- parameter bookkeeping -------------------------------------------------------------
    def _online_params(self) -> dict[str, np.ndarray]:
        return {"We1": self.We1, "be1": self.be1, "We2": self.We2, "be2": self.be2,
                "Wp1": self.Wp1, "bp1": self.bp1, "Wp2": self.Wp2, "bp2": self.bp2}

    def _sync_target(self) -> None:
        self.tWe1, self.tbe1 = self.We1.copy(), self.be1.copy()
        self.tWe2, self.tbe2 = self.We2.copy(), self.be2.copy()

    def _ema_target(self) -> None:
        d = self.cfg.ema_decay
        self.tWe1 = d * self.tWe1 + (1 - d) * self.We1
        self.tbe1 = d * self.tbe1 + (1 - d) * self.be1
        self.tWe2 = d * self.tWe2 + (1 - d) * self.We2
        self.tbe2 = d * self.tbe2 + (1 - d) * self.be2

    def param_count(self, include_target: bool = False) -> int:
        """Trainable parameter count (f_theta + g_phi). The target encoder is an EMA *copy* of the
        encoder, not independently trained; include_target adds its (identical-shape) size for the
        total memory footprint. Both are reported far under the 25M ceiling."""
        n = sum(p.size for p in self._online_params().values())
        if include_target:
            n += self.We1.size + self.be1.size + self.We2.size + self.be2.size
        return int(n)

    # ---- forward paths ---------------------------------------------------------------------
    def encode(self, X: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Online encoder f_theta: retinal code(s) -> latent z. Returns (Z, cache) for backprop.
        X is [N, input_dim] (or [input_dim] -> promoted). Short temporal history is carried by the
        PREDICTOR's k-latent window (JEPA puts dynamics in the predictor), so the encoder is per-frame
        and clean — which also keeps the VICReg batch statistics well-defined."""
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        Xn = _standardize(X)
        pre1 = Xn @ self.We1.T + self.be1
        H1 = np.tanh(pre1)
        Z = H1 @ self.We2.T + self.be2
        return Z, {"Xn": Xn, "H1": H1}

    def encode_target(self, X: np.ndarray) -> np.ndarray:
        """Target encoder f_xi (EMA, stop-gradient): the 'true' latent the predictor is scored against.
        No cache — no gradient ever flows here (that asymmetry, plus VICReg, is the anti-collapse)."""
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        Xn = _standardize(X)
        H1 = np.tanh(Xn @ self.tWe1.T + self.tbe1)
        return H1 @ self.tWe2.T + self.tbe2

    def _predict(self, context: np.ndarray, dt: np.ndarray | None = None
                 ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Predictor g_phi: [W, k*latent] context (+ dt) -> predicted next latent [W, latent]."""
        W = context.shape[0]
        if dt is None:
            dt = np.ones((W, 1))
        Cin = np.concatenate([context, dt], axis=1)
        pp = Cin @ self.Wp1.T + self.bp1
        HP = np.tanh(pp)
        ZHAT = HP @ self.Wp2.T + self.bp2
        return ZHAT, {"Cin": Cin, "HP": HP}

    # ---- windowing -------------------------------------------------------------------------
    def _windows(self, Z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """From per-frame latents Z [N, D] build predictor inputs: for each target t in [k, N), the
        context is the concatenation of z_{t-k..t-1}. Returns (context [W, k*D], target_index [W])."""
        N, D = Z.shape
        k = self.cfg.history_k
        W = max(0, N - k)
        if W == 0:
            return np.zeros((0, k * D)), np.zeros(0, dtype=int)
        ctx = np.empty((W, k * D))
        for j in range(k):
            ctx[:, j * D:(j + 1) * D] = Z[j:j + W]     # context frame j of window w is frame (w+j)
        tgt_idx = np.arange(k, N)
        return ctx, tgt_idx

    # ---- loss + manual backward ------------------------------------------------------------
    def loss_and_grads(self, X: np.ndarray) -> tuple[dict[str, float], dict[str, np.ndarray]]:
        """One sequence -> (loss components, grads for every online param). The target latents come
        from f_xi with stop-gradient. VICReg variance+covariance on the online latents prevents
        collapse. All backward math is finite-difference verified in ``grad_check``."""
        cfg = self.cfg
        D = cfg.latent_dim
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        N = X.shape[0]
        Z, cache = self.encode(X)                       # online latents [N, D]
        ctx, tgt_idx = self._windows(Z)
        Wn = ctx.shape[0]

        grads = {k: np.zeros_like(v) for k, v in self._online_params().items()}
        dZ_pred = np.zeros_like(Z)
        pred_loss = 0.0

        if Wn > 0:
            ZHAT, pcache = self._predict(ctx)
            Ztar = self.encode_target(X[tgt_idx])       # stop-grad EMA target [W, D]
            diff = ZHAT - Ztar
            pred_loss = float(np.sum(diff * diff) / (Wn * D))
            dZHAT = (2.0 / (Wn * D)) * diff
            # predictor backward
            HP, Cin = pcache["HP"], pcache["Cin"]
            grads["Wp2"] += dZHAT.T @ HP
            grads["bp2"] += dZHAT.sum(axis=0)
            dHP = dZHAT @ self.Wp2
            dpp = dHP * (1 - HP ** 2)
            grads["Wp1"] += dpp.T @ Cin
            grads["bp1"] += dpp.sum(axis=0)
            dCin = dpp @ self.Wp1
            dctx = dCin[:, :cfg.history_k * D]           # drop the dt column's grad (dt is input data)
            # scatter context grads back to the frames they came from: window w, chunk j -> frame w+j
            for j in range(cfg.history_k):
                dZ_pred[j:j + Wn] += dctx[:, j * D:(j + 1) * D]

        # VICReg on the online latents (anti-collapse) --------------------------------------
        Zc = Z - Z.mean(axis=0, keepdims=True)
        var = (Zc ** 2).mean(axis=0)
        std = np.sqrt(var + _VAR_EPS)
        hinge = np.maximum(0.0, _VAR_GAMMA - std)
        var_loss = float(hinge.mean())
        mask = (std < _VAR_GAMMA).astype(np.float64)
        dZc_var = (-(1.0 / D) * mask / (N * std))[None, :] * Zc

        cov = (Zc.T @ Zc) / max(1, N - 1)
        off = cov - np.diag(np.diag(cov))
        cov_loss = float(np.sum(off ** 2) / D)
        dZc_cov = (4.0 / (D * max(1, N - 1))) * (Zc @ off)

        dZc_vic = cfg.lambda_var * dZc_var + cfg.lambda_cov * dZc_cov
        dZ_vic = dZc_vic - dZc_vic.mean(axis=0, keepdims=True)   # centering backprop
        dZ = dZ_pred + dZ_vic

        # encoder backward -----------------------------------------------------------------
        H1, Xn = cache["H1"], cache["Xn"]
        grads["We2"] += dZ.T @ H1
        grads["be2"] += dZ.sum(axis=0)
        dH1 = dZ @ self.We2
        dpre1 = dH1 * (1 - H1 ** 2)
        grads["We1"] += dpre1.T @ Xn
        grads["be1"] += dpre1.sum(axis=0)

        total = pred_loss + cfg.lambda_var * var_loss + cfg.lambda_cov * cov_loss
        losses = {"total": total, "pred": pred_loss, "var": var_loss, "cov": cov_loss,
                  "latent_std_min": float(std.min()), "latent_std_mean": float(std.mean())}
        return losses, grads

    def _total_loss(self, X: np.ndarray) -> float:
        """Scalar loss only (for finite-difference gradient checking)."""
        return self.loss_and_grads(X)[0]["total"]

    def _adam_step(self, grads: dict[str, np.ndarray]) -> None:
        self._t += 1
        b1, b2, eps, lr = 0.9, 0.999, 1e-8, self.cfg.lr
        params = self._online_params()
        for name, g in grads.items():
            m = self._m.setdefault(name, np.zeros_like(g))
            v = self._v.setdefault(name, np.zeros_like(g))
            m[:] = b1 * m + (1 - b1) * g
            v[:] = b2 * v + (1 - b2) * (g * g)
            mhat = m / (1 - b1 ** self._t)
            vhat = v / (1 - b2 ** self._t)
            params[name] -= lr * mhat / (np.sqrt(vhat) + eps)

    # ---- training --------------------------------------------------------------------------
    def train(self, sequences: list[np.ndarray], epochs: int = 200,
              verbose: bool = False) -> list[dict[str, float]]:
        """Self-supervised training on retinal-code sequences (NO labels). Each sequence is one batch;
        Adam step per sequence; EMA target update after each step. Returns the per-epoch loss history
        (mean over sequences). Structure, not memorization: generalization is proved on a held-out
        sequence by the harness, never on these frames."""
        rng = np.random.default_rng(self.cfg.seed + 1)
        history: list[dict[str, float]] = []
        seqs = [np.atleast_2d(np.asarray(s, dtype=np.float64)) for s in sequences]
        for ep in range(epochs):
            order = rng.permutation(len(seqs))
            acc: dict[str, float] = {}
            for i in order:
                losses, grads = self.loss_and_grads(seqs[i])
                self._adam_step(grads)
                self._ema_target()
                for k, v in losses.items():
                    acc[k] = acc.get(k, 0.0) + v
            row = {k: v / len(seqs) for k, v in acc.items()}
            row["epoch"] = ep
            history.append(row)
            if verbose and (ep % max(1, epochs // 10) == 0 or ep == epochs - 1):
                print(f"ep{ep:4d} total={row['total']:.4f} pred={row['pred']:.4f} "
                      f"var={row['var']:.4f} std_min={row['latent_std_min']:.3f}")
        return history

    # ---- inference: latent surprise --------------------------------------------------------
    def surprise_stream(self, sigs: np.ndarray) -> np.ndarray:
        """Causal latent surprise for a whole sequence: for each frame t>=k, predict z_t from the k
        preceding ONLINE latents, compare to the target latent of frame t. Uses only the past to
        explain the present -> a legitimate attention/doubt signal. s_t for t<k is 0 (no context yet).

        Returns s [N] with s_t = ||z_hat_t - z_t^xi||_2. This is the single signal the three seams
        consume; it is DATA (a proposal), verified downstream, never enshrined as fact."""
        X = np.atleast_2d(np.asarray(sigs, dtype=np.float64))
        N = X.shape[0]
        k, D = self.cfg.history_k, self.cfg.latent_dim
        Z, _ = self.encode(X)
        Ztar = self.encode_target(X)
        s = np.zeros(N)
        if N <= k:
            return s
        ctx, tgt_idx = self._windows(Z)
        ZHAT, _ = self._predict(ctx)
        s[tgt_idx] = np.linalg.norm(ZHAT - Ztar[tgt_idx], axis=1)
        return s

    def collapse_report(self, sigs: np.ndarray) -> dict[str, Any]:
        """Collapse check: encode a batch of frames and confirm the latent has NOT shrunk to a
        constant. Reports per-dimension std (min/mean), the fraction of dims below the VICReg target,
        and whether the surprise signal itself has spread (a collapsed predictor emits ~constant s_t).
        `ok` is True iff the latent variance is bounded away from zero."""
        X = np.atleast_2d(np.asarray(sigs, dtype=np.float64))
        Z, _ = self.encode(X)
        std = Z.std(axis=0)
        s = self.surprise_stream(X)
        s_active = s[self.cfg.history_k:]
        return {
            "latent_std_min": float(std.min()),
            "latent_std_mean": float(std.mean()),
            "latent_std_max": float(std.max()),
            "dims_below_gamma": int((std < _VAR_GAMMA).sum()),
            "latent_dim": int(self.cfg.latent_dim),
            "surprise_std": float(s_active.std()) if s_active.size else 0.0,
            "surprise_mean": float(s_active.mean()) if s_active.size else 0.0,
            "ok": bool(std.min() > 1e-2),          # bounded away from zero -> no collapse
        }

    # ---- correctness self-test -------------------------------------------------------------
    def grad_check(self, X: np.ndarray, n_probe: int = 4, eps: float = 1e-5) -> dict[str, float]:
        """Finite-difference check of the manual backward pass: perturb a few random entries of each
        param, compare numeric dL/dp to the analytic grad. Returns the max relative error per param.
        A correct implementation yields errors ~1e-5 or smaller. Guards the organ's honesty."""
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        # freeze the EMA target during the check so the loss is a clean function of online params
        saved = (self.tWe1.copy(), self.tbe1.copy(), self.tWe2.copy(), self.tbe2.copy())
        _, grads = self.loss_and_grads(X)
        rng = np.random.default_rng(123)
        out: dict[str, float] = {}
        params = self._online_params()
        for name, P in params.items():
            flat = P.reshape(-1)
            gflat = grads[name].reshape(-1)
            idx = rng.choice(flat.size, size=min(n_probe, flat.size), replace=False)
            worst = 0.0
            for i in idx:
                orig = flat[i]
                flat[i] = orig + eps
                lp = self._total_loss(X)
                flat[i] = orig - eps
                lm = self._total_loss(X)
                flat[i] = orig
                num = (lp - lm) / (2 * eps)
                ana = gflat[i]
                denom = max(1e-8, abs(num) + abs(ana))
                worst = max(worst, abs(num - ana) / denom)
            out[name] = worst
        self.tWe1, self.tbe1, self.tWe2, self.tbe2 = saved   # restore
        return out


# ---- online wrapper for the seams ---------------------------------------------------------
@dataclass
class OnlineLatentSurprise:
    """Causal, per-frame latent-surprise stepper for the live perception loop. Holds a trained coder,
    a rolling window of the most recent online latents, and running (EMA) statistics of the raw
    surprise so it can hand the seams a *standardized* surprise (unitless z-score, robust to the
    absolute scale of ||.||). Seam A/B gate on the standardized value; Seam C (the conformal read)
    wants the RAW nonconformity."""
    coder: LatentPredictiveCoder
    _hist: list[np.ndarray] = field(default_factory=list)
    _s_mean: float = 0.0
    _s_var: float = 1.0
    _n: int = 0
    last_raw: float = 0.0
    last_norm: float = 0.0

    def reset(self) -> None:
        self._hist.clear()
        self._s_mean, self._s_var, self._n = 0.0, 1.0, 0
        self.last_raw = self.last_norm = 0.0

    def push(self, sig: np.ndarray) -> dict[str, float]:
        """Feed one retinal code. Predict its latent from the past k frames BEFORE encoding it as the
        target, so the surprise is strictly causal. Returns {raw, norm, ready}. `ready` is False until
        a full k-frame context exists (cold start -> fall back to the pixel path in Seam A)."""
        k = self.coder.cfg.history_k
        z, _ = self.coder.encode(sig)
        z = z[0]
        ztar = self.coder.encode_target(sig)[0]
        ready = len(self._hist) >= k
        raw = 0.0
        if ready:
            ctx = np.concatenate(self._hist[-k:])[None, :]
            zhat, _ = self.coder._predict(ctx)
            raw = float(np.linalg.norm(zhat[0] - ztar))
            self._update_stats(raw)
        self._hist.append(z)
        if len(self._hist) > k:
            self._hist.pop(0)
        norm = (raw - self._s_mean) / (np.sqrt(self._s_var) + 1e-8) if self._n > 2 else 0.0
        self.last_raw, self.last_norm = raw, float(norm)
        return {"raw": raw, "norm": float(norm), "ready": ready}

    def _update_stats(self, raw: float) -> None:
        # Welford-style running mean/var of the raw surprise (for standardization).
        self._n += 1
        d = raw - self._s_mean
        self._s_mean += d / self._n
        d2 = raw - self._s_mean
        self._s_var = (self._s_var * (self._n - 1) + d * d2) / self._n if self._n > 1 else 1.0

    def latent_nonconformity(self) -> float:
        """Seam C — the clean read interface. Returns the most recent RAW latent surprise s_t as a
        nonconformity candidate the conformal gate can later calibrate into a doubt quantile. This is
        interface only: it does NOT import or touch ``packages/conformal_gate`` (that package is under
        active hardening); wiring is a deliberate follow-up. See docs/ATANOR_vjepa_fusion.md Seam C."""
        return self.last_raw


def latent_nonconformity(coder: LatentPredictiveCoder, recent_sigs: np.ndarray) -> float:
    """Stateless Seam C helper: the raw latent surprise of the LAST frame in ``recent_sigs`` given the
    frames before it. A conformity/doubt candidate for the conformal gate to consume downstream —
    exposed as a read interface only, deliberately NOT wired into ``conformal_gate`` here."""
    s = coder.surprise_stream(recent_sigs)
    return float(s[-1]) if s.size else 0.0
