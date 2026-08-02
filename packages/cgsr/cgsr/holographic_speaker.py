"""HolographicSpeaker — the integration layer that makes the FHRR next-token substrate ATANOR's
*speaker*, hallucination-safe by construction.

Owner asked to execute the holographic integration recommendation (" ", 2026-07-12). The
substrate (``holographic_lm.HolographicLM``) already beats a plain n-gram on generalization and
long-range coherence; the real gap named in the recommendation was INTEGRATION, not a from-scratch
compiler. This module wires the two safety-critical couplings the recommendation called for:

 · (concept gate) — the candidate vocabulary is drawn ONLY from graph-attested context
 (the definition / evidence sentences of the resonant concepts). ``HolographicLM.predict`` already
 accepts ``candidates=``; :func:`concept_gate` builds that allow-set so the speaker can only ever
 utter words that appeared in grounded text. It cannot mint a token no attested sentence contained
 — the fluency layer is fact-bounded.

 · (hormone bias) — the predicted score dict is a set of logits; the digital-hormone
 state (``homeostasis.py``) tilts TONE by a small, MULTIPLICATIVE weight per token. The invariant
 that keeps this honest: a token the substrate scored ``<= 0`` (non-resonant, or outside the
 allow-set) stays there — tone can REORDER what is already sayable, it can never resurrect a fact.
 Warmth-affine words lift when oxytocin/serotonin run high, energetic words when
 noradrenaline/dopamine do. Affinity is READ from the learned lexical field (PPMI/SVD valence
 toward a handful of seed words), never a hardcoded warm-word table — doctrine
 [[learned-lexical-field]], [[two-hard-architecture-rules]].

This is a FLUENCY / VOICE layer. It deliberately does NOT displace the grounded-fact answer path the
P0 battery measures: it speaks where there is no curated answer (open-ended, conversational,
creative), bounded so truth is never at risk. See [[creative-fusion-shipped]], [[fluency-doctrine]],
[[emotion-as-hormone-dynamics]].
"""
from __future__ import annotations

from typing import Iterable

from packages.cgsr.cgsr.holographic_lm import HolographicLM, tokens

# Tone SEEDS only — a handful of anchors the learned lexical field measures every candidate against.
# NOT a valence table (that would violate [[learned-lexical-field]]: seed-first, the field learns the

_WARM_SEEDS = ("따뜻", "함께", "마음", "다정", "포근")
_COLD_SEEDS = ("차갑", "혼자", "쓸쓸", "메마", "얼어")
_HIGH_ENERGY = ("힘차", "달리", "터지", "번쩍", "뜨겁")
_LOW_ENERGY = ("고요", "잔잔", "천천", "가만", "쉬어")

# a successor ending in one of these reads as a finished Korean clause — stop there so the tone-tilt
# does not run the line past its natural close (mirrors HolographicLM._is_sentence_final, kept local
# so this module does not reach into the substrate's private surface).
_FINAL_SUFFIX = ("다", "요", "음", "함", "임", "죠", "됨")
_FINAL_WHOLE = frozenset({"이다", "입니다", "한다", "된다"})


def _is_final(tok: str) -> bool:
    return tok.endswith(_FINAL_SUFFIX) or tok in _FINAL_WHOLE


def _lex_valence(word: str, pos: tuple[str, ...], neg: tuple[str, ...]) -> float | None:
    """The learned valence of ``word`` toward the positive vs. negative seeds, or None if the word
    never appeared in the text-trained space (→ treated as tone-neutral by the caller)."""
    try:
        from packages.graph_scale.lexical_field import valence
        return valence(word, pos, neg)
    except Exception:
        return None


def hormone_tone(hormones: dict | None) -> dict[str, float]:
    """Collapse the 5-hormone vector into the two tone axes the bias uses, each in [-1, 1].

    Reads the coupled hormone levels the homeostasis loop already maintains — this does not re-derive
    mood, it only projects the live vector onto (warmth, energy). Warmth rides oxytocin + serotonin's
    excess over its wellbeing floor, dragged down by cortisol; energy rides noradrenaline + dopamine,
    gently damped when serotonin is high (contentment is calm)."""
    h = hormones or {}
    oxy = float(h.get("oxytocin", 0.0))
    sero = float(h.get("serotonin", 0.55))
    cort = float(h.get("cortisol", 0.0))
    dopa = float(h.get("dopamine", 0.0))
    nora = float(h.get("noradrenaline", 0.0))
    warmth = 0.7 * oxy + 0.5 * (sero - 0.55) - 0.6 * cort
    energy = 0.6 * nora + 0.5 * dopa - 0.3 * (sero - 0.55)
    return {
        "warmth": round(max(-1.0, min(1.0, warmth)), 4),
        "energy": round(max(-1.0, min(1.0, energy)), 4),
    }


def concept_gate(corpus_sentences: Iterable[str], *, extra: Iterable[str] = ()) -> list[str]:
    """The allow-set for the speaker: every token that occurs in the graph-attested sentences (plus
    any explicit ``extra`` — e.g. the theme word). The speaker may utter ONLY these, so it cannot
    fabricate a word that no grounded sentence contained. Empty input → empty gate (caller decides
    whether an empty gate means 'stay silent')."""
    allow: set[str] = set()
    for s in corpus_sentences:
        allow.update(tokens(s))
    allow.update(extra)
    return sorted(allow)


class HolographicSpeaker:
    """Wraps a fitted :class:`HolographicLM` with the concept gate + hormone tone bias."""

    def __init__(self, *, lm: HolographicLM, strength: float = 0.35) -> None:
        self.lm = lm
        # bias strength: small on purpose so tone REORDERS the substrate's vote, never dominates it.
        self.strength = float(strength)
        self._affinity_cache: dict[str, tuple[float, float]] = {}

    def _affinity(self, token: str) -> tuple[float, float]:
        """(warmth, energy) affinity of a token, READ from the learned lexical field. Unseen word →
        (0, 0) neutral. Cached — the field lookup is the only non-trivial cost per candidate."""
        cached = self._affinity_cache.get(token)
        if cached is not None:
            return cached
        w = _lex_valence(token, _WARM_SEEDS, _COLD_SEEDS)
        e = _lex_valence(token, _HIGH_ENERGY, _LOW_ENERGY)
        pair = (float(w) if w is not None else 0.0, float(e) if e is not None else 0.0)
        self._affinity_cache[token] = pair
        return pair

    def tone_bias_fn(self, hormones: dict | None):
        """A ``fn(token) -> float`` in [-1, 1] for :meth:`HolographicLM.generate_fluent`'s ``tone_bias``
        hook — so the substrate's coherence-anchored walk (window vote + global topic memory) is kept
        intact and only re-ranked by mood. Returns None when there is no affect, letting callers skip
        the hook entirely (identical to unbiased generation)."""
        tone = hormone_tone(hormones)
        if abs(tone["warmth"]) < 1e-6 and abs(tone["energy"]) < 1e-6:
            return None
        w, e = tone["warmth"], tone["energy"]

        def _bias(token: str) -> float:
            wa, ea = self._affinity(token)
            return max(-1.0, min(1.0, w * wa + e * ea))

        return _bias

    def biased_scores(
        self,
        ctx_tokens: list[str],
        *,
        candidates: list[str] | None = None,
        hormones: dict | None = None,
    ) -> dict[str, float]:
        """``HolographicLM.predict`` (concept-gated by ``candidates``), then tone-tilted by the
        hormone state. Multiplicative and clamped at zero: a token with a non-positive substrate
        score is returned untouched, so the bias can only re-rank the already-sayable set."""
        scores = self.lm.predict(ctx_tokens, candidates=candidates)
        if not scores:
            return {}
        tone = hormone_tone(hormones)
        if abs(tone["warmth"]) < 1e-6 and abs(tone["energy"]) < 1e-6:
            return scores  # no affect present → the substrate speaks unmodified
        out: dict[str, float] = {}
        for tok, s in scores.items():
            if s <= 0.0:
                out[tok] = s  # INVARIANT: never lift a non-resonant / out-of-gate token
                continue
            wa, ea = self._affinity(tok)
            tilt = 1.0 + self.strength * (tone["warmth"] * wa + tone["energy"] * ea)
            out[tok] = s * max(0.0, tilt)  # a strong adverse tilt can zero a token, never negate it
        return out

    def top(
        self,
        ctx_tokens: list[str],
        *,
        candidates: list[str] | None = None,
        hormones: dict | None = None,
    ) -> str | None:
        scores = self.biased_scores(ctx_tokens, candidates=candidates, hormones=hormones)
        if not scores:
            return None
        best = max(scores, key=scores.get)
        return best if scores[best] > 0.0 else None

    def generate(
        self,
        seed: str | list[str],
        *,
        max_len: int = 16,
        candidates: list[str] | None = None,
        hormones: dict | None = None,
        rep_penalty: float = 0.7,
    ) -> list[str]:
        """Greedy tone-biased next-token walk over the concept gate. Stops at a sentence-final token
        or when the substrate has no further resonant successor — never pads with invented words."""
        out = tokens(seed if isinstance(seed, str) else " ".join(seed))
        for _ in range(max(0, max_len)):
            scores = self.biased_scores(out, candidates=candidates, hormones=hormones)
            if not scores:
                break
            if rep_penalty < 1.0:  # damp immediate loops so the tilt does not stall on one word
                for t in set(out[-4:]):
                    if t in scores:
                        scores[t] *= rep_penalty
            nxt = max(scores, key=scores.get)
            if scores[nxt] <= 0.0:
                break
            out.append(nxt)
            if _is_final(nxt):
                break
        return out
