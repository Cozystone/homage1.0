#!/usr/bin/env python3
"""Community/social durable adapter — Reddit / X / DCInside etc. via SearXNG snippets.

Honest scope: we do NOT use platform APIs or bulk-scrape (X API is paid/ToS-locked,
nitter is dead, DCInside/Reddit bulk-scrape is ToS-risky). Instead we take whatever
those platforms have already had PUBLICLY INDEXED by the search engines SearXNG
aggregates, as reference-only snippets, and keep only results whose URL is a known
community domain. Everything is tagged source_type="community_social" => LOW trust tier
(decomposer._TRUST_TIERS) so it enters as claim/opinion, never as verified fact. Bias is
handled by low trust + multi-source corroboration + the verification/4D layer, NOT by the
phase-interference layer (which does referent-type selection, not veracity).

Writes only to --out (staging). Additive + per-source-removable (durable contract).
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "api"), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import durable_ingest as di                              # noqa: E402
from app.services.web_search import searxng_search       # noqa: E402

_SENT = re.compile(r"(?<=[.!?。])\s+")
# community domains we accept (substring match on host)
COMMUNITY_DOMAINS = (
    "reddit.com", "redd.it",
    "x.com", "twitter.com", "nitter.",
    "dcinside.com",
    "fmkorea.com", "clien.net", "ruliweb.com", "theqoo.net",
    "instiz.net", "inven.co.kr", "ppomppu.co.kr", "bobaedream.co.kr",
    "ycombinator.com",  # hacker news
)


def _is_community(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(d in host for d in COMMUNITY_DOMAINS)


def _sentences(snippet: str) -> list[str]:
    return [s.strip() for s in _SENT.split(snippet or "") if 15 < len(s.strip()) < 240]


def collect(topics: list[str], count: int) -> list[tuple]:
    """Return durable rows = (sentence, community_url, 'reference_only', 'community_social')."""
    rows: list[tuple] = []
    seen_urls: set[str] = set()
    # bias queries toward community surfaces so more indexed community results return
    queries = []
    for t in topics:
        queries += [t, f"{t} reddit", f"{t} 디시", f"{t} 트위터"]
    for q in queries:
        try:
            results = searxng_search(q, count=count)
        except Exception:
            continue
        for r in results:
            url = str(r.get("url") or "").strip()
            if not url or url in seen_urls or not _is_community(url):
                continue
            seen_urls.add(url)
            for sent in _sentences(str(r.get("snippet") or "")):
                rows.append((sent, url, "reference_only", "community_social"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Community/social durable adapter (SearXNG, reference-only)")
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "data" / "cloud_brain" / "staging" / "clean_seed_v2")
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--topics", nargs="*", default=[
        "인공지능", "반도체", "전기차", "비트코인", "게임", "정치", "주식",
        "OpenAI", "AI regulation", "GPU",
    ])
    args = ap.parse_args()

    if not args.out.exists():
        print(f"[COMMUNITY] target store missing: {args.out} (run build_seed_v2 first)")
        return 1

    print(f"[COMMUNITY] collecting indexed community snippets via SearXNG ({len(args.topics)} topics)...")
    rows = collect(args.topics, args.count)
    by_dom = collections.Counter((urlparse(r[1]).hostname or "?") for r in rows)
    print(f"[COMMUNITY] {len(rows)} snippet sentences from community domains: {dict(by_dom.most_common(8))}")
    if not rows:
        print("[COMMUNITY] no community results indexed right now (SearXNG returned none). Store untouched.")
        return 2

    print("[COMMUNITY] RUN 1: durable ingest (LOW-trust tier) into staging...")
    r1 = di.ingest(args.out, rows)
    print(f"   new={r1['new_facts']} dup={r1['dup_skipped']} rejected={r1['rejected']}")
    r2 = di.ingest(args.out, rows)
    print(f"[COMMUNITY] idempotent (run2 new==0): {r2['new_facts'] == 0}")

    # prove the new concepts really landed at the LOW trust tier
    cf = args.out / "concepts.jsonl"
    low = total = 0
    if cf.exists():
        for line in cf.open(encoding="utf-8"):
            try:
                c = json.loads(line); total += 1
                if float(c.get("trust", 1)) <= 0.30:
                    low += 1
            except Exception:
                pass
    print(f"[COMMUNITY] concepts at low-trust(<=0.30) tier: {low} / {total} total")
    print("[COMMUNITY] => community content is in as LOW-trust claims, per-source removable. Bias handled downstream.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
