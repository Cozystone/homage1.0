# -*- coding: utf-8 -*-
"""L1 — - MCQ . (s,p,o) ,
 ** p o**(= ) . 
 , ( =
 ). LLM 0. (Q, gold, distractors) 4 · .

 python scripts/mine_graph_mcq.py [n] [out.jsonl]
 : {"q", "gold", "distractors":[3], "s","p","o","source"} — supervised .
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
CAND = REPO / "data" / "cloud_brain" / "derived_candidates"


SPECS = [
    ("conceptnet_capable_of.jsonl", "capable_of", "What can {s} do?"),
    ("conceptnet_used_for.jsonl", "used_for", "What is {s} used for?"),
    ("conceptnet_has_part.jsonl", "has_part", "What is a part of {s}?"),
    ("conceptnet_part_of.jsonl", "part_of", "What is {s} a part of?"),
    ("conceptnet_located_in.jsonl", "located_in", "Where is {s} typically found?"),
    ("conceptnet_has_property.jsonl", "has_property", "What is a property of {s}?"),
    ("conceptnet_is_a.jsonl", "is_a", "What is {s}?"),
]


def _load(fn: str, limit: int = 200000):
    p = CAND / fn
    if not p.exists():
        return
    n = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            if n >= limit:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            s, o = str(r.get("s", "")).strip().lower(), str(r.get("o", "")).strip().lower()
            if s and o and s != o and 2 <= len(o) <= 40 and len(o.split()) <= 5:
                yield s, o; n += 1


def _load_isa():
    """child → siblings( ). ."""
    parents = defaultdict(set)
    children = defaultdict(set)
    for s, o in _load("conceptnet_is_a.jsonl"):
        parents[s].add(o); children[o].add(s)
    siblings = {}
    for s, ps in parents.items():
        sib = set()
        for p in ps:
            sib |= children[p]
        sib.discard(s)
        if sib:
            siblings[s] = sib
    return siblings


def main():
    n_target = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data" / "graph_scale" / "graph_mcq.jsonl"
    rng = random.Random(0)
    rows = []
    stats = {}
    siblings = _load_isa()
    for fn, pred, tmpl in SPECS:
        by_s = defaultdict(set)
        o_by_subj = defaultdict(set)
        o_pool = []
        for s, o in _load(fn):
            by_s[s].add(o); o_by_subj[s].add(o); o_pool.append(o)
        if len(o_pool) < 20:
            continue
        o_set = list(set(o_pool))
        made, hard = 0, 0
        subjects = list(by_s)
        rng.shuffle(subjects)
        for s in subjects:
            golds = by_s[s]
            gold = rng.choice(list(golds))

            sib_pool = set()
            for sib in siblings.get(s, ()):
                sib_pool |= o_by_subj.get(sib, set())
            sib_pool -= golds
            distractors = []
            if len(sib_pool) >= 3:
                distractors = rng.sample(list(sib_pool), 3); hard += 1
            else:
                seen = set(sib_pool); distractors = list(sib_pool)
                tries = 0
                while len(distractors) < 3 and tries < 60:
                    tries += 1
                    cand = rng.choice(o_set)
                    if cand not in golds and cand not in seen and cand != gold:
                        distractors.append(cand); seen.add(cand)
            if len(distractors) < 3:
                continue
            rows.append({"q": tmpl.format(s=s), "gold": gold, "distractors": distractors[:3],
                         "s": s, "p": pred, "o": gold,
                         "source": "graph_hardneg" if s in siblings else "graph_typerand"})
            made += 1
            if made >= n_target // len(SPECS) + 1:
                break
        stats[pred] = {"made": made, "sibling_hard": hard}
    rng.shuffle(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("RESULT mine_graph_mcq", json.dumps(
        {"total": len(rows), "per_pred": stats, "out": str(out_path),
         "sample": rows[:3]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
