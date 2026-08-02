# -*- coding: utf-8 -*-
"""D1 gate measurement — run the full adversarial 100 through the LIVE engine, classify the
misses by category, and print the honest number. Reuses self_teach_from_failures._is_miss so
the miss definition matches the sprint daemon (no grading theater)."""
from __future__ import annotations
import io, json, sys, time, urllib.request
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "apps" / "api"))

import importlib.util
spec = importlib.util.spec_from_file_location("stf", str(ROOT / "scripts" / "self_teach_from_failures.py"))
stf = importlib.util.module_from_spec(spec); spec.loader.exec_module(stf)

QS = json.load(open(ROOT / "data/answer_quality/adversarial_battery_100.json", encoding="utf-8"))["questions"]


def _ask(q: str, lang: str) -> dict:
    data = json.dumps({"message": q, "language": lang, "web_search": False}).encode()
    req = urllib.request.Request("http://127.0.0.1:8502/api/chat/atanor", data=data,
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("result", {})
    return {"answer": r.get("answer") or "", "kind": r.get("answer_kind") or "?"}


def main() -> int:
    miss_by_cat: Counter = Counter()
    tot_by_cat: Counter = Counter()
    misses: list[tuple] = []
    lat = 0.0
    t_all = time.time()
    for q in QS:
        cat = q["cat"]; text = q["q"]
        lang = "ko" if any("가" <= c <= "힣" for c in text) else "en"
        tot_by_cat[cat] += 1
        t = time.time()
        try:
            res = _ask(text, lang)
        except Exception as e:
            res = {"answer": "", "kind": f"__err__ {type(e).__name__}"}
        lat += time.time() - t
        if stf._is_miss(cat, res["answer"], res["kind"]):
            miss_by_cat[cat] += 1
            misses.append((cat, text, res["kind"], res["answer"][:70]))
    n = len(QS); miss = sum(miss_by_cat.values())
    print(f"=== D1 adversarial 100 (LIVE) ===  pass {n-miss}/{n}  |  mean {lat/n:.2f}s  |  wall {time.time()-t_all:.0f}s")
    print("--- miss by category ---")
    for cat in sorted(tot_by_cat):
        m, t = miss_by_cat[cat], tot_by_cat[cat]
        bar = "MISS" if m else "ok"
        print(f"  {cat:18s} {t-m:2d}/{t:2d}   {bar if m==0 else str(m)+' miss'}")
    print("--- sample misses ---")
    for cat, text, kind, ans in misses[:22]:
        print(f"  [{cat}] {text[:30]}\n      ({kind}) {ans}")
    out = ROOT / "data/answer_quality/d1_live_measure.json"
    out.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pass": n-miss, "n": n,
                               "mean_s": round(lat/n, 3),
                               "miss_by_cat": dict(miss_by_cat), "tot_by_cat": dict(tot_by_cat),
                               "misses": [{"cat": c, "q": q, "kind": k, "a": a} for c, q, k, a in misses]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
