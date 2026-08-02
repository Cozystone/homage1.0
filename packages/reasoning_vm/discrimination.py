# -*- coding: utf-8 -*-
"""C3 discrimination — the missing 4 capability (FINAL_PLAN), verify-gated.

Measured root cause (2026-07-15, [[benchmark-mcq-wall]]): the engine DEFINES the first noun it sees
and never EVALUATES the four options — so it scores below guessing. This organ is the missing move:
given a stem's (subject, relation) and the choices, it VERIFIES each choice against the graph and
picks the one the graph SUPPORTS — the un-hallucinatable path to MCQ. It answers ONLY when the graph
backs a single choice; otherwise it ABSTAINS (never guesses, never fabricates — the omni-engage/
honesty contract). Honestly scoped: this wins FACTUAL-lookup MCQ (// …). Conceptual MCQ
(' ') needs semantic entailment we don't yet have — those abstain, by design, not bluff.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable


def _norm(s: str) -> str:
    """Loose match key: drop a trailing/inner parenthetical clarification then spaces/punctuation,
 so a choice ' ()' matches the graph target ''."""
    s = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", str(s))       # remove ' (…)' / ' […]' clarifiers
    return re.sub(r"[\s·,.'\"]+", "", s).lower()


@dataclass
class Verdict:
    choice_key: str | None            # the picked choice label (e.g. 'A'), or None on abstain
    status: str                       # 'GROUNDED' | 'ABSTAIN'
    confidence: float
    basis: str                        # human-readable derivation (auditable)
    supported: dict[str, bool]        # per-choice: did the graph verify it?


def _targets(subject: str, relation: str, facts_about: Callable[[str], list[tuple[str, str, str]]]
             ) -> list[str]:
    """The graph-verified target(s) of (subject, relation) — the ground truth to match choices to."""
    try:
        facts = facts_about(subject) or []
    except Exception:
        return []
    rel = relation.lower()
    return [str(o) for (s, p, o) in facts if str(p).lower() == rel]


def discriminate_factual(subject: str, relation: str, choices: dict[str, str],
                         facts_about: Callable[[str], list[tuple[str, str, str]]],
                         *, negated: bool = False) -> Verdict:
    """Pick the choice whose text matches the graph-verified target of (subject, relation).

 negated=True handles ' ?' — the answer is the choice that is NOT supported (when
 exactly one is unsupported and the rest are verified). Abstains unless the graph gives a clean,
 single-choice verdict — the honesty contract, not a guess."""
    truth = {_norm(t) for t in _targets(subject, relation, facts_about)}
    supported = {k: (_norm(v) in truth if truth else False) for k, v in choices.items()}
    n_sup = sum(supported.values())

    if not negated:
        if truth and n_sup == 1:
            k = next(k for k, ok in supported.items() if ok)
            return Verdict(k, "GROUNDED", 0.9,
                           f"graph-verified: {subject} -{relation}-> {choices[k]}", supported)
        return Verdict(None, "ABSTAIN", 0.0,
                       ("no graph fact supports exactly one choice"
                        if truth else f"no graph fact for ({subject}, {relation})"), supported)

    # negated: the odd-one-out is the single UNsupported choice when the others are all verified
    unsup = [k for k, ok in supported.items() if not ok]
    if truth and n_sup == len(choices) - 1 and len(unsup) == 1:
        return Verdict(unsup[0], "GROUNDED", 0.85,
                       f"the only choice NOT graph-verified for ({subject}, {relation})", supported)
    return Verdict(None, "ABSTAIN", 0.0, "graph does not isolate a single odd-one-out", supported)


# stem-word → world-pack relation (bounded lexical cue map — the reverse of _WP_REL_CLAUSE; a
# scaffold to be learned from prose later). Only used to ROUTE a stem to discriminate_factual.
_RELATION_CUES = {
    "capital": ("수도",), "country": ("나라", "국가", "소속"), "population": ("인구",),
    "area": ("면적",), "inception": ("설립", "창립", "세워진", "만들어진"), "author": ("저자", "지은이", "쓴"),
    "discovered_by": ("발견",), "creator": ("만든", "창작", "제작"), "born_in": ("태어난", "출생지"),
    "birth_date": ("생년", "태어난 해", "출생일"), "occupation": ("직업",), "is_a": ("종류", "무엇"),
}
_NEG_CUES = ("옳지 않은", "아닌", "틀린", "잘못된", "적절하지 않은", "거리가 먼", "관계가 없는")
_STOP = {"다음", "중", "것은", "것을", "무엇", "인가", "은", "는", "가", "이", "의", "에", "대한", "관한"}

# --- language-agnostic CATEGORY-MEMBERSHIP discrimination (the English+Korean grounded path) -----
# A stem asking "which of the following IS a X" is answered by VERIFYING each choice's is_a against
# the stem's category term(s) TRANSITIVELY — no subject extraction, no language-specific parse, just
# the graph's own taxonomy. Un-hallucinatable (verify-gated) and membrane-gated (fires only on a
# single clean verdict), so it returns GROUNDED exactly where the graph COVERS the categorization.
# This is the wiring that lets the grounded tier fire on ENGLISH MCQ: the prior factual path routes
# only on KOREAN cue words and discriminate_conceptual parses only Korean (Kiwi), so an English
# categorization stem never reached a verify-gate — the same transitive-is_a reasoning fired as the
# soft 'inference' rank instead of a membrane-gated 'grounded' pick.
_ISA_CUE_RE = re.compile(r"(?i)which of the following|which of these|which (?:one )?is|is (?:a|an) |"
                         r"are (?:examples?|types?|kinds?) of|type of|kind of|example of|"
                         r"classified as|categor|belongs? to|종류|무엇|인 것|에 해당")
_EN_NEG_RE = re.compile(r"(?i)\bnot\b|\bexcept\b|\bneither\b|least likely|is false|are false|"
                        r"\bincorrect\b|\bfalse\b")
_EN_STOP = {"which", "following", "these", "that", "this", "those", "and", "for", "are", "was",
            "were", "with", "from", "what", "when", "where", "how", "why", "who", "does", "not",
            "but", "its", "their", "would", "most", "likely", "given", "using", "based", "case",
            "true", "false", "correct", "best", "example", "examples", "type", "types", "kind",
            "kinds", "category", "categories", "group", "classified", "characteristic", "feature",
            "among", "between", "one", "following", "them", "all", "some", "each", "any", "have"}
_WORD_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z\-]{2,}")


def _stem_category_terms(stem: str) -> list[str]:
    """Candidate CATEGORY nouns of a categorization stem (the X in 'which is a X'), longest-first.
    Pure SURFACE extraction (LAD, never a fact); the graph gates which actually resolve to an is_a
    target. Emits single content words AND adjacent bigrams (real categories are often two words:
    'noble gas', 'connective tissue', 'covalent bond')."""
    words = _WORD_RE.findall(str(stem or ""))
    singles = [t for t in words if t.lower() not in _EN_STOP and t not in _STOP]
    grams = list(singles)
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if a.lower() not in _EN_STOP and b.lower() not in _EN_STOP:
            grams.append(a + " " + b)
    return sorted(dict.fromkeys(grams), key=len, reverse=True)


def _neg_signal(stem: str) -> bool:
    """A categorization stem is NEGATED ('which is NOT a X', '... EXCEPT') — pick the odd-one-out."""
    return any(c in stem for c in _NEG_CUES) or bool(_EN_NEG_RE.search(stem))


def discriminate_membership(stem: str, choices: dict[str, str],
                            facts_about: Callable[[str], list[tuple[str, str, str]]],
                            *, negated: bool | None = None) -> Verdict:
    """Verify each choice's is_a against the stem's category term(s) (transitive). GROUNDED when the
    graph isolates exactly one member (or, negated, exactly one non-member while the rest verify) —
    else ABSTAIN. Reuses the transitive is_a walk in statement_entailment.verify_claim (lazy import
    to avoid the cycle). Language-agnostic: 'mammal' and '포유류' resolve the same way."""
    from .statement_entailment import verify_claim
    cats = _stem_category_terms(stem)[:8]
    if not cats:
        return Verdict(None, "ABSTAIN", 0.0, "no category term in stem", {})
    if negated is None:
        negated = _neg_signal(stem)
    supported: dict[str, bool] = {}
    hit_cat: dict[str, str] = {}
    for k, choice in choices.items():
        ok = False
        for cat in cats:
            if _norm(cat) == _norm(choice):
                continue                                  # a choice can't be its own category
            try:
                if verify_claim(choice, "is_a", cat, facts_about):
                    ok, hit_cat[k] = True, cat
                    break
            except Exception:
                pass
        supported[k] = ok
    n_sup = sum(supported.values())
    if not negated:
        if n_sup == 1:
            k = next(k for k, ok in supported.items() if ok)
            return Verdict(k, "GROUNDED", 0.85,
                           f"graph is_a: '{choices[k]}' is a '{hit_cat.get(k)}'", supported)
        return Verdict(None, "ABSTAIN", 0.0,
                       "graph verifies none or more than one membership", supported)
    unsup = [k for k, ok in supported.items() if not ok]
    if n_sup == len(choices) - 1 and len(unsup) == 1:
        return Verdict(unsup[0], "GROUNDED", 0.8,
                       f"the only choice NOT a member of {cats[:2]}", supported)
    return Verdict(None, "ABSTAIN", 0.0, "graph does not isolate a single odd-one-out", supported)

# trailing Korean particle to strip from a candidate — incl. the dual written forms a generated stem

_JOSA_TAIL = re.compile(r"(이\(가\)|을\(를\)|은\(는\)|과\(와\)|와\(과\)|에게|에서|으로|이라|라고|"
                        r"의|은|는|이|가|을|를|에|과|와|로|도|만)$")


def _josa_cands(w: str):
    yield w
    m = _JOSA_TAIL.sub("", w).strip()
    if m and m != w:
        yield m


def _extract_subject(stem: str, relation: str,
                     facts_about: Callable[[str], list[tuple[str, str, str]]]) -> str:
    """The subject is the SPAN before the relation-cue phrase — tried whole, then as longest-first
    contiguous n-grams, then single tokens. Splitting on spaces and testing only single tokens
    abstains on every multi-word entity ('San Isidro Canton', 'Tommy O'Regan'); measured 2026-07-18,
    that held C3 coverage at 0.11 while accuracy-when-answered was 0.99. The graph still gates every
    candidate (a span is accepted only if it has a verified target), so honesty is unchanged."""
    cues = _RELATION_CUES.get(relation, ())
    cut = min([stem.find(c) for c in cues if c in stem] or [len(stem)])
    prefix = re.sub(r"[\s,.?!()]+$", "", stem[:cut]).strip()
    ptoks = [w for w in re.split(r"[\s,.?!()]+", prefix) if w and w not in _STOP]
    spans: list[str] = []
    for size in range(len(ptoks), 0, -1):                 # longest contiguous spans first
        for start in range(len(ptoks) - size + 1):
            spans.append(" ".join(ptoks[start:start + size]))
    tail_toks = sorted((w for w in re.split(r"[\s,.?!()]+", stem) if w and w not in _STOP),
                       key=len, reverse=True)             # single-token fallback (old behaviour)
    seen: set[str] = set()
    for cand in ([prefix] + spans + tail_toks):
        for c in _josa_cands(cand):
            if not c or c in seen:
                continue
            seen.add(c)
            if _targets(c, relation, facts_about):        # graph-verified → accept this span
                return c
    return prefix or (tail_toks[0] if tail_toks else "")


def _chain_relations(stem: str) -> list[str]:
    """Relations whose cue appears in the stem, ordered by first cue POSITION. A 2-cue stem
 ("{} ?" → author, then born_in) is a 2-HOP question: subject -R1-> bridge
 -R2-> answer. Ordered by position (not dict order) so the hop sequence follows the sentence."""
    hits = []
    for rel, cues in _RELATION_CUES.items():
        p = [stem.find(c) for c in cues if c in stem]
        if p:
            hits.append((min(p), rel))
    hits.sort()
    out: list[str] = []
    for _p, rel in hits:
        if rel not in out:
            out.append(rel)
    return out


def _discriminate_chain(stem: str, choices: dict[str, str],
                        facts_about: Callable[[str], list[tuple[str, str, str]]],
                        chain: list[str]) -> Verdict:
    """Backward-chaining discrimination over N hops: subject -R1-> b1 -R2-> … -Rn-> answer. Every
 intermediate hop must resolve to a SINGLE bridge and the final hop to a SINGLE supported choice,
 else ABSTAIN — the same honesty gate as single-hop, N levels deeper. No LLM: each hop is a graph
 lookup. Generalised from 2-hop so 3-hop stems ('{} ?') compose too."""
    subject = _extract_subject(stem, chain[0], facts_about)
    if not subject:
        return Verdict(None, "ABSTAIN", 0.0, "chain: no subject entity in the stem", {})
    cur = subject
    trail = [subject]
    for rel in chain[:-1]:                                    # walk every intermediate hop
        bridges = {_norm(b): b for b in _targets(cur, rel, facts_about)}
        if len(bridges) != 1:                                # need ONE bridge to keep chaining
            return Verdict(None, "ABSTAIN", 0.0,
                           f"chain: ({cur}, {rel}) is not single-valued", {})
        cur = next(iter(bridges.values()))
        trail.append(cur)
    final = chain[-1]
    truth = {_norm(t) for t in _targets(cur, final, facts_about)}
    supported = {k: (_norm(v) in truth if truth else False) for k, v in choices.items()}
    if truth and sum(supported.values()) == 1:
        k = next(k for k, ok in supported.items() if ok)
        path = " -> ".join(trail) + f" -{final}-> {choices[k]}"
        return Verdict(k, "GROUNDED", 0.85, f"chain: {path}", supported)
    return Verdict(None, "ABSTAIN", 0.0,
                   f"chain: no single choice matches ({cur}, {final})", supported)


def discriminate(stem: str, choices: dict[str, str],
                 facts_about: Callable[[str], list[tuple[str, str, str]]],
                 *, subject: str | None = None) -> Verdict:
    """End-to-end factual MCQ: infer (subject, relation) from the stem via bounded cues, then
    discriminate. subject may be supplied by the intent layer; else the longest stem noun the graph
    knows is used. ABSTAINS if no relation cue or subject is found — honest, never guesses."""
    negated = _neg_signal(stem)                          # Korean cues OR English (not/except/EXCEPT…)
    # a 2-cue stem is a 2-hop chain; try that FIRST (single-hop would fire on the first cue and
    # answer the wrong relation). Falls through to single-hop when the chain can't resolve.
    if subject is None and not negated:
        chain = _chain_relations(stem)
        if len(chain) >= 2:
            cv = _discriminate_chain(stem, choices, facts_about, chain)
            if cv.status == "GROUNDED":
                return cv
    # CATEGORY-MEMBERSHIP (language-agnostic is_a verification): 'which of the following is a X'.
    # Fires the grounded tier on ENGLISH categorization the graph covers — where before only the
    # Korean factual/conceptual paths could reach a verify-gate. ABSTAIN falls through unchanged.
    if (subject is None and _ISA_CUE_RE.search(stem)
            and os.environ.get("ATANOR_MEMBERSHIP", "1") != "0"):   # A/B flag (default ON)
        mv = discriminate_membership(stem, choices, facts_about, negated=negated)
        if mv.status == "GROUNDED":
            return mv
    relation = next((rel for rel, cues in _RELATION_CUES.items() if any(c in stem for c in cues)), None)
    if relation is None:
        # no factual relation cue in the STEM → conceptual MCQ (the CHOICES are statements). Verify
        # each statement's claim against the graph; still un-hallucinatable. Lazy import (cycle).
        try:
            from .statement_entailment import discriminate_conceptual
            cv = discriminate_conceptual(stem, choices, facts_about, negated=negated)
            if cv.status == "GROUNDED":
                return cv
        except Exception:
            pass
        return Verdict(None, "ABSTAIN", 0.0, "no factual relation cue in the stem", {})
    if subject is None:
        subject = _extract_subject(stem, relation, facts_about)
    if not subject:
        return Verdict(None, "ABSTAIN", 0.0, "no subject entity found in the stem", {})
    return discriminate_factual(subject, relation, choices, facts_about, negated=negated)
