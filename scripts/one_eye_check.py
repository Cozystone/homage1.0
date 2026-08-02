# -*- coding: utf-8 -*-
"""Does ONE rule do what three hand-picked ones did? Measured on every testbed at once.

    python scripts/one_eye_check.py

The three signals that had accumulated — raw change, prediction error, replacement — were each
reported on whichever testbed suited them, and divisive normalisation was applied where it helped and
omitted where it hurt. That is a mode switch built one measurement at a time, and the owner named it:
a person's eye is the same eye whether they are walking or watching.

So this asks the only question that settles it. For every testbed, score BOTH the best of the three
hand-picked rules and the single always-on rule from `one_eye.py`. If the unified rule is materially
worse anywhere, the three were doing different jobs and merging them lost something real, which is
worth knowing. If it is not, one eye is enough and the three were bookkeeping.

Everything is scored against a chance control of the same boundary COUNT, because a rule that fires
more often hits more true boundaries without knowing anything, and the raw recall hides that
completely.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.attention import frame_signature          # noqa: E402
from packages.perception.efference import BodyModel, Efference     # noqa: E402
from packages.perception.events import EventStream, alignment, boundaries   # noqa: E402
from packages.perception.one_eye import OneEye                     # noqa: E402

EXPLAINER = Path(r"D:\explainer_testbed")
CITY = Path(r"D:\citysample_long")
CARLA = Path(r"D:\carla\episodes")
SCHEMA = Path(r"D:\citysample_drive\body_schema_latest.json")


def _score(signal, truth, n, *, window, ratio, gap, tol) -> dict:
    bs = [b.index for b in boundaries(signal, window=window, ratio=ratio, min_gap=gap)]
    a = alignment(bs, truth, tol=tol, n_frames=n)
    if a.get("recall") is None:
        return {"ratio": 0.0, "recall": 0.0, "found": 0, "p": 1.0}
    return {"ratio": a["recall"] / max(a["chance_recall"], 1e-9), "recall": a["recall"],
            "found": a["found"], "p": a["beats_chance_p"]}


def _old_three(frames, commands=None):
    """The three signals as they were, so the comparison is against what was actually reported."""
    codes = [frame_signature(f) for f in frames]
    raw = [0.0, 0.0] + [float(np.abs(codes[i] - codes[i - 1]).mean()) for i in range(2, len(codes))]
    st = EventStream()
    for c in codes:
        st.push(c)
    return {"raw change": raw, "prediction error": st.errors, "replacement": st.replaced}


def _one_eye(frames, commands=None, eff=None):
    eye = OneEye(efference=eff)
    for i, f in enumerate(frames):
        eye.look(f, commands[i] if commands else None)
    return eye


def run_explainer(rows):
    for mode in ("cut", "build", "pan"):
        best, best_name, uni = None, "", []
        for d in sorted(EXPLAINER.glob(f"{mode}_*")):
            m = json.loads((d / "meta.json").read_text())
            fr = np.load(d / "frames.npz")["rgb"]
            kw = dict(window=20, ratio=2.0, gap=15, tol=6)
            for name, sig in _old_three(fr).items():
                s = _score(sig, m["boundaries"], len(fr), **kw)
                rows.setdefault(("explainer " + mode, name), []).append(s["ratio"])
            eye = _one_eye(fr)
            rows.setdefault(("explainer " + mode, "ONE EYE"), []).append(
                _score(eye.combined(), m["boundaries"], len(fr), **kw)["ratio"])


def run_city(rows):
    runs = [d for d in sorted(CITY.glob("*")) if d.is_dir() and (d / "meta.json").exists()]
    if not runs:
        return
    d = runs[-1]
    m = json.loads((d / "meta.json").read_text())
    fs = sorted(d.glob("*.npz"))
    N = min(len(fs), 3600)
    fps = float(m.get("fps") or 20.0)
    S = max(1, int(round(fps * 0.45)))
    idx = list(range(0, N, S))
    frames = [np.load(fs[i])["rgb"] for i in idx]
    marks = m.get("regime_per_frame") or []
    CMD = {"travel": "w", "turn_left": "mouse-x", "turn_right": "mouse+x", "still": None}
    cmds = [CMD.get(marks[i]) if i < len(marks) else None for i in idx]
    truth = sorted({b // S for b in m.get("boundaries", []) if 0 < b < N})
    kw = dict(window=12, ratio=1.8, gap=4, tol=2)
    for name, sig in _old_three(frames).items():
        rows.setdefault(("city " + d.name, name), []).append(
            _score(sig, truth, len(idx), **kw)["ratio"])
    eff = None
    if SCHEMA.exists():
        eff = Efference(BodyModel.from_schema(SCHEMA))
        eff.calibrate([(frames[i - 1], frames[i], cmds[i]) for i in range(1, len(frames), 3)])
    rows.setdefault(("city " + d.name, "ONE EYE"), []).append(
        _score(_one_eye(frames, cmds, eff).combined(), truth, len(idx), **kw)["ratio"])
    rows.setdefault(("city " + d.name, "ONE EYE (no body)"), []).append(
        _score(_one_eye(frames).combined(), truth, len(idx), **kw)["ratio"])


def run_carla(rows):
    eps = sorted([p for p in CARLA.glob("ep*") if p.is_dir()])[:20]

    def truth_of(P):
        dd = np.diff(P[:, :2], axis=0)
        sp = np.linalg.norm(dd, axis=1)
        yaw = np.unwrap(np.radians(P[:, 4]))
        tr = np.abs(np.diff(yaw))
        mv = (sp > np.percentile(sp, 25) * 1.5 + 1e-6).astype(int)
        tn = (tr > max(np.percentile(tr, 75) * 2, 0.01)).astype(int)
        return sorted({i + 1 for s in (mv, tn) for i in np.where(np.diff(s) != 0)[0]})

    for ep in eps:
        fs = sorted(ep.glob("*.npz"))
        if len(fs) < 36:
            continue
        frames = [np.load(f)["rgb"] for f in fs]
        truth = truth_of(np.stack([np.load(f)["pose"] for f in fs]))
        kw = dict(window=8, ratio=1.6, gap=4, tol=3)
        for name, sig in _old_three(frames).items():
            rows.setdefault(("carla", name), []).append(_score(sig, truth, len(fs), **kw)["ratio"])
        rows.setdefault(("carla", "ONE EYE"), []).append(
            _score(_one_eye(frames).combined(), truth, len(fs), **kw)["ratio"])


def main() -> None:
    rows: dict = {}
    run_explainer(rows)
    run_carla(rows)
    run_city(rows)

    beds = sorted({k[0] for k in rows})
    print(f"\nboundary detection, as a MULTIPLE OF CHANCE (1.0 = knows nothing)\n")
    print(f"{'testbed':22}{'raw change':>12}{'pred error':>12}{'replacement':>13}{'ONE EYE':>10}")
    verdict = []
    for bed in beds:
        vals = {n: float(np.mean(v)) for (b, n), v in rows.items() if b == bed}
        old = [vals.get(k, 0.0) for k in ("raw change", "prediction error", "replacement")]
        one = vals.get("ONE EYE", 0.0)
        print(f"{bed:22}{old[0]:>12.2f}{old[1]:>12.2f}{old[2]:>13.2f}{one:>10.2f}")
        verdict.append((bed, max(old), one))
        if "ONE EYE (no body)" in vals:
            print(f"{'  (same, body ignored)':22}{'':>12}{'':>12}{'':>13}{vals['ONE EYE (no body)']:>10.2f}")

    print(f"\n{'testbed':22}{'best hand-picked':>18}{'one eye':>10}{'kept':>8}")
    for bed, best, one in verdict:
        print(f"{bed:22}{best:>18.2f}{one:>10.2f}{(one / best if best > 1e-9 else 0):>8.0%}")
    worst = min((one / best if best > 1e-9 else 0) for _, best, one in verdict)
    print(f"\n-> one eye keeps at least {worst:.0%} of the best hand-picked rule everywhere."
          f"  {'UNIFICATION HOLDS' if worst >= 0.85 else 'the split was doing real work — do not merge'}")

    out = Path("data/depth_learner/proofs/one_eye.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"as_multiple_of_chance":
                               {b: {n: round(float(np.mean(v)), 3) for (bb, n), v in rows.items() if bb == b}
                                for b in beds},
                               "worst_retention": round(float(worst), 3)}, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
