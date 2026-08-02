# -*- coding: utf-8 -*-
"""The night shift for the senses — the three things that were sample-starved by daylight.

    python scripts/overnight_perception.py --hours 9

WHAT IS HERE AND WHY THESE THREE. Everything built for the ear and the mouth today was measured on a
handful of examples because each run costs minutes and a conversation cannot wait. All three of the
questions left open need MANY samples, generate their own ground truth, and run on a CPU with nothing
downloaded:

    A  OVER-SEGMENTATION   420 syllables were cut into 598 pieces, and that 42% is where the word
                           boundary precision goes (0.411). The cut rule has one real parameter --
                           how close two troughs may be -- and the right value is measurable against
                           streams whose boundaries we generated. Searched over many streams so the
                           answer is not fitted to one.
    B  WHERE IDENTITY      Voice identity was measured on six people. Six is not a room. This grows
       BREAKS              the population until identification fails, which locates the limit
                           instead of asserting one.
    C  A REPERTOIRE        `imitate` recovers one posture in about a minute. A night of them is an
                           inventory, and the error distribution over hundreds of targets says which
                           regions of the vowel space the mouth cannot reach -- something four
                           vowels cannot show.

WHAT IS NOT HERE, and it is the important half. Real video and real speech are not in this: there is
no sound-bearing video on this machine, and downloading AudioSet or LibriSpeech unattended is not a
decision to take while the owner is asleep. Everything below is SYNTHETIC, which makes the oracle
free and also bounds what any result can claim -- a synthetic throat scales uniformly and a real one
does not.

Failures are written, not swallowed. A night of silent exceptions looks exactly like a night of quiet
progress.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LOG = REPO / "data" / "perception" / "overnight_perception.jsonl"

VOWELS = {"a": (700, 1220, 2600), "i": (300, 2300, 3000), "u": (350, 800, 2600),
          "e": (500, 1750, 2500), "o": (450, 900, 2400), "ae": (660, 1720, 2410),
          "ao": (590, 880, 2540), "ei": (400, 2000, 2700)}
SYL = {"tu": (350, 800, 2600, 1900), "pi": (300, 2300, 3000, 700), "ro": (450, 900, 2400, 1500),
       "go": (450, 950, 2350, 2400), "la": (700, 1220, 2600, 1300), "bu": (350, 780, 2500, 700),
       "da": (700, 1250, 2600, 1800), "pa": (720, 1200, 2550, 700), "ti": (300, 2250, 2950, 1900),
       "do": (460, 880, 2380, 1800), "ku": (340, 820, 2620, 2400), "bi": (310, 2280, 3050, 700)}
WORDS = [("tu", "pi", "ro"), ("go", "la", "bu"), ("da", "pa", "ti"), ("do", "ku", "bi")]


def _write(rec: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- A: over-segmentation

def _stream(n, seed):
    rng = np.random.default_rng(seed)
    seq, bounds, prev = [], [], None
    for _ in range(n):
        pool = [w for w in WORDS if w != prev]
        w = pool[int(rng.integers(len(pool)))]
        prev = w
        seq.extend(w)
        bounds.append(len(seq))
    return seq, sorted(set(bounds[:-1]))


def _speak(seq):
    from packages.perception.mouth import Gesture, glide, say
    out = []
    for s in seq:
        f1, f2, f3, locus = SYL[s]
        on = Gesture(f0=120, formants=(300, locus, 2500), seconds=0.015, burst=0.5)
        body = Gesture(f0=120, formants=(f1, f2, f3), seconds=0.125)
        out.extend([on] + glide(on, body, 0.06) + [body])
    return say(out, seed=1)


def phase_a(seed: int) -> dict:
    """How close may two cuts be? Measured against boundaries we made, on a fresh stream."""
    from packages.perception.ear import cochleagram
    from packages.perception.segmentation import discover
    seq, truth = _stream(60, seed)
    cg = cochleagram(_speak(seq))
    fps = int(0.20 * 16000 / 160)
    true_frames = {int(t * fps) for t in truth}
    tol = max(3, fps // 2)
    rows = []
    for frac in (0.4, 0.6, 0.8, 1.0, 1.2):
        d = discover(cg, expect_units=12, syllable_frames=int(fps * frac))
        hit = sum(1 for f in d["boundary_frames"] if any(abs(f - t) <= tol for t in true_frames))
        prec = hit / max(1, len(d["boundary_frames"]))
        rec = hit / max(1, len(true_frames))
        rows.append({"gap_fraction": frac, "pieces": len(d["spans"]), "syllables": len(seq),
                     "over_segmentation": round(len(d["spans"]) / max(1, len(seq)), 3),
                     "units_found": d.get("distinct_found"), "precision": round(prec, 3),
                     "recall": round(rec, 3),
                     "f1": round(2 * prec * rec / max(1e-9, prec + rec), 3)})
    return {"phase": "A_over_segmentation", "seed": seed, "rows": rows}


# ---------------------------------------------------------------- B: where identity breaks

def phase_b(seed: int, n_people: int) -> dict:
    """Grow the room until it can no longer tell people apart."""
    from packages.perception import who as W
    from packages.perception.ear import envelope
    from packages.perception.mouth import Gesture, say
    tmp = REPO / "data" / "perception" / ("_night_ids_%d.jsonl" % seed)
    old, W.LEDGER = W.LEDGER, tmp
    try:
        if tmp.exists():
            tmp.unlink()
        rng = np.random.default_rng(seed)
        people = {"p%d" % i: (float(rng.uniform(0.85, 1.35)), float(rng.uniform(85, 275)))
                  for i in range(n_people)}
        vs = list(VOWELS)
        meet, test = vs[:4], vs[4:]

        def utter(p, v):
            sc, f0 = people[p]
            return envelope(say(Gesture(f0=f0, formants=tuple(f * sc for f in VOWELS[v]),
                                        seconds=0.28), seed=1))
        for p in people:
            W.bind("voice", W.voice_print([utter(p, v) for v in meet]), identity=p)
        said = right = 0
        for p in people:
            r = W.recall_from("voice", [utter(p, v) for v in test])
            said += int(r is not None)
            right += int(r is not None and r["identity"] == p)
        return {"phase": "B_identity_scale", "seed": seed, "people": n_people,
                "spoke_up": said, "correct": right, "chance": round(1 / n_people, 4),
                "precision_when_it_spoke": round(right / max(1, said), 3)}
    finally:
        W.LEDGER = old
        try:
            tmp.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------- C: a repertoire

def phase_c(seed: int, n: int = 24) -> dict:
    """Imitate targets scattered through the vowel space; log where the mouth cannot reach."""
    from packages.perception.mouth import Gesture, imitate, say
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        F = (float(rng.uniform(260, 900)), float(rng.uniform(700, 2600)),
             float(rng.uniform(2100, 3400)))
        F = (F[0], max(F[1], F[0] + 120), max(F[2], F[1] + 200))
        f0 = float(rng.uniform(85, 240))
        got = imitate(say(Gesture(f0=f0, formants=F, seconds=0.28), seed=1),
                      rounds=110, seed=int(rng.integers(10_000)))["gesture"]
        rows.append({"f0": round(f0), "target": [round(x) for x in F],
                     "got": [round(x) for x in got.formants],
                     "err": [round(abs(a - b) / b, 3) for a, b in zip(got.formants, F)]})
    E = np.array([r["err"] for r in rows])
    return {"phase": "C_repertoire", "seed": seed, "n": n, "rows": rows,
            "mean_err": [round(float(x), 3) for x in E.mean(0)],
            "within_25pct_all_three": int((E < 0.25).all(1).sum())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=0.0)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = time.time()
    _write({"event": "night_begins", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid()})
    seed = 0
    while True:
        if a.hours and (time.time() - started) > a.hours * 3600:
            break
        seed += 1
        for fn, args in ((phase_a, (seed,)),
                         (phase_b, (seed, 4 + (seed % 5) * 6)),
                         (phase_c, (seed,))):
            t0 = time.time()
            try:
                rec = fn(*args)
                rec["seconds"] = round(time.time() - t0, 1)
                rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                _write(rec)
                print("%s round %d in %.0fs" % (rec["phase"], seed, time.time() - t0), flush=True)
            except Exception as exc:
                _write({"phase": fn.__name__, "seed": seed, "error": "%s: %s" % (type(exc).__name__, exc),
                        "where": traceback.format_exc()[-700:],
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
                print("%s FAILED: %s" % (fn.__name__, type(exc).__name__), flush=True)
    _write({"event": "night_ends", "rounds": seed,
            "hours": round((time.time() - started) / 3600, 2)})


if __name__ == "__main__":
    main()
