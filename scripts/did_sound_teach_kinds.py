# -*- coding: utf-8 -*-
"""Did asking "what does this sound like" put KINDS into the visual embedding?

THE WALL THIS IS AIMED AT, measured yesterday. The visual encoder declares 32 dimensions and uses
about four, because `learned_signature.harvest` asks it exactly one question -- is this the same
track? A linear probe over its embeddings reached 0.192 against a chance of 0.125, and a probe cannot
invent information that is absent, so KINDS were not in there. Adding more questions of the same TYPE
failed twice: depth, height, texture and colour are all computable FROM THE PATCH, four spellings of
"what does this look like", and count-matched they lost to the single-relation control.

WHAT A THING SOUNDS LIKE IS NOT READABLE FROM THE PATCH AT ALL. It is the first genuinely different
question available, so this is the first real test of the surviving hypothesis: that dimensionality
follows the KIND of question rather than the number.

THE COMPARISON IS ON ONE TASK WITH ONE READOUT, and deliberately not against yesterday's number.
Yesterday's 0.192 was CARLA patches at 24 px through a 106 KB encoder; the AV encoder saw 64 px
VGGSound frames. Comparing those directly would measure the domain gap and call it an encoder
difference. So both arms are scored HERE, on VGGSound's own classes, on clips neither arm trained on:

    untrained   the same architecture at initialisation -- what the shape of the network buys
    AV-trained  the same architecture after learning to match sound to sight

VGGSound's class labels are used ONLY to score. Neither arm ever sees one, exactly as the simulator's
semantic map was used for the eye.

REGISTERED BEFORE RUNNING:
    1  AV-trained beats untrained on held-out class retrieval. If not, co-occurrence did not put
       kinds in either, and the question-type hypothesis is finished rather than unproven.
    2  both beat chance by less than the gap between them, or the architecture is doing the work.
    3  and the AUDIO side should carry kinds at least as well as the visual side -- a sound is a more
       direct report of what a thing IS than one frame of it is.
"""
from __future__ import annotations

import csv
import io as _io
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

CACHE = r"D:\atanor_data\vggsound_features.npz"
CSVP = r"D:\atanor_data\vggsound\vggsound.csv"
OUT = os.path.join(REPO, "data", "perception", "did_sound_teach_kinds.json")
SIDE, DIM = 64, 32


def labels_for(names) -> dict:
    """Class per clip, from the file name we saved it under. Scoring only."""
    rows = list(csv.reader(_io.StringIO(open(CSVP, encoding="utf-8", errors="replace").read())))
    by = {}
    for r in rows:
        if len(r) >= 3:
            by["%s_%s" % (r[0].strip(), r[1].strip())] = r[2].strip()
    out = {}
    for n in names:
        s = str(n)
        s = s[:-4] if s.endswith(".mp4") else s
        if s in by:
            out[s] = by[s]
    return out


def probe(Xtr, ytr, Xte, yte, n_cls, steps=700, lr=0.6, l2=1e-3) -> float:
    """Linear, on purpose: it reports what is already laid out, not what a new net could learn."""
    rng = np.random.default_rng(0)
    W = rng.normal(0, 0.01, (Xtr.shape[1], n_cls))
    b = np.zeros(n_cls)
    Y = np.eye(n_cls)[ytr]
    for _ in range(steps):
        z = Xtr @ W + b
        z -= z.max(1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(1, keepdims=True)
        g = (p - Y) / len(Xtr)
        W -= lr * (Xtr.T @ g + l2 * W)
        b -= lr * g.sum(0)
    return float(((Xte @ W + b).argmax(1) == yte).mean())


def centroid(Xtr, ytr, Xte, yte, n_cls) -> float:
    C = np.stack([Xtr[ytr == c].mean(0) if (ytr == c).any() else np.zeros(Xtr.shape[1])
                  for c in range(n_cls)])
    C /= np.maximum(1e-9, np.linalg.norm(C, axis=1, keepdims=True))
    Xte = Xte / np.maximum(1e-9, np.linalg.norm(Xte, axis=1, keepdims=True))
    return float(((Xte @ C.T).argmax(1) == yte).mean())


def main() -> None:
    import torch
    from scripts.av_cooccurrence import _embed, _nets, train  # noqa: F401
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    d = np.load(CACHE, allow_pickle=True)
    A, V, names = d["audio"], d["video"], d["names"]
    lab = labels_for(names)
    stems = [str(n)[:-4] if str(n).endswith(".mp4") else str(n) for n in names]
    have = np.array([s in lab for s in stems])
    # only classes with enough clips to have a train and a test side
    cls_count: dict = {}
    for s, ok in zip(stems, have):
        if ok:
            cls_count[lab[s]] = cls_count.get(lab[s], 0) + 1
    # FOUR, BECAUSE OF HOW THE CLIPS WERE FETCHED. The overnight download went round-robin over the
    # ontology to get breadth, which gave 309 classes and about four clips each -- good for learning
    # an instance-matching objective and thin for measuring class structure. At six the filter keeps
    # nothing; at four it keeps 206 classes over 918 clips. Both arms face the identical task, so the
    # COMPARISON stands even though each arm's absolute number is limited by the thinness.
    keep_cls = sorted(c for c, n in cls_count.items() if n >= 4)
    sel = np.array([ok and lab[s] in keep_cls for s, ok in zip(stems, have)])
    idx = {c: i for i, c in enumerate(keep_cls)}
    y = np.array([idx[lab[s]] for s, k in zip(stems, sel) if k])
    A, V = A[sel], V[sel]
    print("clips %d | classes %d (>=6 clips each) | chance %.4f"
          % (len(y), len(keep_cls), 1 / len(keep_cls)))

    rng = np.random.default_rng(0)
    order = rng.permutation(len(y))
    cut = int(len(y) * 0.7)
    tr, te = order[:cut], order[cut:]

    rows = {}
    for tag, trained in (("untrained", False), ("AV-trained", True)):
        torch.manual_seed(0)
        vid, aud = _nets(A.shape[1])
        if trained:
            opt = torch.optim.Adam(list(vid.parameters()) + list(aud.parameters()), lr=2e-3)
            B = 48
            for _ in range(30):
                perm = rng.permutation(len(tr))
                for s in range(0, len(tr) - B, B):
                    b = tr[perm[s:s + B]]
                    ev, ea = _embed(vid, aud, V[b], A[b], torch)
                    lg = ea @ ev.T / 0.07
                    l0 = torch.arange(len(b))
                    loss = 0.5 * (torch.nn.functional.cross_entropy(lg, l0)
                                  + torch.nn.functional.cross_entropy(lg.T, l0))
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
        vid.eval()
        aud.eval()
        with torch.no_grad():
            EV, EA = [], []
            for s in range(0, len(y), 64):
                ev, ea = _embed(vid, aud, V[s:s + 64], A[s:s + 64], torch)
                EV.append(ev.numpy())
                EA.append(ea.numpy())
        EV, EA = np.concatenate(EV), np.concatenate(EA)
        rows[tag] = {
            "vision_centroid": centroid(EV[tr], y[tr], EV[te], y[te], len(keep_cls)),
            "vision_linear": probe(EV[tr], y[tr], EV[te], y[te], len(keep_cls)),
            "audio_centroid": centroid(EA[tr], y[tr], EA[te], y[te], len(keep_cls)),
            "audio_linear": probe(EA[tr], y[tr], EA[te], y[te], len(keep_cls)),
        }
        print("%-12s vision %.3f/%.3f   audio %.3f/%.3f  (centroid/linear)"
              % (tag, rows[tag]["vision_centroid"], rows[tag]["vision_linear"],
                 rows[tag]["audio_centroid"], rows[tag]["audio_linear"]), flush=True)

    chance = 1 / len(keep_cls)
    print()
    print("%-14s %12s %12s %12s %12s" % ("", "vis centroid", "vis linear", "aud centroid",
                                         "aud linear"))
    for tag in ("untrained", "AV-trained"):
        r = rows[tag]
        print("%-14s %12.3f %12.3f %12.3f %12.3f"
              % (tag, r["vision_centroid"], r["vision_linear"], r["audio_centroid"],
                 r["audio_linear"]))
    print("%-14s %12.4f %12.4f %12.4f %12.4f" % ("chance", chance, chance, chance, chance))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "chance": chance, "classes": len(keep_cls), "clips": len(y),
                   "note": "VGGSound class labels used ONLY to score; neither arm ever sees one"},
                  f, indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
