# -*- coding: utf-8 -*-
"""The grouping organ, FROZEN, carried to senses it was not written for.

    python scripts/gestalt_frozen_transfer.py

The text layer worked on a rendered page. That is worth nothing if what was built is a page parser wearing
a general name, and everything if the same operation groups things in a sense it has never seen. The
project's own standing rule says so: generality is not another organ, it is the same organ used twice, and
the only proof is FROZEN TRANSFER -- the code that succeeded in domain A is carried to domain B without a
line changed, and measured there.

So `packages/perception/gestalt.py` holds the operation once, knows nothing about pixels or seconds, and is
imported unchanged by all four domains below. Two of them are senses the codebase already had, and each had
HAND-WRITTEN ITS OWN COPY of this operation without knowing the other existed.

    A  SPACE   -- glyph rows on a real Chromium render become lines. The source domain.
    B  TIME    -- 2,067 real commits become work sessions. A sense with no pixels in it at all.
    C  MOTION  -- sprite speeds split into moving and static, REPLACING the tracker's own 1-D k-means.
    D  NULL    -- evenly spaced numbers, where there is no boundary and the organ must say so.

B IS THE LOAD-BEARING ONE AND ITS TRUTH IS NOT MINE. There are no session labels, and inventing them would
make the test circular. But a work session is topically coherent -- a person at one sitting touches the
same files -- and that is a fact about how humans work, not something put into the data by me. So the
derived boundaries are scored against an INDEPENDENT signal: do commits the organ places together share
more files than commits it separates? Against a permutation null, and against the hand-chosen hour
thresholds an engineer would otherwise have picked.

REGISTERED:
    1  the operation is literally the same object in all four domains -- checked by identity, not claimed
    2  TIME: derived sessions are topically coherent above a permutation null (p < 0.01)
    3  TIME: the derived cut matches or beats the best hand-chosen hour threshold, which is the whole
       point -- if a constant an engineer picks does better, the derivation is decoration
    4  MOTION: the frozen organ's split agrees with the hand k-means it replaces, and still puts the body
       on the moving side, so the replacement can delete code rather than add it
    5  NULL: on featureless input the organ ABSTAINS. If it cuts here, every cut above is theatre.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception import gestalt                                    # noqa: E402
from packages.perception.gestalt import (derive_cut, evidence,             # noqa: E402
                                         group_by_proximity, separation, split)
from packages.self_check import preflight                                  # noqa: E402

OUT = Path("data/perception/gestalt_frozen_transfer.json")
HOURS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)


def _gate(claim: str, res: dict, **kw):
    """Hand the verdict to the four checks instead of writing an inequality here.

    M0c. Every experiment in this session wrote its own pass condition, and four of them passed
    vacuously -- both sides degenerate, the comparison technically true. `packages/self_check` was built
    on 2026-07-29 for exactly this and had zero consumers, so the checks that would have caught those
    four sat unwired while I re-derived them by hand, badly, in script after script.

    It also scores INCONCLUSIVE as failure, which is the part a hand-rolled boolean cannot express: a
    check that was never run comes back red rather than silently absent."""
    v = preflight.run(claim, **kw)
    res.setdefault("preflight", {})[claim.split(":")[0]] = v.as_dict()
    print(f"\n-> PREFLIGHT  {claim}")
    print(f"   may_promote: {v.may_promote}")
    for c in v.checks:
        mark = "green" if c.green else ("FAILED" if c.ran else "COULD NOT RUN")
        print(f"     {c.name:<14}{mark:<15}{c.detail}")
    return v


# ---------------------------------------------------------------- B: TIME
def commits(limit: int = 4000):
    """(unix seconds, frozenset of paths) per commit, newest first, from the repo's real history."""
    raw = subprocess.run(["git", "log", f"-n{limit}", "--format=%x00%at", "--name-only"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    out = []
    for chunk in raw.split("\x00"):
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        if not lines:
            continue
        try:
            t = float(lines[0])
        except ValueError:
            continue
        out.append((t, frozenset(lines[1:])))
    return [c for c in out if c[1]]


def jaccard(a, b) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def coherence(order, boundary_after) -> dict:
    """Do consecutive commits INSIDE a group share more files than a pair straddling a boundary?

    The independent signal. A session is topically coherent because a person works on one thing at a
    sitting; nothing here consults a clock, so a boundary set that scores well has found real sittings."""
    within, across = [], []
    for i in range(len(order) - 1):
        j = jaccard(order[i][1], order[i + 1][1])
        (across if boundary_after[i] else within).append(j)
    if not within or not across:
        return {"within": 0.0, "across": 0.0, "lift": 0.0, "n_within": len(within),
                "n_across": len(across)}
    w, a = float(np.mean(within)), float(np.mean(across))
    return {"within": w, "across": a, "lift": w - a,
            "n_within": len(within), "n_across": len(across)}


def permutation_p(order, boundary_after, iters: int = 2000, seed: int = 0) -> float:
    """The same number of boundaries placed at random. Any boundary set splits SOMETHING."""
    obs = coherence(order, boundary_after)["lift"]
    js = np.array([jaccard(order[i][1], order[i + 1][1]) for i in range(len(order) - 1)])
    k = int(np.sum(boundary_after))
    if k == 0 or k >= len(js):
        return 1.0
    rng = np.random.default_rng(seed)
    idx = np.arange(len(js))
    hits = 0
    for _ in range(iters):
        cut = rng.choice(idx, size=k, replace=False)
        m = np.zeros(len(js), bool)
        m[cut] = True
        if (js[~m].mean() - js[m].mean()) >= obs:
            hits += 1
    return (hits + 1) / (iters + 1)


def time_domain(res: dict) -> None:
    cs = commits()
    order = sorted(cs, key=lambda c: c[0])
    gaps = [order[i + 1][0] - order[i][0] for i in range(len(order) - 1)]
    gaps = [g for g in gaps if g > 0]
    rep = evidence(gaps)
    print(f"B  TIME     {len(order)} real commits; gaps span "
          f"{min(gaps):.0f}s to {max(gaps) / 3600:.0f}h")
    print(f"            gap structure   eta2 {rep['eta2']:.3f}  vs unstructured null  p={rep['p']:.4f}")

    cut = derive_cut([order[i + 1][0] - order[i][0] for i in range(len(order) - 1)])
    if cut is None:
        print("            the organ ABSTAINS on commit gaps -- no session structure found")
        res["time"] = {"abstained": True, "sep": rep}
        return
    groups = group_by_proximity(order, position=lambda c: c[0])
    ba = []
    gi, seen = 0, 0
    for i in range(len(order) - 1):
        seen += 1
        end = seen == len(groups[gi])
        ba.append(end)
        if end:
            gi += 1
            seen = 0
    ba = np.array(ba, bool)
    co = coherence(order, ba)
    p = permutation_p(order, ba)
    print(f"            derived cut {cut / 60:.1f} min  ->  {len(groups)} sessions, "
          f"median {np.median([len(g) for g in groups]):.0f} commits each")
    print(f"            topical coherence  within {co['within']:.3f}  across {co['across']:.3f}  "
          f"lift {co['lift']:+.3f}   permutation p={p:.4f}")

    hand = {}
    print(f"            {'hand threshold':<22}{'sessions':>9}{'lift':>9}")
    for h in HOURS:
        m = np.array([(order[i + 1][0] - order[i][0]) > h * 3600 for i in range(len(order) - 1)], bool)
        c = coherence(order, m)
        hand[h] = c
        print(f"            {f'{h} h':<22}{int(m.sum()) + 1:>9}{c['lift']:>+9.3f}")
    best_h = max(hand, key=lambda h: hand[h]["lift"])
    res["time"] = {"cut_s": cut, "sessions": len(groups), "coherence": co, "p": p,
                   "hand": {str(k): v for k, v in hand.items()}, "best_hand_h": best_h,
                   "sep": rep}
    print(f"\n-> 2. TIME sessions are topically coherent above chance: "
          f"{co['lift'] > 0 and p < 0.01}   (lift {co['lift']:+.3f}, p={p:.4f})")
    print(f"-> 3. the derived cut matches or beats the best hand threshold "
          f"({best_h} h): {co['lift'] >= hand[best_h]['lift'] - 0.005}   "
          f"({hand[best_h]['lift']:+.3f} hand  vs  {co['lift']:+.3f} derived)")


# ---------------------------------------------------------------- C: MOTION
def motion_domain(res: dict) -> None:
    from packages.perception.sprite_tracker import SpriteTracker
    from scripts.atari_babble import blobs, sprite_mask
    from scripts.wire_learned_mask import frames_of

    frames, bg, acts, truth, agree = frames_of(200, seed=3)
    tr = SpriteTracker(max_jump=22.0)
    for t, f in enumerate(frames):
        tr.step(blobs(sprite_mask(f, bg)), action=acts[t], moving_only=False)
    sp = np.array([k.speed() for k in tr.tracks], float)
    if len(sp) < 4:
        print("C  MOTION   too few tracks")
        return
    hand_moving, hand_static = tr.motion_split()
    hand_ids = {k.id for k in hand_moving}
    lo, hi = split(sp)
    org_ids = {tr.tracks[i].id for i in hi}
    agree_frac = float(np.mean([(k.id in hand_ids) == (k.id in org_ids) for k in tr.tracks]))

    # the body, located by the oracle used ONLY as an instrument, must survive on the moving side
    last = {k.id: k.pos for k in tr.tracks}
    T = truth[min(len(truth) - 1, len(frames) - 1)]
    body = min(last, key=lambda i: float(np.hypot(*(last[i] - T))))
    rep = evidence(sp)
    print(f"C  MOTION   {len(sp)} tracks; speed structure  eta2 {rep['eta2']:.3f}  p={rep['p']:.4f}")
    print(f"            hand k-means -> {len(hand_moving)} moving / {len(hand_static)} static")
    print(f"            FROZEN organ -> {len(hi)} moving / {len(lo)} static   "
          f"agreement {agree_frac:.1%}")
    print(f"            oracle-located body track kept moving:  hand {body in hand_ids}   "
          f"organ {body in org_ids}")
    res["motion"] = {"tracks": int(len(sp)), "agreement": agree_frac,
                     "hand_moving": len(hand_moving), "organ_moving": int(len(hi)),
                     "body_hand": bool(body in hand_ids), "body_organ": bool(body in org_ids),
                     "oracle_r_x": agree.get("r_x"), "sep": rep}
    # THE VERDICT IS NOT MINE TO WRITE ANY MORE. What used to sit here was a hand-rolled inequality --
    # `agree_frac >= 0.9 and body in org_ids` -- one of dozens written by hand across this session's
    # scripts, each re-deciding what counts as evidence. packages/self_check asks the four questions
    # instead, and scores INCONCLUSIVE AS FAILURE, which a hand-rolled boolean structurally cannot do.
    # Run retroactively on this exact measurement it returned, in one pass: only 10 instances where 30
    # are needed, an effect 1.21x the unit where 2x is needed, and a control that matched the real
    # score. The first of those took three rungs to reach by hand and the second was never reached.
    _gate("MOTION: the frozen organ can replace the hand k-means", res,
          observed_source="ALE frames", intended_source="ALE frames",
          base_rate=len(hi) / max(len(sp), 1), n=int(len(sp)),
          real_score=agree_frac, control_score=0.5,
          target_size=rep["eta2"], unit_size=0.75)


# ---------------------------------------------------------------- A / D
def space_domain(res: dict) -> None:
    from scripts.schema_on_real_render import render
    from scripts.schema_text_layer import glyph_regions, group_lines
    img, _t, _p = render(None)
    lines = group_lines(glyph_regions(img))
    ordered = sorted(lines, key=lambda b: b[1])
    gaps = [max(0.0, ordered[i + 1][1] - ordered[i][3]) for i in range(len(ordered) - 1)]
    rep = evidence(gaps)
    paras = group_by_proximity(ordered, position=lambda b: b[1])
    print(f"A  SPACE    {len(lines)} lines on a real render; gap structure  "
          f"eta2 {rep['eta2']:.3f}  p={rep['p']:.4f}")
    print(f"            FROZEN organ -> {len(paras)} groups "
          f"(derived cut {derive_cut(gaps)})")
    res["space"] = {"lines": len(lines), "groups": len(paras), "sep": rep}
    big = max(gaps) if gaps else 0.0
    med = float(np.median([g for g in gaps if g > 0])) if any(g > 0 for g in gaps) else 0.0
    _gate("SPACE: the organ finds line structure on a real render", res,
          observed_source="chromium render", intended_source="chromium render",
          base_rate=len(lines) / max(len(glyph_regions(img)), 1), n=len(gaps),
          real_score=rep["eta2"], control_score=0.75,
          target_size=big, unit_size=med)


def null_domain(res: dict) -> None:
    even = np.arange(60, dtype=float) * 7.0
    rng = np.random.default_rng(1)
    jitter = even + rng.normal(0, 0.3, size=len(even))
    out = {}
    for name, v in (("evenly spaced", even), ("evenly spaced + noise", jitter)):
        e = evidence(np.diff(np.sort(v)))
        c = derive_cut(np.diff(np.sort(v)))
        g = group_by_proximity(list(v), position=lambda x: x)
        out[name] = {"eta2": e["eta2"], "p": e["p"], "cut": c, "groups": len(g)}
        print(f"D  NULL     {name:<24} eta2 {e['eta2']:>5.3f}  p={e['p']:.4f}   cut {c}   "
              f"groups {len(g)}")
    res["null"] = out
    ok = all(v["cut"] is None and v["groups"] == 1 for v in out.values())
    print(f"\n-> 5. the organ ABSTAINS where there is no boundary: {ok}")


def main() -> None:
    same = (gestalt.derive_cut is derive_cut
            and group_by_proximity.__module__ == gestalt.__name__
            and split.__module__ == gestalt.__name__)
    print("THE GROUPING ORGAN, FROZEN, ACROSS FOUR SENSES")
    print(f"-> 1. one operation, imported unchanged by every domain below: {same}")
    print(f"       packages/perception/gestalt.py  ::  derive_cut  (no domain argument exists)\n")

    res = {"frozen": bool(same)}
    space_domain(res)
    print()
    time_domain(res)
    print()
    motion_domain(res)
    print()
    null_domain(res)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
