# -*- coding: utf-8 -*-
"""ATANOR moves its own body for the first time, and finds out what moving does.

    python scripts/atanor_learn_body.py --window CitySample

Everything the run knows in advance is on this line: there is a window, there are seventeen keys and
a mouse, and there is an eye pointed at the result. It is not told that `w` is forward, that there
is a forward, or that the thing on screen is a city. It presses, it looks, it keeps the pair.

The moves below are listed by KEY, never by meaning, and the labels in the output are descriptions
of measured optical flow — `closes_in`, `view_slides_left` — rather than names borrowed from what a
person knows the key does. If the bindings were changed tomorrow the same script would find the new
mapping and the same words would still be true.

This is the procedure `Track E M1` already passed on a robot arm, on a different body. Whether it
transfers is the question; that it is the SAME procedure is the point.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.eye import WindowSource, open_eye      # noqa: E402
from packages.hand import Move, WindowEffector, babble  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="CitySample")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--hold", type=float, default=0.45)
    args = ap.parse_args()

    hand = WindowEffector(title_contains=args.window)
    ok, why = hand.available()
    if not ok:
        sys.exit(f"hand unavailable: {why}")

    got, detail = hand.focus()
    if not got:
        sys.exit(f"cannot focus {args.window!r}: {detail}")
    print(f"focused: {detail}", flush=True)
    eng = hand.engage()            # foreground is not the same as receiving input; see engage()
    print(f"engaged: {eng}", flush=True)
    time.sleep(1.0)

    src = WindowSource(title_contains=args.window)
    ok, why = src.available()
    if not ok:
        sys.exit(f"eye unavailable: {why}")
    eye = open_eye(src, gate=False)

    # Listed by key. No meanings, no ordering by expected effect.
    moves = [Move(keys=(k,), seconds=args.hold, label=k)
             for k in ("w", "a", "s", "d", "q", "e", "space")]
    moves += [
        Move(mouse_dx=350, seconds=0.05, label="mouse+x"),
        Move(mouse_dx=-350, seconds=0.05, label="mouse-x"),
        Move(mouse_dy=250, seconds=0.05, label="mouse+y"),
        Move(mouse_dy=-250, seconds=0.05, label="mouse-y"),
        Move(keys=("lshift", "w"), seconds=args.hold, label="lshift+w"),
    ]

    print(f"babbling {len(moves)} moves x{args.repeats} ...", flush=True)
    t0 = time.time()
    schema = babble(eye, hand, moves, repeats=args.repeats)
    print(f"done in {time.time()-t0:.1f}s\n", flush=True)

    print("=== what the world does on its own ===")
    print(f"  {schema.still}\n")
    print("=== what ATANOR found out by moving ===")
    for line in schema.describe():
        print("  " + line)

    out = Path(r"D:\citysample_drive\body_schema_latest.json")
    out.write_text(json.dumps(schema.summary(), indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", out)
    eye.close()
    hand.release_all()


if __name__ == "__main__":
    main()
