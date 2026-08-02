# -*- coding: utf-8 -*-
"""Sixth attempt at the body, scored in pixels against the verified oracle.

    python scripts/body_from_pixels.py

Five failures today, each measured rather than assumed:

    as a stated task              1.48 against a 1.5 bar
    as a by-product of curiosity  better separated (0.1637) and never used
    online, over track ids        3.9 identity switches per episode
    chains, nearest blob          0.6% of frames on the body against 4.1% for choosing at random
    chains, motion-restricted     57.4% -- but all nine chains landed within 0.74 percentage points of
                                  each other, so they were one hypothesis wearing nine labels

And the diagnosis against the oracle ruled out everything but the plumbing: the body is inside a blob
in 100.0% of frames, and the true body's track ranked FIRST of 42 under command_prediction whenever it
had enough evidence to be scored at all.

So this rung changes the TRACKER and not the criterion. `packages/perception/sprite_tracker.py` adds
the two standard things the chains lacked -- one-to-one assignment, and matching against a predicted
position rather than a past one -- plus coasting through a missed frame instead of dying.

WHY IT SHOULD MATTER, stated before the numbers so it can be wrong: every identity swap observed today
happened where two sprites passed close together, which is exactly where proximity fails and velocity
does not, and the merge happened because nothing forbade two chains from taking the same blob.

REGISTERED, against the motion-chain rung it must beat:
    1  the tracks are DISTINGUISHABLE -- spread of on-body% across tracks well above the 0.74pp that
       exposed the merge. Without this, a good number is one hypothesis getting lucky.
    2  the track chosen by command_prediction is on the body above 57.4%
    3  and far above what choosing a track at random gives, measured in the same run

The oracle is used ONLY to score, never to decide. Nothing in the tracker or the criterion sees it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy.random as _npr                                                  # noqa: E402

from packages.perception.sprite_tracker import SpriteTracker                 # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                          # noqa: E402
from scripts.atari_find_body import command_prediction, measured_warmup      # noqa: E402
from scripts.atari_play import make                                          # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy      # noqa: E402

OUT = Path("data/atari/body_from_pixels.json")
CHAIN_BEST, CHAIN_SPREAD, CHAIN_CHANCE = 0.574, 0.0074, 0.569


def calibrated_jump(env, warm: int, rng, n_a: int, bg, obs, q: float = 95.0) -> float:
    """How far a sprite actually moves between decisions, measured. The 14 px inherited from the
    babble script is smaller than the body's own step -- today's oracle put its per-step displacement
    at sd 19.7 px in x -- so tracks were being cut at every fast move. Derived, not chosen."""
    prev = blobs(sprite_mask(obs, bg))
    ds = []
    for _ in range(120):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, *_ = env.step(a)
        cur = blobs(sprite_mask(obs, bg))
        if prev and cur:
            P = np.array([[b[0], b[1]] for b in prev])
            C = np.array([[b[0], b[1]] for b in cur])
            D = np.hypot(P[:, None, 0] - C[None, :, 0], P[:, None, 1] - C[None, :, 1])
            ds += list(D.min(axis=1))
        prev = cur
    return float(np.percentile(ds, q)) if ds else 14.0


def command_prediction_z(evidence, trials: int = 40, seed: int = 0) -> float:
    """command_prediction, corrected for evidence length by its OWN shuffled-action null.

    The raw statistic prefers short tracks: 18 samples scored 0.4664 against 30 samples at 0.3893, and
    the 30-sample track was the one actually on the body 100% of the time. This is the same small-sample
    bias that forced a per-track null earlier today, and the same fix -- shuffle which action produced
    each displacement and subtract what the statistic scores on noise of that length."""
    if len(evidence) < 12:
        return -1e9
    real = command_prediction(evidence)
    acts = [e[0] for e in evidence]
    rng = _npr.default_rng(seed)
    null = []
    for _ in range(trials):
        perm = rng.permutation(acts)
        null.append(command_prediction([(int(a), e[1], e[2]) for a, e in zip(perm, evidence)]))
    m, sd = float(np.mean(null)), float(np.std(null))
    return (real - m) / sd if sd > 1e-9 else real - m


def run(steps: int = 900, seed: int = 3):
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=seed)
    env.close()
    if not (agree["r_x"] > 0.9 and agree["r_y"] > 0.9):
        sys.exit("the oracle failed its own check; a pixel score against it would mean nothing")

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

    jump = calibrated_jump(env, warm, rng, n_a, bg, obs)
    print(f"max_jump calibrated from the screen: {jump:.1f} px "
          f"(the inherited constant was 14.0)\n")
    tr = SpriteTracker(max_jump=jump)
    hist: dict = {}
    truth = []
    for t in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        tr.step(blobs(sprite_mask(obs, bg)), action=a)
        truth.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
        for k in tr.tracks:
            hist.setdefault(k.id, {})[t] = k.pos.copy()
    env.close()
    return tr, hist, np.array(truth), agree, jump


def on_body(hist_for_id: dict, truth: np.ndarray) -> tuple[float, int]:
    """Fraction of the frames this track existed in which it sat on the body, and how many that was."""
    if not hist_for_id:
        return 0.0, 0
    ts = sorted(hist_for_id)
    P = np.array([hist_for_id[t] for t in ts])
    T = truth[ts]
    hit = np.hypot(P[:, 0] - T[:, 0], P[:, 1] - T[:, 1]) < 8.0
    return float(hit.mean()), len(ts)


def main() -> None:
    tr, hist, truth, agree, jump = run()
    print(f"oracle verified r_x {agree['r_x']:.3f} r_y {agree['r_y']:.3f}; it SCORES and never decides\n")

    scored = tr.scored(command_prediction_z)
    print(f"{len(tr.tracks)} live tracks, {len(scored)} with >= 12 samples of evidence "
          f"(chains gave 9 tracks that were really one)\n")
    print(f"{'track':>7}{'evidence':>11}{'command pred':>15}{'frames':>9}{'ON THE BODY':>14}")
    rows = []
    for k, s in scored[:12]:
        frac, n = on_body(hist.get(k.id, {}), truth)
        rows.append({"id": k.id, "score": float(s), "on_body": frac, "frames": n,
                     "evidence": len(k.evidence)})
        mark = "  <- chosen, unsupervised" if k is scored[0][0] else ""
        print(f"{k.id:>7}{len(k.evidence):>11}{s:>15.4f}{n:>9}{frac:>13.1%}{mark}")

    fr = [r["on_body"] for r in rows]
    chosen = rows[0]["on_body"] if rows else 0.0
    spread = float(np.std(fr)) if len(fr) > 1 else 0.0
    chance = float(np.mean(fr)) if fr else 0.0
    best_available = max(fr) if fr else 0.0

    print(f"\n-> 1. the tracks are distinguishable: spread {spread:.1%} across tracks "
          f"(the merged chains gave {CHAIN_SPREAD:.2%})  {spread > 4 * CHAIN_SPREAD}")
    print(f"-> 2. the chosen track is on the body {chosen:.1%}, against the chains' {CHAIN_BEST:.1%}  "
          f"{chosen > CHAIN_BEST}")
    print(f"-> 3. and against picking a track at random, {chance:.1%} in this run  {chosen > chance}")
    print(f"   the statistic picked the best track available: "
          f"{abs(chosen - best_available) < 1e-9}  (best {best_available:.1%})")

    ok = spread > 4 * CHAIN_SPREAD and chosen > CHAIN_BEST and chosen > chance
    print(f"\n{'PASSES' if ok else 'FAILS'} — "
          f"{'the merge is broken and the criterion finally has separate hypotheses to choose between'
             if ok else 'the tracker did not separate the body from the rest'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"oracle": agree, "tracks": rows, "chosen_on_body": chosen,
                               "spread": spread, "chance": chance,
                               "best_available": best_available, "max_jump": jump, "passes": bool(ok)},
                              indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
