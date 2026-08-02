# -*- coding: utf-8 -*-
"""ATANOR works out depth for itself, from moving. No simulator tells it anything.

    python scripts/learn_depth_from_motion.py --epochs 6

THE SUPERVISED NET IS NOT THE GOAL, it is the thing this is trying to do without. That one needed
CARLA to report metres, which a street will not do, and a screen cannot do — there is no metre
anywhere on a desktop. This one is given consecutive frames of a body that moved and nothing else.
Every label it trains on it derived itself, by noticing that near things sweep further across the
image than far ones.

GROUND TRUTH IS USED EXACTLY ONCE AND NEVER FOR TRAINING: to check, afterwards, on TOWNS THE NET
NEVER SAW, whether what it worked out is right. That separation is the entire experiment. If the GT
touched the optimiser at any point the result would say nothing about learning depth unsupervised,
and the split is by town rather than by frame because consecutive frames of a drive are nearly the
same picture and a frame split would leak the answer silently.

THREE NUMBERS, and each rules out a different way of being fooled:

    label accuracy      are the self-derived labels themselves right? (0.5 is chance)
    rank accuracy       does the trained net order held-out pairs correctly, judged by GT?
    supervised net      what the CARLA-labelled net scores on the same pairs — the ceiling

Beating chance says something was learned. Approaching the supervised net says what was learned is
most of what the labels were carrying. Neither is a claim about metres: this net predicts ORDER, and
order is all a monocular eye can honestly claim.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.depth_learner.model import DepthNet                                    # noqa: E402
from packages.depth_learner.ordinal import (pairs_from_truth, rank_accuracy,         # noqa: E402
                                            rank_pairs, ranking_loss)

CARLA = Path(r"D:\carla\episodes")
OUT = Path(r"D:\carla\depth_model")
H, W = 240, 320
VAL_TOWNS = ("Town06", "Town07")     # frozen before run 1 of the supervised training; kept here so
                                     # the two experiments are judged on the same held-out world


def _rs(a: np.ndarray) -> np.ndarray:
    ys = (np.arange(H) * (a.shape[0] / H)).astype(np.int32)
    xs = (np.arange(W) * (a.shape[1] / W)).astype(np.int32)
    return np.ascontiguousarray(a[ys][:, xs])


def _town(ep: Path) -> str:
    try:
        m = json.loads((ep / "meta.json").read_text(encoding="utf-8"))
        return str(m.get("town") or m.get("map") or "")
    except Exception:
        return ""


def harvest(eps: list[Path], stride: int = 2, every: int = 4, cap: int = 0) -> list[dict]:
    """Walk the drives and keep every comparison the motion licenses. No GT is read here."""
    out = []
    for ep in eps:
        fs = sorted(ep.glob("*.npz"))
        for i in range(0, len(fs) - stride, every):
            a = np.load(fs[i])
            rgb_a = _rs(a["rgb"])
            r = rank_pairs(rgb_a, _rs(np.load(fs[i + stride])["rgb"]))
            if len(r["pairs"]) < 24:
                continue
            out.append({"rgb": rgb_a, "xy": r["xy"], "pairs": r["pairs"], "conf": r["conf"],
                        "file": str(fs[i])})
            if cap and len(out) >= cap:
                return out
    return out


def truth_check(samples: list[dict], depth_of) -> dict[str, float]:
    """Score ordering against GT. The GT is loaded HERE and nowhere else."""
    lab, mod, n = [], [], 0
    for s in samples:
        gt = np.clip(_rs(np.load(s["file"])["depth_m"]).astype(np.float32), 0.5, 200.0)
        kp, truth = pairs_from_truth(gt, s["xy"], s["pairs"])
        if len(kp) < 20:
            continue
        lab.append(float(truth.mean()))                       # were the self-made labels right?
        d = depth_of(s["rgb"])
        mod.append(rank_accuracy(d, s["xy"], kp))             # is the net's ordering right?
        n += len(kp)
    return {"label_accuracy": round(float(np.mean(lab)), 4) if lab else float("nan"),
            "rank_accuracy": round(float(np.mean(mod)), 4) if mod else float("nan"),
            "pairs": n, "frames": len(lab)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--train-cap", type=int, default=700)
    ap.add_argument("--val-cap", type=int, default=140)
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    eps = sorted([d for d in CARLA.glob("ep*") if d.is_dir()])
    # SUBSTRING, because the meta records the full asset path 'Carla/Maps/Town06' and an equality
    # test against 'Town06' silently matches nothing. It did: the first run of this script fell
    # through to the by-episode fallback and held out episodes from the SAME towns it trained on,
    # which is the leak the supervised training's town split exists to prevent. The fallback printed
    # a warning and the warning was true; I nearly published the number anyway.
    hit = lambda e: any(v in _town(e) for v in VAL_TOWNS)
    val_eps = [e for e in eps if hit(e)]
    trn_eps = [e for e in eps if not hit(e)]
    if not val_eps:
        sys.exit(f"none of {VAL_TOWNS} found in episode meta — refusing to fall back to a "
                 f"by-episode split, which would train and test in the same towns")
    print(f"train {len(trn_eps)} episodes   held out {len(val_eps)} episodes in {VAL_TOWNS} "
          f"(towns the net never sees)")

    t0 = time.time()
    trn = harvest(trn_eps, cap=args.train_cap)
    val = harvest(val_eps, cap=args.val_cap)
    print(f"harvested {len(trn)} training frames / {len(val)} held-out, "
          f"{sum(len(s['pairs']) for s in trn)} self-made comparisons  ({time.time()-t0:.0f}s)")
    if not trn or not val:
        sys.exit("not enough usable motion — every frame pair was a turn or untrackable")

    net = DepthNet().to(dev)                     # RANDOM init: nothing supervised is carried in
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)

    @torch.no_grad()
    def predict(rgb: np.ndarray) -> np.ndarray:
        net.eval()
        x = torch.from_numpy(rgb.astype(np.float32) / 255.0)[None].permute(0, 3, 1, 2).to(dev)
        d = net(x).exp().squeeze().cpu().numpy()
        net.train()
        return d

    print("\nbefore any training (a random net orders pairs at chance):")
    print(" ", truth_check(val, predict))

    rng = np.random.default_rng(0)
    hist = []
    for ep in range(args.epochs):
        order = rng.permutation(len(trn))
        tot, nb = 0.0, 0
        for s in range(0, len(order) - args.batch + 1, args.batch):
            batch = [trn[i] for i in order[s:s + args.batch]]
            x = torch.from_numpy(np.stack([b["rgb"] for b in batch]).astype(np.float32) / 255.0)
            x = x.permute(0, 3, 1, 2).to(dev)
            pred = net(x)
            loss = sum(ranking_loss(pred[k], b["xy"], b["pairs"], b["conf"])
                       for k, b in enumerate(batch)) / len(batch)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
            tot += float(loss)
            nb += 1
        chk = truth_check(val, predict)
        hist.append({"epoch": ep, "train_loss": round(tot / max(nb, 1), 5), **chk})
        print(f"  ep{ep}  loss {hist[-1]['train_loss']:.5f}   held-out rank accuracy "
              f"{chk['rank_accuracy']:.4f}  (its own labels were {chk['label_accuracy']:.4f} right)")

    # the ceiling: the CARLA-supervised net on the same held-out comparisons
    sup = DepthNet().to(dev)
    ck = OUT / "depthnet.pt"
    sup_score = None
    if ck.exists():
        sup.load_state_dict(torch.load(ck, map_location=dev, weights_only=False)["state_dict"])
        sup.eval()

        @torch.no_grad()
        def sup_pred(rgb):
            x = torch.from_numpy(rgb.astype(np.float32) / 255.0)[None].permute(0, 3, 1, 2).to(dev)
            return sup(x).exp().squeeze().cpu().numpy()

        sup_score = truth_check(val, sup_pred)["rank_accuracy"]

    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": net.state_dict(), "size": (W, H), "kind": "ordinal_selfsup"},
               OUT / "ordinal_selfsup.pt")

    final = hist[-1]
    print("\n=== ordering accuracy on held-out worlds (0.5 = chance) ===")
    print(f"  the self-made labels themselves    {final['label_accuracy']:.4f}")
    print(f"  net trained ONLY on those labels   {final['rank_accuracy']:.4f}")
    if sup_score is not None:
        print(f"  net trained on CARLA ground truth  {sup_score:.4f}   <- the ceiling")
    print(f"  held-out comparisons: {final['pairs']} over {final['frames']} frames")

    proof = {"held_out": VAL_TOWNS if val_eps and _town(val_eps[0]) else "by-episode",
             "history": hist, "supervised_ceiling": sup_score,
             "ground_truth_used_for": "evaluation only — never in the optimiser",
             "claim": "ordering, not metres"}
    p = Path("data/depth_learner/proofs/ordinal_selfsup.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print("wrote", p)


if __name__ == "__main__":
    main()
