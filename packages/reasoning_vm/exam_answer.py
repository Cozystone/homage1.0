# -*- coding: utf-8 -*-
"""Exam mode — NEVER abstain (owner 2026-07-15: 0% ). A scored MCQ must always get an answer;
a blank scores 0, but even a guess scores ~0.25, and an evidence-ranked guess beats that. Honesty is
preserved by MARKING confidence, not by staying silent: a verify-gated pick is 'grounded', an
evidence-ranked pick is 'inference', a no-signal pick is 'guess' — never asserted as a settled fact.

Cascade (strongest first, all un-hallucinatable through step 3):
 1. discriminate() — factual lookup (//…), verify-gated.
 2. discriminate_conceptual — statement entailment incl. transitive is_a (our categorization strength).
 3. evidence rank — score each choice by graph connectivity to the stem's entities; pick the
 best (marked inference). Uses partial signal the verify-gate rejects.
 4. deterministic guess — no signal at all → a stable hash-pick (marked guess). ~random, never blank.
"""
from __future__ import annotations

import hashlib
import re
from typing import Callable

from .discrimination import discriminate, _norm
from .statement_entailment import _nouns as _stmt_nouns, verify_claim

_QW = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}")


_JOSA = re.compile(r"(으로|로서|로써|이란|란|인|은|는|이|가|을|를|의|에|와|과|도|만)$")


def _stem_terms(stem: str) -> list[str]:
    """Content terms of the stem (the entities the choices should connect to). Each term is emitted
 both raw and josa-stripped, so a category like '' also matches the graph node ''."""
    stop = {"다음", "중에서", "중", "옳은", "옳지", "않은", "것은", "것을", "무엇", "설명", "가장",
            "적절", "고르", "고른", "보기", "해당", "대한", "관한", "경우", "때문", "아닌", "것"}
    out: list[str] = []
    for t in _QW.findall(str(stem or "")):
        if t in stop:
            continue
        out.append(t)
        st = _JOSA.sub("", t)
        if st and st != t and len(st) >= 2 and st not in stop:
            out.append(st)
    return list(dict.fromkeys(out))


def _evidence_score(choice: str, stem_terms: list[str],
                    facts_about: Callable[[str], list[tuple[str, str, str]]]) -> float:
    """How much graph evidence CONNECTS this choice to the stem's terms. Signal the verify-gate
    discards: any shared neighbour / relation between a choice noun and a stem term counts."""
    score = 0.0
    cnouns = [choice] + _stmt_nouns(choice)
    stem_set = {_norm(t) for t in stem_terms}
    for cn in set(cnouns):
        try:
            facts = facts_about(cn) or []
        except Exception:
            facts = []
        for (_s, _p, o) in facts:
            if _norm(o) in stem_set:                      # choice → stem term (direct link)
                score += 2.0
        # reverse: does any stem term link to this choice?
        for t in stem_terms:
            try:
                if any(_norm(o) == _norm(cn) for (_s, _p, o) in (facts_about(t) or [])):
                    score += 2.0
            except Exception:
                pass
        # STRONG categorization signal: the choice IS-A a stem category (transitive is_a). This is the

        # which choice's taxonomy chain actually reaches X, not by loose co-occurrence.
        for t in stem_terms:
            if len(t) < 2:
                continue
            try:
                if verify_claim(cn, "is_a", t, facts_about):
                    score += 5.0
            except Exception:
                pass
    return score


def answer_exam(stem: str, choices: dict[str, str],
                facts_about: Callable[[str], list[tuple[str, str, str]]],
                passages: dict | None = None, content_index=None) -> dict:
    """Always return a pick (never abstain). dict: {choice_key, mode, confidence, basis}.
    mode ∈ grounded | openbook | inference | guess — honest confidence marking, never a fabricated
    assertion. `passages` (title->lead_text) enables the OPEN-BOOK step: closed-book graph lookup can't
    discriminate propositional MCQ (measured at chance), so we retrieve the entity's real passage and
    pick the option it supports — grounded in a real sentence, still un-hallucinatable."""
    if not choices:
        return {"choice_key": None, "mode": "empty", "confidence": 0.0, "basis": "no choices"}

    # 1) verify-gated factual
    v = discriminate(stem, choices, facts_about)
    if v.status == "GROUNDED" and v.choice_key is not None:
        return {"choice_key": v.choice_key, "mode": "grounded", "confidence": 0.9, "basis": v.basis}

    # 1.3) System-2 grounded DERIVATION (DELIBERATOR back-chainer): multi-hop, proof-verified is_a /
    #      relation composition the single-hop discriminate missed. Additive & verify-gated — returns a
    #      pick only on a checked derivation, else abstains and the cascade continues (작화0). Fires
    #      only where the GRAPH holds the chain; closed-book PhD-science MCQ fall through, by design.
    try:
        from .deliberator.mcq_adapter import engine_pick
        ep = engine_pick(stem, choices, facts_about)
        if ep and ep.get("choice_key") is not None:
            return ep
    except Exception:
        pass

    # 1.5) OPEN-BOOK — retrieve the entity's real passage and pick the option it supports. The honest
    #      lever for propositional/conceptual MCQ (closed-book graph = chance). None if no passage.
    if passages:
        try:
            from .openbook import answer_openbook
            ob = answer_openbook(stem, choices, passages, index=content_index)
            if ob and ob.get("choice_key") is not None:
                return ob
        except Exception:
            pass


    #      2026-07-16: regressed using the search ContentIndex, whose >2% hub pruning zeroed the very

    #      2026-07-18 (E5-fix): that precondition was SATISFIED — rewired to PMISolver's intact table
    #      (df∈[2,40%N], content words kept), margin-gated at 0.25 — and it still did not separate:
    #      KMMLU-200 PMI path answered 43 at **0.2326** (se≈0.064 ⇒ indistinguishable from the 0.25
    #      guess floor), overall 0.260→0.245. It DOES buy coverage (guess 102→61, non-guess fire-rate
    #      0.49→0.695) but buys no signal, so shipping it on would trade a guess for an equally blind
    #      pick plus a multi-minute index build. Hypothesis closed: corpus co-occurrence alone does not
    #      discriminate KMMLU options. Left wired behind the flag for reuse, DEFAULT OFF.
    import os as _os
    if passages and _os.environ.get("ATANOR_PMI") == "1":
        try:
            from .openbook import answer_pmi, get_pmi_solver
            pm = answer_pmi(stem, choices, get_pmi_solver(passages))
            if pm and pm.get("choice_key") is not None:
                return pm
        except Exception:
            pass

    # 2) conceptual entailment (transitive is_a etc.) is already tried inside discriminate() when the
    #    stem has no factual cue; if it GROUNDED we'd have returned. So fall to evidence ranking.
    stem_terms = _stem_terms(stem)
    negated = any(c in stem for c in ("옳지 않은", "아닌", "틀린", "잘못된", "적절하지 않은", "거리가 먼"))

    scored = {k: _evidence_score(v_, stem_terms, facts_about) for k, v_ in choices.items()}
    best = max(scored, key=scored.get)
    if scored[best] > 0:

        if negated:
            best = min(scored, key=scored.get)
        return {"choice_key": best, "mode": "inference", "confidence": 0.35,
                "basis": f"evidence-ranked (score {scored[best]:.0f})"}

    # 4) no signal → stable deterministic guess (reproducible/auditable), never blank.
    # SALTED (E3/E4, 2026-07-18): the guess previously hashed the RAW stem — the same value the
    # GPQA harness uses to Fisher-Yates the options — so guess pick and correct position were
    # COUPLED: analytically the guess could never land on two of the four layouts (hit rate 1/6),
    # measured 0.1356 over 177 no-signal items. The 'below random' GPQA closed-book number was this
    # measurement artifact, not an anti-signal in the graph. A salt decouples the scorer's stream
    # from any harness that seeds by the stem; the pick stays deterministic per stem.
    keys = sorted(choices)
    h = int(hashlib.sha256(("stable-guess::" + str(stem)).encode("utf-8", "ignore")).hexdigest(), 16)
    pick = keys[h % len(keys)]
    return {"choice_key": pick, "mode": "guess", "confidence": 0.25, "basis": "no graph signal — stable guess"}
