#!/usr/bin/env python3
"""Honest answer-quality battery against the LIVE local demo (:8502).

Read-only: POSTs diverse real questions to /api/base-brain/answer and classifies the
result (grounded answer / honest abstain / identity). Surfaces where the engine actually
stands after this session's work + the next quality priorities. No changes made.
"""
from __future__ import annotations
import json
import urllib.request

URL = "http://127.0.0.1:8502/api/base-brain/answer"
ABSTAIN_MARK = "근거가 부족"

BATTERY = {
    "science": ["광합성이란?", "중력이란?", "DNA란?", "효소란?", "세포란?"],
    "tech": ["쿠버네티스가 뭐야?", "도커란?", "블록체인이란?", "GraphRAG란?", "인공지능이란?"],
    "people": ["퀴리란?", "아인슈타인이란?", "세종대왕이란?"],
    "entities": ["삼성전자란?", "방탄소년단란?", "엔비디아란?", "반도체란?"],
    "identity": ["너는 누구야?", "너 뭐 할 수 있어?"],
    "should_abstain": ["오늘 날씨 어때?", "비트코인 지금 가격은?", "인텔에 대해 알려줘"],
    "junk_query": ["원래란?", "오늘이란?"],
}


def ask(q: str) -> str:
    body = json.dumps({"query": q, "language": "ko"}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return str(json.loads(r.read().decode("utf-8")).get("answer") or "")
    except Exception as exc:
        return f"__ERROR__ {type(exc).__name__}"


def main() -> int:
    total = grounded = abstained = errored = 0
    print("=== ANSWER QUALITY BATTERY (live :8502) ===\n")
    for cat, qs in BATTERY.items():
        print(f"[{cat}]")
        for q in qs:
            a = ask(q)
            total += 1
            if a.startswith("__ERROR__"):
                tag, errored = "ERR ", errored + 1
            elif ABSTAIN_MARK in a:
                tag, abstained = "ABST", abstained + 1
            else:
                tag, grounded = "ANS ", grounded + 1
            print(f"  [{tag}] {q:22} {a[:100]}")
        print()
    print("=== SUMMARY ===")
    print(f"total={total} grounded={grounded} abstain={abstained} error={errored}")
    print("(judge by category: science/tech/people/entities SHOULD answer; "
          "should_abstain SHOULD abstain; junk_query graceful; identity should answer.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
