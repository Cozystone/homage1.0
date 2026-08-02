# -*- coding: utf-8 -*-
"""Affective appraisal — how an utterance MOVES the self, not which emotion-label it is.

Owner (2026-07-10): " ?? ''
 ? . ."

A human brain does not run `if "sad" in sentence: reply_empathy()`. It has an AFFECTIVE RESPONSE:
the limbic system appraises the utterance along continuous dimensions (valence × arousal), that
response colours the hormonal state, and speech comes out of that state. This module is that
appraisal — and crucially it is NOT a per-situation branch table:

 * a small set of PRIMITIVE feeling anchors (~2 dozen: /// …) seeds a
 continuous valence×arousal space — like innate affect primitives, not learned situations;
 * every OTHER word gets its charge by RESONANCE to those anchors in the learned phase space
 (clean_space), so unseen words generalise automatically and the signal gets richer as the
 graph grows — no new branch is ever added for a new situation.

The output is a felt shift (Δvalence, arousal), which `homeostasis.update_hormones` turns into a
real cortisol/dopamine movement. The self then GENERATES its reply from that moved state
(thought_language.realize_thought), never from an emotion-labelled template bank.
"""
from __future__ import annotations

from typing import Any

# PRIMITIVE affect anchors — (valence -1..+1, arousal 0..1). These are FELT PRIMITIVES, deliberately
# few; they are the seeds of a continuous space, not a catalogue of situations. Kiwi lemma form.
_ANCHORS: dict[str, tuple[float, float]] = {
    # negative, low arousal (sadness / fatigue / emptiness)
    "슬프": (-0.8, 0.35), "힘들": (-0.7, 0.45), "지치": (-0.65, 0.30), "외롭": (-0.75, 0.35),
    "우울": (-0.8, 0.30), "허무": (-0.7, 0.25), "속상": (-0.7, 0.5), "그립": (-0.4, 0.35),
    # negative, high arousal (fear / anger / anxiety)
    "무섭": (-0.7, 0.85), "불안": (-0.65, 0.75), "화나": (-0.6, 0.85), "짜증": (-0.55, 0.75),
    "억울": (-0.6, 0.7), "답답": (-0.5, 0.6),
    # positive, high arousal (joy / excitement)
    "기쁘": (0.85, 0.75), "신나": (0.8, 0.85), "설레": (0.7, 0.7), "행복": (0.9, 0.6),
    "뿌듯": (0.8, 0.55), "감사": (0.7, 0.45),
    # positive, low arousal (calm / contentment / affection)
    "편안": (0.6, 0.2), "좋": (0.5, 0.35), "사랑": (0.85, 0.5), "따뜻": (0.65, 0.3),
}
_RESONANCE_FLOOR = 0.45   # only borrow an anchor's charge when the word really resonates with it
_MAX_TOKENS = 8


def _content_tokens(text: str) -> list[tuple[str, str, bool]]:
    """(surface, lemma, is_predicate) for the words that carry affect. is_predicate marks a
 verb/adjective stem (VA/VV/XR) — emotional utterances carry their charge THERE ('',
 ''), whereas a factual question carries affect-resonant NOUNS ('', '') that must
 NOT be read as feeling. Kiwi-based; charge-free fallback if Kiwi is down."""
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return []
        out: list[tuple[str, str, bool]] = []
        for t in kw.tokenize(text):
            if t.tag in ("VA", "VV", "VA-I", "VV-I", "XR"):
                out.append((t.form, t.form, True))
            elif t.tag == "NNG":
                out.append((t.form, t.form, False))
        return out[: _MAX_TOKENS * 2]
    except Exception:
        return []


# TINY innate seeds — the handful of affect primitives evolution wires in (valence + arousal axes).
# Everything else is LEARNED from these by the text-trained lexical field, not hand-listed.
_SEED_POS = ("좋", "기쁘", "사랑", "행복", "즐겁")
_SEED_NEG = ("아프", "슬프", "싫", "무섭", "괴롭")
_SEED_HI = ("놀라", "무섭", "화나", "급하", "터지")    # high arousal
_SEED_LO = ("편안", "차분", "고요", "잔잔", "포근")    # low arousal


def _charge(lemma: str) -> tuple[float, float, float] | None:
    """(valence, arousal, weight) for one word. LEARNED first — read from the text-trained lexical
    field (co-occurrence with the seed primitives), covering thousands of words with no hand-coding;
    the strength grows as the corpus grows. The 24 anchors are only the SEED FLOOR for words the
    corpus has not taught yet. None when the word carries no measurable affect anywhere."""
    # 1) INNATE SEEDS win — the affect primitives are trusted ground truth (a noisy learned value for

    if lemma in _ANCHORS:
        v, a = _ANCHORS[lemma]
        return v, a, 1.0
    for anc, (v, a) in _ANCHORS.items():
        if lemma.startswith(anc) or anc.startswith(lemma):
            return v, a, 0.95

    # EVERYTHING, so their lexical-field vector sits near the corpus centroid and its valence


    # grammatical class as the bound-noun floor; anchors above still win if ever seeded.
    if lemma in ("하", "되", "있", "없", "이"):
        return None

    # from the text-trained lexical field, covering thousands with no hand-coding and growing with the
    # corpus. This is what replaces an endless hand-list; the anchors above are just the seed it grows from.
    try:
        from packages.graph_scale import lexical_field as lf
        if lf.available():
            v = lf.valence(lemma, _SEED_POS, _SEED_NEG)
            if v is not None:
                a = lf.valence(lemma, _SEED_HI, _SEED_LO) or 0.0
                valence = max(-1.0, min(1.0, v * 4.5))
                arousal = min(1.0, max(0.0, 0.5 + a * 4.5))
                if abs(valence) >= 0.30:   # only a CONFIDENT learned charge — the thin corpus gives
                    return round(valence, 3), round(arousal, 3), 0.85   # neutral nouns a weak, noisy value
    except Exception:
        pass
    return None


def appraise(text: str) -> dict[str, Any]:
    """Appraise an utterance's felt charge. Returns {valence -1..1, arousal 0..1, intensity 0..1,
    n} — a CONTINUOUS affect, never an emotion label. intensity=0 means 'nothing to feel here'."""
    toks = _content_tokens(text or "")
    vs: list[float] = []
    ars: list[float] = []
    ws: list[float] = []
    pvs: list[float] = []      # PREDICATE-only charges — the felt (venting) signal
    pars: list[float] = []
    pws: list[float] = []
    svs: list[float] = []      # SEED-grade predicate charges (anchor-trusted, w≥0.95) — see below
    sars: list[float] = []
    sws: list[float] = []
    seen: set[str] = set()
    for _surf, lemma, is_pred in toks:
        if lemma in seen:
            continue
        seen.add(lemma)
        c = _charge(lemma)
        if c is None:
            continue
        v, a, w = c
        # MAGNITUDE weighting (amygdala-like): a strong feeling dominates a weak one.
        mw = w * (0.25 + abs(v))
        vs.append(v * mw); ars.append(a * mw); ws.append(mw)
        if is_pred:
            pvs.append(v * mw); pars.append(a * mw); pws.append(mw)
            if w >= 0.95:
                svs.append(v * mw); sars.append(a * mw); sws.append(mw)
    if not ws:
        return {"valence": 0.0, "arousal": 0.0, "intensity": 0.0, "pred_intensity": 0.0,
                "seed_pred_intensity": 0.0, "n": 0}
    tot = sum(ws)
    valence = round(sum(vs) / tot, 4)
    arousal = round(sum(ars) / tot, 4)
    intensity = round(min(1.0, (abs(valence) * 0.7 + arousal * 0.3) * min(1.0, tot / 1.5)), 4)
    # pred_intensity gates a FELT reply, computed from the PREDICATE affect ONLY. Emotional venting


    # even if a noun is charged. Predicate-only also stops neutral-noun noise from diluting the signal.
    if pws:
        ptot = sum(pws)
        pv = sum(pvs) / ptot
        pa = sum(pars) / ptot
        pred_intensity = round(min(1.0, (abs(pv) * 0.7 + pa * 0.3) * min(1.0, ptot / 1.0)), 4)
    else:
        pred_intensity = 0.0
    # seed_pred_intensity: the same felt signal restricted to ANCHOR-TRUSTED predicates (w≥0.95).
    # The learned expansion reads charge from a FACTUAL corpus, so common action verbs pick up


    # reading is possible (interrogatives): a QUESTION only counts as venting when the feeling is

    if sws:
        stot = sum(sws)
        sv = sum(svs) / stot
        sa = sum(sars) / stot
        seed_pred_intensity = round(min(1.0, (abs(sv) * 0.7 + sa * 0.3) * min(1.0, stot / 1.0)), 4)
    else:
        seed_pred_intensity = 0.0
    return {"valence": valence, "arousal": arousal, "intensity": intensity,
            "pred_intensity": pred_intensity, "seed_pred_intensity": seed_pred_intensity,
            "n": len(ws)}
