# -*- coding: utf-8 -*-
"""The answer-time conformal abstention gate.

Wraps a calibrated threshold (marginal, Mondrian per-bin, or CRC) and, given a candidate
answer's real ATANOR signals, returns ACCEPT (certified) or ABSTAIN with a certificate.

Never fabricates: no present signal -> nonconformity 1.0 -> ABSTAIN; a bin with no
calibration -> ABSTAIN (cannot certify) rather than a silent accept. The certificate
records exactly which finite-sample bound backs the decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from packages.conformal_gate import conformal as C
from packages.conformal_gate.nonconformity import SignalVector, nonconformity


@dataclass
class GateDecision:
    accept: bool
    nonconformity: float
    q_hat: float
    alpha: float
    bin: Any
    method: str
    reason: str
    certificate: dict = field(default_factory=dict)


@dataclass
class ConformalGate:
    """A calibrated gate. Build it with one of the classmethods, then call ``decide``.

    ``alpha``            target false-accept level.
    ``q_hat``            marginal acceptance threshold (nonconformity space), or
    ``bin_q_hat``        {bin: q_hat} for Mondrian per-bin thresholds.
    ``method``           'split' | 'mondrian' | 'crc'.
    ``calibration_n``    calibration-set size backing the certificate.
    ``achieved``         calibration-time audit (accept rate / abstain rate / false-accept),
                         for the certificate's "achieved-coverage estimate".
    ``fallback_q_hat``   optional pooled threshold for Mondrian bins that were never seen.
    """
    alpha: float
    method: str = "split"
    q_hat: float = C.ABSTAIN_ALL
    bin_q_hat: dict = field(default_factory=dict)
    calibration_n: int = 0
    guaranteed_bound: Optional[float] = None
    achieved: dict = field(default_factory=dict)
    fallback_q_hat: Optional[float] = None
    weights: Optional[dict] = None

    # ---- constructors -----------------------------------------------------------------
    @classmethod
    def from_calibration(cls, scores: Sequence[float], labels: Sequence, alpha: float,
                         *, weights: Optional[dict] = None) -> "ConformalGate":
        q = C.calibrate(scores, labels, alpha)
        wrong = C._as_wrong_mask(labels)
        rep = C.evaluate(scores, labels, q, alpha)
        return cls(alpha=alpha, method="split", q_hat=q,
                   calibration_n=len(list(labels)),
                   guaranteed_bound=C.guaranteed_conditional_bound(int(wrong.sum()), alpha),
                   achieved=_audit_dict(rep), weights=weights)

    @classmethod
    def from_mondrian(cls, scores: Sequence[float], labels: Sequence, bins: Sequence,
                      alpha: float, *, weights: Optional[dict] = None,
                      fallback_pooled: bool = True) -> "ConformalGate":
        bmap = C.calibrate_mondrian(scores, labels, bins, alpha)
        fallback = C.calibrate(scores, labels, alpha) if fallback_pooled else None
        return cls(alpha=alpha, method="mondrian", bin_q_hat=bmap,
                   calibration_n=len(list(labels)), fallback_q_hat=fallback,
                   weights=weights)

    @classmethod
    def from_crc(cls, scores: Sequence[float], loss_when_accepted: Sequence[float],
                 alpha: float, *, B: Optional[float] = None,
                 weights: Optional[dict] = None) -> "ConformalGate":
        res = C.crc_threshold(scores, loss_when_accepted, alpha, B=B)
        return cls(alpha=alpha, method="crc", q_hat=res.t_hat,
                   calibration_n=res.n, guaranteed_bound=res.bound,
                   achieved={"certifiable": res.certifiable,
                             "empirical_risk": res.empirical_risk, "B": res.B},
                   weights=weights)

    # ---- inference --------------------------------------------------------------------
    def _threshold_for(self, bin: Any) -> tuple[float, str]:
        if self.method == "mondrian":
            if bin in self.bin_q_hat:
                return self.bin_q_hat[bin], f"mondrian bin={bin!r}"
            if self.fallback_q_hat is not None:
                return self.fallback_q_hat, f"mondrian fallback (unseen bin={bin!r})"
            return C.ABSTAIN_ALL, f"mondrian: unseen bin={bin!r}, no fallback -> abstain"
        return self.q_hat, self.method

    def decide(self, signals: SignalVector, *, bin: Any = None) -> GateDecision:
        s = nonconformity(signals, weights=self.weights)
        q, where = self._threshold_for(bin)
        ok = C.accept(s, q)
        if not signals.present():
            reason = "no signal present -> nonconformity=1.0 -> abstain (never fabricate)"
        elif ok:
            reason = f"nonconformity {s:.4f} <= q_hat {q:.4f} ({where}) -> certified accept"
        else:
            reason = f"nonconformity {s:.4f} > q_hat {q:.4f} ({where}) -> abstain"
        cert = {
            "alpha": self.alpha,
            "method": self.method,
            "bin": bin,
            "q_hat": q,
            "nonconformity": s,
            "calibration_n": self.calibration_n,
            "guaranteed_bound": self.guaranteed_bound,
            "guarantee": ("P(accept|wrong) <= alpha (split conformal)"
                          if self.method in ("split", "mondrian")
                          else "E[loss*1(accept)] <= alpha (conformal risk control)"),
            "achieved_estimate": self.achieved,
            "signals_present": list(signals.present().keys()),
        }
        out = GateDecision(accept=ok, nonconformity=s, q_hat=q, alpha=self.alpha,
                           bin=bin, method=self.method, reason=reason, certificate=cert)
        # The receipt is written HERE rather than by the caller, because this organ is reflex tier
        # (plan v5 §2): un-overridable, and therefore obliged to be observable. A receipt a caller
        # could decline to write would make observability a courtesy. The verdict already exists on
        # the line above and `record_decision` swallows everything, so no write outcome can reach
        # the returned decision -- canonical §2.3, an evaluator's result is never altered.
        from packages.conformal_gate.decision_ledger import record_decision
        record_decision(out, lane=str(where))
        return out


def _audit_dict(rep: C.CoverageReport) -> dict:
    return {
        "accept_rate": rep.accept_rate,
        "abstain_rate": rep.abstain_rate,
        "false_accept_given_wrong": rep.false_accept_given_wrong,
        "false_accept_rate": rep.false_accept_rate,
        "error_among_accepted": rep.error_among_accepted,
    }
