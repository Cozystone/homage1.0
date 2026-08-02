# -*- coding: utf-8 -*-
"""knowledge_acquisition — the autonomous knowledge-acquisition CLOSED LOOP (R2 / M4).

Fuses existing organs into one loop: a relational question that HONESTLY ABSTAINS (no graph edge)
triggers a web mine for the missing object, a >= 2-DISTINCT-DOMAIN consensus verification, a
no-retrain graph injection with provenance, and a re-answer that now grounds correctly. Every fact
that enters the graph passed the consensus gate (fabrication 0); an unverified fact is never
injected and the question stays abstained.

Reused organs (not re-implemented): base_brain.relational_lookup (abstain-detect + re-answer),
wild_web (safety floors + consensus doctrine + domain_of), knowledge_harvest.ingest (EXCLUDE_PAIRS
+ TripleStore write pattern), graph_scale.web_knowledge_drain (the live search/fetch lane). The one
NEW organ is the targeted relational OBJECT extractor (relation_extract).

Holds ZERO learned parameters — a DATA-ingestion loop (facts live in the graph with web-consensus
provenance, not in weights).
"""
from __future__ import annotations

from .consensus import ConsensusResult, ConsensusTally, canonical_object
from .evidence import EvidenceSource, FixtureEvidence, WebEvidence
from .inject import inject_fact
from .loop import AcquisitionResult, acquire, acquire_batch, graph_predicate
from .relation_extract import extract_from_documents, extract_relation_facts
from .web_answer import WebReadAnswer, answer_from_web, searxng_reachable

__all__ = [
    "acquire",
    "acquire_batch",
    "AcquisitionResult",
    "graph_predicate",
    "FixtureEvidence",
    "WebEvidence",
    "EvidenceSource",
    "ConsensusTally",
    "ConsensusResult",
    "canonical_object",
    "inject_fact",
    "extract_relation_facts",
    "extract_from_documents",
    "answer_from_web",
    "WebReadAnswer",
    "searxng_reachable",
]
