"""Data-driven subword units (BPE) discover morpheme boundaries — no hand-coded morphology."""
from __future__ import annotations

from cgsr.bpe_tokenizer import learn_bpe, pretty, tokenize


KO = [
    "고양이는 동물이다", "고양이가 운다", "고양이를 봤다",
    "강아지는 동물이다", "강아지가 짖는다", "강아지를 봤다",
    "토끼는 동물이다", "토끼가 뛴다", "토끼를 봤다",
] * 4

EN = ["the cat is an animal", "the cat runs", "the dog is an animal", "the dog barks"] * 4


def test_korean_particle_boundary_is_discovered_for_held_out_form():
    merges = learn_bpe(KO, num_merges=80)


    assert pretty(tokenize("고양이도", merges)) == ["고양이", "도"]
    assert pretty(tokenize("강아지도", merges)) == ["강아지", "도"]


def test_stem_is_a_single_learned_unit():
    merges = learn_bpe(KO, num_merges=80)
    assert "".join(pretty(tokenize("고양이", merges))) == "고양이"
    assert len(tokenize("고양이", merges)) == 1  # the whole stem merged into one token


def test_language_agnostic_english_plural_morpheme():
    merges = learn_bpe(EN, num_merges=40)
    # 'cat' seen, 'cats' never → the plural -s falls out as its own unit.
    assert pretty(tokenize("cats", merges)) == ["cat", "s"]


def test_deterministic():
    assert learn_bpe(KO, num_merges=30) == learn_bpe(KO, num_merges=30)


def test_unseen_characters_survive():
    merges = learn_bpe(KO, num_merges=30)
    # a token with no learned merges is returned as its characters, never dropped
    assert "".join(pretty(tokenize("펭귄", merges))) == "펭귄"
