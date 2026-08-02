#!/usr/bin/env python3
"""SearXNG durable adapter — live news / diverse-web source for the seed pipeline.

SearXNG (self-hosted metasearch, already running at :8888) is the legally-safe way
to pull DIVERSE / NEWS / current content: it returns snippets (reference-only, not
full articles) from many engines. This adapter:
  - queries SearXNG for topics,
  - extracts snippet sentences (verbatim — No-LLM, never paraphrased),
  - feeds them into the durable ingest with per-RESULT-URL provenance
    (source_id = the real article URL, license = reference_only,
     source_type = public_web_feed) so idempotency + per-source removal hold.

Writes only to --out (live store untouched).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "api"), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import durable_ingest as di                              # noqa: E402
from app.services.web_search import searxng_search       # noqa: E402

_SENT = re.compile(r"(?<=[.!?。])\s+")


def _sentences(snippet: str) -> list[str]:
    return [s.strip() for s in _SENT.split(snippet or "") if 15 < len(s.strip()) < 240]


def collect(topics: list[str], count: int) -> list[tuple]:
    """Return durable rows = (sentence, source_url, 'reference_only', 'public_web_feed')."""
    rows: list[tuple] = []
    for q in topics:
        for r in searxng_search(q, count=count):
            url = str(r.get("url") or "").strip()
            if not url:
                continue
            for sent in _sentences(str(r.get("snippet") or "")):
                rows.append((sent, url, "reference_only", "public_web_feed"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="SearXNG durable adapter")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--topics", nargs="*", default=["인공지능 최신 뉴스", "OpenAI news", "반도체 시장 뉴스"])
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    if args.fresh and args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    live = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "wikipedia_grounded_live"
    for fn in ("schema.json", "manifest.json"):
        if (live / fn).exists():
            shutil.copy(live / fn, args.out / fn)

    rows = collect(args.topics, args.count)
    distinct_urls = len({r[1] for r in rows})
    print(f"[SEARXNG] topics={len(args.topics)} -> sentences={len(rows)} from {distinct_urls} distinct source URLs")

    print("=== RUN 1 (ingest news via durable contract) ===")
    r1 = di.ingest(args.out, rows)
    print(r1)
    print("=== RUN 2 (same news -> idempotent) ===")
    r2 = di.ingest(args.out, rows)
    print(r2)
    print(f"\nIDEMPOTENT (run2 new_facts==0): {r2['new_facts'] == 0}")

    # per-source provenance: show top source URLs by fact count
    import collections
    src_counts = collections.Counter()
    for line in (args.out / di.SOURCES_MANIFEST).open(encoding="utf-8"):
        try:
            e = json.loads(line)
            if e.get("new"):
                src_counts[e["source_id"]] += 1
        except Exception:
            pass
    print("PER-SOURCE provenance (removable units):")
    for url, n in src_counts.most_common(5):
        print(f"  {n:3d}  {url[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
