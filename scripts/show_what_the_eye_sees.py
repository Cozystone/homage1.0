# -*- coding: utf-8 -*-
"""Render one honest look — what the eye found, what it could name, what it refused to name.

Owner asked to see how ATANOR looks and recognises. This draws the actual pipeline on an actual
frame, with nothing staged: the regions are whatever `common_fate.things` returns, the words are
whatever `naming` returns, and the declines are drawn as prominently as the names because they are
most of what happens.

Run:  python scripts/show_what_the_eye_sees.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")
import matplotlib.patches as mpatches                          # noqa: E402
import matplotlib.pyplot as plt                                # noqa: E402

from packages.perception import common_fate as CF              # noqa: E402
from packages.perception import learned_signature as LS        # noqa: E402
from packages.perception import naming                         # noqa: E402
from packages.perception.object_permanence import centroid     # noqa: E402

OUT = "reports/what_the_eye_sees.png"
NET = r"D:\carla\depth_model\signature_net_v2.pt"
BOOK = "data/perception/name_book.json"

INK, DIM, HOT, COOL = "#E8E6E1", "#8A867E", "#E0704A", "#5FA8A0"


def _pair_from_camera(side=384):
    from packages.live_selfhood_cycle.eyes import grab
    a = grab("camera", side=side)
    time.sleep(0.7)
    b = grab("camera", side=side)
    return (np.asarray(a), np.asarray(b)) if a is not None and b is not None else (None, None)


def _pair_from_episode(ep="ep202", t=14):
    import glob
    fs = sorted(glob.glob(os.path.join(r"D:\carla\episodes", ep, "*.npz")))
    if len(fs) <= t + 1:
        return (None, None)
    return (np.load(fs[t])["rgb"], np.load(fs[t + 1])["rgb"])


def _read(a, b, net, patch, book):
    """One look, end to end, exactly as the living loop runs it."""
    from packages.perception.one_eye import OneEye
    eye = OneEye()
    eye.look(a)
    r = eye.look(b)
    d = r.as_dict() if hasattr(r, "as_dict") else {}
    lumps = CF.things(a, b)
    rows = []
    for lg in lumps:
        xy = centroid(lg.mask)
        q = LS.crop_at(a, (int(xy[0]), int(xy[1])), patch)
        word, cos = (None, 0.0)
        if q is not None:
            e = LS.embed(net, q[None])[0]
            word, cos = naming.name_of(book, e)
        rows.append({"mask": lg.mask, "xy": xy, "px": int(lg.mask.sum()),
                     "word": word, "cos": float(cos or 0.0)})
    return d, rows


def _panel(ax, img, title):
    ax.imshow(img)
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=8)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2A2A28")


def draw(a, b, d, rows, where: str, path: str) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.4), facecolor="#141413")
    for ax in axes:
        ax.set_facecolor("#141413")

    _panel(axes[0], a, "1 · what arrived")

    over = a.astype(float).copy() * 0.35
    for i, r in enumerate(rows):
        c = np.array(matplotlib.colors.to_rgb(HOT if r["word"] else COOL)) * 255.0
        over[r["mask"]] = 0.45 * over[r["mask"]] + 0.55 * c
    _panel(axes[1], over.astype(np.uint8),
           "2 · what held together as a thing  (%d found)" % len(rows))
    for r in rows:
        axes[1].plot(r["xy"][0], r["xy"][1], "o", ms=4, mfc="none",
                     mec=HOT if r["word"] else COOL)

    axes[2].axis("off")
    axes[2].set_facecolor("#141413")
    named = [r for r in rows if r["word"]]
    y = 0.96
    axes[2].text(0, y, "3 · what it could call them", color=INK, fontsize=11, va="top")
    y -= 0.11
    axes[2].text(0, y, "vocabulary: %d words, all street scenes" % len(book.centroids),
                 color=DIM, fontsize=9, va="top")
    y -= 0.09
    if not rows:
        axes[2].text(0, y, "nothing moved together — no thing to name", color=DIM,
                     fontsize=10, va="top")
    for r in sorted(rows, key=lambda z: -z["px"])[:9]:
        y -= 0.085
        if r["word"]:
            axes[2].text(0, y, "%-11s  %5d px   cos %.2f" % (r["word"], r["px"], r["cos"]),
                         color=HOT, fontsize=10, va="top", family="monospace")
        else:
            axes[2].text(0, y, "%-11s  %5d px   closest %.2f, under 0.78"
                         % ("(no word)", r["px"], r["cos"]),
                         color=COOL, fontsize=10, va="top", family="monospace")
    y -= 0.14
    axes[2].text(0, y, "unexplained  %.2f     my own doing  %.2f"
                 % (float(d.get("magnitude") or 0), float(d.get("self_explained") or 0)),
                 color=INK, fontsize=10, va="top", family="monospace")
    y -= 0.10
    axes[2].text(0, y, "named %d of %d.  A decline is the honest answer,\nnot a gap to be filled."
                 % (len(named), len(rows)), color=DIM, fontsize=9.5, va="top")

    fig.legend(handles=[mpatches.Patch(color=HOT, label="got a word"),
                        mpatches.Patch(color=COOL, label="declined — nothing close enough")],
               loc="lower left", ncol=2, frameon=False, labelcolor=DIM, fontsize=9,
               bbox_to_anchor=(0.012, 0.005))
    fig.suptitle("ATANOR · one look at %s" % where, color=INK, fontsize=13, x=0.012, ha="left")
    fig.tight_layout(rect=(0, 0.045, 1, 0.94))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=130, facecolor="#141413")
    print("wrote %s  (%d things, %d named)" % (path, len(rows), len(named)))


if __name__ == "__main__":
    from pathlib import Path
    net, patch = LS.load_encoder(NET)
    book = naming.NameBook.load(Path(BOOK))
    a, b = _pair_from_camera()
    if a is None:
        a, b = _pair_from_episode()
        where = "a street it has never driven"
    else:
        where = "the room, through the webcam"
    d, rows = _read(a, b, net, patch, book)
    draw(a, b, d, rows, where, OUT)

    a2, b2 = _pair_from_episode()
    if a2 is not None:
        d2, rows2 = _read(a2, b2, net, patch, book)
        draw(a2, b2, d2, rows2, "a street it has never driven",
             "reports/what_the_eye_sees_street.png")
