# -*- coding: utf-8 -*-
"""acquisition_daemon — the autonomous, SAFE knowledge-acquisition daemon (the OAM engine).

Unattended overnight: endogenously detect the graph's own recurring gaps -> run the existing
acquisition closed loop -> accumulate consensus-verified facts into an operator-approval QUEUE.
It PROPOSES; it never auto-writes the shipped graph. Persisting an approved batch to any real store
requires the existing operator-signed promotion gate + an explicit apply.

Pure GLUE over reused organs: gap_signals reuses flywheel.failure_receipts; the loop is
knowledge_acquisition.acquire; the write gate is candidate_promotion_gate. 0 new fact source in
weights — facts live in the graph with web-consensus provenance, and only behind the operator gate.
"""
from __future__ import annotations

from .daemon import (
    AcquisitionDaemon,
    CycleReport,
    OvernightReport,
    store_digest,
)
from .gap_signals import MIN_PRESSURE, GapLedger, gap_key
from .promotion_queue import AcquisitionQueue, result_to_item
from .structural_gaps import StructuralGapScanner, StructuralHole

__all__ = [
    "AcquisitionDaemon",
    "OvernightReport",
    "CycleReport",
    "store_digest",
    "GapLedger",
    "gap_key",
    "MIN_PRESSURE",
    "AcquisitionQueue",
    "result_to_item",
    "StructuralGapScanner",
    "StructuralHole",
]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Schedule-only. What it acquires is gated elsewhere; when it runs is the orchestrator's call.
ATANOR_TIER = "metabolic"
