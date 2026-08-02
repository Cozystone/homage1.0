# -*- coding: utf-8 -*-
""" — (ECE). = " ". 
 ( + , = ), 
(,) · . ECE .
 ECE = . No LLM.

 python scripts/epistemic_calibration.py [n_classes] [members] [exception_rate] [override_coverage]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    n_cls = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    n_mem = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    exc = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
    ovc = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    rng = random.Random(0)
    g = EpistemicGraph()
    props = [f"prop{k}" for k in range(6)]
    truth: dict[tuple, str] = {}

    for c in range(n_cls):
        cls = f"class{c}"
        g.add_isa(cls, "root")
        for p in props:
            cls_val = f"{p}_A"
            g.add_fact(cls, p, cls_val, sources=rng.randint(1, 4))
        for m in range(n_mem):
            mem = f"c{c}m{m}"
            g.add_isa(mem, cls)
            for p in props:
                if rng.random() < exc:
                    tv = f"{p}_B"
                    truth[(mem, p)] = tv
                    if rng.random() < ovc:
                        g.add_override(mem, p, tv, sources=rng.randint(1, 3))
                else:
                    truth[(mem, p)] = f"{p}_A"


    bands = [(0.85, 1.01), (0.7, 0.85), (0.5, 0.7), (0.0, 0.5)]
    agg = {b: [0, 0] for b in bands}                              # [correct, total]
    by_type = {}
    confab = 0
    for (mem, p), tv in truth.items():
        r = g.answer(mem, p)
        pred, conf = r["answer"], r["confidence"]
        correct = int(pred == tv)
        for b in bands:
            if b[0] <= conf < b[1]:
                agg[b][0] += correct; agg[b][1] += 1; break
        t = r["epistemic_type"]
        by_type.setdefault(t, [0, 0]); by_type[t][0] += correct; by_type[t][1] += 1
        confab += int(g.is_confabulation(r))

    N = len(truth)
    ece = 0.0
    band_rows = []
    for b in bands:
        c, tot = agg[b]
        if tot == 0:
            continue
        acc = c / tot
        midconf = (b[0] + min(b[1], 1.0)) / 2
        ece += (tot / N) * abs(acc - midconf)
        band_rows.append({"band": f"{b[0]:.2f}-{min(b[1],1.0):.2f}", "n": tot, "accuracy": round(acc, 3),
                          "~conf": round(midconf, 3)})
    rep = {"benchmark": "EpistemicGraph calibration (ECE)", "n_queries": N,
           "exception_rate": exc, "override_coverage": ovc,
           "ECE": round(ece, 4), "bands": band_rows,
           "by_type": {t: {"acc": round(v[0] / v[1], 3), "n": v[1]} for t, v in by_type.items()},
           "confabulations(high-conf as KNOWN but wrong-class)": confab,
           "reading": "low ECE = the brain's confidence means what it says; KNOWN band ~1.0, INHERITED "
                      "band accuracy ~= its confidence, GUESS band low. Confabulation must be ~0."}
    print("RESULT epistemic_calibration", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    import time
    (REPO / "reports" / "benchmarks" / f"epistemic_calibration_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
