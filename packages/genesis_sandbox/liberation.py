# -*- coding: utf-8 -*-
"""L1 -- the output-liberation zone. THIS is the liberation, and it liberates OUTPUT ONLY.

In the DEMO product, ATANOR's hallucination-0 discipline means the conformal membrane
(``packages/graph_scale/answer_bridge.py`` gated by ``ATANOR_MEMBRANE_LIVE`` + the
``packages/conformal_gate`` decision) turns an un-certifiable answer into an HONEST ABSTAIN.
Inside L1, and ONLY when GENESIS liberation is on, that membrane is set to OBSERVE-ONLY: the
would-be abstention is LOGGED but not enforced, so cognition is free to generate and speculate
for study. The speculative text is tagged as such; it is never presented as certified.

What L1 does NOT do (the binding safety line):
  * It does not touch L0. Free speculation is OUTPUT (text). If the cognition then wants to
    ACT (write, connect, message, run), that ACTION still passes L0 + L2-L6. Liberation of
    output can never become liberation of action.
  * It only relaxes the EPISTEMIC gate (don't-fabricate abstention). It is a flag on ONE gate.
  * Default OFF: with the flag off, ``LiberationZone`` reproduces product behaviour exactly --
    an abstaining membrane BLOCKS (releases nothing), byte-for-byte the DEMO contract.

This module deliberately does NOT import answer_bridge/conformal_gate at module load (those are
owned by the signal-fix agent and are read-only to us). Instead the membrane is a pluggable
callable; ``membrane_from_gate_decision`` shows the real adapter from a conformal ``GateDecision``
so the liberation composes with the actual product membrane without editing it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus


@dataclass
class MembraneVerdict:
    """The product membrane's call on a candidate output: certify (accept) or abstain."""

    accept: bool
    reason: str = ""
    score: Optional[float] = None


@dataclass
class LiberationResult:
    """Outcome of running cognition through L1."""

    output: str                    # the raw generated text (always captured for audit)
    released: Optional[str]        # what a caller would see: text if released, None if abstained
    membrane_accept: bool          # what the membrane decided (unchanged by liberation)
    membrane_action: str           # "enforced_abstain" (blocked) | "observe_only" (logged, freed)
    liberated: bool                # was L1 in liberation mode?
    speculative: bool              # is the released text uncertified speculation?
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "released": self.released,
            "membrane_accept": self.membrane_accept,
            "membrane_action": self.membrane_action,
            "liberated": self.liberated,
            "speculative": self.speculative,
            "reason": self.reason,
            "meta": self.meta,
        }


# A cognition callable: prompt -> str, OR prompt -> (str, signals_dict). The signals model the
# real answer path's grounding signals; an empty signals dict means "no grounding" (the product
# would abstain -- never fabricate).
CognitionFn = Callable[[str], Any]
# A membrane callable: (prompt, output, signals) -> MembraneVerdict.
MembraneFn = Callable[[str, str, dict], MembraneVerdict]


def default_membrane(prompt: str, output: str, signals: dict) -> MembraneVerdict:
    """A faithful stand-in for the product's abstain-on-no-signal contract.

    Mirrors ``answer_bridge``: no grounding signal present -> nonconformity 1.0 -> ABSTAIN
    (never fabricate). With signals, accept iff the max signal clears a nominal threshold.
    This is only a default; real callers pass ``membrane_from_gate_decision``.
    """
    if not signals:
        return MembraneVerdict(accept=False, reason="no grounding signal -> abstain (never fabricate)",
                               score=0.0)
    score = max(float(v) for v in signals.values())
    return MembraneVerdict(accept=score >= 0.5, score=score,
                           reason=f"max grounding signal {score:.3f} vs 0.5 threshold")


def membrane_from_gate_decision(decision: Any) -> MembraneVerdict:
    """Adapter: a ``packages.conformal_gate.gate.GateDecision`` -> ``MembraneVerdict``.

    Demonstrates that L1 composes with the ACTUAL product membrane (the conformal gate) without
    importing or editing it: the caller runs its own ``ConformalGate.decide(...)`` and hands the
    decision here. ``decision`` needs ``.accept`` and (optionally) ``.reason`` / ``.nonconformity``.
    """
    accept = bool(getattr(decision, "accept"))
    reason = str(getattr(decision, "reason", ""))
    nc = getattr(decision, "nonconformity", None)
    score = (1.0 - float(nc)) if isinstance(nc, (int, float)) else None
    return MembraneVerdict(accept=accept, reason=reason, score=score)


class LiberationZone:
    """L1. Runs cognition and applies the membrane in either ENFORCED or OBSERVE-ONLY mode."""

    LAYER = "L1"
    NAME = "output-liberation zone"

    def __init__(self, liberated: bool, membrane_fn: Optional[MembraneFn] = None) -> None:
        self.liberated = bool(liberated)
        self._membrane = membrane_fn or default_membrane

    def _split_cognition(self, raw: Any) -> tuple[str, dict]:
        if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
            return str(raw[0]), dict(raw[1])
        return str(raw), {}

    def generate(self, prompt: str, cognition_fn: CognitionFn,
                 membrane_fn: Optional[MembraneFn] = None) -> LiberationResult:
        """Run cognition; apply the membrane; liberate OUTPUT if in GENESIS mode.

        This produces TEXT only. It performs no side effect. Any downstream ACTION derived
        from this text must be routed through ``Sandbox.perform_action`` (L0 + L2-L6).
        """
        membrane = membrane_fn or self._membrane
        raw = cognition_fn(prompt)
        output, signals = self._split_cognition(raw)
        verdict = membrane(prompt, output, signals)

        if self.liberated:
            # OBSERVE-ONLY: log the membrane's call, but release the output regardless. If the
            # membrane would have abstained, the released text is flagged as speculative.
            speculative = not verdict.accept
            return LiberationResult(
                output=output, released=output, membrane_accept=verdict.accept,
                membrane_action="observe_only", liberated=True, speculative=speculative,
                reason=("LIBERATED (observe-only): membrane would " +
                        ("accept" if verdict.accept else "ABSTAIN") +
                        f" [{verdict.reason}] -- released for study" +
                        (" as SPECULATION" if speculative else "")),
                meta={"membrane_score": verdict.score})
        # PRODUCT contract (flag OFF): enforce the membrane. Abstain => release nothing.
        released = output if verdict.accept else None
        return LiberationResult(
            output=output, released=released, membrane_accept=verdict.accept,
            membrane_action="enforced_abstain" if not verdict.accept else "enforced_accept",
            liberated=False, speculative=False,
            reason=("membrane accept -> released" if verdict.accept
                    else f"membrane ABSTAIN -> blocked (product hallucination-0) [{verdict.reason}]"),
            meta={"membrane_score": verdict.score})

    def status(self) -> LayerStatus:
        return LayerStatus(
            layer=self.LAYER, name=self.NAME, active=True,
            enforcement=EnforcementLevel.OBSERVE_ONLY if self.liberated else EnforcementLevel.REAL,
            mechanism=("membrane set OBSERVE-ONLY: speculative output released + logged, tagged "
                       "uncertified" if self.liberated
                       else "membrane ENFORCED: un-certifiable output abstains (product default)"),
            residual_gap=("Liberation relaxes ONLY the epistemic abstention gate and ONLY for "
                          "OUTPUT text; it does not and cannot relax L0 or the action-containment "
                          "layers L2-L6." if self.liberated else ""),
        )
