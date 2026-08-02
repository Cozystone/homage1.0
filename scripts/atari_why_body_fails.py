# -*- coding: utf-8 -*-
"""Now that the answer is visible, ask why the self-found body missed it. Diagnosis, not a new organ.

    python scripts/atari_why_body_fails.py

The taught rung gave two things: a ceiling (+658 for a supplied body) and, more usefully, an ORACLE
verified at r=1.000 against an independent reading. That converts every previous failure at body
finding from "the score did not rise" into "the estimate was wrong HERE, by THIS many pixels" — which
is the difference between a verdict and a diagnosis.

THREE EXPLANATIONS FOR THE 3.9 SWITCHES PER EPISODE, and they demand opposite repairs:

    fragmentation   the statistic is right and the TRACK IDENTITY it is attached to keeps breaking,
                    so evidence accumulated about the body is thrown away and restarted. Repair:
                    accumulate evidence over space, not over track ids.
    ambiguity       identities are stable and several tracks genuinely look command-predicted, so the
                    statistic cannot separate them. Repair: a better statistic.
    detection       the body is often not a blob at all — missed by background subtraction — so there
                    is nothing to pick. Repair: a different detector.

They are distinguishable with the oracle in hand and nothing else needs building: label each frame's
true body, see which blob it is, and measure how long that blob keeps its id, how often it exists at
all, and how it ranks under the statistic that was used.

WHAT THIS RUNG MAY AND MAY NOT CLAIM. It is diagnosis on supervised labels. It cannot demonstrate any
capability; it can only say which repair is worth attempting. The repair itself has to work unsupervised
or it does not count.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask         # noqa: E402
from scripts.atari_find_body import command_prediction, measured_warmup   # noqa: E402
from scripts.atari_play import make                                # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy   # noqa: E402

OUT = Path("data/atari/why_body_fails.json")


def run(steps: int = 700, seed: int = 3):
    """Play randomly; at every frame record the truth, the blobs, and which blob is the body."""
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=seed)
    env.close()
    if not (agree["r_x"] > 0.9 and agree["r_y"] > 0.9):
        sys.exit("the oracle failed its check in this seed; diagnosis on an unverified label is worthless")

    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    tracks: dict[int, list] = defaultdict(list)
    prev = blobs(sprite_mask(obs, bg))
    ids = list(range(len(prev)))
    nxt = len(prev)

    frames = []          # per frame: truth, id of the blob holding the body, distance to it
    for _t in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        truth = screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY)

        cur = blobs(sprite_mask(obs, bg))
        new_ids: list = [None] * len(cur)
        for i0, i1, dx, dy in match(prev, cur, max_jump=12.0):
            new_ids[i1] = ids[i0]
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                tracks[ids[i0]].append((a, dx, dy))
        for k in range(len(cur)):
            if new_ids[k] is None:
                new_ids[k] = nxt
                nxt += 1
        prev, ids = cur, new_ids

        if cur:
            d = [float(np.hypot(c[0] - truth[0], c[1] - truth[1])) for c in cur]
            j = int(np.argmin(d))
            frames.append({"truth": truth.tolist(), "body_id": ids[j], "dist": d[j], "n_blobs": len(cur)})
        else:
            frames.append({"truth": truth.tolist(), "body_id": None, "dist": np.inf, "n_blobs": 0})
    env.close()
    return frames, tracks


def main() -> None:
    frames, tracks = run()
    D = np.array([f["dist"] for f in frames])
    detected = D < 8.0                       # a blob within a sprite's width of the true body
    print(f"frames {len(frames)}   blobs per frame {np.mean([f['n_blobs'] for f in frames]):.1f}")
    print(f"\nDETECTION  the body is inside some blob in {detected.mean():.1%} of frames")
    print(f"           median distance to the nearest blob: {np.median(D[np.isfinite(D)]):.2f} px")

    # FRAGMENTATION: how long does the id holding the body survive?
    runs, cur_id, n = [], None, 0
    for f, ok in zip(frames, detected):
        if not ok:
            if n:
                runs.append(n)
            cur_id, n = None, 0
            continue
        if f["body_id"] == cur_id:
            n += 1
        else:
            if n:
                runs.append(n)
            cur_id, n = f["body_id"], 1
    if n:
        runs.append(n)
    R = np.array(runs) if runs else np.array([0])
    distinct = len({f["body_id"] for f, ok in zip(frames, detected) if ok})
    print(f"\nFRAGMENTATION  the id holding the body survives {np.median(R):.0f} frames (median), "
          f"{R.mean():.1f} mean, longest {R.max()}")
    print(f"               {distinct} distinct ids held the body across {int(detected.sum())} frames")
    print(f"               the play loop re-estimated every 25 frames and required 12 samples")

    # AMBIGUITY: among tracks long enough to score, where does the true body rank?
    body_ids = {f["body_id"] for f, ok in zip(frames, detected) if ok}
    scored = {t: command_prediction(v) for t, v in tracks.items() if len(v) >= 12}
    ranked = sorted(scored, key=lambda t: -scored[t])
    hits = [i for i, t in enumerate(ranked) if t in body_ids]
    print(f"\nAMBIGUITY  {len(scored)} tracks scoreable; {sum(t in body_ids for t in scored)} of them "
          f"ever held the body")
    if hits and scored:
        best = ranked[hits[0]]
        print(f"           the best-ranked body track sits at position {hits[0] + 1} of {len(ranked)}"
              f"   (score {scored[best]:.4f}, field top {scored[ranked[0]]:.4f})")
        bs = [scored[t] for t in scored if t in body_ids]
        os_ = [scored[t] for t in scored if t not in body_ids]
        if bs and os_:
            print(f"           body tracks score {np.mean(bs):.4f}, others {np.mean(os_):.4f}  "
                  f"-> separation {np.mean(bs) - np.mean(os_):+.4f}")
    else:
        print("           no body track was scoreable at all — which is itself the answer")

    frag = float(np.median(R)) < 25
    amb = bool(hits) and hits[0] > 0
    det = detected.mean() < 0.8
    print("\nWHICH REPAIR THE NUMBERS PICK:")
    if det:
        print(f"   DETECTION. The body is not even a blob in {1 - detected.mean():.0%} of frames, so no")
        print("   statistic over blob tracks can find it. The detector has to change first.")
    elif frag:
        print(f"   FRAGMENTATION. Identity lasts {np.median(R):.0f} frames against the 12 samples the")
        print("   statistic needs and the 25-frame re-estimate, so evidence is discarded before it")
        print("   accumulates. Accumulate over SPACE instead of over track ids.")
    elif amb:
        print("   AMBIGUITY. Identity is stable and the statistic still does not rank the body first.")
        print("   A better statistic is the lever.")
    else:
        print("   None of the three. The estimate should have worked, so the defect is elsewhere.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"frames": len(frames), "detected_frac": float(detected.mean()),
                               "median_dist_px": float(np.median(D[np.isfinite(D)])),
                               "id_run_median": float(np.median(R)), "id_run_mean": float(R.mean()),
                               "id_run_max": int(R.max()), "distinct_ids": distinct,
                               "scoreable_tracks": len(scored),
                               "best_body_rank": (hits[0] + 1) if hits else None},
                              indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
