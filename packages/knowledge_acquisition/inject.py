# -*- coding: utf-8 -*-
"""Provenance-carrying graph injection for a consensus-verified relational fact.

This is the no-retrain WRITE step: a verified ``(subject, predicate, object)`` edge is appended
into the SAME kg_triples TripleStore the base_brain relational lane scans, carrying the CONSENSUS
provenance (the independent domains + one evidence url) in the store's source registry — so the
re-answer cites real grounding (``facts_with_sources``), not a generic label.

Why not ``knowledge_harvest.ingest.ingest_edges`` directly: that batch ingester hardcodes the
source to ``wikidata``/``curated`` (an unknown source silently degrades to "curated"), which would
MISLABEL a web-mined fact's provenance — a fabrication-adjacent honesty breach. So this is a thin,
single-fact writer that reuses the SAME store API (``intern_source`` + ``add`` + ``facts_about``
idempotency + single-writer sanity) and the SAME ``EXCLUDE_PAIRS`` test-locked guard, only with
honest per-edge web provenance. It never opens the shipped store implicitly — the caller passes an
explicit ``root`` (a scoped/ephemeral store for the sealed gate).

Constitution: nothing is injected unless the caller already verified >= 2-domain consensus; the
EXCLUDE_PAIRS guard keeps the two deliberately-ungrounded regression fixtures abstaining even if a
consensus is reached for them (their honest gap is a tested invariant, not a bug to close).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from packages.graph_scale.triple_store import TripleStore
# reuse the exact test-locked absence set the batch ingester uses (single source of truth)
from packages.knowledge_harvest.ingest import EXCLUDE_PAIRS


def _excluded(subject: str, predicate: str) -> bool:
    return (subject.strip().lower(), predicate.strip().lower()) in EXCLUDE_PAIRS


def inject_fact(root: Path | str, subject: str, predicate: str, obj: str,
                domains: list[str], urls: list[str], *,
                retrieved_at: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Append ONE consensus-verified edge into the kg_triples store at ``root`` with web
    provenance. Idempotent (skips a row already present). Returns an audit dict.

    ``domains`` / ``urls`` are the consensus attestation — recorded in the source registry as
    ``web-consensus: d1, d2 (retrieved YYYY-MM-DD)`` with the first evidence url as the pattern.
    """
    root = Path(root)
    retrieved_at = retrieved_at or time.strftime("%Y-%m-%d")
    subject, predicate, obj = subject.strip(), predicate.strip(), obj.strip()

    if not (subject and predicate and obj):
        return {"injected": False, "reason": "empty_field"}
    if _excluded(subject, predicate):
        return {"injected": False, "reason": "excluded_test_locked",
                "pair": (subject.lower(), predicate.lower())}
    if dry_run:
        return {"injected": False, "reason": "dry_run", "would_add": f"{subject} {predicate} {obj}"}

    s_path = root / "s.col"
    size_before = s_path.stat().st_size if s_path.exists() else 0

    store = TripleStore(root)
    # busy_timeout so a concurrent reader (engine holds a shared lock while answering) makes this
    # write WAIT rather than fail — columns are append-only so readers are safe by design.
    try:
        for _conn in getattr(store.terms, "_conns", []) or []:
            _conn.execute("PRAGMA busy_timeout=8000")
    except Exception:
        pass

    # idempotency: is this exact (predicate, object) already on this subject?
    already = False
    for variant in {subject, subject.lower(), subject.title()}:
        try:
            for (_s, p, o) in store.facts_about(variant, limit=200):
                if p == predicate and o == obj:
                    already = True
                    break
        except Exception:
            pass
        if already:
            break
    if already:
        return {"injected": False, "reason": "already_present",
                "fact": f"{subject} {predicate} {obj}"}

    src_name = f"web-consensus: {', '.join(domains)} (retrieved {retrieved_at})"
    src_url = urls[0] if urls else ""
    src_id = store.intern_source(src_name, src_url)

    added = store.add(subject, predicate, obj, source=src_id)
    store.flush()

    size_after = s_path.stat().st_size if s_path.exists() else 0
    delta_rows = (size_after - size_before) // 4
    return {
        "injected": bool(added),
        "reason": "added" if added else "write_gate_refused",   # e.g. English-only write gate
        "fact": f"{subject} {predicate} {obj}",
        "source": src_name,
        "source_url": src_url,
        "domains": domains,
        "single_writer_sanity": {
            "s_col_rows_before": size_before // 4, "s_col_rows_after": size_after // 4,
            "row_delta": delta_rows, "delta_equals_added": (delta_rows == int(bool(added))),
        },
    }
