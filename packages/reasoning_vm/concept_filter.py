# -*- coding: utf-8 -*-
"""Universal neurosymbolic candidate filter — mental model + elimination + logical filtering.

Owner directive (2026-07-18): answer the way a person does — build a mental model, eliminate
candidates that contradict it, and only then select — and do this in EVERY answer path, not
just exams. The measured backdrop: positive lexical SELECTION has a structural ceiling
(gold-uniquely-best-covered oracle 0.165 < the 0.25 chance floor; see E6b), because MCQ
distractors are often assembled by RECOMBINING the passage's own words, so the gold option
loses every overlap contest. ELIMINATION is the mathematically different channel: it does not
need the gold option to win coverage — it needs a distractor's contradiction to be DETECTABLE,
and the more a distractor plagiarises passage vocabulary, the more its polarity flips, number
mismatches, role transpositions and explicit negations are exposed to symbolic checks.

What "mental model" means here, honestly: the activated evidence for the question (retrieved
passage sentences + graph facts), the question's expected-category slot when it states one,
and the stem's own polarity (a "which is NOT…" stem INVERTS elimination into selection). This
is the symbolic skeleton of a mental model, not a claim of human simulation.

Unknown domains: when no evidence retrieves and the graph is silent, every verdict is
"no-verdict" — the caller falls through to its honest fallback (marked guess / abstain-shape).
Silence over fabrication ( 0 ); the filter never invents a contradiction.

Doctrine (BINDING, rules-are-training-wheels): this hand-signal layer is the scaffold. Its
successor is the E9-trained semantic encoder scoring the SAME interface (eliminate() swaps
its scorer, callers unchanged) — the symbolic reasons remain as the audit trail.

★ E10-D1 VERDICT (2026-07-18, measured BEFORE any cascade wiring — do not wire this into the
exam cascade as-is): on MMLU-200 × retrieved passages the symbolic detector is TRIPLE RED
against its pre-declared gates — fired 0.055 (gate ≥0.25), gold falsely killed 0.364 (gate
≤0.08), survivor-pick expected acc 0.227 (< the 0.25 floor). Robustness pool=10 made it WORSE
(gold_kill 0.500, exp_acc 0.177): more retrieval = more spuriously "about" sentences = more
random executions. Root cause measured (`diagnose_elimination_oracle.py` ablation): median
best-aboutness is 0.143 and only 24.6% of options ever meet a sentence that is even minimally
about them — the same evidence starvation as the 0.165 selection ceiling. Standing finding:
**elimination logic over evidence the system cannot semantically match is noise** — the gap
is not the elimination machinery, it is the semantic space (E9). This module therefore ships
as the INTERFACE + the negated-stem/type-slot mechanics; its contradiction scorer awaits the
E9 encoder (or a full-article corpus, queued E10b) before any answer path may trust it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .openbook import (_EN_STOP, _NUM, _SENT, _STOP_CONTENT, _content, _order_sign,
                       _polarity)

# --- stem polarity: a negated stem ("which is NOT correct?") inverts elimination ---
_NEG_STEM_EN = re.compile(r"\b(?:not|except|incorrect|false|least)\b", re.IGNORECASE)
_NEG_STEM_KO = re.compile(r"옳지\s*않은|아닌|틀린|잘못된|적절하지\s*않은|거리가\s*먼")

# explicit negation inside an option/sentence — flips its local polarity
_NEG_WORDS = {"not", "no", "never", "cannot", "can't", "won't", "doesn't", "don't", "didn't",
              "isn't", "aren't", "wasn't", "weren't", "without", "neither", "nor", "unable",
              "fails", "fail", "lack", "lacks", "absence", "absent"}

# expected-category slot: "which of the following is a/an X …?"
_CATEGORY_STEM = re.compile(
    r"which\s+(?:one\s+)?of\s+the\s+following\s+is\s+(?:a|an)\s+([a-z][a-z\- ]{2,30}?)\s*[?,]",
    re.IGNORECASE)

_ABOUT_GATE = 0.34          # a sentence must be ABOUT the option before its signals count
_MIN_TOKENS = 2             # options with <2 content tokens can't anchor a verdict


@dataclass
class Verdict:
    key: str
    eliminated: bool = False
    protected: bool = False                    # graph-confirmed type match — never eliminate
    reasons: list[str] = field(default_factory=list)
    aboutness: float = 0.0                     # best sentence-aboutness seen (0 = no evidence)


def _tokens(text: str) -> list[str]:
    return [t for t in _content(str(text or ""))
            if t not in _STOP_CONTENT and t not in _EN_STOP and len(t) >= 3]


def _local_polarity(text: str) -> int | None:
    """Polarity of a clause with explicit negation folded in: 'does not increase' == NEG."""
    base = _polarity(text)
    toks = set(re.findall(r"[a-z']+", str(text or "").lower()))
    if toks & _NEG_WORDS:
        return None if base is None else (1 - base)
    return base


def stem_is_negated(stem: str) -> bool:
    s = str(stem or "")
    return bool(_NEG_STEM_EN.search(s) or _NEG_STEM_KO.search(s))


def expected_category(stem: str) -> str | None:
    """The stem's stated answer-type slot, when it states one ('…is a mammal?' → 'mammal')."""
    m = _CATEGORY_STEM.search(str(stem or ""))
    return m.group(1).strip().rstrip("s") if m else None


def contradiction_reasons(option: str, sentence: str) -> list[str]:
    """Symbolic contradiction signals between an option and a sentence that is ABOUT it.
    Each reason is a short auditable string — the answer path can show its work."""
    out: list[str] = []
    opol, spol = _local_polarity(option), _local_polarity(sentence)
    if opol is not None and spol is not None and opol != spol:
        out.append("polarity flip vs evidence")
    onums, snums = set(_NUM.findall(option)), set(_NUM.findall(sentence))
    if onums and snums and not (onums & snums):
        out.append(f"number mismatch ({'/'.join(sorted(onums)[:2])} vs {'/'.join(sorted(snums)[:2])})")
    otoks = _tokens(option)
    key2 = sorted(set(otoks), key=lambda t: -len(t))[:2]
    if len(key2) == 2:
        oo = _order_sign(key2[0], key2[1], option.lower())
        so = _order_sign(key2[0], key2[1], sentence.lower())
        if oo and so and oo != so:
            out.append(f"role transposition ({key2[0]}/{key2[1]} reversed)")
    return out


def eliminate(stem: str, choices: dict[str, str], evidence_texts: list[str],
              facts_about=None, verify=None) -> dict[str, Verdict]:
    """Mental-model elimination over answer candidates. Returns a Verdict per key.

    - evidence_texts: retrieved passages (already the caller's activated context). Empty list
      → graph-only mode; graph silent too → all no-verdict (unknown domain, honest fallback).
    - facts_about/verify: graph hooks. Used POSITIVELY only in v0 — a graph-confirmed
      category match PROTECTS an option from elimination; graph silence never eliminates
      (open-world stores must not treat absence as falsity).
    """
    sents: list[str] = []
    for t in evidence_texts or []:
        sents.extend(s for s in _SENT.split(str(t or "")) if s.strip())

    cat = expected_category(stem)
    verdicts: dict[str, Verdict] = {}
    for k, opt in choices.items():
        v = Verdict(key=k)
        otoks = _tokens(opt)
        # graph-positive protection: option verifiably IS the stated category → keep
        if cat and verify is not None and facts_about is not None:
            try:
                if verify(str(opt), "is_a", cat, facts_about):
                    v.protected = True
            except Exception:
                pass
        if len(otoks) >= _MIN_TOKENS and sents and not v.protected:
            tot = sum(len(t) for t in otoks) or 1
            best_about, best_reasons = 0.0, []
            for s in sents:
                sl = s.lower()
                about = sum(len(t) for t in otoks if t in sl) / tot
                if about < _ABOUT_GATE:
                    continue
                rs = contradiction_reasons(opt, s)
                if about > best_about:
                    best_about, best_reasons = about, rs
                elif rs and not best_reasons and about >= best_about - 0.05:
                    best_reasons = rs
            v.aboutness = round(best_about, 3)
            if best_about >= _ABOUT_GATE and best_reasons:
                v.eliminated = True
                v.reasons = best_reasons
        verdicts[k] = v
    return verdicts


def apply_verdicts(stem: str, choices: dict[str, str],
                   verdicts: dict[str, Verdict]) -> dict:
    """Turn verdicts into a cascade decision. Three outcomes:
 pick — negated stem + exactly one contradicted option (the 'NOT true' answer), or
 normal stem + exactly one survivor ( )
 restrict — some options eliminated; caller re-runs its selection over survivors only
 (raises the guess floor from 1/n to 1/|survivors|)
 none — nothing eliminable (unknown domain / no evidence) — caller unchanged
 """
    elim = [k for k, v in verdicts.items() if v.eliminated]
    if not elim:
        return {"action": "none"}
    if stem_is_negated(stem):
        if len(elim) == 1:
            v = verdicts[elim[0]]
            return {"action": "pick", "choice_key": elim[0], "mode": "eliminated",
                    "confidence": 0.4,
                    "basis": f"negated stem — the one option contradicting evidence: {'; '.join(v.reasons)}"}
        return {"action": "none"}                  # several contradicted — can't pick the NOT
    survivors = [k for k in choices if k not in elim]
    if len(survivors) == 1:
        gone = ", ".join(f"{k}({'; '.join(verdicts[k].reasons)})" for k in elim)
        return {"action": "pick", "choice_key": survivors[0], "mode": "eliminated",
                "confidence": 0.4, "basis": f"sole survivor after elimination of {gone}"}
    if survivors:
        return {"action": "restrict", "survivors": survivors,
                "basis": {k: verdicts[k].reasons for k in elim}}
    return {"action": "none"}                      # everything contradicted — signal is noise
