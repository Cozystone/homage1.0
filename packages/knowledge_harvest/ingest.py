# -*- coding: utf-8 -*-
"""Write harvested relational edges to an isolated proposal fragment.

The base-brain relational lane scans only the operator-signed shipped graph.
Candidates produced here become visible only after immutable-batch assembly,
verification, and signed promotion.

Every appended row carries provenance via the store's source registry (``intern_source`` ->
``src.col``): a Wikidata edge cites Wikidata (retrieval date in the source name), a curated edge
cites the bundled CSV. ``facts_with_sources`` then surfaces that provenance to the answer layer.

Honesty guards:
  * NOTHING is fabricated — every edge came from Wikidata (verbatim) or the human-checked CSV.
  * A small EXCLUDE set keeps two edges DELIBERATELY ungrounded so the relational lane keeps
    honestly abstaining on them — they are the fixtures two existing regression tests use to prove
    "edge absent -> abstain, never head-noun define" (population of France, boiling point of water).
    Grounding them would silently regress those tests; the coverage boundary is honest and reported.
  * Idempotent: it diffs against the store (``facts_about``) before adding, so a re-run does not
    duplicate rows (the store's in-RAM dedup set is session-scoped and cannot see on-disk rows).
  * Single-writer sanity: it snapshots s.col before/after and reports whether the row delta equals
    the number it added (a mismatch would mean another process appended concurrently).

Append-only within the proposal fragment: existing rows are never touched.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from packages.graph_scale.triple_store import TripleStore  # noqa: E402
from packages.graph_scale.graph_paths import (  # noqa: E402
    KNOWLEDGE_HARVEST_PROPOSAL_FRAGMENT_ROOT,
)

DEFAULT_ROOT = KNOWLEDGE_HARVEST_PROPOSAL_FRAGMENT_ROOT

# (subject_lower, relation) pairs kept DELIBERATELY ungrounded — see module docstring. These are the
# exact fixtures of apps/api/tests/test_relational_lookup.py::test_other_relational_defects_are_not_
# headnoun_defines (population of France, boiling point of water). The relational lane MUST keep
# abstaining on them; grounding them is an intentional non-goal of this bounded harvest.
EXCLUDE_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("france", "population"),
    ("water", "boiling_point"),
    ("water", "boiling point"),
})


def _excluded(subject: str, relation: str) -> bool:
    return (subject.strip().lower(), relation.strip().lower()) in EXCLUDE_PAIRS


def ingest_edges(edges: Iterable[dict[str, str]], root: Path | str = DEFAULT_ROOT,
                 retrieved_at: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Append edges into the configured proposal fragment.

    Returns an audit dict (added / skipped / excluded counts, per-relation, single-writer sanity).
    ``dry_run=True`` computes what WOULD change without opening the store for write.
    """
    root = Path(root)
    retrieved_at = retrieved_at or time.strftime("%Y-%m-%d")
    edges = list(edges)

    kept: list[dict[str, str]] = []
    excluded = 0
    for e in edges:
        s, rel, o = str(e.get("subject", "")).strip(), str(e.get("relation", "")).strip(), str(e.get("object", "")).strip()
        if not (s and rel and o):
            continue
        if _excluded(s, rel):
            excluded += 1
            continue
        kept.append({"subject": s, "relation": rel, "object": o, "source": e.get("source", "curated")})

    s_path = root / "s.col"
    size_before = s_path.stat().st_size if s_path.exists() else 0

    if dry_run:
        return {"dry_run": True, "root": str(root), "input_edges": len(edges),
                "excluded_test_locked": excluded, "would_consider": len(kept),
                "s_col_rows_before": size_before // 4}

    store = TripleStore(root)                    # backend auto-detected from meta.json (sharded)

    # Give a concurrent proposal-fragment reader a bounded wait rather than
    # failing immediately on a term-shard lock.
    try:
        for _conn in getattr(store.terms, "_conns", []) or []:
            _conn.execute("PRAGMA busy_timeout=8000")
    except Exception:
        pass

    src_ids = {
        "wikidata": store.intern_source(
            f"wikidata (retrieved {retrieved_at})",
            "https://www.wikidata.org/wiki/Special:Search?search={s}"),
        "curated": store.intern_source(
            f"curated:relational-harvest ({retrieved_at})", ""),
    }

    # ---- idempotency: read every subject's existing (predicate, object) pairs BEFORE any write, so
    #      a re-run skips rows already on disk (the store's dedup set is session-scoped) ------------
    subjects = {e["subject"] for e in kept}
    existing: dict[str, set[tuple[str, str]]] = {}
    for subj in subjects:
        pairs: set[tuple[str, str]] = set()
        for variant in {subj, subj.lower(), subj.title()}:
            try:
                for (_s, p, o) in store.facts_about(variant, limit=400):
                    pairs.add((p, o))
            except Exception:
                pass
        existing[subj] = pairs

    added = skipped_present = skipped_gate = 0
    per_relation: dict[str, int] = {}
    per_source: dict[str, int] = {}
    samples: list[str] = []
    for e in kept:
        s, rel, o, src = e["subject"], e["relation"], e["object"], e["source"]
        if (rel, o) in existing.get(s, set()):
            skipped_present += 1
            continue
        if store.add(s, rel, o, source=src_ids.get(src, src_ids["curated"])):
            added += 1
            per_relation[rel] = per_relation.get(rel, 0) + 1
            per_source[src] = per_source.get(src, 0) + 1
            if len(samples) < 6:
                samples.append(f"{s} --{rel}--> {o}  [{src}]")
        else:
            skipped_gate += 1                    # in-session dup or English-only write gate refusal
    store.flush()

    size_after = s_path.stat().st_size if s_path.exists() else 0
    delta_rows = (size_after - size_before) // 4
    return {
        "root": str(root), "retrieved_at": retrieved_at,
        "input_edges": len(edges), "excluded_test_locked": excluded,
        "added": added, "skipped_already_present": skipped_present,
        "skipped_gate_or_session_dup": skipped_gate,
        "per_relation": per_relation, "per_source": per_source,
        "store_count_after": len(store),
        "single_writer_sanity": {
            "s_col_rows_before": size_before // 4, "s_col_rows_after": size_after // 4,
            "row_delta": delta_rows, "delta_equals_added": (delta_rows == added),
        },
        "samples": samples,
    }


def run(prefer_live: bool = True, dry_run: bool = False, root: Path | str = DEFAULT_ROOT,
        timeout: float = 45.0, inter_query_delay: float = 2.0) -> dict[str, Any]:
    """Harvest (Wikidata-first, curated fallback) then ingest. Returns {harvest, ingest}."""
    from .harvester import harvest

    edges, report = harvest(prefer_live=prefer_live, timeout=timeout,
                            inter_query_delay=inter_query_delay)
    audit = ingest_edges(edges, root=root, dry_run=dry_run)
    return {"harvest": report.as_dict(), "ingest": audit}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Harvest bounded relational facts into an unsealed proposal fragment."
    )
    ap.add_argument("--no-live", action="store_true", help="skip Wikidata; use the curated CSV only")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; no write")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--inter-delay", type=float, default=2.0,
                    help="seconds between the two WDQS queries (raise to ~65 when throttled to 1 req/min)")
    args = ap.parse_args(argv)
    out = run(prefer_live=not args.no_live, dry_run=args.dry_run, root=args.root,
              timeout=args.timeout, inter_query_delay=args.inter_delay)
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
