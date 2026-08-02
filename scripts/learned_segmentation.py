# -*- coding: utf-8 -*-
"""E1: a learned segmenter, tested on the thing background subtraction cannot see by construction.

    python scripts/learned_segmentation.py

The incumbent is one line and two hand constants:

    sprite_mask = abs(frame - bg).sum(axis=2) > 40      blobs(min_px=10)

Per the eye document, motion segmentation is a stage humans ACQUIRE -- infants group by common fate long
before they use shape -- so a rule standing there is a training wheel, and it is upstream of every other
perception organ.

WHY A LEARNED SEGMENTER COULD ACTUALLY BE BETTER, rather than merely more fashionable. Subtraction can
only ever see CHANGE. A stationary sprite sits in the rollout median and is removed by construction --
that is precisely the defect that killed the pellet map, where looking for static pellets inside
background subtraction found 74 pixels and a map covering 0.7% of the screen. A model that sees
APPEARANCE can learn "a sprite looks like this" from moving examples and then find one that is not
moving. Subtraction cannot do that at any threshold.

SO THE DECISIVE TEST IS A GENERALISATION TEST, and it is registered before anything is trained:

    labels come ONLY from moving sprites   derived by the incumbent rule, so no hand-drawn masks
    evaluation includes STATIC PELLETS     which the label source never saw and cannot see
    pellet ground truth is itself derived  a pellet is a place something was, went, and never came back;
                                           behaviour, not appearance, and measured from raw frames

    1  on moving sprites, match the incumbent (its detection of the body is currently 100%)
    2  ON STATIC PELLETS, beat it -- the incumbent scores ~0 here by construction, so any real
       generalisation shows up as a gap that cannot be explained by a threshold
    3  beat the SAME architecture with random weights, or the learning bought nothing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import sprite_mask                       # noqa: E402
from scripts.atari_find_body import measured_warmup                # noqa: E402
from scripts.atari_play import make                               # noqa: E402

OUT = Path("data/atari/learned_segmentation.json")
PATCH = 7                  # odd, so a pixel has a centre


def rollout(steps: int, seed: int):
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)
    frames = []
    for _ in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        frames.append(obs.copy())
    env.close()
    return frames, bg


def pellet_truth(frames, tail: int = 60) -> np.ndarray:
    """Places something was, then permanently was not. Behaviour, not appearance, from RAW frames.

    The first version of this looked for static pellets inside background subtraction, which removes
    them by construction -- 74 pixels, a map covering 0.7% of the screen, and a predictor that
    degenerated to `stay`. Only the source changed; the definition did not."""
    a = np.array(frames[:tail], np.int16).mean(axis=0)
    b = np.array(frames[-tail:], np.int16).mean(axis=0)
    return (np.abs(a - b).sum(axis=2) > 60) & (a.sum(axis=2) > b.sum(axis=2))


def patches_at(frame: np.ndarray, ys, xs) -> np.ndarray:
    r = PATCH // 2
    H, W = frame.shape[:2]
    out = np.zeros((len(ys), PATCH, PATCH, 3), np.float32)
    for i, (y, x) in enumerate(zip(ys, xs)):
        y0, x0 = max(0, y - r), max(0, x - r)
        p = frame[y0:min(H, y + r + 1), x0:min(W, x + r + 1)]
        out[i, :p.shape[0], :p.shape[1]] = p
    return out / 255.0


def sample(frames, bg, n_per_frame: int = 400, seed: int = 0):
    """Positives are MOVING sprite pixels; negatives are background. No hand-drawn mask anywhere."""
    rng = np.random.default_rng(seed)
    X, Y = [], []
    for f in frames[::4]:
        m = sprite_mask(f, bg)
        ys, xs = np.where(m)
        if len(ys) < 8:
            continue
        k = min(n_per_frame // 2, len(ys))
        idx = rng.choice(len(ys), k, replace=False)
        X.append(patches_at(f, ys[idx], xs[idx]))
        Y.append(np.ones(k, np.int64))
        by, bx = np.where(~m)
        idx2 = rng.choice(len(by), k, replace=False)
        X.append(patches_at(f, by[idx2], bx[idx2]))
        Y.append(np.zeros(k, np.int64))
    return np.concatenate(X), np.concatenate(Y)


def make_net(dev):
    import torch.nn as nn
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, 1, 1), nn.ReLU(True),
        nn.Conv2d(16, 32, 3, 2, 1), nn.ReLU(True),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Linear(32, 2)).to(dev)


def fit(net, X, Y, dev, epochs: int = 4, lr: float = 2e-3, batch: int = 256, seed: int = 0):
    import torch
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    lossf = torch.nn.CrossEntropyLoss()
    rng = np.random.default_rng(seed)
    Xt = torch.from_numpy(X).permute(0, 3, 1, 2)
    Yt = torch.from_numpy(Y)
    for _ep in range(epochs):
        idx = rng.permutation(len(X))
        for s in range(0, len(idx) - batch + 1, batch):
            j = idx[s:s + batch]
            out = net(Xt[j].to(dev))
            loss = lossf(out, Yt[j].to(dev))
            opt.zero_grad()
            loss.backward()
            opt.step()
    return net


def score_pixels(net, frame, ys, xs, dev, batch: int = 4096) -> np.ndarray:
    import torch
    net.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(ys), batch):
            P = patches_at(frame, ys[s:s + batch], xs[s:s + batch])
            t = torch.from_numpy(P).permute(0, 3, 1, 2).to(dev)
            out.append(net(t).softmax(1)[:, 1].cpu().numpy())
    net.train()
    return np.concatenate(out) if out else np.zeros(0)


def main() -> None:
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    frames, bg = rollout(400, seed=3)
    pel = pellet_truth(frames)
    print(f"{len(frames)} frames, {dev}")
    print(f"pellet ground truth by BEHAVIOUR (was there, went, never returned): {int(pel.sum())} px\n")
    if pel.sum() < 200:
        sys.exit("too few pellet pixels to evaluate generalisation; refusing to report a number")

    X, Y = sample(frames, bg)
    print(f"training pixels: {len(X)}  ({int(Y.sum())} moving-sprite, {int((1-Y).sum())} background)")
    print("labels come ONLY from moving sprites. Pellets are never labelled.\n")

    last = frames[-1]
    mov = sprite_mask(last, bg)
    ys_m, xs_m = np.where(mov)
    still = pel & ~mov
    ys_p, xs_p = np.where(still)
    by, bx = np.where(~mov & ~pel)
    sub = np.random.default_rng(0).choice(len(by), min(4000, len(by)), replace=False)
    by, bx = by[sub], bx[sub]
    print(f"evaluation on the final frame: {len(ys_m)} moving px, {len(ys_p)} STATIC pellet px, "
          f"{len(by)} background px\n")

    rows = {}
    for name, trained in (("learned (labels from motion)", True), ("random weights (control)", False)):
        net = make_net(dev)
        if trained:
            fit(net, X, Y, dev)
        s_m = score_pixels(net, last, ys_m, xs_m, dev)
        s_p = score_pixels(net, last, ys_p, xs_p, dev)
        s_b = score_pixels(net, last, by, bx, dev)
        thr = float(np.percentile(s_b, 95))          # a threshold set by the BACKGROUND, not by me
        rows[name] = {"moving_recall": float((s_m > thr).mean()),
                      "STATIC_pellet_recall": float((s_p > thr).mean()),
                      "background_fpr": float((s_b > thr).mean()), "threshold": thr}
        r = rows[name]
        print(f"  {name:<30} moving {r['moving_recall']:>6.1%}   "
              f"STATIC PELLETS {r['STATIC_pellet_recall']:>6.1%}   "
              f"background FPR {r['background_fpr']:>5.1%}", flush=True)

    inc_m = 1.0                                     # subtraction defines the moving mask
    inc_p = float(mov[still].mean()) if still.sum() else 0.0
    print(f"  {'incumbent (subtraction)':<30} moving {inc_m:>6.1%}   "
          f"STATIC PELLETS {inc_p:>6.1%}   background FPR  0.0%")
    print("   (the incumbent's moving recall is 100% by definition -- it IS the moving mask -- and its")
    print("    static-pellet recall is ~0 by construction, which is the whole point of the test)")

    L, C = rows["learned (labels from motion)"], rows["random weights (control)"]
    print(f"\n-> 2. beats the incumbent on STATIC pellets: {L['STATIC_pellet_recall'] > inc_p + 0.05}  "
          f"({inc_p:.1%} -> {L['STATIC_pellet_recall']:.1%})")
    print(f"-> 3. beats random weights: "
          f"{L['STATIC_pellet_recall'] > C['STATIC_pellet_recall'] + 0.05}  "
          f"({C['STATIC_pellet_recall']:.1%})")
    print(f"-> 1. and does not give up moving sprites: {L['moving_recall'] > 0.8}  "
          f"({L['moving_recall']:.1%})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pellet_px": int(pel.sum()), "arms": rows,
                               "incumbent": {"moving_recall": inc_m,
                                             "STATIC_pellet_recall": inc_p}}, indent=2),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
