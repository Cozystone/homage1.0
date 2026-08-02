# -*- coding: utf-8 -*-
"""L1 — MCQ **MMLU( ) ?** 
 MCQ = L1 . (0.25)·baseline(0.26) . .

 python scripts/eval_judge_mmlu.py [n_per_subject] [ckpt]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.train_mcq_judge import Judge, _ids, _pad, DEV     # noqa: E402
from scripts.benchmark_openbook import _fetch_mmlu             # noqa: E402


def main():
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    ckpt = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data" / "graph_scale" / "mcq_judge.pt"
    model = Judge().to(DEV)
    model.load_state_dict(torch.load(ckpt, map_location=DEV)); model.eval()
    rows = _fetch_mmlu(n_per)
    letters = "ABCD"
    correct = tot = 0
    per_subj: dict[str, list] = {}
    for r in rows:
        opts = [r["choices"][k] for k in letters]
        gi = letters.index(r["gold"])
        qs = [_ids(r["question"]) for _ in opts]
        os_ = [_ids(o) for o in opts]
        with torch.no_grad():
            q = torch.tensor(_pad(qs, 16), device=DEV); o = torch.tensor(_pad(os_, 8), device=DEV)
            pick = int(model(q, o).argmax().item())
        ok = int(pick == gi); correct += ok; tot += 1
        per_subj.setdefault(r["category"], [0, 0]); per_subj[r["category"]][0] += ok; per_subj[r["category"]][1] += 1
    acc = correct / max(1, tot)
    rep = {"benchmark": "MMLU via graph-MCQ judge (transfer)", "n": tot, "accuracy": round(acc, 4),
           "random": 0.25, "baseline_guess": 0.26,
           "per_subject": {k: round(v[0] / v[1], 3) for k, v in per_subj.items()},
           "reading": "acc > 0.26 = 커먼센스 판정기가 과학 MCQ로 전이(진짜 L1 레버). ~0.25 = 전이 안 됨."}
    print("RESULT eval_judge_mmlu", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
