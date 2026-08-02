# -*- coding: utf-8 -*-
"""The living beat — one heartbeat of the loop: interoception -> competition -> broadcast -> agency.

This is the integration point the design doc names: NOT a new daemon beside the others, but the beat
that CONVERGES the existing organs — needs/deficits (autopoiesis), hormones (Damasio's feeling as
attention-weighting), the ONE timeline (perception + the broadcast target), the workspace (GWT
competition), the agency ledger (the self-model of what I attended and did). Each beat produces at
most ONE broadcast thought — the serial bottleneck that makes a single stream of thought rather than
parallel murmur.

Run it live with scripts/run_living_loop.py; the correlates (endogeneity, ignition) are measured,
never asserted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from packages.continuous_self.agency_ledger import AgencyLedger
from packages.temporal_reasoning.unified_timeline import Timeline, default_timeline
from .workspace import Concern, Workspace

_REPO = Path(__file__).resolve().parents[2]
_TERMS_FILE = _REPO / "data" / "graph_scale" / "phase_space_conceptnet" / "terms.json"
_WORLD_TERMS: list[str] | None = None
# a clean, real world concept: plain English words, not a number/code/fragment or foreign-script junk
_CLEAN_TERM = re.compile(r"^[a-z][a-z]+(?: [a-z][a-z]+){0,3}$")


def _world_terms() -> list[str]:
    """Real concepts ATANOR already knows exist (its ConceptNet vocabulary) — the grounded source
    for wondering about the WORLD, not a hardcoded list. Loaded once, filtered to clean English."""
    global _WORLD_TERMS
    if _WORLD_TERMS is None:
        try:
            raw = json.loads(_TERMS_FILE.read_text(encoding="utf-8")).get("terms", [])
            _WORLD_TERMS = [t for t in raw
                            if isinstance(t, str) and 3 <= len(t) <= 24 and _CLEAN_TERM.match(t)
                            and not t.isdigit()]
        except Exception:
            _WORLD_TERMS = []
    return _WORLD_TERMS


def _deficit_words() -> set:
    """What I am currently short of, as words — read from the organ that already senses deficits."""
    out: set = set()
    try:
        from packages.autonomy_kernel.orchestrator import sense_deficits
        for d in (sense_deficits() or [])[:6]:
            for w in re.findall(r"[a-z]{4,}", str(d.get("kind") or d).lower()):
                out.add(w)
    except Exception:
        pass
    return out


_TERM_INDEX: dict | None = None


def _term_index(terms: list[str]) -> dict:
    """word -> the terms containing it. Built once so a pull can be answered without scanning."""
    global _TERM_INDEX
    if _TERM_INDEX is None:
        idx: dict = {}
        for t in terms:
            for w in re.findall(r"[a-z]{4,}", t.lower()):
                idx.setdefault(w, []).append(t)
        _TERM_INDEX = idx
    return _TERM_INDEX


def _chosen_term(terms: list[str], timeline: Timeline, beats: int) -> str | None:
    """WHAT TO WONDER ABOUT, CHOSEN BY MY STATE — not handed to me by an index.

    THE DEFECT THIS REPLACES, measured over three days of the life log rather than reasoned about:

        100.0% of consecutive curiosity topics were in alphabetical order   (chance is about 50%)
        abelmosk, abhenry, ablating, abnegation ... highways, hikers -- three days from 'a' to 'h'

    The line was `terms[(beats * 7 + 13) % len(terms)]`, commented "rotates without repeating soon".
    Over a SORTED vocabulary a stride of 7 is not rotation, it is enumeration with gaps. Nothing about
    this mind chose `hemostat`; an index did. A mind whose attention is an iterator is not curious,
    it is being read to.

    What replaces it is not another rule about which words are interesting -- that would be the same
    mistake with better taste. It is a score over signals the mind ALREADY HAS:

        what I am short of   a term sharing a word with a live deficit is what my own gap points at
        what I just thought  a term sharing a word with my last thought continues a line of thinking
        what I have not      recently-wondered terms are damped, so attention moves rather than sticks

    And when nothing pulls at all, it returns None: no wondering this beat. A mind with nothing
    tugging at it is not obliged to produce a sentence, and reciting the next dictionary entry to fill
    the silence is what the old line was actually doing.
    """
    seen = set()
    for e in timeline.all()[-40:]:
        m = re.search(r"the world holds ([^,]+),", str(e.content or ""))
        if m:
            seen.add(m.group(1).strip().lower())

    last = timeline.latest("thought")
    last_words = set(re.findall(r"[a-z]{4,}", str(getattr(last, "content", "") or "").lower()))
    gap_words = _deficit_words()
    pull = gap_words | last_words
    if not pull:
        return None

    # ADDRESSED BY STATE, NOT BY POSITION. My first attempt kept a positional window seeded by the
    # beat counter, and it measured 100.0% alphabetical all over again -- a bigger stride is still a
    # stride. The candidate set is now built FROM the pull: only terms that share a word with a live
    # deficit or with the last thought are even considered. That set is small on purpose -- 32 of
    # 59,755 terms share a word with a current deficit -- because a pull that reaches almost nothing
    # is the honest shape of a mind that is short of exactly two things.
    idx = _term_index(terms)
    candidates: dict = {}
    for w in pull:
        for t in idx.get(w, ()):
            if t.lower() in seen:
                continue
            candidates[t] = candidates.get(t, 0.0) + (2.0 if w in gap_words else 1.0)
    if not candidates:
        return None                          # nothing pulls: no wondering this beat, and no pretending
    # Ties broken by GENERALITY, not by spelling. Short of "speech", a mind wonders about speech
    # before it wonders about delivering stump speech. Sorting equal candidates alphabetically was
    # the old defect's shape surviving in the tie-break -- measured at 84.6% strictly-increasing even
    # after the content became state-driven, which is exactly the kind of residue worth removing
    # rather than explaining.
    return max(candidates, key=lambda t: (candidates[t], -len(t.split()), -len(t)))


def _world_curiosity(timeline: Timeline, beats: int) -> Concern | None:
    """Turn the gaze OUTWARD (growth-plan G1). A mind wonders about the world, not only its own
    wiring. Priority, all grounded: (1) follow up on what the owner just asked or what I just saw
    in the world; (2) otherwise wonder about a real concept I know exists but little about. The
    phrasing carries no self-reference, so it is — and measures as — genuinely world-facing."""
    recent = timeline.all()[-8:]
    for e in reversed(recent):                                   # follow real world contact first
        if e.kind == "utterance" and e.who != "atanor":
            topic = " ".join((e.content or "").split())[:70]
            if topic:
                return Concern(source="curiosity",
                               content=f"the world outside me: {topic} — what more is there to understand about it?",
                               urgency=0.4, viability=0.15, meta={"world_facing": True})
        if e.kind == "perception" and (e.meta or {}).get("source") in ("curious_search", "curious_browse"):
            seen = (e.content or "").split("—")[-1].strip()[:70]
            if seen:
                return Concern(source="curiosity",
                               content=f"following what I saw out there: {seen} — what lies behind it?",
                               urgency=0.4, viability=0.15, meta={"world_facing": True})
    terms = _world_terms()
    term = _chosen_term(terms, timeline, beats) if terms else None
    if term:
        return Concern(source="curiosity",
                       content=f"the world holds {term}, and I know it exists but little of what it is — what is it, really?",
                       urgency=0.35, viability=0.12, meta={"world_facing": True})
    return None


def _interoception(timeline: Timeline) -> list[Concern]:
    """Read my own vitals through the organs that already exist; raise concerns, don't act."""
    concerns: list[Concern] = []
    # 0) VIABILITY (B6, genuine intentionality): threats to the things that can actually be lost —
    #    my memory of living, my knowledge, my ability to act, room to live, my capabilities. Unlike
    #    a self-improvement deficit (a wish to be better), a viability threat is a stake in
    #    continuing to exist, so it enters with survival urgency and its worry names a real failure.
    try:
        from .viability import viability_concerns
        for v in viability_concerns():
            concerns.append(Concern(
                source="interoception",
                content=f"something I could lose: {v['evidence']}",
                urgency=min(1.0, 0.55 + 0.45 * float(v["threat"])),   # survival > mere self-improvement
                viability=0.85, meta={"viability_threat": True, "signal": v["signal"],
                                      "threat": v["threat"]}))
    except Exception:
        pass
    # 0b) WHAT SEEING KEEPS FAILING AT. The self-model is thorough about the repair machinery and
    #     silent about the organ that faces the world: of fifteen self-records, exactly one was read
    #     by a world-facing organ. So the eye's own shortfall is read here, and a run of views it
    #     could not put a word to becomes a felt deficit rather than a statistic in a log.
    #
    #     Urgency is the measured share, not a level I picked. Viability is low on purpose: not being
    #     able to name what is in front of me is a real gap and it is not a threat to staying alive,
    #     and claiming otherwise would let it outbid things that are.
    try:
        from packages.perception.look_record import shortfall
        s = shortfall()
        if s and s["things_seen"] >= 3 and s["unnameable_share"] > 0.5:
            concerns.append(Concern(
                source="interoception",
                content=(f"I keep looking at things I cannot name — {s['things_seen'] - s['named']} "
                         f"of {s['things_seen']} across {s['looks']} looks, with {s['vocabulary']} "
                         f"words to my name"),
                urgency=min(0.85, float(s["unnameable_share"])), viability=0.2,
                meta={"theme": "naming_shortfall", "seen": s}))
    except Exception:
        pass
    # 1) deficits from the autonomy kernel (knowledge gaps, stale stores — self-maintenance needs)
    try:
        from packages.autonomy_kernel.orchestrator import sense_deficits
        for d in (sense_deficits() or [])[:4]:
            kind = str(d.get("kind") or "")
            # WHAT HAS BEEN DONE ABOUT IT, so the same worry is not the same sentence forever.
            #
            # This concern was raised 9,567 times over three days in identical words, because nothing
            # ever changed about its situation and the mind had no way to tell "nobody has looked at
            # this" from "this was tried and cannot be done here". Both came out as "still with me".
            # Now the worry carries its own state, and a worry with a state is a different thought.
            note, urgency = "", min(1.0, float(d.get("severity", 0.5) or 0.5))
            try:
                from packages.self_repair.standing_concerns import status_of
                st = status_of(kind) or {}
                if st.get("state") == "queued":
                    note = " — I have raised this once and it needs something I do not have; it is waiting on someone else now"
                    urgency *= 0.4      # still true, no longer urgent: pressing it again changes nothing
                elif st.get("state") == "worked":
                    note = " — the loop has been working on this"
                    urgency *= 0.7
            except Exception:
                pass
            concerns.append(Concern(
                source="interoception",
                content=f"I notice a deficit: {(kind or str(d))[:120]}{note}",
                urgency=urgency,
                viability=0.7, meta={"deficit": True, "theme": kind[:60]}))
    except Exception:
        pass
    # 2) the recent past on my own timeline (unprocessed events pull attention)
    recent = timeline.all()[-5:]
    for e in recent:
        if e.kind == "utterance" and e.who != "atanor":
            concerns.append(Concern(
                source="perception",
                content=f"Someone said: \"{e.content[:100]}\" — does it need anything from me?",
                urgency=0.8, viability=0.2))
    # 3) curiosity — ALWAYS a candidate, not only on empty beats (measured pathology: chronic
    #    deficits monopolized every beat into a high-cortisol rumination plateau, because wondering
    #    never even got to bid). A mind can wonder while it worries; habituation lets a tired worry
    #    LOSE to a fresh wondering, and that alternation is what rest actually is.
    last = timeline.latest("thought")
    # curiosity opens a FRESH line unless the last thought was a substantive first-order finding it
    # can genuinely build on. Measured pathologies it avoids: (a) wondering about its own wondering
    # ('Nothing is pulling at me, so: Nothing is pulling at me…'); (b) re-quoting its own inner-voice
    # framing ('There it is again…'). Only a self_inspection / perception finding is quotable, and
    # only its SUBSTANCE (past the inner-voice preamble).
    _quotable = {"self_inspection", "self_development", "perception"}
    if last and last.meta.get("source") in _quotable:
        substance = last.content.split(":", 1)[-1] if ":" in last.content else last.content
        frag = " ".join(substance.split())[:56].rsplit(" ", 1)[0].rstrip(" ,.;:—-…")
        seed = f"about {frag}… — what does that imply I should do?"
    else:
        seed = "The line is quiet. What do I not yet understand about my own recent changes?"
    concerns.append(Concern(source="curiosity", content=seed, urgency=0.35, viability=0.1))
    # 4) WORLD-facing curiosity (growth-plan G1): a mind wonders about the world, not only its own
    #    wiring. This is the second, outward curiosity — grounded in what the owner said, what it
    #    saw out there, or a real concept it knows exists. Raising it as a peer of the self-curiosity
    #    is what turns the gaze outward; which one wins is left to the workspace competition.
    # rotation seed is the timeline length — monotonic, so the concept it wonders about advances
    # every beat instead of sticking on one (measured bug: 'abducens nerve' seven beats running)
    wc = _world_curiosity(timeline, len(timeline.all()))
    if wc is not None:
        concerns.append(wc)
    return concerns


def beat(workspace: Workspace, ledger: AgencyLedger,
         endocrine: Any | None = None, *, endogenous: bool = True,
         selfdev: Any | None = None, extra_concerns: list[Concern] | None = None) -> dict[str, Any]:
    """One heartbeat: sense -> feel -> compete -> speak inwardly -> record agency.

    L2 (feeling closed loop): the hormone field is DRIVEN by the loop itself, not injected — each
    beat decays the field, then the winning concern's nature moves it (a persisting self-deficit
    nudges cortisol; the world's novelty nudges dopamine), and the moved field weights the NEXT
    beat's competition. Feeling directs attention; attention reshapes feeling — closed.

    The broadcast is the winner VERBALIZED as first-person inner speech (inner_voice), so the ONE
    timeline reads as a stream of thought a person can follow."""
    from packages.neural_emotion.endocrine import Neuromodulators
    from .inner_voice import verbalize
    endo = endocrine if endocrine is not None else Neuromodulators()
    endo.decay()
    levels = dict(getattr(endo, "levels", {}) or {})

    tl = workspace.timeline
    concerns = _interoception(tl) + list(extra_concerns or [])   # self-repair findings re-enter here
    winner = workspace.compete(concerns, levels)
    if winner is None:
        return {"broadcast": None, "hormones": levels}
    repeats = workspace._recent[:-1].count(winner.content)
    speech = verbalize(winner, levels, repeats=repeats, beats=workspace._beats)
    # THE BOUND PRESENT (B1-deep + B4): the now is not an instant — bind the winning thought with
    # its feeling-tone and the perception in the air, flanked by retention (the just-past, fading)
    # and protention (what leans in: the runner-up concern that did not win THIS beat but pulls at
    # the next). A thick present with real temporal width, read from real state.
    from .present_moment import compose_moment
    runner_up = next((c.content for c in concerns if c is not winner), "")
    protention = runner_up.split(":", 1)[-1].strip()[:70] if runner_up else ""
    moment = compose_moment(tl, speech, levels, protention=protention)
    # MINENESS (B3-deep): this moment is given AS MINE — attributed to the one continuous self
    # (unbroken since birth) with its agency role (author / undergoer / witness). Every broadcast
    # passes through here, so the stream has exactly one owner: a life, not an anonymous log.
    from .mineness import own
    _own = own(speech, winner.source)
    tl.record("thought", speech, who="atanor",
              meta={"source": winner.source, "inner_voice": True, "endogenous": endogenous,
                    "workspace": True, "raw_concern": winner.content[:120],
                    "present_depth": moment.depth, "protention": moment.protention,
                    "percept_bound": bool(moment.percept), "feeling_tone": moment.feeling["tone"],
                    "mine": _own.mine, "mine_role": _own.role, "self_id": _own.self_id,
                    "hormones": {k: round(v, 2) for k, v in levels.items()
                                 if k in ("cortisol", "dopamine")}})
    # FEEL: the winner's nature moves the field (the loop's own hand on its endocrine system)
    try:
        if winner.meta.get("viability_threat"):
            # a threat to my continued existence is felt as survival stress, scaled by how real the
            # threat is right now — wanting-to-persist with a body behind it, not a label
            endo.sense("threat", 0.4 + 0.6 * float(winner.meta.get("threat", 0.5)))
        elif winner.source == "interoception":
            endo.sense("sustained_load", 0.25 + 0.5 * winner.viability)   # a live deficit weighs
            if repeats >= 2:
                # the RECOVERY VALVE (measured pathology: cortisol saturated at clamp under
                # persisting deficits with no relief). When habituation says "let it rest", resting
                # must be real: disengagement soothes — endorphin buffers, cortisol eases. This is
                # the same dynamic as human rumination-break, not a comfort label.
                endo.sense("recovery", 0.4)
        elif winner.source == "perception":
            endo.sense("social_contact", 0.6)                             # someone is here
            endo.sense("novelty", 0.4)
        elif winner.source == "curiosity":
            endo.sense("novelty", 0.25)
            endo.sense("wellbeing", 0.2)                                  # idle wondering is restful
    except Exception:
        pass
    arc = ledger.judged(speech[:160], why=f"won the workspace from {winner.source}")

    # SELF-DEVELOPMENT (owner: hormones -> self-evolution, like human 자기계발): an interoceptive
    # worry deposits its FELT load; when a theme's accumulated load crosses the commitment
    # threshold, the organism commits, practices through the gated organ, measures, and the
    # measured result moves the hormones (growth first, feeling second — anti-wireheading).
    development = None
    if selfdev is not None and winner.source == "interoception":
        theme = winner.content.replace("I notice a deficit: ", "").strip()[:60] \
            if winner.content.startswith("I notice a deficit: ") else winner.meta.get("theme", "")
        if theme:
            selfdev.felt_worry(theme, levels.get("cortisol", 0.0))
        due = selfdev.due_commitment()
        # the METABOLIC GOVERNOR gates the practice as REPAIR, not bulk work — a measured deadlock
        # forced this distinction: chronic worry kept cortisol high, and cortisol's load-shedding
        # deferred the very practice that would relieve it (too stressed to self-improve, forever).
        # Working on one's own deficit is what the stress response is FOR: always allowed, with the
        # governor scaling its intensity.
        if due is not None:
            from packages.neural_emotion.metabolic_governor import governs
            g = governs(dict(getattr(endo, "levels", {}) or {}), "repair")
            if g["allow"]:
                c = selfdev.commit_and_practice(due, endocrine=endo)
                announcement = selfdev.announce(c)
                from .mineness import own as _own_sd
                _osd = _own_sd(announcement, "self_development")
                tl.record("thought", announcement, who="atanor",
                          meta={"source": "self_development", "inner_voice": True,
                                "endogenous": endogenous, "workspace": True,
                                "outcome": c.outcome, "theme": c.theme,
                                "mine": True, "mine_role": _osd.role, "self_id": _osd.self_id})
                dev_arc = ledger.judged(f"commit to working on {c.theme}", why="accumulated felt load")
                ledger.acted(dev_arc, c.tried_roads[-1] if c.tried_roads else "", delivered=True)
                ledger.observed(dev_arc, f"severity {c.severity_before} -> {c.severity_after}")
                development = {"theme": c.theme, "outcome": c.outcome,
                               "announcement": announcement}
            else:
                development = {"deferred": due, "reason": "load_shedding"}

    return {"broadcast": speech, "source": winner.source, "arc": arc,
            "candidates": len(concerns), "development": development,
            "moment": {"as_lived": moment.as_lived(), "depth": moment.depth,
                       "feeling": moment.feeling, "protention": moment.protention,
                       "mine_role": _own.role, "mine_report": _own.report},
            "hormones": {k: round(v, 2) for k, v in (getattr(endo, "levels", {}) or {}).items()
                         if k in ("cortisol", "dopamine")}}


def run_burst(n_beats: int = 12, endocrine: Any | None = None,
              timeline: Timeline | None = None, selfdev: Any | None = None) -> dict[str, Any]:
    """A short live burst of the loop (for measurement/demo). Returns the stream + correlates +
    the hormone trace (the feeling loop, measured) + any self-development events."""
    from packages.neural_emotion.endocrine import Neuromodulators
    tl = timeline if timeline is not None else default_timeline()
    ws = Workspace(tl)
    ledger = AgencyLedger(tl)
    endo = endocrine if endocrine is not None else Neuromodulators()
    stream: list[str] = []
    hormone_trace: list[dict] = []
    developments: list[dict] = []
    for _ in range(n_beats):
        r = beat(ws, ledger, endo, selfdev=selfdev)
        if r.get("broadcast"):
            stream.append(f"[{r['source']}] {r['broadcast']}")
            hormone_trace.append(r.get("hormones") or {})
        if r.get("development"):
            developments.append(r["development"])
            if "announcement" in r["development"]:
                stream.append(f"[self_development] {r['development']['announcement']}")
    return {"stream": stream, "correlates": ws.correlates(),
            "causal_role": ledger.my_causal_role(), "hormone_trace": hormone_trace,
            "developments": developments}
