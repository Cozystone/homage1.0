# -*- coding: utf-8 -*-
"""Point the image-schema basis at a web page: recover its structure from PIXELS, score against the truth.

    python scripts/schema_on_a_webpage.py

Owner: 사람이 웹사이트를 구조적으로 이해하는 원리가 뭐지? 단순한 모양과 텍스트를 넘어서 맥락으로.

The five layers a person actually uses: Gestalt grouping (proximity, similarity, common region), a learned
LAYOUT SCHEMA for "page" whose violation is immediately noticeable, affordance reading, task-driven
scanning, and text read as a LABEL ON A REGION rather than as prose. Structurally that is a HIERARCHY OF
REGIONS WITH ROLES -- not OCR plus shapes.

AND ATANOR IS NOT DOING THAT TODAY. `packages/atanor_browser/page_distiller.py` is "DOM text to
subject-anchored knowledge": it parses HTML and drops link-dense blocks. It READS THE DOM; it does not see
the page. Same pattern as the graph, which was fed already-structured triples rather than prose.

WHAT THIS RUNG BUILDS AND MEASURES. The DOM is used ONLY as the oracle -- the same discipline as the RAM
oracle in the vision line -- and the input is pixels:

    input      a rendered page, as an image. Nothing reads a tag.
    grouping   PROXIMITY and size similarity over pixel-derived regions, which is Gestalt done with the
               schema basis rather than with a new rule
    hierarchy  PART_WHOLE, implemented today, turns groups into parent-child edges
    oracle     the true nesting, known because the page is generated here
    scored     precision and recall on parent-child edges, against two controls

THE PAGE IS SYNTHETIC AND THAT IS STATED RATHER THAN GLossed. It is drawn here so the ground truth is
exact and no browser is needed; a real rendered page is a later rung and would need its DOM boxes as the
oracle. What this can therefore test is the MECHANISM -- can the basis recover a nested region hierarchy
from pixels at all -- and not yet performance on the web.

REGISTERED:
    1  parent-child F1 well above a RANDOM-PARENT control
    2  and above a FLAT control that claims every region is a child of the page, since a page-is-parent
       guess is right surprisingly often and would flatter any method that beat only random
    3  PART_WHOLE must be doing the work: the same pipeline with the hierarchy step removed must be worse
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema import PartWhole, Proximity, RegionScene    # noqa: E402

OUT = Path("data/language/schema_on_a_webpage.json")
W, H = 900, 700
BG = (250, 250, 250)


def draw_page(seed: int = 0):
    """A page image plus the TRUE nesting. Boxes exist only in the truth; the method sees pixels."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), BG, np.uint8)
    truth: dict = {}
    parent: dict = {}

    def block(name, box, colour, par=None):
        x0, y0, x1, y1 = box
        img[y0:y1, x0:x1] = colour
        truth[name] = box
        if par:
            parent[name] = par

    # header with a nav of items
    block("header", (0, 0, W, 70), (40, 60, 110))
    x = 24
    for i in range(5):
        w = int(rng.integers(80, 130))
        block(f"nav{i}", (x, 20, x + w, 50), (210, 220, 245), "header")
        x += w + 18

    # sidebar with links
    block("sidebar", (0, 90, 200, 620), (232, 232, 238))
    y = 110
    for i in range(6):
        block(f"link{i}", (16, y, 184, y + 26), (255, 255, 255), "sidebar")
        y += 40

    # content with cards, each card holding a title bar and a body
    block("content", (220, 90, W - 20, 620), (255, 255, 255))
    cy = 110
    for i in range(3):
        block(f"card{i}", (240, cy, W - 40, cy + 140), (244, 246, 250), "content")
        block(f"title{i}", (256, cy + 12, 560, cy + 40), (60, 90, 160), f"card{i}")
        block(f"body{i}", (256, cy + 52, W - 60, cy + 124), (250, 251, 253), f"card{i}")
        cy += 160

    block("footer", (0, 640, W, H), (60, 60, 66))
    return img, truth, parent


def regions_from_pixels(img: np.ndarray, min_px: int = 200) -> dict:
    """Regions of UNIFORM COLOUR. Pixels only, and no tag is read.

    The first version took connected components of "not the page background" and recovered SEVEN regions
    out of twenty-six, with every arm scoring an identical 0.571 -- the hierarchy step could not matter
    because there was no hierarchy left to find. NESTING MEANS THE PART IS INSIDE THE WHOLE AND CONNECTED
    TO IT, so a light nav item drawn on a dark header is one connected region with it, and connectivity
    destroys exactly the structure being looked for.

    Human vision does not group by connectivity, it groups by CONTRAST BOUNDARIES. Segmenting by colour
    uniformity keeps the nav item separate from the header it sits on, which is what makes a parent-child
    relation recoverable at all."""
    import cv2
    q = (img.astype(np.int16) // 16)                    # coarse colour classes; boundaries, not identity
    key = q[:, :, 0] * 4096 + q[:, :, 1] * 64 + q[:, :, 2]
    out, i = {}, 0
    for k in np.unique(key):
        m = (key == k).astype(np.uint8)
        n, lab, st, _c = cv2.connectedComponentsWithStats(m, 8)
        for j in range(1, n):
            if st[j, cv2.CC_STAT_AREA] < min_px:
                continue
            x, y, w, h = (st[j, cv2.CC_STAT_LEFT], st[j, cv2.CC_STAT_TOP],
                          st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT])
            if w * h >= img.shape[0] * img.shape[1] * 0.9:
                continue                                # the page ground itself is not an element
            i += 1
            out[f"r{i}"] = (float(x), float(y), float(x + w), float(y + h))
    return out


def gestalt_groups(scene: RegionScene, names: list) -> list:
    """Candidate wholes from PROXIMITY and size similarity -- Gestalt done with the basis, not a new rule.

    Two regions join when they are near relative to the scene's own scale AND comparable in size. The
    threshold is the scene's median element size, so nothing is chosen by me."""
    seen, groups = set(), []
    for a in names:
        if a in seen:
            continue
        grp = [a]
        seen.add(a)
        for b in names:
            if b in seen:
                continue
            near = Proximity(a, b).signed(scene)
            if near is None or near < 0.5:
                continue
            sa, sb = scene._area(a), scene._area(b)
            if sa <= 0 or sb <= 0 or max(sa, sb) / min(sa, sb) > 4.0:
                continue
            grp.append(b)
            seen.add(b)
        if len(grp) > 1:
            groups.append(grp)
    return groups


def recover(img, use_hierarchy: bool = True, random_parent: bool = False,
            flat: bool = False, seed: int = 0):
    """pixels -> regions -> Gestalt groups -> PART_WHOLE hierarchy -> parent-child edges."""
    regs = regions_from_pixels(img)
    names = sorted(regs)
    if flat:
        return {n: "PAGE" for n in names}, regs
    rng = np.random.default_rng(seed)
    if random_parent:
        return ({n: (rng.choice([m for m in names if m != n]) if len(names) > 1 else "PAGE")
                 for n in names}, regs)

    # candidate wholes: the Gestalt groups' bounding boxes, plus the regions themselves
    scene0 = RegionScene(regs)
    boxes = dict(regs)
    for i, g in enumerate(gestalt_groups(scene0, names)):
        xs = [regs[n] for n in g]
        boxes[f"g{i}"] = (min(b[0] for b in xs), min(b[1] for b in xs),
                          max(b[2] for b in xs), max(b[3] for b in xs))
    scene = RegionScene(boxes)

    par = {}
    for n in names:
        best, score = None, 0.0
        for w in boxes:
            if w == n:
                continue
            if not use_hierarchy:
                continue
            d = PartWhole(n, w).signed(scene)
            if d is None or d < 0.9:
                continue
            # the SMALLEST whole that fully contains it -- the immediate parent, not the page
            a = scene._area(w)
            if a <= 0:
                continue
            if best is None or a < score:
                best, score = w, a
        par[n] = best or "PAGE"
    return par, regs


def score_edges(pred: dict, regs: dict, truth: dict, parent: dict) -> dict:
    """Match recovered regions to true elements by box overlap, then compare parent-child edges."""
    def best_true(box):
        bx, by, bx1, by1 = box
        best, iou = None, 0.0
        for t, tb in truth.items():
            w = max(0.0, min(bx1, tb[2]) - max(bx, tb[0]))
            h = max(0.0, min(by1, tb[3]) - max(by, tb[1]))
            inter = w * h
            u = ((bx1 - bx) * (by1 - by) + (tb[2] - tb[0]) * (tb[3] - tb[1]) - inter)
            if u > 0 and inter / u > iou:
                best, iou = t, inter / u
        return best if iou > 0.4 else None

    ident = {r: best_true(b) for r, b in regs.items()}
    tp = fp = fn = 0
    for r, p in pred.items():
        t = ident.get(r)
        if t is None:
            continue
        true_par = parent.get(t, "PAGE")
        pred_par = "PAGE" if p == "PAGE" else (ident.get(p) or
                                              _group_to_true(p, regs, ident, pred))
        if pred_par == true_par:
            tp += 1
        else:
            fp += 1
            fn += 1
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    return {"matched": sum(1 for v in ident.values() if v),
            "precision": prec, "recall": rec,
            "f1": 2 * prec * rec / max(prec + rec, 1e-9)}


def _group_to_true(g, regs, ident, pred):
    """A recovered GROUP has no true element of its own; name it by the true parent its members share."""
    members = [r for r, p in pred.items() if p == g]
    ts = [ident.get(m) for m in members if ident.get(m)]
    return ts[0] if ts else None


def main() -> None:
    img, truth, parent = draw_page(seed=0)
    print(f"synthetic page {W}x{H}: {len(truth)} true elements, "
          f"{len(parent)} true parent-child edges")
    print("input is PIXELS ONLY -- nothing here reads a tag; the nesting is the oracle\n")

    regs = regions_from_pixels(img)
    print(f"regions recovered from pixels: {len(regs)}\n")

    arms = {
        "SCHEMA (Gestalt + PART_WHOLE)": dict(use_hierarchy=True),
        "no hierarchy step": dict(use_hierarchy=False),
        "flat: everything is the page": dict(flat=True),
        "random parent (control)": dict(random_parent=True),
    }
    print(f"{'method':<34}{'matched':>9}{'precision':>11}{'recall':>9}{'F1':>8}")
    res = {}
    for name, kw in arms.items():
        pred, r = recover(img, **kw)
        sc = score_edges(pred, r, truth, parent)
        res[name] = sc
        print(f"{name:<34}{sc['matched']:>9}{sc['precision']:>11.3f}"
              f"{sc['recall']:>9.3f}{sc['f1']:>8.3f}", flush=True)

    S = res["SCHEMA (Gestalt + PART_WHOLE)"]
    print(f"\n-> 1. beats the random-parent control: "
          f"{S['f1'] > res['random parent (control)']['f1'] + 0.05}  "
          f"({res['random parent (control)']['f1']:.3f})")
    print(f"-> 2. beats the flat page-is-parent guess: "
          f"{S['f1'] > res['flat: everything is the page']['f1'] + 0.05}  "
          f"({res['flat: everything is the page']['f1']:.3f})")
    print(f"-> 3. PART_WHOLE is doing the work: "
          f"{S['f1'] > res['no hierarchy step']['f1'] + 0.05}  "
          f"({res['no hierarchy step']['f1']:.3f})")
    print("\n   The page is SYNTHETIC, drawn here so the truth is exact. This tests the mechanism --")
    print("   whether the basis can recover a nested region hierarchy from pixels -- and NOT performance")
    print("   on the real web, which would need real renders with their DOM boxes as the oracle.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"true_elements": len(truth), "true_edges": len(parent),
                               "regions_from_pixels": len(regs), "arms": res},
                              indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
