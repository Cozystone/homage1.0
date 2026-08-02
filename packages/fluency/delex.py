# -*- coding: utf-8 -*-
"""Delexicalization + copy mechanism.

A grounded clause frame like ``{s} is {det} {o}`` is ALREADY a delexicalized skeleton: ``is`` is a
function word, and ``{s}``/``{o}`` are slots. This module makes that separation a first-class,
reusable object and adds the COPY GATE the fluency doctrine requires:

  * REGISTER SKELETON — the ordered function words / structure with typed placeholders. It contains
    ZERO entities, so it can be shared across millions of answers and cannot memorize any entity.
  * SLOTS — typed references (SUBJ / OBJ / DET / REL). CONTENT slots (SUBJ, OBJ, REL) are filled by
    COPYING verbatim from the grounding; FUNCTION slots (DET) come from the morphology floor.
  * COPY GATE — ``copy_fill`` emits a content slot's value only if that value is present in the
    grounding. A slot whose source is not grounded is copied-empty; a clause missing a required
    content slot ABSTAINS (is dropped). An entity absent from the grounding therefore can never be
    invented — this is exactly propose->verify: a proposer may suggest a bone, but only grounded
    strings reach the surface.

We reuse ``realizer_struct.frame_realizer``'s frame lexicon and morphology helpers so the linguistic
knowledge lives in one place (extend, don't duplicate).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from packages.realizer_struct import frame_realizer as fr

# ── grounding: the closed set of strings a copy is allowed to draw from ───────────────────────────
_WORD = re.compile(r"[A-Za-z0-9]+")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


@dataclass
class Grounding:
    """The verified source a copy may draw from. Membership is the copy gate: a content string is
    emittable iff it (or its individual words) trace here. Built from bones by default (self-
    grounded), but a caller may pass a RESTRICTED grounding — e.g. only graph-verified facts — so a
    proposer's unverified bone is dropped at fill time (propose->verify)."""

    values: set[str] = field(default_factory=set)          # normalized whole strings (lowercased)
    words: set[str] = field(default_factory=set)           # individual lowercased word tokens

    @classmethod
    def from_bones(cls, bones: list) -> "Grounding":
        g = cls()
        for triple in bones:
            s, r, o = (list(triple) + ["", "", ""])[:3]
            for cell in (s, o, str(r).replace("_", " ")):
                g.add(cell)
        return g

    def add(self, value: str) -> None:
        v = _norm(value).lower()
        if not v:
            return
        self.values.add(v)
        for w in _WORD.findall(v):
            self.words.add(w)

    def has(self, value: str) -> bool:
        """True iff every content word of `value` traces to the grounding. Morphology the realizer
        itself produces (plural -s/-es/-ies, demonym capitalization, a/an) is accepted as grounded:
        'birds' traces to 'bird', 'German' to 'german'. Nothing else is admitted."""
        v = _norm(value).lower()
        if not v:
            return False
        if v in self.values:
            return True
        toks = _WORD.findall(v)
        if not toks:
            return False
        return all(self._word_ok(t) for t in toks)

    def _word_ok(self, tok: str) -> bool:
        if tok in self.words:
            return True
        for stem in _depluralize(tok):                     # birds->bird, families->family
            if stem in self.words:
                return True
        return False


def _depluralize(tok: str) -> list[str]:
    out = []
    if tok.endswith("ies") and len(tok) > 3:
        out.append(tok[:-3] + "y")
    if tok.endswith("es") and len(tok) > 2:
        out.append(tok[:-2])
    if tok.endswith("s") and len(tok) > 1:
        out.append(tok[:-1])
    # irregulars the morphology floor produces
    _IRR = {"birds": "bird", "people": "person", "children": "child", "men": "man",
            "women": "woman", "mice": "mouse", "geese": "goose", "feet": "foot", "teeth": "tooth"}
    if tok in _IRR:
        out.append(_IRR[tok])
    return out


# ── the delexicalized plan ────────────────────────────────────────────────────────────────────────
_CONTENT_ROLES = ("SUBJ", "OBJ", "REL")                    # must be copied from grounding
_FUNCTION_ROLES = ("DET", "PRON")                          # morphology / closed vocab


@dataclass
class Slot:
    role: str                                              # SUBJ | OBJ | DET | REL | PRON
    key: str                                               # grounding key on the bone: s | o | rel
    value: str = ""                                        # verbatim value to copy (from grounding)
    copied: bool = False                                   # filled from grounding? False = abstained

    @property
    def is_content(self) -> bool:
        return self.role in _CONTENT_ROLES


@dataclass
class Token:
    kind: str                                              # 'LIT' (function word) | 'SLOT'
    text: str = ""                                         # LIT text
    slot: Slot | None = None


@dataclass
class ClausePlan:
    """One delexicalized clause: an ordered list of literal function words and typed slots, plus the
    morphology needed to realize it (plural subject, referring pronoun)."""

    subject: str
    relation: str
    tokens: list[Token]
    plural: bool = False
    reduced_form: str | None = None                        # e.g. 'located in {o}' for aggregation

    def skeleton(self) -> str:
        """The REGISTER SKELETON: function words + typed placeholders, ZERO entities. This string is
        what makes entity memorization impossible — the learnable/storable pattern holds no entity."""
        parts = []
        for t in self.tokens:
            if t.kind == "LIT":
                parts.append(t.text)
            else:
                parts.append(f"[{t.slot.role}]")
        return _norm(" ".join(p for p in parts if p))

    def slots(self) -> list[Slot]:
        return [t.slot for t in self.tokens if t.kind == "SLOT" and t.slot is not None]

    def content_slots(self) -> list[Slot]:
        return [s for s in self.slots() if s.is_content]


# fields the frame templates use -> slot role + grounding key
_FIELD_ROLE = {"s": ("SUBJ", "s"), "o": ("OBJ", "o"), "det": ("DET", "det"), "rel": ("REL", "rel")}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _template_to_tokens(tmpl: str, s: str, o: str, rel: str, plural: bool) -> list[Token]:
    """Parse a frame template string into LITERAL + SLOT tokens, attaching the copied source values.
    Copied values come from the bone; the COPY GATE (copy_fill) decides whether they survive."""
    det = fr._det(o)
    src = {"s": s, "o": o, "det": det, "rel": rel.replace("_", " ")}
    tokens: list[Token] = []
    pos = 0
    for m in _PLACEHOLDER.finditer(tmpl):
        lit = tmpl[pos:m.start()].strip()
        if lit:
            tokens.append(Token("LIT", text=lit))
        field_name = m.group(1)
        role, key = _FIELD_ROLE.get(field_name, ("OBJ", field_name))
        tokens.append(Token("SLOT", slot=Slot(role=role, key=key, value=src.get(key, ""))))
        pos = m.end()
    tail = tmpl[pos:].strip()
    if tail:
        tokens.append(Token("LIT", text=tail))
    return tokens


def delexicalize(bones: list) -> list[ClausePlan]:
    """Grounded bones -> a list of delexicalized ClausePlans (register skeleton + typed slots).

    One plan per (subject, relation, object). No entity is emitted here — plans carry slot values to
    be COPIED later, under the copy gate. Empty/degenerate bones produce no plan."""
    plans: list[ClausePlan] = []
    for triple in bones:
        s, r, o = (list(triple) + ["", "", ""])[:3]
        s, r, o = _norm(s), _norm(str(r)), _norm(o)
        if not s or not o:
            continue
        if r == "alias" and o.lower() == s.lower():
            continue                                       # a self-alias says nothing
        plural = fr._is_plural(s)
        frame = fr.FRAMES.get(r, fr._DEFAULT)
        tokens = _template_to_tokens(frame["tmpl"], s, o, r, plural)
        plans.append(ClausePlan(subject=s, relation=r, tokens=tokens, plural=plural,
                                reduced_form=frame.get("reduced")))
    return plans


def copy_fill(plan: ClausePlan, grounding: Grounding, *, subject_ref: str | None = None,
              agree_plural: bool | None = None) -> str:
    """Realize ONE clause by copying slot values from the grounding ONLY.

    The copy gate: a CONTENT slot (SUBJ/OBJ/REL) is emitted only if its value traces to the
    grounding. If any required content slot is ungrounded, the clause ABSTAINS (returns "") — it is
    never filled with an invented string. Function slots (DET article) come from the morphology
    floor. `subject_ref` overrides the SUBJ surface (e.g. a pronoun, or "" to drop it in a
    conjunction) without changing the copy gate. `agree_plural` overrides subject-verb agreement
    (e.g. singular 'they' takes plural verb forms)."""
    out: list[str] = []
    for t in plan.tokens:
        if t.kind == "LIT":
            out.append(t.text)
            continue
        slot = t.slot
        if slot.role == "DET":
            out.append(slot.value)                         # morphology floor, not a content copy
            slot.copied = True
            continue
        if slot.role == "SUBJ" and subject_ref is not None:
            out.append(subject_ref)                        # pronoun/backref/drop: still not invented
            slot.copied = True
            continue
        if grounding.has(slot.value):
            out.append(slot.value)
            slot.copied = True
        else:
            slot.copied = False                            # ungrounded -> abstain this clause
            return ""
    text = _norm(" ".join(p for p in out if p))
    plural = plan.plural if agree_plural is None else agree_plural
    return fr._agree(text, plural)


def realize_reduced(plan: ClausePlan, grounding: Grounding) -> str:
    """The reduced (aggregating) surface for a clause, e.g. 'located in Germany' — used when the
    register appends a clause to the previous one instead of opening a new sentence. Copy-gated the
    same way: the object must trace to grounding or the reduced form abstains."""
    if not plan.reduced_form:
        return ""
    obj_slots = [s for s in plan.slots() if s.role == "OBJ"]
    if obj_slots and not grounding.has(obj_slots[0].value):
        return ""
    obj = obj_slots[0].value if obj_slots else ""
    return _norm(plan.reduced_form.format(o=obj))
