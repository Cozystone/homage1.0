# -*- coding: utf-8 -*-
"""F2: pay only for change, and test the thesis that says we can.

    python scripts/event_driven_perception.py

The thesis in docs/ATANOR_eye_how_we_win_2026-07-30.md: we beat a per-frame detector not by recognising
better but by being a stateful predictive system, whose cost is proportional to SURPRISE. A detector's cost
is flat by architecture; ours is allowed to fall.

The headroom is measured: 99.0% of every Atari frame is unchanged, 350 pixels of 33,600, and recomputing
only where the world surprised us is worth 25-97x depending on the halo. This rung asks whether the REAL
CHAIN delivers any of it, which is the registered refutation condition:

    If wiring event-driven computation does not deliver a large measured saving on the real chain with
    accuracy held, the thesis is wrong -- 25-97x in principle, and if the chain gives 2x then the cost is
    organ dependencies rather than pixels, and the plan needs rewriting rather than continuing.

WHAT "EVENT-DRIVEN" MEANS HERE, and it is deliberately the cheapest possible version so that a win cannot
be attributed to a clever predictor:

    the predictor is THE PREVIOUS FRAME. Nothing learned, nothing tuned.
    a region is recomputed when its change exceeds the threshold the incumbent mask already uses (40),
      so the same evidence that would have produced a sprite pixel is what triggers the work.
    everything else is CARRIED FORWARD from the last computation.

If even that gives a real saving, a better world model can only widen it. If it does not, no world model
will rescue it, because the ceiling is elsewhere.

MEASURED ON BOTH AXES, since a saving that costs accuracy is not a saving:
    1  wall-clock and pixels touched per decision, against the full-recompute incumbent
    2  the chain's own accuracy -- blobs, and body-finding via the same tracker and criterion
    3  and against a control that skips frames at RANDOM at the same rate, because a saving that survives
       random skipping was never about surprise
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.learned_signature import Pairs, crop, embed, train           # noqa: E402
from packages.perception.self_criterion import intention_momentum                     # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                          # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                                   # noqa: E402
from scripts.learned_appearance_merge import harvest_from_tracks                      # noqa: E402
from scripts.merge_radius_e2 import CalibratedBuckets, pair_distances, youden_radius  # noqa: E402
from scripts.wire_learned_mask import frames_of                                       # noqa: E402

OUT = Path("data/atari/event_driven_perception.json")
CHANGE = 40          # the incumbent mask's own threshold; not a new constant


class EventDriven:
    """Recompute the mask only inside changed regions; carry the rest forward.

    The predictor is the previous frame and nothing else. A saving here cannot be credited to a good
    world model, which is the point: it is a floor on what surprise-proportional computation buys."""

    def __init__(self, bg, halo: int = 2):
        self.bg = bg
        self.halo = halo
        self.prev = None
        self.mask = None
        self.px = 0

    def __call__(self, frame):
        if self.prev is None or self.mask is None:
            self.mask = sprite_mask(frame, self.bg)
            self.px += frame.shape[0] * frame.shape[1]
            self.prev = frame
            return self.mask
        d = np.abs(frame.astype(np.int16) - self.prev.astype(np.int16)).sum(axis=2) > CHANGE
        if self.halo:
            import scipy.ndimage as ndi
            d = ndi.binary_dilation(d, iterations=self.halo)
        n = int(d.sum())
        self.px += n
        if n:
            fresh = sprite_mask(frame, self.bg)
            self.mask = np.where(d, fresh, self.mask)
        self.prev = frame
        return self.mask


class RandomSkip:
    """The control: recompute the same FRACTION of pixels, chosen at random rather than by surprise."""

    def __init__(self, bg, frac: float, seed: int = 0):
        self.bg = bg
        self.frac = frac
        self.rng = np.random.default_rng(seed)
        self.mask = None
        self.px = 0

    def __call__(self, frame):
        if self.mask is None:
            self.mask = sprite_mask(frame, self.bg)
            self.px += frame.shape[0] * frame.shape[1]
            return self.mask
        H, W = frame.shape[:2]
        d = self.rng.random((H, W)) < self.frac
        self.px += int(d.sum())
        fresh = sprite_mask(frame, self.bg)
        self.mask = np.where(d, fresh, self.mask)
        return self.mask


def chain(mask_of, frames, acts, truth, dev, shared_net=None):
    tr = SpriteTracker(max_jump=22.0)
    per_frame, counts = [], []
    t0 = time.perf_counter()
    for t, f in enumerate(frames):
        bl = blobs(mask_of(f))
        counts.append(len(bl))
        before = {k.id: k.pos.copy() for k in tr.tracks}
        tr.step(bl, action=acts[t], moving_only=False)
        per_frame.append([(k.id, k.pos.copy(), k.pos - before.get(k.id, k.pos)) for k in tr.tracks])
    ms = 1000.0 * (time.perf_counter() - t0) / len(frames)

    pairs = harvest_from_tracks(frames, per_frame)
    out = {"ms_per_frame": ms, "blobs_mean": float(np.mean(counts))}
    if len(pairs) < 150:
        out.update({"on_body_overall": 0.0, "note": "too few triplets"})
        return out
    cut = len(pairs) // 5
    ho = Pairs(pairs.a[:cut], pairs.p[:cut], pairs.n[:cut])
    net = shared_net or train(Pairs(pairs.a[cut:], pairs.p[cut:], pairs.n[cut:]),
                              epochs=25, device=dev)
    same, diff = pair_distances(lambda x: embed(net, x, dev), ho)
    r, _j = youden_radius(same, diff)
    B = CalibratedBuckets(r)
    look, seen = {}, collections.defaultdict(collections.Counter)
    mem = collections.defaultdict(list)
    hist = collections.defaultdict(dict)
    for t, rows in enumerate(per_frame):
        for tid, pos, d in rows:
            c = crop(frames[t], pos)
            k = -1 if c is None else B.key(embed(net, c[None], dev)[0])
            seen[tid][k] += 1
            look[tid] = seen[tid].most_common(1)[0][0]
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[look[tid]].append((acts[t], float(d[0]), float(d[1])))
            hist[look[tid]][t] = pos
    scored = [(b, intention_momentum(ev)) for b, ev in mem.items() if len(ev) >= 12]
    if not scored:
        out.update({"on_body_overall": 0.0, "note": "no bucket reached 12 samples", "net": net})
        return out
    chosen = max(scored, key=lambda x: x[1])[0]
    ts = sorted(hist.get(chosen, {}))
    P = np.array([hist[chosen][t] for t in ts]) if ts else np.zeros((0, 2))
    hit = (np.hypot(P[:, 0] - truth[ts, 0], P[:, 1] - truth[ts, 1]) < 8.0) if ts else np.zeros(0)
    pres = len(ts) / len(frames)
    acc = float(hit.mean()) if len(hit) else 0.0
    out.update({"presence": pres, "on_body_given_present": acc,
                "on_body_overall": pres * acc, "net": net})
    return out


def main() -> None:
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    frames, bg, acts, truth, agree = frames_of(400, seed=3)
    H, W = frames[0].shape[:2]
    full = H * W
    print(f"oracle verified r_x {agree['r_x']:.3f}; it SCORES and never decides")
    print(f"{len(frames)} frames of {W}x{H} = {full} px each, {dev}\n")

    ev = EventDriven(bg, halo=2)
    for f in frames:
        ev(f)
    frac = ev.px / (full * len(frames))
    print(f"event-driven touched {ev.px} px over {len(frames)} frames = {frac:.2%} of full\n")

    arms = {
        "full recompute (incumbent)": (lambda f: sprite_mask(f, bg), full),
        "EVENT-DRIVEN (surprise)": (EventDriven(bg, halo=2), None),
        "random skip, same rate (control)": (RandomSkip(bg, frac), None),
    }
    print(f"{'policy':<34}{'px/frame':>10}{'ms/frame':>10}{'blobs':>8}"
          f"{'presence':>10}{'ON-BODY':>9}")
    res, shared = {}, None
    for name, (mof, fixed) in arms.items():
        r = chain(mof, frames, acts, truth, dev, shared_net=shared)
        if shared is None:
            shared = r.pop("net", None)
        else:
            r.pop("net", None)
        px = fixed if fixed is not None else getattr(mof, "px", 0) / len(frames)
        r["px_per_frame"] = float(px)
        res[name] = r
        print(f"{name:<34}{px:>10.0f}{r['ms_per_frame']:>10.2f}{r['blobs_mean']:>8.1f}"
              f"{r.get('presence', 0):>9.1%}{r['on_body_overall']:>9.1%}", flush=True)

    F = res["full recompute (incumbent)"]
    E = res["EVENT-DRIVEN (surprise)"]
    C = res["random skip, same rate (control)"]
    px_save = F["px_per_frame"] / max(E["px_per_frame"], 1e-9)
    ms_save = F["ms_per_frame"] / max(E["ms_per_frame"], 1e-9)
    held = E["on_body_overall"] >= F["on_body_overall"] - 0.03
    beats_ctrl = E["on_body_overall"] > C["on_body_overall"] + 0.03
    print(f"\n-> pixels saved: {px_save:.1f}x   wall clock saved: {ms_save:.2f}x")
    print(f"-> accuracy held (within 3 points): {held}  "
          f"({F['on_body_overall']:.1%} -> {E['on_body_overall']:.1%})")
    print(f"-> and surprise beats random skipping at the same rate: {beats_ctrl}  "
          f"({C['on_body_overall']:.1%})")
    print("\nTHE THESIS' OWN TEST:")
    if held and ms_save > 2.0:
        print(f"   survives -- {ms_save:.1f}x on the real chain with accuracy held.")
    elif held:
        print(f"   PARTIALLY REFUTED. Accuracy holds but the chain gives only {ms_save:.2f}x against")
        print("   25-97x of pixel headroom, so the cost is organ dependencies rather than pixels and")
        print("   the plan needs rewriting rather than continuing -- exactly as registered.")
    else:
        print("   REFUTED on accuracy: skipping costs the chain more than it saves.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"arms": res, "px_saving": px_save, "ms_saving": ms_save,
                               "accuracy_held": bool(held), "beats_random_skip": bool(beats_ctrl)},
                              indent=2, default=str), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
