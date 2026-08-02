# -*- coding: utf-8 -*-
"""Score discrimination.discriminate() against the SEALED factual-MCQ battery
(build_discrimination_battery.py) — the C3 () gate, dev vs holdout.

Reports, per split:
 answered — GROUNDED (the graph backed a single choice), i.e. coverage.
 answered_acc — of the GROUNDED items, fraction correct. MUST beat 0.25 (4-way guess).
 overall_acc — correct / n (an ABSTAIN counts as not-correct); the honest bottom line.
 abstain_rate — GROUNDED is not forced; abstaining is allowed but caps overall_acc.

The gate (declared BEFORE the run, so it can fail): answered_acc >= 0.90 AND answered/n >= 0.60 AND
the dev↔holdout answered_acc gap <= 0.05 (a bigger gap means the battery, not the engine, is being
fit). This is a store-lookup consistency gate: the correct answer IS a store fact, so the engine —
which re-derives from the same store — should route and match it; failures are routing/label-match
regressions. Run: python scripts/eval_discrimination_battery.py
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

from packages.graph_scale.triple_store import TripleStore          # noqa: E402
from packages.reasoning_vm.discrimination import discriminate      # noqa: E402

_Q = re.compile(r"^Q\d+$")
_ST = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full",
                  dict_backend="sharded", write_src=False)
_QCACHE: dict[str, str] = {}


def _qlabel(qid: str) -> str:
    if qid in _QCACHE:
        return _QCACHE[qid]
    lab = next((o for (s, p, o) in _ST.facts_about(qid, limit=6) if p == "qlabel"), qid)
    _QCACHE[qid] = lab
    return lab


def facts_about(subject: str):
    out = []
    for (s, p, o) in _ST.facts_about(subject, limit=40):
        out.append((s, p, _qlabel(o) if _Q.match(str(o)) else o))
    return out


_PREFIX = sys.argv[1] if len(sys.argv) > 1 else "seal_discrimination"


def score(split: str) -> dict:
    path = REPO / "data" / "eval" / f"{_PREFIX}_{split}.jsonl"
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]
    n = answered = correct = 0
    by_rel: dict[str, list[int]] = {}
    misses: list[str] = []
    for it in rows:
        n += 1
        v = discriminate(it["stem"], it["choices"], facts_about)
        rel = it.get("relation") or it.get("chain") or "?"
        by_rel.setdefault(rel, [0, 0, 0])          # [n, answered, correct]
        by_rel[rel][0] += 1
        if v.status == "GROUNDED":
            answered += 1
            by_rel[rel][1] += 1
            hit = v.choice_key == it["gold"]
            correct += int(hit)
            by_rel[rel][2] += int(hit)
            if not hit and len(misses) < 8:
                misses.append(f"{rel}: {it['stem'][:40]} → picked {v.choice_key} want {it['gold']}")
    ans_acc = correct / answered if answered else 0.0
    return {"split": split, "n": n, "answered": answered, "correct": correct,
            "answered_acc": round(ans_acc, 4), "overall_acc": round(correct / n if n else 0, 4),
            "coverage": round(answered / n if n else 0, 4),
            "by_relation": {r: {"n": a[0], "answered": a[1], "acc_of_answered":
                                round(a[2] / a[1], 3) if a[1] else 0.0} for r, a in by_rel.items()},
            "_misses": misses}


def main() -> int:
    print("=== C3 discrimination — sealed battery (live world-pack store) ===\n", flush=True)
    res = {}
    for split in ("dev", "holdout"):
        s = score(split)
        res[split] = s
        print(f"[{split}] n={s['n']} answered={s['answered']} coverage={s['coverage']} "
              f"answered_acc={s['answered_acc']} overall_acc={s['overall_acc']}")
        for r, d in s["by_relation"].items():
            print(f"    {r:14} n={d['n']:4} answered={d['answered']:4} acc={d['acc_of_answered']}")
        if s["_misses"]:
            print("    sample misses:")
            for m in s["_misses"]:
                print(f"      - {m}")
        print()
    gap = abs(res["dev"]["answered_acc"] - res["holdout"]["answered_acc"])
    gate = (res["holdout"]["answered_acc"] >= 0.90 and res["holdout"]["coverage"] >= 0.60
            and gap <= 0.05)
    print(f"=== dev↔holdout answered_acc gap = {round(gap, 4)} (<=0.05 = not memorised)")
    print(f"=== C3 SEALED GATE (holdout answered_acc>=0.90, coverage>=0.60, gap<=0.05): "
          f"{'PASS' if gate else 'not yet'}")
    (REPO / "reports").mkdir(exist_ok=True)
    (REPO / "reports" / "discrimination_seal.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
