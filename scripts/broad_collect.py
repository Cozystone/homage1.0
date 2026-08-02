#!/usr/bin/env python3
"""Broad SearXNG collector — pull everything SearXNG can reach across many topics.

For a wide, diverse topic list it takes ALL SearXNG results and ingests their snippet
sentences (verbatim, No-LLM, reference-only) into the durable store, tagging each row by
URL domain: known community domains -> source_type="community_social" (LOW trust tier);
everything else -> "public_web_feed". The faithful verify->decompose gate decides what
actually becomes graph facts (fragmentary text is refused — that is the design).

Idempotent + per-source provenance (durable contract). Writes only to --out (staging).
"""

from __future__ import annotations

import argparse
import collections
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
from community_adapter import COMMUNITY_DOMAINS          # noqa: E402

_SENT = re.compile(r"(?<=[.!?。])\s+")

TOPICS = [
    # tech / AI / compute
    "인공지능", "머신러닝", "딥러닝", "대형언어모델", "반도체", "GPU", "양자컴퓨터",
    "클라우드 컴퓨팅", "사이버보안", "로보틱스", "자율주행", "5G 6G 통신",
    "artificial intelligence", "semiconductor industry", "quantum computing", "robotics",
    # science / space / nature
    "우주 탐사", "천문학", "물리학", "화학", "생물학", "유전공학", "기후 변화", "재생에너지",
    "space exploration", "astronomy", "genetics", "renewable energy", "climate change",
    # economy / business / finance
    "세계 경제", "주식 시장", "암호화폐", "전기차 시장", "배터리 산업", "원자재 가격",
    "global economy", "stock market", "cryptocurrency", "electric vehicles",
    # medicine / bio
    "신약 개발", "백신", "암 치료", "면역학", "공중보건", "vaccine", "cancer research",
    # world / society / culture / history
    "국제 정세", "지정학", "역사", "지리", "철학", "심리학", "교육", "언어학",
    "world history", "geopolitics", "philosophy", "linguistics",
    # everyday / culture
    "영화", "음악", "스포츠", "건축", "음식 문화", "여행",
]


def _sentences(snippet: str) -> list[str]:
    return [s.strip() for s in _SENT.split(snippet or "") if 15 < len(s.strip()) < 240]


def _source_type(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return "community_social" if any(d in host for d in COMMUNITY_DOMAINS) else "public_web_feed"


def collect(topics: list[str], count: int) -> list[tuple]:
    rows: list[tuple] = []
    seen: set[tuple] = set()
    for i, q in enumerate(topics, 1):
        try:
            results = searxng_search(q, count=count)
        except Exception:
            continue
        for r in results:
            url = str(r.get("url") or "").strip()
            if not url:
                continue
            stype = _source_type(url)
            for sent in _sentences(str(r.get("snippet") or "")):
                key = (sent, url)
                if key in seen:
                    continue
                seen.add(key)
                rows.append((sent, url, "reference_only", stype))
        if i % 10 == 0:
            print(f"   ...{i}/{len(topics)} topics, {len(rows)} rows so far")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Broad SearXNG collector (durable, domain-tagged)")
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "data" / "cloud_brain" / "staging" / "clean_seed_v2")
    ap.add_argument("--count", type=int, default=10)
    args = ap.parse_args()
    if not args.out.exists():
        print(f"[BROAD] target missing: {args.out}")
        return 1

    print(f"[BROAD] collecting across {len(TOPICS)} diverse topics via SearXNG (count={args.count})...")
    rows = collect(TOPICS, args.count)
    doms = collections.Counter((urlparse(r[1]).hostname or "?") for r in rows)
    styp = collections.Counter(r[3] for r in rows)
    print(f"[BROAD] {len(rows)} snippet sentences | by source_type={dict(styp)}")
    print(f"[BROAD] top domains: {dict(doms.most_common(10))}")
    if not rows:
        print("[BROAD] nothing returned (SearXNG :8888 down?).")
        return 2

    print("[BROAD] durable ingest into staging...")
    r1 = di.ingest(args.out, rows)
    print(f"   new={r1['new_facts']} dup={r1['dup_skipped']} rejected={r1['rejected']}")
    r2 = di.ingest(args.out, rows)
    print(f"[BROAD] idempotent (run2 new==0): {r2['new_facts'] == 0}")
    print(f"[BROAD] distinct sources now in manifest provenance (removable units).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
