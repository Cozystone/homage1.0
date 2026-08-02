# -*- coding: utf-8 -*-
"""Neuro-ledger self-registration for the deliberator.

The deliberator introduces ZERO new trained parameters: it is a pure CONTROLLER that composes organs
already registered in the ledger. Its only learned state is the metacog span baselines it writes,
which are registered separately as ``metacog_baselines`` (Welford sufficient statistics, 0 trained
weights). So this entry declares fact_source=False and fallback_params=0, in the experimental/advisory
tier (enforced=False) — it costs nothing against the No-LLM parameter budget.

packages.neuro_ledger.ledger._registry() appends this entry via a guarded import, so the registry
sweep accounts for the deliberator without coupling the ledger to this package's import health.
"""
from __future__ import annotations

from packages.neuro_ledger.ledger import Organ


def ledger_entry() -> Organ:
    """The deliberator's honest ledger row: a zero-parameter, non-fact-source control organ."""
    return Organ(
        id="deliberator_v1",
        path="packages/deliberator/controller.py",
        role="System-2 backward-chaining deliberation controller: structurally decomposes a multi-step "
             "question into typed sub-goals, dispatches each to an EXISTING grounded organ (mechanism "
             "reasoner, situation belief tracker, relational graph lane, safe arithmetic evaluator, L3 "
             "program synthesis), VERIFIES every step, and composes the answer ONLY from verified steps; "
             "abstains honestly if any required step is ungrounded. Holds NO trained weights — a "
             "controller over already-registered organs; never a fact source",
        gate="deliberator propose-verify-compose chain (behind each organ's own grounding gate; "
             "MEC-wrapped via packages.metacog.record_span)",
        artifacts=[],                    # no weight artifacts — a controller; learned state lives in metacog_baselines
        fact_source=False,               # INVARIANT: a controller is never a fact source
        enforced=False,                  # experimental/advisory tier: zero budget impact
        status="active",
        # honest count: 0 trained parameters. The only learned state (MEC span baselines) is counted
        # once under 'metacog_baselines'; the composed organs carry their own registered footprints.
        fallback_params=0,
    )
