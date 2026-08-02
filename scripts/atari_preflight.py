# -*- coding: utf-8 -*-
"""Pre-flight on Atari BEFORE any object work runs. Four questions, asked first this time.

    python scripts/atari_preflight.py

The object track was parked because CARLA street-view could not score a grouping rule: movers were
0.3% of a frame with no traffic and 1.7% with it, the median mover blob was ELEVEN PIXELS, and 71% of
them were smaller than the smallest unit any grouping could emit. Two versions were judged for
failing to output something they structurally could not.

The re-entry condition was "a corpus where objects occupy meaningful area". This asks whether Atari
is that corpus, and asks BEFORE building anything — which is the rule this session promoted after
committing the same error three times.

    I  integrity      is the frame the game's frame, unoccluded and unscaled
    D  data           do independently-moving objects EXIST here, above a base rate
    R  resolution     are they LARGER than the smallest unit a grouping could emit
    X  discriminator  is there ground truth to score against, and does it separate real from random

X is the interesting one. Atari has no semantic segmentation, but the emulator's RAM holds sprite
coordinates, and those are ground truth nobody annotated — the same structure that made Win32's
Z-order usable for the desktop probe. Whether the specific bytes can be READ as positions is exactly
what a pre-flight should establish rather than assume, so this measures whether any RAM byte tracks a
moving object across frames instead of trusting a table of offsets from the internet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/atari/preflight.json")
GAME = "ALE/MsPacman-v5"


def rollout(n: int = 400, seed: int = 0):
    """Frames and RAM, from random play. Random because a policy would bias which objects appear."""
    import ale_py  # noqa: F401
    import gymnasium as gym

    env = gym.make(GAME, obs_type="rgb", frameskip=4, repeat_action_probability=0.0)
    obs, _ = env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    frames, rams = [obs], []
    ale = env.unwrapped.ale
    rams.append(ale.getRAM().copy())
    for _ in range(n - 1):
        obs, _r, term, trunc, _i = env.step(int(rng.integers(0, env.action_space.n)))
        frames.append(obs)
        rams.append(ale.getRAM().copy())
        if term or trunc:
            obs, _ = env.reset()
    env.close()
    return np.array(frames), np.array(rams)


def main() -> None:
    from packages.self_check.preflight import run as preflight

    frames, rams = rollout()
    H, W = frames.shape[1:3]
    print(f"{GAME}: {len(frames)} frames at {W}x{H}, RAM {rams.shape[1]} bytes\n")

    # --- D: do independently-moving things exist, and how much of the frame are they? ---
    import cv2
    grey = np.array([cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames])
    diff = np.abs(grey[1:].astype(np.int16) - grey[:-1].astype(np.int16))
    moving = diff > 12
    base_rate = float(moving.mean())

    # --- R: how big is a moving blob? ---
    sizes = []
    for m in moving[::10]:
        n, _lab, st, _c = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        sizes += [int(st[k, cv2.CC_STAT_AREA]) for k in range(1, n)]
    S = np.array(sizes) if sizes else np.array([0])
    print(f"D  moving pixels: {base_rate:.2%} of a frame   (CARLA street-view: 0.3-1.7%)")
    print(f"R  moving blobs : {len(S)} found, median {np.median(S):.0f} px, "
          f"p75 {np.percentile(S, 75):.0f}, max {S.max()} px")
    for cell, mn in ((4, 2), (6, 2), (8, 3)):
        floor = cell * cell * mn
        print(f"     cell {cell}px x min {mn} = {floor:>4} px floor -> "
              f"{100 * np.mean(S >= floor):.0f}% of blobs are findable")

    # --- X: does any RAM byte track a moving object? ---
    # No offset table is trusted. A byte that IS a sprite coordinate should correlate with where the
    # motion is, frame by frame. Measured against a shuffled-time control.
    cx = np.array([(np.argwhere(m)[:, 1].mean() if m.any() else np.nan) for m in moving])
    cy = np.array([(np.argwhere(m)[:, 0].mean() if m.any() else np.nan) for m in moving])
    ok = ~np.isnan(cx)
    R = rams[1:][ok].astype(float)
    best = []
    for axis, c in (("x", cx[ok]), ("y", cy[ok])):
        cors = []
        for b in range(R.shape[1]):
            v = R[:, b]
            if v.std() < 1e-9:
                continue
            cors.append((abs(float(np.corrcoef(v, c)[0, 1])), b))
        cors.sort(reverse=True)
        rng = np.random.default_rng(0)
        null = []
        for _ in range(200):
            v = R[:, cors[0][1]].copy()
            rng.shuffle(v)
            null.append(abs(float(np.corrcoef(v, c)[0, 1])))
        best.append((axis, cors[0][0], cors[0][1], float(np.percentile(null, 95))))
        print(f"X  RAM byte best |corr| with motion-{axis}: {cors[0][0]:.3f} at byte {cors[0][1]}   "
              f"(shuffled-time p95 {np.percentile(null, 95):.3f})")

    v = preflight(
        "Atari MsPacman as an object-discovery testbed",
        observed_source=GAME, intended_source=GAME, visible_frac=1.0,
        base_rate=base_rate, n=int(len(S)),
        target_size=float(np.median(S)), unit_size=32.0,     # 4px cells x 2 = 32px floor
        real_score=max(b[1] for b in best), control_score=max(b[3] for b in best))
    print("\n=== through the self-check gate ===")
    for c in v.checks:
        print(f"  {c.name:14} green={str(c.green):5} {c.detail}")
    print(f"  -> may_promote: {v.may_promote}")
    if not v.may_promote:
        for r in v.why_not():
            print("     -", r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"game": GAME, "frames": int(len(frames)), "size": [int(W), int(H)],
         "moving_fraction": round(base_rate, 5),
         "blob_median_px": float(np.median(S)), "blob_p75": float(np.percentile(S, 75)),
         "blob_max": int(S.max()),
         "ram_best": [{"axis": a, "corr": c, "byte": b, "null_p95": n} for a, c, b, n in best],
         "self_check": v.as_dict()}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
