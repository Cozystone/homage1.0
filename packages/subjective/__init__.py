# -*- coding: utf-8 -*-
"""Subjective — the FELT judgment organ (owner 2026-07-22: feeling is the root of subjective value).

felt_judgment weights groundable merit by ATANOR's CURRENT felt state, so the same options are
judged differently under different internal states — agent-relative judgment, measured not asserted.

NO-QUALIA HONESTY LINE (binding): nothing here feels like anything. "Feeling" means a load-bearing
internal signal (hormone levels, per-concept somatic traces, stakes vitals) that SHAPES evaluation;
"subjective" means agent-relative and felt-state-dependent. The felt_trace is the honest ground —
it cites the real state that tipped a choice and never invents a reason.
"""
from .felt_judgment import (
    FeltState,
    felt_judgment,
    read_live_felt_state,
)

__all__ = ["FeltState", "felt_judgment", "read_live_felt_state"]
