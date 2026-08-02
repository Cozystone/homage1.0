"""Corpus adapters turn open sentence data into graph fuel — definitional sentences into
triples, Tatoeba translation pairs into cross-lingual aliases, everything else into the
separate surface corpus. The fact lane must stay clean: only real definitions become facts."""
from __future__ import annotations

import tempfile
from pathlib import Path

from packages.graph_scale.corpus_adapters import (
    SentenceStore,
    extract_definition_triple,
    iter_definition_triples,
    iter_oscar_sentences,
    iter_tatoeba_alias_pairs,
    iter_wiktionary_definitions,
)


def test_korean_definition_extracts_is_a():
    assert extract_definition_triple("고양이는 포유류이다") == ("고양이", "defined_as", "포유류")
    assert extract_definition_triple("참새는 새의 일종이다") == ("참새", "is_a", "새")


def test_english_definition():
    # leading article is consumed now: "dog" is the canonical lookup key, "A dog" never was
    assert extract_definition_triple("A dog is a mammal") == ("dog", "is_a", "mammal")


def test_non_definition_yields_nothing():
    # conversational / non-copular sentences must NOT become facts (no fabrication)
    assert extract_definition_triple("나는 오늘 학교에 갔다") is None
    assert extract_definition_triple("What time is it?") is None
    assert extract_definition_triple("그것은 좋다") is None            # stop-word subject


def test_iter_definition_triples_filters_stream():
    sents = ["물은 액체이다", "안녕하세요 반갑습니다", "산소는 기체이다"]
    triples = list(iter_definition_triples(sents))
    assert ("물", "defined_as", "액체") in triples
    assert ("산소", "defined_as", "기체") in triples
    assert len(triples) == 2                                          # the greeting is dropped


def test_tatoeba_alias_pairs():
    d = Path(tempfile.mkdtemp())
    (d / "sentences.csv").write_text(
        "1\tkor\t인공지능\n2\teng\tartificial intelligence\n3\tkor\t나는 밥을 먹었다.\n",
        encoding="utf-8")
    (d / "links.csv").write_text("1\t2\n", encoding="utf-8")
    pairs = list(iter_tatoeba_alias_pairs(d / "sentences.csv", d / "links.csv"))
    assert ("인공지능", "alias", "artificial intelligence") in pairs


def test_oscar_jsonl_splits_sentences():
    d = Path(tempfile.mkdtemp())
    (d / "oscar.jsonl").write_text('{"text": "첫 문장이다. 둘째 문장이다."}\n', encoding="utf-8")
    sents = list(iter_oscar_sentences(d / "oscar.jsonl"))
    assert "첫 문장이다." in sents and "둘째 문장이다." in sents


def test_wiktionary_definition_head():
    d = Path(tempfile.mkdtemp())
    (d / "wik.jsonl").write_text(
        '{"word": "원자", "definition": "물질을 구성하는 기본 단위이다."}\n', encoding="utf-8")
    triples = list(iter_wiktionary_definitions(d / "wik.jsonl"))
    assert triples and triples[0][0] == "원자" and triples[0][1] == "defined_as"


def test_sentence_store_separate_from_facts():
    root = Path(tempfile.mkdtemp()) / "surface"
    ss = SentenceStore(root)
    r = ss.add_many(["안녕하세요", "반갑습니다", "안녕하세요"], lang="ko")   # last is a dup
    assert r["added"] == 2
    assert (root / "sentences.jsonl").exists()
    # reopening counts persisted lines
    assert len(SentenceStore(root)) == 2


def test_en_field_adverbial_and_process_frame_recall():
    from packages.graph_scale.corpus_adapters import extract_definition_triple as x
    assert x("In botany, a fruit is the seed-bearing structure in flowering plants.") == (
        "fruit", "is_a", "seed-bearing structure in flowering plants")
    s, p, o = x("Automated machine learning is the process of automating the tasks of applying machine learning to real-world problems.")
    assert s == "Automated machine learning" and p == "is_a"  # article guard: subject NOT clipped


def test_ko_relative_clause_object_and_garikinda_ending():
    from packages.graph_scale.corpus_adapters import extract_definition_triple as x
    assert x("성남시(城南市)는 경기도 중앙에 있는 시이다.") == ("성남시", "defined_as", "경기도 중앙에 있는 시")
    assert x("기획은 어떤 일을 도모하고 그 일의 절차를 구상하는 것을 가리킨다.") == (
        "기획", "defined_as", "어떤 일을 도모하고 그 일의 절차를 구상하는 것")


def test_precision_guards_hold_after_recall_expansion():
    from packages.graph_scale.corpus_adapters import extract_definition_triple as x
    assert x("그는 어제 학교에 갔다.") is None            # past tense stays out
    assert x("He is a teacher.") is None                   # stop-subject stays out
    assert x("In 1999, the company was a startup, and it grew.") is None  # comma clause stays out


def test_bridge_composes_multi_fact_subjects(tmp_path, monkeypatch):
    """P2 wiring: a subject with two stored predicates answers with a composed
    paragraph (grounded_composition), not the single-fact template."""
    from packages.graph_scale import answer_bridge as ab
    from packages.graph_scale.triple_store import TripleStore

    store = TripleStore(tmp_path / "kg")
    store.bulk_ingest([
        ("에스프레소", "defined_as", "곱게 간 원두에 고압의 물을 통과시켜 추출한 커피"),
        ("에스프레소", "is_a", "커피 음료"),
    ])
    store.flush()
    monkeypatch.setattr(ab, "_store", lambda: store)
    r = ab.answer_from_triples("에스프레소란?")
    assert r is not None and r["answer_kind"] == "grounded_composition"
    assert r["answer"].startswith("에스프레소는 곱게 간 원두에 고압의 물을 통과시켜 추출한 커피입니다.")
    # connective is learned (closed whitelist) — assert content, not one token
    from packages.grounded_composer.composer import _CONNECTIVES

    assert "커피 음료의 일종입니다." in r["answer"]
    assert any(f"{c} 커피 음료의 일종입니다." in r["answer"] for c in _CONNECTIVES)
    assert len(r["reasoning_certificate"]["steps"]) == 2
