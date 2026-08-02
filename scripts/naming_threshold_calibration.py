# -*- coding: utf-8 -*-
"""The namer's silence threshold, calibrated instead of chosen — and the fair test of the wider space.

    python scripts/naming_threshold_calibration.py

WHY THIS EXISTS. Retraining the signature encoder took effective dimensionality from 5.96 to 19.44 and
naming precision from 0.734 to 1.000, but COVERAGE FELL from 49.4% to 25.6%. That drop is not evidence
against the new space: `naming.name_of` refuses below a hard-coded cosine of 0.78, and 0.78 was picked
against a six-dimensional space. Cosines shrink as a space widens -- more axes means less of any two
vectors' mass can be shared -- so the same number is a stricter rule in the new space than the old one.

WHICH MEANS THE HONEST COMPARISON IS AT MATCHED ERROR, NOT AT A MATCHED NUMBER. Fix the certified error
rate, let each space have whatever threshold that rate requires, and read off COVERAGE. Whichever space
speaks more often while promising the same error is the better space, and the comparison cannot be gamed by
the constant.

AND THE THRESHOLD IS CALIBRATED, NOT TUNED. `packages/conformal_gate` already does exactly this: a
split-conformal quantile over held-out (score, correct?) pairs returning a q_hat that certifies
P(accept | wrong) <= alpha. Choosing a threshold by looking at the coverage it produces is fitting to the
test set; taking it from a calibration split I never score on is not. This project has re-implemented that
organ once already, which is the reason for the import rather than the twelve lines it would take.

The nonconformity score is 1 - best_cosine, so higher means less confident, which is the direction the
gate expects. Calibration uses SPEAK-ALWAYS naming, because a calibration split needs wrong answers in it
and the current threshold is what removes them.

A CORRECTION THIS SCRIPT EXISTS TO MAKE, and it is against my own headline. "effective dims 19.44,
naming precision 1.000" was measured on patches drawn from ep441/443/444/446 -- THE EPISODES THE RETRAIN
TRAINED ON. Different patches from the same pool is not held out; a track supplies a dozen views of one
object and the anchor and the test patch can be two views of the same car. The first version of this file
then printed "not the episodes either encoder trained on" about ep446, which was in that list. So the
scoring here runs on ep050/ep100/ep112 -- different towns, never touched by the retrain -- and whatever
those say replaces the 1.000.

TWO CONFOUNDS ALSO FIXED HERE. The two checkpoints declare different patch radii (24 and 20), so each is
fed patches at its own scale rather than both at one radius. And `signature_net.pt` records no training
episodes at all, so "held out" is asserted for the retrained encoder only; for the current one it is
merely unverified.

REGISTERED before running:
    1  at a matched certified alpha, the RETRAINED space covers MORE than the current one. If it covers
       less, the extra dimensions are not usable and 19.44 is noise.
    2  the gate keeps its promise on held-out data: achieved P(accept | wrong) <= alpha for both.
    3  the calibrated threshold for the retrained space sits BELOW 0.78 in cosine, which would be the
       direct explanation of the coverage drop rather than a story about it.
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

CORPUS = Path(r"D:\carla\episodes")
NET_V1 = Path(r"D:\carla\depth_model\signature_net.pt")
NET_V2 = Path(r"D:\carla\depth_model\signature_net_v2.pt")
OUT = Path("data/perception/naming_threshold_calibration.json")
TAGS = {1: "road", 2: "sidewalk", 3: "building", 9: "vegetation", 10: "terrain", 14: "car"}
ALPHAS = (0.05, 0.10, 0.20)
N_ANCHOR = 10
RETRAIN_EPISODES = ("ep441", "ep443", "ep444", "ep446")   # what v2 saw; v1 records none
HOLDOUT = ("ep050", "ep100", "ep112")                     # different towns, disjoint from those


def harvest(episodes, r: int, purity: float = 0.75, per_frame: int = 22, stride: int = 5,
            cap: int = 40):
    """Near-pure patches per class, at THIS encoder's own patch radius. Semantics score only."""
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
                if y < r or x < r or y + r >= rgb.shape[0] or x + r >= rgb.shape[1]:
                    continue
                if (sem[y - r:y + r, x - r:x + r] == tag).mean() >= purity:
                    out[name].append(rgb[y - r:y + r, x - r:x + r])
    return {k: np.stack(v) for k, v in out.items() if len(v) >= N_ANCHOR + 80}


def participation_ratio(E):
    """Effective dimensionality, measured where it counts: on episodes the encoder never trained on."""
    X = np.asarray(E, np.float64)
    X = X - X.mean(0)
    sv = np.linalg.svd(X, compute_uv=False)
    return float((sv ** 2).sum() ** 2 / (sv ** 4).sum())


def load_net(path: Path):
    import torch
    ck = torch.load(path, map_location="cpu")
    net = LS.make_net(ck.get("dim", 32), pool=ck.get("pool", 1))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    return net, ck


def speak_always(book, emb):
    """(nonconformity, correct) with NO refusal — the pairs a calibration split needs."""
    rows = []
    for name, E in emb.items():
        for v in E:
            sims = sorted(((float(naming._unit(v) @ c), n) for n, c in book.centroids.items()),
                          reverse=True)
            rows.append((1.0 - sims[0][0], sims[0][1] == name))
    return np.array([r[0] for r in rows]), np.array([r[1] for r in rows])


def main() -> None:
    if not NET_V2.exists():
        sys.exit(f"no retrained encoder at {NET_V2}")
    print(f"held out: {', '.join(HOLDOUT)}   |   the retrain saw {', '.join(RETRAIN_EPISODES)}, "
          f"and signature_net.pt records no episodes at all\n")

    report = {}
    for tag, path in (("current (triplet, pool=1)", NET_V1), ("retrained (InfoNCE, pool=2)", NET_V2)):
        net, ck = load_net(path)
        patches = harvest(HOLDOUT, ck.get("patch", 20))         # at THIS encoder's own scale
        names = sorted(patches)
        if len(names) < 3:
            sys.exit(f"only {len(names)} usable classes in {HOLDOUT}")
        emb = {k: LS.embed(net, v, "cpu") for k, v in patches.items()}
        book = naming.anchor_from({k: emb[k][:N_ANCHOR] for k in names})
        rest = {k: emb[k][N_ANCHOR:] for k in names}
        half = min(len(v) for v in rest.values()) // 2
        # SEQUENTIAL split: harvest walks ep050 then ep100 then ep112, so calibration and test land in
        # DIFFERENT TOWNS. That is the deployment case, and it breaks the exchangeability conformal
        # assumes -- a fact about the world moving, not about the gate's arithmetic.
        s_cal, y_cal = speak_always(book, {k: v[:half] for k, v in rest.items()})
        s_tst, y_tst = speak_always(book, {k: v[half:2 * half] for k, v in rest.items()})
        # EXCHANGEABLE control: the same patches, split at random. If the promise holds here and only
        # here, the violation beside it is distribution shift rather than a broken threshold.
        rng = np.random.default_rng(0)
        s_all, y_all = speak_always(book, rest)
        perm = rng.permutation(len(s_all))
        mid = len(perm) // 2
        s_xc, y_xc = s_all[perm[:mid]], y_all[perm[:mid]]
        s_xt, y_xt = s_all[perm[mid:]], y_all[perm[mid:]]
        pr = participation_ratio(np.concatenate([emb[k] for k in names]))
        rows = {}
        print(f"{tag}   dim {ck.get('dim')}  pool {ck.get('pool', 1)}  "
              f"patch {ck.get('patch')}  {len(names)} classes ({', '.join(names)})")
        print(f"  {sum(len(v) for v in patches.values())} patches   "
              f"calibration n={len(s_cal)} ({int((~y_cal.astype(bool)).sum())} wrong), "
              f"held-out n={len(s_tst)}")
        print(f"  {'':>7}{'':>13}{'--- A NEW TOWN (calibrate here, deploy there) ---':^43}"
              f"{'--- EXCHANGEABLE ---':^30}")
        print(f"  {'alpha':>7}{'cosine cut':>13}{'coverage':>11}{'precision':>11}"
              f"{'P(acc|wrong)':>14}{'kept?':>7}{'coverage':>13}{'P(a|w)':>10}{'kept?':>7}")
        for a in ALPHAS:
            q = CF.calibrate(s_cal, y_cal, a)
            ev = CF.evaluate(s_tst, y_tst, q, a)
            key = f"{a:.2f}"
            rows[key] = {"q_hat": float(q), "cosine_cut": float(1.0 - q),
                            "coverage": ev.accept_rate, "precision": 1.0 - ev.error_among_accepted,
                            "false_accept_given_wrong": ev.false_accept_given_wrong,
                            "n_wrong_calibration": int((~y_cal.astype(bool)).sum()),
                            "promise_kept": bool(ev.false_accept_given_wrong <= a + 1e-9)}
            qx = CF.calibrate(s_xc, y_xc, a)
            evx = CF.evaluate(s_xt, y_xt, qx, a)
            rows[key]["exchangeable_control"] = {
                "coverage": evx.accept_rate, "precision": 1.0 - evx.error_among_accepted,
                "false_accept_given_wrong": evx.false_accept_given_wrong,
                "promise_kept": bool(evx.false_accept_given_wrong <= a + 1e-9)}
            print(f"  {a:>7.2f}{1.0 - q:>13.3f}{ev.accept_rate:>11.1%}"
                  f"{1.0 - ev.error_among_accepted:>11.3f}{ev.false_accept_given_wrong:>14.3f}"
                  f"{('yes' if rows[key]['promise_kept'] else 'NO'):>7}"
                  f"{evx.accept_rate:>13.1%}{evx.false_accept_given_wrong:>10.3f}"
                  f"{('yes' if rows[key]['exchangeable_control']['promise_kept'] else 'NO'):>7}")

        # the hard-coded 0.78, measured on the same held-out split for reference
        fixed = float((s_tst <= 1.0 - 0.78).mean())
        acc = s_tst <= 1.0 - 0.78
        p78 = float(y_tst[acc].mean()) if acc.any() else float("nan")
        print(f"  {'0.78':>7}{0.780:>13.3f}{fixed:>11.1%}{p78:>11.3f}{'(hard-coded)':>18}\n")
        print(f"  effective dimensions ON HOLDOUT: {pr:.2f}" + chr(10))
        report[tag] = {"checkpoint": str(path), "dim": ck.get("dim"), "pool": ck.get("pool", 1),
                       "patch": ck.get("patch"), "classes": names,
                       "participation_ratio_on_holdout": pr,
                       "n_patches": int(sum(len(v) for v in patches.values())),
                       "by_alpha": rows, "hardcoded_0.78": {"coverage": fixed, "precision": p78}}

    exch = {t: all(r["exchangeable_control"]["promise_kept"] for r in v["by_alpha"].values())
            for t, v in report.items()}
    shift = {t: all(r["promise_kept"] for r in v["by_alpha"].values()) for t, v in report.items()}
    print("-> 0. the gate keeps its promise under an EXCHANGEABLE split: "
          + ", ".join(f"{t.split()[0]} {v}" for t, v in exch.items()))
    print("      and keeps it in A NEW TOWN:                            "
          + ", ".join(f"{t.split()[0]} {v}" for t, v in shift.items()))
    a = "0.10"
    cur = report["current (triplet, pool=1)"]["by_alpha"][a]
    new = report["retrained (InfoNCE, pool=2)"]["by_alpha"][a]
    wider = new["coverage"] > cur["coverage"]
    kept = all(r["promise_kept"] for t in report.values() for r in t["by_alpha"].values())
    lower = new["cosine_cut"] < 0.78
    print(f"-> 1. at alpha=0.10 the retrained space covers MORE: {wider}   "
          f"({cur['coverage']:.1%} -> {new['coverage']:.1%})")
    print(f"-> 2. the gate keeps its promise on held-out data at every alpha: {kept}")
    print(f"-> 3. and the calibrated cut sits below 0.78: {lower}   "
          f"(0.78 -> {new['cosine_cut']:.3f}), which is why the fixed number looked like a loss")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"holdout_episodes": list(HOLDOUT),
                               "retrain_episodes": list(RETRAIN_EPISODES), "n_anchor": N_ANCHOR,
                               "encoders": report,
                               "note": "cosines shrink as a space widens, so a threshold calibrated "
                                       "against a 6-dimensional space is a stricter rule in a "
                                       "19-dimensional one. Comparison is at matched certified alpha, "
                                       "and each encoder is fed its own declared patch radius.",
                               "supersedes": "eff dims 19.44 and naming precision 1.000 were measured on patches from the retrain's OWN episodes, which is in-distribution; the holdout figures here replace them."},
                              indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
