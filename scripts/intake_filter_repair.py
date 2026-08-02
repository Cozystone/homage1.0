# -*- coding: utf-8 -*-
"""Measure the learned intake against the 31-verb incumbent, on both registers, with a real control.

    python scripts/intake_filter_repair.py

REGISTERED BEFORE RUNNING, against the incumbent measured in the same pass:
    1  the learned intake admits sentences the 31-verb lexicon discards, and the rate is reported per
       register -- wiki prose and dialogue are different problems and an average hides which
    2  the RELATION DISTRIBUTION shifts off the 98% is_a/alias monopoly. This is the whole point: more
       admissions of the same copulas would be no repair at all
    3  a RANDOM-SPAN CONTROL is admitted far less often. Random contiguous three-way splits satisfy
       well-formedness and satisfy faithfulness -- the speaker echoes an unknown relation verbatim -- so
       if the control is admitted at the same rate the gates are decorative and the entrenchment
       criterion is doing nothing
    4  a sample of admitted triples is printed, because a distribution can shift and still be garbage

The tagger is loaded from the overnight multi-register run. Nothing here consults a verb list.
"""
from __future__ import annotations

import collections
import io
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.cgsr.cgsr.ingestion.decomposer import (ENGLISH_VERB_LEMMAS,          # noqa: E402
                                                     extract_english_case_roles)
from packages.cgsr.cgsr.ingestion.learned_intake import (Entrenchment, LearnedIntake,  # noqa: E402
                                                         norm)
from packages.cgsr.frame_tagger import FrameTagger                                  # noqa: E402

WEIGHTS = Path("data/language/frame_tagger_multiregister.npz")
WIKI = Path("data/graph_scale/bones_to_text.jsonl")
DIAL = Path("data/graph_scale/dialogue_grounded.jsonl")
OUT = Path("data/language/intake_filter_repair.json")
_S = re.compile(r"(?<=[.!?])\s+")
_SPK = re.compile(r"^\s*[AB]\s*:\s*")


def sentences(path: Path, cap: int):
    out = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            for ln in str(d.get("text") or "").split("\n"):
                for s in _S.split(_SPK.sub("", ln.strip())):
                    s = s.strip()
                    if 4 <= len(s.split()) <= 32:
                        out.append(s)
                        if len(out) >= cap:
                            return out
    return out


class RandomSpanTagger:
    """The control: tags a random contiguous SUBJ/REL/OBJ partition. Well-formed and faithful by
    construction, so only entrenchment can reject it."""

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def tag(self, toks: list) -> list:
        n = len(toks)
        if n < 3:
            return [0] * n
        i = int(self.rng.integers(1, n - 1))
        j = int(self.rng.integers(i + 1, n))
        return [1] * i + [2] * (j - i) + [3] * (n - j)


def incumbent(sent: str):
    roles, pred = extract_english_case_roles(sent)
    if not pred or len(roles) < 2:
        return None
    return roles[0]["head"], pred, roles[-1]["head"]


def run(name: str, sents: list, tagger) -> dict:
    it = LearnedIntake(tagger, Entrenchment(min_pairs=3))
    it.learn_pass(sents)
    admitted = [t for t in (it.admit(s) for s in sents) if t]
    rel = collections.Counter(norm(t[1]) for t in admitted)
    cop = sum(c for r, c in rel.items() if r in ("is", "is a", "are", "is the", "is an", "was", "were"))
    return {"name": name, "n": len(sents), "admitted": len(admitted),
            "rate": len(admitted) / max(len(sents), 1),
            "distinct_relations": len(rel),
            "copula_share": cop / max(len(admitted), 1),
            "top": rel.most_common(10), "sample": admitted[:8],
            "dropouts": dict(it.counts), "entrenchment": it.ent.summary()}


def main() -> None:
    if not WEIGHTS.exists():
        sys.exit(f"{WEIGHTS} not found; run scripts/overnight_register_repair.py first")
    tagger = FrameTagger.load(WEIGHTS)

    CAP = 4000
    corpora = {"wiki prose": sentences(WIKI, CAP), "dialogue": sentences(DIAL, CAP)}
    print(f"tagger loaded from the overnight multi-register run; "
          f"incumbent lexicon holds {len(ENGLISH_VERB_LEMMAS)} verbs\n")

    results = {}
    for cname, sents in corpora.items():
        inc = [t for t in (incumbent(s) for s in sents) if t]
        inc_rel = collections.Counter(norm(t[1]) for t in inc)
        learned = run("learned", sents, tagger)
        ctrl = run("random-span control", sents, RandomSpanTagger())
        results[cname] = {"incumbent": {"admitted": len(inc), "rate": len(inc) / max(len(sents), 1),
                                        "distinct_relations": len(inc_rel),
                                        "top": inc_rel.most_common(6)},
                          "learned": learned, "control": ctrl}
        print(f"--- {cname}  ({len(sents)} sentences)")
        print(f"  incumbent (31-verb lexicon)  admitted {len(inc):>5} = "
              f"{len(inc)/max(len(sents),1):>6.1%}   distinct relations {len(inc_rel):>4}")
        print(f"  LEARNED intake               admitted {learned['admitted']:>5} = "
              f"{learned['rate']:>6.1%}   distinct relations {learned['distinct_relations']:>4}"
              f"   copula share {learned['copula_share']:.1%}")
        print(f"  random-span control          admitted {ctrl['admitted']:>5} = "
              f"{ctrl['rate']:>6.1%}   distinct relations {ctrl['distinct_relations']:>4}")
        print(f"  learned dropouts: {learned['dropouts']}")
        print(f"  incumbent's relations: {inc_rel.most_common(6)}")
        print(f"  learned's relations:   {learned['top'][:6]}")
        for t in learned["sample"][:4]:
            print(f"     admitted: {t}")
        print()

    w, d = results["wiki prose"], results["dialogue"]
    print("-> 1. admits what the lexicon discards: "
          f"wiki {w['learned']['rate']:.1%} vs {w['incumbent']['rate']:.1%}, "
          f"dialogue {d['learned']['rate']:.1%} vs {d['incumbent']['rate']:.1%}")
    print(f"-> 2. copula share among admitted: wiki {w['learned']['copula_share']:.1%}, "
          f"dialogue {d['learned']['copula_share']:.1%}   (the graph today is 98% is_a/alias)")
    beats_ctrl = (w["learned"]["rate"] > 2 * w["control"]["rate"]
                  and d["learned"]["rate"] > 2 * d["control"]["rate"])
    print(f"-> 3. beats the random-span control by more than 2x: {beats_ctrl}  "
          f"(wiki {w['control']['rate']:.1%}, dialogue {d['control']['rate']:.1%})")
    if not beats_ctrl:
        print("      -> the gates are decorative: random spans pass at a comparable rate, so nothing")
        print("         here is evidence that the tagger is reading rather than partitioning.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
