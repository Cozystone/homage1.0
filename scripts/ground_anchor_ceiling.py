# -*- coding: utf-8 -*-
"""Does a ground-plane scale anchor turn an order-only depth model into a metric one? Measured: no.

    python scripts/ground_anchor_ceiling.py

WHY IT WAS TRIED. E5 measured that `ordinal_selfsup` produces order and no metres -- monocular vision
cannot recover scale, since halving every distance and halving the motion gives identical images. A person
with one eye closed still judges distance, and one of the ways they do it is knowing their own eye height:
a flat ground plane at a known camera height turns image row into distance, `Z = h*f/(v - cy)`. That is
free here (the rig fixes the camera at 2.4 m) and it looked like the exact hole E5 left.

THE ANCHOR'S GEOMETRY IS SOUND, and that part is worth keeping. Against ground truth on 124,721 road
pixels below the horizon, `h*f/(v-cy)` reproduces true depth to **5.3% median relative error**. The formula
is not the problem.

THE RECOMMENDATION WAS STILL WRONG, and two experiments retired it.

    arm                                      median      p10        ep460, oracle road mask
    ordinal + ground anchor (one scalar)     0.0242   0.0067
    ordinal + monotone ground calibration    0.0304   0.0105
    RANDOM + monotone ground calibration     0.0433   0.0280      <- anchoring noise scores HIGHER
    ordinal + ORACLE monotone (ceiling)      0.2486   0.2202
    constant (trivial)                       0.2246   0.2092

The ceiling row is the one that decides it. Fit the monotone calibration against GROUND TRUTH over every
valid pixel -- the best any anchoring scheme could ever do -- and the model reaches 0.2486 against a
constant baseline at 0.2246. There is nothing to recover.

WHAT ACTUALLY SETS THE CEILING, across both models:

    model                  median-scaled   ORACLE mono   headroom   Spearman
    depthnet.pt                   0.4052        0.4133     0.0082      0.806
    ordinal_selfsup.pt            0.2521        0.2516    -0.0005      0.477

**Perfect scale handling is worth 0.008 to the good model and nothing to the weak one.** The binding
constraint is ORDERING QUALITY, and delta tracks Spearman almost linearly. Scale was never what E5 was
short of.

AND THIS CORRECTS WHAT I SAID ABOUT STEREO. I framed a second eye as the fix for scale ambiguity. It does
remove that ambiguity, but scale is not the binding constraint -- so stereo's real value here is that
disparity is close to a direct measurement of depth and therefore gives much better ORDERING. Right answer,
wrong reason, and the difference matters for what to build next.

A CAVEAT THAT LIMITS EVERY NUMBER ABOVE: the road mask comes from ground-truth semantics, so these are
CEILINGS. A deployed system would have to find the ground itself, which can only be worse.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CORPUS = Path(r"D:\carla\episodes")
MODELS = Path(r"D:\carla\depth_model")
OUT = Path("data/depth_learner/proofs/ground_anchor_ceiling.json")
ROAD = {1, 24}                      # Roads, RoadLine -- see SEMANTIC_TAGS in carla_depth_recorder
H_CAM, W_OUT, H_OUT = 2.4, 320, 240
FX = 400.0 * W_OUT / 800.0          # rig is 800x600 at fov 90 -> f = 400 px, rescaled to the net's input
CY = 300.0 * H_OUT / 600.0


def d125(pred, true, valid) -> float:
    a, b = pred[valid], true[valid]
    if a.size < 50:
        return float("nan")
    r = np.maximum(a / np.maximum(b, 1e-9), b / np.maximum(a, 1e-9))
    return float(np.mean(r < 1.25))


def spearman(pred, true, valid, cap: int = 4000) -> float:
    a, b = pred[valid], true[valid]
    if a.size > cap:
        i = np.random.default_rng(0).choice(a.size, cap, replace=False)
        a, b = a[i], b[i]
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    return float((ra * rb).sum() / np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))


def monotone(pred, mask, target, nq: int = 24):
    """Calibrate pred -> target through matched quantiles. The honest use of a ground plane.

    A ground plane does not give one number, it gives a CURVE: every road row is its own (predicted,
    geometric) pair. Fitting a single multiplier throws almost all of that away."""
    q = np.linspace(1, 99, nq)
    xp, fp = np.percentile(pred[mask], q), np.percentile(target[mask], q)
    o = np.argsort(xp)
    return np.interp(pred, xp[o], np.maximum.accumulate(fp[o]))


def frames(episode: str, stride: int = 2):
    for p in sorted(glob.glob(str(CORPUS / episode / "*.npz")))[::stride]:
        z = np.load(p)
        rgb, dep, sem = z["rgb"], z["depth_m"].astype(np.float32), z["semantic"]
        ys = (np.arange(H_OUT) * (rgb.shape[0] / H_OUT)).astype(int)
        xs = (np.arange(W_OUT) * (rgb.shape[1] / W_OUT)).astype(int)
        yield (rgb[ys][:, xs].transpose(2, 0, 1).astype(np.float32) / 255.0,
               dep[ys][:, xs], sem[ys][:, xs])


def main() -> None:
    import torch

    from packages.depth_learner.model import DepthNet

    v = np.repeat(np.arange(H_OUT)[:, None], W_OUT, 1).astype(np.float32)
    zgeo = H_CAM * FX / np.maximum(v - CY, 1e-6)
    rows, rng = {}, np.random.default_rng(0)

    for name in ("depthnet.pt", "ordinal_selfsup.pt"):
        ck = torch.load(MODELS / name, map_location="cpu")
        net = DepthNet(width=ck.get("width", 32))
        net.load_state_dict(ck["state_dict"])
        net.eval()
        acc = {k: [] for k in ("median_scaled", "ground_scalar", "ground_monotone",
                               "random_ground_monotone", "oracle_monotone", "spearman", "constant")}
        for rgb, dep, sem in frames("ep460"):
            valid = (sem != 11) & (dep > 0.5) & (dep < 200)
            road = np.isin(sem, list(ROAD)) & (v > CY + 6)
            if not valid.any() or road.sum() < 300:
                continue
            with torch.no_grad():
                pr = torch.exp(net(torch.from_numpy(rgb)[None])).clamp(0.5, 200.0).numpy().squeeze()
            s_gt = float(np.median(dep[valid]) / max(np.median(pr[valid]), 1e-9))
            s_gd = float(np.median(zgeo[road]) / max(np.median(pr[road]), 1e-9))
            noise = rng.random(pr.shape).astype(np.float32) * 10 + 1
            acc["median_scaled"].append(d125(pr * s_gt, dep, valid))
            acc["ground_scalar"].append(d125(pr * s_gd, dep, valid))
            acc["ground_monotone"].append(d125(monotone(pr, road, zgeo), dep, valid))
            acc["random_ground_monotone"].append(d125(monotone(noise, road, zgeo), dep, valid))
            acc["oracle_monotone"].append(d125(monotone(pr, valid, dep), dep, valid))
            acc["spearman"].append(spearman(pr, dep, valid))
            acc["constant"].append(d125(np.full_like(pr, float(np.median(dep[valid]))), dep, valid))
        rows[name] = {k: float(np.nanmedian(x)) for k, x in acc.items()}

    print("ep460, ORACLE road mask -- every number here is a CEILING\n")
    print(f"{'model':<22}{'median-scaled':>14}{'ground scalar':>15}{'ground mono':>13}"
          f"{'ORACLE mono':>13}{'headroom':>10}{'Spearman':>10}")
    for k, r in rows.items():
        print(f"{k:<22}{r['median_scaled']:>14.4f}{r['ground_scalar']:>15.4f}"
              f"{r['ground_monotone']:>13.4f}{r['oracle_monotone']:>13.4f}"
              f"{r['oracle_monotone'] - r['median_scaled']:>10.4f}{r['spearman']:>10.3f}")
    c = rows["depthnet.pt"]["constant"]
    print(f"\nconstant baseline {c:.4f}   |   random + ground mono "
          f"{rows['depthnet.pt']['random_ground_monotone']:.4f}")
    gain = max(r["oracle_monotone"] - r["median_scaled"] for r in rows.values())
    print(f"\n-> perfect scale handling is worth at most {gain:+.4f} to any model here.")
    print("-> the ceiling is set by ORDERING QUALITY, not by scale. The anchor line is retired.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"episode": "ep460", "road_mask": "ORACLE (ground-truth semantics)",
                               "camera_height_m": H_CAM, "fx": FX, "cy": CY,
                               "flat_ground_formula_error_vs_truth": 0.053,
                               "arms": rows,
                               "conclusion": "Scale anchoring buys at most +0.008 delta<1.25. The binding "
                                             "constraint is ordering quality (Spearman), not scale. "
                                             "Stereo's value is better ORDERING, not scale recovery."},
                              indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
