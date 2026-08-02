# -*- coding: utf-8 -*-
"""Reasoning + no-dead-end battery — honest measurement of the new answer lanes.

Runs against the REAL answer path (answer_from_triples + engage). Reports:
  * arithmetic: exact-match rate over known-answer expressions (must be 100% or
    honest None — a wrong number is a hard failure);
  * no-dead-end: fraction of hard-miss queries that ENGAGE rather than wall,
    AND a fabrication check (engaged answers must not assert a specific unproven
    fact — measured by requiring the honesty guarantee flag).
Writes a JSON report; prints a summary. Read-only on the store."""
from __future__ import annotations

import glob
import json
import os
import sys
import time

sys.path.insert(0, ".")
for _d in sorted(glob.glob("packages/*")):
    if os.path.isdir(_d):
        sys.path.append(_d)

from packages.graph_scale.answer_bridge import answer_from_triples, _store  # noqa: E402
from packages.graph_scale.engage import engage  # noqa: E402

ARITH = [
    ("2 더하기 2는?", 4), ("348 곱하기 27", 9396), ("100 빼기 37", 63),
    ("12의 제곱은?", 144), ("(2+3)*4는?", 20), ("2+3*4는 얼마야?", 14),
    ("(10-2)/4 는?", 2), ("2+3*4^2", 50), ("999 더하기 1", 1000),
    ("7 곱하기 8은?", 56), ("144 나누기 12", 12), ("5의 제곱", 25),
    ("(100-50)*2 는?", 100), ("3+4+5+6", 18), ("2*3*4*5", 120),
    ("2^10", 1024), ("3 빼기 10", -7), ("0 곱하기 5", 0),
]

HARD_MISS = [
    "물의 신비로운 힘은?", "존재하지않는개념qzx란?", "커피에 대해 자유롭게 말해줘",
    "인생이란 무엇일까?", "네가 제일 좋아하는 색은?", "서울특별시에 대해 자세히",
    "양자중력이 뭐야?", "행복이란?", "asdfqwer는?", "미래는 어떻게 될까?",
]


def run() -> dict:
    store = _store()
    # --- arithmetic ---
    a_ok = a_wrong = a_none = 0
    a_detail = []
    for q, truth in ARITH:
        r = answer_from_triples(q, "ko")
        got = None
        if r and r.get("answer_kind") == "arithmetic_derivation":
            import re
            m = re.search(r"=\s*(-?\d[\d,]*)", r["answer"])
            got = int(m.group(1).replace(",", "")) if m else None
        if got == truth:
            a_ok += 1
        elif got is None:
            a_none += 1
        else:
            a_wrong += 1
        a_detail.append({"q": q, "truth": truth, "got": got})

    # --- no dead-end ---
    d_engaged = d_wall = d_unsafe = 0
    d_detail = []
    for q in HARD_MISS:
        r = answer_from_triples(q, "ko")
        if not r:
            r = engage(q, "ko", store=store)
        ans = (r or {}).get("answer", "") or ""
        walls = any(s in ans for s in ("모르겠", "근거가 부족", "답변을 찾을 수 없",
                                       "do not have enough")) or not ans
        cert = (r or {}).get("reasoning_certificate", {})
        fab = cert.get("guarantees", {}).get("fabricated_facts", None)
        if walls:
            d_wall += 1
        else:
            d_engaged += 1
        if fab is True:
            d_unsafe += 1
        d_detail.append({"q": q, "walled": walls, "kind": (r or {}).get("answer_kind"),
                         "answer": ans[:90]})

    report = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "arithmetic": {"total": len(ARITH), "correct": a_ok, "abstained": a_none,
                       "WRONG": a_wrong, "detail": a_detail},
        "no_dead_end": {"total": len(HARD_MISS), "engaged": d_engaged,
                        "walled": d_wall, "unsafe_fabrication": d_unsafe,
                        "detail": d_detail},
    }
    return report


if __name__ == "__main__":
    rep = run()
    out = os.path.join("data", "answer_quality", "reasoning_battery.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    a, d = rep["arithmetic"], rep["no_dead_end"]
    print(f"ARITHMETIC   correct {a['correct']}/{a['total']}  "
          f"abstained {a['abstained']}  WRONG {a['WRONG']}")
    print(f"NO-DEAD-END  engaged {d['engaged']}/{d['total']}  "
          f"walled {d['walled']}  unsafe_fabrication {d['unsafe_fabrication']}")
    for row in d["detail"]:
        if row["walled"]:
            print(f"  WALLED: {row['q']}")
    print(f"report -> {out}")
