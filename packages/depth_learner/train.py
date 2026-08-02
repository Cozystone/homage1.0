# -*- coding: utf-8 -*-
"""Train the depth organ on CARLA, and report what it learned against a null it cannot beat by luck.

    python -m packages.depth_learner.train --epochs 8

WHAT IS BEING TESTED, stated before the run. Not "can a CNN regress depth" — that has been settled
for a decade. The question is whether supervision from ONE renderer produces depth that survives a
change of world, because the owner's plan is CARLA -> City Sample -> GTA. So every run reports three
numbers and the gaps between them are the finding:

    train              what it fit
    val_episode        an unseen drive in a town it HAS seen
    val_town           towns it has never seen                       <- the one that matters

THE BASELINE IS MEASURED, NOT ASSUMED. A depth model is compared against predicting the training
set's median depth for every pixel — which on a road scene is a surprisingly strong baseline and has
embarrassed better projects than this one. If the network cannot beat a constant, it has learned
nothing about the image, whatever its loss curve did.

Nothing here is a gate. The numbers go on the record and the judgement is the owner's.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from . import data as D
from .model import MAX_M, MIN_M, DepthNet, metrics, silog_loss

OUT = Path(r"D:\carla\depth_model")


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


@torch.no_grad()
def evaluate(net: DepthNet, paths: list[Path], dev: torch.device, *, batch: int = 8,
             size: tuple[int, int] = (320, 240), limit: int | None = None) -> dict:
    net.eval()
    if limit:
        paths = paths[:limit]
    acc: dict[str, list[float]] = {}
    n = 0
    for rgb, dep, val in D.batches(paths, batch, size=size, shuffle=False):
        x = torch.from_numpy(rgb).to(dev)
        g = torch.from_numpy(dep).to(dev)
        v = torch.from_numpy(val).to(dev)
        m = metrics(net(x), g, v)
        for k, value in m.items():
            acc.setdefault(k, []).append(value)
        n += len(rgb)
    out = {k: round(float(np.mean(v)), 4) for k, v in acc.items() if k != "n_px"}
    out["frames"] = n
    return out


@torch.no_grad()
def constant_baseline(train_paths: list[Path], eval_paths: list[Path], dev: torch.device,
                      *, batch: int = 8, limit: int | None = None) -> dict:
    """Predict one number everywhere — the training median depth.

    This is the null the model has to beat. It is computed, not guessed, because a plausible-looking
    absrel means nothing until you know what a model that has not looked at the image scores."""
    meds = []
    for _rgb, dep, val in D.batches(train_paths[:200], batch, shuffle=False):
        d = dep[val]
        if d.size:
            meds.append(float(np.median(d)))
    const = float(np.median(meds)) if meds else 20.0

    acc: dict[str, list[float]] = {}
    for _rgb, dep, val in D.batches(eval_paths[:limit] if limit else eval_paths, batch, shuffle=False):
        g = torch.from_numpy(dep).to(dev)
        v = torch.from_numpy(val).to(dev)
        pred_log = torch.full_like(g, float(np.log(const)))
        for k, value in metrics(pred_log, g, v).items():
            acc.setdefault(k, []).append(value)
    out = {k: round(float(np.mean(v)), 4) for k, v in acc.items() if k != "n_px"}
    out["constant_m"] = round(const, 2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--stride", type=int, default=10, help="frames apart; 20Hz means 10 = 0.5s")
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--eval-limit", type=int, default=240)
    args = ap.parse_args()

    dev = _device()
    split = D.build_split()
    tr = D.frames(split.train, stride=args.stride)
    ve = D.frames(split.val_episode, stride=args.stride)
    vt = D.frames(split.val_town, stride=args.stride)
    print("split:", json.dumps(split.as_dict(), ensure_ascii=False))
    print(f"frames  train {len(tr)}  val_episode {len(ve)}  val_town {len(vt)}  (stride {args.stride})")

    net = DepthNet(width=args.width).to(dev)
    n_par = sum(p.numel() for p in net.parameters())
    print(f"model: {n_par/1e3:.0f}k params on {dev}")

    print("\nbaseline (constant = train median depth, no image seen):")
    base = {"val_episode": constant_baseline(tr, ve, dev, limit=args.eval_limit),
            "val_town": constant_baseline(tr, vt, dev, limit=args.eval_limit)}
    for k, v in base.items():
        print(f"  {k:12s} absrel_scaled {v.get('absrel_scaled')}  delta1 {v.get('delta1')}  (const {v.get('constant_m')}m)")

    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr, total_steps=max(1, args.epochs * (len(tr) // args.batch)))

    history = []
    for ep in range(args.epochs):
        net.train()
        t0, losses = time.time(), []
        for rgb, dep, val in D.batches(tr, args.batch, shuffle=True, seed=ep):
            x = torch.from_numpy(rgb).to(dev)
            g = torch.from_numpy(dep).to(dev)
            v = torch.from_numpy(val).to(dev)
            loss = silog_loss(net(x), g, v)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
            sched.step()
            losses.append(float(loss.detach()))
        row = {"epoch": ep, "loss": round(float(np.mean(losses)), 4),
               "seconds": round(time.time() - t0, 1),
               "val_episode": evaluate(net, ve, dev, limit=args.eval_limit),
               "val_town": evaluate(net, vt, dev, limit=args.eval_limit)}
        history.append(row)
        print(f"ep{ep}: loss {row['loss']:.4f} ({row['seconds']}s) | "
              f"val_episode absrel_s {row['val_episode'].get('absrel_scaled')} d1 {row['val_episode'].get('delta1')} | "
              f"val_town absrel_s {row['val_town'].get('absrel_scaled')} d1 {row['val_town'].get('delta1')}")

    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": net.state_dict(), "width": args.width,
                "size": (320, 240), "min_m": MIN_M, "max_m": MAX_M}, OUT / "depthnet.pt")
    report = {"split": split.as_dict(), "params": n_par, "args": vars(args),
              "baseline_constant": base, "history": history,
              "final": history[-1] if history else None,
              "train_on": evaluate(net, tr, dev, limit=args.eval_limit)}
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    f = history[-1] if history else {}
    print("\n--- final ---")
    print(f"  train        absrel_scaled {report['train_on'].get('absrel_scaled')}  delta1 {report['train_on'].get('delta1')}")
    print(f"  val_episode  absrel_scaled {f.get('val_episode',{}).get('absrel_scaled')}  delta1 {f.get('val_episode',{}).get('delta1')}")
    print(f"  val_town     absrel_scaled {f.get('val_town',{}).get('absrel_scaled')}  delta1 {f.get('val_town',{}).get('delta1')}")
    print(f"  constant     absrel_scaled {base['val_town'].get('absrel_scaled')}  delta1 {base['val_town'].get('delta1')}   <- must be beaten")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
