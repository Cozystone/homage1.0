# -*- coding: utf-8 -*-
"""Minutes of footage with an exact record of when the motion changed.

    python scripts/citysample_long_capture.py --minutes 3

WHY THIS EXISTS. Event segmentation was tested on CARLA episodes of 40 frames — about two seconds,
barely one event — and tuning a boundary detector against two seconds of anything is not measurement.
What the test needs is long footage where the true boundaries are known exactly.

THE GROUND TRUTH IS BETTER HERE THAN POSE, and that is not a compromise. In CARLA the boundaries had
to be INFERRED from pose by thresholding speed and yaw rate, so the answer key was itself a guess
with parameters in it — and a detector scored against a guessed key can be wrong in the same
direction as the key and look right. Here ATANOR issues the commands, so the moment a regime changes
is recorded rather than derived: no threshold, no percentile, nothing to tune. The frame index where
`travel` became `turn` is written down as it happens.

WHAT A REGIME IS. A stretch during which one motor command is held: travelling, turning left,
turning right, standing still. Standing still is included deliberately — a segmenter that only fires
on motion would score well on footage that is always moving, and the honest test needs the boundary
where motion STOPS as much as where it starts.

The order is drawn at random rather than cycled, so a detector cannot do well by learning the
rhythm; and each regime's duration varies, so boundary spacing carries no information either.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.eye import WindowSource, open_eye                  # noqa: E402
from packages.hand import Move, WindowEffector                   # noqa: E402

OUT = Path(r"D:\citysample_long")


def _downscale(rgb: np.ndarray, w: int = 320, h: int = 240) -> np.ndarray:
    ys = (np.arange(h) * (rgb.shape[0] / h)).astype(np.int32)
    xs = (np.arange(w) * (rgb.shape[1] / w)).astype(np.int32)
    return np.ascontiguousarray(rgb[ys][:, xs])


def _moves_from_schema(path: Path, hold: float) -> dict[str, Move]:
    """Travel and turn moves, chosen by what babbling MEASURED them to do — not by their names."""
    s = json.loads(path.read_text(encoding="utf-8"))
    best_travel, travel_score = None, 0.0
    for key, v in s.get("moves", {}).items():
        if key.startswith("mouse"):
            continue
        if v.get("div", 0) > 0.4 and v["div"] > travel_score:
            best_travel, travel_score = key, v["div"]
    if best_travel is None:
        sys.exit(f"no move in {path} was measured to translate — babble first")
    # TURN SLOWLY ENOUGH TO STAY THE SAME SCENE. The first capture used 260 counts issued every
    # 50ms, which spins the view so fast that frames 0.45s apart are UNRELATED images: phase
    # correlation returned confidence 0.21 and a shift of 0.01px where it should have been large, and
    # every efference-copy gain calibrated to zero because no shift can bridge two unrelated views.
    # The footage looked fine by every summary — 21,032 frames, four regimes, clean separation
    # between them (still 1.2, travel 15.2, turning 27.6 mean pixel difference) — and was useless for
    # anything that has to MATCH one frame to the next.
    return {"travel": Move(keys=tuple(best_travel.split("+")), seconds=hold, label="travel"),
            # 45 counts per 100ms was STILL too fast: ~200 counts per 0.45s sample interval, which
            # spins the camera clear of the scene, so consecutive samples are unrelated images and
            # phase correlation read 0.07px at confidence 0.29. The number that matters is total
            # rotation per sample interval, not per command, and it has to stay small enough that
            # the two views overlap. 8 counts every 250ms is ~14 per 0.45s.
            # Bracketed by three captures rather than guessed: 260/50ms and 45/100ms both spin
            # clear of the scene (~200 counts per 0.45s, views unrelated); 8/250ms is BELOW the
            # game's response (~14 counts per 0.45s, under a pixel, confidence 0.99 because the
            # frames are near-identical). ~55 counts per 0.45s sits between them.
            "turn_left": Move(mouse_dx=-25, seconds=0.20, label="turn_left"),
            "turn_right": Move(mouse_dx=25, seconds=0.20, label="turn_right"),
            "still": Move(seconds=hold, label="still")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--window", default="CitySample")
    ap.add_argument("--schema", default=r"D:\citysample_drive\body_schema_latest.json")
    ap.add_argument("--tag", default="long")
    args = ap.parse_args()

    hand = WindowEffector(title_contains=args.window)
    ok, why = hand.available()
    if not ok:
        sys.exit(f"hand unavailable: {why}")
    got, detail = hand.focus()
    if not got:
        sys.exit(f"cannot focus {args.window!r}: {detail}")
    print(f"focused: {detail}\nengaged: {hand.engage()}", flush=True)
    time.sleep(0.8)

    moves = _moves_from_schema(Path(args.schema), 0.35)
    src = WindowSource(title_contains=args.window)
    ok, why = src.available()
    if not ok:
        sys.exit(f"eye unavailable: {why}")
    eye = open_eye(src, gate=False)

    run = OUT / f"{args.tag}_{time.strftime('%H%M%S')}"
    run.mkdir(parents=True, exist_ok=True)

    state = {"regime": "still", "frame": 0, "stop": False,
             "in_control": True, "interruptions": 0}
    regimes: list[dict] = []
    lock = threading.Lock()
    rng = np.random.default_rng(0)

    def drive() -> None:
        names = list(moves)
        while not state["stop"]:
            r = names[int(rng.integers(0, len(names)))]
            secs = float(rng.uniform(1.6, 5.0))
            with lock:
                # RECORDED, not derived: this is the frame the regime changed on.
                regimes.append({"regime": r, "start_frame": state["frame"], "t": time.time()})
                state["regime"] = r
            t0 = time.time()
            state["in_control"] = True
            while time.time() - t0 < secs and not state["stop"]:
                if r == "still":
                    time.sleep(0.15)
                    continue
                res = hand.do(moves[r])
                if not res.get("ok"):
                    # WAIT, DO NOT DIE. Losing the foreground is transient — Windows Search opening,
                    # a notification, the operator glancing at something — and the first version
                    # returned on it, so one moment of lost focus killed the driver and the rest of
                    # the run recorded a motionless scene under whatever regime was current. Three
                    # captures were ruined that way, and the last one said so out loud:
                    # "driver stopped: not_foreground - foreground is '검색'".
                    #
                    # The REFUSAL is right and stays: keystrokes must never go to whatever window
                    # happens to be in front. What was wrong was treating a refusal as fatal. So it
                    # pauses, and the frames captured while it was not in control are marked, so they
                    # can be excluded rather than silently counted as a regime that was never driven.
                    state["in_control"] = False
                    state["interruptions"] += 1
                    time.sleep(0.4)
                    continue

    th = threading.Thread(target=drive, daemon=True)
    th.start()

    kept, stale, dup, uncontrolled, occluded = 0, 0, 0, 0, 0
    last_thumb = None
    times, marks = [], []
    t0 = time.perf_counter()
    limit = args.minutes * 60.0
    try:
        while time.perf_counter() - t0 < limit:
            look = eye.look()
            if look.frame.meta.get("occluded"):
                # THE HAND REFUSES WHEN FOCUS IS LOST AND THE EYE DID NOT. That asymmetry is what
                # ruined four captures: the driver paused, the eye kept recording whatever window was
                # now on top, and the frames were written under the current regime label as though
                # the body had been doing that all along. A sense organ that keeps reporting while
                # pointed at the wrong thing is worse than one that stops.
                occluded += 1
                continue
            if not look.frame.meta.get("fresh"):
                stale += 1
                continue
            # AND CHECK. The eye's freshness flag comes from Desktop Duplication, which reports that
            # the DESKTOP changed — not that this window did. At 87fps the first capture kept 21,032
            # frames all flagged fresh, of which 55% were pixel-identical to their predecessor. A
            # duplicate carries no motion, so it dilutes every measurement that reads motion while
            # inflating the frame count that makes the corpus look large.
            thumb = _downscale(look.frame.rgb, 40, 30).astype(np.int16)
            if last_thumb is not None and np.abs(thumb - last_thumb).mean() < 0.5:
                dup += 1
                continue
            last_thumb = thumb
            with lock:
                cur = state["regime"]
                ctrl = state["in_control"]
                state["frame"] = kept
            if not ctrl:
                uncontrolled += 1
                continue                      # captured while not in control; not this regime
            np.savez_compressed(run / f"{kept:06d}.npz", rgb=_downscale(look.frame.rgb),
                                t_mono=np.float64(look.frame.t_mono))
            times.append(look.frame.t_mono)
            marks.append(cur)
            kept += 1
            if kept % 900 == 0:
                print(f"  {kept} frames, {time.perf_counter()-t0:.0f}s, regime={cur}", flush=True)
    finally:
        state["stop"] = True
        th.join(timeout=3.0)
        hand.release_all()

    # VERIFY THE FOOTAGE BEFORE TRUSTING IT. Two captures were written, summarised cleanly, and were
    # useless for anything that has to match one frame to the next — a turn that leaves the scene
    # produces a huge pixel difference and no trackable motion, which no frame count reveals. So the
    # run measures its own trackability and says whether the motion can be followed.
    import cv2
    files = sorted(run.glob("*.npz"))
    step = max(1, int(round((kept / max(time.perf_counter() - t0, 1e-6)) * 0.45)))
    track: dict[str, list] = {}
    for i in range(step, min(len(files), 4000), max(1, step * 2)):
        a = cv2.cvtColor(np.load(files[i - step])["rgb"], cv2.COLOR_RGB2GRAY).astype(np.float32)
        b = cv2.cvtColor(np.load(files[i])["rgb"], cv2.COLOR_RGB2GRAY).astype(np.float32)
        (dx, _), resp = cv2.phaseCorrelate(a, b)
        track.setdefault(marks[i], []).append((dx, resp))
    trackability = {r: {"dx_median": round(float(np.median([v[0] for v in vs])), 2),
                        "confidence": round(float(np.median([v[1] for v in vs])), 3),
                        "n": len(vs)}
                    for r, vs in sorted(track.items())}
    lr = [trackability.get(k, {}).get("dx_median", 0.0) for k in ("turn_left", "turn_right")]
    usable = (len(lr) == 2 and lr[0] * lr[1] < 0 and min(abs(lr[0]), abs(lr[1])) > 0.5)

    dt = time.perf_counter() - t0
    gaps = np.diff(times) if len(times) > 1 else np.array([0.0])
    # boundaries as FRAME INDICES, which is what the segmenter is scored against
    bounds = [r["start_frame"] for r in regimes if 0 < r["start_frame"] < kept]
    meta = {"tag": args.tag, "seconds": round(dt, 1), "frames": kept, "stale_dropped": stale,
            "duplicates_dropped": dup, "fps": round(kept / dt, 2),
            "gap_ms": {"median": round(float(np.median(gaps)) * 1000, 1),
                       "p90": round(float(np.percentile(gaps, 90)) * 1000, 1)},
            "trackability": trackability, "self_motion_usable": bool(usable),
            "interruptions": state["interruptions"], "uncontrolled_dropped": uncontrolled,
            "occluded_dropped": occluded,
            "regimes": regimes, "boundaries": bounds,
            "regime_per_frame": marks, "size": [320, 240],
            "ground_truth": "recorded at the moment the command changed; not inferred"}
    (run / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items()
                      if k not in ("regimes", "regime_per_frame", "boundaries")}, indent=2))
    print(f"{len(bounds)} recorded boundaries over {kept} frames")
    print("trackability of the body's own motion over 0.45s:")
    for r, v in trackability.items():
        print(f"  {r:11s} dx {v['dx_median']:+7.2f} px   confidence {v['confidence']:.3f}   n={v['n']}")
    print(f"-> self-motion {'USABLE' if usable else 'NOT USABLE'} "
          f"(turns must be large and OPPOSITE in sign)")
    print("wrote", run)
    eye.close()


if __name__ == "__main__":
    main()
