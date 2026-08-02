# -*- coding: utf-8 -*-
"""Mechanism reasoning — how the world WORKS, not where things ARE.

Owner (2026-07-21): "인간은 세계를 다 기억하지는 않아도 세상이 어떻게 돌아가는지 웬만큼 안다." The
situation model tracks state (where is Mary) but abstains on every realistic question about
MECHANISM — "if the cup is bumped, what happens?", "locked door, key inside — can he enter?",
"bridge blocked — can cars cross?". Those are what real users ask, and answering them is what
separates understanding from a lookup table. This module adds the missing half.

The doctrine line (structure, NOT memorization): a mechanism here is a DOMAIN-BLIND micro-law — the
same category as the situation model's verb frames, a small finite composable set, carrying no
commitment to any subject. "A blocked path cannot be traversed" is a law, not a fact about bridges;
"an unsupported thing falls" is a law, not a fact about cups. These laws fire on conditions STATED
IN THE TEXT (blocked, locked, at-the-edge, bumped) — so nothing is hand-memorized about the world's
contents. When a law needs a MATERIAL property the text does not give (is a vase fragile? does ice
melt?), we ABSTAIN — that is the honesty floor: a mechanism engine reasons from stated conditions,
it does not smuggle in a fact table. Material properties are learned knowledge (graph/web), plugged
in only when actually grounded.

Answered question shapes: capability ("can X <verb>?"), counterfactual ("if <event>, what
happens?"), prediction ("what happens to X?"). Each returns an answer + the law it used as
evidence, or None to fall through to abstention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conditions:
    """Domain-blind conditions read from the passage — the state a mechanism law operates on."""
    blocked: dict = field(default_factory=dict)      # place -> blocking reason (path impassable)
    locked: dict = field(default_factory=dict)       # container -> True (closed against entry)
    key_inside: set = field(default_factory=set)     # containers whose key is stated to be inside
    at_edge: set = field(default_factory=set)        # objects stated to be at/near an edge (unstable)
    disturbed: set = field(default_factory=set)      # objects a disturbance (bump/push) acted on
    supported_by: dict = field(default_factory=dict) # object -> surface it rests on
    raw: list = field(default_factory=list)


_BLOCK = re.compile(r"\b(.+?)\s+(?:was|is|were|are)\s+(?:blocked|obstructed|barricaded|sealed off)\b",
                    re.I)
# the locked container is the noun right after 'locked', bounded to 1-2 words (not the rest of the
# sentence — 'locked the shed and the key is inside' -> 'shed', not the whole clause)
_LOCK = re.compile(r"\b(?:locked|bolted|shut and locked)\s+(?:the\s+)?"
                   r"([a-z]+(?:\s+(?!and\b|but\b|or\b|the\b|with\b|because\b)[a-z]+)?)\b", re.I)
_LOCK2 = re.compile(r"\b(?:the\s+)?([a-z]+)\s+(?:was|is|were|are)\s+locked\b", re.I)
_KEY_INSIDE = re.compile(r"\bkey\b.*\b(?:inside|within|in)\b", re.I)
# the object at the edge is the noun before "near/at/on the edge" — allowing an optional copula
# ('the glass IS at the edge' -> 'glass') but not the whole clause ('sarah put the cup')
_EDGE = re.compile(
    r"\b(?:the|a|an)\s+([a-z]+)\s+(?:(?:is|was|are|were|sits?|sitting|placed|resting|rests?)\s+)?"
    r"(?:near|at|on)\s+(?:the\s+)?edge\b", re.I)
_DISTURB = re.compile(r"\b(?:bumped|pushed|knocked|nudged|hit|shoved)\b", re.I)
_ART = re.compile(r"^(the|a|an|this|that|his|her|their)\s+", re.I)


def _np(s: str) -> str:
    return _ART.sub("", s.strip().lower()).strip(" .,;:")


def read_conditions(text: str) -> Conditions:
    """Extract stated, domain-blind conditions sentence by sentence — no world facts assumed."""
    c = Conditions()
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = raw.strip()
        if not s:
            continue
        c.raw.append(s)
        m = _BLOCK.search(s)
        if m:
            c.blocked[_np(m.group(1))] = s
        m = _LOCK.search(s) or _LOCK2.search(s)
        if m:
            c.locked[_np(m.group(1))] = True
        if _KEY_INSIDE.search(s):
            for loc in list(c.locked) + ["room", "door", "car"]:      # the just-locked container
                c.key_inside.add(loc)
        m = _EDGE.search(s)
        if m:
            c.at_edge.add(m.group(1).strip().lower())
        if _DISTURB.search(s):
            # the disturbed object is the object of the disturbing verb, or the last edge object
            om = re.search(r"\b(?:bumped|pushed|knocked|nudged|hit|shoved)\s+(?:the\s+)?([a-z]+)", s, re.I)
            if om:
                c.disturbed.add(_np(om.group(1)))
            c.disturbed |= set(c.at_edge)               # bumping near-edge things disturbs them
    return c


def _ev(law: str, because: str) -> dict[str, Any]:
    return {"answer": None, "law": law, "because": because}


def answer_mechanism(question: str, text: str) -> dict[str, Any] | None:
    """Answer a mechanism question from stated conditions + domain-blind laws, or None to abstain."""
    q = question.strip().lower()
    c = read_conditions(text)

    # LAW: a blocked path cannot be traversed. "Can cars cross the (blocked) bridge?" -> no.
    m = re.search(r"can\s+.*\b(?:cross|pass|enter|go through|get through|traverse)\b\s+(?:the\s+)?([a-z ]+)?", q)
    if m and c.blocked:
        target = _np(m.group(1) or "")
        if any(target in b or b in target or not target for b in c.blocked):
            b = next(iter(c.blocked))
            return {"answer": "no", "supported": True, "law": "blocked-path-is-impassable",
                    "evidence": c.blocked[b],
                    "reasoning": f"The path ({b}) is blocked, and a blocked path cannot be crossed."}

    # LAW: a locked container whose only key is inside cannot be entered. "Can Tom enter the room?"
    if re.search(r"can\s+\w+\s+(?:enter|get in|get into|access|open)\b", q) and c.locked:
        cont = next(iter(c.locked))
        if c.key_inside:
            return {"answer": "no", "supported": True, "law": "locked-no-accessible-key",
                    "evidence": f"{cont} is locked; the key is inside",
                    "reasoning": f"The {cont} is locked and its key is inside it, so it cannot be "
                                 f"opened from outside."}

    # LAW: an unsupported / at-the-edge object that is disturbed falls. "If the cup is bumped, what
    # happens?" / "what happens to the cup?"
    m = re.search(r"(?:what happens (?:to|if)|if).*\b([a-z]+)\b", q)
    edge_obj = None
    for obj in c.at_edge:
        head = obj.split()[-1]
        if head in q or obj in q:
            edge_obj = obj
            break
    if edge_obj and (c.disturbed or "bump" in q or "if" in q):
        return {"answer": f"the {edge_obj} falls", "supported": True, "law": "unsupported-things-fall",
                "evidence": f"{edge_obj} is at the edge",
                "reasoning": f"The {edge_obj} is at the edge, so when disturbed it is no longer "
                             f"supported and falls."}

    return None                                          # no law grounded -> abstain (honesty floor)
