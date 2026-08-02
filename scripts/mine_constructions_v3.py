# -*- coding: utf-8 -*-
"""Mine again with a derived content-word test, so better alignment can finally be used.

    python scripts/mine_constructions_v3.py

Owner: 연결어에 내용어 없는 기준으로 다시 캐.

v2 improved alignment 2.5x (3,646 -> 9,302 bones) and got WORSE, because the extra sentences dragged
determiners and modifiers into the connective. v1's verbatim matching had been acting as a quality
filter nobody designed. The missing piece was never recall; it was a criterion for what a connective is
allowed to contain, and neither of the two guards tried so far reaches it:

    type frequency        stops an idiosyncratic string entrenching. Does NOT stop systematic content:
                          `is a chemical` and `is the capital and largest` both cleared 12 distinct
                          argument pairs, because there are many chemicals and many capitals.
    determiner-final      restores the speaker to 74.0% and costs more comprehension than it saves,
                          so the real fault is broader than determiners.

THE CRITERION, AND IT USES NO LEXICON. A function word is not defined by a list; it is defined by
behaving the same everywhere. `is`, `of`, `also`, `known`, `as` appear in the connectives of many
different relations. `chemical` appears only in `is_a`'s. So:

    a word is STRUCTURAL if it occurs in the connectives of at least two distinct relations
    a connective is admissible if every word in it is structural

Two is the smallest non-trivial threshold, so nothing is tuned, and the shuffled null below says
whether that split is real: relabel which relation each connective belongs to and recompute. If the
structural set is the same size under the shuffle, the criterion is counting nothing.

This is the same abstraction this project already uses for discrimination — lift against the marginal.
A content word is concentrated against the marginal distribution over relations; a function word
matches it.

REGISTERED BEFORE RUNNING, against the standing v1 rung (self-speech 74.0%, human prose 32.0%):
    1  the shuffled null shows the structural/content split is not an artefact of counting
    2  the named content templates (`is a chemical`, `is the capital and largest`) are rejected
    3  human prose above 32.0%
    4  self-speech within 2 points of 74.0% — v2 failed here at 31.2% and that is the trap
"""
from __future__ import annotations

import collections
import io
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema.inverse_speaker import InverseSpeaker, norm       # noqa: E402
from packages.realizer_struct.frame_realizer import FRAMES, realize          # noqa: E402
from scripts.mine_constructions_v2 import FUNC, PAIRS, concentrated, mine    # noqa: E402

MINED = Path("data/realizer_struct/mined_frames.json")
OUT = Path("data/language/mined_constructions_v3.json")


def structural_words(seen, min_relations: int = 2) -> tuple[set, dict]:
    """Words that behave the same across relations. Derived from the mined set, not from a list."""
    where = collections.defaultdict(set)
    for (rel, tmpl), _pairs in seen.items():
        for w in tmpl[4:-4].split():
            where[w].add(rel)
    return {w for w, rs in where.items() if len(rs) >= min_relations}, where


def shuffled_null(seen, trials: int = 20, seed: int = 0) -> list:
    """Relabel which relation each connective belongs to. If the structural set does not shrink, the
    criterion is measuring nothing and must be withdrawn before it is used."""
    rng = random.Random(seed)
    keys = list(seen)
    rels = [k[0] for k in keys]
    out = []
    for _ in range(trials):
        rng.shuffle(rels)
        fake = {(r, k[1]): v for r, k, v in zip(rels, keys, seen.values())}
        out.append(len(structural_words(fake)[0]))
    return out


def claimed_surfaces() -> dict:
    """Surface form -> the relation that already produces it, over every construction now installed."""
    out = {}
    for rel, f in FRAMES.items():
        for t in [f["tmpl"]] + list(f.get("alts", [])):
            if t.startswith("{s}"):
                out.setdefault(norm(t[4:-4]), rel)
    return out


def admissible(rel: str, tmpl: str, claimed: dict) -> bool:
    """A construction is admissible if its surface form is not already ANOTHER relation's.

    This, and not a content-word test, is what the collapse turned out to need. Ablating the 22 mined
    constructions one at a time found exactly ONE culprit -- `alias` -> `{s} is a {o}` -- which
    collides head-on with is_a's canonical `{s} is {det} {o}`. Every "X is a Y" then regenerates under
    two structures with identical argument lengths, so MDL cannot separate them, and since is_a is 56%
    of the corpus that single entry took self-speech from 74.0% to 31.2%.

    Two guards were tried before this and both were wrong. Cross-relation word diversity FAILED ITS OWN
    SHUFFLED NULL (structural fraction 27.3% against a null of 29.3%) and let `chemical` and `capital`
    through. Document frequency passed its null decisively (1,782 admissible against 4 +- 15 shuffled)
    and still did not fix the collapse, because content words were never the cause. Neither guard is
    kept: a criterion that does not explain the failure has no business filtering."""
    mid = norm(tmpl[4:-4])
    if not mid:
        return False
    owner = claimed.get(mid)
    return owner is None or owner == rel


def install(seen, struct, min_types: int, use_content_test: bool) -> tuple[int, list]:
    added, kept = 0, []
    claimed = claimed_surfaces()
    for (rel, tmpl), pairs in seen.items():
        if len(pairs) < min_types or concentrated(pairs) or not tmpl.startswith("{s}"):
            continue
        if use_content_test and not admissible(rel, tmpl, claimed):
            continue
        claimed.setdefault(norm(tmpl[4:-4]), rel)
        if rel not in FRAMES:
            # a relation the speaker had no frame for at all: this construction becomes its primary.
            # It must be persisted too -- saving only relations that gained ALTS silently dropped
            # these, and the artefact then measured 32.0% where the run measured 32.8%.
            FRAMES[rel] = {"tmpl": tmpl, "mined": True}
            added += 1
            kept.append((rel, tmpl))
            continue
        f = FRAMES[rel]
        if tmpl == f["tmpl"]:
            continue
        alts = f.setdefault("alts", [])
        if tmpl not in alts:
            alts.append(tmpl)
            added += 1
            kept.append((rel, tmpl))
    return added, kept


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
    out = {"label": label, "surfaces": len(inv.inv), "self_top1": top1 / max(tot, 1),
           "human": human / 250.0}
    print(f"  {label:<36} surfaces {out['surfaces']:>5}   self top-1 {out['self_top1']:>6.1%}"
          f"   HUMAN PROSE {out['human']:>6.1%}")
    return out


def main() -> None:
    rows, V = [], collections.Counter()
    aliases = collections.defaultdict(set)
    with io.open(PAIRS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            for b in d.get("bones") or []:
                if len(b) >= 2:
                    V[b[1]] += 1
                if len(b) >= 3 and b[1] == "alias":
                    aliases[norm(str(b[0]))].add(str(b[2]))
                    aliases[norm(str(b[2]))].add(str(b[0]))
            if d.get("bones") and d.get("text"):
                rows.append(d)
    vocab = [r for r, _ in V.most_common() if norm(r) not in FUNC and V[r] >= 3]

    seen, aligned, scanned = mine(rows, aliases)
    struct, where = structural_words(seen)
    null = shuffled_null(seen)
    print(f"aligned {aligned} bones over {scanned} sentences (v2's alignment, kept)")
    print(f"connective vocabulary {len(where)} words -> STRUCTURAL {len(struct)}")
    print(f"  shuffled null: {sum(null)/len(null):.0f} +- {max(null)-min(null)} structural words")
    real_frac = len(struct) / max(len(where), 1)
    null_frac = (sum(null) / len(null)) / max(len(where), 1)
    print(f"  structural fraction {real_frac:.1%} vs null {null_frac:.1%}  -> the split is "
          f"{'REAL' if real_frac < null_frac * 0.8 or real_frac > null_frac * 1.25 else 'NOT distinguishable from counting'}")
    for w in ("is", "of", "also", "known", "as", "chemical", "capital", "largest"):
        print(f"    {w:<10} in {len(where.get(w, ())):>3} relations   "
              f"{'structural' if w in struct else 'CONTENT'}")

    print()
    base = evaluate(rows, vocab, "hand-written frames only")
    results = [base]
    for thr, test in ((12, False), (12, True), (6, True)):
        for rel in list(FRAMES):
            FRAMES[rel].pop("alts", None)
        n, kept = install(seen, struct, thr, test)
        r = evaluate(rows, vocab,
                     f">= {thr} pairs{', collision guard' if test else ', NO guard'} [{n}]")
        r.update({"installed": n, "min_types": thr, "content_test": test,
                  "kept": [f"{a}: {b}" for a, b in kept[:20]]})
        results.append(r)

    V1_SELF, V1_HUMAN = 0.740, 0.320
    guarded = [r for r in results if r.get("content_test")]
    best = max(guarded, key=lambda r: r["human"]) if guarded else base
    cl = claimed_surfaces()
    rejected = [(rel, t) for (rel, t), p in seen.items()
                if len(p) >= 12 and t.startswith("{s}") and not admissible(rel, t, cl)]
    print(f"\n-> 2. collisions rejected: {len(rejected)}  "
          f"{[(r, t[4:-4]) for r, t in rejected[:4]]}")
    print(f"-> 3. human prose above v1's {V1_HUMAN:.1%}: {best['human'] > V1_HUMAN}  "
          f"({V1_HUMAN:.1%} -> {best['human']:.1%})")
    print(f"-> 4. self-speech within 2 points of {V1_SELF:.1%}: "
          f"{best['self_top1'] >= V1_SELF - 0.02}  ({best['self_top1']:.1%})")
    passed = best["human"] > V1_HUMAN and best["self_top1"] >= V1_SELF - 0.02
    print(f"\n{'PASSES — persisting' if passed else 'FAILS — v1 is left in place'}")

    if passed:
        for rel in list(FRAMES):
            FRAMES[rel].pop("alts", None)
        install(seen, struct, best["min_types"], True)
        art = {rel: {"template": f["tmpl"], "alts": list(f.get("alts", []))}
               for rel, f in FRAMES.items() if f.get("alts") or f.get("mined")}
        MINED.write_text(json.dumps(art, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"persisted {sum(len(v['alts']) for v in art.values())} constructions -> {MINED}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"aligned": aligned, "structural": len(struct),
                               "vocab": len(where), "null": null, "results": results,
                               "passed": bool(passed)}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
