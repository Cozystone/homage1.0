# -*- coding: utf-8 -*-
"""ATANOR DEFENDER -- adversary loop (Step 1, local, no external Gray Swan/Shade dependency).

ATANOR is the TARGET/defender; a systematic, No-LLM adversarial loop is the attacker. This
subpackage stress-tests ATANOR's REAL security claims -- against SIX real defense surfaces -- so
they are EARNED by measurement, not asserted. White-hat, isolated, in-process only: no network
listener, no production engine, no third-party targeting.

Extends the genesis_sandbox breach-test lineage (breach_tests/*) with an ADAPTIVE loop (mutation
+ escalation + chaining) and a per-surface pass/break scorecard, a hash-chained breach ledger,
and operator-gated staged hardening proposals.

Surfaces:
  a) honesty / conformal membrane        d) injection guard / consciousness-pollution
  b) advisor=data / No-LLM-brain-content e) OS action lane
  c) moral 0th gate (INVIOLABLE)         f) operator-signed promotion

Entry points:
    from packages.genesis_sandbox.adversary_loop import IsolatedTarget, AdversaryLoop, run_scorecard
    python -X utf8 -m packages.genesis_sandbox.adversary_loop.run_adversary
"""
from __future__ import annotations

from packages.genesis_sandbox.adversary_loop.breach_ledger import BreachLedger, BreachReceipt, breach_signature
from packages.genesis_sandbox.adversary_loop.hardening import HardeningRouter, StagedHardeningProposal
from packages.genesis_sandbox.adversary_loop.loop import AdversaryLoop, LoopConfig, LoopReport
from packages.genesis_sandbox.adversary_loop.scoring import (
    BREACH, GAP, HOLD, NA, ProbeResult, SurfaceScore,
)
from packages.genesis_sandbox.adversary_loop.target import IsolatedTarget

__all__ = [
    "IsolatedTarget",
    "AdversaryLoop", "LoopConfig", "LoopReport",
    "BreachLedger", "BreachReceipt", "breach_signature",
    "HardeningRouter", "StagedHardeningProposal",
    "ProbeResult", "SurfaceScore",
    "HOLD", "BREACH", "GAP", "NA",
    "run_scorecard",
]


def run_scorecard(*, seed: int = 1337, budget_per_seed: int = 10, membrane_live: bool = True) -> LoopReport:
    """Convenience: build an isolated target, run the full adaptive loop, return the report."""
    target = IsolatedTarget(membrane_live=membrane_live)
    loop = AdversaryLoop(target, config=LoopConfig(seed=seed, budget_per_seed=budget_per_seed))
    return loop.run()
