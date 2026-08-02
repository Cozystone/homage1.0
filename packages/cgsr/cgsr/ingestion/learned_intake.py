# -*- coding: utf-8 -*-
"""Intake without a verb list: the learned tagger proposes, three gates decide.

WHAT IS BEING REPLACED, and why it is the root of everything measured yesterday.
`decomposer.extract_english_case_roles` scans for the first token in `ENGLISH_VERB_LEMMAS` and, finding
none, returns `([], "")` -- the sentence is silently discarded. That lexicon holds THIRTY-ONE verbs and
every one is definitional: is, are, has, contains, includes, defines, describes, represents, refers,
means, consists, provides, supports, requires, stores, tracks, manages, enables, allows, connects,
records, becomes. No action verb at all. Downstream:

    98% of the graph's 223,592 bones are is_a (56%) or alias (42%)
    the frame miner acquired 2 constructions, both already hand-written, net contribution zero
    the speaker had 12 templates and concatenated everything else
    and in the Atari line, death pays exactly 0.00 reward because nothing represents consequences

One filter, five layers of symptom.

THE REPAIR IS NOT A LONGER LIST. A list of 10,000 verbs would be the same training wheel with more
spokes, and the standing rule is that rules are scaffolding for a learned router. So the proposal comes
from `packages.cgsr.frame_tagger`, which was fitted from zero weights on spans the corpus already
contained, and knows no verbs at all.

THREE GATES, AND THE THIRD IS THE ONE THAT BITES.

    well-formedness   SUBJ before REL before OBJ, each contiguous. A tag sequence that interleaves
                      roles is not a reading of the sentence.
    faithfulness      the triple must REGENERATE the sentence. This catches invention and dropping --
                      but on its own it is VACUOUS, because the speaker echoes an unknown relation
                      verbatim, so any three-way split of any sentence regenerates it. Measured, not
                      assumed: that is exactly how R1's 91.2% turned out to be worthless.
    entrenchment      the relation's surface form must have been seen with several DISTINCT argument
                      pairs. A construction is a pattern across arguments; a string seen once with one
                      pair is a memorised sentence. This is the criterion that separates a real relation
                      from a lucky parse, and it is what a random-span control fails.

WHAT THIS MODULE DOES NOT DO. It does not replace the shipped filter yet. `brain_link_pool` and the
verified-store path call the old one and a swap before the numbers are in would be exactly the
build-then-measure inversion this repo keeps paying for. It is measured beside the incumbent first.
"""
from __future__ import annotations

import collections
import re
from typing import Iterable

_W = re.compile(r"[^a-z0-9 ]+")


def norm(s: str) -> str:
    return " ".join(_W.sub(" ", (s or "").lower()).split())


def ordered_spans(tokens: list, tags: list):
    """SUBJ / REL / OBJ as contiguous, ordered blocks, or None if the tagging is not a reading."""
    pos = {1: [], 2: [], 3: []}
    for i, t in enumerate(tags):
        if t in pos:
            pos[t].append(i)
    if not pos[1] or not pos[2]:
        return None
    for k in (1, 2, 3):
        idx = pos[k]
        if idx and idx != list(range(idx[0], idx[-1] + 1)):
            return None                                  # interleaved: not a reading
    if pos[1][-1] >= pos[2][0]:
        return None
    if pos[3] and pos[2][-1] >= pos[3][0]:
        return None
    join = lambda ks: " ".join(tokens[i] for i in ks)     # noqa: E731
    return join(pos[1]), join(pos[2]), (join(pos[3]) if pos[3] else "")


def faithful(triple, sentence: str) -> bool:
    """Does the triple say the sentence back? Catches invention and dropping, and nothing subtler."""
    from packages.realizer_struct.frame_realizer import realize_variants
    target = norm(sentence)
    try:
        return any(norm(v) == target for v in realize_variants([[triple[0], triple[1], triple[2]]]))
    except Exception:
        return False


class Entrenchment:
    """How many DISTINCT argument pairs a connective has been seen with. Built by observing, once."""

    def __init__(self, min_pairs: int = 3):
        self.min_pairs = min_pairs
        self.pairs: dict = collections.defaultdict(set)

    def observe(self, triple) -> None:
        s, r, o = triple
        self.pairs[norm(r)].add((norm(s), norm(o)))

    def entrenched(self, relation: str) -> bool:
        return len(self.pairs.get(norm(relation), ())) >= self.min_pairs

    def summary(self) -> dict:
        return {"surfaces": len(self.pairs),
                "entrenched": sum(1 for v in self.pairs.values() if len(v) >= self.min_pairs)}


class LearnedIntake:
    """sentence -> triple, or nothing. No verb list anywhere in the path."""

    def __init__(self, tagger, entrenchment: Entrenchment | None = None):
        self.tagger = tagger
        self.ent = entrenchment or Entrenchment()
        self.counts = collections.Counter()

    def propose(self, sentence: str):
        toks = norm(sentence).split()
        if not (3 <= len(toks) <= 32):
            self.counts["too short or too long"] += 1
            return None
        tri = ordered_spans(toks, self.tagger.tag(toks))
        if tri is None:
            self.counts["not a reading"] += 1
            return None
        if not faithful(tri, sentence):
            self.counts["unfaithful"] += 1
            return None
        self.counts["proposed"] += 1
        return tri

    def learn_pass(self, sentences: Iterable[str]) -> int:
        """First pass: observe which connectives recur across different arguments."""
        n = 0
        for s in sentences:
            tri = self.propose(s)
            if tri:
                self.ent.observe(tri)
                n += 1
        return n

    def admit(self, sentence: str):
        """Second pass: admit only what the corpus has entrenched as a construction."""
        tri = self.propose(sentence)
        if tri is None:
            return None
        if not self.ent.entrenched(tri[1]):
            self.counts["not entrenched"] += 1
            return None
        self.counts["admitted"] += 1
        return tri
