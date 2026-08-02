# -*- coding: utf-8 -*-
"""loop_schema — D1: what a loop IS, derived from loops that work.

A loop is four slots: step, progress measure, termination, stall detection. The step belongs to the
domain; the other three are the arithmetic of knowing whether the work is getting anywhere, and that
arithmetic is small pure functions over numbers -- which is what makes a loop an AUTHORING TARGET
rather than something only a person can write.

Read from behaviour, never from attribute names. See ``schema.read_schema``.
"""
from packages.loop_schema.schema import (  # noqa: F401
    Conformance, LoopSchema, conforms, read_schema)

__all__ = ["Conformance", "LoopSchema", "conforms", "read_schema"]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Output-only: it reads traces another organ produced and reports a schema. It steers nothing and
# holds no state the orchestrator could bend.
ATANOR_TIER = "perception"
