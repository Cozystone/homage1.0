# -*- coding: utf-8 -*-
"""Curiosity with a body: ATANOR decides WHERE to go, using what moving taught it.

`babble.py` answers "what does this key do". This answers "so where do I go", and it is the rung
that turns a body from something that can be driven into something that drives itself. Nothing here
is given a destination, a map, or a route. It has three things: the moves babbling found to work, an
eye, and a preference for seeing what it has not seen.

WHAT COUNTS AS REWARD, AND WHY IT IS THIS AND NOT FRAME-TO-FRAME CHANGE. Novelty is the distance
from the view it arrived at to the NEAREST view already in memory — not how much the image changed
while getting there. Those two come apart in a way that decides whether this organ works at all.

    An agent paid for frame-to-frame change parks in front of the most unpredictable pixels it can
    find — traffic, flickering signage, water — and collects reward forever without going anywhere.
    That is the noisy-TV failure, and it is the standard way a novelty drive dies.

Distance-to-nearest-in-memory does not pay for that. A busy intersection is enormously changeable
and, after the first visit, entirely familiar: its retinal code sits right next to one already
stored, so novelty reads near zero no matter how much is moving inside the frame. The signal says
"somewhere new", which is what curiosity is actually for, rather than "something moved".

HOW A MOVE IS CHOSEN. Each move keeps a running mean of the novelty it has delivered, plus an
optimism bonus that decays with how often it has been tried, so an untried move outranks a known
mediocre one and stops outranking it once tried. This is the ordinary bandit form, and the point is
that the values are LEARNED FROM CONSEQUENCE — the same commitment as the body schema. No move is
seeded as "the good one".

WHAT IT KNOWS ABOUT ITS OWN MOVES, IT MEASURED. When novelty collapses — a wall — it needs to change
the view without translating, and it finds those moves by reading the babbling record for effects
that slid the view without expanding it. That is a description of measured optical flow, not
knowledge that some key is 'turn'. Rebind the game and the same read finds the new keys.

WHAT IT REFUSES TO DO. It never takes focus. `WindowEffector.focus()` and `engage()` are acts on the
operator's desktop and stay operator-initiated; this loop only moves a body it has already been
placed in, and stops the moment the window it was given stops being in front. An autonomous organ
that could grab the screen would be a different and much worse thing than one that can walk around
inside a window it was handed.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from packages.perception.attention import change_energy, frame_signature

from .babble import flow_signature

LEDGER = Path(r"D:\citysample_drive\exploration.jsonl")

# How different a view has to be from everything already seen to count as somewhere new.
#
# MEASURED, on the 3,144 City Sample frames already on disk, by `scripts/measure_place_threshold.py`
# -- and the first version of this constant was 0.06 with a comment claiming consecutive frames read
# "0.01-0.03". They read 0.0002. I had asserted the scale instead of measuring it, was wrong by a
# factor of fifty, and set a floor so high that the first live run threw away every view it found:
# 70 steps, novelty readings around 0.031, `places_seen` 1, `frames_kept` 0.
#
#     same spot, adjacent frames      median 0.0002    p90 0.0069
#     elsewhere in the city (+600)    median 0.0668-0.1313    p10 0.0606
#
# Those two bands do not overlap, so the floor is not a tuned parameter -- almost any value between
# them separates them. 0.02 is ~3x the same-spot p90 and well under the different-place p10, and the
# live readings it was getting wrong sit comfortably above it.
NEW_PLACE = 0.02


@dataclass
class Territory:
    """Where it has been, as retinal codes. Not a map — it has no coordinates and cannot have any."""

    codes: list[np.ndarray] = field(default_factory=list)
    max_codes: int = 4000

    def novelty(self, code: np.ndarray) -> float:
        """Distance to the nearest thing already seen. 1.0 when nothing has been seen yet."""
        if not self.codes:
            return 1.0
        return min(change_energy(code, c) for c in self.codes)

    def remember(self, code: np.ndarray) -> None:
        self.codes.append(code)
        if len(self.codes) > self.max_codes:
            # Drop the OLDEST, not a random one: a place revisited late still reads familiar because
            # it was re-remembered on the revisit, while somewhere seen once long ago is genuinely
            # allowed to become interesting again. Forgetting on a long horizon is not a defect here.
            self.codes.pop(0)


@dataclass
class MoveValue:
    """What a move has been worth, as measured."""

    tries: int = 0
    total: float = 0.0

    @property
    def mean(self) -> float:
        return self.total / self.tries if self.tries else 0.0

    def score(self, step: int) -> float:
        """Mean novelty plus optimism for the untried. The bonus is the usual sqrt(log t / n) shape:
        large while a move is unknown, negligible once it has been sampled enough to have a mean
        worth trusting."""
        if not self.tries:
            return 1e9                       # everything gets tried once before anything gets judged
        return self.mean + 0.5 * float(np.sqrt(np.log(max(step, 2)) / self.tries))


def _moves_from_schema(schema: dict[str, Any], all_moves: list) -> tuple[list, list]:
    """Split the babbled moves into (travel, look-around) by what they were MEASURED to do.

    travel      moved the body through the world  -> expansion or contraction (`div`)
    look_around changed the view without translating -> slide only

    A move babbling found to do nothing is dropped from both. That is the schema being used as
    knowledge rather than as a log: `space` did nothing measurable in this body, so curiosity never
    wastes a step on it, and no line here says the word 'jump'."""
    found = schema.get("moves", {})
    travel, look = [], []
    for mv in all_moves:
        key = mv.label or "+".join(mv.keys)
        v = found.get(key)
        if not v:
            continue
        div, dx, dy, mag = abs(v.get("div", 0)), abs(v.get("dx", 0)), abs(v.get("dy", 0)), v.get("mag", 0)
        if mag < 0.5:
            continue                          # measured to do nothing; not a candidate
        if div > 0.4:
            travel.append(mv)
        elif dx > 0.4 or dy > 0.4:
            look.append(mv)
    return travel, look


def explore(eye, hand, moves, schema: dict[str, Any], *, steps: int = 40,
            settle: float = 0.35, keep: Path | None = None) -> dict[str, Any]:
    """Go somewhere. Returns what was seen and what each move turned out to be worth.

    `schema` is the output of `babble()`. Passing it in rather than re-deriving it is the point: the
    body had to be learned before it could be used, and if the schema is empty this refuses instead
    of flailing, because a body it does not understand is not one it should be driving."""
    travel, look = _moves_from_schema(schema, moves)
    if not travel and not look:
        return {"ok": False, "refused": "no usable moves in the body schema — babble first"}

    candidates = travel + look
    values: dict[str, MoveValue] = {(m.label or "+".join(m.keys)): MoveValue() for m in candidates}
    territory = Territory()
    kept, stuck_runs, path = 0, 0, []

    if keep:
        keep.mkdir(parents=True, exist_ok=True)

    code = frame_signature(eye.look().frame.rgb)
    territory.remember(code)

    for step in range(steps):
        ok, why = hand._foreground_ok()
        if not ok:
            # The operator took the screen back, or something popped up. Stop — do not keep sending
            # keystrokes at whatever is there now.
            return {"ok": False, "stopped": "lost_foreground", "detail": why,
                    "steps_done": step, **_report(values, territory, kept, path)}

        # Stuck: several steps in a row that found nothing new -- a wall, a corner, a dead end. The
        # response is to change the view without translating, using the moves babbling measured to
        # slide without expanding.
        #
        # IT ALTERNATES, and that is a repair rather than a flourish. The first version switched the
        # pool to look-around moves and left it there, because `stuck_runs` only reset on finding
        # somewhere new -- which cannot happen while the moves that travel are locked out. So the
        # response to being stuck made being stuck permanent. The live run showed it exactly: `a` and
        # `d` tried 11-12 times each, `w` once, `lshift+w` never, for 66 of 70 steps. Turning and
        # then trying to move again is what getting out of a corner actually looks like.
        pool = look if (stuck_runs >= 3 and stuck_runs % 2 == 1 and look) else candidates
        mv = max(pool, key=lambda m: values[m.label or "+".join(m.keys)].score(step + 1))
        key = mv.label or "+".join(mv.keys)

        before = eye.look().frame.rgb.copy()
        res = hand.do(mv)
        if not res.get("ok"):
            values[key].tries += 1            # a refused move is worth nothing, and that IS its value
            continue
        time.sleep(settle)
        after = eye.look().frame.rgb.copy()

        code = frame_signature(after)
        nov = territory.novelty(code)
        values[key].tries += 1
        values[key].total += nov
        flow = flow_signature(before, after)

        if nov >= NEW_PLACE:
            territory.remember(code)
            stuck_runs = 0
            if keep is not None:
                # Somewhere new is worth keeping. This is where curiosity feeds the depth learner:
                # the corpus grows toward places the body has NOT already photographed, instead of
                # accumulating a thousand frames of one street.
                np.savez_compressed(keep / f"{kept:05d}.npz", rgb=after,
                                    t_mono=np.float64(time.perf_counter()), novelty=np.float32(nov))
                kept += 1
        else:
            stuck_runs += 1

        path.append({"step": step, "move": key, "novelty": round(float(nov), 4),
                     "flow": flow, "stuck_runs": stuck_runs})

    hand.release_all()
    out = {"ok": True, "steps_done": steps, **_report(values, territory, kept, path)}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **out}, ensure_ascii=False) + "\n")
    return out


def _report(values: dict[str, MoveValue], territory: Territory, kept: int,
            path: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "places_seen": len(territory.codes),
        "frames_kept": kept,
        "move_value": {k: {"tries": v.tries, "mean_novelty": round(v.mean, 4)}
                       for k, v in sorted(values.items(), key=lambda kv: -kv[1].mean)},
        "path": path[-60:],
    }
