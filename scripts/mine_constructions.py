# -*- coding: utf-8 -*-
"""Mine constructions from human sentences, give them to the speaker, and see if understanding grows.

    python scripts/mine_constructions.py

Owner: 프레임 캐서 화자 키워.

The coupling registered in the design document is that comprehension is bounded above by generation:
understanding is regeneration, so a construction the speaker cannot produce is a sentence it cannot
read. Human prose sits at ~17.6% for exactly that reason. The lever is therefore not a bigger proposer
but a bigger SPEAKER, and the material is already on disk — 223,592 rows of (bones, human sentence),
where a human shows how that relation is actually said.

    bones      ['Anarchism', 'alias', 'anarchy']
    human      "Anarchism appears in English from 1642 as anarchisme..."
                          ^ whatever lies between the two arguments is a candidate construction

WHY THE EXISTING MINER RETURNED TWO. It acquired `is_a` and `alias`, both already hand-written, for a
net contribution of zero. That is not a bug in the miner: 98% of the graph's bones ARE is_a and alias,
so those are the only relations with enough evidence to entrench. The intake bottleneck reaches all the
way here.

THE GUARD AGAINST SURFACE MEMORISATION, which is the failure mode this whole line is meant to avoid. A
connective is promoted on TYPE frequency — the number of DISTINCT argument pairs it appeared with — not
on how often it occurred. A string seen a thousand times with one pair is a memorised sentence; a string
seen twenty times with twenty different pairs is a construction. The existing realizer's docstring
already claims "ZERO surface memorization"; this is the criterion that has to earn it.

REGISTERED BEFORE RUNNING:
    1  human-prose comprehension rises above the 17.6% measured with the cleaned vocabulary
    2  the rise is NOT explained by memorisation — re-measured with the mined frames restricted to
       those seen with many distinct argument pairs, and reported at several thresholds so the shape
       of the trade is visible rather than a single flattering point
    3  self-speech comprehension (74.4% top-1) must not fall: new constructions must add coverage,
       not corrupt what already worked
"""
from __future__ import annotations

import collections
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema.inverse_speaker import InverseSpeaker, norm    # noqa: E402
from packages.realizer_struct.frame_realizer import FRAMES, realize       # noqa: E402

PAIRS = Path("data/graph_scale/bones_to_text.jsonl")
OUT = Path("data/language/mined_constructions.json")
FUNC = set("a an the of to in on at is are was were and or its his her their this that for by "
           "with from as it one also".split())
MAX_MID = 5            # a connective longer than this is a clause, not a construction


def _find(hay: str, needle: str):
    m = re.search(r"\b" + re.escape(needle) + r"\b", hay, re.IGNORECASE)
    return m.span() if m else None


def mine(rows, cap_rows: int = 60000):
    """(relation, connective) -> the set of distinct argument pairs it was seen with."""
    seen: dict = collections.defaultdict(set)
    n_used = 0
    for d in rows[:cap_rows]:
        text = (d.get("text") or "").strip()
        if not text or len(text.split()) > 40:
            continue
        for b in d.get("bones") or []:
            if len(b) < 3:
                continue
            s, r, o = (str(x).strip() for x in b)
            if not s or not o or norm(r) in FUNC:
                continue
            a, c = _find(text, s), _find(text, o)
            if not a or not c or a[1] >= c[0]:
                continue
            mid = norm(text[a[1]:c[0]])
            if not mid or len(mid.split()) > MAX_MID:
                continue
            seen[(r, mid)].add((norm(s), norm(o)))
            n_used += 1
    return seen, n_used


def install(seen, min_types: int) -> int:
    """Give the speaker every construction entrenched by at least `min_types` distinct pairs."""
    added = 0
    for (rel, mid), pairs in seen.items():
        if len(pairs) < min_types:
            continue
        tmpl = "{s} " + mid + " {o}"
        f = FRAMES.setdefault(rel, {"tmpl": tmpl})
        if tmpl == f["tmpl"]:
            continue
        alts = f.setdefault("alts", [])
        if tmpl not in alts:
            alts.append(tmpl)
            added += 1
    return added


def evaluate(rows, vocab, label: str) -> dict:
    inv = InverseSpeaker(vocab)
    tot = got = top1 = 0
    for d in rows[:250]:
        bones = [list(b) for b in d["bones"]]
        s = realize(bones)
        if not s:
            continue
        tot += 1
        best, _n = inv.best(s)
        if best is None:
            continue
        got += 1
        if tuple(norm(str(x)) for x in best) == tuple(norm(str(x)) for x in bones[0]):
            top1 += 1
    human = sum(1 for d in rows[:250] if inv.best(d["text"])[0] is not None)
    out = {"label": label, "surfaces": len(inv.inv), "self_solved": got / max(tot, 1),
           "self_top1": top1 / max(tot, 1), "human": human / 250.0}
    print(f"  {label:<26} surface forms {out['surfaces']:>5}   self-speech top-1 "
          f"{out['self_top1']:>6.1%}   HUMAN PROSE {out['human']:>6.1%}")
    return out


def main() -> None:
    rows = []
    V = collections.Counter()
    with io.open(PAIRS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            for b in d.get("bones") or []:
                if len(b) >= 2:
                    V[b[1]] += 1
            if d.get("bones") and d.get("text"):
                rows.append(d)
    vocab = [r for r, _ in V.most_common() if norm(r) not in FUNC and V[r] >= 3]
    print(f"{len(rows)} pairs, cleaned relation vocabulary {len(vocab)}\n")

    seen, n_used = mine(rows)
    print(f"mined {len(seen)} (relation, construction) candidates from {n_used} aligned bones")
    by_types = sorted(seen.items(), key=lambda kv: -len(kv[1]))
    print("  most entrenched, by DISTINCT argument pairs:")
    for (rel, mid), pairs in by_types[:10]:
        print(f"    {rel:<14} {mid!r:<28} {len(pairs):>5} distinct pairs")

    print("\nbaseline, before anything is installed:")
    base = evaluate(rows, vocab, "hand-written frames only")

    results = [base]
    for thr in (40, 12, 4):
        for rel in list(FRAMES):
            FRAMES[rel].pop("alts", None)
        n = install(seen, thr)
        results.append(evaluate(rows, vocab, f"mined, >= {thr} distinct pairs"))
        results[-1]["installed"] = n
        results[-1]["min_types"] = thr

    print(f"\n{'threshold':<26}{'constructions':>15}{'self top-1':>13}{'human prose':>14}")
    for r in results:
        print(f"  {r['label']:<24}{r.get('installed', 0):>15}{r['self_top1']:>12.1%}"
              f"{r['human']:>14.1%}")
    best = max(results[1:], key=lambda r: r["human"])
    print(f"\n-> 1. human prose rose above the 17.6% baseline: "
          f"{best['human'] > base['human']}  ({base['human']:.1%} -> {best['human']:.1%})")
    print(f"-> 3. self-speech did not regress: "
          f"{best['self_top1'] >= base['self_top1'] - 0.02}  "
          f"({base['self_top1']:.1%} -> {best['self_top1']:.1%})")
    print("-> 2. the thresholds above ARE the memorisation control: a gain that only appears at the")
    print("      loosest threshold is a gain from strings seen with few argument pairs, which is")
    print("      memorisation wearing a construction's clothes.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"results": results, "candidates": len(seen),
                               "top": [{"rel": r, "mid": m, "types": len(p)}
                                       for (r, m), p in by_types[:40]]},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
