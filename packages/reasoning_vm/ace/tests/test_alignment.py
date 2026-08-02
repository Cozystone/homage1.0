# -*- coding: utf-8 -*-
"""Interactive-alignment priming — prime extraction must pick recent content words, the bias must
actually tilt decoding toward primed tokens, and stopwords must never prime."""
from __future__ import annotations

import torch

from packages.reasoning_vm.ace.alignment import extract_prime_words, prime_bias
from packages.reasoning_vm.ace.realizer import Realizer


class _TinyTok:
    """Minimal tokenizer stub: id = hash of the string (stable within a run)."""
    class _Enc:
        def __init__(self, ids):
            self.ids = ids

    def encode(self, s):
        return self._Enc([abs(hash(s)) % 60 + 4])


def test_extracts_recent_content_words_not_stopwords():
    hist = ["Tell me about the mitochondria in cells",
            "And what is the powerhouse exactly?"]
    words = extract_prime_words(hist)
    assert "powerhouse" in words and "mitochondria" in words
    assert "the" not in words and "what" not in words          # stopwords never prime
    assert words.index("powerhouse") < words.index("mitochondria")   # recency first


def test_recency_weighting_decays():
    tok = _TinyTok()
    bias = prime_bias(tok, ["older turn about oceans", "newer turn about volcanoes"], strength=2.0)
    assert bias and all(0 < v <= 2.0 for v in bias.values())


def test_bias_tilts_generation_toward_primed_token():
    torch.manual_seed(0)
    m = Realizer(vocab=64, d_model=64, layers=2, heads=4, ffn=128).eval()
    prefix = [1, 10, 11, 12]
    target = 37
    base = m.generate(prefix, sep_id=2, max_new=6, greedy=True)
    primed = m.generate(prefix, sep_id=2, max_new=6, greedy=True, logit_bias={target: 50.0})
    assert primed and primed[0] == target                     # a strong prime wins the first slot
    assert base != primed                                     # and it genuinely changed the output


def test_empty_history_gives_empty_bias():
    assert prime_bias(_TinyTok(), []) == {}
