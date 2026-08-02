# -*- coding: utf-8 -*-
"""Score semantic_frame.encode against the SEALED C1 comprehension holdout.

Reports per-slot accuracy for each split and the dev↔holdout gap. Because the compositional layer
is a lexical pattern set and the battery deliberately includes unseen realisations, a LOW holdout
number here is the honest signal that the patterns have hit their ceiling and a learned act
classifier is the next step — not something to paper over.

Gate declared before the run: holdout overall >= 0.90 AND gap <= 0.05.
Run:  python scripts/eval_c1_battery.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.graph_scale.semantic_frame import encode  # noqa: E402

SLOTS = ["act", "modality", "polarity", "refers_to_prior", "self_directed"]


def score(split: str) -> dict:
    path = REPO / "data" / "eval" / f"seal_c1_{split}.jsonl"
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]
    per: dict[str, list[int]] = {s: [0, 0] for s in SLOTS}
    misses: list[str] = []
    for it in rows:
        f = encode(it["utterance"])
        for s, want in it["gold"].items():
            got = getattr(f, s, None)
            per[s][0] += 1
            if got == want:
                per[s][1] += 1
            elif len(misses) < 12:
                misses.append(f"{it['utterance'][:38]!r:42} {s}: got {got!r} want {want!r}")
    tot = sum(v[0] for v in per.values())
    ok = sum(v[1] for v in per.values())
    return {"split": split, "n": len(rows), "checked": tot, "correct": ok,
            "overall": round(ok / tot, 4) if tot else 0.0,
            "by_slot": {s: (round(v[1] / v[0], 3) if v[0] else None) for s, v in per.items()},
            "_misses": misses}


def main() -> int:
    print("=== C1 sealed comprehension holdout (semantic_frame.encode, English) ===\n")
    res = {}
    for split in ("dev", "holdout"):
        s = score(split)
        res[split] = s
        print(f"[{split}] n={s['n']} slots_checked={s['checked']} overall={s['overall']}")
        print(f"    by_slot={s['by_slot']}")
        for m in s["_misses"]:
            print(f"      - {m}")
        print()
    gap = abs(res["dev"]["overall"] - res["holdout"]["overall"])
    gate = res["holdout"]["overall"] >= 0.90 and gap <= 0.05
    print(f"=== dev↔holdout gap = {round(gap, 4)}")
    print(f"=== C1 SEALED GATE (holdout overall>=0.90, gap<=0.05): {'PASS' if gate else 'not yet'}")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
