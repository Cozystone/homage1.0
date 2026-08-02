# -*- coding: utf-8 -*-
"""ATANOR goes for a walk, because it wants to see something it has not seen.

    python scripts/atanor_explore_city.py --window CitySample --steps 60

Two rungs, in the order they have to happen. First it moves at random and finds out what its own
moves do (`babble`). Then it uses that to go somewhere (`explore`) — choosing each move by how much
NEW WORLD that move has been delivering, which it also finds out by doing it.

Nothing here supplies a destination, a route, or a meaning for any key. The operator supplies a
window and a body; everything after that is measured.

WHAT THE KEPT FRAMES ARE, AND WHAT THAT IS NOT YET WORTH. A frame is written only where the view was
unfamiliar against everything seen so far, so the pile is de-duplicated by construction: 52 frames
out of 90 steps, every one of them at least 0.02 from all its predecessors.

It does NOT follow that this makes a better corpus than recording, and the measurement says so. Those
52 frames have a mean pairwise distance of 0.0647; 52 frames sampled evenly from a hand-flown drive
score 0.0799. Curiosity selected a *less* varied set than plain sampling did.

The comparison is confounded — the hand-flown drive crossed the whole city in 75 seconds while this
loop shuffles around a block in 0.45-second presses — so it is not evidence that the rule is bad
either. What it does mean is that "curiosity widens the corpus" is an untested claim, and the honest
current statement is narrower: the rule removes duplicates, and whether it beats sampling for
coverage is unmeasured and needs runs that travel comparable distances.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.eye import WindowSource, open_eye                       # noqa: E402
from packages.hand import Move, WindowEffector, babble, explore       # noqa: E402

OUT = Path(r"D:\citysample_drive")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="CitySample")
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--hold", type=float, default=0.45)
    ap.add_argument("--schema", default="", help="reuse a schema instead of babbling again")
    args = ap.parse_args()

    hand = WindowEffector(title_contains=args.window)
    ok, why = hand.available()
    if not ok:
        sys.exit(f"hand unavailable: {why}")
    got, detail = hand.focus()
    if not got:
        sys.exit(f"cannot focus {args.window!r}: {detail}")
    print(f"focused: {detail}", flush=True)
    print(f"engaged: {hand.engage()}", flush=True)
    time.sleep(1.0)

    src = WindowSource(title_contains=args.window)
    ok, why = src.available()
    if not ok:
        sys.exit(f"eye unavailable: {why}")
    eye = open_eye(src, gate=False)

    moves = [Move(keys=(k,), seconds=args.hold, label=k) for k in ("w", "a", "s", "d", "q", "e", "space")]
    moves += [Move(mouse_dx=350, seconds=0.05, label="mouse+x"),
              Move(mouse_dx=-350, seconds=0.05, label="mouse-x"),
              Move(mouse_dy=250, seconds=0.05, label="mouse+y"),
              Move(mouse_dy=-250, seconds=0.05, label="mouse-y"),
              Move(keys=("lshift", "w"), seconds=args.hold, label="lshift+w")]

    if args.schema:
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        print(f"reusing schema from {args.schema}", flush=True)
    else:
        print("learning the body first ...", flush=True)
        schema = babble(eye, hand, moves, repeats=3).summary()

    run = OUT / f"explore_{time.strftime('%H%M%S')}"
    print(f"exploring {args.steps} steps ...", flush=True)
    t0 = time.time()
    rep = explore(eye, hand, moves, schema, steps=args.steps, keep=run)
    print(f"done in {time.time()-t0:.1f}s\n", flush=True)

    if not rep.get("ok"):
        print("stopped:", rep.get("stopped") or rep.get("refused"), rep.get("detail", ""))
    print(f"places seen : {rep['places_seen']}")
    print(f"frames kept : {rep['frames_kept']}   -> {run}")
    print("\n=== what each move turned out to be worth ===")
    for k, v in rep["move_value"].items():
        print(f"  {k:10s} tried {v['tries']:3d}   mean novelty {v['mean_novelty']:.4f}")

    (run if run.exists() else OUT).mkdir(parents=True, exist_ok=True)
    (OUT / "explore_latest.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    eye.close()
    hand.release_all()


if __name__ == "__main__":
    main()
