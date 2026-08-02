# -*- coding: utf-8 -*-
"""World-state tracker — the situation model's STATE organs (G3 extension, exposed by bAbI 0.127).

The first external exam we did not write (bAbI, strict 0.127) showed exactly which organs the
situation model lacks: it parsed events but kept no WORLD STATE — where each entity is, what it
holds, how places connect, what kinds inherit, why agents act. These are not benchmark hacks; they
are the state-update semantics any situation model needs (the reasoner's own comment admitted
"v0 does not extract locations, so it abstains").

Domain-blind by construction: a small lexicon of VERB FRAMES (motion, acquire, release, transfer,
copula) — lexical frames are the accepted floor (fluency doctrine: new predicates get frames;
Korean LAD precedent) — updates typed state. Rooms are identified BY USAGE (something travelled TO
them), not by a place lexicon. Kinds/properties come from the passage itself, never from the world
graph: situation-scoped knowledge only, so a wrong story is answered faithfully-to-the-story.

Epistemic honesty: definite state answers are grounded in the exact sentence (evidence kept);
disjunctive location answers "maybe"; peer-induction (a swan's colour from other swans) is tagged
induced=True — the caller may surface the hedge; anything untracked stays None => the reasoner
abstains as before.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

_SING_IRR = {"mice": "mouse", "wolves": "wolf", "geese": "goose", "sheep": "sheep",
             "children": "child", "people": "person", "cattle": "cow", "oxen": "ox"}
_NUM_WORD = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten"}
_DIRV = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0),
         "above": (0, 1), "below": (0, -1), "left": (-1, 0), "right": (1, 0)}
_DIR_LETTER = {"north": "n", "south": "s", "east": "e", "west": "w"}
_LEAD_CUE = re.compile(r"^(after that|following that|afterwards?|then|later|earlier|meanwhile|"
                       r"subsequently|finally|next|yesterday|this (?:morning|afternoon|evening))[,\s]+",
                       re.IGNORECASE)
_DAYPART_RANK = {"yesterday": 0, "this morning": 1, "this afternoon": 2, "this evening": 3}
_PRONOUN_ONE = {"he", "she", "it"}
_ART = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)

# ---- Theory-of-Mind surface frames (a small lexical set, fluency-doctrine floor) ----
# Presence timeline + belief tracking read the SAME sentences the reality frames read, but write a
# separate shadow. These frames only decide WHO witnessed WHAT; they never touch the reality organs.
_TOM_SUBJ = re.compile(r"^([A-Z][a-z']+(?:\s+and\s+[A-Z][a-z']+)*)\s+\w")   # 'A' or 'A and B' actors
_TOM_LEAVE = re.compile(r"\b(?:stepped\s+out|walked\s+out|went\s+outside|went\s+home|left)\b", re.I)
_TOM_MOTION = re.compile(r"\b(?:went|walked|moved|journeyed|travell?ed|came|ran|hurried|drove|flew)"
                         r"\s+(?:back\s+)?to\s+(?:the\s+)?([a-z][a-z']*)", re.I)
_TOM_PUTDOWN = re.compile(r"\b(?:put\s+down|dropped|placed|set\s+down|deposited)\s+"
                          r"(?:the\s+)?([a-z][a-z']*)", re.I)
# an object placement is stated with a LEADING article ('The gem was in the urn'); a leading capital
# name ('Ann was in the kitchen') is an AGENT taking a position, not an object being placed
_TOM_COPULA_PLACE = re.compile(r"^(?:the|a|an)\s+([a-z][a-z']*)\s+(?:is|was|are|were)\s+"
                               r"(?:in|at|on|inside)\s+(?:the\s+)?([a-z][a-z']*)\b", re.I)
_TOM_SCENE_IN = re.compile(r"\bin\s+(?:the\s+)?([a-z][a-z']*)\b", re.I)      # shared-scene name


def _sing(w: str) -> str:
    w = (w or "").lower().strip()
    if w in _SING_IRR:
        return _SING_IRR[w]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _np(s: str) -> str:
    """Normalize a noun phrase: drop articles, lowercase, collapse spaces."""
    return " ".join(_ART.sub("", (s or "").strip()).lower().split())


@dataclass
class Give:
    giver: str
    obj: str
    recipient: str
    order: int
    raw: str


@dataclass
class WorldState:
    loc: dict = field(default_factory=dict)          # entity -> current location
    not_loc: dict = field(default_factory=dict)      # entity -> set of excluded locations
    maybe_loc: dict = field(default_factory=dict)    # entity -> disjunctive candidate set
    traj: dict = field(default_factory=dict)         # entity -> [(timekey, loc, raw)]
    holding: dict = field(default_factory=dict)      # person -> [objects in acquisition order]
    holder_of: dict = field(default_factory=dict)    # object -> current holder ('' if released)
    obj_at: dict = field(default_factory=dict)       # object -> location where released
    gives: list = field(default_factory=list)        # Give records (three-arg relations)
    spatial_edges: list = field(default_factory=list)  # (a, dirname, b, raw): a is <dir> of b
    adj: dict = field(default_factory=dict)          # place -> [(neighbor, dir-letter)]
    bigger: list = field(default_factory=list)       # (big, small, raw) transitive order facts
    kinds: dict = field(default_factory=dict)        # instance -> kind
    kind_rel: dict = field(default_factory=dict)     # kind -> {relation-phrase: object}
    inst_adj: dict = field(default_factory=dict)     # instance -> [(order, adjective, raw)]
    motions: list = field(default_factory=list)      # (order, actor, destination) for motive queries
    acts: list = field(default_factory=list)         # (order, actor, object, raw) acquisitions
    rooms: set = field(default_factory=set)          # names used as motion destinations
    evidence: dict = field(default_factory=dict)     # entity -> last supporting sentence
    # --- Theory-of-Mind shadow (never read by the reality organs above) ---
    present: set = field(default_factory=set)         # agents currently in the active scene
    presence_log: list = field(default_factory=list)  # (order, agent, 'present'|'leave', raw)
    belief: dict = field(default_factory=dict)        # agent -> {entity: (loc, order, raw)}  (1st-order)
    belief2: dict = field(default_factory=dict)       # holder -> {subj: {entity: (loc, order, raw)}}
    agents: set = field(default_factory=set)          # names seen acting (belief-bearers)


class StateTracker:
    """Feed sentences in narrative order; query typed world state afterwards."""

    def __init__(self) -> None:
        self.w = WorldState()
        self._last_actors: list[str] = []            # for pronoun resolution (he/she -> [x], they -> group)
        self._had_daypart = False
        self._wloc: dict[str, str] = {}              # ToM: each agent's scene/location for co-presence

    # ---------- ingestion ----------

    def ingest(self, sentence: str, order: int) -> None:
        s = sentence.strip().rstrip(".!?")
        daypart = ""
        m = re.match(r"^(yesterday|this (?:morning|afternoon|evening))\s+", s, re.IGNORECASE)
        if not m:      # the cue may trail the clause ("Julie went to the park this afternoon")
            m = re.search(r"\s+(yesterday|this (?:morning|afternoon|evening))$", s, re.IGNORECASE)
        if m:
            daypart = m.group(1).lower()
            self._had_daypart = True
            s = (s[:m.start()] + " " + s[m.end():]).strip() if m.start() > 0 else s[m.end():].strip()
        s = _LEAD_CUE.sub("", s).strip()
        s = self._resolve_pronoun(s)
        timekey = (_DAYPART_RANK.get(daypart, 99), order)

        # ToM: update the presence timeline + belief shadow FIRST, unconditionally. It reads the same
        # sentence but writes only the shadow fields, so the reality frames below are untouched
        # whether or not any of them match (a copula placement short-circuits the frame loop — the
        # belief update must not depend on that).
        self._witness(s, order, sentence.strip())

        frames = (self._f_motion, self._f_copula_loc, self._f_disjunct, self._f_transfer,
                  self._f_acquire, self._f_release, self._f_spatial, self._f_comparative,
                  self._f_kind_rel, self._f_is_a, self._f_copula_adj)
        for frame in frames:
            if frame(s, order, timekey, sentence.strip()):
                return
        # SECOND PASS — nothing matched. Fragmented text drops the function words the frames key on
        # ('mary went kitchen', 'mary in the kitchen'), so put them back and try once more. Strictly
        # a fallback: a clean sentence has already matched above and never reaches this guess.
        from packages.situation_model.text_normalizer import (repair_function_words,
                                                              snap_to_frame_vocab)
        repaired = repair_function_words(snap_to_frame_vocab(s))
        if repaired != s:
            for frame in frames:
                if frame(repaired, order, timekey, sentence.strip()):
                    return

    def _resolve_pronoun(self, s: str) -> str:
        words = s.split()
        if not words:
            return s
        w0 = words[0].lower()
        if w0 in _PRONOUN_ONE and self._last_actors:
            return f"{self._last_actors[-1]} " + " ".join(words[1:])
        if w0 == "they" and self._last_actors:
            return f"{' and '.join(self._last_actors)} " + " ".join(words[1:])
        return s

    def _set_actors(self, subj: str) -> list[str]:
        actors = [_np(a) for a in re.split(r"\s+and\s+", subj) if _np(a)]
        if actors:
            self._last_actors = actors
        return actors

    def _move(self, actor: str, dest: str, timekey, raw: str) -> None:
        w = self.w
        w.loc[actor] = dest
        w.not_loc.pop(actor, None)
        w.maybe_loc.pop(actor, None)
        w.traj.setdefault(actor, []).append((timekey, dest, raw))
        for held in w.holding.get(actor, []):         # possessions travel with their holder
            w.traj.setdefault(held, []).append((timekey, dest, raw))
        w.rooms.add(dest)
        w.evidence[actor] = raw
        w.motions.append((timekey[1], actor, dest))

    # ---------- Theory-of-Mind: presence timeline + per-agent belief (witnessed-only) ----------
    # A world-state tracker follows REALITY (loc); a mind-reader must also follow what each agent has
    # SEEN. belief[agent][entity] is a shadow of loc that updates only when the agent is co-present
    # with the placement, so an UNWITNESSED move makes belief diverge from reality — and that
    # divergence is the false belief. Everything here is additive; the reality organs never read it.

    def _witness(self, s: str, order: int, raw: str) -> None:
        if not s:
            return
        w = self.w
        # (1) leading subject agents: capitalized names ('A', 'A and B'); never an article/object
        subj: list[str] = []
        ms = _TOM_SUBJ.match(s)
        if ms:
            for nm in re.split(r"\s+and\s+", ms.group(1)):
                k = _np(nm)
                if k and k not in {"the", "a", "an"}:
                    subj.append(k)
                    w.agents.add(k)
        leaving = bool(_TOM_LEAVE.search(s))
        # (2) presence timeline + each agent's scene/location (for later co-presence tests)
        if subj:
            if leaving:
                for a in subj:
                    w.present.discard(a)
                    w.presence_log.append((order, a, "leave", raw))
            else:
                mo = _TOM_MOTION.search(s)
                sc = None if mo else _TOM_SCENE_IN.search(s)
                where = _np(mo.group(1)) if mo else (_np(sc.group(1)) if sc else None)
                for a in subj:
                    w.present.add(a)
                    if where:
                        self._wloc[a] = where
                    w.presence_log.append((order, a, "present", raw))
        # (3) object-placement events -> update belief for whoever was co-present
        actor = subj[0] if (subj and not leaving) else None
        pm = _TOM_PUTDOWN.search(s)
        if pm and actor:                          # agent-carry: 'P put down the O' (O lands at P's loc)
            obj, loc = _np(pm.group(1)), self._wloc.get(actor)
            if obj and loc and obj not in w.agents:
                self._register_belief(obj, loc, order, actor, raw)
            return
        cm = _TOM_COPULA_PLACE.match(s)
        if cm:                                    # copula: 'The O was in the L' (whole scene sees it)
            ent, loc = _np(cm.group(1)), _np(cm.group(2))
            if ent and loc and ent not in w.agents:
                self._register_belief(ent, loc, order, None, raw)

    def _register_belief(self, entity: str, loc: str, order: int, actor, raw: str) -> None:
        """A placement of `entity` at `loc` is witnessed by the agents co-present at that instant: the
        whole scene for a copula placement (actor is None), or the acting agent plus anyone standing
        at the same location for an agent-carry placement. Each witness's first-order belief is set to
        loc; every co-present PAIR also fixes the second-order belief (each sees the other see it).
        Absent agents keep their stale belief — that retained value is the divergence from reality."""
        w = self.w
        if actor is None:
            witnesses = set(w.present)
        else:
            witnesses = {actor} | {a for a in w.present if self._wloc.get(a) == loc}
        for a in witnesses:
            w.belief.setdefault(a, {})[entity] = (loc, order, raw)
        ordered = sorted(witnesses)
        for a in ordered:
            for b in ordered:
                if a != b:
                    w.belief2.setdefault(a, {}).setdefault(b, {})[entity] = (loc, order, raw)

    def believes(self, agent: str, entity: str) -> tuple[str, str] | None:
        """First-order: where does `agent` think `entity` is? -> (loc, evidence), or None to abstain
        (the agent was never co-present with the entity, so its belief is ungrounded)."""
        rec = self.w.belief.get(_np(agent), {}).get(_np(entity))
        return (rec[0], rec[2]) if rec else None

    def believes_second(self, holder: str, subject: str, entity: str) -> tuple[str, str] | None:
        """Second-order: where does `holder` think `subject` will look for `entity`? -> (loc, ev) or
        None. Grounded only when `holder` actually witnessed `subject` observing the entity (both
        co-present at a placement); otherwise `holder` has no model of `subject`'s belief -> abstain."""
        rec = self.w.belief2.get(_np(holder), {}).get(_np(subject), {}).get(_np(entity))
        return (rec[0], rec[2]) if rec else None

    # frame: <A[ and B]> went|moved|journeyed|... [back] to the <L>
    def _f_motion(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:went|moved|journeyed|travell?ed|came|ran|walked|hurried|drove|"
                     r"flew)\s+(?:back\s+)?to\s+(?:the\s+)?(.+)$", s, re.IGNORECASE)
        if not m:
            return False
        for actor in self._set_actors(m.group(1)):
            self._move(actor, _np(m.group(2)), timekey, raw)
        return True

    # frame: <S> is|was [not|no longer] in|at the <L>
    def _f_copula_loc(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:is|was)\s+(no longer\s+|not\s+)?(?:in|at)\s+(?:the\s+)?(.+)$",
                     s, re.IGNORECASE)
        if not m:
            return False
        neg, place = bool(m.group(2)), _np(m.group(3))
        for actor in self._set_actors(m.group(1)):
            if neg:
                self.w.not_loc.setdefault(actor, set()).add(place)
                if self.w.loc.get(actor) == place:
                    del self.w.loc[actor]
                self.w.evidence[actor] = raw
            else:
                self._move(actor, place, timekey, raw)
        return True

    # frame: <S> is either in the <A> or the <B>
    def _f_disjunct(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:is|was)\s+either\s+in\s+(?:the\s+)?(.+?)\s+or\s+(?:the\s+)?(.+)$",
                     s, re.IGNORECASE)
        if not m:
            return False
        for actor in self._set_actors(m.group(1)):
            self.w.maybe_loc[actor] = {_np(m.group(2)), _np(m.group(3))}
            self.w.loc.pop(actor, None)
            self.w.evidence[actor] = raw
        return True

    # frame: <S> gave|handed|passed the <O> to <R>   /   <S> gave <R> the <O>
    def _f_transfer(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:gave|handed|passed)\s+(?:the\s+)?(.+?)\s+to\s+(.+)$",
                     s, re.IGNORECASE)
        giver = obj = rec = None
        if m:
            giver, obj, rec = _np(m.group(1)), _np(m.group(2)), _np(m.group(3))
        else:
            m = re.match(r"^(.+?)\s+(?:gave|handed|passed)\s+([A-Z]\w*)\s+the\s+(.+)$", s)
            if not m:
                return False
            giver, rec, obj = _np(m.group(1)), _np(m.group(2)), _np(m.group(3))
        w = self.w
        if giver in w.holding and obj in w.holding[giver]:
            w.holding[giver].remove(obj)
        w.holding.setdefault(rec, []).append(obj)
        w.holder_of[obj] = rec
        w.obj_at.pop(obj, None)
        w.gives.append(Give(giver, obj, rec, order, raw))
        w.evidence[obj] = raw
        self._set_actors(giver)
        return True

    # frame: <S> took|picked up|got|grabbed the <O>
    def _f_acquire(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:took|picked\s+up|got|grabbed)\s+(?:the\s+)?(.+)$",
                     s, re.IGNORECASE)
        if not m:
            return False
        actors = self._set_actors(m.group(1))
        obj = _np(re.sub(r"\s+(?:there|from\s+.*)$", "", m.group(2), flags=re.IGNORECASE))
        if not actors:
            return False
        holder = actors[0]
        self.w.holding.setdefault(holder, []).append(obj)
        self.w.holder_of[obj] = holder
        self.w.obj_at.pop(obj, None)
        if holder in self.w.loc:                      # the object is now wherever its holder is
            tr = self.w.traj.setdefault(obj, [])
            if not tr or tr[-1][1] != self.w.loc[holder]:
                tr.append((timekey, self.w.loc[holder], raw))
        self.w.evidence[obj] = raw
        self.w.acts.append((timekey[1], holder, obj, raw))
        return True

    # frame: <S> dropped|discarded|put down|left the <O>  (O must not be a known room — 'left the
    # office' is motion-out, not release; and 'left' must not swallow the spatial 'to the left of')
    def _f_release(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:dropped|discarded|put\s+down|left(?!\s+of\b))\s+(?:the\s+)?(.+)$",
                     s, re.IGNORECASE)
        if not m:
            return False
        obj = _np(re.sub(r"\s+there$", "", m.group(2), flags=re.IGNORECASE))
        if obj in self.w.rooms:
            return False
        actors = self._set_actors(m.group(1))
        if not actors:
            return False
        holder = actors[0]
        if holder in self.w.holding and obj in self.w.holding[holder]:
            self.w.holding[holder].remove(obj)
        self.w.holder_of[obj] = ""
        if holder in self.w.loc:
            self.w.obj_at[obj] = self.w.loc[holder]
        self.w.evidence[obj] = raw
        return True

    # frame: The <A> is <dir> of the <B> — stored as an edge CONSTRAINT; coordinates are computed
    # lazily per connected component at query time (assigning ad-hoc origins at ingest time gave
    # garbage cross-component comparisons — measured at chance on positional yes/no)
    def _f_spatial(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:is|was)\s+(?:to\s+the\s+)?(north|south|east|west|left|right)"
                     r"\s+of\s+(?:the\s+)?(.+)$", s, re.IGNORECASE)
        if not m:      # above/below take a bare object ('the triangle is above the rectangle')
            m = re.match(r"^(.+?)\s+(?:is|was)\s+(above|below)\s+(?:of\s+)?(?:the\s+)?(.+)$",
                         s, re.IGNORECASE)
        if not m:
            return False
        a, d, b = _np(m.group(1)), m.group(2).lower(), _np(m.group(3))
        w = self.w
        w.spatial_edges.append((a, d, b, raw))
        if d in _DIR_LETTER:
            w.adj.setdefault(a, []).append((b, _DIR_LETTER[{"north": "south", "south": "north",
                                                            "east": "west", "west": "east"}[d]]))
            w.adj.setdefault(b, []).append((a, _DIR_LETTER[d]))
        w.evidence[a] = raw
        return True

    def _coords(self) -> dict[str, tuple]:
        """BFS coordinate assignment per connected component; nodes carry a component id so queries
        can refuse cross-component comparisons (abstain instead of fabricating a relation)."""
        neigh: dict[str, list] = {}
        for a, d, b, _ in self.w.spatial_edges:
            vx, vy = _DIRV[d]
            neigh.setdefault(a, []).append((b, -vx, -vy))
            neigh.setdefault(b, []).append((a, vx, vy))
        out: dict[str, tuple] = {}
        comp = 0
        for start in neigh:
            if start in out:
                continue
            comp += 1
            out[start] = (comp, 0, 0)
            q = deque([start])
            while q:
                cur = q.popleft()
                _, cx, cy = out[cur]
                for nb, dx, dy in neigh.get(cur, []):
                    if nb not in out:
                        out[nb] = (comp, cx + dx, cy + dy)
                        q.append(nb)
        return out

    # frame: <Ks> are afraid of <X>  (bare-plural subject => kind-level relation; the plural may be
    # irregular — 'mice', 'wolves' — so any single word before 'are' qualifies, singularized)
    def _f_kind_rel(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^([A-Za-z]+)\s+are\s+(afraid\s+of|scared\s+of)\s+(?:the\s+)?(.+)$",
                     s, re.IGNORECASE)
        if not m:
            return False
        kind = _sing(m.group(1))
        self.w.kind_rel.setdefault(kind, {})["afraid of"] = _sing(_np(m.group(3)))
        self.w.evidence[kind] = raw
        return True

    # frame: <A> is bigger|smaller than <B>  /  <A> fits inside <B> — a transitive order relation
    def _f_comparative(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:is|was)\s+(bigger|larger|smaller)\s+than\s+(?:the\s+)?(.+)$",
                     s, re.IGNORECASE)
        if m:
            a, rel, b = _np(m.group(1)), m.group(2).lower(), _np(m.group(3))
            big, small = (a, b) if rel in ("bigger", "larger") else (b, a)
            self.w.bigger.append((big, small, raw))
            return True
        m = re.match(r"^(.+?)\s+fits?\s+(?:inside|in)\s+(?:the\s+)?(.+)$", s, re.IGNORECASE)
        if m:      # 'A fits inside B' entails B is bigger than A
            self.w.bigger.append((_np(m.group(2)), _np(m.group(1)), raw))
            return True
        return False

    # frame: <P> is a <K>
    def _f_is_a(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^([A-Z]\w*)\s+is\s+a\s+([a-z]\w*)$", s)
        if not m:
            return False
        inst = _np(m.group(1))
        self.w.kinds[inst] = _sing(m.group(2))
        self.w.evidence[inst] = raw
        return True

    # frame: <P> is <adjective>  (single word: colour, feeling, size-class — query decides meaning)
    def _f_copula_adj(self, s, order, timekey, raw) -> bool:
        m = re.match(r"^(.+?)\s+(?:is|was|are|were)\s+([a-z]+)$", s, re.IGNORECASE)
        if not m:
            return False
        adj = m.group(2).lower()
        if adj in {"a", "an", "the", "in", "at", "there", "here", "not"}:
            return False
        for actor in self._set_actors(m.group(1)):
            self.w.inst_adj.setdefault(actor, []).append((order, adj, raw))
            self.w.evidence[actor] = raw
        return True

    # ---------- queries (None => the caller abstains) ----------

    def where_is(self, ent: str) -> tuple[str, str] | None:
        """Current location of an entity or a held/released object. -> (answer, evidence)"""
        w = self.w
        e = _np(ent)
        if e in w.loc:
            return w.loc[e], w.evidence.get(e, "")
        holder = w.holder_of.get(e)
        if holder:
            seen = {e}
            while holder and holder in w.holder_of and holder not in seen:   # chains, defensively
                seen.add(holder)
                holder = w.holder_of[holder]
            if holder and holder in w.loc:
                return w.loc[holder], w.evidence.get(e, "")
        if e in w.obj_at:
            return w.obj_at[e], w.evidence.get(e, "")
        return None

    def where_was(self, ent: str, ref: str, before: bool) -> tuple[str, str] | None:
        """Location before/after the entity was at `ref` (trajectory scan, daypart-aware)."""
        e = _np(ent)
        tr = sorted(self.w.traj.get(e, []))
        stops = [loc for _, loc, _ in tr]
        r = _np(ref)
        if r not in stops:
            return None
        # 'before the X' refers to the MOST RECENT stay at X (measured: first-occurrence indexing
        # abstained whenever the entity revisited a place); 'after the X' to the first stay
        i = (len(stops) - 1 - stops[::-1].index(r)) if before else stops.index(r)
        j = i - 1 if before else i + 1
        if 0 <= j < len(stops):
            return stops[j], tr[j][2]
        return None

    def loc_yesno(self, ent: str, place: str) -> tuple[str, str] | None:
        w = self.w
        e, p = _np(ent), _np(place)
        if e in w.loc:
            return ("yes" if w.loc[e] == p else "no"), w.evidence.get(e, "")
        if p in w.not_loc.get(e, set()):
            return "no", w.evidence.get(e, "")
        if e in w.maybe_loc:
            return ("maybe" if p in w.maybe_loc[e] else "no"), w.evidence.get(e, "")
        return None

    def holdings(self, person: str) -> list[str] | None:
        p = _np(person)
        if p in self.w.holding:
            return list(self.w.holding[p])
        if p in self.w.loc:            # a tracked actor who never acquired anything holds nothing
            return []
        return None

    def spatial_what(self, direction: str, anchor: str, inverse: bool) -> tuple[str, str] | None:
        """'What is <dir> of the X?' (inverse=False) / 'What is the X <dir> of?' (inverse=True) —
        answered from DIRECT stated edges first (that is what the question asks), never composed."""
        d = direction.lower()
        opp = {"north": "south", "south": "north", "east": "west", "west": "east",
               "above": "below", "below": "above", "left": "right", "right": "left"}.get(d)
        a = _np(anchor)
        for ea, ed, eb, raw in reversed(self.w.spatial_edges):
            if not inverse:                        # 'what is d of A' <= 'X is d of A' | 'A is opp of X'
                if ed == d and eb == a:
                    return ea, raw
                if ed == opp and ea == a:
                    return eb, raw
            else:                                  # 'what is A d of' <= 'A is d of X' | 'X is opp of A'
                if ed == d and ea == a:
                    return eb, raw
                if ed == opp and eb == a:
                    return ea, raw
        return None

    def pos_yesno(self, a: str, direction: str, b: str) -> tuple[str, str] | None:
        """'Is the A <dir> of the B?' by lazily-BFS'd coordinates; cross-component comparisons
        abstain (there is no stated chain connecting them — answering would be fabrication)."""
        d = direction.lower()
        if d not in _DIRV:
            return None
        coords = self._coords()
        pa, pb = coords.get(_np(a)), coords.get(_np(b))
        if pa is None or pb is None or pa[0] != pb[0]:
            return None
        dx, dy = pa[1] - pb[1], pa[2] - pb[2]
        vx, vy = _DIRV[d]
        ok = (dx * vx > 0) if vx else (dy * vy > 0)
        return ("yes" if ok else "no"), ""

    def size_yesno(self, a: str, rel: str, b: str) -> tuple[str, str] | None:
        """'Is the A bigger/smaller than the B?' / 'does the A fit in the B?' over the transitive
        closure of stated order facts; no path either way => abstain."""
        big_of: dict[str, set] = {}
        for big, small, _ in self.w.bigger:
            big_of.setdefault(big, set()).add(small)

        def bigger_than(x: str, y: str) -> bool:
            q, seen = deque([x]), {x}
            while q:
                cur = q.popleft()
                for s in big_of.get(cur, ()):
                    if s == y:
                        return True
                    if s not in seen:
                        seen.add(s)
                        q.append(s)
            return False

        x, y = _np(a), _np(b)
        want_bigger = rel in ("bigger", "larger")
        if rel == "fit":                            # A fits in B  <=>  B is bigger than A
            x, y, want_bigger = y, x, True
        if bigger_than(x, y):
            return ("yes" if want_bigger else "no"), ""
        if bigger_than(y, x):
            return ("no" if want_bigger else "yes"), ""
        return None

    def path(self, src: str, dst: str) -> tuple[str, str] | None:
        """BFS over direct adjacency; answer as direction letters 'n,e'."""
        s, t = _np(src), _np(dst)
        if s not in self.w.adj:
            return None
        q, seen = deque([(s, [])]), {s}
        while q:
            cur, steps = q.popleft()
            if cur == t:
                return ",".join(steps), ""
            for nb, letter in self.w.adj.get(cur, []):
                if nb not in seen:
                    seen.add(nb)
                    q.append((nb, steps + [letter]))
        return None

    def kind_relation(self, inst: str, relation: str) -> tuple[str, str] | None:
        """Inherit a kind-level relation for an instance ('what is gertrude afraid of')."""
        k = self.w.kinds.get(_np(inst))
        if k and relation in self.w.kind_rel.get(k, {}):
            return self.w.kind_rel[k][relation], self.w.evidence.get(k, "")
        return None

    def induced_adjective(self, inst: str) -> tuple[str, str, bool] | None:
        """Colour-style property: stated for the instance (induced=False) or induced from same-kind
        peers, most-recent first (induced=True — epistemic hedge is the caller's duty)."""
        e = _np(inst)
        if e in self.w.inst_adj:
            o, adj, raw = self.w.inst_adj[e][-1]
            return adj, raw, False
        k = self.w.kinds.get(e)
        if not k:
            return None
        peers = [p for p, pk in self.w.kinds.items() if pk == k and p != e and p in self.w.inst_adj]
        votes: dict[str, int] = {}
        last_raw = ""
        for p in peers:
            _, adj, raw = self.w.inst_adj[p][-1]
            votes[adj] = votes.get(adj, 0) + 1
            last_raw = raw
        if not votes:
            return None
        best = max(votes, key=lambda a: (votes[a],))
        return best, last_raw, True

    def motive(self, actor: str, dest: str) -> tuple[str, str] | None:
        """'Why did X go to the L?' -> X's last stated state-adjective before that motion."""
        a, d = _np(actor), _np(dest)
        move_order = None
        for order, who, where in self.w.motions:
            if who == a and where == d:
                move_order = order
        if move_order is None:
            return None
        return self._state_before(a, move_order)

    def motive_get(self, actor: str, obj: str) -> tuple[str, str] | None:
        """'Why did X get the O?' -> X's last stated state-adjective before that acquisition."""
        a, o = _np(actor), _np(obj)
        for order, who, what, _ in reversed(self.w.acts):
            if who == a and what == o:
                return self._state_before(a, order)
        return None

    def _state_before(self, actor: str, order: int) -> tuple[str, str] | None:
        prior = [(o, adj, raw) for o, adj, raw in self.w.inst_adj.get(actor, []) if o < order]
        if not prior:
            return None
        _, adj, raw = prior[-1]
        return adj, raw

    def predicted_destination(self, actor: str) -> tuple[str, str, bool] | None:
        """'Where will X go?' -> destination another agent with the same last state went to
        (in-story induction; tagged induced=True)."""
        a = _np(actor)
        states = self.w.inst_adj.get(a, [])
        if not states:
            return None
        my_state = states[-1][1]
        for order, who, where in self.w.motions:
            m = self.motive(who, where)
            if m and m[0] == my_state:
                return where, m[1], True
        return None

    def count_word(self, n: int) -> str:
        return _NUM_WORD.get(n, str(n))


def track(sentences: list[str]) -> StateTracker:
    t = StateTracker()
    for i, s in enumerate(sentences):
        t.ingest(s, i)
    return t
