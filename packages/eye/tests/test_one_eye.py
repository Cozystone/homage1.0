# -*- coding: utf-8 -*-
"""The two things that make this ONE eye rather than several, checked rather than asserted in prose.

These run without a screen, a camera or a network: sources are replaced by a fake that produces
frames from arrays. That is deliberate — a test that needed a desktop would be skipped on every
machine that matters and the property would go unchecked.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.eye import Frame, as_rgb, bgr_to_rgb, now_utc
from packages.eye.eye import Eye
from packages.eye.sources import Source


class _FakeSource(Source):
    """A door onto arrays. Stands in for screen / window / video / camera alike, which is the point:
    if the cortex can tell this from a real one, the eye is not source-blind."""

    def __init__(self, frames, name="fake"):
        self.frames, self.name, self.i = frames, name, 0

    def available(self):
        return True, ""

    def grab(self):
        arr = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return Frame(rgb=as_rgb(arr), t_utc=now_utc(), t_mono=float(self.i) * 0.2, source=self.name)


def _still(v=120, n=8):
    return [np.full((64, 64, 3), v, np.uint8) for _ in range(n)]


# ---------------------------------------------------------------- the gate's contract

def test_gate_contract_key_is_run_not_attend():
    """Pins the key this eye reads off `attention.decide`.

    The first version of eye.py read `decision.get("attend", True)`. The gate returns `run`, so the
    lookup always missed, always defaulted to True, and the eye attended to 18 of 18 frames of a
    STATIC screen while reporting a working gate. Nothing raised and nothing failed; the only signal
    was the number looking wrong. This test is the signal instead."""
    from packages.perception import attention
    st = attention.new_state()
    sig = attention.frame_signature(np.full((64, 64, 3), 100, np.uint8))
    d = attention.decide(st, sig, now=1.0)
    assert isinstance(d, dict)
    assert "run" in d, "attention.decide must return `run`; eye.Eye._attention reads it"
    assert "energy" in d and "next_interval_s" in d


def test_still_scene_is_mostly_not_attended():
    """A gate that lets everything through is not a gate. On an unchanging scene most looks must be
    skipped — that is what makes an always-open eye affordable."""
    eye = Eye(source=_FakeSource(_still(n=12)))
    looks = [eye.look() for _ in range(12)]
    assert looks[0].attend, "the first look must be taken — cold start has nothing to compare to"
    assert sum(l.attend for l in looks) <= 4, f"gate passed too much: {[l.reason for l in looks]}"
    assert eye.stats()["attend_rate"] <= 0.4


def test_gate_off_attends_everything():
    eye = Eye(source=_FakeSource(_still(n=5)), gate=False)
    assert all(eye.look().attend for _ in range(5))


# ---------------------------------------------------------------- source blindness

def test_frames_from_different_doors_are_indistinguishable():
    """`source` is provenance, never a switch. Two doors, same pixels -> everything a perception
    organ can see must be identical. The moment an organ could branch on the door, the single eye
    has silently become two, and nothing learned through one would transfer to the other."""
    arr = np.random.default_rng(7).integers(0, 255, (48, 48, 3), dtype=np.uint8)
    a = Eye(source=_FakeSource([arr], name="screen")).look().frame
    b = Eye(source=_FakeSource([arr], name="camera")).look().frame

    assert type(a) is type(b)
    assert a.rgb.shape == b.rgb.shape and a.rgb.dtype == b.rgb.dtype
    assert np.array_equal(a.rgb, b.rgb)
    assert a.size == b.size

    from packages.perception import attention
    assert np.allclose(attention.frame_signature(a.rgb), attention.frame_signature(b.rgb))


# ---------------------------------------------------------------- the pixel contract

@pytest.mark.parametrize("shape,expect", [((8, 8), (8, 8, 3)), ((8, 8, 3), (8, 8, 3)), ((8, 8, 4), (8, 8, 3))])
def test_as_rgb_normalises_grey_rgb_and_alpha(shape, expect):
    """Greyscale, RGB and RGBA all become HxWx3 uint8 — handled once, not in every source. A source
    that got this wrong would emit valid-looking, colour-swapped frames and never raise."""
    out = as_rgb(np.zeros(shape, np.uint8))
    assert out.shape == expect and out.dtype == np.uint8


def test_bgr_conversion_actually_swaps():
    bgr = np.zeros((2, 2, 3), np.uint8)
    bgr[..., 0] = 255                                    # blue in BGR
    assert bgr_to_rgb(bgr)[0, 0, 2] == 255               # must land in the RED... no: the BLUE slot
    assert bgr_to_rgb(bgr)[0, 0, 0] == 0


def test_float_input_is_clipped_not_wrapped():
    """Casting a float array straight to uint8 wraps: 300.0 becomes 44. Clipping is the only safe
    read of an out-of-range pixel."""
    out = as_rgb(np.array([[[300.0, -5.0, 128.0]]]))
    assert out[0, 0, 0] == 255 and out[0, 0, 1] == 0 and out[0, 0, 2] == 128


def test_time_is_absolute_utc_not_a_frame_counter():
    """Frames land on the one UTC timeline beside hormones and graph edits. A frame that knew only
    its index could not be placed next to any of them."""
    f = Eye(source=_FakeSource(_still(n=1))).look().frame
    assert f.t_utc.endswith("+00:00") and "T" in f.t_utc
    assert isinstance(f.t_mono, float)
