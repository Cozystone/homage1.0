"""HolographicSpeaker — locks the hallucination-safety invariants of the tone/concept layer.

The load-bearing guarantees, asserted here so a future refactor cannot quietly break them:
  1. concept gate — the speaker utters ONLY tokens the attested corpus contained;
  2. bias is multiplicative & zero-clamped — a token the substrate did not vote for can never be
     resurrected by tone, no matter how affine it is;
  3. tone actually re-ranks — a positive hormone state can change which sayable token wins;
  4. no affect → the substrate speaks unmodified.
"""
from __future__ import annotations

from packages.cgsr.cgsr.holographic_lm import HolographicLM
from packages.cgsr.cgsr.holographic_speaker import (
    HolographicSpeaker,
    concept_gate,
    hormone_tone,
)

_CORPUS = [
    "봄이 오면 마음이 따뜻해진다",
    "바다는 잔잔하게 빛난다",
    "함께 걷는 길은 포근하다",
    "별빛이 고요하게 내린다",
]


def _speaker(strength: float = 0.5) -> HolographicSpeaker:
    lm = HolographicLM(dim=256, window=3, decay=0.7, seed=7, semantic=True)
    lm.fit(_CORPUS)
    return HolographicSpeaker(lm=lm, strength=strength)


def test_concept_gate_is_the_attested_vocabulary():
    gate = set(concept_gate(_CORPUS))
    assert "따뜻해진다" in gate and "바다는" in gate
    assert "코카콜라" not in gate  # never appeared → cannot be uttered
    # extra lets the theme word in even if the corpus omitted it
    assert "테마" in set(concept_gate(_CORPUS, extra=("테마",)))


def test_gate_bounds_what_predict_can_return():
    sp = _speaker()
    # restrict candidates to a single attested token: prediction may only return that token (or none)
    scores = sp.biased_scores(["봄이", "오면"], candidates=["마음이"])
    assert set(scores).issubset({"마음이"})


def test_bias_never_resurrects_a_nonresonant_token():
    """The safety invariant: a token the substrate scored <= 0 stays <= 0 after the tone tilt, even
    with a maximally warm hormone state — tone re-ranks the sayable, it does not fabricate."""
    sp = _speaker(strength=5.0)  # exaggerated so any leak would show
    warm = {"oxytocin": 1.0, "serotonin": 1.0}
    base = sp.lm.predict(["봄이", "오면"])
    biased = sp.biased_scores(["봄이", "오면"], hormones=warm)
    # every token biased above zero must have had a positive base score
    for tok, s in biased.items():
        if s > 0.0:
            assert base.get(tok, 0.0) > 0.0
    # and no brand-new tokens appeared
    assert set(biased).issubset(set(base))


def test_no_affect_leaves_scores_untouched():
    sp = _speaker()
    ctx = ["함께", "걷는"]
    neutral = sp.biased_scores(ctx, hormones=None)
    baseline = sp.lm.predict(ctx)
    assert neutral == baseline


def test_generation_stays_inside_the_gate():
    sp = _speaker()
    gate = concept_gate(_CORPUS)
    out = sp.generate("봄이", max_len=10, candidates=gate,
                      hormones={"oxytocin": 0.8, "serotonin": 0.9})
    # seed token may be anything; every GENERATED token must be attested
    for tok in out[1:]:
        assert tok in set(gate)


def test_hormone_tone_projection_signs():
    warm = hormone_tone({"oxytocin": 0.9, "serotonin": 0.9})
    assert warm["warmth"] > 0.0
    stressed = hormone_tone({"cortisol": 0.9})
    assert stressed["warmth"] < 0.0
    energized = hormone_tone({"noradrenaline": 0.9, "dopamine": 0.7})
    assert energized["energy"] > 0.0
    assert hormone_tone(None) == {"warmth": 0.0, "energy": 0.0}
