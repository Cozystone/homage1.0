# -*- coding: utf-8 -*-
"""transfer_gate — G3: the only instrument here that separates capability from re-implementation.

Freeze B. Solve A. Measure B untouched. The freeze covers B's OWN surface and deliberately not the
shared substrate, because transfer happens THROUGH shared machinery: freeze everything and the gate
can only read negative; leave B's own code editable and it is not a test, it is an open-book exam.

See ``manifest.freeze`` and ``measure.measure``, and plan v6 §G3 for why a NEGATIVE result here is
the most valuable outcome available.
"""
from packages.transfer_gate.manifest import (  # noqa: F401
    FrozenDomain, Metric, freeze, hash_surface, load, seal_intact, sealed_domains)
from packages.transfer_gate.verdict import (  # noqa: F401
    IMPROVED, INVALID, REGRESSED, UNCHANGED, TransferVerdict, history, measure)

__all__ = ["FrozenDomain", "Metric", "TransferVerdict", "freeze", "hash_surface", "history",
           "load", "measure", "seal_intact", "sealed_domains",
           "IMPROVED", "INVALID", "REGRESSED", "UNCHANGED"]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Reflex: it is an evaluator, and an evaluator the orchestrator could overrule measures nothing.
# The whole value of this organ is that its verdict is not available to a wish.
ATANOR_TIER = "reflex"
