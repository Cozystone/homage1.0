#!/usr/bin/env python3
"""Inject REAL news sentences into the LIVE clean foundation store, durably.

Makes the live graph genuinely multi-source (evidence + real news) per the operator's
standing instruction ("don't learn from wiki only"). Uses the proven SearXNG adapter +
durable contract: idempotent (re-run adds 0), per-source provenance (each article URL is
a removable unit), faithful (verbatim snippet sentences, No-LLM). Additive & reversible.

Run with the continuous worker STOPPED (avoid write race on the same VerifiedStore).
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "api"), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import durable_ingest as di          # noqa: E402
import searxng_adapter as sx         # noqa: E402

LIVE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "clean_seed_v1"
TOPICS = [
    "인공지능 최신 뉴스", "반도체 시장 뉴스", "삼성전자 뉴스", "SK하이닉스 뉴스",
    "OpenAI news", "AI chip news", "전기차 배터리 뉴스", "우주 발사 뉴스",
    "기후 변화 뉴스", "양자컴퓨터 뉴스",
]


def _rel_types(store: Path) -> dict:
    rel = store / "relations.jsonl"
    types = collections.Counter()
    for line in rel.open(encoding="utf-8"):
        try:
            types[json.loads(line).get("relation")] += 1
        except Exception:
            pass
    return dict(types)


def main() -> int:
    if not LIVE.exists():
        print(f"[NEWS] live store missing: {LIVE}")
        return 1
    before_rel = _rel_types(LIVE)
    print(f"[NEWS] live store BEFORE: relations={sum(before_rel.values())} types={before_rel}")

    print(f"[NEWS] collecting real news snippets via SearXNG ({len(TOPICS)} topics)...")
    rows = sx.collect(TOPICS, count=6)
    distinct = len({r[1] for r in rows})
    print(f"[NEWS] collected {len(rows)} snippet sentences from {distinct} distinct article URLs")
    if not rows:
        print("[NEWS] no rows (SearXNG :8888 down?) — aborting, live store untouched.")
        return 2

    print("[NEWS] RUN 1: durable ingest into LIVE store...")
    r1 = di.ingest(LIVE, rows)
    print(f"   {r1['new_facts']} new facts | {r1['dup_skipped']} dup | {r1['rejected']} rejected")
    print("[NEWS] RUN 2: same rows (idempotency check)...")
    r2 = di.ingest(LIVE, rows)
    print(f"   idempotent (run2 new==0): {r2['new_facts'] == 0}  (run2 new={r2['new_facts']})")

    after_rel = _rel_types(LIVE)
    of = sum(v for k, v in after_rel.items() if str(k).endswith("_OF"))
    total = sum(after_rel.values())
    print(f"\n[NEWS] live store AFTER: relations={total} types={after_rel}")
    print(f"[NEWS] cleanliness preserved: _OF noise = {of} ({100*of/max(total,1):.1f}%)")

    # per-source provenance (removable units) from this run
    src = collections.Counter()
    for line in (LIVE / di.SOURCES_MANIFEST).open(encoding="utf-8"):
        try:
            e = json.loads(line)
            if e.get("new") and "http" in str(e.get("source_id", "")):
                src[e["source_id"]] += 1
        except Exception:
            pass
    print("[NEWS] per-source provenance (each removable by filter-rebuild):")
    for url, n in src.most_common(6):
        print(f"   {n:3d}  {url[:64]}")
    print("[NEWS] => LIVE graph is now multi-source (evidence + real news), durably & reversibly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
