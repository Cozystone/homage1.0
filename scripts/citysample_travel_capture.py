# -*- coding: utf-8 -*-
"""Capture while the body is actually TRAVELLING, and refuse to pretend when it was not.

    python scripts/citysample_travel_capture.py --seconds 90

WHY THIS EXISTS. The first two City Sample captures were unusable for depth-from-motion and looked
fine: 1,441 and 1,703 frames, no errors, no dropped frames. Measured afterwards, the median flow
between frames was 0.56 px at 320x240 — and it did not grow with the gap between them. Two seconds
apart, the picture had moved less than one pixel:

    stride    1    3   10   30   60
    px       0.56 0.56 0.56 0.56 0.88

Parallax IS the training signal for self-supervised depth. With none, there is nothing to learn, and
the run said so honestly: the auto-mask kept 10% of pixels and the model never beat not-warping. The
frames were not corrupt; the body had barely gone anywhere, because those captures were flown with
short taps and long pauses, and turning was most of the motion.

TURNING IS WORTH NOTHING HERE, and that is geometry rather than a tuning detail. Under pure rotation
every pixel moves the same way whatever its distance, so a rotating camera carries no depth
information at all. Only TRANSLATION separates near from far. So this holds a move the body schema
measured to translate — expansion in the flow field, not sliding — and holds it continuously instead
of tapping it.

IT MEASURES WHAT IT GOT. The capture reports achieved parallax and marks the run `usable_for_depth`
only if it cleared the floor. Writing a corpus without checking is how the first two runs happened,
and a directory of frames gives no sign that the body inside them was standing still.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.eye import WindowSource, open_eye                     # noqa: E402
from packages.hand import Move, WindowEffector                      # noqa: E402
from packages.hand.babble import _block_flow, _grey                 # noqa: E402

OUT = Path(r"D:\citysample_drive")

# A pair of frames needs to have moved this far to constrain depth. Below roughly a pixel the warp
# cannot tell 30m from 100m, which is exactly what the first captures ran into.
MIN_FLOW_PX = 1.5     # at 320x240


def _downscale(rgb: np.ndarray, w: int = 640, h: int = 480) -> np.ndarray:
    ys = (np.arange(h) * (rgb.shape[0] / h)).astype(np.int32)
    xs = (np.arange(w) * (rgb.shape[1] / w)).astype(np.int32)
    return np.ascontiguousarray(rgb[ys][:, xs])


def _travel_move(schema_path: Path, hold: float) -> Move:
    """The move the body schema measured to TRANSLATE, strongest first.

    Read from the babbling record rather than named. If City Sample rebinds its keys, or the body is
    swapped for one that flies rather than walks, this picks up whatever now moves it forward."""
    s = json.loads(schema_path.read_text(encoding="utf-8"))
    best, score = None, 0.0
    for key, v in s.get("moves", {}).items():
        if key.startswith("mouse"):
            continue
        if v.get("div", 0) > 0.4 and v.get("div", 0) > score:      # expansion = closing in
            best, score = key, v["div"]
    if best is None:
        sys.exit(f"no move in {schema_path} was measured to translate — babble first")
    keys = tuple(best.split("+"))
    return Move(keys=keys, seconds=hold, label=best)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--window", default="CitySample")
    ap.add_argument("--hold", type=float, default=2.5, help="seconds per continuous travel burst")
    ap.add_argument("--turn-every", type=int, default=8, help="bursts between course changes")
    ap.add_argument("--schema", default=r"D:\citysample_drive\body_schema_latest.json")
    ap.add_argument("--tag", default="travel")
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

    go = _travel_move(Path(args.schema), args.hold)
    turn = Move(mouse_dx=600, seconds=0.05, label="mouse+x")
    print(f"travelling with {go.label!r} (chosen by measured expansion, not by name)", flush=True)

    src = WindowSource(title_contains=args.window)
    ok, why = src.available()
    if not ok:
        sys.exit(f"eye unavailable: {why}")
    eye = open_eye(src, gate=False)

    run = OUT / f"{args.tag}_{time.strftime('%H%M%S')}"
    run.mkdir(parents=True, exist_ok=True)

    import threading
    stop = threading.Event()

    def _drive():
        """Hold the travel key in a separate thread so capture never pauses for the body."""
        bursts = 0
        while not stop.is_set():
            if not hand.do(go).get("ok"):
                break
            bursts += 1
            if bursts % args.turn_every == 0:
                hand.do(turn)          # change course, so it is not one straight corridor forever

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()

    kept, seen, stale, times = 0, 0, 0, []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < args.seconds:
        look = eye.look()
        seen += 1
        if not look.frame.meta.get("fresh"):
            stale += 1
            continue
        np.savez_compressed(run / f"{kept:05d}.npz", rgb=_downscale(look.frame.rgb),
                            t_mono=np.float64(look.frame.t_mono))
        times.append(look.frame.t_mono)
        kept += 1
    stop.set()
    driver.join(timeout=5.0)
    hand.release_all()
    dt = time.perf_counter() - t0

    # DID IT ACTUALLY MOVE? Measured on what was just written, not assumed from the fact that keys
    # were pressed — every key in the first failed captures reported ok too.
    files = sorted(run.glob("*.npz"))
    mags = []
    for i in range(0, max(0, len(files) - 3), max(1, len(files) // 40)):
        a = np.load(files[i])["rgb"]
        b = np.load(files[i + 3])["rgb"]
        fl = _block_flow(_grey(a), _grey(b))
        mags.append(float(np.sqrt(fl[..., 0] ** 2 + fl[..., 1] ** 2).mean()) * 320 / 96)
    med = float(np.median(mags)) if mags else 0.0
    usable = med >= MIN_FLOW_PX

    gaps = np.diff(times) if len(times) > 1 else np.array([0.0])
    meta = {"tag": args.tag, "seconds": round(dt, 2), "kept": kept, "stale_dropped": stale,
            "fps": round(kept / dt, 2), "travel_move": go.label,
            "gap_ms": round(float(np.median(gaps)) * 1000, 1),
            "parallax_px_at_320": round(med, 2), "floor": MIN_FLOW_PX,
            "usable_for_depth": bool(usable)}
    (run / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("\n" + json.dumps(meta, indent=2))
    print(f"\n{'USABLE' if usable else 'NOT USABLE'} for depth-from-motion "
          f"({med:.2f} px vs floor {MIN_FLOW_PX})")
    print("wrote", run)
    eye.close()


if __name__ == "__main__":
    main()
