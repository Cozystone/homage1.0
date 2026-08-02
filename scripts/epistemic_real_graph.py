# -*- coding: utf-8 -*-
""" — ** ConceptNet **(is_a 190k + ~10)
EpistemicGraph . ( ):
 1. ** **: (bird) 1 (penguin,robin…) ?
 → ' (,)' = . .
 2. ** **: KNOWN/INHERITED/ANALOGIZED/UNKNOWN ? 0?
No LLM. — .

 python scripts/epistemic_real_graph.py [max_isa] [max_facts]
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
CAND = REPO / "data" / "cloud_brain" / "derived_candidates"
PROP_FILES = ["conceptnet_capable_of.jsonl", "conceptnet_has_property.jsonl",
              "conceptnet_has_part.jsonl", "conceptnet_part_of.jsonl",
              "conceptnet_used_for.jsonl", "conceptnet_located_in.jsonl"]


def _iter(fn, limit):
    p = CAND / fn
    if not p.exists():
        return
    n = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            if limit and n >= limit:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("s") and r.get("o"):
                yield r; n += 1


def main():
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    max_isa = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
    max_facts = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
    t0 = time.time()
    g = EpistemicGraph(spreading=True)

    n_isa = 0
    for r in _iter("conceptnet_is_a.jsonl", max_isa):
        g.add_isa(str(r["s"]).strip().lower(), str(r["o"]).strip().lower()); n_isa += 1
    n_fact = 0
    per_pred_facts = {}
    for fn in PROP_FILES:
        p = fn.replace("conceptnet_", "").replace(".jsonl", "")
        c = 0
        for r in _iter(fn, max_facts):
            g.add_fact(str(r["s"]).strip().lower(), p, str(r["o"]).strip().lower(),
                       sources=1 + int(float(r.get("weight", 1.0)) > 2))
            n_fact += 1; c += 1
        per_pred_facts[p] = c
    load_s = round(time.time() - t0, 1)



    def _descendants(root, cap=400):
        seen, out, stack = {root}, [], [root]
        while stack and len(out) < cap:
            node = stack.pop()
            for ch in g.children.get(node, ()):
                if ch not in seen:
                    seen.add(ch); out.append(ch); stack.append(ch)
        return out

    rng = random.Random(0)
    stored = list(g.facts.keys())
    sample = rng.sample(stored, min(3000, len(stored)))
    inh_gain = 0; base = 0
    for (s, p) in sample:
        base += 1
        for d in _descendants(s):
            if (d, p) not in g.facts and (d, p) not in g.overrides:
                inh_gain += 1
    amp = round(1 + inh_gain / max(1, base), 2)


    entities = [c for c in g.isa.keys() if g.isa.get(c)]
    q_ent = rng.sample(entities, min(4000, len(entities)))
    preds = list(per_pred_facts.keys())
    grades = {}; confab = 0; examples = {"KNOWN": None, "INHERITED": None, "ANALOGIZED": None}
    for s in q_ent:
        p = rng.choice(preds)
        r = g.answer(s, p)
        grades[r["epistemic_type"]] = grades.get(r["epistemic_type"], 0) + 1
        confab += int(g.is_confabulation(r))
        et = r["epistemic_type"]
        if et in examples and examples[et] is None and r["answer"]:
            examples[et] = {"q": f"{s}.{p}", "answer": r["answer"],
                            "surface": r["surface"], "conf": r["confidence"], "path": r["path"][:1]}

    total_q = sum(grades.values())
    engaged = total_q - grades.get("UNKNOWN", 0)
    rep = {"benchmark": "EpistemicGraph on REAL ConceptNet subgraph",
           "loaded": {"is_a_edges": n_isa, "facts": n_fact, "per_pred": per_pred_facts,
                      "entities_with_parents": len(entities), "load_s": load_s},
           "inheritance_compression": {"sampled_stored_facts": base,
                                        "extra_entity_prop_covered_by_inheritance": inh_gain,
                                        "amplification_x": amp,
                                        "reading": "저장 1건이 상속으로 평균 이만큼의 (엔티티,속성)을 무저장 커버"},
           "grade_distribution": grades, "engaged_rate": round(engaged / max(1, total_q), 3),
           "confabulations": confab, "examples": examples}
    print("RESULT epistemic_real_graph", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"epistemic_real_graph_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
