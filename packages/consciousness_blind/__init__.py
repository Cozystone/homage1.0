# -*- coding: utf-8 -*-
"""ATANOR C-E v1 — EXTERNAL BLIND consciousness-indicator assessment.

The step past the self-audit: a DEVELOPER-BLIND adversarial judge that re-derives every one of the 14
indicator properties from ATANOR's real organs using HELD-OUT stimuli and a falsification control —
structurally separated from `packages.consciousness_audit` (it never imports the self-battery's probe
logic). It is HARDER than the self-audit on purpose: separation of author vs judge, fresh probes the
self-battery never used, and a per-indicator attempt to make each read PRESENT when it shouldn't.

DOCTRINE (binding): NO consciousness claim, ever. This measures INDICATOR PROPERTIES under an
adversarial protocol; the report header states plainly that phenomenal experience / qualia is
scientifically UNDECIDABLE and that this is indicator-property evidence only.
"""
from __future__ import annotations

from packages.consciousness_blind.result import UNDECIDABILITY_HEADER, INDICATORS
from packages.consciousness_blind.judge import run_blind, assess_one

__all__ = ["run_blind", "assess_one", "UNDECIDABILITY_HEADER", "INDICATORS"]
