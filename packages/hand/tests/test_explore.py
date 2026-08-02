# -*- coding: utf-8 -*-
"""Does curiosity-with-a-body actually seek NEW PLACES, or just moving pixels?

Every test here drives a fake world, because the interesting failures are about what the reward
signal rewards and those are visible without a game running. The one that matters most is the
noisy TV: a novelty drive that pays for change rather than for unfamiliarity will sit in front of
flickering pixels forever, and it will look like it is working the whole time.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.hand import Move, Territory, explore
from packages.hand.explore import NEW_PLACE


def _view(seed: int, h: int = 120, w: int = 160) -> np.ndarray:
    """A smooth, distinctive scene. Smooth because that is what real frames are, and what the
    retinal code's block averaging assumes."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w), np.float32)
    for _ in range(5):
        cy, cx = rng.uniform(0, h), rng.uniform(0, w)
        img += rng.uniform(40, 200) * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / rng.uniform(300, 3000))
    img = np.clip(img, 0, 255)
    return np.repeat(img[:, :, None], 3, axis=2).astype(np.uint8)


class _FakeEye:
    def __init__(self, world):
        self.world = world

    def look(self):
        class _L:
            pass
        l = _L()
        l.frame = type("F", (), {"rgb": self.world.frame()})()
        return l


class _FakeHand:
    """Accepts every move; the world decides what a move does."""

    def __init__(self, world):
        self.world = world
        self.sent = []

    def _foreground_ok(self):
        return True, "fake"

    def do(self, mv):
        key = mv.label or "+".join(mv.keys)
        self.sent.append(key)
        self.world.apply(key)
        return {"ok": True}

    def release_all(self):
        return None


class _Corridor:
    """A line of rooms. `go` advances, `turn` does not — so only `go` finds anywhere new."""

    def __init__(self):
        self.at = 0

    def apply(self, key):
        if key == "go":
            self.at += 1

    def frame(self):
        return _view(self.at)


class _NoisyTV:
    """One room with traffic: a fixed scene crossed by large blobs on a loop. Every move is useless;
    the picture never stops changing.

    THE FIRST VERSION OF THIS FIXTURE WAS WRONG, and the counterfactual test below is what caught it.
    It churned a patch of WHITE NOISE, and the counterfactual — "frame-to-frame change would have
    been fooled by this" — failed, reading 0.005 where it needed 0.06. The reason is that the retinal
    code block-AVERAGES, and any patch of white noise averages to the same mid-grey every frame. So
    the pixels were screaming and the code could not hear them.

    Which means the noisy-TV test was passing for a reason I had mis-attributed: block averaging was
    killing the distractor before the novelty rule ever saw it, not the novelty rule beating it.

    The real trap is motion at a scale the code CAN see — traffic, a rotating sign, waves — so that
    is what this is now. Large bright blobs sweep across on a period of 6, which keeps frame-to-frame
    change high indefinitely and gives distance-to-memory something real to beat."""

    PERIOD = 6

    def __init__(self):
        self.t = 0

    def apply(self, key):
        self.t += 1

    def frame(self):
        self.t += 1
        base = _view(7).astype(np.float32)
        h, w = base.shape[:2]
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        phase = (self.t % self.PERIOD) / self.PERIOD
        for lane, cy in enumerate((35.0, 85.0)):
            cx = ((phase + 0.5 * lane) % 1.0) * w
            blob = 210.0 * np.exp(-((y - cy) ** 2 / 260.0 + (x - cx) ** 2 / 900.0))
            base += blob[:, :, None]
        return np.clip(base, 0, 255).astype(np.uint8)


SCHEMA = {"moves": {
    "go":   {"div": 1.2, "dx": 0.1, "dy": 0.0, "mag": 1.4},     # measured to translate
    "turn": {"div": 0.0, "dx": 1.6, "dy": 0.0, "mag": 1.6},     # measured to slide only
    "dead": {"div": 0.0, "dx": 0.0, "dy": 0.0, "mag": 0.1},     # measured to do nothing
}}
MOVES = [Move(keys=("w",), label="go"), Move(keys=("a",), label="turn"),
         Move(keys=("space",), label="dead")]


def test_a_move_measured_to_do_nothing_is_never_tried():
    """The schema is knowledge, not a log. `space` did nothing when babbled, so no step is spent
    on it — and nothing in the code says the word 'jump'."""
    w = _Corridor()
    hand = _FakeHand(w)
    explore(_FakeEye(w), hand, MOVES, SCHEMA, steps=12, settle=0.0)
    assert "dead" not in hand.sent


def test_it_learns_which_move_finds_new_places():
    w = _Corridor()
    out = explore(_FakeEye(w), _FakeHand(w), MOVES, SCHEMA, steps=24, settle=0.0)
    v = out["move_value"]
    assert v["go"]["mean_novelty"] > v["turn"]["mean_novelty"], v
    assert w.at >= 8, "should have travelled down the corridor"


def test_the_noisy_tv_does_not_hold_it():
    """THE ONE THAT MATTERS. In a room that churns but never changes, measured novelty must fall to
    the floor — otherwise the drive would happily stand here forever."""
    w = _NoisyTV()
    out = explore(_FakeEye(w), _FakeHand(w), MOVES, SCHEMA, steps=20, settle=0.0)
    # It is allowed to find the first pass through the loop interesting — those really are views it
    # had not seen. What it must not do is keep finding the SAME loop interesting on every pass.
    later = [p["novelty"] for p in out["path"][2 * _NoisyTV.PERIOD:]]
    assert max(later) < NEW_PLACE, f"still paying itself for traffic: {later}"
    assert out["places_seen"] <= _NoisyTV.PERIOD + 2, out["places_seen"]


def test_frame_to_frame_change_would_have_been_fooled():
    """The counterfactual, measured rather than asserted: the SAME noisy room scored the way a naive
    novelty drive would score it — change between consecutive frames — stays high indefinitely.

    Without this, 'we avoided the noisy TV' is a claim about a bug that was never demonstrated."""
    from packages.perception.attention import change_energy, frame_signature
    w = _NoisyTV()
    prev, changes = frame_signature(w.frame()), []
    for _ in range(20):
        cur = frame_signature(w.frame())
        changes.append(change_energy(prev, cur))
        prev = cur
    # Frame-to-frame change never habituates: the twentieth pass of the same traffic scores like the
    # first. Distance-to-memory, on the same room, fell below the floor after one loop.
    assert min(changes) > NEW_PLACE, f"the trap must actually be a trap: {changes}"


class _DeadEnd:
    """A corridor with a wall across it. Travelling does nothing while facing the wall; turning
    changes which way `go` points, and only one heading leads anywhere.

    This is the world that catches an absorbing stuck rule: any agent that responds to being stuck by
    turning FOREVER stays here at one place, and the live City Sample run did exactly that."""

    def __init__(self):
        self.at, self.heading = 0, 0

    def apply(self, key):
        if key == "turn":
            self.heading = (self.heading + 1) % 3
        elif key == "go" and self.heading == 2:      # only one way out
            self.at += 1

    def frame(self):
        return _view(self.at * 7 + self.heading)


def test_it_gets_out_of_a_dead_end():
    """Being stuck must not be permanent. It has to turn AND then try travelling again — the first
    version locked itself into look-around moves the moment it stalled, so it could never discover
    that turning had made travelling work."""
    w = _DeadEnd()
    hand = _FakeHand(w)
    out = explore(_FakeEye(w), hand, MOVES, SCHEMA, steps=60, settle=0.0)
    assert w.at >= 3, f"never escaped the dead end (at={w.at}, sent={hand.sent[:20]})"
    assert hand.sent.count("go") >= 5, f"stopped trying to travel: {hand.sent}"
    assert out["places_seen"] > 2, out["places_seen"]


def test_it_stops_when_the_window_stops_being_in_front():
    w = _Corridor()
    hand = _FakeHand(w)
    calls = {"n": 0}

    def _fg():
        calls["n"] += 1
        return (True, "fake") if calls["n"] < 5 else (False, "foreground is 'Notepad'")

    hand._foreground_ok = _fg
    out = explore(_FakeEye(w), hand, MOVES, SCHEMA, steps=30, settle=0.0)
    assert out["ok"] is False and out["stopped"] == "lost_foreground"
    assert out["steps_done"] < 30


def test_it_refuses_a_body_it_has_not_learned():
    w = _Corridor()
    out = explore(_FakeEye(w), _FakeHand(w), MOVES, {"moves": {}}, steps=5, settle=0.0)
    assert out["ok"] is False and "babble first" in out["refused"]


def test_territory_treats_a_revisit_as_familiar():
    t = Territory()
    from packages.perception.attention import frame_signature
    a, b = frame_signature(_view(1)), frame_signature(_view(2))
    t.remember(a)
    assert t.novelty(b) > NEW_PLACE
    t.remember(b)
    assert t.novelty(a) < 1e-6, "coming back to where it started is not a discovery"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
