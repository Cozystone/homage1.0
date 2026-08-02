# -*- coding: utf-8 -*-
"""E3 — WHICH stage of the exam cascade is anti-correlated on GPQA closed-book?

E1 (store-free) exonerated question-surface overlap: the 0.1465 (< guess 0.25, full coverage)
cannot come from surface bias, so it must come from a CASCADE STAGE firing wrong: answer_exam runs
(1) verify-gated discriminate → (2) conceptual entailment (inside discriminate) → (3) graph-evidence
rank → (4) stable guess. The prior report kept only the aggregate, so this runner re-scores the
gated set recording the PATH (mode) per item and prints fire-rate × accuracy per path — the number
that says exactly where the anti-signal lives (a fair cascade should have every stage ≥ 0.25, and
'guess' ≈ 0.25 by construction).

GPQA license (BINDING): gated CSV read from the gitignored cache only; aggregates printed, never
question/option text. Run:  python scripts/diagnose_gpqa_stage_decomposition.py [N]
"""
from __future__ import annotations

import csv
import hashlib
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
for _d in sorted((REPO / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

CSV_PATH = REPO / "data" / "benchmarks" / "gpqa" / "gpqa_diamond.csv"


def _shuffled(question: str, correct: str, incorrect: list[str]) -> tuple[dict[str, str], str]:
    seed = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16)
    opts = [correct] + incorrect
    order = list(range(4))
    for i in range(3, 0, -1):
        seed, j = divmod(seed, i + 1)
        order[i], order[j] = order[j], order[i]
    shuffled = [opts[k] for k in order]
    letters = ["A", "B", "C", "D"]
    return dict(zip(letters, shuffled)), letters[shuffled.index(correct)]


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not CSV_PATH.exists():
        print("gated GPQA cache not present")
        return 1

    from scripts.benchmark_openbook import _answer, _load_store

    kg, meta = _load_store()
    print(f"store: {meta}")
    fa = lambda t: kg.facts_about(t, limit=24)          # noqa: E731

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    if limit:
        rows = rows[:limit]
    per_path: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # path -> [n, correct]
    pick_pos = Counter()
    n = 0
    for r in rows:
        q = r.get("Question") or ""
        correct = r.get("Correct Answer") or ""
        inc = [r.get(k) or "" for k in ("Incorrect Answer 1", "Incorrect Answer 2", "Incorrect Answer 3")]
        if not q or not correct or not all(inc):
            continue
        n += 1
        choices, gold_letter = _shuffled(q, correct, inc)
        res = _answer(q, choices, gold_letter, fa)
        path = str(res.get("path") or "?")
        per_path[path][0] += 1
        per_path[path][1] += 1 if res.get("correct") else 0
        pick_pos[str(res.get("pick"))] += 1
        if n % 40 == 0:
            print(f"  …{n} scored", flush=True)

    total = sum(v[0] for v in per_path.values())
    corr = sum(v[1] for v in per_path.values())
    print(f"\n=== GPQA closed-book cascade decomposition (n={total}) ===")
    print(f"  overall: {corr/max(1,total):.4f}   (guess floor 0.25)\n")
    print(f"  {'path':<12} {'fired':>6} {'share':>7} {'acc':>7}")
    for path, (pn, pc) in sorted(per_path.items(), key=lambda kv: -kv[1][0]):
        print(f"  {path:<12} {pn:>6} {pn/max(1,total):>7.3f} {pc/max(1,pn):>7.4f}")
    print(f"\n  pick-position distribution: {dict(pick_pos)}")
    print("\nReading: any non-guess path with acc < 0.25 is the anti-signal — it should abstain to")
    print("the stable guess instead of firing. The E4 fix targets exactly those paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
