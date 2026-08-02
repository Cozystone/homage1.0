# -*- coding: utf-8 -*-
"""Relation extractor v3: higher-order patterns pull real triples, junk is
rejected, and the topology gate + Surgeon keep it to gated candidates."""


def test_english_definitional_and_hyponym():
    from packages.graph_scale.relation_extractor import extract_triples
    t = {(x["s"], x["p"], x["o"]) for x in
         extract_triples("System 2 is a slow process.", "en")}
    assert ("System 2", "is_a", "slow process") in t
    # hyponymy swaps direction: (dogs, is_a, animals)
    h = {(x["s"], x["p"], x["o"]) for x in
         extract_triples("animals such as dogs and cats", "en")}
    assert ("dogs", "is_a", "animals") in h


def test_clause_swallowing_subject_is_trimmed_to_the_head():
    from packages.graph_scale.relation_extractor import extract_triples
    # the regex would grab 'Amos reported that the answer' as subject; the clause
    # split must keep only 'answer' (the real NP nearest the verb)
    t = {(x["s"], x["p"], x["o"]) for x in
         extract_triples("Amos reported that the answer was a qualified yes.", "en")}
    assert ("answer", "is_a", "qualified yes") in t
    assert not any(x["s"].startswith("Amos reported") for x in
                   extract_triples("Amos reported that the answer was a qualified yes.", "en"))


def test_causal_verb_and_junk_rejected():
    from packages.graph_scale.relation_extractor import extract_triples
    v = {(x["s"], x["p"], x["o"]) for x in
         extract_triples("Smoking causes cancer.", "en")}
    assert ("Smoking", "원인", "cancer") in v
    # pronoun subject + vacuous head must NOT become a triple
    junk = extract_triples("It is a good idea.", "en")
    assert junk == []


def test_korean_definitional():
    from packages.graph_scale.relation_extractor import extract_triples
    t = {(x["s"], x["p"], x["o"]) for x in extract_triples("고양이는 동물이다.", "ko")}
    assert ("고양이", "is_a", "동물") in t


def test_topology_score_is_none_without_space(monkeypatch):
    """No trained space -> no topology signal (None), not a crash or a fake score."""
    from packages.graph_scale import relation_extractor as rx
    from packages.graph_scale import phase_space
    monkeypatch.setattr(phase_space, "_load", lambda: False)
    assert rx.topology_score("a", "is_a", "b") is None


def test_extract_from_sentences_writes_gated_candidates(tmp_path):
    from packages.graph_scale.relation_extractor import extract_from_sentences
    sents = ["A dog is an animal.", "Smoking causes cancer.",
             "It is a good idea.", "birds such as sparrows"]
    r = extract_from_sentences(sents, lang="en", store=None, out_dir=tmp_path)
    assert r["written_to_production"] is False
    assert r["candidates_written"] > 0 and "is_a" in r["predicates"]
    isa = (tmp_path / "extracted_is_a.jsonl").read_text(encoding="utf-8")
    assert '"tier": "candidate"' in isa and "rule+topology" in isa
    # idempotent
    r2 = extract_from_sentences(sents, lang="en", store=None, out_dir=tmp_path)
    assert r2["candidates_written"] == 0


def test_korean_predicate_filenames_stay_distinct(tmp_path):
    """Korean predicates (/) must land in distinct ledgers, not collide
 into one sanitized-to-underscores filename (a data-loss bug)."""
    from packages.graph_scale.relation_extractor import extract_from_sentences
    sents = ["Smoking causes cancer.", "water contains hydrogen."]
    extract_from_sentences(sents, lang="en", store=None, out_dir=tmp_path)
    names = {p.name for p in tmp_path.glob("extracted_*.jsonl")}
    assert "extracted_원인.jsonl" in names and "extracted_구성요소.jsonl" in names
