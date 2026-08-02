# -*- coding: utf-8 -*-
"""Grow the vocabulary from anchors whose labels are already free, and SCORE it held out.

THE PROBLEM THIS ANSWERS. The name book holds six street words, and measured on a live webcam it
called an indoor scene 'road' in 18 of 225 regions. A small vocabulary does not only miss things; it
over-claims the things it has, because every region is pulled to the nearest word it owns.

WHERE THE ANCHORS COME FROM, AND WHY NOT A DETECTOR. The owner's rule for an open-vocabulary detector
is that it is a SAMPLER OF EXAMPLE PATCHES at training time and never a runtime dependency. The
simulator's semantic map is the same kind of thing and strictly better here: it is already on disk,
it is exact, and it costs nothing. So this uses it for the street words, and a detector's turn comes
for the indoor vocabulary the simulator has no examples of.

THE SCORE IS HELD OUT AND IT IS FREE. Anchors are drawn from one set of episodes and every number is
measured on different ones. Per word, of the patches that really are that word, how many got called
it (recall), and of the patches called it, how many really were (precision). Nothing is annotated for
this; the simulator already knows.

WHAT A GOOD RESULT LOOKS LIKE, decided before running: more words WITHOUT the old words getting less
precise. A vocabulary that grows by making 'road' mean everything is worse than six honest words.

Run:  python scripts/grow_name_book.py --anchors 40
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception import learned_signature as LS       # noqa: E402
from packages.perception import naming                        # noqa: E402

EPISODES = r"D:\carla\episodes"
NET = r"D:\carla\depth_model\signature_net.pt"
BOOK = "data/perception/name_book.json"

#: CARLA's semantic ids. Only the ones that name a KIND OF THING are taken: 'unlabeled', 'other',
#: 'static' and 'dynamic' are bookkeeping, not words, and a name book that learns them learns to say
#: "stuff" confidently.
WORDS = {1: "building", 2: "fence", 4: "person", 5: "pole", 6: "roadline", 7: "road",
         8: "sidewalk", 9: "vegetation", 10: "car", 11: "wall", 12: "trafficsign",
         13: "sky", 14: "ground", 17: "guardrail", 18: "trafficlight", 21: "water",
         22: "terrain"}

#: A patch counts as an example of a word only if it is nearly ALL that word. A patch straddling a
#: boundary teaches the cluster to sit between two things, and then it matches everything weakly.
PURE = 0.9


def _net():
    ck = torch.load(NET, map_location="cpu")
    net = LS.make_net(ck.get("dim", 64))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    return net


def _episodes(lo: int, hi: int) -> list:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    return eps[lo:hi]


def _harvest(eps: list, per_word: int, rng) -> dict:
    """Patches that are almost entirely one class, gathered per word."""
    p = LS.PATCH
    out: dict = {k: [] for k in WORDS}
    for ep in eps:
        fs = sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))
        for f in fs[::4]:
            if all(len(v) >= per_word for v in out.values()):
                return out
            d = np.load(f)
            rgb, sem = d["rgb"], d["semantic"]
            h, w = sem.shape
            for _ in range(240):
                x = int(rng.integers(p, w - p))
                y = int(rng.integers(p, h - p))
                win = sem[y - p // 2:y + p // 2, x - p // 2:x + p // 2]
                if win.size == 0:
                    continue
                ids, counts = np.unique(win, return_counts=True)
                k = int(ids[int(np.argmax(counts))])
                if k not in out or counts.max() / win.size < PURE:
                    continue
                if len(out[k]) >= per_word:
                    continue
                q = LS.crop(rgb, (x, y))
                if q is not None:
                    out[k].append(q)
    return out


def main(per_word: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    net = _net()
    train = _harvest(_episodes(0, 22), per_word, rng)
    have = {WORDS[k]: v for k, v in train.items() if len(v) >= 8}
    print("anchors gathered: %s" % ", ".join("%s=%d" % (k, len(v)) for k, v in sorted(have.items())))
    embeds = {name: LS.embed(net, np.stack(v)) for name, v in have.items()}
    book = naming.anchor_from(embeds)
    print("book now holds %d words (was 6)" % len(book.centroids))

    test = _harvest(_episodes(40, 62), 60, np.random.default_rng(seed + 1))
    tp: dict = {}
    fp: dict = {}
    total: dict = {}
    for k, patches in test.items():
        name = WORDS[k]
        if not patches:
            continue
        total[name] = len(patches)
        for e in LS.embed(net, np.stack(patches)):
            got, _c = naming.name_of(book, e)
            if got == name:
                tp[name] = tp.get(name, 0) + 1
            elif got:
                fp[got] = fp.get(got, 0) + 1
    print()
    print("%-13s %6s %8s %10s" % ("word", "truth", "recall", "precision"))
    for name in sorted(total):
        r = tp.get(name, 0) / total[name]
        called = tp.get(name, 0) + fp.get(name, 0)
        pr = (tp.get(name, 0) / called) if called else float("nan")
        print("%-13s %6d %8.3f %10.3f" % (name, total[name], r, pr))
    named = sum(tp.values()) + sum(fp.values())
    seen = sum(total.values())
    print()
    print("overall: %d of %d patches got a word (%.0f%%), %d of those were right (%.3f)"
          % (named, seen, 100 * named / max(1, seen), sum(tp.values()),
             sum(tp.values()) / max(1, named)))

    # MARGIN, MEASURED RATHER THAN CHOSEN. `name_of` defaults to min_margin 0.0 -- the closest
    # centroid above threshold wins even when the runner-up is a hair behind. With six far-apart
    # street words that was harmless; with seventeen the clusters crowd, and a word won by a
    # hairsbreadth is a coin toss wearing a name. So sweep it and let the numbers say. Requiring a
    # margin can only LOWER coverage, so the question is what it buys in exchange.
    print()
    print("%-8s %10s %10s   %s" % ("margin", "coverage", "correct", "of those it did name"))
    embedded = {WORDS[k]: LS.embed(net, np.stack(v)) for k, v in test.items() if v}
    for m in (0.0, 0.02, 0.05, 0.10, 0.15):
        ok = spoke = 0
        for name, es in embedded.items():
            for e in es:
                got, _c = naming.name_of(book, e, min_margin=m)
                if got:
                    spoke += 1
                    ok += (got == name)
        print("%-8.2f %10.3f %10.3f   %d of %d"
              % (m, spoke / max(1, seen), ok / max(1, spoke), ok, spoke))
    if os.environ.get("WRITE_BOOK") == "1":
        book.save(BOOK)
        print("written to %s" % BOOK)
    else:
        print("(not written -- set WRITE_BOOK=1 to replace the book)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchors", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    main(a.anchors, a.seed)
