# -*- coding: utf-8 -*-
"""Learned realizer — the , finally LEARNED instead of hand-templated (FINAL_PLAN C4).

The realizer sounded like a dictionary because its flesh was 36 hand-written connectives
(',/,/,') that ENUMERATE grounded fact-clauses as separate sentences. This module
replaces that with discourse LEARNED from real prose: it INDUCES the clause-fusion grammar humans
actually use (which connective endings ~/~/~, how often they fuse vs list, how often they
refer back with ' X') from real Korean sentences the AI has read, then FUSES the same grounded
fact-clauses into one flowing sentence.

Doctrine (BINDING, FINAL_PLAN):
 - No LLM, no sLLM, no hand template. The connective INVENTORY + their frequencies are MINED from
 real prose (learned, like the falsifier induces procedures from examples); nothing here is a
 hand-authored sentence. Korean connective/josa MORPHOLOGY is grammar application (same status as
 the josa engine), not content.
 - stays verbatim: every content clause is a graph-grounded `description`, unchanged. Only the
 JOINING (connectives, back-reference, ordering) is generated, and it carries no facts →
 grounding is structurally preserved (verify with `grounding_ok`).
 - Grows as the AI reads more prose (the grammar is re-mined), never hand-tuned.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .korean_orthography import has_batchim, josa

REPO = Path(__file__).resolve().parents[2]
_GRAMMAR_PATH = REPO / "data" / "surface_brain" / "realizer_grammar.json"

# ── connective morphology (GRAMMAR, not content — same status as josa) ────────────────────────


_NOUN_CONNECT = ("이며", "이자", "이고")           # copula-fusion after a noun phrase
_VERB_CONNECT_UNIV = "고"
_VERB_CONNECT_MYEO = ("으며", "며")


def _is_clause_verb_final(text: str) -> bool:
    """True when the clause ends like a predicate (…/…), False for a noun phrase."""
    t = text.rstrip(" .!?。")
    return bool(re.search(r"(다|음)$", t))


def _verb_stem(text: str) -> str:
    """Strip a trailing plain-form ender to get the connectable stem (→, →)."""
    return re.sub(r"다$", "", text.rstrip(" .!?。"))


# Kiwi is the BINDING single authority for Korean morphology: it conjugates a clause's predicate to


_KIWI: Any = None
_KIWI_TRIED = False


def _kiwi():
    global _KIWI, _KIWI_TRIED
    if not _KIWI_TRIED:
        _KIWI_TRIED = True
        try:
            from kiwipiepy import Kiwi
            _KIWI = Kiwi()
        except Exception:
            _KIWI = None
    return _KIWI


_PRED_TAGS = {"VV", "VA", "VCP", "VCN", "VX", "XSV", "XSA", "EP"}


def _kiwi_reinflect(clause: str, ending: str, tag: str) -> str | None:
    """Conjugate ONLY the clause's final predicate word by swapping its sentence-final ending for
    `(ending, tag)` and re-joining — keeping the rest of the clause verbatim (grounding preserved;
    re-joining the whole clause would let Kiwi renormalize spacing/numbers and break the fact).
    None if Kiwi is absent or the tail isn't predicate-final."""
    k = _kiwi()
    if k is None:
        return None
    prefix, _, last = clause.rstrip(" .!?。").rpartition(" ")   # split off the final word
    tail = last or clause.rstrip(" .!?。")
    try:
        ms = [(t.form, t.tag) for t in k.analyze(tail)[0][0]]
        while ms and ms[-1][1] in ("EF", "SF", "SP", "SE", "SW"):
            ms.pop()
        if not ms or ms[-1][1].split("-")[0] not in _PRED_TAGS:   # 'VV-I'/'VV-R' → base tag
            return None
        ms.append((ending, tag))
        conj = k.join(ms)
        if not isinstance(conj, str) or not conj:
            return None
        return (f"{prefix} {conj}" if prefix else conj).strip()
    except Exception:
        return None


def _kiwi_connect(clause: str, ec: str) -> str | None:
    return _kiwi_reinflect(clause, ec, "EC")


def _to_connective(clause: str, *, connective: str) -> str:
    """Attach a learned connective to a fact-clause. GRAMMAR only (Kiwi) — content untouched."""
    c = clause.strip().rstrip(" .!?。")
    if c.endswith("이다"):                                  # noun+copula clause → copula-fusion, not
        conn = connective if connective in _NOUN_CONNECT else "이며"   # the verb (Kiwi) path
        return c[:-2] + conn
    if _is_clause_verb_final(c):
        ec = "고" if connective in ("고", *_NOUN_CONNECT) else connective
        kj = _kiwi_connect(c, ec)
        if kj:
            return kj
        stem = _verb_stem(c)
        return stem + "고" if ec == "고" else stem + ("으며" if has_batchim(stem) else "며")
    # noun phrase → copula-fusion; the mined connective is one of _NOUN_CONNECT
    conn = connective if connective in _NOUN_CONNECT else "이며"
    return c + conn


def _has_ss_final(ch: str) -> bool:
    """True if the syllable ends in (past-tense marker: //// …)."""
    if not ("가" <= ch <= "힣"):
        return False
    return (ord(ch) - 0xAC00) % 28 == 20


def _final_polite(clause: str) -> str:
    """Realize the LAST clause with a natural closing (keeps content, clean ending). Uses Kiwi
 (single-authority morphology) to conjugate the final predicate to ; falls back to shape rules."""
    c = clause.strip().rstrip(" .!?。")
    if c.endswith("이다"):
        return josa(c[:-2], "copula") + "."
    if _is_clause_verb_final(c):
        kp = _kiwi_reinflect(c, "어요", "EF")
        if kp:
            return kp + "."
        stem = _verb_stem(c)                              # fallback (Kiwi absent)
        if stem.endswith("있") or stem.endswith("없"):
            return stem + "어요."
        if stem and _has_ss_final(stem[-1]):
            return stem + "어요."
        if stem.endswith("하") or stem.endswith("한"):
            return re.sub(r"[하한]$", "해요", stem) + "."
        return c + "."
    return josa(c, "copula") + "."


# ── grammar induction: LEARN discourse from real prose (frequencies, not hand lists) ──────────
_CONNECTIVE_CUES = ("이며", "이자", "이고", "으로써", "으며", "면서", "는데", "은데",
                    "아서", "어서", "하여", "라서", "지만", "거나", "고,", "며,")
_BACKREF_CUES = ("이 ", "이는", "그 ", "그는", "해당", "이러한", "그러한", "이때", "이곳")


def mine_grammar(sentences: list[str]) -> dict[str, Any]:
    """Induce the fusion grammar from REAL prose: which connectives, how often humans fuse (clauses
    per sentence), how often they refer back. Statistics only — never content."""
    if not sentences:
        return {}
    conn: Counter = Counter()
    fused = backref = 0
    clause_counts: list[int] = []
    for s in sentences:
        hit = [c for c in _CONNECTIVE_CUES if c in s]
        for c in hit:
            conn[c.rstrip(",")] += 1
        if hit:
            fused += 1
        if any(s.startswith(m) or (" " + m) in s for m in _BACKREF_CUES):
            backref += 1
        # rough clause count = connective joins + 1
        clause_counts.append(1 + sum(s.count(c) for c in ("이며", "이자", "고,", "며,", "으며")))
    n = len(sentences)
    noun_conn = {c: conn[c] for c in _NOUN_CONNECT if conn[c]}
    return {
        "n": n,
        "fusion_rate": round(fused / n, 3),                        # humans fuse this often
        "backref_rate": round(backref / n, 3),
        "mean_clauses_per_sentence": round(sum(clause_counts) / n, 2),
        # learned connective distribution (weights for sampling) — mined, not hand-ranked
        "noun_connectives": noun_conn or {"이며": 1},
        "connective_total": dict(conn.most_common(12)),
    }


def learn_and_save(sentences: list[str] | None = None) -> dict[str, Any]:
    if sentences is None:
        from .discourse_learner import harvest_web_prose
        sentences = harvest_web_prose()
    g = mine_grammar(sentences)
    if g:
        _GRAMMAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GRAMMAR_PATH.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    return g


_CACHE: dict[str, Any] = {"g": None, "mtime": 0.0}


def grammar() -> dict[str, Any]:
    try:
        if not _GRAMMAR_PATH.exists():
            return {}
        m = _GRAMMAR_PATH.stat().st_mtime
        if _CACHE["g"] is None or _CACHE["mtime"] != m:
            _CACHE["g"] = json.loads(_GRAMMAR_PATH.read_text(encoding="utf-8"))
            _CACHE["mtime"] = m
        return _CACHE["g"] or {}
    except Exception:
        return {}


def _sample_noun_connective(g: dict[str, Any], rng: random.Random) -> str:
    dist = g.get("noun_connectives") or {"이며": 1}
    items, weights = zip(*dist.items())
    return rng.choices(items, weights=weights, k=1)[0]



def realize_fused(topic: str, clauses: list[str], *, g: dict[str, Any] | None = None,
                  seed: int = 0, prepend_topic: bool = True) -> str:
    """Fuse grounded fact-clauses (, verbatim) into ONE flowing sentence using the learned fusion
 grammar — replacing enumeration. Content is untouched; only joins are generated.

 prepend_topic=True → the clauses are bare descriptions ABOUT `topic` (' '): state
 `topic` once, then fuse (shared-subject mode).
 prepend_topic=False → the clauses already carry their OWN subjects (' …', ' …'):
 fuse them as-is, keeping each subject (multi-subject mode; no doubling)."""
    g = g if g is not None else grammar()
    picked = [c.strip() for c in clauses if c and c.strip()]
    if not picked:
        return ""
    rng = random.Random((seed << 8) ^ hash(topic) & 0xFFFF)
    if len(picked) == 1:
        lead = f"{josa(topic, 'topic')} " if prepend_topic else ""
        return f"{lead}{_final_polite(picked[0])}"

    lead = f"{josa(topic, 'topic')} " if prepend_topic else ""
    head = lead + _to_connective(picked[0], connective=_sample_noun_connective(g, rng))
    mids: list[str] = []
    # middle clauses: fused, subject dropped (shared topic) — how the real prose reads
    for c in picked[1:-1]:
        conn = _VERB_CONNECT_UNIV if _is_clause_verb_final(c) else _sample_noun_connective(g, rng)
        mids.append(_to_connective(c, connective=conn))
    tail = _final_polite(picked[-1])
    # commas between fused clauses (matches real prose punctuation); no comma before the final.
    return ", ".join([head, *mids, tail]).replace(" ,", ",").strip()


def realize_fused_en(topic: str, clauses: list[str], *, seed: int = 0) -> str:
    """English fusion realizer — the analytic-language twin of realize_fused. English needs no josa
    or conjugation, so fusion is joining the VERBATIM fact-clauses into ONE flowing sentence with the
    frequency-dominant clause connectives (', ' between, ', and ' before the last) — the same 'learned
    function-word surface' role josa plays in Korean, never a template sentence. Content is untouched
    (grounding-safe): enumeration 'A. B. C.' becomes the fused 'A, B, and C.'."""
    picked = [re.sub(r"\s+", " ", c.strip()).rstrip(".").strip() for c in clauses if c and c.strip()]
    if not picked:
        return ""
    if len(picked) == 1:
        s = picked[0]
        return s[0].upper() + s[1:] + "."
    out = picked[0]
    for i, c in enumerate(picked[1:], start=1):
        c = (c[0].lower() + c[1:]) if c[:1].isupper() else c        # lowercase mid-sentence
        conn = ", and " if i == len(picked) - 1 else ", "
        out += conn + c
    out = out.strip()
    return out[0].upper() + out[1:] + "."


def grounding_ok_en(output: str, clauses: list[str]) -> bool:
    """English grounding gate: every clause's content survives verbatim in the fused output (the join
    only adds connectives, so a well-formed fusion always passes; this catches a broken join)."""
    o = re.sub(r"\s+", " ", output)
    for c in clauses:
        core = re.sub(r"\s+", " ", str(c).strip()).rstrip(".").strip()
        if core and core[: max(6, len(core) - 3)] not in o:
            return False
    return True


def grounding_ok(output: str, clauses: list[str]) -> bool:
    """The grounding hard-gate for the realizer: every grounded clause's CONTENT core must survive
    in the fused output (fusion may reshape endings, never drop or invent facts)."""
    for c in clauses:
        core = _verb_stem(c).strip(" .!?。") if _is_clause_verb_final(c) else c.strip(" .!?。")
        core = core[:-1] if core.endswith("있") else core
        if core and core[: max(4, len(core) - 2)] not in output:
            return False
    return True
