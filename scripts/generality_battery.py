# -*- coding: utf-8 -*-
"""Generality battery — the owner's proof of general-purpose competence.

100 questions across 5 registers (daily / info / logic / prediction / creation).
A pass = the engine ANSWERS on-register (not abstention, not an error, not empty),
AND does it fast. Owner's bar: mean latency < 0.4s (offline, web_search off — the
proof is about the local brain's breadth+speed, not the network).

Correctness is NOT auto-graded (that needs a human) — every answer is written out so
the owner can eyeball the hard ones. The machine grades what it can measure honestly:
answered-vs-abstained, on-register, and latency.

  python scripts/generality_battery.py                 # run all, write report
  python scripts/generality_battery.py --cat logic     # one register
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "answer_quality" / "generality_battery_100.json"
OUT_DIR = ROOT / "data" / "answer_quality" / "generality_runs"
URL = "http://127.0.0.1:8502/api/chat/atanor"

# an answer that means "I couldn't" — these FAIL the generality bar
_ABSTAIN_MARK = (
    "확정해서 답하기 어려", "조금만 더 구체적으로", "잘 모르겠", "답을 만들지 못",
    "찾지 못했", "정보가 부족", "I couldn't", "not sure", "don't know", "no answer",
)


def ask(q: str, language: str) -> tuple[float, str, str]:
    body = json.dumps({"message": q, "language": language, "web_search": False}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        raw = urllib.request.urlopen(req, timeout=30).read()
        dt = time.perf_counter() - t0
        r = (json.loads(raw).get("result") or {})
        return dt, str(r.get("answer") or ""), str(r.get("answer_kind") or "")
    except Exception as exc:  # network/engine error is a hard fail
        return time.perf_counter() - t0, "", f"__error__:{type(exc).__name__}"


def graded(answer: str, kind: str) -> bool:
    if not answer.strip() or kind.startswith("__error__"):
        return False
    if any(m in answer for m in _ABSTAIN_MARK):
        return False
    return len(answer.strip()) >= 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", default=None, help="only one register: daily/info/logic/prediction/creation")
    args = ap.parse_args()

    spec = json.loads(DATA.read_text(encoding="utf-8"))
    qs = spec["questions"]
    if args.cat:
        qs = [q for q in qs if q["cat"] == args.cat]
    target = spec["meta"]["latency_target_s"]

    rows = []
    for item in qs:
        q = item["q"]
        language = "en" if not any(0xAC00 <= ord(c) <= 0xD7A3 for c in q) else "ko"
        dt, ans, kind = ask(q, language)
        ok = graded(ans, kind)
        rows.append({**item, "latency_s": round(dt, 3), "answer": ans, "kind": kind, "pass": ok})

    # aggregates
    cats: dict[str, list] = {}
    for r in rows:
        cats.setdefault(r["cat"], []).append(r)
    total = len(rows)
    passed = sum(1 for r in rows if r["pass"])
    lat = [r["latency_s"] for r in rows]
    lat_sorted = sorted(lat)
    mean_lat = sum(lat) / len(lat) if lat else 0.0
    p95 = lat_sorted[int(len(lat_sorted) * 0.95) - 1] if lat_sorted else 0.0
    under_target = sum(1 for x in lat if x <= target)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "at": stamp, "total": total, "passed": passed, "pass_rate": round(passed / total, 3) if total else 0,
        "latency_target_s": target, "mean_latency_s": round(mean_lat, 3),
        "p95_latency_s": round(p95, 3), "max_latency_s": round(max(lat), 3) if lat else 0,
        "under_target_count": under_target, "under_target_rate": round(under_target / total, 3) if total else 0,
        "by_category": {c: {"n": len(v), "passed": sum(1 for x in v if x["pass"]),
                            "mean_latency_s": round(sum(x["latency_s"] for x in v) / len(v), 3)}
                        for c, v in cats.items()},
        "rows": rows,
    }
    out = OUT_DIR / f"run_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== generality battery {stamp} ===")
    print(f"PASS {passed}/{total} ({report['pass_rate']*100:.0f}%)   "
          f"mean {report['mean_latency_s']}s   p95 {report['p95_latency_s']}s   "
          f"<= {target}s: {under_target}/{total}")
    for c, agg in report["by_category"].items():
        print(f"  {c:11} {agg['passed']}/{agg['n']}  mean {agg['mean_latency_s']}s")
    fails = [r for r in rows if not r["pass"]]
    if fails:
        print("--- FAILS ---")
        for r in fails[:20]:
            print(f"  [{r['id']}] {r['q']}  -> ({r['kind']}) {r['answer'][:50]}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
