# -*- coding: utf-8 -*-
"""co_allocator — the Conscious-Orchestrator metacognitive effort allocator (NS-4 / C1).

The allocator decides HOW MUCH expensive symbolic reasoning to spend on a query, cheaply, without
meta-regress. It realizes docs/ATANOR_final_gate_research.md §4 (rational metareasoning / Value of
Computation, Russell & Wefald 1991): think while VOC > 0, on a DISCRETE few-rung ladder, with a
META-GREEDY depth-1 decision (one dot product, no meta-plan), a HARD budget, and a set of stop
criteria (Schmitt trigger, minimum-block refractory, Ackerman diminishing stop, verifier-gated stop).

It is a *controller + adapter* over EXISTING engines, imported READ-ONLY:
  * R0 = packages.graph_scale.spreading_activation.spread        (cheap graph lookup + felt confidence)
  * R1/R2 = packages.deliberator.controller.deliberate           (System-2 propose/verify/compose)
  * felt confidence (FOR) = packages.subjective.felt_judgment    (the cheap "feeling of rightness")
  * X1 VOC proxy = packages.evolution.compression_progress       ("will more computation change it?")
  * conflict / abstain-margin = derived from the real spread activation field

Nothing here is wired into the live CO or the live answer path — that is a later operator step. This
package is a *measurable* controller: probe.py runs it against a three-class probe (EASY / HARD /
OVERTHINKING-PRONE) and reports accuracy AND compute versus always-R0 and always-R2 baselines.

BINDING: abstain is the floor (never fabricate); the decision is regress-free (depth-1, discrete,
budgeted); it uses REAL signals, no fabricated "it's wired to CO".
"""
from __future__ import annotations

from .ladder import RungResult, run_r0, run_r1, run_r2, ABSTAIN, spread_work_counter
from .allocator import Allocator, AllocatorConfig, DEFAULT_W, Features, AllocationTrace

__all__ = [
    "RungResult", "run_r0", "run_r1", "run_r2", "ABSTAIN", "spread_work_counter",
    "Allocator", "AllocatorConfig", "DEFAULT_W", "Features", "AllocationTrace",
]
