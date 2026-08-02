# -*- coding: utf-8 -*-
"""D2 — measure the S1/S2 router. On a mix of single-hop (SQuAD) and multi-hop (HotpotQA) questions, does
routing keep S1 (cheap) for the easy ones and escalate to S2 (multi-evidence) only for the hard ones,
reaching ~S2 accuracy at well-below-S2 cost? Reports per-set F1 for always-S1, always-S2, and routed, plus
escalation rate and a cost proxy (mean evidence paragraphs read). No LLM.

  python scripts/deliberator_d2_router.py [n_each]
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_ART = {"a", "an", "the"}


def _norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(w for w in s.split() if w not in _ART)


def _f1(pred, gold):
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)
    c = sum((Counter(p) & Counter(g)).values())
    if not c:
        return 0.0
    pr, rc = c / len(p), c / len(g)
    return 2 * pr * rc / (pr + rc)


def _hotpot(n):
    import pandas as pd
    df = pd.read_parquet(REPO / "data" / "benchmarks" / "hotpotqa" / "dev_distractor.parquet")
    out = []
    for _i, r in df.iterrows():
        if len(out) >= n:
            break
        if str(r["answer"]).lower() in ("yes", "no"):
            continue
        ctx = r["context"]
        titles, sents = list(ctx["title"]), list(ctx["sentences"])
        paras = [(str(titles[j]), " ".join(str(x) for x in sents[j])) for j in range(len(titles))]
        out.append((str(r["question"]), paras, str(r["answer"])))
    return out


def _squad(n):
    from packages.reasoning_vm.ace import data as D
    rows = [r for r in D.load_squad("dev") if r["answerable"]][:n]
    # single passage split into pseudo-paragraphs so the router has candidates (single-hop by construction)
    out = []
    for r in rows:
        ctx = str(r["ctx"])
        parts = re.split(r"(?<=[.!?])\s+", ctx)
        paras = [(f"s{j}", " ".join(parts[j:j + 2])) for j in range(0, max(1, len(parts)), 2)][:6]
        out.append((str(r["q"]), paras, str(r["golds"][0] if r["golds"] else "")))
    return out


def _eval(reader, router, rows):
    from time import time as _t
    s1 = s2 = rt = esc = passes = 0.0
    t0 = _t()
    for q, paras, gold in rows:
        a1 = reader.answer(q, paras, k=1, chain=False, rank="ans")
        a2 = reader.answer(q, paras, k=3, chain=False, rank="ans")
        ar = router.answer(q, paras)
        s1 += _f1(a1["answer"], gold); s2 += _f1(a2["answer"], gold); rt += _f1(ar["answer"], gold)
        esc += float(ar["escalated"]); passes += (3 if ar["escalated"] else 1)
    n = max(1, len(rows))
    return {"n": len(rows), "S1_F1": round(s1 / n, 4), "S2_F1": round(s2 / n, 4),
            "routed_F1": round(rt / n, 4), "escalation_rate": round(esc / n, 4),
            "mean_passes_routed": round(passes / n, 2), "mean_passes_alwaysS2": 3.0,
            "elapsed_s": round(_t() - t0, 1)}


def main():
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    from packages.reasoning_vm.deliberator.system_router import SystemRouter
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    reader = MultiHopReader(ckpt="ace_hotpot.pt")
    router = SystemRouter(reader)
    rep = {"benchmark": "D2 S1/S2 router",
           "hotpot_multihop": _eval(reader, router, _hotpot(n)),
           "squad_singlehop": _eval(reader, router, _squad(n)),
           "reading": "router should stay S1 (low escalation) on single-hop SQuAD and escalate on multi-hop "
                      "HotpotQA, keeping routed_F1 ~= max(S1,S2) at mean_passes < 3 (cheaper than always-S2)."}
    print("\nRESULT d2_router", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"d2_router_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
