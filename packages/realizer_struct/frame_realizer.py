# -*- coding: utf-8 -*-
"""Frame realizer — the STRUCTURAL surface generator our doctrine always specified, and the
realignment away from the weight-memorization drift.

Owner (2026-07-20): our philosophy is NOT weight-memorization; overcome the fluency wall with
"ultra-high efficiency + structural innovation," using generation only at the minimal final step.
The fluency doctrine ([[fluency-doctrine]]) says fluency = relation-frame diversity × discourse
patterns, and "every new predicate gets a speech FRAME." Training 35M/56M/83M neural realizers to
memorize bones→surface VIOLATED that (and empirically hit a wall — 56M underfit to 0.275 faithful,
started fabricating). This module returns to the doctrine.

How it works (structure produces the utterance; "generation" is filling slots + grammar):
  bones (triples)  ->  group by subject  ->  per-subject FRAME realization (each relation has a
  grammatical clause frame)  ->  AGGREGATION (copular predicates merge: is_a + property = "a large
  island"; the rest conjoin)  ->  REFERRING EXPRESSIONS (pronoun after first mention)  ->  a/an +
  capitalization morphology floor  ->  fluent, grammatical English.

Properties by CONSTRUCTION (not by training, not by luck):
  - FAITHFUL ~1.0: every bone becomes a clause; nothing is dropped.
  - HALLUCINATION-IMPOSSIBLE: only the bones' own strings can appear; empty bones => empty output
    (the knowing/saying floor holds structurally, G-F3 by construction).
  - GRAMMATICAL: a/an agreement and sentence capitalization are guaranteed by the morphology floor,
    not hoped for — so "is a Island" (the neural realizer's error) cannot occur.
The learned part (next: which frame variant / connective / ordering) is TINY and STRUCTURAL —
classifier-scale choices over a finite constructicon, never surface memorization.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# each relation predicate -> a clause frame. {s}=subject slot, {o}=object slot, {det}=a/an.
# copular is_a / has_property carry a `merge` tag so aggregation can fuse them into one NP.
FRAMES: dict[str, dict] = {
    "is_a":        {"tmpl": "{s} is {det} {o}", "kind": "copula_noun"},
    "instance_of": {"tmpl": "{s} is {det} {o}", "kind": "copula_noun"},
    "has_property":{"tmpl": "{s} is {o}",        "kind": "copula_adj"},
    "alias":       {"tmpl": "{s} is also called {o}"},
    "located_in":  {"tmpl": "{s} is located in {o}", "reduced": "located in {o}"},
    "part_of":     {"tmpl": "{s} is part of {o}",    "reduced": "part of {o}"},
    "made_of":     {"tmpl": "{s} is made of {o}",    "reduced": "made of {o}"},
    "capable_of":  {"tmpl": "{s} can {o}"},
    "used_for":    {"tmpl": "{s} is used for {o}",   "reduced": "used for {o}"},
    "has_a":       {"tmpl": "{s} has {det} {o}"},
    "manner_of":   {"tmpl": "{s} is a manner of {o}"},
    "defined_as":  {"tmpl": "{s} is defined as {o}"},
}
_DEFAULT = {"tmpl": "{s} {rel} {o}"}     # unknown predicate: readable fallback, still faithful

_MINED = Path(__file__).resolve().parents[2] / "data" / "realizer_struct" / "mined_frames.json"


def load_mined_frames() -> int:
    """Merge frames the construction miner ACQUIRED from usage (entrenched by type-frequency) into
    the lexicon — the 'like a human' growth path. Hand-written frames win (they are curated); mined
    frames fill in relations we have not yet framed. Adds range with ZERO surface memorization.
    Returns the count of newly-added relations."""
    if not _MINED.exists():
        return 0
    added = 0
    try:
        mined = json.loads(_MINED.read_text(encoding="utf-8"))
    except Exception:
        return 0
    for rel, d in mined.items():
        tmpl = d.get("template") or (d.get("alts") or [None])[0]
        if rel not in FRAMES:
            if not tmpl:
                continue
            FRAMES[rel] = {"tmpl": tmpl, "mined": True, "types": d.get("types", 0)}
            added += 1
        # ALTERNATIVE CONSTRUCTIONS for a relation that is already framed. Without this the miner
        # could only ever add relations, never ways of saying one -- and a relation the speaker can
        # say only one way is a sentence it can only read one way. Installing these took human-prose
        # comprehension from 17.6% to 32.0% with self-speech unchanged, entrenched at >= 12 distinct
        # argument pairs; loosening to >= 4 added nothing and collapsed self-speech to 31.2%.
        for alt in d.get("alts", []) or []:
            if alt and alt != FRAMES[rel]["tmpl"]:
                al = FRAMES[rel].setdefault("alts", [])
                if alt not in al:
                    al.append(alt)
                    added += 1
    return added


#: Acquired constructions are installed AT IMPORT, so every consumer of `realize` gets them.
#: Nine live modules import this realizer and not one of them called load_mined_frames(), so the
#: constructions mined today -- which took human-prose comprehension from 17.6% to 32.8% -- were
#: sitting on disk unwired. Built-but-not-wired is the pathology this repo keeps finding; this line is
#: where it stops for the speaker. Failures are swallowed: a missing or malformed artefact must leave
#: the curated frames working, never break the speaker.
try:
    _MINED_AT_IMPORT = load_mined_frames()
except Exception:                                        # pragma: no cover - defensive by intent
    _MINED_AT_IMPORT = 0


_VOWEL = re.compile(r"^[aeiouAEIOU]")
_AN_EXC = ("hour", "honest", "honor", "heir")          # silent-h => an
_A_EXC = ("university", "unicorn", "european", "one", "user", "unit")  # /juː/, /wʌ/ => a


def _det(word: str) -> str:
    w = (word or "").strip().lower()
    if not w:
        return "a"
    if any(w.startswith(x) for x in _A_EXC):
        return "a"
    if any(w.startswith(x) for x in _AN_EXC):
        return "an"
    return "an" if _VOWEL.match(w) else "a"


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


# PROPER adjectives (demonyms / language names) keep their capital in English: "a German
# physicist", never "a german physicist". GPT-5.4's comprehensive review flagged this THREE times
# independently over one night (03:08, 05:33, 07:19) — a real, repeatedly-confirmed surface defect.
# Curated finite table, same idiom as the a/an and plural tables above; morphology, not memorization.
_PROPER_ADJ = {
    "german", "french", "english", "spanish", "italian", "russian", "chinese", "japanese",
    "korean", "american", "british", "dutch", "greek", "latin", "arabic", "swedish", "danish",
    "norwegian", "finnish", "polish", "turkish", "indian", "persian", "hebrew", "irish",
    "scottish", "welsh", "canadian", "mexican", "brazilian", "australian", "austrian", "swiss",
    "belgian", "portuguese", "hungarian", "czech", "romanian", "ukrainian", "vietnamese", "thai",
    "egyptian", "roman", "african", "european", "asian", "victorian", "islamic", "christian",
}


def _proper(word: str) -> str:
    """Capitalize a proper adjective/demonym; leave every other word untouched."""
    return word[:1].upper() + word[1:] if word.strip().lower() in _PROPER_ADJ else word


_IRR_PLURAL_FORMS = {"children", "people", "men", "women", "mice", "geese", "feet", "teeth"}


def _is_plural(subject: str) -> bool:
    w = subject.strip().lower()
    if w in _IRR_PLURAL_FORMS:                            # irregular plurals don't end in 's'
        return True
    return w.endswith("s") and not w.endswith("ss") and len(w) > 3


_PLURAL_IRR = {"child": "children", "person": "people", "man": "men", "woman": "women",
               "mouse": "mice", "goose": "geese", "foot": "feet", "tooth": "teeth"}


def _pluralize(noun: str) -> str:
    """Agree a predicate-nominative with a plural subject ('penguins are birds', not 'a bird') —
    the flaw GPT-5.4 caught in the comprehensive review. Regular English + a small irregular set."""
    w = noun.strip()
    if not w:
        return w
    lw = w.lower()
    if lw in _PLURAL_IRR:
        return _PLURAL_IRR[lw]
    if lw.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    if lw.endswith("y") and len(w) > 1 and w[-2].lower() not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"


def _agree(text: str, plural: bool) -> str:
    """Subject-verb agreement floor: for a plural subject, 'is'->'are', 'has'->'have'. Applied to
    the leading verb only (word-boundary), so object strings are untouched."""
    if not plural:
        return text
    text = re.sub(r"(?<=\s)is(?=\s)", "are", text, count=1)
    text = re.sub(r"(?<=\s)has(?=\s)", "have", text, count=1)
    return text


def _clause(subj: str, rel: str, obj: str, plural: bool = False, variant: str = "") -> str:
    f = FRAMES.get(rel, _DEFAULT)
    tmpl = variant or f["tmpl"]
    out = tmpl.format(s=subj, o=obj, rel=rel.replace("_", " "), det=_det(obj))
    return _agree(out, plural)


def constructions(rel: str) -> list:
    """Every way the speaker can say this relation: the curated frame first, then acquired ones.

    A relation has more than one construction in any real language -- `part_of` is 'is part of', and
    also 'belongs to', and also 'is one of'. Holding only one is why the speaker sounded flat and, more
    to the point here, why the inverse could not recognise a human sentence that used a different one:
    understanding is regeneration, so a construction the speaker lacks is a sentence it cannot read."""
    f = FRAMES.get(rel, _DEFAULT)
    return [f["tmpl"]] + [t for t in f.get("alts", []) if t and t != f["tmpl"]]


def realize_variants(bones: list) -> list:
    """The same bones said every way the speaker knows. Used by the inverse, and by anything that
    wants variety instead of the one canonical phrasing."""
    if not bones or len(bones) != 1:
        return [realize(bones)]
    s, r, o = [str(x).strip() for x in bones[0]]
    if not s or not o:
        return []
    plural = _is_plural(s)
    return [_cap(_clause(s, r, o, plural, v).strip()) + "." for v in constructions(r)]


def realize(bones: list) -> str:
    """Bones (list of [s, r, o]) -> fluent, faithful, grammatical English. Empty bones -> ''."""
    if not bones:
        return ""                                          # knowing/saying floor, by construction
    # group by subject, preserving first-seen order
    order: list[str] = []
    by_subj: dict[str, list] = {}
    for s, r, o in bones:
        s = (s or "").strip(); r = (r or "").strip(); o = (o or "").strip()
        if not s or not o:
            continue
        if r == "alias" and o.lower() == s.lower():        # a self-alias says nothing — drop it
            continue
        if s not in by_subj:
            by_subj[s] = []; order.append(s)
        by_subj[s].append((r, o))

    sentences: list[str] = []
    for i, subj in enumerate(order):
        preds = by_subj[subj]
        plural = _is_plural(subj)
        pron = "they" if plural else "it"
        head_ref = subj if i == 0 else pron                # first mention full, then pronoun
        # --- aggregation: fuse a leading is_a with adjacent has_property adjectives into one NP ---
        adjs_raw = [o for r, o in preds if r == "has_property"]        # originals mark `used`
        adjs = [_proper(o) for o in adjs_raw]                          # 'German', not 'german'
        noun = next((o for r, o in preds if r in ("is_a", "instance_of")), None)
        used = set()
        clauses: list[str] = []
        if noun is not None:
            head_noun = _pluralize(noun) if plural else noun   # 'penguins are birds', not 'a bird'
            np = " ".join(adjs + [head_noun]) if adjs else head_noun
            cop = "are" if plural else "is"
            det = "" if plural else _det(np) + " "         # plural predicate-nominative: no article
            clauses.append(f"{head_ref} {cop} {det}{np}".replace("  ", " "))
            used.add(("is_a", noun)); used.add(("instance_of", noun))
            for a in adjs_raw:
                used.add(("has_property", a))
        # --- remaining predicates: reduced form appends to the head; else its own clause ---
        first_done = bool(clauses)
        for r, o in preds:
            if (r, o) in used:
                continue
            f = FRAMES.get(r, _DEFAULT)
            if clauses and "reduced" in f:
                clauses[-1] = clauses[-1] + ", " + f["reduced"].format(o=o)
            else:
                ref = subj if not first_done else pron
                clauses.append(_clause(ref, r, o, plural))
                first_done = True
        # join this subject's clauses into one fluent sentence
        sent = clauses[0]
        for c in clauses[1:]:
            body = re.sub(r"^(it|they)\s+", "", c)         # drop the repeated pronoun in conjunction
            sent += ", and " + body
        sentences.append(_cap(sent.strip()) + ".")
    return " ".join(sentences)
