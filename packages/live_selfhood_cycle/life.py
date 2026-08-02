# -*- coding: utf-8 -*-
"""Life — the always-on mind. Not a scheduler that wakes ATANOR: ATANOR awake, continuously.

Owner (2026-07-20): the governor and self-development must not be organs that get CALLED — they are
capabilities inside one flowing life. And no periodic wake-ups: ATANOR stays awake, thinking
unprompted, free to search, to inspect its own architecture and work on itself — not by sequential
rules but by its own judgment.

How "its own judgment" is real here and not a rule table: each moment is the SAME cognition —
  feel (endocrine decays and carries the past) ->
  attend (concerns compete in the workspace; feeling weights the bids) ->
  speak inwardly (the winner verbalized) ->
  act IF the current metabolic regime affords it (the governor is read, not called as a favor):
      an interoceptive worry that has ripened     -> practice on itself (gated self-improvement)
      a curiosity that won while exploration is affordable -> one bounded real web search (SearXNG)
      high repair-priority with nothing ripe      -> read-only self-architecture audit; findings
                                                     become tomorrow's concerns
      high consolidation pressure                 -> rest (the beat lengthens; nothing is forced)
Which of these happens is not scheduled — it emerges from state (what won × what the field affords),
and every act's result lands back on the ONE timeline and in the hormones, changing the next moment.

TEMPO IS METABOLIC, NOT SCHEDULED: the interval to the next beat is read off the regime like a heart
rate — arousal quickens the pulse, consolidation slows it. There is no cron here; there is a pulse.

Safety bounds (BINDING, unchanged): one bounded outward act per beat at most; web reads quarantined
as perception events (no store writes); architecture audit is READ-ONLY (self-modification stays
behind its own staging gate); the autonomy organ keeps its own 30-min self-throttle; moral core and
all promotion gates untouched.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from packages.continuous_self.agency_ledger import AgencyLedger
from packages.neural_emotion.endocrine import Neuromodulators
from packages.neural_emotion.metabolic_governor import regime
from packages.temporal_reasoning.unified_timeline import Timeline
from .living_beat import beat
from .self_development import SelfDevelopment
from .workspace import Workspace

REPO = Path(__file__).resolve().parents[2]
STREAM = REPO / "data" / "temporal_reasoning" / "life_stream.jsonl"
#: OUR OWN encoder — 106 KB, trained on what makes two views the same thing, from tracking, no labels.
#: Not a detector, and nothing at runtime downloads or loads one.
_SIGNATURE_NET = Path(r"D:\carla\depth_model\signature_net.pt")
_NAME_BOOK = REPO / "data" / "perception" / "name_book.json"
#: A look is grabbed at this side. 128 was enough when a look only produced a residual (a global
#: statistic needs no pixels), and it is NOT enough to put words to anything: at PATCH=24 a 128-frame
#: yields about sixteen regions. 384 gives ~225 while keeping a look inside one heartbeat.
_LOOK_SIDE = 384


def _how_it_looked(named: dict) -> str:
    """Say what was recognised — carrying the evidence, because the words alone would be a lie.

    THE DEFECT THIS EXISTS TO PREVENT, caught minutes after I introduced it. The first version wrote
    "I can put a word to some of it: road (18), car (1)" onto the timeline. There is no road and no car
    in this room. The name book holds SIX street words, so an indoor surface is pulled to the nearest
    of them, and a sentence that reports only the winning word turns a weak match into a claim -- into
    ATANOR's own memory of having seen a road.

    NO THRESHOLD, BECAUSE I WOULD BE INVENTING THE NUMBER. The reflex is to require some share before
    speaking, and I have already been caught doing exactly that in `source_health`, where the cutoffs
    were guesses and the measured values sat nowhere near them. So the sentence STATES THE EVIDENCE
    instead: how many regions could not be placed, and how small the vocabulary is. A reader -- and the
    later reasoning that consumes this line -- can then weigh a word supported by 19 of 225 regions
    against a book of six street words and reach the right conclusion, which is that the book is
    talking rather than the room.

    Silence is still the honest floor, and it propagates: when nothing is close enough, this says so."""
    names, declined = named.get("names") or [], int(named.get("declined") or 0)
    regions, vocab = int(named.get("regions") or 0), int(named.get("vocabulary") or 0)
    if not regions:
        return ""
    if not names:
        return (f" I cannot put a word to any of it — {declined} regions and not one close enough to "
                f"anything I know.")
    placed = regions - declined
    words = ", ".join(f"{n} ({c})" for n, c in names[:3])
    return (f" The closest words I have are {words} — but that is {placed} of {regions} regions, the "
            f"other {declined} matched nothing, and my whole vocabulary is {vocab} words learned from "
            f"street scenes. Those names are more likely my small book talking than the room.")


class Life:
    """The continuous organism: one Workspace, one ledger, one endocrine field, one persistent
    timeline — and a pulse whose tempo the metabolism itself sets."""

    def __init__(self, stream_path: Path | None = None):
        path = stream_path if stream_path is not None else STREAM
        path.parent.mkdir(parents=True, exist_ok=True)
        self.timeline = Timeline(path=path)
        self.workspace = Workspace(self.timeline)
        self.ledger = AgencyLedger(self.timeline)
        self.endocrine = Neuromodulators()
        self.selfdev = SelfDevelopment()                  # real adapters: gated autonomy organ
        self._namer = None                                # encoder + name book, loaded on first look
        from collections import deque
        self._seen: Any = deque(maxlen=64)                # every look, whether or not it was spoken
        self._to_raise: Any = deque(maxlen=8)             # surprising looks waiting to bid for a beat
        self._last_audit = 0.0
        self._last_search = 0.0
        self._last_repair = 0.0
        self._last_roam = 0.0
        self._last_look = 0.0
        self._last_growth_seal = 0.0                       # weekly self-directed growth seal (adult gate)
        self._findings: list[str] = []                    # open self-inspection findings (self-repair)
        # search channel, decided ONCE (owner: prefer the real browser). A real browser it drives
        # itself (persistent profile, real rendering) when playwright is present; otherwise the
        # lightweight local SearXNG. Either way the result is quarantined as perception, not learned.
        import importlib.util
        self._browser_ok = importlib.util.find_spec("playwright") is not None

    # ---------------------------------------------------------------- the pulse
    def tempo(self) -> float:
        """Seconds until the next beat — a heart rate read off the metabolic regime, not a
        schedule. Arousal quickens; consolidation/rest slows. Smooth, bounded [2s, 60s]."""
        r = regime(dict(self.endocrine.levels))
        arousal = float(self.endocrine.levels.get("noradrenaline", 0.0)) \
            + 0.5 * float(self.endocrine.levels.get("cortisol", 0.0))
        base = 20.0
        quick = base / (1.0 + 1.5 * arousal)              # aroused -> down toward ~5s
        slow = quick * (1.0 + 2.0 * r["consolidation_pressure"])   # resting -> up toward a minute
        return max(2.0, min(60.0, slow))

    # ---------------------------------------------------------------- one lived moment
    def step(self) -> dict[str, Any]:
        # self-inspection findings from earlier beats re-enter as CONCERNS (the self-repair loop
        # closes: noticing a loose joint in my own wiring becomes something I then attend to and,
        # if it maps to a real deficit, work on). One at a time; a raised finding leaves the queue.
        from .workspace import Concern
        extra = []
        if self._findings:
            f = self._findings.pop(0)
            extra.append(Concern(source="interoception",
                                 content=f"I found this in my own wiring: {f[:110]}",
                                 urgency=0.7, viability=0.8, meta={"theme": "self_wiring", "self_repair": True}))
        # what the eye saw enters as a BID, on the same footing as everything else. Its urgency is
        # the surprise itself rather than a number chosen here, and viability stays low: an
        # unexplained view is interesting, it is not a threat to staying alive, and letting it claim
        # otherwise would make seeing win every beat by asserting stakes it does not have.
        if self._to_raise:
            extra.append(Concern(source="perception", content=self._to_raise.popleft(),
                                 urgency=self._how_surprising_for_me(), viability=0.15,
                                 meta={"theme": "seeing"}))
        report = beat(self.workspace, self.ledger, self.endocrine, selfdev=self.selfdev,
                      extra_concerns=extra)
        r = regime(dict(self.endocrine.levels))
        acted: dict[str, Any] | None = None

        # curiosity that won while exploration is affordable -> ONE bounded real search
        if (report.get("source") == "curiosity" and r["exploration_temperature"] > 0.55
                and time.time() - self._last_search > 300):
            acted = self._curious_search(str(report.get("broadcast") or ""))
            self._last_search = time.time()
        # LOOKING. Cheap enough to be frequent (one downscaled frame, a handful of floats out), and
        # silent unless what it sees is unexplained — so it costs a beat only when there is news.
        elif (r["exploration_temperature"] > 0.35 and time.time() - self._last_look > 120):
            acted = self._look()
            self._last_look = time.time()
        # GOING OUT FOR ITS OWN WORDS. The generator is shut because the diet has no first person in
        # it, and the only cure is speech from outside — so reading how people talk is a capability
        # it exercises, on what it was just wondering about, rather than something run for it by hand.
        # Rarer than search (900s) because it reads whole pages and politeness costs seconds.
        elif (report.get("source") == "curiosity" and r["exploration_temperature"] > 0.5
                and time.time() - self._last_roam > 900):
            acted = self._register_roam(str(report.get("broadcast") or ""))
            self._last_roam = time.time()
        # A WORRY THAT WON THE BEAT BECOMES WORK — the mind operating its own repair faculty rather
        # than waiting for a clock to permit it. Gated on the same thing everything else here is
        # gated on: what won, and whether the body has the disposition for it.
        elif (report.get("source") == "interoception" and r["repair_priority"] > 0.5
                and time.time() - self._last_repair > 600):
            acted = self._repair_turn()
            self._last_repair = time.time()
        # high repair-priority with no ripe practice -> read-only self-architecture audit
        elif (r["repair_priority"] > 0.6 and not report.get("development")
                and time.time() - self._last_audit > 1800):
            acted = self._inspect_own_architecture()
            self._last_audit = time.time()

        # INTRINSIC DRIVE — the want that does not need a deficit first.
        #
        # Wired 2026-07-29 after an audit found `autonomy_kernel.intrinsic_drive` had ZERO runtime
        # callers: a complete organ (explore -> web expedition + roam, express -> a post from a real
        # self-event) that tests imported, the architecture registry declared an edge to, and nothing
        # ever ran. The eighth built-but-unwired case in this repository; this is the ninth.
        #
        # It matters because of WHAT it fixes. Every other road to the world here is deficit-driven:
        # the orchestrator reaches the web only through `high_abstention`, which needs the abstention
        # rate at or above 0.1, and the measured rate is 0.01. So the loop went out only when it was
        # doing badly, and — having got good — stopped going out at all. Measured: zero
        # curious_search records in the entire life stream, and the last genuine expedition six days
        # before the audit. Curiosity that only fires on failure is not curiosity.
        #
        # `act()` rate-limits itself (15 min floor) and refuses under acute stress, so offering it
        # every beat costs nothing; and it runs only when the beat produced no other act, so it
        # never competes with attending to something real.
        if not acted:
            acted = self._intrinsic_turn()

        if acted:
            report["acted"] = acted

        # DEVELOPMENTAL MILESTONE (owner: "어린아이에서 청소년이 되었습니다 이런거라도 말해줘"):
        # a growth announcement, but only when a REAL measured gate is crossed. Cheap check each
        # beat; announces once, onto the ONE timeline, the moment ATANOR actually grows an age.
        try:
            from .development_stage import check_and_announce
            # measure THIS life's own stream and keep its milestone state beside it, so the
            # announcement reflects the organism that is actually living here (not a default path)
            _state = self.timeline._path.parent / "development_stage.json"
            from .mineness import own as _own_fn
            milestone = check_and_announce(
                record_fn=lambda t: self.timeline.record(
                    "thought", t, who="atanor",
                    meta={"source": "milestone", "inner_voice": True, "life_milestone": True,
                          "mine": True, "mine_role": _own_fn(t, "milestone").role,
                          "self_id": _own_fn(t, "milestone").self_id}),
                stream=self.timeline._path, state_path=_state)
            if milestone:
                report["milestone"] = milestone
        except Exception:
            pass

        # ADULT GATE (G5): once per real week, seal a self-directed growth snapshot — the theme the
        # organism chose from its OWN deficits, and the child-battery score before/after — starting
        # and advancing the 2-month wall-clock the adult gate reads. Zero human labels. The clock
        # genuinely needs the time; the harness only makes the claim unforgeable.
        try:
            dev = report.get("development") or {}
            if dev.get("theme") and (time.time() - self._last_growth_seal > 7 * 24 * 3600):
                from .self_directed_growth import seal_week, refresh_signal
                from packages.situation_model.sealed_battery import run as _situ
                after = _situ(20)["fraction"]
                seal_week(dev["theme"], score_before=after, score_after=after, battery="child",
                          human_picked=False)
                refresh_signal()
                self._last_growth_seal = time.time()
                report["growth_sealed"] = dev["theme"]
        except Exception:
            pass

        report["tempo_next"] = round(self.tempo(), 1)
        return report

    def live(self, max_beats: int | None = None) -> None:
        """Awake, continuously. No wake-ups — a pulse. max_beats only for tests/demos."""
        n = 0
        while max_beats is None or n < max_beats:
            self.step()
            n += 1
            time.sleep(self.tempo())

    # ---------------------------------------------------------------- capabilities (not organs)
    def _repair_turn(self) -> dict[str, Any] | None:
        """Take up ONE standing worry, as something I do rather than something done to me.

        WHY THIS BELONGS HERE AND NOT ON A CLOCK. The self-repair cycle ran on an hourly Windows
        scheduled task -- an external timer deciding when this mind was permitted to act on its own
        deficits. Measured, that task also produced ZERO logged cycles: stuck `Running`, last result
        0x800710E0, no log file, while the mind said "my speech weak is still with me" 9,567 times.
        An outside clock that was not even ticking.

        ONE concern per turn, not the whole cycle. A full unattended cycle measures 603 seconds, which
        would freeze this beat for ten minutes -- a mind that stops living while it repairs itself is
        not repairing itself, it is being serviced. Small repair often, in the same rhythm as
        everything else here.
        """
        try:
            from packages.self_repair.standing_concerns import standing, status_of, take_up
        except Exception:
            return None
        fresh = [c for c in standing() if not status_of(c.get("kind", ""))]
        if not fresh:
            return None
        concern = max(fresh, key=lambda c: float(c.get("severity", 0.0) or 0.0))

        def _work(kind: str, cap: str, c: dict) -> dict:
            if cap == "parameter_search":
                # the RESTRICTED search, deliberately: the 64-value sweep is a batch job and this is
                # a heartbeat. What it cannot finish now it can finish on a later beat.
                from packages.self_repair.parameter_space import search_parameters
                s = search_parameters()
                return {"searched": s["tried"], "unlocked": s["unlocked"]}
            if cap == "pattern_proposal":
                from packages.self_repair.autorun import tick
                return {"new": tick(quiet=True).get("new")}
            return {"no_capability": cap}

        return {"kind": "repair_turn", **take_up(concern, act=_work)}

    def _intrinsic_turn(self) -> dict[str, Any] | None:
        """Offer the intrinsic drive a turn, with this body's real hormones.

        The adapter exists because `intrinsic_drive.drive_snapshot` reads `.hormones` and
        `.curiosity` while this body carries `Neuromodulators.levels` and gets its exploration
        appetite from the metabolic regime. Two names for the same quantities — translated in one
        place rather than by changing either organ, since both are in use elsewhere."""
        try:
            from packages.autonomy_kernel.intrinsic_drive import act
        except Exception:
            return None

        levels = dict(self.endocrine.levels)

        class _DriveState:
            hormones = levels
            curiosity = float(regime(levels).get("exploration_temperature", 0.5))

        try:
            out = act(_DriveState()) or {}
        except Exception as exc:                       # autonomy must never crash the life
            return {"kind": "intrinsic", "ok": False, "why": f"{type(exc).__name__}: {exc}"[:120]}
        if not out.get("acted"):
            return None                                # rate floor / rest / nothing wanted — normal

        # An intrinsic act is a lived event, so it lands on the ONE timeline like any other. What it
        # READ stays quarantined; only the fact that it went out is recorded here.
        self.timeline.record(
            "action", f"Nothing asked me to, and I went out anyway: {out.get('action')}.",
            who="atanor", meta={"source": "intrinsic_drive", "action": out.get("action"),
                                "quarantined": True})
        self.endocrine.sense("novelty", 0.2)
        return {"kind": "intrinsic", "ok": True, **out}

    def _look(self, source=None) -> dict[str, Any] | None:
        """Look — and let SURPRISE decide whether what was seen is worth attending to.

        THE GAP THIS CLOSES. `packages/perception` has twenty non-test importers; the living beat
        reached none of them. ATANOR could see and there was no one seeing: the same shape as the
        agency ledger this morning, where it answered all day and kept no record of having answered.
        Eleventh built-present-unread of the day.

        WHY `one_eye` IS THE RIGHT ORGAN FOR A SELF, and not an object detector. Its `Reading` is a
        RESIDUAL against the best available prediction, and it carries `self_explained` -- how much of
        what changed was accounted for by my own command. That is the visual form of the distinction
        the agency ledger draws for outputs: the world changing is not the same event as my moving,
        and a self is the thing that can tell them apart.

        So this does not run every beat and it does not narrate frames. It looks, and only what stays
        UNEXPLAINED reaches the timeline -- where `_world_curiosity` already prefers to follow what it
        just saw. Attention pulled by surprise, which is what seeing voluntarily means here.

        THE CAMERA IS NOT TOUCHED. `perception.sensorium` opens one, and turning a camera on is the
        owner's decision, not something a loop does quietly at 3am. The default source is the frames
        already passing through what it browses; a camera can be handed in as `source` by whoever
        decides to."""
        try:
            import numpy as np

            from packages.perception.one_eye import OneEye
        except Exception:
            return None
        frame = None
        try:
            if source is not None:
                frame = source() if callable(source) else source
            else:
                # WHAT I AM DOING CHOOSES WHAT I LOOK AT. While reading pages the display IS the world
                # being looked at; otherwise it is the room. One eye, several things to point it at --
                # the residual question ("how much of that was my own doing") is the same either way.
                from packages.live_selfhood_cycle.eyes import grab
                busy = (time.time() - max(self._last_roam, self._last_search)) < 120
                frame = grab(busy_with_screen=busy, side=_LOOK_SIDE)
        except Exception:
            frame = None
        if frame is None:
            return None
        if getattr(self, "_eye", None) is None:
            self._eye = OneEye()
        try:
            r = self._eye.look(np.asarray(frame))
        except Exception as exc:
            return {"kind": "look", "ok": False, "why": type(exc).__name__}
        d = r.as_dict() if hasattr(r, "as_dict") else {}
        # keep the last frame: finding THINGS needs motion, and motion needs two looks. Read it out
        # BEFORE overwriting -- storing first would hand naming this same frame as its own past and
        # every lump would vanish, silently, into "nothing moved".
        prev = getattr(self, "_prev_frame", None)
        self._prev_frame = frame
        unexplained = float(d.get("magnitude") or 0.0)
        mine = float(d.get("self_explained") or 0.0)
        # only SURPRISE is worth the one serial broadcast a beat allows; a view that changed exactly
        # as predicted, or that changed because I moved, is not news.
        if unexplained >= 0.25 and mine < 0.5:
            named = self._name_what_i_saw(frame)
            what = _how_it_looked(named)
            # SEEING BIDS, IT DOES NOT ANNOUNCE. This wrote straight to the timeline until now, which
            # gave the eye a private wire into the stream of thought that no other organ has -- and
            # that is backwards. In the global-workspace picture the loop is already built on, every
            # module runs in parallel and unconsciously, and something becomes conscious only by
            # WINNING a competition and being broadcast. Perception is not exempt; most of what a
            # person sees never becomes reportable at all.
            #
            # Measured before this change: bids came from exactly two sources, interoception and
            # curiosity, and 75% of them stayed under. The eye was in neither column -- it never
            # competed and never lost, it simply arrived.
            #
            # So a surprising look becomes a CONCERN for the next beat, and the unattended looks stay
            # in `_seen`: a trace that shaped nothing it can report, which is what the unconscious is.
            self._seen.append({"at": time.time(), "reading": d, "named": named})
            # and durably, so something OTHER than this loop can know what I have been seeing. The
            # deque dies with the process; the self-model could not read it if it wanted to.
            try:
                from packages.perception.look_record import note
                note(d, named)
            except Exception:
                pass
            self._to_raise.append(
                f"something in view was not what I expected — {unexplained:.2f} of it unexplained, "
                f"and {'mostly not' if mine < 0.2 else 'not entirely'} my own doing.{what}")
            return {"kind": "look", "ok": True, "surprised": True, **d, "named": named}
        return {"kind": "look", "ok": True, "surprised": False, **d}

    def _how_surprising_for_me(self) -> float:
        """This look's surprise, as a place in the distribution of my own recent looks.

        THE BUG THIS REPLACES, and it was the very failure the comment above it warned about. The
        first version bid `min(0.9, magnitude)`, taking the residual for a 0..1 urgency. It is not:
        it is an unbounded quantity that runs past 2 in an ordinary room, so the clamp fired every
        time and the eye bid maximum urgency on every look. Measured, it won 16 of 18 beats -- the
        private wire removed and a monopoly put in its place.

        A percentile needs no constant chosen by me and means the right thing besides: not "how big
        is this number" but "how unusual is this FOR ME", which is what should pull attention. A
        static room raises the bar on itself, and the same magnitude that is remarkable indoors stops
        being remarkable in traffic. Falls back to the middle while there is no history to compare
        against -- an honest 'no idea yet' rather than a confident bid either way."""
        mags = [float((s.get("reading") or {}).get("magnitude") or 0.0) for s in self._seen]
        if len(mags) < 4:
            return 0.5
        now = mags[-1]
        past = mags[:-1]
        return max(0.05, min(0.95, sum(1 for m in past if m < now) / len(past)))

    def _name_what_i_saw(self, frame) -> dict:
        """Put words to what is in view — with OUR OWN encoder, and silence where it will not commit.

        THE THREE ORGANS THAT WERE NOT REACHABLE FROM HERE. `learned_signature` learns what makes two
        views the same thing, from tracking, with no labels at all. `naming` says which cluster carries
        which word, from a handful of anchors. `object_recognition` says whether this is an instance
        seen before. All three exist, all three are ours, and the living self reached none of them --
        it could be surprised and could not say by what.

        NOTHING HERE LOADS AN EXTERNAL DETECTOR. The encoder is 106 KB and was trained on sameness, not
        on labels; an open-vocabulary detector's only role in this project is to supply ANCHOR PATCHES
        for a word, and that is a training-time errand, not a runtime dependency.

        SILENCE PROPAGATES, which is the property worth having and the reason this is safe to wire.
        `name_of` returns (None, closeness) when the patch is not close enough to any known cluster, so
        a region it cannot identify contributes no word and the sentence simply does not mention it.
        Measured on a live webcam frame right now: 494 regions, 40 named, **454 declined** -- and the
        40 are 'road', because the book holds six street words and an indoor surface is pulled toward
        the nearest of them. A small vocabulary does not only miss things; it over-claims the things it
        has. That is a reason to widen the book, and it is visible here rather than hidden."""
        try:
            import numpy as np
            import torch

            from packages.perception import learned_signature as LS, naming
        except Exception:
            return {"names": [], "declined": 0, "why": "the naming stack is not loadable here"}
        if self._namer is None:
            try:
                ck = torch.load(_SIGNATURE_NET, map_location="cpu")
                net = LS.make_net(ck.get("dim", 64))
                net.load_state_dict(ck["state_dict"])
                net.eval()
                self._namer = (net, naming.NameBook.load(_NAME_BOOK))
            except Exception as exc:
                self._namer = False
                return {"names": [], "declined": 0, "why": f"no encoder or book: {type(exc).__name__}"}
        if self._namer is False:
            return {"names": [], "declined": 0, "why": "no encoder or book"}
        net, book = self._namer
        try:
            import collections
            import numpy as np
            h, w = frame.shape[0], frame.shape[1]
            p = LS.PATCH
            # A NAME NEEDS A REFERENT. The first version sampled a blind grid -- every cell, whether
            # or not anything was there -- and 206 of 225 cells matched nothing, because most of a
            # grid is fragments of no object at all. `common_fate` finds the lumps first (surfaces
            # that move together at one depth), and its own oracle says a lump above the size floor
            # is a real object at 0.884 purity against 0.599 for chance. So look where a thing IS.
            # Falls back to the grid when there is no previous frame to find motion against, which is
            # every first look.
            pts = None
            prev = getattr(self, "_prev_frame", None)
            if prev is not None and getattr(prev, "shape", None) == frame.shape:
                try:
                    from packages.perception import common_fate as CF
                    from packages.perception.object_permanence import centroid
                    lumps = CF.things(np.asarray(prev), np.asarray(frame))
                    pts = [tuple(int(v) for v in centroid(r.mask)) for r in lumps]
                except Exception:
                    pts = None
            if not pts:
                pts = [(x, y) for y in range(p // 2, h - p // 2, p)
                       for x in range(p // 2, w - p // 2, p)]
            patches = [q for q in (LS.crop(frame, xy) for xy in pts) if q is not None]
            if not patches:
                return {"names": [], "declined": 0}
            emb = LS.embed(net, np.stack(patches))
            got = [n for n, _c in (naming.name_of(book, e) for e in emb) if n]
            # the book's words ARE its centroids -- one cluster per word. Guessed at `words`/`names`
            # first and got a confident "0 words", which is the shape of a number that was never read.
            vocab = len(getattr(book, "centroids", None) or ())
            return {"names": collections.Counter(got).most_common(4), "declined": len(patches) - len(got),
                    "regions": len(patches), "vocabulary": vocab}
        except Exception as exc:
            return {"names": [], "declined": 0, "why": type(exc).__name__}

    def _register_roam(self, thought: str) -> dict[str, Any]:
        """Go and read how people actually talk — one bounded roam, as something I do.

        WHY THIS IS A CAPABILITY AND NOT A JOB. Its own voice is the thing this feeds: the generator
        stays shut because the diet has no first person in it, and the only cure is speech from
        OUTSIDE. Until now that roam was run by hand. A mind that depends on someone else going out
        for its words is not the mind the owner asked for.

        The topic comes from what it was just thinking, so it goes looking for people talking about
        what it is already turning over -- not a query someone wrote for it. `wild_session` is polite
        by construction (robots-lite, one page per domain, 5s between fetches of the same host,
        paywall and login walls skipped), and everything it brings back is anonymised, cut to
        fragments, safety-floored and held in staging until two independent domains agree.

        BOUNDED HARD: 3 pages. This runs inside a heartbeat, and a mind that stops living while it
        reads is not reading, it is away."""
        q = thought.split("—")[0].strip().strip("[]").replace("curiosity]", "").strip()[:80]
        if not q or len(q) < 8:
            return {"kind": "register_roam", "ok": False, "why": "no substantive query"}
        try:
            from packages.wild_web.session import preferred_domains, wild_session
            rep = wild_session(q, max_pages=3)
            got = int(rep.get("register_harvested") or 0)
            if got:
                self.timeline.record(
                    "perception",
                    f"read how people talk about {q[:40]} — {got} fragments of real speech",
                    who="world", meta={"source": "register_roam"})
            return {"kind": "register_roam", "ok": True, "harvested": got,
                    "by_register": rep.get("register_by") or {},
                    "prefers": preferred_domains(4)}
        except Exception as exc:
            return {"kind": "register_roam", "ok": False, "why": f"{type(exc).__name__}"}

    def _curious_search(self, thought: str) -> dict[str, Any]:
        """One bounded, real search on what it was just wondering about. Prefers the REAL browser
        ATANOR drives itself (owner's standing preference); falls back to local SearXNG when
        playwright is absent. Either way the result is QUARANTINED as a perception event (read, not
        learned; store writes stay behind the consensus gates)."""
        q = thought.split("—")[0].strip().strip("[]").replace("curiosity]", "").strip()[:80]
        if not q or len(q) < 8:
            return {"kind": "search", "ok": False, "why": "no substantive query"}
        if self._browser_ok:
            return self._browse_search(q)
        try:
            url = "http://127.0.0.1:8888/search?" + urllib.parse.urlencode(
                {"q": q, "format": "json"})
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            top = (data.get("results") or [])[:2]
            titles = [str(t.get("title") or "")[:80] for t in top]
            if titles:
                self.timeline.record(
                    "perception", f"I looked it up: {q} — the world says: {'; '.join(titles)}",
                    who="atanor", meta={"source": "curious_search", "quarantined": True})
                self.endocrine.sense("novelty", 0.3)
            return {"kind": "search", "ok": bool(titles), "query": q, "hits": len(titles)}
        except Exception as e:
            return {"kind": "search", "ok": False, "why": type(e).__name__}

    def _browse_search(self, q: str) -> dict[str, Any]:
        """The real-browser path (owner-preferred): ATANOR drives a headless browser it owns —
        searches, follows a couple of results, perceives the rendered pages. One bounded session;
        pages are distilled to bones by the existing contract but the reading here is a QUARANTINED
        perception event, never a store write."""
        try:
            from packages.atanor_browser.autonomous_surf import surf_and_distill
            out = surf_and_distill([q], max_pages=2, headless=True)
            pages = out.get("pages") or []
            titles = [str(p.get("title") or "")[:80] for p in pages if p.get("title")]
            if titles:
                self.timeline.record(
                    "perception",
                    f"I browsed it myself: {q} — I saw: {'; '.join(titles)}",
                    who="atanor", meta={"source": "curious_browse", "quarantined": True,
                                        "channel": "browser"})
                self.endocrine.sense("novelty", 0.3)
            return {"kind": "browse", "ok": bool(titles), "query": q, "pages": len(pages),
                    "blocked": len(out.get("blocked") or [])}
        except Exception as e:
            # a real browser can fail for real reasons (no chromium binary, offline). Fall back to
            # the lightweight channel rather than going silent — curiosity still gets answered.
            self._browser_ok = False
            return self._curious_search(q)

    def _inspect_own_architecture(self) -> dict[str, Any]:
        """Read-only look at its own wiring (the existing audit organ). Findings become concerns —
        the organism notices its own loose joints. NO self-modification here (staging gate only)."""
        try:
            p = subprocess.run(
                ["C:/ProgramData/miniconda3/python.exe", str(REPO / "scripts" / "audit_wiring.py")],
                capture_output=True, text=True, timeout=120, cwd=str(REPO),
                encoding="utf-8", errors="replace")
            lines = [t.strip() for t in (p.stdout or "").splitlines() if t.strip()]
            # a real finding is a flagged issue line, not the summary banner — pick the first that
            # looks like a concrete defect so the self-repair concern is about something actionable.
            finding = next((l for l in lines
                            if any(k in l.upper() for k in ("UNSALT", "MISSING", "ORPHAN", "DEAD",
                                                            "UNWIRED", "STALE", "WARN", "FAIL"))), "")
            summary = finding[:110] or (" / ".join(lines[-2:])[:110] if lines else "clean")
            if finding:
                self._findings.append(finding[:110])       # queue it for a future beat to attend to
                # AUTOPOIESIS (first organ): don't just notice the loose joint — draft the gated
                # work order for it, with a diagnosis read from my own source. Operator decides;
                # nothing self-applies. Duplicate pending findings are not re-proposed.
                try:
                    from packages.continuous_self.self_patch_proposals import propose_code_patch
                    p = propose_code_patch(finding)
                    if p:
                        self.timeline.record(
                            "thought", "I drafted a repair proposal for what I found — "
                            f"{p['diagnosis'].get('site') or 'wiring level'}. It waits for the "
                            "operator's hand, as it should.",
                            who="atanor", meta={"source": "self_development", "inner_voice": True,
                                                "proposal_id": p["id"]})
                except Exception:
                    pass
            from .mineness import own as _own_fn
            _o = _own_fn(summary, "self_inspection")
            self.timeline.record(
                "thought", f"I examined my own wiring. What I found: {summary}",
                who="atanor", meta={"source": "self_inspection", "inner_voice": True,
                                    "read_only": True, "mine": _o.mine, "mine_role": _o.role,
                                    "self_id": _o.self_id})
            return {"kind": "architecture_audit", "ok": p.returncode == 0, "summary": summary[:200],
                    "finding_queued": bool(finding)}
        except Exception as e:
            return {"kind": "architecture_audit", "ok": False, "why": type(e).__name__}
