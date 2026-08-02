# -*- coding: utf-8 -*-
"""self_evolution — the BROAD self-evolution orchestrator.

Owner intent (2026-07-22): ATANOR should always hold the POTENTIAL to self-improve, in EVERY area it
feels deficient. This package makes that potential honest and bounded. It does NOT rewrite the brain;
it (1) DETECTS weakness by reading real scorecards (deficiency sensus), (2) knows the real
self-improvement loops as DATA (evolution registry), (3) ORCHESTRATES a ranked plan that either
dispatches a verifier-backed loop or flags an operator proposal, and (4) reports the HONEST CEILING —
autonomous-now vs needs-a-verifier vs operator-gated-forever.

BINDING doctrine: self-evolution compounds only where a MEASUREMENT gate, a GENERATOR, and a VERIFIER
all exist. No verifier -> no autonomous promotion. Constitution files and tests are immutable by
self-mod (wireheading guard). Architecture rewrites are operator-gated. Nothing unverified is promoted;
every action is journalled.
"""
from __future__ import annotations

from .deficiency_sensus import (
    DomainWeakness,
    build_weakness_map,
    refresh_computed_scorecards,
    sense_domain,
)
from .evolution_registry import EvolutionLoop, evolvability_probes, load_registry
from .orchestrator import (
    evolvability,
    headroom,
    impact,
    plan_next_evolution,
    rank_score,
    render_report,
)
from .wireheading_guard import GuardVerdict, immutable_hits, is_wireheading, review
from . import ceiling, journal, ledger_contribution

__all__ = [
    "DomainWeakness",
    "build_weakness_map",
    "sense_domain",
    "refresh_computed_scorecards",
    "EvolutionLoop",
    "load_registry",
    "evolvability_probes",
    "plan_next_evolution",
    "render_report",
    "headroom",
    "impact",
    "evolvability",
    "rank_score",
    "review",
    "immutable_hits",
    "is_wireheading",
    "GuardVerdict",
    "ceiling",
    "journal",
    "ledger_contribution",
]
