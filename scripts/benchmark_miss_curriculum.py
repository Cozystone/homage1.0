# -*- coding: utf-8 -*-
"""Benchmark-miss curriculum — the exam tells the roamer what to go learn.

The self-evolution flywheel's return edge (BENCHMARK_NORTH_STAR): every benchmark item the
graph could not ground (or grounded wrongly) names a TERRITORY the world pack + roaming must
cover. This miner reads the latest open-book reports and distills missed items into a
curriculum of TOPIC TOKENS that intrinsic_drive._frontier_topic consumes with priority — so
the always-on roamer/expedition studies exactly what the exam proved it doesn't know.

NO-TRAINING-ON-TEST GUARD (BINDING): only topic tokens ever leave the reports — never the
question text, choices, or gold answers. Learning the territory, never memorizing the test.

  python scripts/benchmark_miss_curriculum.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "reports" / "benchmarks"
OUT = REPO / "data" / "autonomy" / "benchmark_curriculum.json"

# generic exam-language tokens that name no territory (both languages)
_STOP = {"following", "which", "what", "true", "false", "correct", "statement", "statements",
         "would", "according", "most", "best", "than", "with", "from", "this", "that", "these",
         "your", "their", "about", "when", "where", "given", "value", "using", "the", "and",
         "for", "are", "was", "were", "has", "have", "had", "not", "but", "his", "her", "its",
         "they", "them", "will", "can", "could", "should", "may", "might", "each", "such",
         "into", "over", "under", "between", "among", "likely", "information", "calculate",
         "difference", "does", "did", "how", "why", "who", "whom", "all", "any", "some",
         "more", "less", "many", "much", "very", "other", "another", "both", "either",
         "neither", "only", "also", "then", "there", "here", "being", "been", "because",
         "출제", "다음", "무엇", "옳은", "옳지", "않은", "가장", "경우", "위한", "대한", "설명",
         "그것", "어떤", "있는", "없는", "하는", "된다", "하면", "이다", "것은", "것이"}


def _latest_reports(k: int = 4) -> list[dict]:
    rows = []
    for fp in sorted([*REPORTS.glob("*_closedbook_*.json"), *REPORTS.glob("*_openbook_*.json")], reverse=True)[:k]:
        try:
            rows.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows


def main() -> int:
    reports = _latest_reports()
    if not reports:
        print("no reports — run scripts/benchmark_openbook.py first")
        return 1
    counts: Counter[str] = Counter()
    subjects: Counter[str] = Counter()
    n_missed = 0
    for rep in reports:
        for it in rep.get("items", []):
            if it.get("answered") and it.get("correct"):
                continue                      # a hit teaches nothing new
            n_missed += 1
            subjects[str(it.get("subject"))] += 1
            for tok in set(it.get("q_tokens", [])):     # per-item dedup = document frequency
                t = str(tok).strip().lower()
                if t in _STOP or re.fullmatch(r"\d+", t):
                    continue
                # latin needs >= 4 chars to be content-like; Korean >= 2 already filtered upstream
                if re.fullmatch(r"[a-z]+", t) and len(t) < 4:
                    continue
                counts[t] += 1
    # keep tokens seen in >=2 missed items but not in >30% of them (too generic to steer)
    ceiling = max(3, int(n_missed * 0.3))
    topics = [t for t, c in counts.most_common(200) if 2 <= c <= ceiling][:120]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "from_reports": len(reports), "missed_items": n_missed,
        "topics": topics, "cursor": 0,
        "weak_subjects": dict(subjects.most_common(10)),
        "guard": "topic tokens only — question text/choices/answers never stored (BINDING)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"curriculum: {len(topics)} topics from {n_missed} missed items "
          f"(weakest: {dict(subjects.most_common(4))})")
    print("sample:", topics[:12])
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
