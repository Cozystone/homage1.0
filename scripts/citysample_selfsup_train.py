# -*- coding: utf-8 -*-
"""Take what CARLA taught, and keep learning where nobody hands out metres.

    python scripts/citysample_selfsup_train.py --epochs 8

The supervised net learned depth from a simulator that reports ground truth. City Sample does not,
and neither does a street. So the question this answers is whether the thing it learned survives
contact with a world that will not label anything — and whether it can go on improving there using
only the fact that the body moved.

WHAT IS BEING MEASURED, AND WHAT CANNOT BE. There is no ground truth here, so nothing in this script
can report an error in metres, and any such number would be invented. What CAN be measured without
labels is whether the predicted depth explains the motion between real frames: warp frame t into
t+1 using the prediction, and see how wrong the picture looks. That is a genuine, falsifiable score
that a wrong depth map cannot fake, and it is the same quantity the training minimises — so the
honest reporting rule is that the number is only meaningful on frames HELD OUT of training.

THREE BASELINES, because a photometric number alone means nothing:

    identity     no warp at all — what you get for predicting nothing
    constant     one depth everywhere, the best single value
    supervised   the CARLA net, untouched, on these frames

The first two are the floor. Beating `identity` says the prediction carries real geometry rather
than a plausible-looking picture; failing to beat it would say the whole thing is decoration. The
third is the question the owner actually asked: does what it learned in CARLA apply in a game it has
never seen, the way a person who can judge distance in one city can judge it in another.

TRAIN AND TEST ARE SPLIT BY RUN, NOT BY FRAME. Consecutive frames of a 30fps capture are almost the
same picture; splitting at random would put a frame's own neighbour in the test set and the score
would be leakage. The same discipline as the town split in the supervised training, for the same
reason, and it is the one that quietly ruins this kind of measurement when skipped.
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

from packages.depth_learner.model import DepthNet                          # noqa: E402
from packages.depth_learner.selfsup import (PoseNet, bounded_log_depth, intrinsics,  # noqa: E402
                                            photometric, relative_pose, selfsup_loss, warp)

DRIVES = Path(r"D:\citysample_drive")
CKPT = Path(r"D:\carla\depth_model")
H, W = 240, 320


def _load_run(run: Path, limit: int = 0) -> np.ndarray:
    files = sorted(run.glob("*.npz"))
    if limit:
        files = files[:limit]
    out = []
    for f in files:
        rgb = np.load(f)["rgb"]
        ys = (np.arange(H) * (rgb.shape[0] / H)).astype(np.int32)
        xs = (np.arange(W) * (rgb.shape[1] / W)).astype(np.int32)
        out.append(rgb[ys][:, xs])
    return np.stack(out).astype(np.float32) / 255.0 if out else np.zeros((0, H, W, 3), np.float32)


def _triplets(frames: np.ndarray, stride: int = 3) -> list[tuple[int, int, int]]:
    """(previous, target, next). `stride` because adjacent frames at 30fps barely move, and a warp
    with no baseline has nothing to constrain depth with — the parallax IS the signal."""
    return [(i - stride, i, i + stride) for i in range(stride, len(frames) - stride)]


def _batch(frames: np.ndarray, trips: list, idx: np.ndarray, dev) -> tuple:
    t = lambda a: torch.from_numpy(a).permute(0, 3, 1, 2).contiguous().to(dev)
    p = np.stack([frames[trips[i][0]] for i in idx])
    c = np.stack([frames[trips[i][1]] for i in idx])
    n = np.stack([frames[trips[i][2]] for i in idx])
    return t(c), [t(p), t(n)]


@torch.no_grad()
def evaluate(depth_net, pose_net, frames, trips, K, dev, batch: int = 8) -> dict[str, float]:
    """Photometric error on held-out frames, against the floors. Lower is better; all in the same
    units, so they are directly comparable."""
    depth_net.eval()
    tot = {"model": 0.0, "identity": 0.0, "constant": 0.0}
    n = 0
    for s in range(0, len(trips), batch):
        idx = np.arange(s, min(s + batch, len(trips)))
        tgt, nbrs = _batch(frames, trips, idx, dev)
        d = bounded_log_depth(depth_net(tgt)).exp().unsqueeze(1)   # net squeezes the channel
        poses = [relative_pose(pose_net, tgt, nbrs[0], invert=True),
                 relative_pose(pose_net, tgt, nbrs[1], invert=False)]
        model = torch.cat([photometric(warp(s_, d, p, K), tgt) for s_, p in zip(nbrs, poses)],
                          1).min(1, keepdim=True)[0]
        ident = torch.cat([photometric(s_, tgt) for s_ in nbrs], 1).min(1, keepdim=True)[0]
        flat = torch.full_like(d, float(d.median()))
        const = torch.cat([photometric(warp(s_, flat, p, K), tgt) for s_, p in zip(nbrs, poses)],
                          1).min(1, keepdim=True)[0]
        k = len(idx)
        tot["model"] += model.mean().item() * k
        tot["identity"] += ident.mean().item() * k
        tot["constant"] += const.mean().item() * k
        n += k
    depth_net.train()
    return {k: round(v / max(n, 1), 5) for k, v in tot.items()}



# --- FORGETTING GUARD, added 2026-07-31 ------------------------------------------------------------
# The checkpoint this script produced on 2026-07-29 was measured on a blind seal at delta<1.25 = 0.1506,
# BELOW the constant baseline of 0.2181, from a starting point that scores 0.5268 on the same frames. The
# fine-tune destroyed a working model.
#
# AND THE INSTRUMENT COULD NOT HAVE SEEN IT. `evaluate()` reports photometric error and takes pose_net,
# which trains jointly -- so when the run's own log shows the CONSTANT baseline moving from 0.08493 to
# 0.18774, that is not depth getting worse, it is the metric moving underneath every arm at once. A number
# that shares parameters with the thing it is measuring cannot report on it.
#
# So the original domain is now held out and scored against GROUND TRUTH, which City Sample does not have
# and CARLA does. If the fine-tune degrades CARLA below where it started, the run refuses to overwrite the
# checkpoint unless --allow-forgetting is passed. Adapting to a new domain by losing the old one is a
# result worth having; it is not a checkpoint worth shipping by default.
def carla_holdout(depth_net, dev, limit: int = 120):
    """delta<1.25 on CARLA's own held-out towns, median-scaled, sky excluded. Ground truth, not a proxy."""
    import numpy as _np
    import torch as _t
    from packages.depth_learner.data import ROOT as _ROOT, build_split as _split, frames as _frames, load as _load
    sp = _split(_ROOT)
    paths = _frames(tuple(sorted(set(sp.val_town) | set(sp.val_episode))), _ROOT, stride=10)[:limit]
    if not paths:
        return None
    depth_net.eval()
    hits = []
    with _t.no_grad():
        for p in paths:
            rgb, dep, valid = _load(p)
            if not valid.any():
                continue
            y = _t.exp(depth_net(_t.from_numpy(rgb)[None].to(dev))).clamp(0.5, 200.0)
            pr = y.squeeze().cpu().numpy()
            a, b = pr[valid], dep[valid]
            a = a * (_np.median(b) / max(_np.median(a), 1e-9))
            r = _np.maximum(a / _np.maximum(b, 1e-9), b / _np.maximum(a, 1e-9))
            hits.append(float(_np.mean(r < 1.25)))
    depth_net.train()
    return float(_np.mean(hits)) if hits else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-forgetting", action="store_true", dest="allow_forgetting",
                    help="save even if the CARLA holdout degrades. Off by default: the 2026-07-29 run "
                         "shipped a checkpoint that scored below a constant baseline because nothing "
                         "was watching the original domain.")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--limit", type=int, default=900, help="frames per run")
    ap.add_argument("--stride", type=int, default=3, help="frames between a triplet's members")
    ap.add_argument("--init", default=str(CKPT / "depthnet.pt"))
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    # ONLY RUNS THAT ACTUALLY MOVED. `citysample_travel_capture` measures the parallax it achieved
    # and records the verdict; runs that failed it are excluded here rather than remembered. The
    # first two captures were unusable — 0.56 px of median flow, no growth with stride, so no
    # parallax and therefore no depth signal — and they were indistinguishable from good ones by
    # frame count, file size or error log. Training on them produced a model that never beat
    # not-warping, which was the correct answer to a corpus with nothing in it to learn.
    runs, skipped = [], []
    for d in sorted(DRIVES.glob("*")):
        if not d.is_dir() or len(list(d.glob("*.npz"))) < 100:
            continue
        try:
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            m = {}
        if m.get("usable_for_depth"):
            runs.append(d)
        else:
            skipped.append((d.name, m.get("parallax_px_at_320", "unmeasured")))
    if skipped:
        print("skipped (no measurable parallax): " +
              ", ".join(f"{n} ({p} px)" for n, p in skipped))
    if len(runs) < 2:
        sys.exit(f"need two runs with measured parallax under {DRIVES}; have {[r.name for r in runs]}")

    # split by RUN. The last one is held out entirely; see the module docstring.
    train_runs, test_run = runs[:-1], runs[-1]
    tr = np.concatenate([_load_run(r, args.limit) for r in train_runs])
    te = _load_run(test_run, args.limit)
    tr_trips, te_trips = _triplets(tr, args.stride), _triplets(te, args.stride)
    print(f"train {[r.name for r in train_runs]} -> {len(tr)} frames, {len(tr_trips)} triplets")
    print(f"test  {test_run.name} -> {len(te)} frames, {len(te_trips)} triplets  (held out)")

    depth_net = DepthNet().to(dev)
    init_note = "random"
    if Path(args.init).exists():
        ck = torch.load(args.init, map_location=dev, weights_only=False)
        depth_net.load_state_dict(ck["state_dict"] if isinstance(ck, dict) and "state_dict" in ck else ck)
        init_note = Path(args.init).name
    print(f"depth net initialised from: {init_note}")
    pose_net = PoseNet().to(dev)
    K = intrinsics(H, W, device=dev)

    before = evaluate(depth_net, pose_net, te, te_trips, K, dev)
    print(f"\nheld out, BEFORE any self-supervision: {before}")
    carla_before = carla_holdout(depth_net, dev)
    print(f"CARLA held-out delta<1.25 BEFORE: "
          f"{'%.4f' % carla_before if carla_before is not None else '(corpus unavailable)'}"
          f"   <- ground truth; this is the number the old run could not see")

    opt = torch.optim.Adam([{"params": depth_net.parameters(), "lr": args.lr},
                            {"params": pose_net.parameters(), "lr": args.lr * 5}])
    rng = np.random.default_rng(0)
    hist = []
    for ep in range(args.epochs):
        order = rng.permutation(len(tr_trips))
        run_loss, run_kept, nb, t0 = 0.0, 0.0, 0, time.time()
        for s in range(0, len(order) - args.batch + 1, args.batch):
            idx = order[s:s + args.batch]
            tgt, nbrs = _batch(tr, tr_trips, idx, dev)
            d = bounded_log_depth(depth_net(tgt)).exp().unsqueeze(1)   # net squeezes the channel
            poses = [relative_pose(pose_net, tgt, nbrs[0], invert=True),
                     relative_pose(pose_net, tgt, nbrs[1], invert=False)]
            out = selfsup_loss(tgt, nbrs, d, poses, K)
            opt.zero_grad()
            out["loss"].backward()
            torch.nn.utils.clip_grad_norm_(list(depth_net.parameters()) + list(pose_net.parameters()), 5.0)
            opt.step()
            run_loss += out["loss"].item()
            run_kept += out["kept"].item()
            nb += 1
        ev = evaluate(depth_net, pose_net, te, te_trips, K, dev)
        carla_now = carla_holdout(depth_net, dev)
        hist.append({"epoch": ep, "train_loss": round(run_loss / max(nb, 1), 5),
                     "automask_kept": round(run_kept / max(nb, 1), 3),
                     "carla_delta125": (round(carla_now, 4) if carla_now is not None else None), **ev})
        print(f"  ep{ep}  train {hist[-1]['train_loss']:.5f}  kept {hist[-1]['automask_kept']:.2f}  "
              f"| held-out model {ev['model']:.5f}  identity {ev['identity']:.5f}  "
              f"constant {ev['constant']:.5f}"
              f"{'' if carla_now is None else '  | CARLA d1 %.4f' % carla_now}"
              f"   ({time.time()-t0:.0f}s)")

    after = hist[-1]
    carla_after = hist[-1].get("carla_delta125")
    forgot = (carla_before is not None and carla_after is not None
              and carla_after < carla_before - 0.02)
    if forgot and not args.allow_forgetting:
        print(f"\nREFUSING TO SAVE: CARLA held-out delta<1.25 fell {carla_before:.4f} -> "
              f"{carla_after:.4f}. This is the failure that produced the 2026-07-29 checkpoint, which "
              f"scored below a constant baseline on a blind seal. Pass --allow-forgetting to keep it "
              f"anyway, and say in the proof why losing the original domain is acceptable.")
        Path("data/depth_learner/proofs").mkdir(parents=True, exist_ok=True)
        Path("data/depth_learner/proofs/citysample_selfsup_refused.json").write_text(
            json.dumps({"refused": True, "reason": "catastrophic forgetting on the CARLA holdout",
                        "carla_before": carla_before, "carla_after": carla_after,
                        "history": hist}, indent=2), encoding="utf-8")
        return
    CKPT.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": depth_net.state_dict(), "size": (W, H),
                "init": init_note, "carla_delta125_before": carla_before,
                "carla_delta125_after": carla_after,
                "forgetting_accepted": bool(forgot)}, CKPT / "citysample_selfsup.pt")

    print("\n=== held-out photometric error (no labels exist here; lower is better) ===")
    print(f"  identity (no warp)     {after['identity']:.5f}   <- the floor")
    print(f"  constant depth         {after['constant']:.5f}")
    print(f"  CARLA net, untouched   {before['model']:.5f}")
    print(f"  after self-supervision {after['model']:.5f}")
    verdict = ("the prediction explains the motion better than not warping at all"
               if after["model"] < after["identity"]
               else "NOT better than not warping — the prediction is not carrying geometry here")
    print(f"  -> {verdict}")

    proof = {"train_runs": [r.name for r in train_runs], "test_run": test_run.name,
             "init": init_note, "before": before, "history": hist,
             "beats_identity": bool(after["model"] < after["identity"]),
             "beats_constant": bool(after["model"] < after["constant"]),
             "improved_on_carla_init": bool(after["model"] < before["model"]),
             "note": "no ground truth exists in City Sample; these are photometric, not metric"}
    out = Path("data/depth_learner/proofs/citysample_selfsup.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
