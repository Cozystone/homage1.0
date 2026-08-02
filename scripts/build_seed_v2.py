#!/usr/bin/env python3
"""Build a fresh multi-source candidate store in STAGING (not live, not under
candidate_runs/) so the read-model cannot auto-cut-over. Operator gates the cutover.

clean_seed_v2 = current clean_seed_v1 (clean evidence base, 100% IS_A) + REAL news
(SearXNG, verbatim snippets, durable contract). Validates the durable invariants:
idempotent (re-run adds 0), clean (0% _OF), per-source provenance (each URL removable).

Read-only w.r.t. the live store (it is only COPIED). All writes go to staging.
"""

from __future__ import annotations

import collections
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "api"), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import durable_ingest as di          # noqa: E402
import searxng_adapter as sx         # noqa: E402

LIVE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "clean_seed_v1"
STAGING = REPO_ROOT / "data" / "cloud_brain" / "staging" / "clean_seed_v2"
TOPICS = [
    "인공지능 최신 뉴스", "반도체 시장 뉴스", "삼성전자 뉴스", "SK하이닉스 뉴스",
    "OpenAI news", "AI chip news", "전기차 배터리 뉴스", "우주 발사 뉴스",
    "기후 변화 뉴스", "양자컴퓨터 뉴스", "로봇 산업 뉴스", "바이오 신약 뉴스",
]


def _rel_types(store: Path) -> dict:
    types = collections.Counter()
    f = store / "relations.jsonl"
    if f.exists():
        for line in f.open(encoding="utf-8"):
            try:
                types[json.loads(line).get("relation")] += 1
            except Exception:
                pass
    return dict(types)


def main() -> int:
    if not LIVE.exists():
        print(f"[V2] live base missing: {LIVE}")
        return 1
    print(f"[V2] fresh copy of clean base -> {STAGING}")
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(LIVE, STAGING)

    base_rel = _rel_types(STAGING)
    print(f"[V2] base relations: {sum(base_rel.values())} types={base_rel}")

    print(f"[V2] collecting real news via SearXNG ({len(TOPICS)} topics)...")
    rows = sx.collect(TOPICS, count=6)
    distinct = len({r[1] for r in rows})
    print(f"[V2] {len(rows)} snippet sentences from {distinct} distinct article URLs")
    if not rows:
        print("[V2] no news (SearXNG :8888 down?) — staging holds clean base only.")
        rows = []

    if rows:
        print("[V2] RUN 1: durable ingest of news into staging...")
        r1 = di.ingest(STAGING, rows)
        print(f"   new={r1['new_facts']} dup={r1['dup_skipped']} rejected={r1['rejected']}")
        print("[V2] RUN 2: idempotency...")
        r2 = di.ingest(STAGING, rows)
        print(f"   idempotent(run2 new==0): {r2['new_facts'] == 0}")

    after = _rel_types(STAGING)
    total = sum(after.values())
    of = sum(v for k, v in after.items() if str(k).endswith("_OF"))
    print(f"\n[V2] staging AFTER: relations={total} types={after}")
    print(f"[V2] INVARIANT clean: _OF={of} ({100*of/max(total,1):.1f}%)")

    src = collections.Counter()
    mf = STAGING / di.SOURCES_MANIFEST
    if mf.exists():
        for line in mf.open(encoding="utf-8"):
            try:
                e = json.loads(line)
                if e.get("new") and "http" in str(e.get("source_id", "")):
                    src[e["source_id"]] += 1
            except Exception:
                pass
    print(f"[V2] INVARIANT per-source provenance: {len(src)} distinct news URLs (each removable)")
    for url, n in src.most_common(5):
        print(f"   {n:3d}  {url[:60]}")
    print(f"\n[V2] staged at: {STAGING}  (NOT live — read-model ignores staging/)")
    print("[V2] cutover = move into candidate_runs/ (operator-gated, separate step).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
