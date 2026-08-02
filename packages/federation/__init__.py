# -*- coding: utf-8 -*-
"""federation — FEDERATED CAPABILITY EVOLUTION (owner design 2026-07-22).

Many ATANOR instances self-evolve in DIFFERENT directions. A dev-PC orchestrator monitors them
privately, gathers their VERIFIED-good capabilities, integrates, and redistributes — but SHARES the
ABILITY while keeping each node's PERSONHOOD UNIQUE.

CONSTITUTION (BINDING):
  0. PUBLIC SCOPE (amendment, owner-authorised 2026-07-31). Crawled facts about the PUBLIC world may
     travel, on one condition: every fact carries the source DOMAINS that assert it, and a receiving
     node counts those domains, never the peer that sent them. Five peers citing one site is one
     source, so a ring cannot manufacture consensus. Layer 3 below is untouched -- personal /
     lived-record / felt-state still NEVER merges -- and the capability lane still hard-rejects
     `facts` and `triples`. See world_facts.py; the guarantees are pinned in
     tests/test_world_facts_public_scope.py rather than asserted here.
  1. Federate STRUCTURE, not DATA — a node contributes a verified SCHEMA / router-diff / organ-param
     (the shape of an ability), never its corpus / lived-record / personal graph.
  2. SEALED JUDGE — a contribution is promoted to the universal layer only if it REPRODUCES on the
     orchestrator's developer-blind holdout with no regression (MSH-style), never on self-report.
  3. TWO-LAYER SPLIT — Universal (promoted abilities = everyone's floor) vs Personal (each node's
     subjectivity / felt-state / lived-record / local grounding), which NEVER merges.
  4. PRIVACY — a contribution carrying PII / entities is rejected (reuses wild_web's gate).
  5. ROLLBACKABLE SIGNED GENERATIONS — the integrated build ships as a signed generation; a regression
     rolls back instantly.

Honest scope: this is a SINGLE-PROCESS prototype (nodes, orchestrator, and holdout run in one Python
process). It proves the doctrine mechanics; it is not yet real networked federation, and the
generation "signature" is a local HMAC integrity seal rather than per-node asymmetric signatures.
"""
from __future__ import annotations

from .contribution import (
    CAPABILITY_KINDS,
    Contribution,
    SanitizeResult,
    sanitize,
)
from .judge import Verdict, evaluate, score_on_suite, sealed_suites
from .orchestrator import (
    ContributionReview,
    FederationStore,
    Orchestrator,
    PersonalLayerWriteError,
    adopt,
)
from . import ledger_contribution

__all__ = [
    "Contribution",
    "SanitizeResult",
    "sanitize",
    "CAPABILITY_KINDS",
    "Verdict",
    "evaluate",
    "score_on_suite",
    "sealed_suites",
    "Orchestrator",
    "FederationStore",
    "ContributionReview",
    "PersonalLayerWriteError",
    "adopt",
    "ledger_contribution",
]
