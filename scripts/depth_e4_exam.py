# -*- coding: utf-8 -*-
"""The E4 sealed exam kit for depth_learner: three commands with three different people behind them.

    python scripts/depth_e4_exam.py seal  --out <dir> --episodes ep031 ep042 ...   # EXAMINER only
    python scripts/depth_e4_exam.py run   --seal <dir>/public.json --out <dir>     # anyone, incl. me
    python scripts/depth_e4_exam.py score --seal <dir> --pred <dir>/pred.npz       # EXAMINER only

Pre-registration: docs/ATANOR_depth_E4_prereg.md, committed BEFORE any exam data was drawn. Read it first;
this file only implements what that document already fixed.

WHY THE KIT IS SPLIT IN THREE. depth_learner already has a real result -- derotated flow agreement 0.283 on
City Sample against a random control of -0.006, p = 2.16e-10, instrument validated on CARLA ground truth
first. That is M3 and not E4 for one reason: I wrote the harness, chose the data, and read the number. E4
needs an evaluator who is not the builder. So the roles are separated in code, not in good intentions:

    seal    the EXAMINER picks the episodes and keeps the answers. Writes `public.json` (frame paths only)
            and `sealed.npz` (the answers). Only the public half is ever handed over.
    run     loads the frozen checkpoint and emits predictions. It CANNOT read ground truth -- the loader
            used here raises on any attempt to touch `depth_m`, so the guard is mechanical rather than a
            promise. Safe for me to run.
    score   the EXAMINER computes the verdict. Imports nothing from packages.depth_learner, so a bug in the
            organ cannot flatter its own exam.

THE THREAT THIS CONTROLS, named from the existing proof's own caveats: "the two City Sample runs disagree
more than sampling alone explains (0.187 in one sampling and 0.252 in another), and higher parallax did not
give a higher score, which is unexplained." The instrument is unstable and nobody knows why, so a pass
condition on a point estimate would be a coin flip wearing a certificate. Twenty independent samplings; the
net's 10th percentile must clear the trivial baseline's 90th. The distributions must not overlap.

I cannot open the seal, cannot run `score`, and cannot write the outcome into the registry --
packages/architecture_registry/tests/test_registry_is_enforced.py fails on any self-assigned E4+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CORPUS = Path(r"D:\carla\episodes")
CKPT = Path(r"D:\carla\depth_model\depthnet.pt")
SIZE = (320, 240)
N_SAMPLINGS = 20
MIN_FRAMES = 200
FRAMES_PER_SAMPLING = 40
MIN_M, MAX_M = 0.5, 200.0        # as packages/depth_learner/model.py defines them
PLAUSIBLE_M = (3.0, 60.0)        # a driving corpus whose constant baseline is 8.7 m


def _iso_mtime(t: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(t).isoformat(timespec="seconds")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resize_idx(shape, size):
    h, w = size[1], size[0]
    return ((np.arange(h) * (shape[0] / h)).astype(np.int32),
            (np.arange(w) * (shape[1] / w)).astype(np.int32))


class RgbOnly:
    """A frame loader that mechanically cannot return depth.

    The builder must be able to run `run` without the exam being compromised, and 'I promise not to look'
    is not a control. This raises on `depth_m`, so the guarantee is enforced by the code path rather than
    by my restraint."""

    FORBIDDEN = ("depth_m", "depth", "semantic")

    def __init__(self, path: Path):
        self._z = np.load(path)

    def rgb(self) -> np.ndarray:
        a = self._z["rgb"]
        ys, xs = _resize_idx(a.shape, SIZE)
        return a[ys][:, xs].transpose(2, 0, 1).astype(np.float32) / 255.0

    def __getitem__(self, key):
        if key in self.FORBIDDEN:
            raise PermissionError(
                f"{key!r} is ground truth. The runner may not read it; only `score`, executed by the "
                f"examiner, sees answers. See docs/ATANOR_depth_E4_prereg.md §4."
            )
        return self._z[key]


# ------------------------------------------------------------------ seal  (EXAMINER)
def never_trained() -> tuple[str, ...]:
    """Episodes the checkpoint never saw, read off build_split rather than chosen here.

    Deterministic from a seed fixed in code before training, so this pool cannot have been selected to fit
    a result. It is small -- 9 episodes, 2,640 frames -- which is why prereg 5a stopped excluding the
    held-out towns."""
    from packages.depth_learner.data import build_split
    s = build_split(CORPUS)
    return tuple(sorted(set(s.val_town) | set(s.val_episode)))


def draw_from_secret(secret: str, pool: tuple[str, ...], min_frames: int, stride: int):
    """Pick the seal from a passphrase the builder never sees.

    The one thing E4 needs that a code constant cannot give: the builder had no say in WHICH subset was
    drawn. Selection is SHA-256(secret) -> a permutation of the pool, taking episodes until the frame floor
    is cleared. The secret is never printed, never stored, and never written to any artefact."""
    h = hashlib.sha256(secret.encode("utf-8")).digest()
    order = sorted(pool, key=lambda e: hashlib.sha256(h + e.encode()).hexdigest())
    chosen, n = [], 0
    for e in order:
        chosen.append(e)
        n += len(sorted((CORPUS / e).glob("*.npz"))[::stride])
        if n >= min_frames and len(chosen) >= 3:
            break
    return tuple(sorted(chosen)), n


def cmd_seal(a) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if out.joinpath("sealed.npz").exists() and not a.force:
        sys.exit(f"{out/'sealed.npz'} exists. A seal is drawn ONCE; re-drawing after a verdict voids the "
                 f"exam (prereg §9). Pass --force only to fix a seal no verdict has been read from.")
    if a.all_unseen:
        # THE POOL IS TOO SMALL FOR A SUBSET TO MEAN ANYTHING, so take all of it and remove selection
        # entirely. With nine episodes and a 200-frame floor, --from-secret draws eight of nine whatever
        # passphrase is used: two different secrets differed by ONE episode. A passphrase that changes one
        # ninth of the seal is not independence, it is the appearance of it. Using the whole never-trained
        # pool is strictly stronger -- there is no subset for anyone, builder or examiner, to have chosen.
        eps = list(never_trained())
        est = sum(len(sorted((CORPUS / e).glob("*.npz"))[::a.stride]) for e in eps)
        print(f"sealing the ENTIRE never-trained pool: {len(eps)} episodes, {est} frames at stride "
              f"{a.stride}. No subset was selected by anyone.")
    elif a.from_secret:
        pool = never_trained()
        eps, est = draw_from_secret(a.from_secret, pool, MIN_FRAMES, a.stride)
        eps = list(eps)
        print(f"drawn from the examiner's passphrase out of a {len(pool)}-episode never-trained pool "
              f"({est} frames at stride {a.stride}). The passphrase is not recorded anywhere.")
    elif a.episodes:
        eps = list(a.episodes)
        illegal = [e for e in eps if e not in never_trained()]
        if illegal and not a.force:
            sys.exit(f"{illegal} were TRAINED ON. Seal material must come from the never-trained pool: "
                     f"{never_trained()}. Pass --force only if you know why.")
    else:
        sys.exit("give --all-unseen (recommended: no selection effect at all), "
                 "--from-secret <passphrase>, or --episodes <ep...>")
    frames = []
    for ep in eps:
        frames.extend(sorted((CORPUS / ep).glob("*.npz"))[::a.stride])
    if len(frames) < MIN_FRAMES:
        sys.exit(f"seal yields {len(frames)} frames, prereg §6 requires >= {MIN_FRAMES}. INCONCLUSIVE = FAIL.")

    rgbs, deps, valids = [], [], []
    for p in frames:
        z = np.load(p)
        ys, xs = _resize_idx(z["rgb"].shape, SIZE)
        dep = z["depth_m"].astype(np.float32)[ys][:, xs]
        sem = z["semantic"][ys][:, xs]
        deps.append(dep)
        valids.append((sem != 11) & (dep > 0.5) & (dep < 200.0))   # sky excluded, as data.load does
        rgbs.append(str(p))
    np.savez_compressed(out / "sealed.npz", depth=np.stack(deps), valid=np.stack(valids))

    # PROOF THE DATA POSTDATES THE FREEZE, so the exam does not rest on trusting whoever drew the seal.
    # A checkpoint cannot have trained on frames that did not exist when it was written. Timestamps make
    # that checkable by anyone: if every sealed frame is newer than the checkpoint, the "never trained on"
    # property is a fact about the filesystem rather than a claim about the builder's restraint.
    ck_mtime = CKPT.stat().st_mtime if CKPT.exists() else 0.0
    f_mtimes = [Path(f).stat().st_mtime for f in rgbs]
    postdates = bool(f_mtimes and min(f_mtimes) > ck_mtime)
    import datetime as _dt
    _iso = lambda t: _dt.datetime.fromtimestamp(t).isoformat(timespec="seconds")   # noqa: E731

    public = {"schema": "atanor.depth.e4.public.v2", "frames": rgbs, "size": list(SIZE),
              "checkpoint_mtime": _iso(ck_mtime),
              "earliest_frame_mtime": _iso(min(f_mtimes)) if f_mtimes else None,
              "frames_postdate_checkpoint": postdates,
              "postdate_note": ("Every sealed frame is newer than the frozen checkpoint, so the model "
                                "provably never trained on them. Verifiable from file mtimes by anyone; "
                                "it does not depend on trusting who drew the seal."
                                if postdates else
                                "WARNING: some frames predate the checkpoint. The never-trained property "
                                "is NOT established by timestamps for this seal."),
              "episodes": eps, "stride": a.stride,
              "checkpoint": str(CKPT), "checkpoint_sha256": sha(CKPT) if CKPT.exists() else None,
              "n_samplings": N_SAMPLINGS, "frames_per_sampling": FRAMES_PER_SAMPLING,
              "prereg": "docs/ATANOR_depth_E4_prereg.md",
              "answers_sha256": sha(out / "sealed.npz"),
              "note": ("The examiner keeps sealed.npz. Only this file is handed to the runner. The episode "
                       "list is disclosed because the runner needs the images; the ANSWERS are not.")}
    (out / "public.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    print(f"sealed {len(frames)} frames from {len(eps)} episodes")
    print(f"  answers   {out/'sealed.npz'}   sha256 {public['answers_sha256'][:16]}...  KEEP THIS")
    print(f"  public    {out/'public.json'}  hand this to the runner")
    print(f"  ckpt      {public['checkpoint_sha256'][:16] if public['checkpoint_sha256'] else '(missing)'}...")
    print(f"  freeze    checkpoint written {public['checkpoint_mtime']}")
    print(f"  data      earliest frame     {public['earliest_frame_mtime']}")
    print(f"  -> frames postdate the freeze: {postdates}  "
          f"{'(never-trained is a filesystem fact, not a promise)' if postdates else '(NOT ESTABLISHED)'}")


# ------------------------------------------------------------------ run  (anyone)
def cmd_run(a) -> None:
    import torch
    from packages.depth_learner.model import DepthNet

    pub = json.loads(Path(a.seal).read_text(encoding="utf-8"))
    ckpt = Path(a.checkpoint) if a.checkpoint else CKPT
    if not ckpt.is_absolute():
        ckpt = CKPT.parent / ckpt
    if not ckpt.exists():
        sys.exit(f"no checkpoint at {ckpt}")

    # THE PROPERTY THAT MATTERS IS ORDER IN TIME, NOT HASH EQUALITY. E4 ran one checkpoint, so comparing
    # its hash to the one recorded at seal time was the same thing as checking it had not been swapped.
    # E5 runs THREE against one seal, so that equality is wrong by construction. What has to hold for any
    # of them is that the weights predate the frames: a checkpoint cannot have trained on data that did
    # not exist when it was written, and file mtimes make that checkable by anyone.
    ck_mtime = ckpt.stat().st_mtime
    earliest = min(Path(f).stat().st_mtime for f in pub["frames"])
    if ck_mtime >= earliest:
        sys.exit(f"VOID: {ckpt.name} was written after the sealed frames existed "
                 f"({ck_mtime} >= {earliest}). It could have trained on them.")
    ck = torch.load(ckpt, map_location="cpu")
    net = DepthNet(width=ck.get("width", 32))
    print(f"checkpoint {ckpt.name}  kind={ck.get('kind') or 'supervised'}  "
          f"init={ck.get('init') or 'random'}  written {_iso_mtime(ck_mtime)}", flush=True)
    net.load_state_dict(ck["state_dict"])
    net.eval()

    preds = []
    with torch.no_grad():
        for i, fp in enumerate(pub["frames"]):
            rgb = RgbOnly(Path(fp)).rgb()            # ground truth is unreachable from here
            y = net(torch.from_numpy(rgb)[None])
            # THE HEAD PREDICTS LOG DEPTH. model.py says so in a comment and model.metrics opens with
            # `p = torch.exp(pred_log)`. Exam 001 stored the raw output and scored it as metres, and
            # FAILED -- on a units bug, not on the model. exp then clamp, exactly as metrics does.
            m = torch.exp(y).clamp(MIN_M, MAX_M)
            preds.append(np.asarray(m).squeeze())
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(pub['frames'])}", flush=True)
    # UNITS PREFLIGHT, and the reason it exists. Before the seal was spent I checked that predictions
    # were non-degenerate and never that they were in the right UNITS -- so a log-depth map sailed through
    # looking healthy (per-frame medians 0.128..2.950, plausible-looking numbers that as metres would put
    # an entire street inside three metres). A sanity range on the corpus's own scale catches that class
    # of bug BEFORE an examiner spends a seal on it.
    P = np.stack(preds)
    med = float(np.median(P))
    kind = ck.get("kind") or "supervised"
    if kind == "ordinal_selfsup":
        # AN ORDER-ONLY MODEL HAS NO RIGHT SCALE, so a metre-range check is the wrong question to ask it.
        # The guard was added after exam 001's units bug and it assumed every arm emits metres; run against
        # this checkpoint it refused predictions that were exactly what the model was trained to produce.
        # What CAN go wrong here is degeneracy -- a collapsed or constant map orders nothing -- so that is
        # what is checked instead. The metre band is not relaxed for metric arms; it simply does not apply.
        spread = float(np.median([float(f.max() - f.min()) for f in P]))
        flat = int(sum(1 for f in P if f.std() < 1e-6))
        if flat or spread <= 1e-3:
            sys.exit(f"ordinal preflight FAILED: {flat} constant frames, median within-frame spread "
                     f"{spread:.5f}. An order-only map that does not vary orders nothing.")
        print(f"ordinal preflight: median output {med:.3f} (scale is arbitrary and that is correct), "
              f"within-frame spread {spread:.3f}, constant frames {flat}")
    else:
        if not (PLAUSIBLE_M[0] <= med <= PLAUSIBLE_M[1]):
            sys.exit(f"units preflight FAILED: median predicted depth {med:.3f} is outside the plausible "
                     f"{PLAUSIBLE_M[0]}-{PLAUSIBLE_M[1]} m range for this corpus (its constant baseline "
                     f"is 8.7 m). A log-depth map read as metres lands near 2; do not spend a seal on it.")
        print(f"units preflight: median predicted depth {med:.2f} m, "
              f"range {P.min():.2f}-{P.max():.2f} m  (corpus constant baseline 8.7 m)")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "pred.npz", pred=P)
    import datetime as _dt
    meta = {"schema": "atanor.depth.e4.pred.v3", "n": len(preds),
            "units": "metres (exp of the net's log-depth head, clamped to [0.5, 200])",
            "median_predicted_m": med,
            "pred_sha256": sha(out / "pred.npz"),
            "checkpoint": ckpt.name,
            "checkpoint_kind": ck.get("kind") or ("supervised" if "min_m" in ck else "unknown"),
            "checkpoint_init": ck.get("init"),
            "checkpoint_sha256": sha(ckpt),
            "checkpoint_mtime": _dt.datetime.fromtimestamp(ck_mtime).isoformat(timespec="seconds"),
            "predates_the_frames": True,
            "answers_sha256": pub.get("answers_sha256"),
            "read_ground_truth": False}
    (out / "pred.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {out/'pred.npz'}  sha256 {meta['pred_sha256'][:16]}...  ({len(preds)} frames)")
    print("hand this to the examiner. This process never read depth_m.")


# ------------------------------------------------------------------ score  (EXAMINER)
def delta125(pred, true, valid) -> float:
    """Fraction of valid pixels within 25% of truth, after median scaling. Registered primary metric."""
    p, t, m = pred[valid], true[valid], None
    if p.size == 0:
        return float("nan")
    s = np.median(t) / max(np.median(p), 1e-9)
    p = p * s
    r = np.maximum(p / np.maximum(t, 1e-9), t / np.maximum(p, 1e-9))
    return float(np.mean(r < 1.25))


def spearman(pred, true, valid, cap: int = 4000, seed: int = 0) -> float:
    """Rank correlation between predicted and true depth. The metric for an ORDER-ONLY model.

    E5 v1 registered delta<1.25 for `ordinal_selfsup`, which has no metres -- its own module says monocular
    vision cannot recover them, so a rank is the honest form of what a single moving eye can know. Rank
    correlation is scale-free by construction, which is exactly the property that makes it right here and
    delta wrong. Pixels are subsampled: a frame is 76,800 of them and the correlation settles long before.
    """
    p, t = pred[valid], true[valid]
    if p.size < 50:
        return float("nan")
    if p.size > cap:
        i = np.random.default_rng(seed).choice(p.size, cap, replace=False)
        p, t = p[i], t[i]
    rp = np.argsort(np.argsort(p)).astype(float)
    rt = np.argsort(np.argsort(t)).astype(float)
    rp -= rp.mean()
    rt -= rt.mean()
    d = float(np.sqrt((rp ** 2).sum() * (rt ** 2).sum()))
    return float((rp * rt).sum() / d) if d > 0 else float("nan")


def absrel(pred, true, valid) -> float:
    p, t = pred[valid], true[valid]
    if p.size == 0:
        return float("nan")
    p = p * (np.median(t) / max(np.median(p), 1e-9))
    return float(np.mean(np.abs(p - t) / np.maximum(t, 1e-9)))


def cmd_score(a) -> None:
    from packages.self_check import preflight            # the only import, and it is not the organ

    sealdir = Path(a.seal)
    z = np.load(sealdir / "sealed.npz")
    depth, valid = z["depth"], z["valid"]
    pub = json.loads((sealdir / "public.json").read_text(encoding="utf-8"))
    pred = np.load(a.pred)["pred"]
    pmeta = json.loads(Path(a.pred).with_suffix(".json").read_text(encoding="utf-8"))

    void = []
    if pmeta.get("answers_sha256") != pub.get("answers_sha256"):
        void.append("prediction file was produced against a different seal")
    if pmeta.get("checkpoint_sha256") != pub.get("checkpoint_sha256"):
        void.append("checkpoint hash differs from seal time")
    if len(pred) != len(depth):
        void.append(f"prediction count {len(pred)} != sealed frame count {len(depth)}")
    if void:
        sys.exit("VOID (prereg §9): " + "; ".join(void))

    # A FRAME WITH NO VALID PIXELS POISONS EVERY ARM. Seal 002 held exactly one such frame out of 252 --
    # depth uniformly 1000 m, the sky sentinel everywhere, so the camera saw nothing but sky -- and
    # `delta125` returned nan for it, which `np.mean` then spread across net, constant, shuffled and true
    # alike. Every number came back nan and the exam FAILED on arithmetic rather than on the model.
    #
    # Such a frame is uninformative for all arms equally, so dropping it is right; dropping it SILENTLY is
    # not, because quietly discarding inconvenient frames is how a harness flatters its own result. The
    # count is printed, recorded in the verdict, and too many of them is INCONCLUSIVE, which counts as
    # failure under prereg 6.
    usable = np.array([bool(valid[i].any()) for i in range(len(depth))], bool)
    dropped = int((~usable).sum())
    if dropped:
        print(f"  {dropped} of {len(depth)} sealed frames have NO valid pixels (all sky / beyond range) "
              f"and are excluded from every arm equally", flush=True)
    if dropped > 0.05 * len(depth):
        sys.exit(f"INCONCLUSIVE = FAIL (prereg 6): {dropped}/{len(depth)} frames carry no valid pixels. "
                 f"A seal that is mostly sky measures nothing; draw a fresh one.")
    keep = np.where(usable)[0]

    rng = np.random.default_rng(0)
    const = float(np.median(depth[valid]))
    rows = {"net": [], "constant": [], "shuffled": [], "true": []}
    ar = {"net": [], "constant": [], "shuffled": []}
    n = min(FRAMES_PER_SAMPLING, len(keep))
    for _ in range(N_SAMPLINGS):
        idx = rng.choice(keep, size=n, replace=False)
        sh = rng.permutation(idx)                            # net's own maps on the WRONG frames
        for name, P in (("net", pred[idx]), ("constant", np.full_like(pred[idx], const)),
                        ("shuffled", pred[sh]), ("true", depth[idx])):
            d = float(np.mean([delta125(P[k], depth[i], valid[i]) for k, i in enumerate(idx)]))
            rows[name].append(d)
            if name in ar:
                ar[name].append(float(np.mean([absrel(P[k], depth[i], valid[i])
                                               for k, i in enumerate(idx)])))

    def p(v, q):
        return float(np.percentile(v, q))

    print(f"sealed exam: {len(depth)} frames, episodes {pub['episodes']}, "
          f"{N_SAMPLINGS} samplings of {n}\n")
    print(f"{'arm':<12}{'delta<1.25 p10':>16}{'median':>10}{'p90':>10}{'AbsRel med':>13}")
    for k in ("net", "constant", "shuffled", "true"):
        am = f"{np.median(ar[k]):.4f}" if k in ar else "     --"
        print(f"{k:<12}{p(rows[k],10):>16.4f}{np.median(rows[k]):>10.4f}{p(rows[k],90):>10.4f}{am:>13}")

    c1 = p(rows["net"], 10) > p(rows["constant"], 90)
    c2 = np.median(ar["net"]) < np.median(ar["constant"])
    c3 = p(rows["net"], 10) > p(rows["shuffled"], 90)
    v = preflight.run("depth_learner E4: CARLA-learned depth transfers to a sealed held-out set",
                      observed_source="sealed CARLA episodes", intended_source="sealed CARLA episodes",
                      base_rate=float(valid.mean()), n=int(len(depth)),
                      real_score=float(np.median(rows["net"])),
                      control_score=float(np.median(rows["constant"])),
                      target_size=abs(p(rows["net"], 10) - p(rows["constant"], 90)),
                      unit_size=float(np.std(rows["net"])) or 1e-3)
    print(f"\n-> 1. net p10 beats constant p90      : {c1}")
    print(f"-> 2. AbsRel agrees                     : {c2}")
    print(f"-> 3. net p10 beats shuffled p90        : {c3}")
    print(f"-> 4. preflight all green               : {v.may_promote}")
    for c in v.checks:
        print(f"     {c.name:<14}{'green' if c.green else ('FAILED' if c.ran else 'COULD NOT RUN'):<15}"
              f"{c.detail}")
    verdict = bool(c1 and c2 and c3 and v.may_promote)
    # A SPENT SEAL CANNOT ATTEST, AND ITS RECORD CANNOT BE OVERWRITTEN. Both were learned on seal 001: a
    # diagnostic rescore printed "E4 PASS" and replaced the FAIL verdict file, leaving a git message as
    # the only surviving trace of the failure. An artefact recording a failure must not be silently
    # swapped for one recording a pass.
    prior = sealdir / "verdict.json"
    spent = prior.exists()
    if spent:
        k = 2
        while (sealdir / f"verdict_diagnostic_{k:03d}.json").exists():
            k += 1
        out = sealdir / f"verdict_diagnostic_{k:03d}.json"
        print(f"\nVERDICT: DIAGNOSTIC ({'conditions hold' if verdict else 'conditions fail'})")
        print(f"  This seal already produced {prior.name}. Feedback has flowed from it, so nothing read "
              f"afterwards can be an E4 attestation -- not because any single fix is suspect, but because "
              f"the process is no longer blind and nobody outside can tell one honest fix from the "
              f"seventh attempt. A fresh seal is required. See docs/ATANOR_depth_E4_prereg.md 10.")
    else:
        out = prior
        print(f"\nVERDICT: {'E4 PASS' if verdict else 'FAIL'}  "
              f"({'all four registered conditions hold' if verdict else 'at least one condition failed; '
                 'inconclusive counts as failure'})")
    out.write_text(json.dumps({"schema": "atanor.depth.e4.verdict.v1",
                               "pass": verdict, "attestation": not spent,
                               "seal_spent_before_this_run": spent,
                               "conditions": {"net_p10_beats_constant_p90": c1,
                                              "absrel_agrees": bool(c2),
                                              "net_p10_beats_shuffled_p90": c3,
                                              "preflight": v.may_promote},
                               "delta125": {k: {"p10": p(rows[k], 10), "median": float(np.median(rows[k])),
                                                "p90": p(rows[k], 90)} for k in rows},
                               "absrel_median": {k: float(np.median(x)) for k, x in ar.items()},
                               "answers_sha256": pub.get("answers_sha256"),
                               "pred_sha256": pmeta.get("pred_sha256"),
                               "checkpoint_sha256": pub.get("checkpoint_sha256"),
                               "prereg": "docs/ATANOR_depth_E4_prereg.md",
                               "preflight": v.as_dict(),
                               "examiner": a.examiner or "(unsigned -- an unsigned verdict is not E4)"},
                              indent=2), encoding="utf-8")
    print("wrote", out)
    if verdict and not a.examiner:
        print("\nNOTE: pass with no --examiner is not an E4 attestation. Re-run score with the "
              "examiner's identity, and let the EXAMINER make the registry edit.")


# ------------------------------------------------------------------ paired  (EXAMINER, E5)
def cmd_paired(a) -> None:
    """E5: several frozen checkpoints against ONE seal, each scored on what it was trained to emit.

    Pre-registration: docs/ATANOR_depth_E5_prereg_v2.md. Metric arms keep delta<1.25; the ordinal arm is
    scored on Spearman rho. Mixing them is what voided v1."""
    from packages.self_check import preflight

    sealdir = Path(a.seal)
    z = np.load(sealdir / "sealed.npz")
    depth, valid = z["depth"], z["valid"]
    pub = json.loads((sealdir / "public.json").read_text(encoding="utf-8"))

    arms = {}
    for spec in a.pred:
        path = Path(spec)
        meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if meta.get("answers_sha256") != pub.get("answers_sha256"):
            sys.exit("VOID: " + str(path) + " was produced against a different seal")
        if not meta.get("predates_the_frames"):
            sys.exit("VOID: " + str(meta.get("checkpoint")) + " does not predate the sealed frames")
        arms[meta.get("checkpoint", path.stem)] = (np.load(path)["pred"], meta)

    usable = np.array([bool(valid[i].any()) for i in range(len(depth))], bool)
    dropped = int((~usable).sum())
    if dropped:
        print("  " + str(dropped) + "/" + str(len(depth)) +
              " frames have no valid pixels; excluded from every arm equally")
    if dropped > 0.05 * len(depth):
        sys.exit("INCONCLUSIVE = FAIL: " + str(dropped) + " frames carry no valid pixels.")
    keep = np.where(usable)[0]

    rng = np.random.default_rng(0)
    const = float(np.median(depth[valid]))
    n = min(FRAMES_PER_SAMPLING, len(keep))
    res = {}
    for name, (P_, meta) in arms.items():
        ordinal = meta.get("checkpoint_kind") == "ordinal_selfsup"
        fn = spearman if ordinal else delta125
        real, shuf, ctl = [], [], []
        for _ in range(N_SAMPLINGS):
            idx = rng.choice(keep, size=n, replace=False)
            sh = rng.permutation(idx)
            real.append(float(np.nanmean([fn(P_[i], depth[i], valid[i]) for i in idx])))
            shuf.append(float(np.nanmean([fn(P_[j], depth[i], valid[i]) for i, j in zip(idx, sh)])))
            ctl.append(float(np.nanmean([fn(np.full_like(P_[i], const), depth[i], valid[i])
                                         for i in idx])))
        res[name] = {"metric": "spearman" if ordinal else "delta125", "label_free": bool(ordinal),
                     "init": meta.get("checkpoint_init") or "random",
                     "real_p10": float(np.percentile(real, 10)),
                     "real_median": float(np.median(real)),
                     "shuffled_p90": float(np.percentile(shuf, 90)),
                     "shuffled_median": float(np.median(shuf)),
                     "constant_p90": float(np.percentile(ctl, 90))}

    print("")
    print("sealed exam: " + str(len(depth)) + " frames, " + str(N_SAMPLINGS) +
          " samplings of " + str(n))
    print("")
    print("%-26s%-11s%-14s%10s%9s%10s%11s" % ("arm", "metric", "init", "real p10", "median",
                                              "shuf p90", "const p90"))
    for k, r in res.items():
        print("%-26s%-11s%-14s%10.4f%9.4f%10.4f%11.4f" % (k, r["metric"], str(r["init"])[:13],
                                                          r["real_p10"], r["real_median"],
                                                          r["shuffled_p90"], r["constant_p90"]))

    metric_arms = {k: r for k, r in res.items() if r["metric"] == "delta125"}
    free = {k: r for k, r in res.items() if r["label_free"]}
    c1 = bool(metric_arms) and all(r["real_p10"] > r["constant_p90"] for r in metric_arms.values())
    c2 = bool(free) and all(r["real_p10"] > r["shuffled_p90"] for r in free.values())
    c3 = all(np.isfinite(r["real_median"]) for r in res.values())
    f0 = list(free.values())[0] if free else None
    v = preflight.run("depth_learner E5: label-free depth transfers to a sealed unseen town",
                      observed_source="sealed CARLA episodes", intended_source="sealed CARLA episodes",
                      base_rate=float(valid.mean()), n=int(len(depth)),
                      real_score=(f0["real_median"] if f0 else None),
                      control_score=(f0["shuffled_median"] if f0 else None),
                      target_size=(abs(f0["real_p10"] - f0["shuffled_p90"]) if f0 else None),
                      unit_size=0.02)
    print("")
    print("-> 1. both metric arms clear constant       : " + str(c1))
    print("-> 2. LABEL-FREE arm clears its shuffled    : " + str(c2) + "   <- load-bearing")
    print("-> 3. arms resolve (no nan medians)         : " + str(c3))
    print("-> 4. preflight all green                   : " + str(v.may_promote))
    for c in v.checks:
        mark = "green" if c.green else ("FAILED" if c.ran else "COULD NOT RUN")
        print("     %-14s%-15s%s" % (c.name, mark, c.detail))
    verdict = bool(c1 and c2 and c3 and v.may_promote)
    prior = sealdir / "verdict.json"
    spent = prior.exists()
    out = prior if not spent else sealdir / "verdict_diagnostic_e5.json"
    print("")
    if spent:
        print("VERDICT: DIAGNOSTIC -- this seal already produced a verdict; not an attestation.")
    else:
        print("VERDICT: " + ("E5 PASS" if verdict else "FAIL") +
              ("  (all four registered conditions hold)" if verdict
               else "  (at least one failed; inconclusive counts as failure)"))
    out.write_text(json.dumps({"schema": "atanor.depth.e5.verdict.v1", "pass": verdict,
                               "attestation": not spent, "seal_spent_before_this_run": spent,
                               "conditions": {"metric_arms_clear_constant": c1,
                                              "label_free_clears_shuffled": c2,
                                              "arms_resolve": c3, "preflight": v.may_promote},
                               "arms": res, "dropped_frames": dropped,
                               "answers_sha256": pub.get("answers_sha256"),
                               "prereg": "docs/ATANOR_depth_E5_prereg_v2.md",
                               "preflight": v.as_dict(),
                               "examiner": a.examiner or "(unsigned -- not an attestation)"},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote " + str(out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seal", help="EXAMINER: draw the seal and keep the answers")
    s.add_argument("--out", required=True)
    s.add_argument("--episodes", nargs="*", default=[],
                   help="explicit episode list; must be from the never-trained pool")
    s.add_argument("--all-unseen", action="store_true", dest="all_unseen",
                   help="RECOMMENDED. Seal the entire never-trained pool, so no subset is chosen by "
                        "anyone. At this pool size a passphrase changes only one episode in nine.")
    s.add_argument("--from-secret", default="", dest="from_secret",
                   help="a passphrase only you know; the draw is derived from it and the builder "
                        "had no say. Never recorded.")
    s.add_argument("--stride", type=int, default=10)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_seal)
    r = sub.add_parser("run", help="anyone: frozen model -> predictions, ground truth unreachable")
    r.add_argument("--seal", required=True, help="path to public.json")
    r.add_argument("--out", required=True)
    r.add_argument("--checkpoint", default="",
                   help="which frozen checkpoint to run; defaults to depthnet.pt. A bare filename is "
                        "resolved against the model directory. E5 needs all three.")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("score", help="EXAMINER: predictions + answers -> verdict")
    c.add_argument("--seal", required=True, help="the seal DIRECTORY")
    c.add_argument("--pred", required=True, help="path to pred.npz")
    c.add_argument("--examiner", default="", help="who is attesting; unsigned is not E4")
    c.set_defaults(fn=cmd_score)
    q = sub.add_parser("paired", help="EXAMINER, E5: several checkpoints against one seal")
    q.add_argument("--seal", required=True, help="the seal DIRECTORY")
    q.add_argument("--pred", nargs="+", required=True, help="one pred.npz per arm")
    q.add_argument("--examiner", default="", help="who is attesting; unsigned is not E5")
    q.set_defaults(fn=cmd_paired)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
