# -*- coding: utf-8 -*-
"""kind_prediction — domain B for the V7-3 frozen transfer gate.

Predicts an entity's kind from behaviour alone, through `packages.substrate`. Exists to be
frozen: its whole value is that it is NOT touched while the substrate is worked on.
"""
from packages.kind_prediction.eval import CORPUS, PREVALENCES, evaluate, report  # noqa: F401

__all__ = ["CORPUS", "PREVALENCES", "evaluate", "report"]

# Plan v5 §2 tier -- output-only: it reads frozen data and reports a score.
ATANOR_TIER = "perception"
