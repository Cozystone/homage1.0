# -*- coding: utf-8 -*-
""" — KNOWN·INHERITED·SCHEMA·ANALOGIZED·GUESSED 
 () . . :
 · +( ) → KNOWN/INHERITED ( )
 · + typ: truth typ ( gap ) → SCHEMA
 · : , truth ana → ANALOGIZED
- (KNOWN>INHERITED>SCHEMA>ANALOGIZED) 0, ECE . No LLM.

 python scripts/epistemic_ladder_full.py [typ] [ana]
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    from packages.reasoning_vm.schema_layer import SchemaLayer
    typ = float(sys.argv[1]) if len(sys.argv) > 1 else 0.65
    ana = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
    rng = random.Random(7)

    sch = SchemaLayer()
    g = EpistemicGraph(schema=sch, spreading=True)
    truth: dict[tuple, str] = {}


    props = [f"p{k}" for k in range(4)]
    for c in range(30):
        cls = f"class{c}"; g.add_isa(cls, "thing")
        for p in props:
            g.add_fact(cls, p, f"{p}_A", sources=rng.randint(1, 4))
        for m in range(20):
            mem = f"c{c}m{m}"; g.add_isa(mem, cls)
            for p in props:
                if rng.random() < 0.2:
                    truth[(mem, p)] = f"{p}_B"
                    if rng.random() < 0.5:
                        g.add_override(mem, p, f"{p}_B", sources=rng.randint(1, 3))
                else:
                    truth[(mem, p)] = f"{p}_A"


    sprops = ["s0", "s1", "s2"]
    for si in range(15):
        situ = f"situ{si}"
        slots = {sp: f"{sp}_typ" for sp in sprops}
        sch.add(situ, slots=slots)
        for inst in range(20):
            node = f"{situ}_i{inst}"; g.add_isa(node, situ)
            for sp in sprops:

                truth[(node, sp)] = f"{sp}_typ" if rng.random() < typ else f"{sp}_atyp{inst%3}"



    for gi in range(12):
        shared = f"flavor{gi}"
        rep = f"grp{gi}_rep"
        rep_trait = f"trait_{gi}"
        g.add_fact(rep, "flavor", shared, sources=2)
        g.add_fact(rep, "trait", rep_trait, sources=2)
        for k in range(6):
            mem = f"grp{gi}_m{k}"
            g.add_fact(mem, "flavor", shared, sources=2)

            truth[(mem, "trait")] = rep_trait if rng.random() < ana else f"other_{gi}_{k%2}"


    by_type: dict[str, list[int]] = {}
    bands = [(0.85, 1.01), (0.7, 0.85), (0.55, 0.7), (0.35, 0.55), (0.0, 0.35)]
    agg = {b: [0, 0] for b in bands}
    confab = 0
    for (s, p), tv in truth.items():
        r = g.answer(s, p)
        ok = int(r["answer"] == tv)
        t = r["epistemic_type"]
        by_type.setdefault(t, [0, 0]); by_type[t][0] += ok; by_type[t][1] += 1
        for b in bands:
            if b[0] <= r["confidence"] < b[1]:
                agg[b][0] += ok; agg[b][1] += 1; break
        confab += int(g.is_confabulation(r))

    N = len(truth); ece = 0.0; band_rows = []
    for b in bands:
        c, tot = agg[b]
        if not tot:
            continue
        acc = c / tot; mid = (b[0] + min(b[1], 1.0)) / 2
        ece += (tot / N) * abs(acc - mid)
        band_rows.append({"band": f"{b[0]:.2f}-{min(b[1],1.0):.2f}", "n": tot,
                          "accuracy": round(acc, 3), "~conf": round(mid, 3)})
    order = ["KNOWN", "INHERITED", "SCHEMA", "ANALOGIZED", "GUESSED", "UNKNOWN"]
    rep = {"benchmark": "EpistemicGraph FULL ladder calibration", "n_queries": N,
           "schema_typicality": typ, "analogy_hitrate": ana, "ECE": round(ece, 4),
           "by_type": {t: {"acc": round(by_type[t][0] / by_type[t][1], 3), "n": by_type[t][1]}
                       for t in order if t in by_type},
           "bands": band_rows, "confabulations": confab,
           "reading": "각 등급 acc가 그 확신도 근처면 정직. 정렬 KNOWN>INHERITED>SCHEMA>ANALOGIZED 기대. 작화=0 필수."}
    print("RESULT epistemic_ladder_full", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"epistemic_ladder_full_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
