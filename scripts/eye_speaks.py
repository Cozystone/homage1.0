# -*- coding: utf-8 -*-
"""The eye perceives, and then ATANOR says it — in its own voice, with no external model anywhere.

    python scripts/eye_speaks.py

THE ORDER IS THE POINT, and it is the owner's: perception of the world through the eye comes FIRST, and the
brain forms sentences from what was perceived. Anything else is a language organ talking about words. Until
today the scene sentence came out of a hand-written Korean template fed by a 593 MB external detector --
three separate violations of that order at once.

    packages/perception/learned_signature   what makes two views the SAME thing, from tracking, NO labels
    packages/perception/naming              which cluster carries which word, from a few anchors
    packages/realizer_struct                bones [subject, relation, object] -> an English sentence

Nothing here loads OWLv2. The encoder is 103 KB.

SILENCE PROPAGATES, and that is the property worth having. When the namer declines a patch -- the space is
not close enough to any known cluster -- the region contributes no bone, so the sentence simply does not
mention it. An organ that abstains upstream of a speaker that only realises what it is given cannot produce
a confident sentence about something it could not identify. That is the structural version of the honesty
rule, rather than a filter bolted on at the end.

WHAT THIS DOES NOT DO, said plainly because the output looks more finished than the system is:
    - it samples a grid, it does not SEGMENT. "There is a car" is grounded; "there are two cars" is not,
      because nothing here counts objects -- `learned_mask` and `gestalt` are the organs for that.
    - the construction bank holds 14 mined frames and NONE for spatial relations, so every spatial bone
      falls back to the generic "{s} {rel} {o}" and the speech comes out telegraphic. That is a real gap
      in the speaker, visible in the output below, and not something to paper over with a template.
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
from packages.realizer_struct.frame_realizer import realize   # noqa: E402

CORPUS = Path(r"D:\carla\episodes")
NET = Path(r"D:\carla\depth_model\signature_net.pt")
BOOK = Path("data/perception/name_book.json")
OUT = Path("data/perception/eye_speaks.json")
GRID = 6


def where(cx: float, cy: float) -> str:
    """Coarse position words. Deliberately coarse: the eye samples a grid, it does not localise."""
    col = "left" if cx < 0.36 else "right" if cx > 0.64 else "centre"
    row = "near" if cy > 0.68 else "far" if cy < 0.42 else "middle distance"
    return f"the {row} {col}" if col != "centre" else f"{row} centre"


def perceive(net, book, rgb, patch_r: int):
    """Name what the grid finds, and keep NOTHING the namer declined."""
    h, w = rgb.shape[:2]
    cells, spoken, declined = [], 0, 0
    ys = np.linspace(patch_r, h - patch_r - 1, GRID).astype(int)
    xs = np.linspace(patch_r, w - patch_r - 1, GRID).astype(int)
    patches, coords = [], []
    for y in ys:
        for x in xs:
            patches.append(rgb[y - patch_r:y + patch_r, x - patch_r:x + patch_r])
            coords.append((x / w, y / h))
    emb = LS.embed(net, np.stack(patches), "cpu")
    for e, (cx, cy) in zip(emb, coords):
        name, close = naming.name_of(book, e)
        if name is None:
            declined += 1
            continue
        spoken += 1
        cells.append({"name": name, "cx": float(cx), "cy": float(cy), "closeness": round(close, 3)})
    return cells, spoken, declined


def bones_from(cells) -> list:
    """Perceived regions -> [subject, relation, object]. The only thing handed to the speaker.

    Regions of the same name are collapsed to one bone at their centre of mass: the eye sampled a grid and
    saw 'road' in nine cells, which is one road seen nine times and not nine roads. Counting is a claim
    this pipeline cannot support, so it does not make one."""
    by = collections.defaultdict(list)
    for c in cells:
        by[c["name"]].append(c)
    out = []
    for name, group in sorted(by.items(), key=lambda kv: -len(kv[1])):
        cx = float(np.mean([g["cx"] for g in group]))
        cy = float(np.mean([g["cy"] for g in group]))
        out.append([name, "in", where(cx, cy)])
    return out


def main() -> None:
    import torch

    if not BOOK.exists():
        sys.exit(f"no name book at {BOOK}; run scripts/naming_vs_owlv2.py first")
    ck = torch.load(NET, map_location="cpu")
    net = LS.make_net(ck.get("dim", 64))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    book = naming.NameBook.load(BOOK)
    print(f"encoder {NET.stat().st_size // 1024} KB, {ck.get('dim', 64)}-dim, label-free")
    print(f"name book: {', '.join(sorted(book.centroids))}  "
          f"({sum(book.counts.values())} anchors total)\n")

    rows = []
    files = sorted(glob.glob(str(CORPUS / "ep444" / "*.npz")))[40:240:60]
    for f in files:
        z = np.load(f)
        rgb, sem = z["rgb"], z["semantic"]
        cells, spoke, declined = perceive(net, book, rgb, ck.get("patch", 20))
        bones = bones_from(cells)
        sentence = realize(bones) if bones else None
        truth = sorted({n for n in ("road", "building", "vegetation", "sidewalk", "terrain", "car")
                        if _truth_has(sem, n)})
        said = sorted({b[0] for b in bones})
        rows.append({"file": Path(f).name, "said": said, "truth": truth,
                     "spoke_cells": spoke, "declined_cells": declined,
                     "sentence": sentence})
        print(f"{Path(f).name}   named {spoke}/{spoke + declined} cells, declined {declined}")
        print(f"   ATANOR says : {sentence or '(nothing -- the namer declined every cell)'}")
        print(f"   really there: {', '.join(truth)}")
        print(f"   invented    : {', '.join(sorted(set(said) - set(truth))) or 'none'}")
        print(f"   missed      : {', '.join(sorted(set(truth) - set(said))) or 'none'}\n")

    tp = sum(len(set(r["said"]) & set(r["truth"])) for r in rows)
    fp = sum(len(set(r["said"]) - set(r["truth"])) for r in rows)
    fn = sum(len(set(r["truth"]) - set(r["said"])) for r in rows)
    p, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    print(f"precision {p:.2f}   recall {rc:.2f}   (tp {tp} fp {fp} fn {fn})")
    print(f"OWLv2 on this corpus: precision 0.51 recall 0.95, 593 MB, ~200 ms/frame")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"frames": rows, "precision": p, "recall": rc,
                               "encoder_kb": NET.stat().st_size // 1024,
                               "external_models_used": []}, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


def _truth_has(sem, name: str, frac: float = 0.02) -> bool:
    tag = {"road": 1, "sidewalk": 2, "building": 3, "vegetation": 9, "terrain": 10, "car": 14}[name]
    return bool((sem == tag).mean() >= frac)


if __name__ == "__main__":
    main()
