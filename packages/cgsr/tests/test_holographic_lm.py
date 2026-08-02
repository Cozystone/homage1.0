"""Holographic associative substrate: generalizes + uses wide context, beating the bigram baseline."""
from __future__ import annotations

import json
import pathlib
from collections import Counter, defaultdict

import numpy as np
import pytest

from cgsr.holographic_lm import HolographicLM, resonance, tokens

_EVIDENCE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "data" / "cloud_brain" / "candidate_runs" / "clean_retrain_v1" / "evidence.jsonl"
)

# Shapes are decided by the NOUN, which sits BEFORE the shared token "IS". A last-token bigram
# therefore cannot tell round from square (it only sees "IS"); the holographic window can.
_NOUNS = {"ball": "round", "box": "square", "ring": "round", "cube": "square", "plate": "round", "brick": "square"}


def _train_corpus():
    corpus = []
    for mod in ("red", "blue"):
        for noun, shape in _NOUNS.items():
            corpus.append(f"{mod} {noun} IS {shape}")
    return corpus


def test_wide_context_disambiguates_where_bigram_cannot():
    lm = HolographicLM(window=3, seed=7).fit(_train_corpus())
    for noun, shape in _NOUNS.items():
        holo = lm.predict([noun, "IS"], candidates=["round", "square"])
        assert max(holo, key=holo.get) == shape, (noun, holo)
    # the bigram sees only "IS" → it is at chance (round and square tie)
    bg = lm.predict_bigram(["ball", "IS"])
    assert abs(bg.get("round", 0) - bg.get("square", 0)) < 1e-9


def test_generalizes_to_unseen_modifier_and_beats_bigram():
    lm = HolographicLM(window=3, seed=7).fit(_train_corpus())
    holo_correct = 0
    bigram_correct = 0
    for noun, shape in _NOUNS.items():
        ctx = ["green", noun, "IS"]  # "green" never appears in training
        holo = lm.predict(ctx, candidates=["round", "square"])
        if holo and max(holo, key=holo.get) == shape:
            holo_correct += 1
        bg = lm.predict_bigram(ctx)
        if bg and max(bg, key=bg.get) == shape:
            bigram_correct += 1
    holo_acc = holo_correct / len(_NOUNS)
    bigram_acc = bigram_correct / len(_NOUNS)
    assert holo_acc >= 0.9, holo_acc          # generalizes via the shared sub-context
    assert bigram_acc <= 0.6, bigram_acc      # last-token baseline is at chance
    assert holo_acc > bigram_acc + 0.3


def test_generation_stays_on_topic_coherence():
    # Two disjoint topics; a topic seed must not drift into the other topic's vocabulary.
    corpus = [
        "물고기 는 물 에서 헤엄친다", "물 은 강 에서 흐른다", "강 에서 물고기 가 헤엄친다",
        "로켓 은 우주 로 날아간다", "우주 에서 로켓 이 날아간다", "우주 는 넓다",
    ]
    lm = HolographicLM(window=3, seed=7).fit(corpus)
    out = lm.generate(["물고기", "는"], length=6)
    space_words = {"로켓", "우주"}
    assert not (set(out) & space_words), out  # stayed in the water topic


def test_no_fabrication_only_corpus_tokens():
    corpus = ["alpha beta gamma", "beta gamma delta"]
    lm = HolographicLM(window=2, seed=7).fit(corpus)
    vocab = set(tokens(" ".join(corpus)))
    out = lm.generate("alpha", length=8)
    assert set(out) <= vocab  # never emits a token not grounded in the corpus


def test_deterministic():
    a = HolographicLM(window=3, seed=7).fit(_train_corpus()).predict(["ball", "IS"], candidates=["round", "square"])
    b = HolographicLM(window=3, seed=7).fit(_train_corpus()).predict(["ball", "IS"], candidates=["round", "square"])
    assert a == b


def test_semantic_base_resonance_is_distributional():
    # co-occurrence-similar tokens must resonate; dissimilar ones must not.
    train = ["dog runs", "cat runs", "dog eats", "cat eats", "car drives", "truck drives"]
    lm = HolographicLM(window=1, seed=7, semantic=True, bandwidth=2.0).fit(train)
    dog_cat = resonance(lm._filler_vec["dog"], lm._filler_vec["cat"])
    dog_car = resonance(lm._filler_vec["dog"], lm._filler_vec["car"])
    assert dog_cat > 0.5
    assert dog_car < 0.2
    assert dog_cat > dog_car + 0.4


def test_semantic_generalization_that_token_overlap_cannot_do():
    # puppy/sedan NEVER precede barks/honks — only DISTRIBUTIONAL similarity can decide, so
    # this is generalization the random-base (token-overlap) model cannot reach.
    train = [
        "dog chased ball", "cat chased ball", "puppy chased ball",
        "dog ate bone", "cat ate bone", "puppy ate bone",
        "car drove road", "truck drove road", "sedan drove road",
        "dog barks", "cat barks", "car honks", "truck honks",
    ]

    def decide(lm, tok):
        p = lm.predict([tok], candidates=["barks", "honks"])
        return max(p, key=p.get) if p else None

    sem = HolographicLM(window=1, seed=7, semantic=True, bandwidth=2.0).fit(train)
    assert decide(sem, "puppy") == "barks"   # animal-like → animal sound
    assert decide(sem, "sedan") == "honks"   # machine-like → machine sound

    rnd = HolographicLM(window=1, seed=7, semantic=False).fit(train)
    # random base has no distributional kinship → it cannot get both right
    assert not (decide(rnd, "puppy") == "barks" and decide(rnd, "sedan") == "honks")


def test_semantic_mode_is_deterministic():
    train = ["dog runs", "cat runs", "car drives"]
    a = HolographicLM(window=1, seed=7, semantic=True).fit(train).predict(["dog"], candidates=["runs", "drives"])
    b = HolographicLM(window=1, seed=7, semantic=True).fit(train).predict(["dog"], candidates=["runs", "drives"])
    assert a == b


@pytest.mark.skipif(not _EVIDENCE.exists(), reason="real corpus not present in this checkout")
def test_beats_bigram_on_real_held_out_sentences():
    # The honest bar: on REAL encyclopedic sentences, kernel-vote top-1 next-token accuracy must
    # beat the last-token bigram the surface walk uses today. No training, no LLM.
    sents = []
    for line in _EVIDENCE.open(encoding="utf-8"):
        try:
            text = json.loads(line).get("text") or ""
        except Exception:
            continue
        toks = tokens(text)
        if 4 <= len(toks) <= 40:
            sents.append(toks)
    rng = np.random.default_rng(0)
    rng.shuffle(sents)
    cut = int(len(sents) * 0.85)
    train, test = sents[:cut], sents[cut:]
    lm = HolographicLM(dim=512, window=4, seed=7, semantic=True, bandwidth=3.0).fit([" ".join(s) for s in train])
    bigram: dict[str, Counter] = defaultdict(Counter)
    for s in train:
        for i in range(1, len(s)):
            bigram[s[i - 1]][s[i]] += 1
    bigram_top = {k: c.most_common(1)[0][0] for k, c in bigram.items()}
    holo_hits = bigram_hits = total = 0
    for s in test:
        for i in range(1, len(s)):
            if s[i] not in lm._successors:
                continue
            scores = lm.predict(s[max(0, i - 4):i])
            holo = max(scores, key=scores.get) if scores else None
            holo_hits += holo == s[i]
            bigram_hits += bigram_top.get(s[i - 1]) == s[i]
            total += 1
            if total >= 600:
                break
        if total >= 600:
            break
    assert total > 200
    assert holo_hits / total > bigram_hits / total, (holo_hits / total, bigram_hits / total)


def test_generate_fluent_completes_and_is_grounded():
    corpus = [
        "광합성 은 빛 에너지 를 화학 에너지 로 바꾸는 과정 이다",
        "호흡 은 산소 를 사용 하는 과정 이다",
    ]
    lm = HolographicLM(dim=256, window=4, seed=7, semantic=True).fit(corpus)
    out = lm.generate_fluent("광합성", max_len=20)
    vocab = set(tokens(" ".join(corpus)))
    assert set(out) <= vocab                    # grounded — only corpus tokens
    assert lm._is_sentence_final(out[-1])        # stops at a complete sentence


def test_generate_fluent_stays_coherent_no_topic_drift():

    # them; the global-superposition coherence must keep generation inside ONE topic.
    corpus = [
        "물고기 는 물 에서 헤엄친다", "물 은 강 에서 흐른다", "강 에서 물고기 가 헤엄친다",
        "로켓 은 우주 로 날아간다", "우주 에서 로켓 이 날아간다", "우주 는 넓다",
    ]
    lm = HolographicLM(dim=256, window=4, seed=7, semantic=True).fit(corpus)
    out = lm.generate_fluent("물고기", max_len=12)
    assert not ({"로켓", "우주"} & set(out)), out   # stayed in the water topic, no drift


def test_generate_fluent_deterministic():
    corpus = ["광합성 은 빛 을 화학 에너지 로 바꾸는 과정 이다"]
    lm = HolographicLM(dim=256, window=4, seed=7, semantic=True).fit(corpus)
    assert lm.generate_fluent("광합성") == lm.generate_fluent("광합성")


def test_bind_unbind_recovers():
    lm = HolographicLM(dim=2048, seed=7)
    role = lm.space.vec("role")
    filler = lm.space.vec("filler")
    bound = lm.space.bind(role, filler)
    recovered = lm.space.unbind(bound, role)
    assert resonance(recovered, filler) > 0.99  # FHRR bind is invertible
