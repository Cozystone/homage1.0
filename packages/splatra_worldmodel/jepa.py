# -*- coding: utf-8 -*-
"""JEPA dynamics predictor over the turbovec light vector (design sec 3 recipe, on 3D fields).

The V-JEPA recipe, at our scale, action-conditioned (V-JEPA 2-AC), predicting the next
physical field state in a LEARNED EMBEDDING of the turbovec light vector -- not in pixels,
not in raw particles:

  * Context encoder f_theta : light_vector -> embedding e_t.
  * Predictor      g_phi    : (e_t, action) -> predicted embedding e_hat_{t+1}.
  * Target encoder f_xi     : EMA (stop-gradient) copy of f_theta -> true e*_{t+1}.
  * Latent surprise         : s_t = || e_hat_{t+1} - e*_{t+1} ||  (the single JEPA signal).
  * Collapse guard          : VICReg-style variance + covariance terms on e_t so the
                              embedding cannot shrink to a constant (EMA asymmetry + VICReg).

Non-generative: there is NO pixel decoder in the predictive loss. A separate learned
``FieldDecoder`` maps a predicted embedding -> per-particle delta; per the honest boundary
(design sec 9) that decode is the acknowledged reconstruction MOVED into the compressed 3D
field, trained on a DETACHED embedding so no reconstruction gradient leaks into the
predictive latent. The decoder's output is a PROPOSAL -- physics_truth.py verifies it.

Light torch, CPU, No-LLM. Single model, <= 25M params (report the actual count).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn


def _mlp(d_in: int, d_hidden: int, d_out: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(d_in, d_hidden),
        nn.LayerNorm(d_hidden),
        nn.GELU(),
        nn.Linear(d_hidden, d_out),
    )


class ContextEncoder(nn.Module):
    """f_theta: turbovec light vector -> embedding."""

    def __init__(self, d_light: int, d_hidden: int, d_emb: int):
        super().__init__()
        self.net = _mlp(d_light, d_hidden, d_emb)

    def forward(self, light: torch.Tensor) -> torch.Tensor:
        return self.net(light)


class Predictor(nn.Module):
    """g_phi: (embedding, action) -> predicted next embedding."""

    def __init__(self, d_emb: int, d_action: int, d_hidden: int):
        super().__init__()
        self.net = _mlp(d_emb + d_action, d_hidden, d_emb)

    def forward(self, emb: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([emb, action], dim=-1))


class FieldDecoder(nn.Module):
    """h_psi: predicted embedding -> per-particle delta (3N). The acknowledged decode."""

    def __init__(self, d_emb: int, d_hidden: int, n_particles: int):
        super().__init__()
        self.n = n_particles
        self.net = _mlp(d_emb, d_hidden, 3 * n_particles)

    def forward(self, emb: torch.Tensor) -> torch.Tensor:
        return self.net(emb)  # (B, 3N)


def vicreg_terms(emb: torch.Tensor, gamma: float = 1.0, eps: float = 1e-4
                 ) -> tuple[torch.Tensor, torch.Tensor]:
    """VICReg variance + covariance terms (collapse guard).

    variance: hinge that pushes each embedding dim's std toward >= gamma (prevents shrink to
    a constant). covariance: pushes off-diagonal feature covariances toward 0 (prevents dims
    from all encoding the same thing). Returns (var_term, cov_term), both to be MINIMIZED.
    """
    b, d = emb.shape
    emb_c = emb - emb.mean(dim=0, keepdim=True)
    std = torch.sqrt(emb_c.var(dim=0) + eps)
    var_term = torch.mean(torch.relu(gamma - std))
    if b > 1:
        cov = (emb_c.T @ emb_c) / (b - 1)
        off = cov - torch.diag(torch.diag(cov))
        cov_term = (off ** 2).sum() / d
    else:
        cov_term = torch.zeros((), dtype=emb.dtype)
    return var_term, cov_term


@dataclass
class JEPAConfig:
    d_light: int
    n_particles: int
    d_action: int = 3
    d_hidden: int = 128
    d_emb: int = 64
    ema_decay: float = 0.996
    lambda_var: float = 25.0
    lambda_cov: float = 1.0


class TurbovecJEPA(nn.Module):
    """The full JEPA-over-turbovec dynamics predictor + its EMA target + a decode head."""

    def __init__(self, cfg: JEPAConfig):
        super().__init__()
        self.cfg = cfg
        self.context = ContextEncoder(cfg.d_light, cfg.d_hidden, cfg.d_emb)
        self.predictor = Predictor(cfg.d_emb, cfg.d_action, cfg.d_hidden)
        self.decoder = FieldDecoder(cfg.d_emb, cfg.d_hidden, cfg.n_particles)
        # EMA target encoder: same architecture, NOT trained by gradients (stop-grad).
        self.target = ContextEncoder(cfg.d_light, cfg.d_hidden, cfg.d_emb)
        self.target.load_state_dict(self.context.state_dict())
        for p in self.target.parameters():
            p.requires_grad_(False)

    # ---- forward pieces ---------------------------------------------------------------
    def encode(self, light: torch.Tensor) -> torch.Tensor:
        return self.context(light)

    @torch.no_grad()
    def target_encode(self, light: torch.Tensor) -> torch.Tensor:
        return self.target(light)

    def predict_embedding(self, light_t: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return self.predictor(self.context(light_t), action)

    def decode_delta(self, emb: torch.Tensor) -> torch.Tensor:
        return self.decoder(emb).reshape(emb.shape[0], self.cfg.n_particles, 3)

    @torch.no_grad()
    def update_target(self) -> None:
        d = self.cfg.ema_decay
        for tp, sp in zip(self.target.parameters(), self.context.parameters()):
            tp.mul_(d).add_(sp, alpha=1.0 - d)

    # ---- convenience for inference ----------------------------------------------------
    @torch.no_grad()
    def predict_next_positions(self, light_t: np.ndarray, action: np.ndarray,
                               cur_pos: np.ndarray) -> np.ndarray:
        """light vector + action + true current positions -> predicted next positions."""
        self.eval()
        lt = torch.as_tensor(light_t, dtype=torch.float32).unsqueeze(0)
        at = torch.as_tensor(action, dtype=torch.float32).unsqueeze(0)
        emb_hat = self.predictor(self.context(lt), at)
        delta = self.decoder(emb_hat).reshape(self.cfg.n_particles, 3).cpu().numpy()
        return np.asarray(cur_pos, dtype=np.float64) + delta.astype(np.float64)

    @torch.no_grad()
    def latent_surprise(self, light_t: np.ndarray, action: np.ndarray,
                        light_next: np.ndarray) -> float:
        """s_t = || predicted embedding - EMA-target embedding of the true next field ||."""
        self.eval()
        lt = torch.as_tensor(light_t, dtype=torch.float32).unsqueeze(0)
        at = torch.as_tensor(action, dtype=torch.float32).unsqueeze(0)
        ln = torch.as_tensor(light_next, dtype=torch.float32).unsqueeze(0)
        emb_hat = self.predictor(self.context(lt), at)
        emb_star = self.target(ln)
        return float(torch.linalg.vector_norm(emb_hat - emb_star, dim=-1).item())

    # ---- accounting -------------------------------------------------------------------
    def param_counts(self) -> dict[str, int]:
        def n(mod: nn.Module) -> int:
            return int(sum(p.numel() for p in mod.parameters()))
        trainable = int(sum(p.numel() for p in self.parameters() if p.requires_grad))
        return {
            "context_encoder": n(self.context),
            "predictor": n(self.predictor),
            "decoder": n(self.decoder),
            "ema_target": n(self.target),
            "trainable_total": trainable,
            "total_incl_ema": int(sum(p.numel() for p in self.parameters())),
        }


@dataclass
class TrainReport:
    epochs: int
    final_pred_loss: float
    final_decode_loss: float
    final_var_term: float
    final_cov_term: float
    emb_std_mean: float
    emb_std_min: float
    param_counts: dict[str, int]


def train_jepa(cfg: JEPAConfig, light: np.ndarray, action: np.ndarray,
               light_next: np.ndarray, delta: np.ndarray, *, epochs: int = 1500,
               lr: float = 1e-3, batch: int = 128, seed: int = 0,
               log_every: int = 0) -> tuple[TurbovecJEPA, TrainReport]:
    """Train the JEPA predictive latent + the decode head on clean (verified) transitions.

    Predictive loss (latent only): || g_phi(f_theta(light_t), a) - sg f_xi(light_{t+1}) ||^2
                                    + lambda_var * var + lambda_cov * cov   (VICReg).
    Decode loss (separate, detached): || h_psi(sg e_hat) - true_delta ||^2  -- trains the
    decoder without leaking reconstruction gradient into the predictive latent (design sec 9).
    """
    torch.manual_seed(seed)
    model = TurbovecJEPA(cfg)

    L = torch.as_tensor(light, dtype=torch.float32)
    A = torch.as_tensor(action, dtype=torch.float32)
    LN = torch.as_tensor(light_next, dtype=torch.float32)
    D = torch.as_tensor(delta, dtype=torch.float32).reshape(delta.shape[0], -1)
    n = L.shape[0]

    jepa_params = list(model.context.parameters()) + list(model.predictor.parameters())
    opt_jepa = torch.optim.Adam(jepa_params, lr=lr)
    opt_dec = torch.optim.Adam(model.decoder.parameters(), lr=lr)

    g = torch.Generator().manual_seed(seed + 1)
    pred_loss = dec_loss = var_t = cov_t = torch.zeros(())
    model.train()
    for ep in range(epochs):
        idx = torch.randperm(n, generator=g)[:batch] if n > batch else torch.arange(n)
        lt, at, ln, dt = L[idx], A[idx], LN[idx], D[idx]

        # --- predictive (JEPA) update: latent only, EMA stop-grad target ---
        emb_t = model.context(lt)
        emb_hat = model.predictor(emb_t, at)
        with torch.no_grad():
            emb_star = model.target(ln)
        pred_loss = ((emb_hat - emb_star) ** 2).sum(dim=-1).mean()
        var_t, cov_t = vicreg_terms(emb_t, gamma=1.0)
        loss_jepa = pred_loss + cfg.lambda_var * var_t + cfg.lambda_cov * cov_t
        opt_jepa.zero_grad(set_to_none=True)
        loss_jepa.backward()
        opt_jepa.step()
        model.update_target()

        # --- decode update: detached predicted embedding -> true delta (no leak) ---
        with torch.no_grad():
            emb_hat_d = model.predictor(model.context(lt), at)
        dec_pred = model.decoder(emb_hat_d)
        dec_loss = ((dec_pred - dt) ** 2).mean()
        opt_dec.zero_grad(set_to_none=True)
        dec_loss.backward()
        opt_dec.step()

        if log_every and (ep % log_every == 0 or ep == epochs - 1):
            print(f"[jepa] ep={ep} pred={pred_loss.item():.5f} dec={dec_loss.item():.5f} "
                  f"var={var_t.item():.4f} cov={cov_t.item():.4f}")

    # collapse diagnostics on the full set
    model.eval()
    with torch.no_grad():
        emb_all = model.context(L)
        std = emb_all.std(dim=0)
    report = TrainReport(
        epochs=epochs,
        final_pred_loss=float(pred_loss.item()),
        final_decode_loss=float(dec_loss.item()),
        final_var_term=float(var_t.item()),
        final_cov_term=float(cov_t.item()),
        emb_std_mean=float(std.mean().item()),
        emb_std_min=float(std.min().item()),
        param_counts=model.param_counts(),
    )
    return model, report
