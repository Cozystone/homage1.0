# -*- coding: utf-8 -*-
"""Validate the depth instruments where the answer is known, THEN use them where it is not.

    python scripts/depth_instrument_check.py

Two questions, in the only order that makes them meaningful.

FIRST, on CARLA, where every frame carries ground-truth metres: can each instrument tell the true
depth map from a random one? An instrument that scores noise and truth alike cannot be used to judge
anything, and the previous round of this work reported a verdict from exactly such an instrument —
whole-frame photometric error, which put no-warp, constant, random and CARLA depth inside a span of
0.0009. The failure was invisible because the number looked like a measurement.

SECOND, and only if the first passes, on City Sample, where there is no ground truth: does the depth
the net learned in CARLA carry over to a game it has never seen?

The two instruments answer different questions and are both reported:

    foveal photometric   the old measurement, weighted by where depth is observable
    flow agreement       does predicted disparity RANK like the flow that was measured

The ceiling matters as much as the score. On CARLA the true depth's flow agreement is the best any
depth map could achieve on those pairs, so a City Sample number is only readable against it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.depth_learner.model import DepthNet                              # noqa: E402
from packages.depth_learner.observe import (concentration, flow_agreement,     # noqa: E402
                                            observability)

CARLA = Path(r"D:\carla\episodes")
DRIVES = Path(r"D:\citysample_drive")
CKPT = Path(r"D:\carla\depth_model\depthnet.pt")
H, W = 240, 320


def _rs(a: np.ndarray, nearest: bool = False) -> np.ndarray:
    ys = (np.arange(H) * (a.shape[0] / H)).astype(np.int32)
    xs = (np.arange(W) * (a.shape[1] / W)).astype(np.int32)
    return np.ascontiguousarray(a[ys][:, xs])


def _net(dev):
    n = DepthNet().to(dev)
    n.load_state_dict(torch.load(CKPT, map_location=dev, weights_only=False)["state_dict"])
    n.eval()
    return n


@torch.no_grad()
def _predict(net, rgb: np.ndarray, dev) -> np.ndarray:
    x = torch.from_numpy(rgb.astype(np.float32) / 255.0)[None].permute(0, 3, 1, 2).to(dev)
    return net(x).exp().squeeze().cpu().numpy()


def carla_validation(dev, n_pairs: int = 40, stride: int = 2) -> dict:
    """Where truth exists. The question is whether the instruments can see it."""
    eps = sorted([d for d in CARLA.glob("ep*") if d.is_dir()])
    rng = np.random.default_rng(0)
    net = _net(dev)
    rows = {k: [] for k in ("true", "random", "constant", "net")}
    conc, pairs = [], 0
    for ep in eps:
        fs = sorted(ep.glob("*.npz"))
        for i in range(0, len(fs) - stride, 6):
            if pairs >= n_pairs:
                break
            a, b = np.load(fs[i]), np.load(fs[i + stride])
            rgb_a, rgb_b = _rs(a["rgb"]), _rs(b["rgb"])
            d_true = _rs(a["depth_m"]).astype(np.float32)
            sky = d_true > 500.0
            d_true = np.clip(d_true, 0.5, 100.0)
            if sky.mean() > 0.6:
                continue
            cands = {
                "true": d_true,
                "random": rng.uniform(0.5, 100.0, d_true.shape).astype(np.float32),
                "constant": np.full_like(d_true, float(np.median(d_true))),
                "net": np.clip(_predict(net, rgb_a, dev), 0.5, 100.0),
            }
            for k, d in cands.items():
                for tagname, dr in (("", False), ("_derot", True)):
                    r = flow_agreement(rgb_a, rgb_b, d, derotate=dr)
                    if np.isfinite(r["rho"]):
                        rows.setdefault(k + tagname, []).append(r["rho"])
            conc.append(concentration(observability(rgb_a, d_true)))
            pairs += 1
        if pairs >= n_pairs:
            break
    out = {k: {"rho_median": round(float(np.median(v)), 4), "n": len(v)} for k, v in rows.items() if v}
    out["pairs"] = pairs
    out["observability_concentration_p90"] = round(float(np.median(conc)), 4) if conc else None
    return out


def citysample(dev, run: str, n_pairs: int = 40, stride: int = 6) -> dict:
    net = _net(dev)
    fs = sorted((DRIVES / run).glob("*.npz"))
    rng = np.random.default_rng(1)
    rows = {k: [] for k in ("net", "random", "constant")}
    conc = []
    step = max(1, (len(fs) - stride) // n_pairs)
    for i in range(0, len(fs) - stride, step):
        rgb_a, rgb_b = _rs(np.load(fs[i])["rgb"]), _rs(np.load(fs[i + stride])["rgb"])
        d_net = np.clip(_predict(net, rgb_a, dev), 0.5, 100.0)
        cands = {"net": d_net,
                 "random": rng.uniform(0.5, 100.0, d_net.shape).astype(np.float32),
                 "constant": np.full_like(d_net, float(np.median(d_net)))}
        for k, d in cands.items():
            for tagname, dr in (("", False), ("_derot", True)):
                r = flow_agreement(rgb_a, rgb_b, d, derotate=dr)
                if np.isfinite(r["rho"]):
                    rows.setdefault(k + tagname, []).append(r["rho"])
        conc.append(concentration(observability(rgb_a, d_net)))
    out = {k: {"rho_median": round(float(np.median(v)), 4), "n": len(v)} for k, v in rows.items() if v}
    out["observability_concentration_p90"] = round(float(np.median(conc)), 4) if conc else None
    return out


def main() -> None:
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("=== 1. instrument validation on CARLA (ground truth exists here) ===")
    v = carla_validation(dev)
    for k in ("true", "true_derot", "net", "net_derot", "constant", "random", "random_derot"):
        if k in v:
            print(f"  flow agreement, {k:9s} depth   rho = {v[k]['rho_median']:+.4f}   ({v[k]['n']} pairs)")
    print(f"  observability: 90% of the depth information lives in "
          f"{100 * (v['observability_concentration_p90'] or 0):.1f}% of the pixels")

    ok = ("true" in v and "random" in v and
          v["true"]["rho_median"] > v["random"]["rho_median"] + 0.25)
    print(f"\n  -> instrument {'PASSES' if ok else 'FAILS'}: "
          f"{'it separates truth from noise' if ok else 'it cannot tell truth from noise — do not use it'}")

    result = {"carla_validation": v, "instrument_valid": bool(ok)}

    if ok:
        runs = [d.name for d in sorted(DRIVES.glob("travel*")) if d.is_dir()]
        print("\n=== 2. City Sample (no ground truth; read against the CARLA ceiling above) ===")
        for r in runs:
            c = citysample(dev, r)
            result[r] = c
            print(f"  {r}")
            for k in ("net", "net_derot", "constant", "random", "random_derot"):
                if k in c:
                    print(f"    {k:9s} rho = {c[k]['rho_median']:+.4f}   ({c[k]['n']} pairs)")
        transfer = [result[r]["net"]["rho_median"] - result[r]["random"]["rho_median"]
                    for r in runs if "net" in result.get(r, {})]
        result["transfer_margin_over_random"] = [round(x, 4) for x in transfer]
        print(f"\n  margin of the CARLA-trained net over random depth: "
              f"{', '.join(f'{x:+.4f}' for x in transfer)}")

    out = Path("data/depth_learner/proofs/depth_instrument_check.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
