#!/usr/bin/env python3
"""PHFE question battery — measure the hidden wave-interference core against real answers.

The Phase-Holographic Folding Engine runs in compare_mode: it folds the internal state for
every eligible question and logs how well its folded core AGREES with the evidence the
actual answer path used — without ever changing the answer (fold_driver_mode=compare_mode,
answer_changed=False). This battery quantifies that agreement across varied real questions:

  attach rate      how often the fold even runs (concept coverage of the question)
  agreement        jaccard / recall between folded core and answer evidence
  coherence        folded_global_coherence (field self-consistency)
  timing           fold_timing_ms (must stay cheap — it rides every answer)

Honest purpose: this is the promotion gate for the user's core PHFE vision — the wave core
may only graduate from hidden trace to answer driver when its agreement is consistently
high. Results are appended to data/eval/phfe_battery_history.jsonl so the trend is visible.

  python scripts/phfe_battery.py            # run against the live :8502 engine
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "eval" / "phfe_battery_history.jsonl"
URL = "http://127.0.0.1:8502/api/chat/atanor"

# Varied real questions: definitions, factual lookups, causal, self, conversational —
# the same mix users actually send (fold eligibility should differ across these).
QUESTIONS = [
    "세포란 무엇인가요?",
    "탄소란?",
    "인공지능이 뭐야?",
    "일본의 수도는?",
    "중력이란?",
    "광합성은 왜 중요해?",
    "너는 누구야?",
    "너 지금 무슨 생각해?",
    "DNA와 유전자의 차이는?",
    "성남시가 뭐야?",
    "요즘 피곤한데 어떡하지?",
    "12 곱하기 12는?",
]


def ask(question: str) -> dict:
    body = json.dumps({"question": question, "language": "ko"}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    rows = []
    for q in QUESTIONS:
        t0 = time.time()
        try:
            resp = ask(q)
        except Exception as exc:
            rows.append({"q": q, "error": str(exc)[:80]})
            print(f"  ERR  {q}  ({exc})")
            continue
        result = resp.get("result") or resp
        fold = (result.get("compact_trace") or {}).get("holographic_fold")
        engine = result.get("answer_engine") or {}
        row = {
            "q": q,
            "answer_kind": result.get("answer_kind"),
            "attached": bool(fold),
            "wall_ms": round((time.time() - t0) * 1000),
        }
        if fold:
            row.update({
                "jaccard": fold.get("agreement_jaccard"),
                "recall": fold.get("agreement_recall"),
                "overlap": fold.get("agreement_overlap"),
                "coherence": fold.get("folded_global_coherence"),
                "fold_ms": fold.get("fold_timing_ms"),
                "answer_changed": fold.get("answer_changed"),
            })
        row["hidden_trace_only"] = engine.get("fold_answer_source") == "hidden_trace_only"
        rows.append(row)
        mark = "FOLD" if fold else "----"
        print(f"  {mark} j={row.get('jaccard','-')!s:6} r={row.get('recall','-')!s:6} "
              f"coh={row.get('coherence','-')!s:6} {q}")

    attached = [r for r in rows if r.get("attached")]
    summary = {
        "at": datetime.now(timezone.utc).isoformat(),
        "questions": len(QUESTIONS),
        "errors": sum(1 for r in rows if "error" in r),
        "attach_rate": round(len(attached) / max(1, len(rows) - sum(1 for r in rows if "error" in r)), 3),
        "mean_jaccard": round(sum(float(r.get("jaccard") or 0) for r in attached) / len(attached), 4) if attached else None,
        "mean_recall": round(sum(float(r.get("recall") or 0) for r in attached) / len(attached), 4) if attached else None,
        "mean_fold_ms": round(sum(float(r.get("fold_ms") or 0) for r in attached) / len(attached), 1) if attached else None,
        "answer_never_changed": all(r.get("answer_changed") is False for r in attached) if attached else None,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
