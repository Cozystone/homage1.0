# -*- coding: utf-8 -*-
"""Learning what a sound IS from what is visible when it happens — no labels anywhere.

    python scripts/av_cooccurrence.py --cache      # extract features once
    python scripts/av_cooccurrence.py --train

THE QUESTION THIS ANSWERS, and why it is the one the night said to ask. The self-repair loop ran
twenty-one identical cycles in seven hours and produced nothing, because a closed deterministic system
has a fixed point: with no new evidence from outside, repetition cannot discover. Meanwhile the ear
learned to hear and has no idea what anything IS -- forty looks last night, forty things it could not
name, six words to its name.

Co-occurrence is the way out and it is free. When a dog barks on screen, the bark and the dog arrive
TOGETHER, and a bark from a different clip does not. Nobody has to label either one. That pairing is
the supervision, and VGGSound is curated so the sound source is actually visible in the frame, which
is what makes the pairing mean something rather than being two unrelated streams that happen to share
a file.

AND IT IS THE KIND OF QUESTION THE ENCODER WAS MISSING. Yesterday's measurement: the visual encoder
declares 32 dimensions and uses about four, because `harvest` asks it exactly one question -- is this
the same track? Adding more questions of the same TYPE (depth, height, texture, colour, all readable
from the patch itself) did not help, twice. "What does this sound like" is not readable from the patch
at all. That is the first genuinely different question available.

BOTH ENCODERS ARE OURS. A small convolution for frames, a small network over the cochleagram for
sound, trained together by InfoNCE so that a clip's audio lands near its own video and away from
everyone else's. Nothing pretrained, nothing downloaded but the clips.

REGISTERED BEFORE RUNNING:
    1  on clips it never trained on, given a sound, the right video is retrieved above chance.
    2  a SHUFFLED control -- the same trained model, audio re-paired at random -- scores at chance.
       Without this, a model that has learned "clips from this dataset look like this" would pass.
    3  and an UNTRAINED pair of the same encoders scores at chance, or the architecture is doing the
       work rather than the learning.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

#: BOTH SOURCES, because they hold the same corpus in two shapes. The scraped directory has
#: `id_1.mp4`; the tarball unpacks to `.../video/id_000001.mp4`. Reading one would silently halve the
#: data and reading both without normalising names would silently lose every label -- `_stem` is what
#: keeps those two failures from being invisible.
CLIPS = [r"D:\atanor_data\vggsound", r"D:\atanor_data\vggsound_direct"]
CACHE = r"D:\atanor_data\vggsound_features.npz"
OUT = os.path.join(REPO, "data", "perception", "av_cooccurrence.json")
SIDE, FPS, DIM = 64, 2, 32


def _stem(path: str) -> str:
    """One name per clip whatever it was fetched as, so labels line up.

    `id_000001.mp4` from the tarball and `id_1.mp4` from the scraper are the same clip, and the csv
    calls it `id_1`. A mismatch here does not raise -- it just scores every class-level measurement
    against an empty label set, which is the quietest possible way to be wrong."""
    n = os.path.basename(path)
    n = n[:-4] if n.endswith(".mp4") else n
    m = re.match(r"^(.*)_(\d+)$", n)
    return "%s_%d" % (m.group(1), int(m.group(2))) if m else n


def _audio(path):
    from packages.perception.ear import SR, cochleagram
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, timeout=120).stdout
    if len(raw) < 4 * SR:
        return None
    return cochleagram(np.frombuffer(raw, dtype=np.float32))


def _video(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-vf",
                          "fps=%d,scale=%d:%d" % (FPS, SIDE, SIDE), "-pix_fmt", "rgb24",
                          "-f", "rawvideo", "-"], capture_output=True, timeout=120).stdout
    n = len(raw) // (SIDE * SIDE * 3)
    if n < 4:
        return None
    return np.frombuffer(raw, dtype=np.uint8)[:n * SIDE * SIDE * 3].reshape(n, SIDE, SIDE, 3)


def cache() -> None:
    """Features once, so the training loop is not an ffmpeg benchmark."""
    files = []
    for root in CLIPS:
        files += glob.glob(os.path.join(root, "*.mp4"))
        files += glob.glob(os.path.join(root, "**", "*.mp4"), recursive=True)
    files = sorted(set(files))
    A, V, keep = [], [], []
    t0 = time.time()
    for i, f in enumerate(files):
        try:
            cg, fr = _audio(f), _video(f)
        except Exception:
            cg = fr = None
        if cg is None or fr is None:
            continue
        # AUDIO AS A SHORT SUMMARY, not the whole roll: forty bands of mean and of variability. A
        # clip is ten seconds of one thing, and what identifies it is its spectral shape and how much
        # that shape moves, not the exact order of its frames.
        A.append(np.concatenate([cg.mean(0), cg.std(0)]).astype(np.float32))
        # UINT8, AND THE REASON IS A CRASH. Held as float32 this is 12,408 clips x 8 frames x
        # 64x64x3 x 4 bytes = 4.9 GB, and the compression step needs another copy of it -- the run
        # over the full corpus died silently, leaving a stale 1,160-clip cache that looked like a
        # finished one. Bytes are what came off the wire anyway; the divide by 255 moves to load time,
        # where it costs one batch instead of the whole corpus.
        V.append(fr[:: max(1, len(fr) // 8)][:8].astype(np.uint8))
        keep.append(_stem(f))
        if (i + 1) % 200 == 0:
            print("%d/%d  %.0fs" % (i + 1, len(files), time.time() - t0), flush=True)
    V = np.stack([v[:8] if len(v) >= 8 else np.concatenate([v] * 8)[:8] for v in V])
    np.savez_compressed(CACHE, audio=np.stack(A), video=V, names=np.array(keep))
    print("cached %d clips -> %s" % (len(keep), CACHE))


def _nets(a_dim):
    import torch
    import torch.nn as nn
    vid = nn.Sequential(
        nn.Conv2d(3, 16, 5, 2, 2), nn.ReLU(), nn.Conv2d(16, 32, 3, 2, 1), nn.ReLU(),
        nn.Conv2d(32, 64, 3, 2, 1), nn.ReLU(), nn.AdaptiveAvgPool2d(2), nn.Flatten(),
        nn.Linear(64 * 4, DIM))
    aud = nn.Sequential(nn.Linear(a_dim, 128), nn.ReLU(), nn.Linear(128, DIM))
    return vid, aud


def _embed(vid, aud, V, A, torch):
    b, n = V.shape[0], V.shape[1]
    V = V.astype(np.float32) / 255.0 if V.dtype == np.uint8 else V
    x = torch.from_numpy(V).permute(0, 1, 4, 2, 3).reshape(b * n, 3, SIDE, SIDE)
    ev = vid(x).reshape(b, n, DIM).mean(1)
    ea = aud(torch.from_numpy(A))
    ev = ev / ev.norm(dim=1, keepdim=True).clamp(min=1e-6)
    ea = ea / ea.norm(dim=1, keepdim=True).clamp(min=1e-6)
    return ev, ea


def retrieval(ev, ea, k: int, rng, shuffled=False) -> float:
    """Given a sound, pick its video out of k. Chance is 1/k."""
    E_v, E_a = ev.detach().numpy(), ea.detach().numpy()
    if shuffled:
        E_a = E_a[rng.permutation(len(E_a))]
    hits = 0
    trials = 0
    for i in range(len(E_a)):
        others = rng.choice([j for j in range(len(E_v)) if j != i], size=k - 1, replace=False)
        cand = np.concatenate([[i], others])
        if int(np.argmax(E_a[i] @ E_v[cand].T)) == 0:
            hits += 1
        trials += 1
    return hits / max(1, trials)


def train(epochs: int, seed: int) -> dict:
    import torch
    d = np.load(CACHE, allow_pickle=True)
    A, V = d["audio"], d["video"]
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(A))
    cut = int(len(A) * 0.8)
    tr, te = idx[:cut], idx[cut:]
    print("train %d clips | held out %d" % (len(tr), len(te)))
    torch.manual_seed(seed)
    vid, aud = _nets(A.shape[1])

    with torch.no_grad():
        ev0, ea0 = _embed(vid, aud, V[te], A[te], torch)
    before = {k: retrieval(ev0, ea0, k, np.random.default_rng(0)) for k in (2, 5, 10)}

    opt = torch.optim.Adam(list(vid.parameters()) + list(aud.parameters()), lr=2e-3)
    B = 48
    for ep in range(epochs):
        perm = rng.permutation(len(tr))
        tot = 0.0
        for s in range(0, len(tr) - B, B):
            b = tr[perm[s:s + B]]
            ev, ea = _embed(vid, aud, V[b], A[b], torch)
            logits = ea @ ev.T / 0.07
            lab = torch.arange(len(b))
            loss = 0.5 * (torch.nn.functional.cross_entropy(logits, lab)
                          + torch.nn.functional.cross_entropy(logits.T, lab))
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss)
        print("epoch %d loss %.3f" % (ep + 1, tot / max(1, len(tr) // B)), flush=True)

    vid.eval()
    aud.eval()
    with torch.no_grad():
        ev, ea = _embed(vid, aud, V[te], A[te], torch)
        # CAN IT EVEN FIT WHAT IT SAW? The decisive split between "the setup is broken" and "there is
        # not enough data": a contrastive model that cannot retrieve its own TRAINING clips has a
        # wiring or objective fault, and one that fits training and fails held-out is short of data.
        sub = tr[:len(te)]
        evt, eat = _embed(vid, aud, V[sub], A[sub], torch)
    on_train = {k: retrieval(evt, eat, k, np.random.default_rng(0)) for k in (2, 5, 10)}
    after = {k: retrieval(ev, ea, k, np.random.default_rng(0)) for k in (2, 5, 10)}
    control = {k: retrieval(ev, ea, k, np.random.default_rng(0), shuffled=True) for k in (2, 5, 10)}
    return {"held_out_clips": len(te), "trained": after, "on_training_clips": on_train,
            "untrained_control": before,
            "shuffled_control": control, "chance": {k: 1 / k for k in (2, 5, 10)}, "epochs": epochs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.cache:
        cache()
    if a.train:
        r = train(a.epochs, a.seed)
        print()
        print("%-26s %8s %8s %8s" % ("given a sound, pick from", "2", "5", "10"))
        for name, row in (("chance", r["chance"]), ("untrained encoders", r["untrained_control"]),
                          ("SHUFFLED pairs", r["shuffled_control"]),
                          ("trained, ON TRAINING clips", r["on_training_clips"]),
                          ("trained, held out", r["trained"])):
            print("%-26s %8.3f %8.3f %8.3f" % (name, row[2], row[5], row[10]))
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=1)
        print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
