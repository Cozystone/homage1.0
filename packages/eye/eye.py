# -*- coding: utf-8 -*-
"""The eye: a source, the existing attention gate, and nothing else.

WHAT THIS DELIBERATELY DOES NOT DO. It does not recognise objects, read faces, build a scene graph
or predict latents — `packages.perception` already does all four, and every one of them already
takes the HxWx3 uint8 array this produces. Adding a second copy of any of them here would create the
thing this project has caught itself building nine times: an organ that duplicates a working one and
then diverges from it.

WHAT IT DOES DO is the one thing that was missing — turn a source into frames, and decide which
frames are worth spending the cortex on. The second half is not new either: `perception.attention`
already implements a predictive gate whose whole point is to compute only on CHANGE. This wires it
in, so the eye is cheap when the world is still and expensive only when something moves.

The gate is what makes an always-open eye affordable. A 5 Hz screen grab that ran full recognition
on every frame would burn a core to watch a static page; the same grab with the gate in front spends
almost nothing until the page changes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np

from .frame import Frame
from .sources import Source


@dataclass
class Look:
    """One frame plus what the attention gate decided about it. `attend=False` is a real outcome,
    not a failure: a still world SHOULD produce mostly unattended looks.

    The field names mirror `perception.attention.decide`'s actual keys (`run`, `energy`,
    `next_interval_s`) rather than names invented here. The first version of this file invented
    `attend`/`change`, which the gate never returns — so `.get("attend", True)` fell through to its
    default and the eye attended to 18 frames out of 18 of a STATIC screen while reporting that a
    gate was running. Nothing raised. The only thing that caught it was the number being obviously
    wrong for a still desktop, which is a thin defence, so the names are pinned to the source."""

    frame: Frame
    attend: bool                        # gate's `run`
    energy: float                       # gate's `energy` — pixel change since the last committed look
    reason: str = ""
    next_interval_s: float | None = None   # gate's own suggested cadence
    latent_surprise: float | None = None


@dataclass
class Eye:
    """An open eye on one source."""

    source: Source
    gate: bool = True                       # run the predictive attention gate
    _state: Any = None
    _prev_thumb: Any = None
    _looks: int = 0
    _attended: int = 0
    _quiet: int = 0
    _opened_mono: float = field(default_factory=time.monotonic)

    # -------------------------------------------------------------- capability, asked not assumed
    def available(self) -> tuple[bool, str]:
        return self.source.available()

    # -------------------------------------------------------------- looking
    def _attention(self, frame: Frame, latent_surprise: float | None) -> Look:
        if not self.gate:
            return Look(frame=frame, attend=True, energy=1.0, reason="gate off")
        try:
            from packages.perception import attention
        except Exception as exc:
            # No gate available is NOT a licence to attend to everything silently — say so, and
            # attend, because dropping frames on a broken gate would lose real perception.
            return Look(frame=frame, attend=True, energy=1.0,
                        reason=f"gate unavailable: {type(exc).__name__}")
        try:
            sig = attention.frame_signature(frame.rgb)
            if self._state is None:
                self._state = attention.new_state()
            d = attention.decide(self._state, sig, now=frame.t_mono,
                                 latent_surprise=latent_surprise)
            run = bool(d["run"])                 # KeyError here is correct: a gate that stopped
            if run:                              # returning `run` must break loudly, not default
                attention.commit(self._state, sig, now=frame.t_mono)
            return Look(frame=frame, attend=run, energy=float(d.get("energy", 0.0)),
                        reason=str(d.get("reason", "")),
                        next_interval_s=d.get("next_interval_s"),
                        latent_surprise=d.get("latent_surprise"))
        except Exception as exc:
            return Look(frame=frame, attend=True, energy=1.0,
                        reason=f"gate error: {type(exc).__name__}: {exc}"[:120])

    def look(self, *, latent_surprise: float | None = None) -> Look:
        """One look. `latent_surprise` is Seam A: the standardized z-score from
        `perception.latent_predictor`. When supplied the gate fires on SEMANTIC change instead of
        pixel delta — which is the whole reason a V-JEPA lives next to this eye, and passing it
        through is what keeps the two from becoming separate pipelines."""
        frame = self.source.grab()
        look = self._attention(frame, latent_surprise)
        self._looks += 1
        self._attended += int(look.attend)
        return look

    # ------------------------------------------------------------------ the fast lane
    def _motion(self, frame: Frame) -> float:
        """Change energy on a heavily downsampled frame — cheap enough to run on EVERY frame.

        This is the eye's fast channel and it is deliberately not the attention gate. The gate's
        `frame_signature` costs 18ms at 1080p, which caps the whole eye at ~54 fps before anything
        else runs; on a 32x18 grey thumbnail the same question costs microseconds. So the eye can
        SAMPLE at the backend's full rate (120 fps here) while paying recognition prices only when
        the slow channel is opened.

        The split is not an optimisation dressed up as biology — it is the same division of labour
        vision actually uses. A fast, low-detail, high-temporal channel reports THAT something moved
        and where; a slower, high-detail channel works out WHAT it is. An eye that ran recognition
        on every frame would be neither fast nor eye-like."""
        rgb = frame.rgb
        h, w = rgb.shape[:2]
        sy, sx = max(1, h // 18), max(1, w // 32)
        thumb = rgb[::sy, ::sx].mean(axis=2)               # grey, ~32x18
        prev, self._prev_thumb = self._prev_thumb, thumb
        if prev is None or prev.shape != thumb.shape:
            return 1.0                                     # first look: everything is new
        return float(np.abs(thumb - prev).mean() / 255.0)

    def sample(self, *, hz: float | None = None, limit: int | None = None,
               motion_threshold: float = 0.004) -> Iterator[Look]:
        """The high-rate lane: every frame gets motion, only movers get recognition.

        `hz=None` runs at whatever the backend delivers. Frames below `motion_threshold` are yielded
        with attend=False and cost only the thumbnail; frames above it go through the real attention
        gate, which then makes the final call (it still knows about motion bursts, settling and
        periodic refresh, none of which a bare threshold does).

        The threshold is a floor on the fast channel, not a replacement for the gate. It exists so a
        static screen costs almost nothing at 120 fps; everything the gate decides, the gate still
        decides."""
        try:
            self.source.open_stream(target_fps=int(hz or 120))     # dxcam continuous mode
        except Exception:
            pass
        n, nxt = 0, time.monotonic()
        period = (1.0 / hz) if hz else 0.0
        while limit is None or n < limit:
            frame = self.source.grab()
            n += 1
            self._looks += 1
            motion = self._motion(frame)
            if motion < motion_threshold:
                self._quiet += 1
                yield Look(frame=frame, attend=False, energy=motion, reason="still (fast lane)")
            else:
                look = self._attention(frame, None)
                look = Look(frame=look.frame, attend=look.attend, energy=look.energy,
                            reason=look.reason, next_interval_s=look.next_interval_s,
                            latent_surprise=look.latent_surprise)
                self._attended += int(look.attend)
                yield look
            if period:
                nxt += period
                slack = nxt - time.monotonic()
                if slack > 0:
                    time.sleep(slack)
                else:
                    nxt = time.monotonic()

    def watch(self, *, hz: float | None = None, limit: int | None = None,
              attended_only: bool = False) -> Iterator[Look]:
        """Keep looking. `attended_only` yields just the frames the gate let through — the normal
        setting for anything that costs real compute downstream.

        With `hz=None` the cadence comes from the gate's own `next_interval_s`: slow while the scene
        is predicted, fast while it settles after motion. That is the same metabolic-tempo principle
        the life loop runs on — the rate is read off the state, not scheduled — and it is why an
        always-open eye on a static screen costs almost nothing. Pass an explicit `hz` only when a
        fixed sampling rate is the point (a measurement, a recording)."""
        n, nxt = 0, time.monotonic()
        while limit is None or n < limit:
            look = self.look()
            n += 1
            if look.attend or not attended_only:
                yield look
            period = (1.0 / max(hz, 0.01)) if hz else float(look.next_interval_s or 0.2)
            nxt += period
            slack = nxt - time.monotonic()
            if slack > 0:
                time.sleep(slack)
            else:
                nxt = time.monotonic()          # fell behind; do not accumulate debt

    def close(self) -> None:
        self.source.close()

    # -------------------------------------------------------------- receipts
    def stats(self) -> dict[str, Any]:
        """What this eye actually did — the numbers an audit needs, not a claim that it worked."""
        elapsed = max(1e-6, time.monotonic() - self._opened_mono)
        return {"source": self.source.name, "looks": self._looks,
                "attended": self._attended, "quiet_fast_lane": self._quiet,
                "attend_rate": round(self._attended / self._looks, 4) if self._looks else None,
                "seconds": round(elapsed, 2),
                "hz": round(self._looks / elapsed, 2)}


def open_eye(source: Source, *, gate: bool = True) -> Eye:
    """Open an eye, refusing loudly if the source cannot actually produce frames here."""
    eye = Eye(source=source, gate=gate)
    ok, why = eye.available()
    if not ok:
        raise RuntimeError(f"{source.name} source unavailable: {why}")
    return eye
