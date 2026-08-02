# -*- coding: utf-8 -*-
"""GPQA Diamond CLOSED-BOOK baseline (learned graph = the model) — reuses the closed-book scorer, keeps GPQA SEALED.

GPQA license (BINDING): do NOT reveal examples in plain text online. So this runner:
  - reads the gated CSV only from the gitignored cache (data/benchmarks/gpqa/),
  - deterministically shuffles the 4 options per question (seed = question hash) → stable A-D,
  - scores closed-book via benchmark_openbook._answer (graph evidence overlap, No-LLM),
  - writes a report with TOPIC TOKENS only — never question text/choices/answers — and the report
    is NOT committed (reports/ is gitignored; do not force-add GPQA).

  python scripts/benchmark_gpqa.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
for _d in sorted((REPO / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from scripts.benchmark_openbook import _answer  # noqa: E402

CSV = REPO / "data" / "benchmarks" / "gpqa" / "gpqa_diamond.csv"
REPORTS = REPO / "reports" / "benchmarks"


def _shuffled(question: str, correct: str, incorrect: list[str]) -> tuple[dict[str, str], str]:
    """Deterministic option order from a question hash → identical layout across reruns."""
    seed = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16)
    opts = [correct] + incorrect
    order = list(range(4))
    for i in range(3, 0, -1):                       # Fisher-Yates with the seeded stream
        seed, j = divmod(seed, i + 1)
        order[i], order[j] = order[j], order[i]
    letters = "ABCD"
    choices = {letters[k]: str(opts[order[k]]).strip() for k in range(4)}
    gold = letters[order.index(0)]
    return choices, gold


def main() -> int:
    if not CSV.exists():
        print("no GPQA cache — download gpqa_diamond.csv first (needs accepted gate + HF token)")
        return 1
    from packages.graph_scale import answer_bridge as AB
    kg = AB._store()
    fa = lambda t: kg.facts_about(t, limit=24)      # noqa: E731

    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    items, total = [], 0
    answered = correct_ans = correct_tot = 0
    t0 = time.time()
    for r in rows:
        q = str(r.get("Question") or "").strip()
        cor = str(r.get("Correct Answer") or "").strip()
        inc = [str(r.get(f"Incorrect Answer {i}") or "").strip() for i in (1, 2, 3)]
        if not q or not cor or not all(inc):
            continue
        choices, gold = _shuffled(q, cor, inc)
        res = _answer(q, choices, gold, fa)
        items.append({"subject": "diamond", "q_tokens": res["q_tokens"],
                      "answered": res["answered"], "correct": res["correct"]})
        total += 1
        if res["answered"]:
            answered += 1
            if res["correct"]:
                correct_ans += 1
                correct_tot += 1

    report = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "store_meta": json.loads((REPO / "data/graph_scale/kg_triples/meta.json")
                                 .read_text(encoding="utf-8")),
        "benchmark": "GPQA-Diamond(closed-book)", "n": total,
        "answered": answered, "coverage": round(answered / max(1, total), 4),
        "answered_acc": round(correct_ans / max(1, answered), 4) if answered else None,
        "strict_acc": round(correct_tot / max(1, total), 4),
        "guess_baseline": 0.25, "items": items, "elapsed_s": round(time.time() - t0, 1),
        "honest_note": "GPQA Diamond is expert-PhD-level (~65% expert, ~34% skilled non-expert, "
                       "~39% GPT-4). strict_acc counts abstentions wrong. Topic tokens only; "
                       "question text never stored (license + no-training-on-test guard).",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"gpqa_diamond_closedbook_{time.strftime('%Y%m%d_%H%M')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GPQA-Diamond n={total}  coverage={report['coverage']:.3f}  "
          f"answered_acc={report['answered_acc']}  strict_acc={report['strict_acc']:.3f}  (guess=0.25)")
    print(f"wrote {out}  (NOT committed — GPQA stays sealed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
