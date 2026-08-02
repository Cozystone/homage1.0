# -*- coding: utf-8 -*-
"""DELIBERATOR D3.3 — does the INTERNAL MONOLOGUE (iterative sub-query chaining, adaptive hops via the
DoubtGate) beat the single-shot reader on HotpotQA? Same dev subset, same span questions, head-to-head:
  • single  — rd.answer(rank='ans', chain=False)         [prior full-pipe F1 0.409]
  • iter    — rd.answer_iterative(max_hops=2, gate=DoubtGate)
Reports answer F1/EM (span Qs) for both + the mean hop count the monologue actually used. Honest: if iter
does not beat single, say so — the value is the inspectable reasoning trail either way, but the number decides
whether adaptive chaining earns the default. No LLM.

  python scripts/deliberator_d3_iter.py [n]
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


def main():
    import pandas as pd
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    df = pd.read_parquet(REPO / "data" / "benchmarks" / "hotpotqa" / "dev_distractor.parquet")
    rd = MultiHopReader(ckpt="ace_hotpot.pt")
    gate = DoubtGate(rd, threshold=0.7)                             # conf=p_ans; stop hopping when confident

    s_f1 = s_em = i_f1 = i_em = i2_f1 = i2_em = 0.0
    span_n = 0
    hops = 0
    total = 0
    for _idx, r in df.iterrows():
        if total >= n:
            break
        ctx = r["context"]
        titles, sents = list(ctx["title"]), list(ctx["sentences"])
        paras = [(str(titles[j]), " ".join(str(x) for x in sents[j])) for j in range(len(titles))]
        gold = str(r["answer"])
        if gold.lower() in ("yes", "no"):
            total += 1
            continue                                               # yes/no scored elsewhere (D3.1)
        q = str(r["question"])
        single = rd.answer(q, paras, k=2, chain=False, rank="ans")
        it = rd.answer_iterative(q, paras, max_hops=2, gate=gate)         # adaptive stop
        it2 = rd.answer_iterative(q, paras, max_hops=2, gate=None)        # forced 2 hops
        s_f1 += _f1(single["answer"], gold); s_em += float(_norm(single["answer"]) == _norm(gold))
        i_f1 += _f1(it["answer"], gold); i_em += float(_norm(it["answer"]) == _norm(gold))
        i2_f1 += _f1(it2["answer"], gold); i2_em += float(_norm(it2["answer"]) == _norm(gold))
        hops += len(it["monologue"])
        span_n += 1
        total += 1

    rep = {"benchmark": "HotpotQA multi-hop: internal monologue vs single-shot", "span_n": span_n,
           "single_F1": round(s_f1 / max(1, span_n), 4), "single_EM": round(s_em / max(1, span_n), 4),
           "iter_adaptive_F1": round(i_f1 / max(1, span_n), 4), "iter_adaptive_EM": round(i_em / max(1, span_n), 4),
           "iter_adaptive_mean_hops": round(hops / max(1, span_n), 2),
           "iter_forced2hop_F1": round(i2_f1 / max(1, span_n), 4), "iter_forced2hop_EM": round(i2_em / max(1, span_n), 4),
           "best_beats_single_F1": bool(max(i_f1, i2_f1) > s_f1),
           "reading": "the monologue forges sub-queries hop-by-hop (inspectable trail) with adaptive hop "
                      "count; F1 decides whether it earns the default over single-shot.",
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d3.3_iter", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"deliberator_d3_iter_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
