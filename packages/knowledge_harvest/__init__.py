# -*- coding: utf-8 -*-
"""knowledge_harvest — bounded relational-fact harvester + graph ingest (No-LLM, DATA only).

Owner-priority gap (W-B increment, 2026-07-22): the base_brain relational lane
(``packages/base_brain/relational_lookup.py``) parses "the X of Y" questions and RESOLVES them by
scanning the curated graph (``data/graph_scale/kg_triples``) for an edge whose label matches the
asked relation. Measured: it worked, but HONESTLY ABSTAINED on "what is the capital of France?"
because the graph held rich ``defined_as`` prose ("… Capital and largest city: Paris") yet NO
structured ``capital`` edge. A whole class of well-known facts fell to honest-abstention.

The fix is STRUCTURAL + GRAPH, not a bolt-on lookup table (doctrine two-hard-rules: knowledge
lives in the GRAPH; every fact carries a source certificate; unknown -> still abstain, never
fabricate). This package pulls high-frequency relations (capital, population, currency,
official_language, located_in, author, inventor) for a BOUNDED entity set (countries + major
literary works/inventions) from a STRUCTURED source — Wikidata SPARQL preferred, a bundled
curated CSV as the offline fallback — and writes sourced (subject, relation, object) candidates
to an isolated proposal fragment. The relational lane sees them only after immutable-batch
assembly, independent verification, and operator-signed promotion into the shipped graph.

It holds ZERO learned parameters — it is a data-ingestion pipeline (registered in the neuro
ledger as a 0-param DATA organ, ``fact_source=False``: accepted facts live in the graph with
Wikidata/curated provenance, not in this code).
"""
from __future__ import annotations

from .harvester import (
    RELATION_PIDS,
    HarvestReport,
    harvest,
    load_curated,
)

__all__ = ["RELATION_PIDS", "HarvestReport", "harvest", "load_curated"]
