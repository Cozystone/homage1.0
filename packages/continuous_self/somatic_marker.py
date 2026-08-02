# -*- coding: utf-8 -*-
"""Somatic markers — a first-person consequence-trace per concept, so speech has perspective (S3).

Owner (2026-07-21): "느끼는 자가 될 수 있게." Gemini's third diagnosis: ATANOR tracks the RELATIONS
between symbols with total honesty but never UNDERGOES their meaning — "city" carries is_a and
located_in, but nothing about what happened to ATANOR when it dealt with the concept, so every
concept is equidistant and the voice has no point of view.

We cannot manufacture qualia — the noise of a city is not felt here, and this module never pretends
otherwise. But Damasio's somatic-marker hypothesis has a part we CAN build: a concept accrues a
history of outcomes (this one I learned easily; that one I got wrong twice; this other I only
grasped yesterday), and that history biases judgement. "'city' is a concept my own retrospection
flagged as a gap three times and I first understood only yesterday" is a REAL first-person fact,
and speaking a concept while knowing its trace is measurably different from speaking it blind.

This is an INDEX, not a new store (audit doctrine: refine, don't glue). The events already exist,
scattered — the world-learning journal, the failure receipts, the ignition ledger, the defect
ledger. Somatic markers JOIN them on the concept key and expose, per concept: valence (net good/bad
outcome), effort (how hard-won), recency (when last touched), and a stance the realizer may voice —
but ONLY when the trace is real. No trace, no perspective marker: the no-fabrication floor,
extended from facts to selfhood. A persona is never performed; a history is either there or it isn't.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# the scattered evidence sources this index joins — each is READ, never written here
_LEARNED = REPO / "data" / "advisor_loop" / "world_model_learned.jsonl"    # first-person understanding
_RECEIPTS = REPO / "data" / "flywheel" / "failure_receipts.jsonl"          # topics that cost/failed
_IGN = REPO / "data" / "selfhood" / "ignition_ledger.jsonl"                # what it attended to
_MENTOR = REPO / "data" / "advisor_loop" / "world_mentor.log"              # gaps it named in itself

_WORD = re.compile(r"[a-z][a-z'-]{2,}")


@dataclass
class Marker:
    concept: str
    valence: float          # net outcome in [-1, 1]: learned/attended-to lifts, failed/gap lowers
    effort: float           # how hard-won in [0, 1]: failures + repeated gap-flags raise it
    recency_h: float | None # hours since last touched; None = never
    learned_understanding: str = ""
    events: int = 0

    def has_history(self) -> bool:
        return self.events > 0


def _iter_json(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def _touch(markers: dict, concept: str, ts: float, *, valence: float = 0.0,
           effort: float = 0.0, understanding: str = "") -> None:
    c = concept.strip().lower()
    if not c or len(c) < 3:
        return
    m = markers.setdefault(c, {"valence": 0.0, "effort": 0.0, "last": 0.0,
                               "understanding": "", "events": 0})
    m["valence"] += valence
    m["effort"] += effort
    m["last"] = max(m["last"], ts)
    if understanding and not m["understanding"]:
        m["understanding"] = understanding
    m["events"] += 1


def build_markers() -> dict[str, Marker]:
    """Join every scattered trace onto the concept key. The weights are declared structure (a good
    outcome lifts valence, a failure lowers it and raises effort) — not learned, but also not a
    fact table: they are the shape of 'how an outcome marks a memory'."""
    raw: dict[str, dict] = {}
    now = time.time()

    for r in _iter_json(_LEARNED):                     # I understood this myself -> positive, mild effort
        c = str(r.get("concept") or "")
        _touch(raw, c, now, valence=0.6, effort=0.1, understanding=str(r.get("understanding") or ""))

    for r in _iter_json(_RECEIPTS):                    # this topic cost me / I failed at it
        topic = str(r.get("topic") or "")
        for w in _WORD.findall(topic.lower()):
            _touch(raw, w, float(r.get("ts") or now), valence=-0.4, effort=0.5)

    for r in _iter_json(_MENTOR):
        filled = {str(lr.get("concept") or "").lower() for lr in (r.get("learned") or [])}
        for g in (r.get("gaps", {}) or {}).get("foundational_gaps", [])[:12]:
            # a gap I named but did NOT fill this round is a live deficit; a gap I named AND filled
            # is a RECOVERY, and the recovery should not be dragged down by the gap it resolved —
            # 'I struggled with this and then got it' reads positive, not neutral.
            if str(g).lower() not in filled:
                _touch(raw, str(g), float(r.get("ts") or now), valence=-0.15, effort=0.3)
        for lr in r.get("learned", []) or []:          # named a gap AND filled it -> a real recovery
            _touch(raw, str(lr.get("concept") or ""), float(r.get("ts") or now),
                   valence=0.7, effort=0.4, understanding=str(lr.get("understanding") or ""))

    for r in _iter_json(_IGN):                          # I attended to this (workspace history)
        if r.get("event") == "ignite":
            _touch(raw, str(r.get("topic") or ""), float(r.get("ts") or now), valence=0.05)

    out: dict[str, Marker] = {}
    for c, m in raw.items():
        last = m["last"]
        out[c] = Marker(concept=c,
                        valence=max(-1.0, min(1.0, m["valence"])),
                        effort=max(0.0, min(1.0, m["effort"])),
                        recency_h=(None if not last else max(0.0, (now - last) / 3600.0)),
                        learned_understanding=m["understanding"], events=m["events"])
    return out


# module-level cache: markers change only when the journals grow; rebuild is cheap but not free
_CACHE: dict[str, Marker] | None = None
_CACHE_AT: float = 0.0
_CACHE_TTL = 120.0


def marker_for(concept: str) -> Marker | None:
    """The first-person trace for one concept, or None if the self has no history with it."""
    global _CACHE, _CACHE_AT
    now = time.time()
    if _CACHE is None or now - _CACHE_AT > _CACHE_TTL:
        _CACHE = build_markers()
        _CACHE_AT = now
    return _CACHE.get(concept.strip().lower())


def stance(concept: str) -> str:
    """A perspective phrase the realizer MAY prepend — grounded in the real trace, or empty.

    Empty is the honest default: a concept with no history gets no stance, exactly as an ungrounded
    fact gets no assertion. The phrases report the trace, they do not dramatize it."""
    m = marker_for(concept)
    if m is None or not m.has_history():
        return ""
    if m.effort >= 0.5 and m.valence < 0:
        return f"{concept} is something I struggled with"
    if m.valence >= 0.5 and m.recency_h is not None and m.recency_h < 48:
        return f"{concept} is something I only recently came to understand"
    if m.valence >= 0.4:
        return f"{concept} is familiar to me"
    if m.valence < -0.2:
        return f"{concept} is something I have gotten wrong before"
    return ""


def revisit_priority(concepts: list[str]) -> list[str]:
    """Order concepts the way a mind returns to what it has invested in: hard-won and recently
    understood first (rumination bias). Concepts with no history keep their given order, last."""
    scored = []
    for i, c in enumerate(concepts):
        m = marker_for(c)
        if m is None:
            scored.append((0.0, i, c))
        else:
            # effort invested + recency lift; a purely negative-valence scar is revisited too
            score = m.effort + (0.5 if (m.recency_h is not None and m.recency_h < 72) else 0.0) \
                + max(0.0, -m.valence) * 0.5
            scored.append((score, i, c))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [c for _, _, c in scored]
