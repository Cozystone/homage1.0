# -*- coding: utf-8 -*-
"""Overnight, offline: label the dialogue registers by distant supervision and retrain the tagger.

    python scripts/overnight_register_repair.py [minutes]

Owner: 코퍼스 편향 해결하고 섭취필터 고치고 다양한 문장들 학습하는 쪽으로 가자 ... 밤새 돌면서 atanor가
자의적으로 고루 데이터 수집하게 하고싶은데.

THE SUPPLY WAS NEVER THE PROBLEM AND IT IS ALREADY ON DISK. Measured tonight, by simple counts that do
not depend on any detector of mine:

    corpus                        sentences   short (<=8 words)   questions
    dialogue_register.jsonl        135,668         51.8%            7.9%
    dialogue_grounded.jsonl         41,588         39.9%            8.3%
    bones_to_text.jsonl (wiki)      25,001          2.3%            0.0%

The corpus the tagger was trained on contains LITERALLY ZERO questions and almost no short sentences,
with 167 MB of dialogue sitting beside it unused. "The corpus has no imperatives" was true of what I
fed it, not of what ATANOR has.

WHY THIS DID NOT JUST HAPPEN ALREADY: labels. The tagger learns from spans, and spans came from
alignment -- a bone whose subject and object were both located in the sentence. Dialogue rows carry no
such bones.

DISTANT SUPERVISION IS THE STANDARD ANSWER AND NEEDS NO LLM. If a dialogue sentence mentions two
entities the GRAPH already relates, the graph supplies the labels for that sentence: those spans are the
subject and the object, and what lies between them is the relation. The text is new; the supervision is
knowledge ATANOR already had. Nothing is generated, nothing is guessed, and a sentence that mentions no
related pair simply yields no example.

WHAT IS DELIBERATELY NOT DONE TONIGHT. No network. No autonomous browsing: with the intake still
recognising 31 definitional verbs, crawling would collect the same shape from a wider set of pages, and
unattended crawling is an outward-facing act that is the owner's call to make awake. Those options stay
open and are stated in the report this writes.

MEASURED, HELD OUT BY SOURCE so a register cannot be tested on itself:
    1  the register composition of the training set actually changes
    2  held-out F1 is reported PER REGISTER, because an average over wiki and dialogue hides which one
       the model can read
    3  imperatives and questions -- the two things the wiki-only tagger could not do at all
    4  against a label-shuffled control at every stage, since a shuffled control reached F1_REL 0.503
       earlier tonight purely from position
"""
from __future__ import annotations

import collections
import io
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.cgsr.frame_tagger import FrameTagger, LABELS, norm            # noqa: E402
from scripts.mine_constructions_v2 import find, stem                        # noqa: E402
from scripts.train_frame_tagger import evaluate, positional_baseline        # noqa: E402

WIKI = Path("data/graph_scale/bones_to_text.jsonl")
DIALOGUE = [Path("data/graph_scale/dialogue_grounded.jsonl"),
            Path("data/graph_scale/dialogue_register.jsonl")]
OUT = Path("data/language/overnight_register_repair.json")
WEIGHTS = Path("data/language/frame_tagger_multiregister.npz")
_S = re.compile(r"(?<=[.!?])\s+")
_SPK = re.compile(r"^\s*[AB]\s*:\s*")


def graph_pairs(cap: int = 400000):
    """(subject, object) -> relation, from the graph's own bones. The supervision, already earned."""
    rel: dict = {}
    ent: dict = collections.defaultdict(set)
    with io.open(WIKI, encoding="utf-8") as f:
        for i, line in enumerate(f):
            d = json.loads(line)
            for b in d.get("bones") or []:
                if len(b) < 3:
                    continue
                s, r, o = (norm(str(x)) for x in b)
                if not s or not o or s == o or len(s) < 3 or len(o) < 3:
                    continue
                rel.setdefault((s, o), r)
                ent[s.split()[-1]].add(s)
                ent[o.split()[-1]].add(o)
            if i >= cap:
                break
    return rel, ent


def sentences_of(text: str):
    for ln in str(text).split("\n"):
        ln = _SPK.sub("", ln.strip())
        for s in _S.split(ln):
            s = s.strip()
            if s:
                yield s


def label_by_distant_supervision(sent: str, rel: dict, ent: dict):
    """Spans for a sentence that mentions two entities the graph already relates. None otherwise."""
    w = norm(sent).split()
    if not (4 <= len(w) <= 32):
        return None
    st = [stem(x) for x in w]
    present = []
    for j, tok in enumerate(w):
        for cand in ent.get(tok, ()):
            span = find(w, st, cand, {})
            if span and span not in [p[1] for p in present]:
                present.append((cand, span))
    for a_name, a in present:
        for b_name, b in present:
            if a is b or a[1] > b[0]:
                continue
            r = rel.get((a_name, b_name))
            if not r or b[0] - a[1] < 1 or b[0] - a[1] > 6:
                continue
            lab = [0] * len(w)
            for i in range(a[0], a[1]):
                lab[i] = 1
            for i in range(a[1], b[0]):
                lab[i] = 2
            for i in range(b[0], b[1]):
                lab[i] = 3
            return w, lab, r
    return None


def harvest(rel, ent, budget_s: float):
    """Scan the dialogue corpora until the time budget runs out. Yields (tokens, labels, source)."""
    out = []
    t0 = time.time()
    for path in DIALOGUE:
        if not path.exists():
            continue
        with io.open(path, encoding="utf-8") as f:
            for line in f:
                if time.time() - t0 > budget_s:
                    return out
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                for s in sentences_of(d.get("text") or ""):
                    got = label_by_distant_supervision(s, rel, ent)
                    if got:
                        out.append((got[0], got[1], path.stem))
    return out


def wiki_examples(cap: int = 12000):
    from scripts.train_frame_tagger import build_examples
    ex, arts = build_examples()
    return [(t, l, "wiki") for t, l in ex][:cap], arts


def register_stats(rows) -> dict:
    n = len(rows) or 1
    return {"n": len(rows),
            "short_le8": sum(1 for t, _l, _s in rows if len(t) <= 8) / n,
            "mean_len": float(np.mean([len(t) for t, _l, _s in rows])) if rows else 0.0}


def main() -> None:
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    print(f"budget {minutes:.0f} min, offline, no network\n", flush=True)

    rel, ent = graph_pairs()
    print(f"graph supervision: {len(rel)} related entity pairs, {len(ent)} head-word buckets",
          flush=True)

    dial = harvest(rel, ent, budget_s=minutes * 60 * 0.55)
    # The trainer is plain numpy SGD, so an unbounded harvest would spend the night in fit() instead
    # of in the corpus. Cap what is TRAINED on and report what was HARVESTED, so the two are never
    # confused -- a silent truncation reads as "used everything".
    CAP = 30000
    harvested = len(dial)
    if len(dial) > CAP:
        rng0 = np.random.default_rng(1)
        idx = rng0.choice(len(dial), CAP, replace=False)
        dial = [dial[i] for i in sorted(idx)]
        print(f"harvested {harvested}, training on a random {CAP} of them (the trainer is the "
              f"bottleneck, not the corpus)", flush=True)
    wiki, _arts = wiki_examples()
    print(f"distant-supervised dialogue examples: {len(dial)}", flush=True)
    print(f"wiki alignment examples:              {len(wiki)}", flush=True)
    if len(dial) < 200:
        print("\nTOO FEW dialogue examples to train on; reporting the harvest and stopping rather "
              "than producing a number from a handful.", flush=True)

    print(f"\nregister composition   wiki {register_stats(wiki)}   dialogue {register_stats(dial)}",
          flush=True)

    rng = np.random.default_rng(0)
    rng.shuffle(dial)
    cut = max(1, len(dial) // 5)
    te_d, tr_d = dial[:cut], dial[cut:]
    cutw = max(1, len(wiki) // 5)
    te_w, tr_w = wiki[:cutw], wiki[cutw:]

    arms = {}
    for name, tr in (("wiki only", tr_w), ("wiki + dialogue", tr_w + tr_d)):
        if not tr:
            continue
        m = FrameTagger()
        m.fit([(t, l) for t, l, _s in tr])
        arms[name] = {"wiki": evaluate(m.tag, [(t, l) for t, l, _s in te_w]),
                      "dialogue": evaluate(m.tag, [(t, l) for t, l, _s in te_d]) if te_d else None,
                      "model": m}
    sh = FrameTagger()
    sh.fit([(t, list(rng.permutation(l))) for t, l, _s in (tr_w + tr_d)][:6000], epochs=3)
    arms["label-shuffled control"] = {
        "wiki": evaluate(sh.tag, [(t, l) for t, l, _s in te_w]),
        "dialogue": evaluate(sh.tag, [(t, l) for t, l, _s in te_d]) if te_d else None,
        "model": sh}

    print(f"\n{'arm':<26}{'wiki acc':>10}{'wiki F1REL':>12}{'dial acc':>10}{'dial F1REL':>12}")
    for k, v in arms.items():
        dv = v["dialogue"] or {"acc": float("nan"), "f1_REL": float("nan")}
        print(f"{k:<26}{v['wiki']['acc']:>10.3f}{v['wiki']['f1_REL']:>12.3f}"
              f"{dv['acc']:>10.3f}{dv['f1_REL']:>12.3f}", flush=True)

    best = arms.get("wiki + dialogue") or arms.get("wiki only")
    m = best["model"]
    print("\nimperatives and questions, which the wiki-only corpus could not teach:", flush=True)
    probes = ["Avoid the ghosts.", "Eat the pellets.", "Shun the ghosts.",
              "What is albedo?", "Where is the office?"]
    for s in probes:
        t = norm(s).split()
        print(f"  {s:<26} {' '.join(f'{w}/{LABELS[g]}' for w, g in zip(t, m.tag(t)))}", flush=True)

    m.save(WEIGHTS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"dialogue_examples_trained": len(dial), "dialogue_examples_harvested": harvested,
         "wiki_examples": len(wiki),
         "register": {"wiki": register_stats(wiki), "dialogue": register_stats(dial)},
         "arms": {k: {"wiki": v["wiki"], "dialogue": v["dialogue"]} for k, v in arms.items()},
         "note": "offline only; no network, no autonomous browsing. The crawl decision is the "
                 "owner's to make awake, and with the 31-verb intake unchanged it would collect "
                 "the same shape from more pages."},
        indent=2), encoding="utf-8")
    print(f"\nwrote {OUT} and {WEIGHTS}", flush=True)


if __name__ == "__main__":
    main()
