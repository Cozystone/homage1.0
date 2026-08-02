# -*- coding: utf-8 -*-
"""CLOSED-BOOK benchmark through the LIVE ENGINE — the real answer path, not a toy scorer.

Receipts that forced this (2026-07-15, commit 6cb59ce2): three same-condition runs proved the
token-overlap scorer has NO signal on KMMLU conceptual MCQ (acc 0.133→0.063→0.0, all ≤ guess),
and the trained clean phase space knows 3/14 of the failure vocabulary (semantic matcher dead on
arrival). Meanwhile the engine's FULL answer path (intent execution, definitions, multihop,
honesty gates — the machinery that holds P0 23/23) had never been pointed at a benchmark.

This adapter asks the LIVE engine each cached KMMLU question (same items as the harness), then
scores each choice by overlap with the ENGINE'S OWN ANSWER TEXT. Closed-book bookkeeping: every
row records the engine's answer kind; any web-sourced kind is EXCLUDED from the closed-book
accuracy and reported separately (owner's naming correction: learned graph = the model =
closed-book; web at test time would be open-book).

  python scripts/benchmark_engine.py [n_per_subject]      # default 8, same cache as the harness
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# NOTE: benchmark_openbook wraps sys.stdout in utf-8 at import — do NOT wrap again here
# (double-wrapping orphans the first wrapper, which closes the shared buffer on GC).
from scripts.benchmark_openbook import _fetch_subject, _tokens, SUBJECTS  # noqa: E402

ENGINE = "http://127.0.0.1:8502"
REPORTS = REPO / "reports" / "benchmarks"
_WEB_KIND = re.compile(r"web|search|rescue", re.I)


def _ask(q: str) -> dict:
    body = json.dumps({"message": q, "conversation_context": []}).encode("utf-8")
    req = urllib.request.Request(ENGINE + "/api/chat/atanor", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=60) as r:      # nosec B310 - localhost engine
        out = json.loads(r.read().decode("utf-8"))
    res = out.get("result") if isinstance(out, dict) else {}
    return res if isinstance(res, dict) else {}


def _pick(answer_text: str, question: str, choices: dict[str, str]) -> tuple[str | None, float]:
    """Choose the option most supported by the engine's own words — fresh tokens only (the
    engine's answer minus the question's words), the lesson from the harness dissection."""
    fresh = _tokens(answer_text) - _tokens(question)
    if not fresh:
        return None, 0.0
    best, second, pick = 0.0, 0.0, None
    for letter, text in choices.items():
        ct = _tokens(text)
        s = (len(ct & fresh) / max(1, len(ct))) if ct else 0.0
        if s > best:
            best, second, pick = s, best, letter
        elif s > second:
            second = s
    if pick is None or best <= 0.0 or best == second:       # nothing or a tie → honest abstain
        return None, best
    return pick, best


def main() -> int:
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    total = answered = correct = web_rows = 0
    per_subject: dict[str, list[int]] = {}
    rows_out = []
    for subj in SUBJECTS:
        rows = _fetch_subject(subj)[:n_per]
        s_n = s_ans = s_cor = 0
        for row in rows:
            q = str(row.get("question") or "")
            choices = {k: str(row.get(k) or "") for k in ("A", "B", "C", "D")}
            gold = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(str(row.get("answer") or "").strip())
            if not q or not gold:
                continue
            total += 1
            s_n += 1
            try:
                res = _ask(q)
            except Exception:
                res = {}
            ans = str(res.get("answer") or "")
            kind = str(res.get("kind") or res.get("route") or "")
            is_web = bool(_WEB_KIND.search(kind))
            if is_web:
                web_rows += 1                                # open-book leak — excluded below
            pick, score = _pick(ans, q, choices) if (ans and not is_web) else (None, 0.0)
            if pick is not None:
                answered += 1
                s_ans += 1
                if pick == gold:
                    correct += 1
                    s_cor += 1
            rows_out.append({"subject": subj, "q": q[:80], "gold": gold, "pick": pick,
                             "score": round(score, 3), "kind": kind, "web": is_web,
                             "answer_head": ans[:100]})
        per_subject[subj] = [s_n, s_ans, s_cor]
        acc = (s_cor / s_ans) if s_ans else None
        print(f"  {subj:38} n={s_n:3}  engine_answered={s_ans}  acc={acc if acc is None else round(acc, 3)}")

    cov = answered / max(1, total)
    aacc = (correct / answered) if answered else None
    strict = correct / max(1, total)
    print(f"\nTOTAL n={total}  closed_book_answered={answered}  coverage={cov:.3f}  "
          f"answered_acc={aacc if aacc is None else round(aacc, 4)}  strict_acc={strict:.3f}  "
          f"web_excluded_rows={web_rows}  (guess=0.25)")
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"kmmlu_engine_closedbook_{time.strftime('%Y%m%d_%H%M')}.json"
    out.write_text(json.dumps({
        "benchmark": "KMMLU(engine,closed-book)", "n": total, "coverage": round(cov, 4),
        "answered_acc": aacc, "strict_acc": round(strict, 4), "web_excluded_rows": web_rows,
        "per_subject": per_subject, "rows": rows_out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
