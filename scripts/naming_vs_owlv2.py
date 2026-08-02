# -*- coding: utf-8 -*-
"""Can ATANOR name what it sees without the external detector? Measured against it on the same frames.

    python scripts/naming_vs_owlv2.py

WHY. OWLv2 was brought in as the BENCHMARK TO BEAT, not as a component, and it drifted into being one --
including in a figure captioned "what ATANOR says it sees", where the thing doing the seeing was a 593 MB
external model. This measures the independent path on the same corpus so the comparison is a number rather
than an intention.

THE TWO PATHS DO DIFFERENT WORK and the comparison has to say so. `learned_signature` learns what makes two
views the SAME thing, with positives drawn from tracking and no labels anywhere; naming then attaches a word
to a cluster from a handful of anchors. OWLv2 does open-vocabulary detection over a whole scene. Patch
classification against six known classes is the EASIER task, and the numbers below are not
interchangeable -- what they can be compared on is the trade each makes between speaking and being right.

REGISTERED before running:
    1  ours beats chance by a wide margin on held-out patches, or the signature space is not carrying names
    2  ABSTENTION BUYS PRECISION -- the whole claim. Naming only when the space is decisive must raise
       precision above the speak-always version, or silence is costing recall for nothing.
    3  coverage is reported beside precision every time, because a namer that abstains on everything scores
       1.000 and is useless
"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception import learned_signature as LS      # noqa: E402
from packages.perception import naming                       # noqa: E402

CORPUS = Path(r"D:\carla\episodes")
NET = Path(r"D:\carla\depth_model\signature_net.pt")
OUT = Path("data/perception/naming_vs_owlv2.json")
BOOK = Path("data/perception/name_book.json")
TAGS = {1: "road", 2: "sidewalk", 3: "building", 5: "fence", 6: "pole",
        9: "vegetation", 10: "terrain", 14: "car"}
TEST_PER_CLASS = 40


def harvest(net, episode: str, purity: float = 0.75, per_frame: int = 14, stride: int = 6):
    """Patches whose semantics are nearly pure. Labels are used ONLY to build anchors and to score."""
    import torch

    ck = torch.load(NET, map_location="cpu")
    r = ck.get("patch", 20)
    rng = np.random.default_rng(0)
    pat = collections.defaultdict(list)
    for f in sorted(glob.glob(str(CORPUS / episode / "*.npz")))[::stride][:34]:
        z = np.load(f)
        rgb, sem = z["rgb"], z["semantic"]
        for k, name in TAGS.items():
            ys, xs = np.where(sem == k)
            if len(ys) < 40:
                continue
            for i in rng.choice(len(ys), min(per_frame, len(ys)), replace=False):
                y, x = int(ys[i]), int(xs[i])
                if y < r or x < r or y + r >= rgb.shape[0] or x + r >= rgb.shape[1]:
                    continue
                if (sem[y - r:y + r, x - r:x + r] == k).mean() >= purity:
                    pat[name].append(rgb[y - r:y + r, x - r:x + r])
    return {k: v for k, v in pat.items() if len(v) >= TEST_PER_CLASS + 20}


def main() -> None:
    import torch

    ck = torch.load(NET, map_location="cpu")
    net = LS.make_net(ck.get("dim", 64))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    size_kb = NET.stat().st_size // 1024

    pat = harvest(net, "ep444")
    emb = {k: LS.embed(net, np.stack(v[:300]), "cpu") for k, v in pat.items()}
    names = sorted(emb)
    test = {k: emb[k][-TEST_PER_CLASS:] for k in names}     # FIXED, never used as an anchor at any n
    pool = {k: emb[k][:-TEST_PER_CLASS] for k in names}

    print(f"signature encoder {size_kb} KB, {ck.get('dim', 64)}-dim, trained with NO labels")
    print(f"classes: {', '.join(names)}   held-out {TEST_PER_CLASS} per class\n")
    print(f"{'anchors':<9}{'speak-always':>14}{'ABSTAINING':>13}{'coverage':>11}"
          f"{'precision gain':>16}")
    rows = {}
    for n in (1, 2, 3, 5, 10, 20):
        if min(len(pool[k]) for k in names) < n:
            break
        book = naming.anchor_from({k: pool[k][:n] for k in names})
        always = abst = spoke = tot = 0
        for k in names:
            for v in test[k]:
                # speak-always: nearest centroid, no refusal. The version to beat.
                sims = sorted(((float(naming._unit(v) @ c), nm)
                               for nm, c in book.centroids.items()), reverse=True)
                always += sims[0][1] == k
                nm, _m = naming.name_of(book, v)
                if nm is not None:
                    spoke += 1
                    abst += nm == k
                tot += 1
        p_always = always / tot
        p_abst = (abst / spoke) if spoke else float("nan")
        cov = spoke / tot
        rows[n] = {"speak_always_precision": p_always, "abstaining_precision": p_abst,
                   "coverage": cov, "n_test": tot}
        print(f"{n:<9}{p_always:>14.3f}{p_abst:>13.3f}{cov:>11.1%}{p_abst - p_always:>+16.3f}")

    best = max(rows, key=lambda n: rows[n]["abstaining_precision"])
    chance = 1.0 / len(names)
    gains = [r["abstaining_precision"] - r["speak_always_precision"] for r in rows.values()]
    print(f"\nchance {chance:.3f}   |   OWLv2 on this corpus: precision 0.51, recall 0.95, "
          f"593 MB, ~200 ms/frame")
    print(f"\n-> 1. well above chance: {rows[best]['speak_always_precision'] > 3 * chance}")
    print(f"-> 2. ABSTENTION BUYS PRECISION: {all(g >= 0 for g in gains)}   "
          f"(median gain {np.median(gains):+.3f})")
    print(f"-> 3. and it is not bought by silence: coverage "
          f"{rows[best]['coverage']:.1%} at the best setting")

    book = naming.anchor_from({k: pool[k][:20] for k in names})
    book.save(BOOK)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"encoder_kb": size_kb, "dim": ck.get("dim", 64),
                               "classes": names, "chance": chance, "by_anchors": rows,
                               "owlv2_reference": {"precision": 0.51, "recall": 0.95,
                                                   "cache_mb": 593, "params_m": 155},
                               "caveat": "patch classification over known classes is an EASIER task than "
                                         "open-vocabulary scene detection; these numbers are not "
                                         "interchangeable with OWLv2's."},
                              indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}  and the name book to {BOOK}")


if __name__ == "__main__":
    main()
