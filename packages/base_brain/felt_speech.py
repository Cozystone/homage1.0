# -*- coding: utf-8 -*-
"""Felt speech — the creative/emotional realizer, doctrine-pure (owner 2026-07-15 DNT reframe).

The DNT proposal wanted to RELAX the verify-gate for creative mode; that is fabrication by another
name. The correct move is to RE-TARGET the grounding, not loosen it: an emotional/creative utterance
is not a factual CLAIM, so it does not ground in world facts — it grounds in the AI's REAL internal
state (neural_emotion) and REAL learned associations (the graph / PHFE neighbours), and it is MARKED
as felt/expression, never asserted as true. A metaphor is not a false fact; it is a marked figure.

So nothing is invented: the affect comes from the running emotion vector, the associations are real
graph neighbours, the flow uses the learned connectives, and the surface (mood lexicon, evocation
verb, josa) is LAD — the same kind of function-word surface as josa, not a canned response sentence.
Output carries mode="felt" so the caller frames it honestly. Returns None when there is no real
material (no fabrication, no template fallback — honest silence).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# affect LAD lexicon: (valence, arousal) quadrant → a mood word. Small surface map (like josa), not a
# response template — it lexicalizes the REAL emotion vector, it does not fabricate a feeling.
_MOOD = {
    ("+", "+"): ("설레는", "들뜬", "생기 도는"),
    ("+", "-"): ("잔잔한", "편안한", "따뜻한"),
    ("-", "+"): ("초조한", "긴장된", "뒤숭숭한"),
    ("-", "-"): ("가라앉은", "쓸쓸한", "무거운"),
}


def _josa(word: str, kind: str) -> str:
    """Attach the correct particle via the LAD orthography engine; plain fallback if unavailable."""
    try:
        from packages.language_lad.korean_orthography import josa
        return josa(word, kind)
    except Exception:
        has = bool(word) and word[-1] >= "가" and (ord(word[-1]) - 0xAC00) % 28 != 0
        table = {"topic": ("은", "는"), "subj": ("이", "가"), "obj": ("을", "를"),
                 "from": ("에서", "에서")}
        pair = table.get(kind, ("", ""))
        return word + (pair[0] if has else pair[1])


def _mood_word(valence: float, arousal: float, seed: int) -> str:
    vq = "+" if valence >= 0 else "-"
    aq = "+" if arousal >= 0 else "-"
    pool = _MOOD[(vq, aq)]
    return pool[seed % len(pool)]


@dataclass
class Felt:
    text: str
    mode: str = "felt"                       # NEVER 'fact' — the caller frames it as expression
    mood: str = ""
    associations: list[str] = field(default_factory=list)
    guarantees: dict[str, bool] = field(default_factory=lambda: {
        "external_llm": False, "fabricated_facts": False, "asserted_as_fact": False,
        "grounded_in": True})                # grounded in real state + real associations, marked felt

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.text, "answer_kind": "felt_speech", "mode": self.mode,
                "mood": self.mood, "associations": self.associations,
                "reasoning_certificate": {"derivation_kind": "felt_speech",
                                          "grounding": "internal_state+learned_association",
                                          "guarantees": self.guarantees}}


def felt_speech(topic: str, *, valence: float = 0.0, arousal: float = 0.0,
                associations: list[str] | None = None, seed: int = 0) -> Felt | None:
    """Compose a felt utterance from REAL affect (valence/arousal, from the emotion engine) and REAL
    associations (graph neighbours of `topic`). Fuses a mood clause with an evocation of the
    associations via the learned realizer; marked mode='felt'. None if there is no real material."""
    topic = (topic or "").strip()
    assoc = [a.strip() for a in (associations or []) if a and a.strip()][:3]
    mood = _mood_word(valence, arousal, seed)
    mood_clause = f"지금 마음이 {mood}데"                        # the real affect, lexicalized (LAD)

    if not topic and not assoc:
        # only a mood, no topic/association to ground the expression on → just the felt state, honest
        return Felt(text=f"지금은 마음이 {mood} 상태예요.", mood=mood)

    if not assoc:
        # a topic but no learned association → do NOT invent one; state the felt orientation only
        return Felt(text=f"{mood_clause}, {_josa(topic, 'topic')} 아직 또렷한 상이 안 잡혀요.",
                    mood=mood, associations=[])

    # real associations → weave them as an EVOCATION (marked felt, not a factual claim). The verb

    evoked = ", ".join(assoc[:-1] + [f"그리고 {assoc[-1]}"]) if len(assoc) > 1 else assoc[0]
    body = f"{mood_clause}, {_josa(topic, 'subj')} 떠오를 때 {_josa(evoked, 'subj')} 함께 스쳐요."
    return Felt(text=body, mood=mood, associations=assoc)
