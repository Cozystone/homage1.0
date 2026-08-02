# -*- coding: utf-8 -*-
"""operator_census — G1: which computations does ATANOR keep re-implementing?

Measured by SHAPE, never by name. Plan v6's central claim is that the generality gap is a
consolidation gap, and a keyword sweep cannot establish it -- this repository produced two keyword
artifacts in a single day. See ``census.recurring``.
"""
from packages.operator_census.census import (  # noqa: F401
    Occurrence, RecurringShape, duplication_report, find_shape_of, organ_duplication, recurring,
    scan, signature_of)

__all__ = ["Occurrence", "RecurringShape", "duplication_report", "find_shape_of",
           "organ_duplication", "recurring", "scan", "signature_of"]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Output-only: it reads source and reports shapes. It consolidates nothing and steers nothing.
ATANOR_TIER = "perception"
