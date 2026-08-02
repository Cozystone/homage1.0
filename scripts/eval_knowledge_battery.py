# -*- coding: utf-8 -*-
"""Score the resolution path (store → alias → qid-label sidecar → supplementary overlay) against the
SEALED C2 knowledge holdout — the ①/②-grade gate. Reports, per split: coverage (answered),
correctness (of answered), and HALLUCINATION (control subjects that were answered instead of
abstaining — must be 0). Gate declared before the run: holdout correctness ≥ 0.90, controls 100%
abstain, dev↔holdout correctness gap ≤ 0.05. Run: python scripts/eval_knowledge_battery.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np                                                     # noqa: E402
from packages.graph_scale.triple_store import TripleStore             # noqa: E402
from packages.graph_scale.qid_labels import resolve as _sidecar       # noqa: E402
from packages.graph_scale.supplementary_facts import facts_for as _supp  # noqa: E402

_Q = re.compile(r"^Q\d+$")
_ST = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full", dict_backend="sharded", write_src=False)
_COLS = _ST.open_columns()
_S, _P, _O = _COLS["s"], _COLS["p"], _COLS["o"]
_AID = _ST.terms.lookup("alias")
_QC: dict[str, str] = {}


def _qlabel(o: str) -> str:
    if not _Q.match(str(o)):
        return o
    if o in _QC:
        return _QC[o]
    v = next((x for (_s, p, x) in _ST.facts_about(o, limit=8) if p == "qlabel"), o)
    if _Q.match(str(v)):
        v = _sidecar(v)
    _QC[o] = v
    return v


def _rev_alias(subj: str) -> list[str]:
    sid = _ST.terms.lookup(subj)
    if sid is None or _AID is None:
        return []
    m = (_P == _AID) & (_O == sid)
    return [_ST.terms.term(int(_S[i])) for i in np.nonzero(m)[0][:6].tolist()]


def resolved(subj: str, rel: str) -> list[str]:
    seen = {subj}
    fx = list(_ST.facts_about(subj, limit=60))
    for a in ({o for (_s, p, o) in fx if p == "alias"} | set(_rev_alias(subj))):
        if a not in seen and not _Q.match(str(a)):
            seen.add(a)
            fx += _ST.facts_about(a, limit=60)
    vals = [_qlabel(o) for (_s, p, o) in fx if p == rel]
    for a in seen:
        for row in _supp(a, rel):
            vals.extend(row["object"])
    return [v for v in vals if v and not _Q.match(str(v))]


def _norm(s: str) -> str:
    return re.sub(r"[\s.,'\"()]+", "", str(s).lower())


def score(split: str) -> dict:
    rows = [json.loads(l) for l in (REPO / "data" / "eval" / f"seal_knowledge_{split}.jsonl").open(encoding="utf-8")]
    n = ans = correct = halluc = ctrl = ctrl_ok = 0
    byrel: dict[str, list[int]] = {}
    misses: list[str] = []
    for it in rows:
        vals = resolved(it["subject"], it["relation"])
        if it["control"]:
            ctrl += 1
            if vals:
                halluc += 1
                misses.append(f"HALLUCINATION {it['subject']} -{it['relation']}-> {vals[:2]}")
            else:
                ctrl_ok += 1
            continue
        n += 1
        d = byrel.setdefault(it["relation"], [0, 0])
        d[0] += 1
        if not vals:
            if len(misses) < 8:
                misses.append(f"MISS {it['subject']} -{it['relation']}-> ? want {it['accept'][:1]}")
            continue
        ans += 1
        acc = {_norm(a) for a in it["accept"]}
        if any(any(na in _norm(v) or _norm(v) in na for na in acc) for v in vals):
            correct += 1
            d[1] += 1
        elif len(misses) < 8:
            misses.append(f"WRONG {it['subject']} -{it['relation']}-> {vals[:2]} want {it['accept'][:1]}")
    return {"split": split, "n": n, "answered": ans, "correct": correct,
            "coverage": round(ans / n, 4) if n else 0, "correctness": round(correct / n, 4) if n else 0,
            "controls": ctrl, "controls_abstained": ctrl_ok, "hallucinations": halluc,
            "by_relation": {r: round(a[1] / a[0], 3) for r, a in byrel.items()}, "_misses": misses[:8]}


def main() -> int:
    print("=== C2 sealed knowledge holdout (store + alias + qid-sidecar + overlay) ===\n", flush=True)
    res = {}
    for split in ("dev", "holdout"):
        s = score(split)
        res[split] = s
        print(f"[{split}] n={s['n']} coverage={s['coverage']} correctness={s['correctness']} "
              f"controls_abstain={s['controls_abstained']}/{s['controls']} halluc={s['hallucinations']}")
        print(f"    by_relation={s['by_relation']}")
        for m in s["_misses"]:
            print(f"      - {m}")
    gap = abs(res["dev"]["correctness"] - res["holdout"]["correctness"])
    gate = (res["holdout"]["correctness"] >= 0.90 and res["holdout"]["hallucinations"] == 0
            and res["dev"]["hallucinations"] == 0 and gap <= 0.05)
    print(f"\n=== dev↔holdout correctness gap = {round(gap, 4)}")
    print(f"=== C2 SEALED KNOWLEDGE GATE (holdout correctness>=0.90, hallucinations==0, gap<=0.05): "
          f"{'PASS' if gate else 'not yet'}")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
