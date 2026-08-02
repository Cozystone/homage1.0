# -*- coding: utf-8 -*-
"""ATANOR fluency organ (F0) — delexicalization + copy mechanism + register lever.

The measured fluency wall (see memory: track-f-fluency-strategy, corpus-composition-is-the-
bottleneck) is NOT model size. Its two causes are (1) register complexity of the corpus and
(2) entity memorization. This package attacks both WITHOUT an LLM and WITHOUT free autoregressive
sampling — generation stays bone+flesh, hallucination-safe (BINDING doctrine).

  delex     — separate a grounded answer into a REGISTER SKELETON (function words / connectives /
              clause structure; zero entities) and typed SLOTS (entities, numbers, names). The
              copy mechanism fills slots ONLY from the grounded source, so entity memorization is
              removed as a failure mode: an entity absent from the grounding is copied-empty or the
              clause abstains — it can never be invented.
  register  — a small, DATA-driven set of register templates (simple / neutral / explanatory) that
              select clause complexity. Selected by context, default simple. Adding a register is a
              data edit, not a code branch.
  realizer  — the AFTER surface generator: delex -> pick register -> assemble -> copy-fill. Faithful
              and copy-safe by construction, built on realizer_struct.frame_realizer's morphology
              floor (a/an, plural agreement, demonym capitalization) so content correctness is
              identical to the BEFORE and only the register surface changes.
  fluency_v1— a 30-task grounded benchmark: faithfulness (must stay ~1.0), an HONEST fluency proxy
              (heuristic, not a human score), and slot-copy accuracy, reported BEFORE -> AFTER.
"""
from __future__ import annotations

from packages.fluency.delex import (
    ClausePlan,
    Grounding,
    Slot,
    Token,
    copy_fill,
    delexicalize,
)
from packages.fluency.register import (
    RegisterSpec,
    load_registers,
    select_register,
)
from packages.fluency.realizer import realize, realize_with_trace

__all__ = [
    "ClausePlan",
    "Grounding",
    "Slot",
    "Token",
    "copy_fill",
    "delexicalize",
    "RegisterSpec",
    "load_registers",
    "select_register",
    "realize",
    "realize_with_trace",
]
