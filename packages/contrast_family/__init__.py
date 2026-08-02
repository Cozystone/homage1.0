# -*- coding: utf-8 -*-
"""contrast_family — G0: are the discrimination contrasts substitutable, or is each site stuck?

Plan v6 §7-§8. The cheapest available falsification of the consolidation thesis: it needs no frozen
domain, and if no contrast beats its incumbent at a site it was not written for, there is nothing to
transfer. See ``contrasts.probe``.
"""
from packages.contrast_family.contrasts import (  # noqa: F401
    ALL, CONTROLS, NON_MEMBERS, REAL, Admission, SiteResult, admit, cross_swap, probe)

__all__ = ["ALL", "CONTROLS", "NON_MEMBERS", "REAL", "Admission", "SiteResult",
           "admit", "cross_swap", "probe"]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Reflex: it is an evaluator of the plan's own central thesis, and an evaluator the orchestrator
# could overrule measures nothing.
ATANOR_TIER = "reflex"
