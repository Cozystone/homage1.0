# -*- coding: utf-8 -*-
"""perception_recurrence — within-percept recurrent refinement (the deep sensory feedback loop RPT
asks for). A noisy/ambiguous perceptual read is iteratively sharpened by folding top-down context back
onto fixed bottom-up evidence until it stabilises — or, when evidence and context are insufficient,
honestly gives up without fabricating confidence.

This is the WITHIN-percept complement to the GATE-level recurrence in packages/perception/attention.py
and the SEQUENCE-level recurrence in packages/situation_model/state_tracker.py.
"""
from __future__ import annotations

from packages.perception_recurrence.refinement import (  # noqa: F401
    RefinementTrace,
    refine,
    refine_with_plausibility,
    plausibility_prior,
    ledger_entry,
)

__all__ = ["RefinementTrace", "refine", "refine_with_plausibility", "plausibility_prior", "ledger_entry"]
