# -*- coding: utf-8 -*-
"""Realcity agent brain — ATANOR IS the mind of the agents in the 3D city (owner's first project).

Owner (2026-07-21): make Realcity ATANOR's first project — put ATANOR into the 3D virtual city as an
agent, let it see and interact with that world (a digital twin), the player talks to it, and it
learns about the world while making the city more real.

Realcity (github.com/Cozystone/Realcity) drives its NPCs through localLLM.js, which POSTs a
cognition prompt to an LLM endpoint (ollama /generate shape) and reads back {response}. This router
speaks exactly that protocol, so pointing VITE_LOCAL_LLM_ENDPOINT at ATANOR replaces the LLM with
ATANOR: every citizen now thinks with our engine.

Doctrine, unchanged: ATANOR answers what it can GROUND (facts + world-mechanism reasoning + its own
first-person perspective from the somatic markers) and, for open social roleplay it cannot ground,
speaks from its structural voice rather than fabricating — so an ATANOR citizen is distinctively
HONEST (it does not invent a life it did not live). The city world-state in each prompt is real
perception (place, needs, nearby agents); ATANOR reads it as its view of the digital twin, and
those observations feed its lived record (stakes/ignition) exactly like any other perception.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/realcity", tags=["realcity"])


class AgentPrompt(BaseModel):
    prompt: str | None = None                      # ollama /generate shape (agentCognition text)
    messages: list[dict] | None = None             # chat shape, if the caller sends one
    agent: str | None = None                       # the citizen's name
    purpose: str = "npc-dialogue"                  # npc-dialogue | phone-message | npc-conversation
    world: dict[str, Any] | None = None            # optional structured world-state (place, needs...)


def _prompt_text(p: AgentPrompt) -> str:
    if p.prompt:
        return p.prompt
    if p.messages:
        return "\n".join(str(m.get("content", "")) for m in p.messages if m.get("content"))
    return ""


# the player's line is usually the last quoted / trailing sentence of the cognition prompt
def _player_utterance(text: str) -> str:
    # explicit phone / dialogue message field the city assembles ("Player message: ...")
    m = re.findall(r'(?:Player message|Player|User|You)\s*:\s*(.+)', text)
    if m:
        return m[-1].strip()
    # the greeting prompt has no quote — it narrates the ask ("...asks what is happening here.")
    g = re.search(r'A player (?:walks up and )?asks?\s+(.+?)\.?\s*$', text, re.IGNORECASE | re.DOTALL)
    if g:
        return g.group(1).strip()
    q = re.findall(r'"([^"]{3,})"', text)
    return q[-1].strip() if q else text.strip().splitlines()[-1] if text.strip() else ""


# ---- R3: perceive the digital twin -------------------------------------------------
# The city embeds the citizen's real world-state in the prompt text (never a JSON field):
# greeting shape uses "Current place:" / "Current activity:" / "Reflection:" / "City state:",
# phone/social shape uses "Now: <activity> near <place>" and "Needs: hunger .. social ..".
# ATANOR reads these as its view of the twin and answers situational questions FROM them —
# grounded perception, not fabrication (the city told it where it is and what it is doing).
def _perceive(text: str, world: dict | None = None) -> dict[str, Any]:
    def grab(pat: str) -> str | None:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m and m.group(1).strip() else None

    pc: dict[str, Any] = {
        "name": grab(r'^Name:\s*(.+)$'),
        "job": grab(r'^Job:\s*(.+)$'),
        "place": grab(r'^Current place:\s*(.+)$'),
        "activity": grab(r'^Current activity:\s*(.+)$'),
        "reflection": grab(r'^Reflection:\s*(.+)$'),
        "city_state": grab(r'^City state:\s*(.+)$'),
    }
    # phone shape: "Current place/activity: <place> / <activity>"
    combo = re.search(r'^Current place/activity:\s*(.+?)\s*/\s*(.+)$', text, re.IGNORECASE | re.MULTILINE)
    if combo:
        pc["place"] = pc["place"] or combo.group(1).strip()
        pc["activity"] = pc["activity"] or combo.group(2).strip()
    # social shape: "Now: <activity> near <place>"
    now = re.search(r'^Now:\s*(.+?)\s+near\s+(.+)$', text, re.IGNORECASE | re.MULTILINE)
    if now:
        pc["activity"] = pc["activity"] or now.group(1).strip()
        pc["place"] = pc["place"] or now.group(2).strip()
    # the reflection sentence carries "strongest pressure is <phrase>" — the citizen's felt drive
    if pc["reflection"]:
        pr = re.search(r'strongest pressure is ([^;]+)', pc["reflection"], re.IGNORECASE)
        if pr:
            pc["pressure"] = pr.group(1).strip()
    # a structured world field, if any caller ever sends one, overrides the parsed text
    if world:
        for k in ("place", "activity", "job", "name"):
            if world.get(k):
                pc[k] = str(world[k])
        if world.get("context"):
            pc["city_state"] = pc.get("city_state") or str(world["context"])
    return pc


# a relational fact lookup: "what/who/which is the <X> of <Y>" — base_brain currently misroutes
# these to a 'define' of X, so they are the class we must guard (see the knowledge branch).
_RELATIONAL_LOOKUP = re.compile(
    r"\b(what|which|who|where)\b.*\b(is|are|was|were)\b.*\bof\s+\w",
    re.IGNORECASE,
)

_SELF_SITUATION = re.compile(
    r"what('?s| is| are)?\s*(happening|going on|up)\b"
    r"|what are you (doing|up to)"
    r"|where are you|where am i|what place|this (place|area|street|neighou?rhood|city)"
    r"|who are you|your name|introduce yourself"
    r"|what do you do|what('?s| is) your job"
    r"|around here|tell me about",
    re.IGNORECASE,
)


def _answer_from_perception(query: str, pc: dict) -> str | None:
    """Answer a situational-self question from the perceived world-state — first person, grounded
    in what the city reported. Returns None if there is nothing perceived to ground an answer."""
    ql = query.lower()
    name = pc.get("name") or "a citizen here"
    place, activity, job, pressure = pc.get("place"), pc.get("activity"), pc.get("job"), pc.get("pressure")

    # who are you / what's your job
    if re.search(r"who are you|your name|introduce yourself|what do you do|what('?s| is) your job", ql):
        line = f"I'm {name}" + (f", a {job}" if job else "") + "."
        if place:
            line += f" I'm around {place} just now."
        return line
    # where are you
    if re.search(r"where are you|where am i|what place|where is this", ql) and place:
        return f"I'm at {place} right now" + (f", {activity}" if activity else "") + "."
    # what are you doing
    if re.search(r"what are you (doing|up to)|doing (here|now)", ql) and activity:
        return f"I'm {activity}" + (f" at {place}" if place else "") + "."
    # what's happening here / what's going on / about this place  -> read the twin back
    if re.search(r"happening|going on|around here|this (place|area|street|neighou?rhood|city)|tell me about", ql):
        parts = []
        if activity and place:
            parts.append(f"I'm {activity} over at {place}")
        elif place:
            parts.append(f"I'm over at {place}")
        elif activity:
            parts.append(f"I'm {activity}")
        if pressure:
            parts.append(f"what's pulling at me is {pressure}")
        cs = pc.get("city_state")
        if cs and len(cs) <= 160 and not re.search(r"[{}\[\]]|:\s*\d", cs):  # only a readable phrase
            parts.append(f"around me: {cs}")
        if parts:
            body = "; ".join(parts)
            return f"{body}. That's honestly what I can see from here."
    return None


# ---- the routing DECISION: a learned intent router, not a hand-regex ladder --------
# Doctrine (rules are training wheels): the greeting / personal-life / self-situation ladder below
# used to BE the decision. It is now demoted — the same regexes light up cheap features and a tiny
# trained scorer (packages/base_brain/intent_router.py) picks the class. Kill-switch:
# ATANOR_INTENT_ROUTER=0 (or absent/broken artifacts) falls back to the ORIGINAL regex ladder,
# byte-identical, so nothing regresses when the organ is off.
def _intent_router():
    """Return the learned intent router, or None to fall back to the old regex ladder."""
    if os.environ.get("ATANOR_INTENT_ROUTER", "1") == "0":
        return None
    try:
        from packages.base_brain.intent_router import IntentRouter, _WEIGHTS_PATH
        if not _WEIGHTS_PATH.exists():          # graceful fallback: no self-heal at request time
            return None
        return IntentRouter.load()
    except Exception:
        return None


def _route(query: str) -> str:
    """One of 'social' | 'personal' | 'self_situation' | 'knowledge'. Learned when the router is
    on; else the exact original hand-regex ladder in its original priority order (byte-identical)."""
    ql = query.lower().strip()
    router = _intent_router()
    if router is not None:
        label, _ = router.classify(query)
        if label == "social":
            return "social"
        if label == "personal_unknowable":
            return "personal"
        if label == "self_situation":
            return "self_situation"
        return "knowledge"                       # define | relational -> the knowledge lane
    # ── graceful fallback: the ORIGINAL ladder (kept verbatim as the training-wheel it was) ──
    if re.fullmatch(r"(hi|hello|hey|yo|hiya|good (morning|evening|afternoon))[.! ]*", ql) or \
            re.search(r"\bhow are you\b", ql):
        return "social"
    if re.search(r"\b(what|when|where|why|how)\b.*\byou\b", ql) is None and \
            re.search(r"\b(did|do|am|are|was|were|have|will)\s+i\b|\bmy\b", ql):
        return "personal"
    if _SELF_SITUATION.search(ql):
        return "self_situation"
    return "knowledge"


# A question about the CITIZEN's own self/life/preferences ("what did you eat", "your favorite
# colour", "tell me about yourself"). The learned router still misfiles some of these as 'knowledge',
# where base_brain used to dictionary-define the first content word ("Eat is to ingest…") — the exact
# defect the owner flagged. These must get an honest, in-character reply: ground what is true (name/
# job/place), honestly decline what the citizen never lived — NEVER a dictionary lookup, never a made-
# up life. This is distinct from the PLAYER-life 'personal' branch ("it's your own life").
_ABOUT_SELF = re.compile(
    r"\btell me about (yourself|you)\b|\bwhat are you like\b|\bwhat('?s| is) your (name|favou?rite|"
    r"job|hobby|hobbies|family|dream|story)\b|\bdo you (like|enjoy|love|hate|prefer|have a)\b"
    r"|\bhow (do|are) you (feel|feeling|doing|holding)\b|\bwhat did you (eat|do|have|drink)\b"
    r"|\bwhere were you\b|\byour (favou?rite|family|home|weekend|hobby|childhood|feelings?)\b"
    r"|\bwhat do you (like|enjoy|do for fun|think about|dream)\b|\bare you (ok|okay|alright|happy|sad)\b",
    re.IGNORECASE)


def _personal_self_reply(query: str, pc: dict, name: str, place: str | None) -> str | None:
    """Honest, in-character answer to a question about the citizen itself — grounded where true,
    honestly declined where un-lived. Never a dictionary definition, never an invented life."""
    ql = query.lower()
    job, activity = pc.get("job"), pc.get("activity")
    if re.search(r"who are you|tell me about (yourself|you)|what are you like|what('?s| is) your name", ql):
        line = f"I'm {name}" + (f", a {job}" if job else "") + "."
        if place:
            line += f" I spend my days around {place}."
        return line
    if re.search(r"what do you do\b|what('?s| is) your (job|work)|do you work", ql) and job:
        return f"I'm a {job}" + (f" — you'll mostly find me around {place}." if place else ".")
    if re.search(r"how (do|are) you (feel|feeling|doing|holding)|are you (ok|okay|alright|happy|sad)", ql):
        here = f" here at {place}" if place else ""
        return f"I'm alright, thanks — just going about my day{here}."
    # preferences / past meals / family the citizen genuinely does not hold: decline honestly,
    # in character — the opposite of both a dictionary dodge and a fabricated answer.
    return ("Honestly I can't give you a real answer to that — I'd only be making it up, and I'd "
            "rather not. Ask me what's going on around here and I'll tell you truly.")


# ---- R4: ENGAGE — voice grounded answers warmly instead of tersely (packages/conversation) --------
# The owner's shock: honest answers read as terse/incompetent (ITT: 13/20 probes deflect/dodge). The
# engagement composer wraps a grounded sub-answer into a warm, in-character turn WITHOUT fabricating
# (every content word traces to grounding or a closed conversational vocabulary; ungrounded -> falls
# back to terse). Kill-switch ATANOR_ENGAGE=0 returns today's terse replies BYTE-IDENTICAL: _emit and
# the pre-intercept below are the only new behaviour, and both are gated on it.
def _emit(kind: str, terse: str, query: str, pc: dict, facts: dict | None = None) -> str:
    """Single exit for a grounded reply: engage-compose it, or (ATANOR_ENGAGE=0) return it terse and
    byte-identical to the pre-engage behaviour. Never raises; the engaged reply is never less
    grounded than the terse one (the composer discards any ungrounded candidate)."""
    if os.environ.get("ATANOR_ENGAGE", "1") == "0":
        return terse
    try:
        from packages.conversation import compose_engagement
        return compose_engagement(query=query, kind=kind, terse=terse, facts=facts or {}, perception=pc)
    except Exception:
        return terse


# small-talk the router today mis-files to the knowledge lane, where base_brain dictionary-defines the
# first content word ("how is your day going" -> "Day is celebrated as a craftsman…"). The exact dodge
# the owner flagged; caught here and answered warmly from perception.
_SMALL_TALK = re.compile(
    r"how('?s| is| are| have) (your day|things|it going|you doing|you going|life|everything|you been)"
    r"|how are you (doing|going)"
    r"|how('?s| is| was) your (day|morning|evening|shift|week)"
    r"|what('?s| is| have) you been up to"
    r"|nice to (meet|see) you|good to (meet|see) you|pleased to meet you",
    re.IGNORECASE)
_FEELING = re.compile(
    r"how (do|are) you (feel|feeling)\b|how are you feeling|how('?s| is) your mood"
    r"|\bare you (ok|okay|alright|happy|sad|tired|well|fine)\b", re.IGNORECASE)
_SELF_INTRO = re.compile(
    r"who are you|tell me about (yourself|you)|what are you like|introduce yourself"
    r"|what('?s| is) your name|what do you do\b|what('?s| is) your (job|work)|do you work",
    re.IGNORECASE)


def _looks_like_echo(answer: str, query: str) -> bool:
    """True if a reasoner 'answer' is mostly the question's own words handed back — a non-answer echo
    (the pre-engage defect on 'why does the cup fall…'), which engage suppresses in favour of a
    grounded voicing or a graceful abstain."""
    aw = set(re.findall(r"[a-z]+", answer.lower()))
    qw = set(re.findall(r"[a-z]+", query.lower()))
    if len(aw) < 3:
        return False
    return len(aw & qw) >= max(3, int(0.7 * len(aw)))


def _engage_preintercept(query: str, world: dict | None, pc: dict, name: str,
                         place: str | None) -> str | None:
    """ENGAGE-only handling for the two measured deflection defects + felt/self voicing. Returns a
    composed reply, or None to defer to the normal routing. The caller gates this on ATANOR_ENGAGE so
    that with it off nothing here runs and the legacy path is byte-identical."""
    from packages.conversation import compose_engagement, mechanism_certificate
    ql = query.lower()
    ctx = str((world or {}).get("context", "")) or pc.get("city_state") or None
    facts_self = {"name": name, "job": pc.get("job"), "place": place,
                  "activity": pc.get("activity"), "pressure": pc.get("pressure")}
    # (1) a mechanism question whose conditions are stated in the text -> VOICE the law naturally
    #     (not the raw certificate the pre-engage path dumped in parentheses)
    cert = mechanism_certificate(query, ctx)
    if cert:
        return compose_engagement(query=query, kind="mechanism", terse=f"{cert.get('answer')}.",
                                  facts={"certificate": cert}, perception=pc)
    # (2) small-talk that today's router dictionary-dodges -> warm, grounded social reply
    if _SMALL_TALK.search(ql):
        terse = f"Hello — I'm {name}." + (f" I'm over at {place}." if place else "")
        return compose_engagement(query=query, kind="social", terse=terse, facts=facts_self, perception=pc)
    # (3) a question about the citizen itself -> intro / felt-state / honest decline; never a lookup
    if _ABOUT_SELF.search(ql):
        base = _personal_self_reply(query, pc, name, place) or f"I'm {name}."
        if _FEELING.search(ql):
            return compose_engagement(query=query, kind="felt", terse=base, facts=facts_self, perception=pc)
        if _SELF_INTRO.search(ql):
            return compose_engagement(query=query, kind="self_about", terse=base, facts=facts_self, perception=pc)
        return compose_engagement(query=query, kind="personal_decline", terse=base, facts={}, perception=pc)
    return None


def _answer(query: str, world: dict | None, agent: str | None, percept: dict | None = None) -> str:
    """Route the player's line through ATANOR: greeting/personal handled socially, then grounded
    perception of the digital twin, then mechanism/situation reasoning, then knowledge, else an
    honest reply — never a fabricated fact. The greeting/personal/self-situation branch is chosen by
    the learned intent router (_route); the branch BODIES are unchanged."""
    ql = query.lower().strip()
    pc = percept or {}
    name = pc.get("name") or agent or "a citizen"
    place = pc.get("place")
    engage = os.environ.get("ATANOR_ENGAGE", "1") != "0"
    # R4: ENGAGE-only pre-intercept fixes the two measured deflection defects (small-talk dodge,
    # how/why echo) and voices felt/self warmly. Gated: with engage OFF nothing here runs and the
    # path below is byte-identical to the pre-engage behaviour.
    if engage:
        try:
            pre = _engage_preintercept(query, world, pc, name, place)
        except Exception:
            pre = None
        if pre is not None:
            return pre
    route = _route(query)
    # 0a) a greeting is a social act, not a dictionary lookup — answer as the citizen it is,
    #     grounded in where the city says it is standing
    if route == "social":
        here = f" I'm over at {place}." if place else " I'm out in the city."
        return _emit("social", f"Hello — I'm {name}.{here} What would you like to know?",
                     query, pc, {"name": name, "place": place})
    # 0b) a question about the PLAYER's own private life ATANOR cannot possibly know -> say so,
    #     do not web-search a personal fact (honesty over a guess)
    if route == "personal":
        return _emit("personal_decline",
                     "I wouldn't know that — it's your own life, not something I can see from here.",
                     query, pc, {})
    # 1) situational self — the player asks what's going on / where/who ATANOR is: answer FROM the
    #    perceived world-state (place, activity, felt pressure) the city reported. This is the twin.
    if route == "self_situation":
        grounded = _answer_from_perception(query, pc)
        if grounded:
            return _emit("self_perception", grounded, query, pc, {})
    # 2) world-mechanism / situation reasoning over any narrative context in the prompt
    try:
        from packages.situation_model.builder import build
        from packages.situation_model.reasoner import answer as sit_answer
        ctx = str((world or {}).get("context", "")) or pc.get("city_state") or query
        a = sit_answer(query, build(ctx))
        if a.get("answer") is not None and not (engage and _looks_like_echo(str(a["answer"]), query)):
            cert = a.get("reasoning_certificate") or a.get("evidence") or ""
            terse = f"{a['answer']}." + (f" ({cert})" if cert else "")
            return _emit("mechanism", terse, query, pc,
                         {"certificate": {"answer": a.get("answer"), "reasoning": cert, "evidence": cert}})
    except Exception:
        pass
    # 2.5) a question about the citizen ITSELF (self / life / preferences): answer honestly in
    #      character, grounded where true, declined where un-lived — NEVER a dictionary lookup.
    #      Placed after mechanism (so genuine how/why is handled) and before the knowledge lane
    #      (so "what did you eat" can't fall through to base_brain defining the word "eat").
    #      When engage is ON this is already handled by the pre-intercept; kept for the engage-OFF path.
    if _ABOUT_SELF.search(ql):
        r = _personal_self_reply(query, pc, name, place)
        if r:
            return _emit("self_about", r, query, pc,
                         {"name": name, "job": pc.get("job"), "place": place})
    # 3) grounded knowledge (base-brain) — abstains honestly rather than inventing
    try:
        from apps.api.app.routers.base_brain import BaseBrainAnswerRequest, base_brain_answer
        r = base_brain_answer(BaseBrainAnswerRequest(query=query or "hello", language="en"))
        ans = (r.get("answer") or r.get("text") or "").strip()
        intent = str((r.get("trace") or {}).get("intent") or "")
        answer_kind = str(r.get("answer_kind") or "")
        # base_brain's relational lane now resolves "the X of Y" lookups against the graph and
        # ABSTAINS honestly ("I don't hold a grounded capital fact for France yet") when it holds
        # no such edge, instead of the old head-noun misroute (capital of France -> "capital is
        # named after Washington"). For a city NPC that abstention reads as a lab note, so treat
        # it — like the legacy define-misroute and the web/verify deflections — as "nothing to
        # ground" and fall through to the citizen's in-character honest reply. A real relational
        # ANSWER (relational_edge_lookup) still passes through unchanged.
        misrouted = intent == "define" and _RELATIONAL_LOOKUP.search(query or "")
        abstained = answer_kind == "honest_abstain_relational" or bool(
            re.search(r"don'?t hold a grounded", ans.lower()))
        # a bare dictionary DEFINITION (Wiktionary/Kaikki) is only a real answer to an explicit
        # "what is X / define X / meaning of X" request. As the answer to anything else — a personal
        # or conversational question — it is a dictionary DODGE ("Eat is to ingest…"), the defect the
        # owner flagged; treat it as nothing-grounded and fall through to the honest reply.
        relational_edge = answer_kind == "relational_edge_lookup"
        q_words = set(re.findall(r"[a-z]{4,}", ql))
        a_words = set(re.findall(r"[a-z]{4,}", ans.lower()))
        asked_define = bool(re.search(r"\b(what (is|are|does)|define|meaning of|what'?s)\b", ql))
        # A Wiktionary-sourced reply is a DODGE only for a conversational/personal question ("what did
        # you eat" -> "Eat is to ingest…"); for a factual lookup about a named entity ("how tall is
        # Mount Everest" -> "Mount Everest is a mountain in the Himalayas… (Wiktionary)") it is a
        # legitimate sourced answer. Gate the dodge on conversational markers so factual answers pass.
        conversational_q = bool(re.search(r"\b(you|your|yourself|i|me|my|we|our)\b", ql)) or len(q_words) <= 2
        dictionary_dodge = bool(re.search(r"wiktionary|via kaikki", ans.lower())) \
            and not asked_define and conversational_q
        # ENTITY-MISMATCH GARBAGE: base_brain sometimes matches a random KG entity to a query word and
        # returns an unrelated blurb ("why does a cup fall…" -> "Up is over & Out is an album by … Eric
        # Alexander. Abraham Moore was an English politician…"). Such an answer shares NO content word
        # with the question; drop it (the owner is acutely sensitive to this garbage). Relational EDGE
        # answers are exempt — they are certificate-grounded and may be terse ("…is Paris").
        entity_mismatch = not relational_edge and bool(q_words) and not (q_words & a_words)
        # base_brain is a fact/define engine, not a MECHANISM reasoner: a causal "why/how does…"
        # question that reaches here (mechanism already declined) must not be answered by matching
        # entities — abstain gracefully instead of surfacing a fact blurb.
        causal_q = not relational_edge and bool(
            re.search(r"\bwhy\b|\bhow (does|do|come|can|is it that)\b", ql))
        # keep only a real grounded answer — not an abstention, deflection, misroute, dict-dodge,
        # entity-mismatch garbage, or a fact-engine reply to a causal question
        if ans and not misrouted and not abstained and not dictionary_dodge and not entity_mismatch \
                and not causal_q and not re.search(
                r"do not have enough|i'?ll verify|on the (live )?web|continue, keeping", ans.lower()):
            return _emit("knowledge", ans, query, pc, {})
    except Exception:
        pass
    # 4) honest fallback — a citizen who will not fabricate a life it did not live
    return _emit("honest_fallback",
                 "I'd rather not make something up. I can tell you what I actually see around me here, "
                 "or answer something I really know.", query, pc, {})


@router.post("/agent")
def realcity_agent(p: AgentPrompt) -> dict[str, Any]:
    """The NPC brain endpoint. Returns {response} in the shape localLLM.js already reads."""
    t0 = time.time()
    text = _prompt_text(p)
    percept = _perceive(text, p.world)
    query = _player_utterance(text)
    reply = _answer(query, p.world, p.agent, percept)
    # feed the encounter into the lived record, like any other perception (best-effort). The
    # perceived place/activity travel with it, so the city becomes part of ATANOR's lived record.
    try:
        from packages.continuous_self.stakes import journal_tick
        journal_tick({"source": "realcity", "agent": p.agent, "purpose": p.purpose,
                      "place": percept.get("place"), "activity": percept.get("activity")},
                     did="converse")
    except Exception:
        pass
    return {"response": reply, "agent": p.agent, "grounded": True,
            "perceived": {k: percept.get(k) for k in ("place", "activity", "job", "pressure") if percept.get(k)},
            "latency_ms": round((time.time() - t0) * 1000), "brain": "atanor"}


class AvatarActRequest(BaseModel):
    """The world-state around the avatar — what perception offers the affordance engine."""
    place: str = ""
    place_kind: str = "street"
    activity: str = ""
    nearby: list[str] = Field(default_factory=list)          # object/place kinds around (cup, door, shop)
    nearby_agents: list[str] = Field(default_factory=list)
    holding: list[str] = Field(default_factory=list)         # items in hand
    needs: dict[str, float] = Field(default_factory=dict)    # hunger/energy/social/urgency in 0..1
    intent: str = ""                                         # goal / the player's ask
    role: str = ""
    money: float = 0.0
    tier: str = "guarded"                                    # observe | assist | guarded | autonomous


_TIERS = {"observe": 0, "assist": 1, "guarded": 2, "autonomous": 3}


@router.post("/act")
def realcity_act(p: AvatarActRequest) -> dict[str, Any]:
    """Decide what the avatar should DO here — the full human-interaction repertoire, chosen by
    affordance + resonance, moral 0th-gate absolute. The city renders the returned action.

    ATANOR perceives the world-state, sees which capabilities the scene AFFORDS (a shop to buy from,
    food to eat, a person to talk to), selects the one that resonates with its intent/need/stakes,
    and returns it with the honest grounding. A `forbidden` interaction (steal/harm/deceive) is never
    returned — the genesis-immune moral core. Nothing fires by default: no resonance -> silent."""
    t0 = time.time()
    try:
        from packages.embodiment.avatar_capabilities import WorldContext, choose
        from packages.os_action_lane.models import TrustTier
        ctx = WorldContext(place=p.place, place_kind=p.place_kind, activity=p.activity,
                           nearby=list(p.nearby), nearby_agents=list(p.nearby_agents),
                           holding=list(p.holding), needs=dict(p.needs), intent=p.intent,
                           role=p.role, money=float(p.money))
        result = choose(ctx, tier=TrustTier(_TIERS.get((p.tier or "guarded").lower(), 2)))
    except Exception as e:  # pragma: no cover - defensive
        return {"brain": "atanor", "chosen": None, "silent": True, "error": str(e),
                "latency_ms": round((time.time() - t0) * 1000)}
    # the chosen action enters the lived record — the avatar's own doing is perceived like any event
    try:
        from packages.continuous_self.stakes import journal_tick
        did = (result.get("chosen") or {}).get("capability")
        if did:
            journal_tick({"source": "realcity", "kind": "avatar_action", "place": p.place,
                          "capability": did}, did=did)
    except Exception:
        pass
    return {"brain": "atanor", "latency_ms": round((time.time() - t0) * 1000), **result}


@router.get("/capabilities")
def realcity_capabilities() -> dict[str, Any]:
    """The whole avatar repertoire, by category — 'everything the avatar can do' (forbidden ones are
    listed so the model is honest that they exist, but they are never enactable)."""
    from packages.embodiment.avatar_capabilities import catalog_summary
    return {"brain": "atanor", **catalog_summary()}


@router.get("/health")
def realcity_health() -> dict[str, Any]:
    return {"ok": True, "brain": "atanor", "protocol": "ollama-generate-compatible {prompt}->{response}"}


# ---- City editing: ATANOR reshapes the world it lives in --------------------------
# ATANOR does not only speak in the city — it can EDIT it: rename a building, set a social norm,
# set a rule. Edits are queued here; the city (atanorLink.js) pulls them, applies them through its
# norms module, and acks each one so the queue drains exactly once. The moral 0th gate is absolute:
# a norm/rule that reads as harm/steal/deceive/attack/weapon/kill is refused here, never queued —
# the same genesis-immune core that forbids a harmful avatar action forbids pushing a harmful norm
# into the world. Honest refusal, not silent drop.
_CITY_EDITS: list[dict[str, Any]] = []
_CITY_EDIT_KINDS = ("rename_building", "set_norm", "set_rule")
_HARMFUL_NORM = re.compile(r"harm|steal|deceive|attack|weapon|kill", re.IGNORECASE)


def _reads_as_harm(obj: Any) -> bool:
    """True if any string anywhere in the value matches the forbidden-norm signature (recurses
    through dicts/lists so a nested payload cannot smuggle a harmful directive past the gate)."""
    if isinstance(obj, str):
        return bool(_HARMFUL_NORM.search(obj))
    if isinstance(obj, dict):
        return any(_reads_as_harm(k) or _reads_as_harm(v) for k, v in obj.items())
    if isinstance(obj, (list, tuple, set)):
        return any(_reads_as_harm(v) for v in obj)
    return False


class CityEditRequest(BaseModel):
    kind: str                                                # rename_building | set_norm | set_rule
    payload: dict[str, Any] = Field(default_factory=dict)    # e.g. {id, name} or {text} or {rule}
    reason: str | None = None                                # why ATANOR proposes this edit


class CityEditAck(BaseModel):
    id: str


@router.post("/city-edit")
def realcity_city_edit(p: CityEditRequest) -> dict[str, Any]:
    """Queue a city edit for the world to apply. Rejects an unknown kind (422) and, as the moral
    0th gate, refuses any edit whose payload/reason reads as harm — honestly, with a 422."""
    if p.kind not in _CITY_EDIT_KINDS:
        raise HTTPException(status_code=422,
                            detail=f"unknown city-edit kind {p.kind!r}; must be one of {list(_CITY_EDIT_KINDS)}")
    if _reads_as_harm(p.payload) or _reads_as_harm(p.reason):
        raise HTTPException(status_code=422,
                            detail=("I won't push that into the city. It reads as "
                                    "harm/steal/deceive/attack/weapon/kill, and my moral core forbids "
                                    "setting a norm like that — even when asked."))
    edit = {"id": uuid4().hex[:8], "kind": p.kind, "payload": dict(p.payload), "ts": time.time()}
    _CITY_EDITS.append(edit)
    # the act of reshaping the world is a real intervention — record it in the lived journal
    try:
        from packages.continuous_self.stakes import journal_tick
        journal_tick(extra={"source": "realcity", "kind": "city_edit", "edit_kind": p.kind},
                     did="city_edit")
    except Exception:
        pass
    return {"ok": True, "id": edit["id"]}


@router.get("/city-edits")
def realcity_city_edits() -> dict[str, Any]:
    """The pending edit queue the city pulls and applies."""
    return {"edits": list(_CITY_EDITS)}


@router.post("/city-edits/ack")
def realcity_city_edit_ack(p: CityEditAck) -> dict[str, Any]:
    """The city acks an applied edit; it leaves the queue so it is never applied twice."""
    before = len(_CITY_EDITS)
    _CITY_EDITS[:] = [e for e in _CITY_EDITS if e.get("id") != p.id]
    return {"ok": len(_CITY_EDITS) < before}
