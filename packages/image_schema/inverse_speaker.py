# -*- coding: utf-8 -*-
"""The speaker, inverted. An index from what it SAYS back to what it MEANT — built from the speaker.

Understanding is regeneration: propose a structure, regenerate it, keep what reproduces the sentence.
R1 measured that inverse at 91.2% on ATANOR's own speech and only 5.5% UNIQUE, and I concluded the
realizer was too weak to constrain anything. That conclusion was premature. My proposer had been
handing arbitrary SUBSTRINGS to the verifier as candidate relations, and the realizer's fallback for an
unknown relation is `{s} {rel} {o}` — concatenation — so every substring trivially regenerated itself.
The ambiguity was an artefact of the proposer, not a property of the method.

A relation is not a substring. It is a member of a KNOWN VOCABULARY, and the speaker already knows what
each one sounds like. So the inverse is not a search over splits at all:

    for each relation the speaker knows, ask it to say ['qsubj', relation, 'qobj']
    whatever appears between qsubj and qobj is that relation's SURFACE FORM
    invert that map, and a sentence's middle span names its relation directly

Two properties this has that the substring search did not.

    it is derived, not written    every entry comes from calling the speaker. Teach the speaker a new
                                  construction and the index gains it on the next build, with nothing
                                  edited here. That is the coupling the design document promised:
                                  comprehension grows exactly as generation grows.
    it is O(1) per split          a lookup, not 376 regenerations, so the verifier can afford to check
                                  every candidate exactly rather than approximately.

WHAT IT STILL CANNOT DO, stated so the number is not mistaken for more than it is. Collisions are real:
several relations can share a surface form, and the index returns all of them rather than choosing. It
does not resolve them and must not pretend to — that is the abstention the doctrine requires, and the
collision rate is reported rather than hidden.
"""
from __future__ import annotations

import re
from collections import defaultdict

from packages.realizer_struct.frame_realizer import realize, realize_variants

_SUBJ = "qsubj"
_OBJ = "qobj"
_W = re.compile(r"[^a-z0-9 ]+")


def norm(s: str) -> str:
    return " ".join(_W.sub(" ", (s or "").lower()).split())


def surfaces_of(relation: str) -> list:
    """EVERY way the speaker can say this relation, not just its canonical one.

    The first version asked the speaker once and indexed one surface form per relation. Constructions
    mined from human text were installed as alternatives and the index never saw them -- built but not
    wired, which is the pathology diagnosed elsewhere in this repo and committed again here on the same
    day. A relation has several constructions and the inverse must know all of them, because a sentence
    using one the index lacks is a sentence that cannot be regenerated and therefore cannot be read."""
    out = []
    for said in realize_variants([[_SUBJ, relation, _OBJ]]):
        n = norm(said)
        if not n.startswith(_SUBJ) or _OBJ not in n:
            continue
        mid = n[len(_SUBJ):n.rindex(_OBJ)].strip()
        if mid not in out:
            out.append(mid)
    return out


def build_index(relations) -> tuple[dict, dict]:
    """surface form -> the relations that produce it, and relation -> all its surface forms."""
    fwd, inv = {}, defaultdict(list)
    for r in relations:
        ms = surfaces_of(r)
        if not ms:
            continue
        fwd[r] = ms
        for m in ms:
            if r not in inv[m]:
                inv[m].append(r)
    return dict(inv), fwd


class InverseSpeaker:
    """Sentence -> the structures that regenerate it. The verifier is still exact regeneration; the
    index only decides WHAT IS WORTH CHECKING, which is the proposer's whole job."""

    def __init__(self, relations):
        self.inv, self.fwd = build_index(relations)
        self.collisions = {m: rs for m, rs in self.inv.items() if len(rs) > 1}

    def candidates(self, sentence: str, max_len: int = 18):
        w = sentence.split()
        if not (2 < len(w) <= max_len):
            return []
        out = []
        for i in range(1, len(w)):
            for j in range(i, len(w)):
                mid = norm(" ".join(w[i:j]))
                for rel in self.inv.get(mid, ()):
                    out.append([" ".join(w[:i]), rel, " ".join(w[j:])])
        return out

    def understand(self, sentence: str):
        """Structures that REGENERATE the sentence under ANY construction the speaker knows for the
        relation. Empty is an abstention, not a wrong answer."""
        target = norm(sentence)
        hits = []
        for c in self.candidates(sentence):
            try:
                if any(norm(v) == target for v in realize_variants([c])):
                    hits.append(c)
            except Exception:
                continue
        return hits

    # ---------------------------------------------------------------- ranking
    @staticmethod
    def description_length(cand) -> tuple:
        """How much of the sentence the GRAMMAR failed to explain. Lower is better.

        The residual ambiguity is not pollution and not the concatenation fallback — both were
        hypothesised and both were measured wrong. Looked at directly, it is a genuine collision
        between frames:

            is_a         "{s} is {det} {o}"   + (Albedo, is_a,        ratio)    -> "Albedo is a ratio."
            has_property "{s} is {o}"         + (Albedo, has_property, a ratio) -> "Albedo is a ratio."

        Identical to the character. The determiner sits inside the frame in one and inside the argument
        in the other, and English does not distinguish them at this level. A filter cannot settle that
        without knowing which words are nouns; a RANKING can, on a principle this project already uses
        for schema induction — minimum description length. The structure whose frame consumes more of
        the sentence leaves less to be memorised in its arguments, so it is the better account of it.

        Ties are broken by the shorter arguments, and then lexically, so the order is deterministic and
        a tie is still visible as a tie rather than as a silent choice."""
        subj, rel, obj = cand
        return (len(norm(subj).split()) + len(norm(obj).split()), len(norm(rel)) * -1, str(cand))

    def best(self, sentence: str):
        """The MDL-preferred structure, and how many others regenerated the sentence equally well."""
        hits = self.understand(sentence)
        if not hits:
            return None, 0
        ranked = sorted(hits, key=self.description_length)
        return ranked[0], len(hits)
