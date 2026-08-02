# -*- coding: utf-8 -*-
"""How well could this encoder name things if it were simply TOLD the answers?

WHY THE CEILING AND NOT MORE SEARCH. Held-out naming is 0.278 against a chance of 0.125, and two
readings fit that equally well:

    the OBJECTIVE is wrong    the architecture can carry kinds, and triplets over free relations are
                              not the way to put them there. Then better relations are worth hunting.
    the ARCHITECTURE cannot   a 40x40 patch through ~0.1M parameters cannot represent kinds at all.
                              Then no relation set will ever work and hunting them wastes the effort.

Handing over the labels separates them, per the owner's standing rule: when self-effort failing does
not distinguish "design wrong" from "parts bad", supply the answers, measure the ceiling, and put a
number on the gap. Everything else is held identical -- same patches, same net, same steps, same
held-out episodes, same nearest-centroid readout -- so the ONLY difference is where the training
signal comes from.

THE CEILING ARM MAKES NO CAPABILITY CLAIM. It trains on the simulator's semantic map, which ATANOR
never sees at runtime. It says what the architecture can hold, and nothing about what the eye can do
unaided. Recorded that way so a later reader cannot mistake it for a result.

Run:  python scripts/naming_ceiling.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception import learned_signature as LS                    # noqa: E402
from scripts.question_type_aligned import (DIM, harvest, naming,           # noqa: E402
                                           participation_ratio, train, triplets)

EPISODES = r"D:\carla\episodes"
OUT = "data/perception/naming_ceiling.json"


def train_supervised(patches, attrs, epochs=14, batch=128, lr=2e-3):
    """The same encoder, told outright which class each patch is.

    A linear head on the embedding, thrown away afterwards: what is scored is the EMBEDDING, read by
    the same nearest-centroid rule as every self-supervised arm, so the comparison is like for like
    and nothing is won by having a classifier at test time."""
    import torch
    keep = [i for i, a in enumerate(attrs) if a["_class"] >= 0]
    cls = sorted({attrs[i]["_class"] for i in keep})
    y = torch.tensor([cls.index(attrs[i]["_class"]) for i in keep])
    X = torch.from_numpy(patches[keep].astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    net = LS.make_net(DIM)
    head = torch.nn.Linear(DIM, len(cls))
    opt = torch.optim.Adam(list(net.parameters()) + list(head.parameters()), lr=lr)
    lossf = torch.nn.CrossEntropyLoss()
    for _ in range(epochs):
        perm = torch.randperm(len(y))
        for s in range(0, len(y) - batch, batch):
            i = perm[s:s + batch]
            e = net(X[i])
            e = e / e.norm(dim=1, keepdim=True).clamp(min=1e-6)
            loss = lossf(head(e), y[i])
            opt.zero_grad()
            loss.backward()
            opt.step()
    net.eval()
    return net, len(cls)


def main() -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    Ptr, Atr = harvest(eps[0:14], np.random.default_rng(0))
    Pte, Ate = harvest(eps[44:54], np.random.default_rng(1))
    print("train %d | held-out %d" % (len(Ptr), len(Pte)))
    rows = {}
    print("%-34s %10s %10s %8s" % ("arm", "eff dims", "naming", "chance"))

    best_free = ["identity", "depth", "height", "texture"]
    net = train(Ptr, triplets(Atr, best_free))
    Etr, Ete = LS.embed(net, Ptr), LS.embed(net, Pte)
    acc, ch, k = naming(Etr, Atr, Ete, Ate)
    rows["free relations (best so far)"] = {"naming_heldout": acc, "chance": ch,
                                            "participation_ratio": participation_ratio(Etr)}
    print("%-34s %10.2f %10.3f %8.3f" % ("free relations (best so far)",
                                         participation_ratio(Etr), acc, ch))

    net, ncls = train_supervised(Ptr, Atr)
    Etr, Ete = LS.embed(net, Ptr), LS.embed(net, Pte)
    acc_c, ch, k = naming(Etr, Atr, Ete, Ate)
    rows["CEILING — told the answers"] = {"naming_heldout": acc_c, "chance": ch,
                                          "participation_ratio": participation_ratio(Etr),
                                          "classes_trained_on": ncls,
                                          "not_a_capability_claim": True}
    print("%-34s %10.2f %10.3f %8.3f" % ("CEILING - told the answers",
                                         participation_ratio(Etr), acc_c, ch))

    gap = acc_c - rows["free relations (best so far)"]["naming_heldout"]
    print()
    print("gap between what it learns unaided and what it could hold: %+.3f" % gap)
    print("a LARGE ceiling means the objective is the problem and better relations are worth hunting.")
    print("a ceiling near the free arm means the architecture cannot carry kinds and no relation will.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "gap": gap,
                   "note": "the ceiling arm trains on simulator labels ATANOR never sees at "
                           "runtime; it bounds the architecture, it is not a capability"},
                  f, indent=1)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
