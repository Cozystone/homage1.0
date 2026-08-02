# -*- coding: utf-8 -*-
"""C1 — statement entailment: extend discrimination from ENTITY-lookup to STATEMENT-verification.

`discrimination.py` picks the choice whose TEXT is a graph-verified target of (subject, relation) —
great for ' ? → ', but a conceptual MCQ's choices are whole STATEMENTS ('
 '), not bare entities. This organ decomposes each statement into its (subject,
relation, object) CLAIM — reusing the SAME cue map discrimination routes with, plus Kiwi for the two
content nouns (surface parse = LAD, never a fact) — and VERIFIES the claim against the graph. Then the
identical un-hallucinatable move applies: for ' ?' pick the single graph-SUPPORTED statement;
for ' ?' pick the single UNsupported one when the rest are verified. ABSTAINS whenever the
graph can't isolate one — most science-exam claims the graph doesn't cover abstain, by design, not
bluff (the honest scope from [[benchmark-mcq-wall]]: this wins conceptual MCQ the world graph COVERS,
which is a minority today; it never guesses on the rest).

No facts are authored here — the graph is the sole source of truth; this only reads STRUCTURE off the
surface (which two nouns, which relation) and asks the graph whether the claim holds.
"""
from __future__ import annotations

import re
from typing import Callable

from .discrimination import Verdict, _RELATION_CUES, _norm

_CONTENT = {"NNG", "NNP", "SL", "SH"}


_CUE2REL = sorted(((cue, rel) for rel, cues in _RELATION_CUES.items() for cue in cues if rel != "is_a"),
                  key=lambda kv: -len(kv[0]))
_GENERIC = {"종류", "일종", "하나", "종", "무엇", "것", "개념", "분류", "예"}   # not real objects
_COPULA = re.compile(r"(이다|이에요|예요|입니다|이야|다)\s*$")


def _kiwi():
    from packages.base_brain.neighborhood import _kiwi as _k
    return _k()


def _nouns(text: str) -> list[str]:
    """Ordered noun PHRASES () of a statement — the claim's argument candidates. Adjacent content
 tokens are merged (' ', ' ') so real multi-word Wikidata labels survive; a
 particle/verb/ending breaks the run (so subject '' object stay separate)."""
    try:
        toks = _kiwi().analyze(text)[0][0]
    except Exception:
        return [w for w in re.split(r"[\s,.?!()]+", text) if len(w) >= 2]   # Kiwi-absent fallback
    phrases: list[str] = []
    cur: list[str] = []
    for t in toks:
        if t.tag in _CONTENT:
            cur.append(t.form)
        else:
            if cur:
                phrases.append(" ".join(cur))
                cur = []
    if cur:
        phrases.append(" ".join(cur))
    return phrases





_VERB_NOUN_REL = {"발견": "discovered_by", "발명": "creator", "제작": "creator", "창작": "creator",
                  "작곡": "creator", "설계": "creator", "저술": "author", "집필": "author",
                  "작사": "creator", "작화": "creator", "저작": "author"}


def _verb_claim(statement: str) -> tuple[str, str, str] | None:
    """Agentive statement (' ') → (theme, relation, agent) via case markers.
 A mis-parse can only yield an unmatched claim → ABSTAIN downstream, never a wrong answer."""
    try:
        toks = _kiwi().analyze(statement)[0][0]
    except Exception:
        return None
    forms = {t.form for t in toks}
    rel = next((r for n, r in _VERB_NOUN_REL.items() if n in forms), None)
    if rel is None:
        return None
    theme = agent = ""
    cur: list[str] = []
    for t in toks:
        if t.tag in _CONTENT:
            cur.append(t.form)
        elif t.tag == "JKO" and cur:
            theme = " ".join(cur); cur = []
        elif t.tag == "JKS" and cur:
            agent = " ".join(cur); cur = []
        else:
            cur = []
    if theme and agent and theme != agent:
        return theme, rel, agent
    return None


def extract_claim(statement: str) -> tuple[str, str, str] | None:
    """Statement → (subject, relation, object) claim, or None if none can be read.

 POSITION-BASED so a cue that is ALSO a valid object works: a possessive/marked cue ('X Y',
 'X Y ') sets the relation ONLY when an object noun follows it; when the noun that looks like
 a cue is the predicate itself (' ') no object follows, so it falls to the copula
 path → (X, is_a, ). subject = first content noun; object = last content noun after the cue (or,
 for classification, the last non-generic noun)."""
    s = statement.strip()
    vc = _verb_claim(s)
    if vc is not None:
        return vc
    nouns = _nouns(s)
    if len(nouns) < 2:
        return None
    subject = nouns[0]
    for cue, rel in _CUE2REL:                                    # possessive relation w/ object
        idx = s.find(cue)
        if idx < 0:
            continue
        after = [n for n in nouns
                 if n != subject and n != cue and n not in _GENERIC and s.find(n, idx + len(cue)) >= 0]
        if after:
            return subject, rel, after[-1]
    if _COPULA.search(s):                                        # classification → is_a
        obj = next((n for n in reversed(nouns[1:]) if n not in _GENERIC and n != subject), "")
        if obj:
            return subject, "is_a", obj
    return None


def _rel(p: str) -> str:
    return str(p).lower()


_TRANSITIVE = {"is_a", "subclass_of"}
_TAX_RELS = ("is_a", "subclass_of")


def verify_claim(subject: str, relation: str, obj: str,
                 facts_about: Callable[[str], list[tuple[str, str, str]]],
                 *, max_depth: int = 6, max_nodes: int = 200) -> bool:
    """True iff the graph holds (subject, relation, obj) — DIRECTLY, or, for a taxonomy relation,
    TRANSITIVELY along is_a/subclass_of (verified reasoning, not fabrication). Cycle-safe and bounded
    (depth + node cap) so a hub near the top of the tree can't blow up the walk. Reads only."""
    goal = _norm(obj)
    try:
        facts = facts_about(subject) or []
    except Exception:
        return False
    if goal in {_norm(o) for (s, p, o) in facts if _rel(p) == relation}:
        return True                                          # direct edge
    if relation not in _TRANSITIVE:
        return False
    seen: set[str] = set()
    frontier = [subject]
    for _ in range(max_depth):
        nxt: list[str] = []
        for node in frontier:
            key = _norm(node)
            if key in seen or len(seen) >= max_nodes:
                continue
            seen.add(key)
            try:
                nf = facts_about(node) or []
            except Exception:
                nf = []
            for (s, p, o) in nf:
                if _rel(p) in _TAX_RELS:
                    if _norm(o) == goal:
                        return True                          # reached the claimed ancestor
                    nxt.append(o)
        frontier = nxt
        if not frontier:
            break
    return False


def verify_statement(statement: str,
                     facts_about: Callable[[str], list[tuple[str, str, str]]]) -> str:
    """'SUPPORTED' | 'UNVERIFIED' — is the statement's decomposed claim backed by the graph?
    UNVERIFIED covers both 'graph refutes it' and 'graph doesn't cover it' (both are 'not supported'
    for the odd-one-out move; we never assert a claim FALSE we merely can't confirm — honesty)."""
    claim = extract_claim(statement)
    if claim is None:
        return "UNVERIFIED"
    return "SUPPORTED" if verify_claim(*claim, facts_about) else "UNVERIFIED"


_NEG_CUES = ("옳지 않은", "아닌", "틀린", "잘못된", "적절하지 않은", "거리가 먼", "관계가 없는", "옳지않은")


def discriminate_conceptual(stem: str, choices: dict[str, str],
                            facts_about: Callable[[str], list[tuple[str, str, str]]],
                            *, negated: bool | None = None) -> Verdict:
    """Conceptual MCQ whose choices are STATEMENTS: verify each against the graph and pick the single
 supported one (' ?') — or, when negated (' ?'), the single UNsupported one while
 the rest are all verified. ABSTAINS unless the graph isolates exactly one — never guesses."""
    if negated is None:
        negated = any(c in stem for c in _NEG_CUES)
    supported = {k: (verify_statement(v, facts_about) == "SUPPORTED") for k, v in choices.items()}
    n_sup = sum(supported.values())

    if not negated:
        if n_sup == 1:
            k = next(k for k, ok in supported.items() if ok)
            return Verdict(k, "GROUNDED", 0.8, f"only graph-supported statement: {choices[k]}", supported)
        return Verdict(None, "ABSTAIN", 0.0,
                       "graph supports none or more than one statement", supported)

    unsup = [k for k, ok in supported.items() if not ok]
    if n_sup == len(choices) - 1 and len(unsup) == 1:
        return Verdict(unsup[0], "GROUNDED", 0.75,
                       f"the only statement NOT graph-supported: {choices[unsup[0]]}", supported)
    return Verdict(None, "ABSTAIN", 0.0, "graph does not isolate a single odd-one-out", supported)
