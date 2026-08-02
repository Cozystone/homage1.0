# -*- coding: utf-8 -*-
"""R1 — can the speaker read back what it just said? The floor of understanding-by-regeneration.

    python scripts/understand_by_regeneration_r1.py

Owner: 인간도 자신이 말하면서 그 내용을 바탕으로 또 이해를 하는데 atanor는 말할줄만 알았던거니까.

Today's audit proved the asymmetry at code level: `realize()` will say ANY relation handed to it,
action verbs included, while the comprehension path knows 31 definitional verbs and cannot represent
an imperative at all. So the inward arc is missing, not limited — and if the system can go structure →
sentence, comprehension is that organ run backwards under a verifier.

    propose candidate structures  ->  regenerate each  ->  keep only what reproduces the sentence

Nothing is learned in this rung. The proposer here is EXHAUSTIVE, deliberately: R1 is not asking
whether a proposer can be trained, it is asking whether the inverse EXISTS at all. Two things can kill
the method before any training is worth doing, and both are measured here:

    recoverability  does the true structure regenerate its own sentence? If `realize` is lossy in a way
                    that no candidate reproduces, there is nothing to invert.
    uniqueness      does ONLY the true structure regenerate it? If many structures produce the same
                    string, the verifier cannot pick, and comprehension is ambiguous by construction.
                    This is the number that decides whether the method is sound, and it is the one I
                    would not have thought to look at if the doctrine did not require abstention over
                    a guess.

THIS RUNG IS A FLOOR AND NOT AN ACHIEVEMENT. Reading back one's own output is the easiest case there
is. So the human-written text from the SAME rows is run through the identical machinery in the same
pass — that is the real task, it is expected to fail here, and printing the two side by side is what
keeps the floor from being reported as a result.

Doctrine: the verifier is exact string comparison after normalisation. A structure that does not
regenerate the sentence is REJECTED, never approximated. Understanding is regeneration or abstention.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.realizer_struct.frame_realizer import realize   # noqa: E402

PAIRS = Path("data/graph_scale/bones_to_text.jsonl")
OUT = Path("data/language/r1_regeneration.json")
_WS = re.compile(r"[^a-z0-9 ]+")


def norm(s: str) -> str:
    """The verifier's notion of 'the same sentence'. Case and punctuation only — nothing semantic."""
    return " ".join(_WS.sub(" ", (s or "").lower()).split())


def propose(sentence: str, max_len: int = 14):
    """Every contiguous three-way split of the sentence into subject, relation, object.

    Exhaustive on purpose. A learned proposer replaces exactly this function in R2 and nothing else,
    which is what makes R1 a measurement of the METHOD rather than of a model."""
    w = sentence.split()
    if not (2 < len(w) <= max_len):
        return []
    out = []
    for i in range(1, len(w) - 1):
        for j in range(i + 1, len(w)):
            out.append([w[:i], w[i:j], w[j:]])
    return [[" ".join(a), " ".join(b), " ".join(c)] for a, b, c in out]


def recover(sentence: str):
    """Structures that REGENERATE this sentence. Zero of them is an abstention, not a failure to try."""
    target = norm(sentence)
    hits = []
    for cand in propose(sentence):
        try:
            if norm(realize([cand])) == target:
                hits.append(cand)
        except Exception:
            continue
    return hits


def main() -> None:
    rows = []
    with io.open(PAIRS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("bones") and d.get("text"):
                rows.append(d)
            if len(rows) >= 400:
                break
    print(f"{len(rows)} rows from {PAIRS}\n")

    said, human = [], []
    for d in rows:
        bones = [list(b) for b in d["bones"]]
        s = realize(bones)                    # what ATANOR itself would say for this structure
        if s:
            hits = recover(s)
            said.append({"bones": bones, "said": s, "n_hits": len(hits),
                         "recovered": any(norm(" ".join(h)) == norm(" ".join(map(str, bones[0])))
                                          for h in hits),
                         "any": bool(hits)})
        h = recover(d["text"])
        human.append({"text": d["text"][:90], "n_hits": len(h), "any": bool(h)})

    n = len(said)
    got = sum(x["any"] for x in said)
    exact = sum(x["recovered"] for x in said)
    uniq = sum(x["n_hits"] == 1 for x in said if x["any"])
    amb = [x["n_hits"] for x in said if x["any"]]
    hn = len(human)
    hgot = sum(x["any"] for x in human)

    print("R1a  ITS OWN SPEECH — the floor. Reading back what it just said.")
    print(f"  sentences it produced                     {n}")
    print(f"  some structure regenerates the sentence   {got}/{n} = {got / max(n,1):.1%}")
    print(f"  and it is the TRUE structure              {exact}/{n} = {exact / max(n,1):.1%}")
    print(f"  exactly ONE structure regenerates it      {uniq}/{max(got,1)} = {uniq / max(got,1):.1%}"
          f"   <- ambiguity; a verifier cannot choose among ties")
    if amb:
        print(f"  candidates per solved sentence            mean {sum(amb)/len(amb):.2f}, "
              f"max {max(amb)}")
    print(f"  abstained                                 {n - got}/{n} = {(n-got)/max(n,1):.1%}")

    print("\nR1b  HUMAN-WRITTEN TEXT from the same rows — the real task, same machinery, same pass.")
    print(f"  sentences                                 {hn}")
    print(f"  some structure regenerates the sentence   {hgot}/{hn} = {hgot / max(hn,1):.1%}")
    print(f"  abstained                                 {hn - hgot}/{hn} = {(hn-hgot)/max(hn,1):.1%}")

    print("\nWHAT THIS DOES AND DOES NOT ESTABLISH")
    if got / max(n, 1) < 0.5:
        print("  The inverse does NOT exist even on its own output. The method is wrong as stated and")
        print("  R2 must not be built on it; the realizer is lossy in a way regeneration cannot undo.")
    elif uniq / max(got, 1) < 0.5:
        print("  The inverse exists but is AMBIGUOUS: several structures produce the same sentence, so")
        print("  the exact verifier cannot pick one. The proposer cannot fix this — a ranking or a")
        print("  richer structure has to, and that is a change to the design, not to a model.")
    else:
        print("  The inverse exists and is mostly unique on self-generated text. That licenses R2 and")
        print("  NOTHING MORE: reading back one's own output is the easiest case, and R1b is the gap.")
    print(f"  The gap R2 has to close: {got/max(n,1):.1%} on its own speech vs "
          f"{hgot/max(hn,1):.1%} on human prose.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"n": n, "self_any": got, "self_exact": exact, "self_unique": uniq,
                               "mean_candidates": (sum(amb) / len(amb)) if amb else None,
                               "human_n": hn, "human_any": hgot,
                               "examples": said[:8], "human_examples": human[:8]},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
