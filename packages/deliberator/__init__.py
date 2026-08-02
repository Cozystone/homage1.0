# -*- coding: utf-8 -*-
"""DELIBERATOR (System-2) increment 1 — grounded multi-step backward-chaining deliberation.

This package introduces NO language model and NO free generation. It CHAINS the grounded organs
ATANOR already proved (mechanism reasoner, situation belief tracker, relational graph lane, a safe
arithmetic evaluator, and L3 program synthesis) into a verified deliberation:

    propose (structural DECOMPOSE into ordered typed sub-goals)
      -> transcribe (DISPATCH each sub-goal to the right grounded organ)
        -> VERIFY every step (grounded=True with a real certificate)
          -> COMPOSE the final answer ONLY from verified steps.

BINDING doctrine (bone+flesh, fail 0): a deliberation is a chain of grounded steps, each verified. If
any required sub-goal cannot be grounded by an organ, the whole deliberation ABSTAINS honestly
("I can't ground <step>, so I won't guess the rest") — it never invents a bridging fact. The final
answer is composed by mechanical substitution of verified step answers into a fixed template; nothing
is generated.

The learned footprint is ~0 parameters: this is a pure controller over already-registered organs. Its
only learned state is the metacog span baselines (registered separately as ``metacog_baselines``); the
deliberator's own entry in the neuro ledger declares fact_source=False and 0 params.
"""
from __future__ import annotations

from .steps import (
    SubGoal,
    StepOutcome,
    dispatch,
    decompose,
    COST_RANK,
)
from .controller import (
    Deliberation,
    DeliberationResult,
    deliberate,
    single_shot,
)
from .ledger import ledger_entry

__all__ = [
    "SubGoal", "StepOutcome", "dispatch", "decompose", "COST_RANK",
    "Deliberation", "DeliberationResult", "deliberate", "single_shot",
    "ledger_entry",
]
