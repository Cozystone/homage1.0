# -*- coding: utf-8 -*-
"""Loss x pooling, trained identically, scored in a town none of them ever saw.

    python scripts/encoder_ablation_holdout.py

WHY. The retrained signature encoder reported effective dimensionality 19.44 against the current one's
5.96, and naming precision 1.000 against 0.734. Both numbers came from patches drawn from the retrain's OWN
episodes. Measured on three other towns the same two encoders give 4.14 and 2.48 -- so most of 19.44 was
track-specific variation memorised, and the honest gap is 4.14 vs 2.48 rather than 19.44 vs 5.96.

That comparison still is not clean, for two reasons. `signature_net.pt` records no training episodes at
all, so it may well have seen the towns it is being tested on. And the two checkpoints differ in BOTH the
loss and the pooling at once, so neither change can be credited.

This trains all four combinations from scratch on the same tracks, with the same patch radius, the same
epochs and the same seed, and scores them where none of them trained:

    triplet  + pool 1     what the organ shipped
    triplet  + pool 2     pooling alone
    InfoNCE  + pool 1     loss alone
    InfoNCE  + pool 2     the retrain

Naming is scored under a threshold calibrated in ONE holdout town and applied in the OTHERS, which is the
deployment case: a robot calibrates where it is and then drives somewhere else.

REGISTERED before running:
    1  InfoNCE + pool 2 has the highest holdout effective dimensionality of the four. If it does not, the
       retrain's advantage was provenance rather than method.
    2  the two changes are separable -- each single change beats triplet+pool1 on holdout dimensions. If
       only the pair helps, they interact and neither is a lever on its own.
    3  and the extra dimensions are USABLE: at a matched calibrated error rate the best encoder by
       dimensionality is not the worst by coverage. Dimensions that cost coverage are not an improvement.
"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.conformal_gate import conformal as CF                 # noqa: E402
from packages.perception import learned_signature as LS             # noqa: E402
from packages.perception import naming                              # noqa: E402
from packages.perception.coherence import tracks                    # noqa: E402

CORPUS = Path(r"D:\carla\episodes")
OUT = Path("data/perception/encoder_ablation_holdout.json")
CKPT_DIR = Path(r"D:\carla\depth_model\ablation")
TRAIN_EPISODES = ("ep441", "ep443", "ep444", "ep446")
CAL_TOWN = "ep050"
TEST_TOWNS = ("ep100", "ep112")
TAGS = {1: "road", 2: "sidewalk", 3: "building", 9: "vegetation", 10: "terrain", 14: "car"}
R = 20
DIM = 32
EPOCHS = 16
ALPHA = 0.10
N_ANCHOR = 10


def train_patches(episodes, frames_per_ep: int = 70, per_track: int = 12):
    """Patches grouped by POINT TRACK. No labels: a track is 'the same thing' by construction."""
    rng = np.random.default_rng(0)
    P, G = [], []
    gid = 0
    for ep in episodes:
        files = sorted(glob.glob(str(CORPUS / ep / "*.npz")))[:frames_per_ep]
        if not files:
            continue
        Z = [np.load(f) for f in files]
        fr = [z["rgb"] for z in Z]
        tr = tracks(fr, max_points=300)
        xy, alive = tr["xy"], tr["alive"]
        for j in range(alive.shape[1]):
            ts = np.where(alive[:, j])[0]
            if len(ts) < 10:
                continue
            for t in rng.choice(ts, min(per_track, len(ts)), replace=False):
                x, y = int(xy[t, j, 0]), int(xy[t, j, 1])
                if y < R or x < R or y + R >= fr[t].shape[0] or x + R >= fr[t].shape[1]:
                    continue
                P.append(fr[t][y - R:y + R, x - R:x + R])
                G.append(gid)
            gid += 1
    return np.stack(P), np.array(G)


def triplets_from(groups, n: int = 12000, seed: int = 0):
    rng = np.random.default_rng(seed)
    by = collections.defaultdict(list)
    for i, g in enumerate(groups):
        by[int(g)].append(i)
    keys = [k for k, v in by.items() if len(v) >= 2]
    out = []
    for _ in range(n):
        k = keys[int(rng.integers(len(keys)))]
        i, j = rng.choice(by[k], 2, replace=False)
        k2 = k
        while k2 == k:
            k2 = keys[int(rng.integers(len(keys)))]
        out.append((int(i), int(j), int(by[k2][int(rng.integers(len(by[k2])))])))
    return out


def labelled_patches(episodes, purity: float = 0.75, per_frame: int = 22, stride: int = 5,
                     cap: int = 40):
    """Near-pure patches per class, for SCORING only. Semantics never touch training."""
    rng = np.random.default_rng(0)
    out = collections.defaultdict(list)
    for f in [g for ep in episodes
              for g in sorted(glob.glob(str(CORPUS / ep / "*.npz")))[::stride][:cap]]:
        z = np.load(f)
        rgb, sem = z["rgb"], z["semantic"]
        for tag, name in TAGS.items():
            ys, xs = np.where(sem == tag)
            if len(ys) < 40:
                continue
            for i in rng.choice(len(ys), min(per_frame, len(ys)), replace=False):
                y, x = int(ys[i]), int(xs[i])
                if y < R or x < R or y + R >= rgb.shape[0] or x + R >= rgb.shape[1]:
                    continue
                if (sem[y - R:y + R, x - R:x + R] == tag).mean() >= purity:
                    out[name].append(rgb[y - R:y + R, x - R:x + R])
    return {k: np.stack(v) for k, v in out.items() if len(v) >= N_ANCHOR + 60}


def participation_ratio(E):
    X = np.asarray(E, np.float64)
    X = X - X.mean(0)
    sv = np.linalg.svd(X, compute_uv=False)
    return float((sv ** 2).sum() ** 2 / (sv ** 4).sum())


def speak_always(book, emb):
    rows = []
    for name, E in emb.items():
        for v in E:
            sims = sorted(((float(naming._unit(v) @ c), n) for n, c in book.centroids.items()),
                          reverse=True)
            rows.append((1.0 - sims[0][0], sims[0][1] == name))
    return np.array([r[0] for r in rows]), np.array([r[1] for r in rows])


def main() -> None:
    import torch

    P, G = train_patches(TRAIN_EPISODES)
    sizes = collections.Counter(G.tolist())
    print(f"train: {len(P)} patches / {len(sizes)} tracks from {', '.join(TRAIN_EPISODES)}   "
          f"(median {int(np.median(list(sizes.values())))} per track)")
    cal_raw = labelled_patches([CAL_TOWN])
    tst_raw = labelled_patches(list(TEST_TOWNS))
    names = sorted(set(cal_raw) & set(tst_raw))
    print(f"calibrate in {CAL_TOWN}, score in {', '.join(TEST_TOWNS)}   "
          f"classes {', '.join(names)}\n")
    trips = triplets_from(G)

    recipes = [("triplet + pool 1", "triplet", 1), ("triplet + pool 2", "triplet", 2),
               ("InfoNCE + pool 1", "infonce", 1), ("InfoNCE + pool 2", "infonce", 2)]
    rows = {}
    print(f"{'recipe':<20}{'eff dims (holdout)':>20}{'coverage':>11}{'precision':>11}"
          f"{'P(acc|wrong)':>15}{'kept?':>7}")
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    for tag, loss, pool in recipes:
        torch.manual_seed(0)
        if loss == "triplet":
            A = np.asarray(trips)
            pairs = LS.Pairs(P[A[:, 0]], P[A[:, 1]], P[A[:, 2]])
            net = LS.train(pairs, dim=DIM, epochs=EPOCHS, pool=pool)
        else:
            net = LS.train_infonce(P, G, dim=DIM, pool=pool, epochs=EPOCHS)
        net.eval()
        e_cal = {k: LS.embed(net, cal_raw[k], "cpu") for k in names}
        e_tst = {k: LS.embed(net, tst_raw[k], "cpu") for k in names}
        pr = participation_ratio(np.concatenate([e_tst[k] for k in names]))
        book = naming.anchor_from({k: e_cal[k][:N_ANCHOR] for k in names})
        s_cal, y_cal = speak_always(book, {k: v[N_ANCHOR:] for k, v in e_cal.items()})
        s_tst, y_tst = speak_always(book, e_tst)
        q = CF.calibrate(s_cal, y_cal, ALPHA)
        ev = CF.evaluate(s_tst, y_tst, q, ALPHA)
        kept = bool(ev.false_accept_given_wrong <= ALPHA + 1e-9)
        rows[tag] = {"loss": loss, "pool": pool, "eff_dims_holdout": pr,
                     "coverage": ev.accept_rate, "precision": 1.0 - ev.error_among_accepted,
                     "false_accept_given_wrong": ev.false_accept_given_wrong,
                     "promise_kept": kept, "cosine_cut": float(1.0 - q)}
        print(f"{tag:<20}{pr:>20.2f}{ev.accept_rate:>11.1%}"
              f"{1.0 - ev.error_among_accepted:>11.3f}{ev.false_accept_given_wrong:>15.3f}"
              f"{('yes' if kept else 'NO'):>7}")
        torch.save({"state_dict": net.state_dict(), "dim": DIM, "patch": R, "pool": pool,
                    "loss": loss, "train_episodes": list(TRAIN_EPISODES),
                    "eff_dims_holdout": pr, "holdout": list(TEST_TOWNS)},
                   CKPT_DIR / f"{loss}_pool{pool}.pt")

    base = rows["triplet + pool 1"]["eff_dims_holdout"]
    best = max(rows, key=lambda k: rows[k]["eff_dims_holdout"])
    separable = (rows["triplet + pool 2"]["eff_dims_holdout"] > base
                 and rows["InfoNCE + pool 1"]["eff_dims_holdout"] > base)
    worst_cov = min(rows, key=lambda k: rows[k]["coverage"])
    print(f"\n-> 1. InfoNCE + pool 2 is the widest on holdout: {best == 'InfoNCE + pool 2'}   "
          f"(best is {best} at {rows[best]['eff_dims_holdout']:.2f}, "
          f"baseline {base:.2f})")
    print(f"-> 2. the two changes are separable, each helping alone: {separable}   "
          f"(pool alone {rows['triplet + pool 2']['eff_dims_holdout']:.2f}, "
          f"loss alone {rows['InfoNCE + pool 1']['eff_dims_holdout']:.2f})")
    print(f"-> 3. the widest is not also the quietest: {best != worst_cov}   "
          f"({best} covers {rows[best]['coverage']:.1%}, "
          f"lowest is {worst_cov} at {rows[worst_cov]['coverage']:.1%})")
    print(f"\nreference: human object representations ~49 dimensions (Hebart et al. 2020), ~66 later")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"train_episodes": list(TRAIN_EPISODES), "calibration_town": CAL_TOWN,
                               "test_towns": list(TEST_TOWNS), "classes": names, "alpha": ALPHA,
                               "epochs": EPOCHS, "dim": DIM, "patch_radius": R,
                               "n_train_patches": int(len(P)), "n_tracks": len(sizes),
                               "recipes": rows,
                               "note": "all four trained from scratch on identical patches, tracks, "
                                       "epochs and seed; scored where none of them trained. Threshold "
                                       "calibrated in one town and applied in the others."},
                              indent=2), encoding="utf-8")
    print(f"wrote {OUT}  and four checkpoints to {CKPT_DIR}")


if __name__ == "__main__":
    main()
