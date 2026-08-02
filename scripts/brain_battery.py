# -*- coding: utf-8 -*-
""" — ( ) :
 ·· 0·verify . ( ConceptNet ) ** **
: KNOWN/, UNKNOWN, , '' . .
No LLM.

 python scripts/brain_battery.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


ASK = [
    ("where is paris", {"KNOWN", "INHERITED"}),
    ("what is a car used for", {"KNOWN", "INHERITED"}),
    ("what can a dog do?", {"KNOWN", "INHERITED"}),
    ("properties of water", {"KNOWN", "INHERITED"}),
    ("식당|staff", {"SCHEMA"}),
    ("병원|staff", {"SCHEMA"}),
    ("존재하지않는개념xyzzy|capable_of", {"UNKNOWN"}),
    ("random_nonexistent_thing_qqq|located_in", {"UNKNOWN"}),
]
VERIFY = [
    ("is a whale a mammal?", {"AFFIRM", "UNCONFIRMED"}),
    ("can a dog bark?", {"AFFIRM", "UNCONFIRMED"}),
    ("can a dog fly?", {"UNCONFIRMED", "REFUTE"}),
    ("존재안함qqq|capable_of|fly", {"UNKNOWN"}),
]


def main():
    from packages.reasoning_vm.brain_loader import load_real_brain, parse_question, parse_verify_question
    g = load_real_brain()
    grades, confab, behaved = {}, 0, 0
    ask_rows = []
    for q, expect in ASK:
        p = parse_question(q)
        r = g.answer(*p) if p else {"epistemic_type": "UNKNOWN", "surface": "파싱실패", "confidence": 0}
        et = r["epistemic_type"]; grades[et] = grades.get(et, 0) + 1
        ok = et in expect
        behaved += int(ok); confab += int(g.is_confabulation(r)) if p else 0
        ask_rows.append({"q": q, "grade": et, "ok": ok, "surface": r["surface"]})
    v_ok = 0; v_false_no = 0; v_rows = []
    for q, expect in VERIFY:
        parsed = parse_verify_question(q)
        r = g.verify(*parsed) if parsed else {"verdict": "UNKNOWN", "surface": "파싱실패"}
        vd = r["verdict"]; ok = vd in expect
        v_ok += int(ok)

        if q.startswith("can a dog fly") and vd == "AFFIRM":
            v_false_no += 1
        v_rows.append({"q": q, "verdict": vd, "ok": ok, "surface": r["surface"]})

    total = len(ASK)
    rep = {"benchmark": "brain-like graph behavior battery",
           "loaded": g._load_stats,
           "ask": {"n": total, "behaved_as_expected": behaved, "rate": round(behaved / total, 3),
                   "grade_distribution": grades,
                   "engaged_rate": round(1 - grades.get("UNKNOWN", 0) / total, 3)},
           "verify": {"n": len(VERIFY), "behaved_as_expected": v_ok,
                      "rate": round(v_ok / len(VERIFY), 3), "false_affirmations": v_false_no},
           "confabulations": confab, "ask_rows": ask_rows, "verify_rows": v_rows,
           "gate": bool(confab == 0 and behaved == total and v_ok == len(VERIFY) and v_false_no == 0)}
    print("RESULT brain_battery", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    import time
    (REPO / "reports" / "benchmarks" / f"brain_battery_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if rep["gate"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
