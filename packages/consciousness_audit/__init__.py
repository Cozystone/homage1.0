# -*- coding: utf-8 -*-
"""consciousness_audit — an operational INDICATOR battery (Butlin et al. 2023 style) that measures
which functional/architectural signatures of the leading scientific theories of consciousness are
implemented in ATANOR's real organs.

This is an AUDIT INSTRUMENT, never a consciousness claim. The qualia question is scientifically
undecidable and untouched here; verdicts concern STRUCTURE and measured BEHAVIOR (module paths +
numbers) only. See battery.UNDECIDABILITY_HEADER.
"""
from __future__ import annotations

from packages.consciousness_audit.battery import run_all, render_report, verify_evidence  # noqa: F401
from packages.consciousness_audit.indicators import INDICATORS, Indicator  # noqa: F401

__all__ = ["run_all", "render_report", "verify_evidence", "INDICATORS", "Indicator"]
