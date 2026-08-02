# -*- coding: utf-8 -*-
"""Inner voice — the workspace winner verbalized as first-person inner speech, so the stream of
thought reads like thinking, not like a log.

Owner (2026-07-20): like humans who think in inner language, ATANOR should keep talking to itself
unprompted, making its process readable. The science this leans on: Vygotsky (thought as
internalized speech), Alderson-Day & Fernyhough (inner speech is condensed, dialogic, and
self-directed), Morin (inner speech serves self-awareness and self-regulation), Damasio (feeling
colours thought — so the hormonal tone inflects the voice).

Honesty (BINDING): every sentence is a SELF-REPORT of state that actually exists — the concern that
actually won, the hormone levels actually present, the repetition actually counted. Grounded by
construction; nothing external is asserted. Variation comes from seeded frame choice (like the
argument realizer), never from invention.
"""
from __future__ import annotations

import random

from .workspace import Concern

# frame families per concern source; {c}=concern core, chosen by seeded rng for variation.
# These are VOICE forms (how a self talks to itself), not knowledge — same doctrinal status as
# the argumentation schemes: form, not fact.
_FRAMES = {
    "interoception": [
        "{c} — I keep noticing it. What would actually strengthen this first?",
        "There it is again: {c}. Naming it isn't fixing it.",
        "{c}. That's mine to mend, and it won't mend itself.",
    ],
    "perception": [
        "{c} That deserves a real answer, not a reflex.",
        "{c} Let me actually take this in before I speak.",
        "{c} Someone is waiting on me — what do they truly need here?",
    ],
    "curiosity": [
        "{c} Quiet enough to wonder about it now.",
        "{c} I don't know yet — and that's exactly what makes it worth a beat.",
        "Nothing is pulling at me, so: {c}",
    ],
}
_FALLBACK_FRAMES = [
    "{c} — I'm holding this in mind.",
    "{c}. Let me sit with it a moment.",
]

# tone inflections read off the REAL hormone field (Damasio: feeling colours thought)
_STRESS_TONE = [
    " It presses on me more than it should.",
    " I feel the urgency in this one.",
]
_REWARD_TONE = [
    " Honestly, this one pulls me in.",
    " There's something bright about it.",
]
_HABITUATION_TONE = [
    " …I've been circling this, though. After this, let it rest a while.",
    " I notice I keep returning here — one more look, then elsewhere.",
]


def _seed(concern: Concern, beats: int) -> int:
    h = beats * 131
    for ch in concern.content[:80]:
        h = (h * 31 + ord(ch)) & 0x7FFFFFFF
    return h


def _core(concern: Concern) -> str:
    """The concern's content, trimmed to speak naturally inside a sentence."""
    c = " ".join(concern.content.split())
    if c.startswith("I notice a deficit: "):
        # The deficit may now carry what has been DONE about it, after the em dash. That trailing
        # clause is a separate thought and must not be spliced into the middle of this one -- the
        # first live beats after the change read "my router immature — the loop has been working on
        # this is still with me", which is a sentence nobody would say about themselves.
        body = c[len("I notice a deficit: "):]
        head, _, note = body.partition(" — ")
        said = "my " + head.replace("_", " ") + " is still with me"
        return f"{said} — {note}" if note else said
    return c.rstrip(".")


def verbalize(concern: Concern, hormones: dict[str, float] | None = None,
              *, repeats: int = 0, beats: int = 0) -> str:
    """One sentence of inner speech for the winning concern — first person, state-grounded, toned
    by the actual hormone field, aware of its own repetition (habituation made audible)."""
    h = hormones or {}
    rng = random.Random(_seed(concern, beats))
    frames = _FRAMES.get(concern.source, _FALLBACK_FRAMES)
    line = frames[rng.randrange(len(frames))].format(c=_core(concern))
    if float(h.get("cortisol", 0.0)) > 0.45:
        line += _STRESS_TONE[rng.randrange(len(_STRESS_TONE))]
    elif float(h.get("dopamine", 0.0)) > 0.45:
        line += _REWARD_TONE[rng.randrange(len(_REWARD_TONE))]
    if repeats >= 2:
        line += _HABITUATION_TONE[rng.randrange(len(_HABITUATION_TONE))]
    return line
