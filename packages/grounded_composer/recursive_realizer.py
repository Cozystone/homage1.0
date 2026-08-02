# -*- coding: utf-8 -*-
"""Recursive construction realizer — infinite flexibility from finite means.

The owner's final Fable5 directive: implement the STRUCTURAL answer to
 . An LLM buys flexibility with probability (and pays in
hallucination). Language itself buys it with RECURSION: a finite inventory of
constructions, composed recursively, yields unboundedly many novel sentences
(Humboldt's "infinite use of finite means"). This module is that engine for
the grounded graph:

 fact -> clause (construction per predicate class)
 clause + head -> embedding " … "
 object -> recursive expansion "[ ] …"
 clauses -> coordination "…, …"

so ( is_a ) + (located_in ) + ( 968) realizes as
" , 968 ." — a sentence that
exists in NO template, composed at answer time, with every content morpheme
traceable to a stated fact and every structural morpheme drawn from the closed
construction inventory below ( ·· — the LAD/surface
layer, which is the one place hand-written linguistic knowledge is allowed).

The combinatorics are the point: n modifier facts give factorially many valid
embedding orders and 2^n subset choices across depth levels — infinite in the
limit of graph growth — while the hallucination-safety proof stays one line:
output ⊆ closure(constructions ∪ fact-strings)."""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from typing import Any

# ---- closed construction inventory (structural morphemes only) --------------

# {o} is always a verbatim fact object; nothing else is content.
_PRENOMINAL = {
    "located_in": "{o}에 위치한",
    "country": "{o}에 속한",
    "part_of": "{o}의 일부인",
    "capital": "수도가 {o}인",
    "인구": "인구 {o}의",
    "면적": "면적 {o}의",
    "설립": "{o}에 세워진",
    "used_for": "{o}에 쓰이는",
    "made_of": "{o}(으)로 이루어진",
    "author": "{o}이(가) 지은",
}
_CLAUSE = {  # coordinated tail clauses — each carries its OWN full ending
    "capital": "수도는 {o}입니다",
    "인구": "인구는 {o}명입니다",
    "면적": "면적은 {o}입니다",
    "설립": "{o}에 세워졌습니다",
    "통화": "통화는 {o}입니다",
    "언어": "언어는 {o}입니다",
    "대륙": "{o}에 속합니다",
}
_HEAD_PREDS = ("is_a", "defined_as")   # the head noun / identity slot


def _josa_final(word: str, with_batchim: str, without: str) -> str:
    c = ord(word[-1]) if word else 0
    if 0xAC00 <= c <= 0xD7A3:
        return with_batchim if (c - 0xAC00) % 28 else without
    return without


@dataclass
class Realization:
    text: str
    facts_used: list[tuple[str, str, str]] = field(default_factory=list)
    constructions: list[str] = field(default_factory=list)
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "facts_used": self.facts_used,
                "constructions": self.constructions, "depth": self.depth,
                "guarantees": {"content_from_stated_facts_only": True,
                               "structure_from_closed_inventory_only": True}}


_EMBED_PREDS = ("located_in", "part_of", "country")   # clean containment only


def _expand_object(obj: str, lookup: Any, depth: int,
                   used: list, cons: list, subject: str = "") -> str:
    """RECURSION: an embedded object may itself carry one prenominal modifier
 ("" -> " "), depth-bounded. lookup(term)
 returns that term's facts, or None."""
    if depth <= 0 or lookup is None:
        return obj
    try:
        for s, p, o in (lookup(obj) or [])[:8]:
            form = _PRENOMINAL.get(p)
            # circularity guard: never embed a fact that points back to the


            if (form and p in _EMBED_PREDS and o and o != obj
                    and o != subject and subject not in o and len(o) <= 24):
                used.append((s, p, o))
                cons.append(f"prenominal:{p}@embed")
                return form.format(o=_expand_object(o, lookup, depth - 1, used, cons, subject)) + " " + obj
    except Exception:
        pass
    return obj


def realize(subject: str, facts: list[tuple[str, str, str]], *,
            max_modifiers: int = 2, embed_depth: int = 1,
            lookup: Any = None) -> Realization | None:
    """Compose ONE natural sentence from verified facts by recursive embedding.

 Head = the is_a/defined_as fact (identity noun). Up to `max_modifiers`
 relation facts become modifiers stacked before the head; leftover
 facts join as one coordinated tail clause. Returns None when there is no
 head or fewer than two usable facts — single facts stay on the precise
 template path (this engine exists for COMPOSITION, not to replace it)."""
    head = None
    mods: list[tuple[str, str, str]] = []
    tail: list[tuple[str, str, str]] = []
    # location is not identity: an is_a object that ALSO appears as this


    _placed = {str(o) for _s, p, o in facts if p in ("located_in", "country", "대륙")}
    for s, p, o in facts:
        if not o or p in ("alias", "sense"):
            continue
        if (head is None and p in _HEAD_PREDS and len(str(o)) <= 60
                and not re.search(r"\d", str(o)[:12])
                and re.search(r"[가-힣]", str(o))     # the head noun must speak Korean
                and str(o) not in _placed):           # location is not identity
            head = (s, p, str(o))
        elif (p in _PRENOMINAL and len(mods) < max_modifiers and len(str(o)) <= 40
                and str(o) != subject):
            mods.append((s, p, str(o)))
        elif p in _CLAUSE:
            tail.append((s, p, str(o)))
    if head is None or (len(mods) + len(tail)) < 1:
        return None

    used: list[tuple[str, str, str]] = [head]
    cons: list[str] = [f"head:{head[1]}"]
    # head noun: for is_a the object IS the noun; a defined_as head keeps only
    # its first clause as an appositive noun phrase when short enough
    head_noun = head[2]
    if head[1] == "defined_as":
        head_noun = head_noun.split(".")[0].split(",")[0][:40]


        # would claim France is a name — measured)


        head_noun = re.sub(r"(?<=나라)\s*(이름|명칭)$", "", head_noun).strip() or head[2][:40]

    # prenominal stack, phase-coherent order when available (nearest to the
    # head noun last — Korean modifiers read outward-in)
    try:
        from .phase_flow import flow_order
        mods = flow_order(head, mods) if len(mods) > 1 else mods
    except Exception:
        pass
    parts = []
    for s, p, o in mods:
        used.append((s, p, o))
        cons.append(f"prenominal:{p}")
        parts.append(_PRENOMINAL[p].format(
            o=_expand_object(o, lookup, embed_depth, used, cons, subject)))
    modifier = ", ".join(parts)

    topic = subject + _josa_final(subject, "은", "는")
    copula = "입니다" if _josa_final(head_noun, "이", "") == "" else "이 됩니다"

    sentence = topic + " " + (modifier + " " if modifier else "") + head_noun + "입니다"


    if tail:
        clauses = []
        for s, p, o in tail[:2]:
            used.append((s, p, o))
            cons.append(f"clause:{p}")
            clauses.append(_CLAUSE[p].format(o=o))
        if len(clauses) == 2:

            mid = clauses[0]
            for _end in ("입니다", "습니다"):
                if mid.endswith(_end):
                    mid = mid[: -len(_end)]
                    break
            joined = mid + "이고, " + clauses[1]
        else:
            joined = clauses[0]
        sentence = sentence[:-3] + "이며, " + joined

    depth = 1 + (1 if any("@embed" in c for c in cons) else 0)
    return Realization(text=sentence + ".", facts_used=used,
                       constructions=cons, depth=depth)
