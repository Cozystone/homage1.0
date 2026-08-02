"""CGSR Stage 1: construction induction, dedupe, and Korean morphology.

This package is independent from the existing surface_brain runtime.  Stage 1
does not call external LLMs, does not write Local Brain memory, and does not
connect to RHFC cleanup memory yet.
"""

from .canonicalize import canonicalize, dedupe_constructions
from .induction import induce_constructions
from .korean_realizer import realize_simple_clause, select_eomi, select_euro_ro, select_josa
from .morphology import analyze, analyzer_status

__all__ = [
    "analyze",
    "analyzer_status",
    "canonicalize",
    "dedupe_constructions",
    "induce_constructions",
    "realize_simple_clause",
    "select_eomi",
    "select_josa",
]
