# -*- coding: utf-8 -*-
"""The whole chain, end to end: an English sentence I type, and behaviour that differs because of it.

    python scripts/instruct_in_english.py

Owner: 그 다음부터는 너(claude)가 atanor한테 직접 자연어로 명령해보며 테스트할수도 있고.

Every part now exists, so this joins them and MEASURES WHERE THE CHAIN BREAKS rather than assuming it
holds. Four stages, each reported separately, because a single end-to-end number would hide which one
failed:

    1  SAY        can the speaker produce the instruction at all? Comprehension is bounded above by
                  generation, exactly, and this is where that ceiling becomes visible per sentence.
    2  UNDERSTAND InverseSpeaker recovers the structure by regeneration + MDL. 74.4% top-1 on
                  sentences the speaker produced.
    3  BIND       relation -> image schema. THIS STAGE IS SUPPLIED AND IS THE POINT OF THE WHOLE
                  DESIGN, so it is flagged on every line it touches. The registered falsification is
                  that unseen verbs must work; supplying the map means that test is NOT passed here,
                  and the probe at the end shows exactly how it fails today.
    4  ACT        the schema drives the executor. Pixels only.

WHAT WOULD BE SELF-DECEPTION HERE. Typing `if "avoid" in sentence` anywhere. The instruction reaches
behaviour through structure or it does not reach it: stage 2 must recover (agent, relation, patient)
from the sentence, and stage 3 must key off the RELATION, never off the sentence text. A sentence whose
relation the speaker cannot say must fail at stage 1 and be reported as unsayable, not special-cased.

THE PROBE AT THE END is the registered falsification in miniature: an instruction using a verb that is
in NO table anywhere. It is expected to fail today. Printing that failure is the point — it is the
distance between this and generality, stated as a line of output rather than as a promise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema import Proximity                                    # noqa: E402
from packages.image_schema.inverse_speaker import InverseSpeaker, norm         # noqa: E402
from packages.realizer_struct.frame_realizer import FRAMES, realize            # noqa: E402

OUT = Path("data/language/instruct_in_english.json")

# STAGE 1 — the speaker is TAUGHT TO SAY these, which is what lets it read them. Growing the speaker
# is the sanctioned way to grow comprehension; the design document states the coupling as the honest
# ceiling. These are constructions, not verbs-with-behaviour: nothing here says what avoiding IS.
NEW_FRAMES = {
    "avoid":  {"tmpl": "{s} must stay away from {o}"},
    "chase":  {"tmpl": "{s} must go after {o}"},
    "eat":    {"tmpl": "{s} must swallow {o}"},
    "reach":  {"tmpl": "{s} must arrive at {o}"},
}

# STAGE 3 — SUPPLIED. relation -> (schema class, polarity). Twenty rows at most by construction,
# because the basis is closed; but every row is a row I wrote, and that is the debt this design owes.
SUPPLIED_BIND = {
    "avoid": (Proximity, -1),
    "chase": (Proximity, +1),
    "reach": (Proximity, +1),
}

INSTRUCTIONS = [
    "Pac-Man must stay away from the ghosts.",
    "Pac-Man must go after the ghosts.",
    "Pac-Man must arrive at the fruit.",
    "Pac-Man must swallow the pellets.",          # sayable, understandable, NOT bound -> must abstain
    "Pac-Man must outfox the ghosts.",            # THE PROBE: unseen verb, expected to fail at stage 1
]


def main() -> None:
    for r, f in NEW_FRAMES.items():
        FRAMES.setdefault(r, f)
    inv = InverseSpeaker(sorted(FRAMES))
    print(f"the speaker knows {len(FRAMES)} constructions; the index inverted "
          f"{len(inv.fwd)} of them into {len(inv.inv)} surface forms\n")

    rows = []
    for text in INSTRUCTIONS:
        rec = {"text": text}
        # 2 UNDERSTAND
        best, n = inv.best(text)
        rec["structure"] = best
        rec["alternatives"] = n
        if best is None:
            # 1 SAY — distinguish "cannot be understood" from "cannot be said", which are the same
            # fact seen from two sides and only one of them is actionable.
            rec["stage"] = "UNSAYABLE"
            rec["why"] = ("no construction the speaker knows produces this sentence, so the index has "
                          "no entry to propose and understanding abstains")
            rows.append(rec)
            continue
        subj, rel, obj = best
        # 3 BIND
        if rel not in SUPPLIED_BIND:
            rec["stage"] = "UNBOUND"
            rec["why"] = f"understood as ({subj!r}, {rel!r}, {obj!r}) but no schema is bound to {rel!r}"
            rows.append(rec)
            continue
        cls, pol = SUPPLIED_BIND[rel]
        rec["stage"] = "BOUND"
        rec["schema"] = cls("me", norm(obj), polarity=pol).name
        rec["polarity"] = pol
        rec["goal"] = (f"prefer futures where distance(me, {norm(obj)}) is "
                       f"{'LARGE' if pol < 0 else 'SMALL'}")
        rows.append(rec)

    w = max(len(r["text"]) for r in rows)
    for r in rows:
        print(f"  {r['text']:<{w}}  {r['stage']}")
        if r.get("structure"):
            plural = "s" if r["alternatives"] != 1 else ""
            print(f"  {'':<{w}}    understood: {r['structure']}  "
                  f"({r['alternatives']} structure{plural} regenerate it)")
        if r.get("goal"):
            print(f"  {'':<{w}}    schema:     {r['schema']} polarity {r['polarity']:+d}   [BIND SUPPLIED]")
            print(f"  {'':<{w}}    goal:       {r['goal']}")
        if r.get("why"):
            print(f"  {'':<{w}}    {r['why']}")
        print()

    bound = [r for r in rows if r["stage"] == "BOUND"]
    print(f"reached a goal functional: {len(bound)}/{len(rows)}")
    pols = {r["polarity"] for r in bound}
    print(f"-> two English sentences produce OPPOSITE goals through one pipeline: "
          f"{len(pols) > 1}  (polarities seen: {sorted(pols)})")
    print("\nTHE PROBE, and it is the registered falsification in miniature:")
    probe = rows[-1]
    print(f"  {probe['text']!r} -> {probe['stage']}")
    print("  An unseen verb fails at the FIRST stage, not the third: the speaker cannot say `outfox`,")
    print("  so the index cannot propose it and understanding abstains rather than guessing. That is")
    print("  the correct failure — it abstains instead of fabricating — and it is still a failure.")
    print("  Closing it needs the two learned stages the design document registers as unbuilt: a frame")
    print("  tagger that does not depend on the speaker's inventory, and a learned relation -> schema")
    print("  map. Until an unseen verb reaches a goal functional, no claim of generality is available.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
