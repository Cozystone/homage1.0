# -*- coding: utf-8 -*-
"""L2 — (AlphaGeometry ' ' ). (··%)
 ** + ( ) + ** . (→)
 — v0 (GSM8K 0.014) ' ' . (0).
LLM 0. round-trip ( ) .

 python scripts/gen_synthetic_math.py [n] [out.jsonl]
: {"question","answer","derivation":[["op",a,b,r]...],"template"} — (→ ).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NAMES = ["Tom", "Sara", "Mike", "Anna", "Ben", "Lucy", "Sam", "Emma", "Jack", "Mia"]
ITEMS = ["apples", "books", "coins", "marbles", "cookies", "pencils", "stickers", "cards", "eggs", "flowers"]
CONTAINERS = ["boxes", "bags", "baskets", "shelves", "jars", "packs"]


def _r(rng, lo, hi):
    return rng.randint(lo, hi)


def gen(rng) -> dict | None:
    """ 2~3 + ."""
    who, who2 = rng.sample(NAMES, 2)
    item = rng.choice(ITEMS)
    cont = rng.choice(CONTAINERS)
    t = rng.randint(0, 5)
    d = []
    if t == 0:  # a + b, then - c  (has, gets more, gives away)
        a, b, c = _r(rng, 5, 40), _r(rng, 3, 30), _r(rng, 1, 20)
        s1 = a + b; ans = s1 - c
        if ans < 0:
            return None
        q = (f"{who} has {a} {item}. {who2} gives {who} {b} more. "
             f"Then {who} gives away {c} {item}. How many {item} does {who} have now?")
        d = [["+", a, b, s1], ["-", s1, c, ans]]
    elif t == 1:  # groups * per + extra
        g, per, ex = _r(rng, 2, 12), _r(rng, 2, 15), _r(rng, 0, 20)
        s1 = g * per; ans = s1 + ex
        q = (f"There are {g} {cont} with {per} {item} in each. There are also {ex} extra {item}. "
             f"How many {item} are there in total?")
        d = [["*", g, per, s1], ["+", s1, ex, ans]]
    elif t == 2:  # total / groups  (share equally)
        per, g = _r(rng, 2, 20), _r(rng, 2, 10)
        tot = per * g; ans = per
        q = (f"{who} shares {tot} {item} equally among {g} {cont}. "
             f"How many {item} are in each of the {cont}?")
        d = [["/", tot, g, ans]]
    elif t == 3:  # a - b, then * k
        a, b, k = _r(rng, 20, 60), _r(rng, 1, 19), _r(rng, 2, 5)
        s1 = a - b; ans = s1 * k
        q = (f"{who} had {a} {item} but lost {b}. Then {who2} gave {who} {k} times that many {item}. "
             f"How many {item} did {who2} give?")
        d = [["-", a, b, s1], ["*", s1, k, ans]]
    elif t == 4:  # percent of
        base = _r(rng, 1, 20) * 10; pct = rng.choice([10, 20, 25, 50, 75])
        ans = base * pct // 100
        q = f"{who} has {base} {item} and gives {pct}% of them to {who2}. How many {item} does {who2} get?"
        d = [["*", base, pct, base * pct], ["/", base * pct, 100, ans]]
    else:  # two groups sum then split
        a, b, g = _r(rng, 5, 30), _r(rng, 5, 30), rng.choice([2, 3, 5])
        s1 = a + b
        if s1 % g != 0:
            return None
        ans = s1 // g
        q = (f"{who} has {a} {item} and {who2} has {b} {item}. They combine them and split equally into "
             f"{g} {cont}. How many {item} go in each?")
        d = [["+", a, b, s1], ["/", s1, g, ans]]
    return {"question": q, "answer": float(ans), "derivation": d, "template": t}


def _execute(d):
    """ () — round-trip . ."""
    ops = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
           "/": lambda a, b: a / b if b else None}
    last = None
    for op, a, b, r in d:
        got = ops[op](a, b)
        if got is None or abs(got - r) > 1e-6:
            return None
        last = got
    return last


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data" / "graph_scale" / "synthetic_math.jsonl"
    rng = random.Random(0)
    rows, bad = [], 0
    while len(rows) < n and bad < n * 3:
        g = gen(rng)
        if g is None:
            bad += 1; continue
        chk = _execute(g["derivation"])
        if chk is None or abs(chk - g["answer"]) > 1e-6:
            bad += 1; continue
        rows.append(g)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    tmpl = Counter(r["template"] for r in rows)
    print("RESULT gen_synthetic_math", json.dumps(
        {"total": len(rows), "roundtrip_verified": len(rows), "rejected": bad,
         "by_template": dict(tmpl), "out": str(out), "sample": rows[0]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
