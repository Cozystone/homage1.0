# -*- coding: utf-8 -*-
"""Neuro Ledger — the registry + budget audit for every LEARNED component in ATANOR.

Owner fear (2026-07-22): "neuro growth tipping into LLM / the model getting heavy". This package is
the machinery that enforces the architectural line. It keeps an honest registry of every learned
organ (its code, its persisted weights, the symbolic gate it sits inside, and — invariant — that it
is NOT a fact source), measures each organ's real parameter count, and audits the footprint against a
hard budget so the No-LLM brain cannot silently grow into an LLM.
"""
from .ledger import (
    SINGLE_ORGAN_MAX,
    TOTAL_MAX,
    Organ,
    load_ledger,
    measure_all,
    measure_params,
    repo_root,
)

__all__ = [
    "SINGLE_ORGAN_MAX",
    "TOTAL_MAX",
    "Organ",
    "load_ledger",
    "measure_all",
    "measure_params",
    "repo_root",
]
