# -*- coding: utf-8 -*-
"""L2 v0 — GSM8K No-LLM . - - = No-LLM .
: + → → DFS → . (0).
: — v0 1~2 . ( ).

 python scripts/gsm8k_solve.py [n]
"""
from __future__ import annotations

import json
import re
import sys
from itertools import combinations, permutations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
G = REPO / "data" / "benchmarks" / "gsm8k" / "test.jsonl"
_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")


def _gold(ans: str) -> float | None:
    m = re.search(r"####\s*([-\d.,]+)", ans)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None


def _nums(q: str) -> list[float]:
    out = []
    for m in _NUM.findall(q.replace(",", "")):
        try:
            out.append(float(m))
        except Exception:
            pass
    return out


def solve(q: str, max_nums: int = 5) -> float | None:
    """ : , . - ."""
    nums = _nums(q)
    if not (2 <= len(nums) <= 8):
        return None
    ql = q.lower()

    wants = []
    if any(k in ql for k in ("total", "altogether", "in all", "sum", "combined", "how many", "how much")):
        wants.append("+")
    if any(k in ql for k in ("each", "every", "per ", "times", "twice", "double")):
        wants.append("*")
    if any(k in ql for k in ("left", "remain", "how many more", "difference", "fewer", "lost", "gave", "ate", "spent")):
        wants.append("-")
    if any(k in ql for k in ("split", "share", "divide", "each of", "average", "per person")):
        wants.append("/")
    ops = wants or ["+", "-", "*", "/"]
    use = nums[:max_nums]
    best, best_score = None, -1.0

    def ap(a, b, op):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        return a / b if b else None


    for k in (2, 3):
        if len(use) < k:
            continue
        for combo in combinations(range(len(use)), k):
            vals = [use[i] for i in combo]
            for perm in permutations(vals):
                for op1 in ops:
                    r = ap(perm[0], perm[1], op1)
                    if r is None:
                        continue
                    if k == 2:
                        cands = [(r, [op1])]
                    else:
                        cands = []
                        for op2 in ops:
                            r2 = ap(r, perm[2], op2)
                            if r2 is not None:
                                cands.append((r2, [op1, op2]))
                    for val, used_ops in cands:
                        if val is None or val < 0 or val != val:
                            continue

                        score = 0.0
                        if abs(val - round(val)) < 1e-6:
                            score += 1.0
                        score += sum(0.6 for o in used_ops if o in wants)
                        score += 0.1 * k
                        if 0 < val < 1e7:
                            score += 0.2
                        if score > best_score:
                            best_score, best = score, val
    return best


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rows = [json.loads(l) for l in G.read_text(encoding="utf-8").splitlines()][:n]
    correct = attempted = 0
    for r in rows:
        g = _gold(r["answer"])
        if g is None:
            continue
        pred = solve(r["question"])
        if pred is not None:
            attempted += 1
            if abs(pred - g) < 1e-4:
                correct += 1
    acc = correct / max(1, len(rows))
    rep = {"benchmark": "GSM8K (No-LLM deterministic v0)", "n": len(rows),
           "correct": correct, "attempted": attempted, "strict_acc": round(acc, 4),
           "attempted_acc": round(correct / max(1, attempted), 4),
           "reading": "계산-바운드 축(No-LLM 최적합). v0은 1~2연산만. >0이면 진짜(검증가능 환각0). 다단계=다음."}
    print("RESULT gsm8k_solve", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
