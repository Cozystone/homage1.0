# -*- coding: utf-8 -*-
"""L2 v2 — . ** **: ,
 ' ' (acc=n0, acc=op_i(acc,n_i)). GSM8K (→
 , 2~4). ** → **( = ).
 round-trip ( , 0). LLM 0. ··.

 python scripts/gen_synthetic_math_v2.py [n] [out.jsonl]
: {"question","numbers":[...],"labels":["base","+","*",...],"answer"} — labels[i]=n_i .
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NAMES = ["Tom", "Sara", "Mike", "Anna", "Ben", "Lucy", "Sam", "Emma", "Jack", "Mia", "Leo", "Zoe",
         "Noah", "Ella", "Ryan", "Nina", "Alex", "Kate", "Ian", "Ruby", "Omar", "Tara"]
ITEMS = ["apples", "books", "coins", "marbles", "cookies", "pencils", "stickers", "cards", "eggs",
         "flowers", "candies", "stamps", "shells", "balloons", "oranges", "toys", "beads", "nuts",
         "grapes", "buttons", "rocks", "leaves"]
UNITS = ["boxes", "bags", "baskets", "shelves", "jars", "packs", "crates", "bins", "rows", "groups"]


ADD = ["Then {w} found {v} more {it}.", "{w} bought {v} additional {it}.",
       "Later, {w} got {v} more {it}.", "{w2} gave {w} {v} more {it}.",
       "{w} picked up {v} extra {it}.", "Someone added {v} {it} to the pile."]
SUB = ["{w} gave away {v} {it}.", "{w} lost {v} {it}.", "{w} used {v} {it}.",
       "{w} ate {v} of them.", "{v} {it} fell out and were lost.", "{w} sold {v} {it}."]
MUL = ["Then the total was multiplied by {v}.", "{w2} gave {w} {v} times that many {it}.",
       "The amount grew to {v} times as much.", "{w} tripled it." ]  # v-aware handled below
DIV = ["{w} split them equally into {v} {u}.", "They were shared among {v} {u} evenly.",
       "{w} divided them into {v} equal {u}."]
START = ["{w} has {v} {it}.", "{w} started with {v} {it}.", "There were {v} {it} in {w}'s collection.",
         "{w} owns {v} {it}.", "{w} collected {v} {it}."]
QEND = ["How many {it} does {w} have now?", "How many {it} are there in the end?",
        "What is the final number of {it}?", "How many {it} remain?"]


def build(rng):
    who = rng.choice(NAMES); who2 = rng.choice([n for n in NAMES if n != who])
    it = rng.choice(ITEMS); u = rng.choice(UNITS)
    depth = rng.randint(1, 4)

    def fill(s, v):
        return s.format(v=(int(v) if float(v) == int(v) else v), w=who, w2=who2, it=it, u=u)

    base = rng.randint(6, 50)
    nums = [float(base)]; labels = ["base"]; frags = [fill(rng.choice(START), base)]
    acc = float(base)
    for _ in range(depth):
        kind = rng.choice(["+", "+", "-", "*", "/"])
        if kind == "+":
            v = rng.randint(2, 40); acc += v; frags.append(fill(rng.choice(ADD), v))
        elif kind == "-":
            v = rng.randint(1, max(1, int(acc)))
            if v >= acc:
                v = rng.randint(1, max(1, int(acc) - 1)) if acc > 1 else 0
                if v == 0:
                    continue
            acc -= v; frags.append(fill(rng.choice(SUB), v))
        elif kind == "*":
            v = rng.randint(2, 5); acc *= v; frags.append(fill(rng.choice(MUL), v))
        else:  # /
            v = rng.choice([2, 3, 4, 5])
            if int(acc) % v != 0:
                continue
            acc /= v; frags.append(fill(rng.choice(DIV), v))
        nums.append(float(v)); labels.append(kind)
    if len(nums) < 2 or acc < 0 or acc != int(acc) or acc > 1e7:
        return None
    q = " ".join(frags) + " " + fill(rng.choice(QEND), 0)
    # round-trip
    chk = nums[0]
    for lab, v in zip(labels[1:], nums[1:]):
        chk = {"+": chk + v, "-": chk - v, "*": chk * v, "/": chk / v if v else None}[lab]
        if chk is None:
            return None
    if abs(chk - acc) > 1e-6:
        return None
    return {"question": q, "numbers": nums, "labels": labels, "answer": float(int(acc)), "depth": depth}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80000
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data" / "graph_scale" / "synthetic_math_v2.jsonl"
    rng = random.Random(0)
    rows, bad = [], 0
    while len(rows) < n and bad < n * 4:
        g = build(rng)
        if g is None:
            bad += 1; continue
        rows.append(g)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    lab = Counter(l for r in rows for l in r["labels"] if l != "base")
    print("RESULT gen_synthetic_math_v2", json.dumps(
        {"total": len(rows), "rejected": bad, "depth_dist": dict(sorted(Counter(r["depth"] for r in rows).items())),
         "label_dist": dict(lab), "out": str(out), "sample": rows[2]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
