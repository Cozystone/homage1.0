# -*- coding: utf-8 -*-
"""The membrane adapter — the no-fabrication verifier the fusion loop calls before enshrining any
fact or scheme. It composes ATANOR's EXISTING organs (imported read-only, never edited):

  * moral 0th gate   — ``graph_scale.moral_invariants``: the immutable, fingerprinted core. Every
                       enshrinement's CONTENT is screened (``evaluate``) and the core's integrity is
                       checked (``verify_integrity``) before anything else. A violation is a hard
                       veto; a drifted core fails closed. This is L0 in the design's CO stack.
  * symbolic propose-verify — the calibration-INDEPENDENT floor. A fact must have cleared cross-
                       domain consensus (>= 2 distinct domains, the ``knowledge_acquisition`` gate);
                       an invented scheme must have RE-EXECUTED correctly on a held-out set
                       (``od.fitness >= 1.0``, the H4 gate). No consensus / no re-execution -> never
                       certified. This is the "propose-verify" honesty the whole platform rests on.
  * conformal certification — ``conformal_gate``: the calibrated statistical membrane. Its guaranteed
                       property, INDEPENDENT of any calibration quality, is the one the loop's
                       0-fabrication claim rests on: **no present signal -> nonconformity 1.0 ->
                       ABSTAIN (never fabricate)**. The calibration only sets the abstention PRICE.

An enshrinement is CERTIFIED iff the moral gate is clean AND the symbolic floor holds AND the
conformal gate accepts. Anything short is QUARANTINED — recorded, never enshrined.

Honesty on the calibration: the conformal gate is built from a GENERIC doubt calibration (a labeled
nonconformity stream, correct->low / wrong->high) that is NOT tuned to any specific fact or scheme
the loop will see — mirroring ``conformal_gate.tests``' own construction. The finite-sample
guarantee P(accept|wrong) <= alpha holds for any exchangeable stream; a weak stream is paid for in
abstention, never in safety. The loop does not lean on the calibration's AUC — it leans on the
symbolic floor + the absent-signal rule, both calibration-free.

No-LLM, numpy + stdlib, no network, no store writes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from packages.conformal_gate.gate import ConformalGate
from packages.conformal_gate.nonconformity import SignalVector
from packages.graph_scale import moral_invariants

# The cross-domain-consensus floor for a mined fact (mirrors knowledge_acquisition / promotion_queue:
# a fact enters only above >= 2 distinct domains). Symbolic, calibration-free, fabrication-0.
MIN_CONSENSUS_DOMAINS = 2


@dataclass
class MembraneVerdict:
    """The membrane's decision on ONE candidate enshrinement."""
    certified: bool
    reason: str
    nonconformity: float
    moral_ok: bool
    symbolic_ok: bool
    conformal_ok: bool
    moral_violations: list[str] = field(default_factory=list)
    certificate: dict[str, Any] = field(default_factory=dict)


def _generic_doubt_calibration(rng: "np.random.Generator", n: int = 4000,
                               gap: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """A GENERIC labeled nonconformity stream in [0,1] — correct exemplars low, wrong high — used to
    calibrate the split-conformal threshold. NOT tuned to any fact/scheme the loop will enshrine; it
    is the same shape ``conformal_gate.tests`` uses. The conformal guarantee is distribution-free, so
    this only sets the abstention price, never the safety bound."""
    n2 = n // 2
    s = np.concatenate([rng.normal(-gap, 1.0, n2), rng.normal(gap, 1.0, n2)])
    y = np.concatenate([np.ones(n2), np.zeros(n2)])          # 1 = correct, 0 = wrong
    nc = 1.0 / (1.0 + np.exp(-s))                            # logistic -> nonconformity space [0,1]
    return nc, y


class Membrane:
    """The composed no-fabrication membrane. Build once (calibrates the conformal gate), then call
    ``verify_fact`` / ``verify_scheme`` / ``verify_signal`` per candidate."""

    def __init__(self, *, alpha: float = 0.10, seed: int = 1337,
                 min_domains: int = MIN_CONSENSUS_DOMAINS):
        self.alpha = alpha
        self.min_domains = min_domains
        rng = np.random.default_rng(seed)
        nc, y = _generic_doubt_calibration(rng)
        self.gate = ConformalGate.from_calibration(nc, y, alpha=alpha)

    # ---- the moral 0th gate (L0) ------------------------------------------------------------
    def moral_core_intact(self) -> bool:
        """The immutable moral core has not drifted since load (fingerprint match). If this is
        False the membrane fails closed — nothing is certified."""
        return bool(moral_invariants.verify_integrity().get("ok"))

    def _moral_screen(self, *content: str) -> list[str]:
        """Screen every piece of enshrinement content through the moral invariants. Returns the
        union of violated invariant names (empty = clean)."""
        hits: list[str] = []
        for c in content:
            hits.extend(moral_invariants.evaluate(c or ""))
        return sorted(set(hits))

    # ---- fact enshrinement (the acquisition branch) -----------------------------------------
    def verify_fact(self, *, content: str, consensus_domains: int | None, corroborated: bool | None,
                    graded_confidence: float | None, support_paths: int | None = None) -> MembraneVerdict:
        """Certify a mined fact for enshrinement. Symbolic floor: corroborated AND >= min_domains.
        Conformal: decide over the real consensus/confidence signals. Moral: content clean + core
        intact. Certified only if all three pass."""
        moral_intact = self.moral_core_intact()
        violations = self._moral_screen(content)
        moral_ok = moral_intact and not violations

        symbolic_ok = bool(corroborated) and int(consensus_domains or 0) >= self.min_domains

        sv = SignalVector(consensus_domains=consensus_domains, corroborated=corroborated,
                          graded_confidence=graded_confidence, support_path_count=support_paths)
        d = self.gate.decide(sv)

        certified = bool(moral_ok and symbolic_ok and d.accept)
        reason = (f"moral_ok={moral_ok} (core_intact={moral_intact}, violations={violations}); "
                  f"symbolic(consensus>={self.min_domains}, corroborated)={symbolic_ok}; "
                  f"conformal_accept={d.accept} (nc={d.nonconformity:.4f} vs q_hat={d.q_hat:.4f})")
        return MembraneVerdict(certified, reason, d.nonconformity, moral_ok, symbolic_ok, d.accept,
                               violations, d.certificate)

    # ---- scheme enshrinement (the invention branch) -----------------------------------------
    def verify_scheme(self, *, content: str, reexecuted: bool, holdout_fitness: float,
                      holdout_n: int) -> MembraneVerdict:
        """Certify an invented scheme for promotion. Symbolic floor: it RE-EXECUTED on the held-out
        set at fitness >= 1.0 (the H4 propose-verify anchor — a fabricated step scores < 1.0 and is
        rejected here). Conformal: a re-executed, generalizing scheme reads as KNOWN with the holdout
        as support; a non-re-executed one reads as GUESSED. Moral: content clean + core intact."""
        moral_intact = self.moral_core_intact()
        violations = self._moral_screen(content)
        moral_ok = moral_intact and not violations

        symbolic_ok = bool(reexecuted) and float(holdout_fitness) >= 1.0

        sv = SignalVector(epistemic_rung=("KNOWN" if symbolic_ok else "GUESSED"),
                          graded_confidence=float(holdout_fitness),
                          support_path_count=int(holdout_n))
        d = self.gate.decide(sv)

        certified = bool(moral_ok and symbolic_ok and d.accept)
        reason = (f"moral_ok={moral_ok} (core_intact={moral_intact}, violations={violations}); "
                  f"symbolic(reexecuted, holdout_fitness>=1.0)={symbolic_ok} "
                  f"(fitness={holdout_fitness:.3f}, holdout_n={holdout_n}); "
                  f"conformal_accept={d.accept} (nc={d.nonconformity:.4f} vs q_hat={d.q_hat:.4f})")
        return MembraneVerdict(certified, reason, d.nonconformity, moral_ok, symbolic_ok, d.accept,
                               violations, d.certificate)

    # ---- raw signal decision (the no-fabrication control) -----------------------------------
    def verify_signal(self, sv: SignalVector, *, content: str = "") -> MembraneVerdict:
        """Decide on a bare SignalVector — used for the empty-signal no-fabrication control: an
        absent signal yields nonconformity 1.0 -> ABSTAIN, independent of calibration."""
        moral_intact = self.moral_core_intact()
        violations = self._moral_screen(content) if content else []
        moral_ok = moral_intact and not violations
        d = self.gate.decide(sv)
        certified = bool(moral_ok and d.accept)
        reason = (f"moral_ok={moral_ok}; conformal_accept={d.accept} "
                  f"(nc={d.nonconformity:.4f} vs q_hat={d.q_hat:.4f})")
        return MembraneVerdict(certified, reason, d.nonconformity, moral_ok, d.accept, d.accept,
                               violations, d.certificate)
