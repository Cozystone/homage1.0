# -*- coding: utf-8 -*-
"""Align better, mine more, and stop the one kind of memorisation the first guard let through.

    python scripts/mine_constructions_v2.py

Owner: 정렬 개선해서 더 캐.

The first miner aligned 3,646 bones out of 60,000 rows — 6% — because it looked for each argument
VERBATIM. Four things were losing the other 94%, and each is a property of English rather than of this
corpus:

    inflection      the bone says `ratio`, the sentence says `ratios`
    modification    the bone says `Albedo`, the sentence says `surface albedo`; the bone says
                    `the office`, the sentence says `office`
    order           `anarchy, also called anarchism` puts the object first. That is not noise, it is a
                    DIFFERENT CONSTRUCTION, and mining it as `{o} ... {s}` doubles what one aligned
                    sentence can teach
    naming          the sentence uses a name the graph already knows is the same thing. The graph's own
                    `alias` edges are the fix, which is ATANOR using its own knowledge to read better

AND A NEW GUARD, because the last run showed exactly where the old one leaked. Promotion on TYPE
frequency stops an idiosyncratic string from entrenching, and it does NOT stop content that is itself
systematic:

    {s} is a type of {o}                  a construction
    {s} is a chemical {o}                 content — there are many chemicals
    {s} is the capital and largest {o}    content — there are many capitals

Both passed >= 12 distinct argument pairs. What separates them is that the content ones only ever take
one kind of argument: the objects of `is the capital and largest` are all `city`. So a construction
must not have its arguments concentrated on a single head word. That is derived from the pairs
themselves, needs no lexicon, and is measured below rather than asserted.

REGISTERED BEFORE RUNNING, against the committed previous rung (alignment 3,646; self-speech 74.0%;
human prose 32.0%):
    1  alignment rises well above 6% of scanned rows
    2  human prose rises above 32.0%
    3  self-speech does not fall more than 2 points below 74.0%
    4  the concentration guard removes the content templates named above and the gain SURVIVES it —
       if the gain only exists with them, the gain was memorisation
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
MINED = Path("data/realizer_struct/mined_frames.json")
OUT = Path("data/language/mined_constructions_v2.json")
FUNC = set("a an the of to in on at is are was were and or its his her their this that for by "
           "with from as it one also".split())
DET = ("the ", "a ", "an ")
MAX_MID = 5


def stem(w: str) -> str:
    """Enough morphology to match a plural to its singular. No lexicon, no lemmatiser."""
    w = w.lower().strip("'s")
    for suf, cut in (("ies", 3), ("es", 2), ("s", 1)):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[:-cut] + ("y" if suf == "ies" else "")
    return w


def variants(arg: str, aliases: dict) -> list:
    """The forms this argument may wear in a sentence: itself, its head, and what the graph calls it."""
    a = arg.strip()
    out = [a]
    low = a.lower()
    for d in DET:
        if low.startswith(d):
            out.append(a[len(d):])
    if len(a.split()) > 1:
        out.append(a.split()[-1])                       # the head noun carries the reference
    out += list(aliases.get(norm(a), ()))[:3]
    seen, uniq = set(), []
    for v in out:
        if v and norm(v) not in seen:
            seen.add(norm(v))
            uniq.append(v)
    return uniq


def find(text_words, text_stems, arg: str, aliases: dict):
    """Span of the best form of `arg` in the sentence, matched on stems. None if absent."""
    for v in variants(arg, aliases):
        vs = [stem(x) for x in norm(v).split()]
        if not vs:
            continue
        n = len(vs)
        for i in range(len(text_stems) - n + 1):
            if text_stems[i:i + n] == vs:
                return (i, i + n)
    return None


def mine(rows, aliases, cap_rows: int = 60000):
    seen = collections.defaultdict(set)
    aligned = scanned = 0
    for d in rows[:cap_rows]:
        text = (d.get("text") or "").strip()
        if not text or len(text.split()) > 40:
            continue
        scanned += 1
        w = norm(text).split()
        st = [stem(x) for x in w]
        for b in d.get("bones") or []:
            if len(b) < 3:
                continue
            s, r, o = (str(x).strip() for x in b)
            if not s or not o or norm(r) in FUNC:
                continue
            a, c = find(w, st, s, aliases), find(w, st, o, aliases)
            if not a or not c or a == c:
                continue
            if a[1] <= c[0]:
                mid, tmpl = " ".join(w[a[1]:c[0]]), "{s} %s {o}"
            elif c[1] <= a[0]:
                mid, tmpl = " ".join(w[c[1]:a[0]]), "{o} %s {s}"      # the reversed construction
            else:
                continue
            if len(mid.split()) > MAX_MID:
                continue
            aligned += 1
            seen[(r, tmpl % mid if mid else tmpl % "")].add((norm(s), norm(o)))
    return seen, aligned, scanned


def concentrated(pairs, limit: float = 0.5) -> bool:
    """True if one head word dominates the arguments — the signature of content, not construction."""
    heads = collections.Counter(o.split()[-1] for _s, o in pairs if o)
    if not heads:
        return True
    return heads.most_common(1)[0][1] / sum(heads.values()) > limit


def install(seen, min_types: int, guard: bool) -> int:
    added = 0
    for (rel, tmpl), pairs in seen.items():
        if len(pairs) < min_types:
            continue
        if guard and concentrated(pairs):
            continue
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
    out = {"label": label, "surfaces": len(inv.inv), "self_top1": top1 / max(tot, 1),
           "human": human / 250.0}
    print(f"  {label:<34} surfaces {out['surfaces']:>5}   self top-1 {out['self_top1']:>6.1%}"
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
    print(f"{len(rows)} pairs, vocabulary {len(vocab)}, alias table {len(aliases)} names\n")

    seen, aligned, scanned = mine(rows, aliases)
    print(f"aligned {aligned} bones over {scanned} sentences  "
          f"(previous miner: 3,646 over 60,000 rows = 6%)")
    print(f"candidates {len(seen)}  (previous: 2,567)\n")

    base = evaluate(rows, vocab, "hand-written frames only")
    results = [base]
    for thr, guard in ((12, False), (12, True), (6, True)):
        for rel in list(FRAMES):
            FRAMES[rel].pop("alts", None)
        n = install(seen, thr, guard)
        r = evaluate(rows, vocab,
                     f">= {thr} pairs{', concentration guard' if guard else ', no guard'}")
        r.update({"installed": n, "min_types": thr, "guard": guard})
        results.append(r)

    PREV_SELF, PREV_HUMAN = 0.740, 0.320
    best = max(results[1:], key=lambda x: x["human"])
    guarded = [r for r in results[1:] if r["guard"]]
    bg = max(guarded, key=lambda x: x["human"]) if guarded else None
    print(f"\n-> 1. alignment rose: {aligned} vs 3,646")
    print(f"-> 2. human prose above {PREV_HUMAN:.1%}: {best['human'] > PREV_HUMAN}  "
          f"({PREV_HUMAN:.1%} -> {best['human']:.1%})")
    print(f"-> 3. self-speech held: {best['self_top1'] >= PREV_SELF - 0.02}  "
          f"({PREV_SELF:.1%} -> {best['self_top1']:.1%})")
    if bg:
        print(f"-> 4. the gain SURVIVES the concentration guard: "
              f"{bg['human'] > PREV_HUMAN}  (guarded best {bg['human']:.1%})")

    for rel in list(FRAMES):
        FRAMES[rel].pop("alts", None)
    install(seen, 12, True)
    art = {}
    for rel, f in FRAMES.items():
        if f.get("alts"):
            art[rel] = {"template": f["tmpl"], "alts": list(f["alts"])}
    MINED.parent.mkdir(parents=True, exist_ok=True)
    MINED.write_text(json.dumps(art, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\npersisted {sum(len(v['alts']) for v in art.values())} constructions over "
          f"{len(art)} relations -> {MINED}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"aligned": aligned, "scanned": scanned,
                               "candidates": len(seen), "results": results},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
