# -*- coding: utf-8 -*-
"""Render one honest listen — the room as the cochlea delivers it, and what is still missing.

Companion to `show_what_the_eye_sees`. Nothing staged: the bands are whatever the filterbank
produces, the onsets are whatever the flux crosses, and the panel that says the ear has no words for
any of it says so as plainly as the eye's picture did.

Run:  python scripts/show_what_the_ear_hears.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                # noqa: E402

from packages.perception.ear import (F_HI, F_LO, HOP, N_BANDS,  # noqa: E402
                                     SR, listen, onsets)

OUT = "reports/what_the_ear_hears.png"
INK, DIM, HOT, COOL = "#E8E6E1", "#8A867E", "#E0704A", "#5FA8A0"


def draw(cg, path):
    secs = len(cg) * HOP / SR
    hz = np.linspace(F_LO, F_HI, N_BANDS)
    fig = plt.figure(figsize=(15, 5.6), facecolor="#141413")
    gs = fig.add_gridspec(2, 2, width_ratios=[2.1, 1], height_ratios=[3, 1], hspace=0.32,
                          wspace=0.22)

    ax = fig.add_subplot(gs[:, 0])
    ax.imshow(cg.T, aspect="auto", origin="lower", cmap="magma",
              extent=(0, secs, 0, N_BANDS))
    ticks = [0, 9, 19, 29, 39]
    ax.set_yticks(ticks)
    ax.set_yticklabels(["%d Hz" % hz[t] for t in ticks], color=DIM, fontsize=8)
    ax.set_xlabel("seconds", color=DIM, fontsize=9)
    ax.set_title("1 · the room, as the cochlea delivers it  (%d bands, log frequency, log energy)"
                 % N_BANDS, color=INK, fontsize=11, loc="left", pad=8)
    ax.tick_params(colors=DIM)
    for s in ax.spines.values():
        s.set_color("#2A2A28")

    o = onsets(cg)
    thr = float(np.percentile(o, 97))
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(np.arange(len(o)) * HOP / SR, o, color=COOL, lw=1.0)
    ax2.axhline(thr, color=HOT, lw=0.9, ls="--")
    ax2.set_title("2 · where energy RISES  (%d crossings)"
                  % int(sum(1 for i in range(1, len(o)) if o[i] > thr and o[i] >= o[i - 1])),
                  color=INK, fontsize=10, loc="left", pad=6)
    ax2.set_facecolor("#141413")
    ax2.tick_params(colors=DIM, labelsize=8)
    for s in ax2.spines.values():
        s.set_color("#2A2A28")

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis("off")
    e = cg.mean(0)
    top = np.argsort(e)[::-1][:3]
    ax3.text(0, 0.95, "3 · what it can say about it", color=INK, fontsize=10, va="top")
    ax3.text(0, 0.66, "loudest  " + ", ".join("~%dHz" % hz[i] for i in top),
             color=HOT, fontsize=9.5, va="top", family="monospace")
    ax3.text(0, 0.44, "quietest ~%dHz" % hz[int(e.argmin())],
             color=COOL, fontsize=9.5, va="top", family="monospace")
    ax3.text(0, 0.16, "and no word for any of it — nothing here\nhas learned what a sound IS yet.",
             color=DIM, fontsize=9, va="top")

    fig.suptitle("ATANOR · one listen to the room", color=INK, fontsize=13, x=0.012, ha="left")
    fig.tight_layout(rect=(0, 0.01, 1, 0.93))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=130, facecolor="#141413")
    print("wrote %s  (%.1f s, %d frames)" % (path, len(cg) * HOP / SR, len(cg)))


if __name__ == "__main__":
    cg = listen(5.0)
    if cg is None:
        print("nothing to listen with")
    else:
        draw(cg, OUT)
