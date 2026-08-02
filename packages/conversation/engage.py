# -*- coding: utf-8 -*-
"""Engagement composer — turn a grounded sub-answer into a warm, in-character reply (not a terminal).

Owner shock (2026-07-22): an ATANOR citizen's honest answers are CORRECT but read as terse and
incompetent — the ITT measured 13/20 probes as deflect/dodge. The failure is NOT honesty; it is
CONVERSATIONAL SURFACE. This organ fixes the surface WITHOUT touching the honesty floor: it takes a
reply ATANOR already grounded (mechanism reasoning, perceived place/activity, a graph fact, its own
felt state) and assembles a natural 1-3 sentence turn — ACKNOWLEDGE -> GROUNDED CONTENT -> an
in-character OFFER/QUESTION BACK — so the exchange feels like a person talking, not a lookup table.

THE HALLUCINATION-SAFE CONTRACT (binding, and TESTED):
  * The composer NEVER invents a fact. Everything it can add beyond the grounded content is drawn
    from a CLOSED conversational vocabulary (acknowledgements / offers / connectives — the same
    closed-vocabulary discipline as packages/fluency's APPROVED_CONNECTIVES). It cannot emit a place,
    a name, a number, a meal, or any world-entity that is not already in the grounding it was handed.
  * verify_grounded() proves it: every CONTENT word of the composed reply must trace to the grounding
    (the terse answer + structured facts + perception + the user's own question) or to the closed
    conversational lexicon. A word outside both is a fabrication — and the composer, on detecting one,
    DISCARDS its candidate and returns the terse answer unchanged. So it is safe by construction: the
    engaged reply can only ever be as grounded as the terse one, never more.
  * Where nothing is grounded, it abstains GRACEFULLY — it keeps the honest decline and adds an offer
    of what it CAN help with, rather than a bare "I don't know". Graceful != fabricated.

Registers are DATA (simple / warm / curious): small pools of closed acknowledgements and offers,
selected by the kind of answer. Adding a register or a phrase is a data edit here, never free text at
runtime. NO learned weights — registered in the neuro ledger as a near-zero-param control organ.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

# ── closed conversational lexicon ────────────────────────────────────────────────────────────────
# The ONLY content words the composer may introduce beyond the grounding. Everything else must come
# from the grounded answer/facts/perception/question. This is the honesty gate's allowlist — the same
# discipline as fluency.register.APPROVED_CONNECTIVES: register data selects from a closed surface, it
# can never smuggle in a world-fact. (Function words / stopwords are filtered before the check and are
# not listed here.)
CONVERSATIONAL_VOCAB: frozenset[str] = frozenset({
    # acknowledgements
    "hey", "right", "sure", "okay", "well", "good",
    # offer / question-back verbs + framing
    "would", "like", "know", "anything", "want", "ask", "around", "here", "happy", "help",
    "however", "can", "about", "area", "going", "tell", "glad", "helps", "walk", "through",
    "another", "reason", "more", "again", "one", "else",
    # honest-frame words shared with the abstain templates
    "honestly", "truly", "actually", "see", "really", "something", "answer", "make", "up",
    "rather", "wouldn", "own", "life", "not", "from", "what", "who",
    # small-talk / self framing
    "doing", "alright", "steady", "day", "just", "mind", "thing", "things", "spend", "days",
    "usually", "find", "much", "today", "how", "you", "your",
    # felt vital-note plain words (the DATA vital->phrase map below)
    "low", "little", "running", "energy", "wanting", "some", "company", "curious",
    "learn", "new", "scattered", "thoughts", "bit", "now",
    # light connectives (closed)
    "so", "and", "but", "or", "still", "over", "at",
})

# grounding words that are common enough to also appear in templates; treated as neither fabrication
# nor a "content" claim. Kept minimal on purpose.
_STOP: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "of", "to", "in", "on",
    "for", "with", "it", "its", "this", "that", "these", "those", "i", "im", "me", "my", "we",
    "he", "she", "they", "them", "his", "her", "their", "as", "by", "if", "then", "there", "when",
    "s", "re", "ll", "ve", "t", "d", "m", "no", "yes", "do", "does", "did", "has", "have", "had",
    "will", "would", "can", "could", "should", "out", "into", "about",
})


def _tokens(text: str) -> list[str]:
    # split on non-letters so contractions break into parts ("i'm" -> i, m; "what's" -> what, s);
    # the fragments (i, m, s, ll, ...) are stopwords, so only real content survives the filter.
    return [w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) >= 2]


def _content_tokens(text: str) -> list[str]:
    return [w for w in _tokens(text) if w not in _STOP]


def _grounding_words(*sources: Any) -> set[str]:
    """Collect the content words available as grounding (from strings / dict values / lists)."""
    out: set[str] = set()

    def add(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            out.update(_content_tokens(x))
        elif isinstance(x, dict):
            for v in x.values():
                add(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                add(v)
        else:
            add(str(x))

    for s in sources:
        add(s)
    return out


def verify_grounded(composed: str, grounding: set[str]) -> tuple[bool, list[str]]:
    """The fabrication gate. Returns (ok, fabricated_words). A composed reply is grounded iff every
    content word traces to the grounding set or the closed conversational lexicon. Any other content
    word is a fabrication — a world-entity the composer conjured that its inputs never contained."""
    allowed = grounding | CONVERSATIONAL_VOCAB
    fabricated = [w for w in _content_tokens(composed) if w not in allowed]
    return (not fabricated), fabricated


# ── register data: simple / warm / curious (closed pools, DATA not code branches) ────────────────
@dataclass(frozen=True)
class Register:
    id: str
    offers: tuple[str, ...] = ()      # question-back / offer-of-help lines (closed vocabulary)


# offer pools per conversational situation. Every word here is in CONVERSATIONAL_VOCAB.
_OFFERS: dict[str, tuple[str, ...]] = {
    "social": (
        "What would you like to know?",
        "Anything you want to ask about around here?",
        "Happy to help however I can.",
    ),
    "self": (
        "What would you like to know about me or around here?",
        "Ask me anything about what's going on.",
    ),
    "mechanism": (
        "Want me to walk through another?",
        "Happy to reason through more if you like.",
    ),
    "knowledge": (
        "Want to know more?",
        "Ask me anything else you're curious about.",
    ),
    "abstain": (
        "But I'm glad to tell you what's going on around here, if that helps.",
        "Ask me what's going on around here and I'll tell you truly.",
    ),
    "felt": (
        "How about you?",
    ),
}

REGISTERS: dict[str, Register] = {
    "simple": Register("simple", offers=()),
    "warm": Register("warm", offers=_OFFERS["social"]),
    "curious": Register("curious", offers=_OFFERS["mechanism"]),
}

# felt vital -> plain-words self-report (DATA map; a real vital DEFICIT renders as one of these). This
# is a rendering of a measured internal signal, not a claimed quale — see the no-qualia line in
# packages/subjective. Every word is in CONVERSATIONAL_VOCAB.
_VITAL_NOTE: dict[str, str] = {
    "energy": "I'm running a little low on energy",
    "social": "I've been wanting some company",
    "coherence": "my thoughts are a bit scattered just now",
    "knowledge": "I'm curious to learn something new",
}


def _pick(pool: tuple[str, ...], seed: str) -> str:
    """Deterministic pick so a given question yields a stable reply (reproducible, testable)."""
    if not pool:
        return ""
    return pool[hash(seed) % len(pool)]


def _first_lower(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _strip_trailing_period(s: str) -> str:
    return s.rstrip().rstrip(".").rstrip()


# ── mechanism voicing: read the user's stated conditions, VOICE the law (not the raw certificate) ──
# The situation_model mechanism engine returns a structured certificate {answer, law, evidence,
# reasoning}. We call it (never edit it) and speak the `reasoning` as a natural clause. For a "why /
# what-happens" question whose falling-at-the-edge conditions are stated INSIDE the question, we
# reshape the user's OWN words into the declarative form the engine reads (every token is the user's,
# no world-fact added) so the citizen can voice the law instead of echoing the question.
_DISTURB = r"(bumped|knocked|pushed|nudged|hit|shoved)"
_EDGE_Q = re.compile(r"\bthe\s+([a-z]+)\b.*?\b" + _DISTURB + r"\s+(?:at|near|on)\s+(?:the\s+)?edge", re.I)


def mechanism_certificate(query: str, ctx: str | None = None) -> dict[str, Any] | None:
    """Ground a mechanism question -> {answer, reasoning, evidence, law} or None. Calls
    situation_model.mechanism; abstains (None) when no domain-blind law is grounded by stated
    conditions (the honesty floor — never a guess)."""
    try:
        from packages.situation_model.mechanism import answer_mechanism
    except Exception:
        return None
    text = ctx if (ctx and ctx.strip() and ctx.strip() != query.strip()) else query
    cert = answer_mechanism(query, text)
    if cert and cert.get("answer") is not None:
        return cert
    # faithful reshape of the user's own falling-at-the-edge scenario into declaratives
    m = _EDGE_Q.search(query)
    if m:
        subj, verb = m.group(1), m.group(2)
        reshaped = f"the {subj} is at the edge. someone {verb} the {subj}."
        cert = answer_mechanism(f"what happens to the {subj}?", reshaped)
        if cert and cert.get("answer") is not None:
            return cert
    return None


def _voice_mechanism(cert: dict[str, Any]) -> str:
    """Speak the reasoning naturally. A 'no' verdict LEADS with No; a prediction states the outcome."""
    ans = str(cert.get("answer") or "").strip()
    reasoning = str(cert.get("reasoning") or "").strip()
    if not reasoning:
        reasoning = str(cert.get("evidence") or "").strip()
    if ans.lower() == "no":
        return "No — " + _first_lower(reasoning) if reasoning else "No."
    # e.g. "the cup falls" — the reasoning sentence already contains and explains the outcome
    return reasoning or (ans[:1].upper() + ans[1:] + ".")


# ── felt-state voicing (honest self-report from packages/subjective, if present) ─────────────────
def _felt_note() -> str:
    """A plain-words note about a real internal DEFICIT (a stakes-vital running low), or '' if the
    body is even. Reads the live felt state; never claims a quale (no-qualia line)."""
    try:
        from packages.subjective import read_live_felt_state
        fs = read_live_felt_state()
    except Exception:
        return ""
    worst, worst_def = None, 0.0
    for vital in ("energy", "social", "coherence", "knowledge"):
        d = fs.hunger(vital)
        if d is not None and d > worst_def:
            worst, worst_def = vital, d
    if worst is not None and worst_def >= 0.45 and worst in _VITAL_NOTE:
        return _VITAL_NOTE[worst]
    return ""


# ── the composer ─────────────────────────────────────────────────────────────────────────────────
@dataclass
class GroundedReply:
    kind: str
    terse: str
    facts: dict[str, Any] = field(default_factory=dict)
    perception: dict[str, Any] = field(default_factory=dict)
    query: str = ""


_SELF_GROUP = {"self_perception", "self_about"}
_ABSTAIN_GROUP = {"personal_decline", "honest_fallback", "knowledge_abstain"}


def _assemble(parts: list[str]) -> str:
    """Join non-empty parts into clean sentences (each part is its own sentence)."""
    out = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if p[0].islower():                              # sentence-case each part (grounded words only)
            p = p[0].upper() + p[1:]
        if p[-1] not in ".!?":
            p += "."
        out.append(p)
    return " ".join(out)


def compose_engagement(query: str, kind: str, terse: str,
                       facts: dict[str, Any] | None = None,
                       perception: dict[str, Any] | None = None) -> str:
    """Assemble a warm, in-character 1-3 sentence reply from a grounded sub-answer. Kill-switch:
    ATANOR_ENGAGE=0 returns the terse answer unchanged (byte-identical to the pre-engage behaviour).
    Safe by construction: any candidate that would introduce an ungrounded content word is discarded
    in favour of the terse answer, so engagement can never reduce faithfulness."""
    if os.environ.get("ATANOR_ENGAGE", "1") == "0":
        return terse
    facts = facts or {}
    pc = perception or {}
    grounding = _grounding_words(terse, facts, pc, query)

    name = str(facts.get("name") or pc.get("name") or "").strip()
    place = str(facts.get("place") or pc.get("place") or "").strip()
    job = str(facts.get("job") or pc.get("job") or "").strip()
    activity = str(facts.get("activity") or pc.get("activity") or "").strip()
    pressure = str(facts.get("pressure") or pc.get("pressure") or "").strip()

    parts: list[str] = []
    offer_key = "social"

    if kind == "social":
        head = f"Hey — I'm {name}" if name else "Hey"
        if activity and place:
            head += f", {activity} over at {place}"
        elif place:
            head += f" over at {place}"
        parts.append(head)
        offer_key = "social"

    elif kind == "self_about":
        head = f"I'm {name}" if name else "I'm around here"
        if job:
            head += f", a {job}"
        parts.append(head)
        if place:
            parts.append(f"You'll usually find me around {place}")
        offer_key = "self"

    elif kind == "felt":
        base = "Honestly, I'm steady" + (f" — just going about my day over at {place}" if place else "")
        parts.append(base)
        note = _felt_note()
        if note:
            parts.append(note)
        elif pressure:
            parts.append(f"the thing on my mind is {pressure}")
        offer_key = "felt"

    elif kind == "self_perception":
        # the terse perception voicing is already grounded; keep it and add a warm offer
        parts.append(_strip_trailing_period(terse))
        offer_key = "self"

    elif kind == "mechanism":
        cert = facts.get("certificate") if isinstance(facts.get("certificate"), dict) else facts
        parts.append(_voice_mechanism(cert))
        offer_key = "mechanism"

    elif kind == "knowledge":
        parts.append(_strip_trailing_period(terse))
        offer_key = "knowledge"

    elif kind in _ABSTAIN_GROUP:
        # graceful abstention: keep the honest decline verbatim, add an offer of what it CAN do
        parts.append(_strip_trailing_period(terse))
        # honest_fallback already carries its own offer; personal_decline does not
        offer_key = "abstain" if kind == "personal_decline" else None  # type: ignore[assignment]

    else:
        return terse  # unknown kind -> never worse than terse

    offer = _pick(_OFFERS.get(offer_key, ()), query) if offer_key else ""
    if offer:
        parts.append(offer)

    candidate = _assemble(parts)
    ok, _fab = verify_grounded(candidate, grounding)
    if not ok or not candidate.strip():
        return terse                                   # safety: never emit an ungrounded word
    return candidate
