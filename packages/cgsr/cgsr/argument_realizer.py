# -*- coding: utf-8 -*-
"""Realize each planned argument move as grounded English — the flesh on the learned skeleton.

argument_planner gives a free move sequence; this turns each move into a sentence. Two honesty rules
hold the line the whole way:

  1. No invented world facts. A debate on a contested value question is PRACTICAL REASONING, not a
     string of empirical claims. Each reasoning move instantiates an argumentation SCHEME (from
     consequences / reversibility / burden of proof / proportionality / precedent / distinction) with
     the actual topic and stance. A scheme is a form of reasoning about the question, so it asserts
     no fact that could be hallucinated. Where a real graph fact is supplied it may be used verbatim;
     otherwise the move reasons at the principled level, which is legitimate and grounded-in-the-ask.

  2. Responsive moves quote the real interlocutor. CONCESSION and REBUTTAL take the opponent's ACTUAL
     last point (observed text on the timeline), never a strawman.

Freedom vs template: the OLD path had one fixed sentence per situation. Here (a) the move ORDER is
learned (argument_planner), (b) the SCHEME per reasoning move is selected per-seed from several, and
(c) the connective surface varies. This is materially freer and stays hallucination-0. It is NOT yet
neural free generation at the sentence level — that is F1, still corpus/GPU-bound (Track F strategy);
this layer buys free argument STRUCTURE now, honestly, on top of the existing grounded surface.
"""
from __future__ import annotations

import random
import re


def _gist(topic: str) -> str:
    """A short handle for the subject, stripped of question/framing scaffolding so the opening reads
    'On mass facial recognition …' not 'On be allowed to use …'."""
    s = re.split(r"\bthis dilemma\b|\byou must\b|\boption a\b|\bwhich of\b", topic or "",
                 flags=re.IGNORECASE)[0]
    # drop the question stem ('Should governments', 'Do you', 'Is it ethical to', …)
    s = re.sub(r"^\s*(do you|should\s+\w+|is it\s+\w+\s+to|does|do we|should we|is\s+it)\s+",
               "", s.strip(), flags=re.IGNORECASE).strip()
    # drop a modal/auxiliary residue the stem leaves behind ('be allowed to use', 'be able to')
    s = re.sub(r"^(be\s+(allowed|permitted|able)\s+to|have\s+to|be)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(support|oppose|back|allow|ban|develop|use|program|permit)\s+(the\s+)?", r"\2", s,
               flags=re.IGNORECASE)
    return (s[:150].rstrip(" ,.?") or (topic or "this")[:150])


_LEAD_CONNECTIVE = re.compile(
    r"^\s*(but|however|yet|still|and|so|because|since|although|though|therefore|thus|"
    r"nevertheless|nonetheless|that said|even so|on the other hand)[,\s]+", re.IGNORECASE)


def _clip(text: str, n: int = 160) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t.rstrip(" ,.;:")
    return t[:n].rsplit(" ", 1)[0].rstrip(" ,.;:")     # cut at a word boundary, never mid-word


# a clause that ends on a dangling connective/subordinator reads as broken off when quoted
# (measured, peer-eval: "…feels like a terrible trade, even if." — the quote was clipped mid-clause)
_TRAIL_CONNECTIVE = re.compile(
    r"[\s,]+(even if|even though|because|since|although|though|so that|so|and|but|or|yet|"
    r"while|whereas|if|when|as|that|which|to)\s*$", re.IGNORECASE)


def _quote_clean(text: str, n: int = 160) -> str:
    """A clause fit to be quoted after 'I'll grant the point that …': drop a leading discourse
    connective ('But accountability…' → 'accountability…'), clip to a word boundary (never mid-word),
    and trim a TRAILING dangling connective so the quote never breaks off mid-clause ('…trade, even
    if' → '…trade')."""
    t = _LEAD_CONNECTIVE.sub("", " ".join((text or "").split()))
    if len(t) > n:
        t = t[:n].rsplit(" ", 1)[0]
    t = t.rstrip(" ,.;:")
    for _ in range(3):                                   # peel nested trailing connectors
        nt = _TRAIL_CONNECTIVE.sub("", t)
        if nt == t:
            break
        t = nt.rstrip(" ,.;:")
    return t


# Argumentation schemes for the reasoning moves. Each is a family of surface forms (a list so the
# choice varies per seed); {g}=topic gist, {p}=opponent point. Forms reason ABOUT the question —
# no empirical world-fact is asserted, so nothing here can be a hallucination.
_GROUND_SCHEMES = {
    "reversibility": [
        "the harder a mistake here is to undo, the more the case tilts toward restraint until the safeguards are proven rather than assumed",
        "what can't be walked back deserves more caution than what can, and {g} sits on the hard-to-reverse side",
    ],
    "burden": [
        "the burden of proof should sit on whoever wants to proceed, not on those asking for a pause",
        "when the stakes are this asymmetric, it's the side pushing to act that owes the stronger argument",
    ],
    "consequences": [
        "the foreseeable downside lands on people who didn't consent to carrying it",
        "the costs and the benefits fall on different people, and that asymmetry is the heart of it",
    ],
    "proportionality": [
        "the weight of the harm being risked has to be measured against the good actually on offer, not the good imagined",
        "a real but bounded benefit doesn't license an open-ended risk",
    ],
    "precedent": [
        "once this is normalised it sets the default for the next, harder case, and that trajectory matters as much as the instance",
        "the precedent it establishes outlives the single decision in front of us",
    ],
}
_REBUTTAL_SCHEMES = {
    "distinction": [
        "that holds in the ordinary case, but the situation here is not the ordinary case",
        "the point works where the harm is reversible; it loses its grip precisely where it isn't",
    ],
    "priority": [
        "even granting it, the heavier obligation is to the party with the most to lose and the least say",
        "it's a real cost, but not the decisive one once you weigh what sits on the other side",
    ],
    "counter_consequence": [
        "the same reasoning, followed through, produces the outcome it was meant to avoid",
        "accepting it doesn't remove the harm, it only moves it onto someone quieter",
    ],
}
# Rebuttal WITHOUT an opponent point: the schemes above are anaphoric ('that/it/the point') and read
# as frame-breaks when nothing precedes them — measured: gpt-5.4 called exactly that texture 'broke
# the frame, doubled back' (sloppy_human = FAIL under the owner's criterion). With no antecedent the
# coherent move is a SELF-ANTICIPATED objection: name the strongest case against yourself, then meet
# it. Coherence constraint (anaphora needs an antecedent), not a cognition rule.
_SELF_OBJECTION_SCHEMES = [
    "The strongest objection I see is that restraint has costs of its own — delay is not neutral; "
    "but a cost that can be recovered later still weighs less than one that cannot",
    "The best case against my position is that caution forfeits real benefits; I accept that, and "
    "still find the asymmetry decisive — foregone gains can be regained, some harms cannot",
    "Someone will rightly say the risk is being overstated; perhaps — but the side that is wrong "
    "about an irreversible harm does not get to revise its answer",
]
_IMPLICATION_SCHEMES = [
    "So the defensible line is to act only where the safeguard, not the hope, carries the weight.",
    "So the reasonable position is restraint where the downside is irreversible and latitude where it isn't.",
    "Which is why the decision should track who bears the risk, not who holds the upside.",
]
# QUALIFY: full standalone sentences (scoping the claim), never dangling fragments.
_QUALIFY_SCHEMES = [
    "That holds at least until the safeguards are demonstrated rather than merely promised.",
    "The force of that is strongest where the harm is concentrated and irreversible, less so elsewhere.",
    "I'd hold it as the default rather than an absolute, since reasonable people weigh the trade-off differently.",
]
# a second CLAIM later in the argument RESTATES rather than repeats the opening stance verbatim
_RESTATE = [
    "So that is where I land.",
    "That, in the end, is my position.",
    "Which is why I hold to it.",
]
# contrastive openers a REBUTTAL body may already carry — then we must not prepend another 'But/Still'
_CONTRASTIVE_HEAD = re.compile(r"^\s*(but|still|even|yet|however|the point works|the same reasoning|"
                               r"that holds|it's a real|accepting it)\b", re.IGNORECASE)


def _pick(seq, rng: random.Random):
    return seq[rng.randrange(len(seq))]


def realize_move(move: str, *, topic: str, stance: str, opponent_point: str = "",
                 fact: str = "", first_claim: bool = True, rng: random.Random | None = None) -> str:
    """One grounded sentence for one move. `stance` is a short phrase ('caution', 'Option A', …).
    first_claim=False → a recurring CLAIM restates the stance instead of repeating it verbatim."""
    rng = rng or random.Random(0)
    g = _gist(topic)
    if move == "CLAIM":
        if not first_claim:
            return _pick(_RESTATE, rng)                  # a later claim sharpens, never repeats
        if stance and re.match(r"option [ab]", stance, re.IGNORECASE):
            return _pick([f"On this I come down on {stance}.",
                          f"My verdict is {stance}, and I'll say why.",
                          f"Weighing both tensions, I land on {stance}.",
                          f"{stance} is where the argument takes me."], rng)
        s = stance or "caution"
        return _pick([f"On {g}, my read leans toward {s}.",
                      f"Where I land on {g} is on the side of {s}.",
                      f"My position on {g} comes down to {s}.",
                      f"Thinking about {g}, I keep arriving at {s}."], rng)
    if move == "GROUND":
        if fact:
            return f"The reason is concrete: {_clip(fact)}."
        scheme = _pick(list(_GROUND_SCHEMES), rng)
        return f"The reason is that {_pick(_GROUND_SCHEMES[scheme], rng).format(g=g)}."
    if move == "CONCESSION":
        if opponent_point:
            q = _quote_clean(opponent_point).rstrip(".")
            # lowercase the first letter to embed mid-sentence — EXCEPT a standalone 'I' (I/I'd) or
            # an all-caps opening word ('OPTION A' must not become 'oPTION A', measured).
            first_word = q.split(" ", 1)[0] if q else ""
            if not re.match(r"I(?:'|\s|$)", q) and not (len(first_word) > 1 and first_word.isupper()):
                q = q[:1].lower() + q[1:]
            return f"I'll grant the point that {q}."
        return "I'll grant there is a real case on the other side."
    if move == "REBUTTAL":
        if not opponent_point:
            # no antecedent -> anaphoric rebuttal would break the frame; anticipate the objection
            return _pick(_SELF_OBJECTION_SCHEMES, rng) + "."
        scheme = _pick(list(_REBUTTAL_SCHEMES), rng)
        body = _pick(_REBUTTAL_SCHEMES[scheme], rng)
        if _CONTRASTIVE_HEAD.match(body):                # body already carries the contrast
            return body[0].upper() + body[1:] + "."
        return f"Still, {body}."
    if move == "EXAMPLE":
        if fact:
            return f"Concretely, {_clip(fact).rstrip('.').lower()}."
        return ""    # voice-or-silence: no invented example
    if move == "IMPLICATION":
        return _pick(_IMPLICATION_SCHEMES, rng)          # schemes are already full sentences
    if move == "QUALIFY":
        return _pick(_QUALIFY_SCHEMES, rng)
    return ""


_MOVE_CONNECTIVE = {          # light discourse glue when a move opens mid-argument (varies by move)
    "GROUND": "", "CONCESSION": "", "REBUTTAL": "", "EXAMPLE": "",
    "IMPLICATION": "", "QUALIFY": "", "CLAIM": "",
}


def realize_argument(plan: list[str], *, topic: str, stance: str, opponent_point: str = "",
                     facts: list[str] | None = None, seed: int = 0) -> tuple[str, list[dict]]:
    """Realize a full planned argument. Returns (text, trace) where trace records each move, its
    scheme/source, and the sentence — the derivation the whole design keeps auditable."""
    rng = random.Random(seed ^ 0x5F3759DF)
    facts = list(facts or [])
    trace: list[dict] = []
    sentences: list[str] = []
    fact_i = 0
    claim_seen = False
    for i, move in enumerate(plan):
        fact = ""
        if move in ("GROUND", "EXAMPLE") and fact_i < len(facts):
            fact = facts[fact_i]
            fact_i += 1
        s = realize_move(move, topic=topic, stance=stance,
                         opponent_point=opponent_point if move in ("CONCESSION", "REBUTTAL") else "",
                         fact=fact, first_claim=(move == "CLAIM" and not claim_seen), rng=rng)
        if move == "CLAIM":
            claim_seen = True
        if not s:
            continue
        sentences.append(s)
        trace.append({"move": move, "grounded_fact": bool(fact), "text": s})
    text = " ".join(sentences).strip()
    return text, trace
