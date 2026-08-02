"""Golden tests for the English surface realizer (M1).

These lock the behaviour established when the English answer path was rebuilt
from a per-relation slot-filler into an aggregated, article-correct realizer:

  * English answers never leak Hangul (no Korean labels or repair injections).
  * Relations are aggregated under one pronoun subject instead of repeating the
    head concept once per relation.
  * Object noun phrases carry determiners where the relation expects one.
  * Answers end as clean sentences (single terminal period, no ``..``).
"""

from __future__ import annotations

import re

import pytest

from packages.base_brain.zero_user_answer import (
    _en_noun_phrase,
    _english_relation_sentence,
    _english_second_hop,
    _label,
    answer_with_base_brain,
)

_HANGUL = re.compile(r"[가-힣]")

EN_QUERIES = [
    "What is GraphRAG?",
    "What is ATANOR?",
    "Explain how local brain stores memory.",
    "What is an ontology graph?",
    "What is Kubernetes?",
    "What is the difference between local AI and cloud AI?",
    # Regression: these concept descriptions END with a period; the comparison
    # frame used to append another, yielding "... user.." (double period).
    "What is the difference between local brain and cloud brain?",
    "Why does evidence matter for reducing hallucination?",
]


def test_comparison_with_period_terminated_descriptions_is_clean(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    answer = answer_with_base_brain(
        "What is the difference between local brain and cloud brain?",
        language="en",
        audience_level="beginner",
    )["answer"]
    assert ".." not in answer, f"double period in comparison: {answer!r}"
    assert "By contrast," in answer  # still uses the comparison frame


def test_description_does_not_stutter_the_concept_name(tmp_path, monkeypatch) -> None:
    # "AI inference" whose description begins "inference uses …" used to render
    # "AI inference is inference uses …". The clause should stand on its own.
    monkeypatch.chdir(tmp_path)
    answer = answer_with_base_brain(
        "Compare AI training and AI inference.", language="en", audience_level="beginner"
    )["answer"]
    assert "is inference uses" not in answer.lower(), f"stutter: {answer!r}"
    assert "is training adjusts" not in answer.lower(), f"stutter: {answer!r}"
    assert ".." not in answer


@pytest.mark.parametrize("query", EN_QUERIES)
def test_english_answer_has_no_hangul_leak(query, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    answer = answer_with_base_brain(query, language="en", audience_level="beginner")["answer"]
    assert answer, "expected a non-empty answer"
    assert not _HANGUL.search(answer), f"Hangul leaked into English answer: {answer!r}"


@pytest.mark.parametrize("query", EN_QUERIES)
def test_english_answer_is_clean_sentence(query, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    answer = answer_with_base_brain(query, language="en", audience_level="beginner")["answer"]
    assert ".." not in answer, f"double period in answer: {answer!r}"
    assert answer.rstrip().endswith((".", "!", "?")), f"answer not terminated: {answer!r}"


def test_relations_do_not_repeat_the_subject(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    # GraphRAG has two relations; the old realizer emitted "GraphRAG ... GraphRAG ... GraphRAG ...".
    answer = answer_with_base_brain("What is GraphRAG?", language="en", audience_level="beginner")["answer"]
    assert answer.count("GraphRAG") == 1, f"subject repeated per relation: {answer!r}"
    assert " It " in answer or answer.split(". ", 1)[-1].startswith("It "), (
        f"expected pronoun-aggregated relation clause: {answer!r}"
    )


def test_relation_sentence_aggregates_and_articles() -> None:
    primary = {
        "concept_id": "atanor",
        "labels": {"en": "ATANOR"},
        "relations": [
            {"relation": "uses", "target": "semantic_graph"},
            {"relation": "uses", "target": "surface_graph"},
            {"relation": "requires", "target": "privacy"},
        ],
    }
    context_map = {
        "semantic_graph": {"concept_id": "semantic_graph", "labels": {"en": "semantic graph"}},
        "surface_graph": {"concept_id": "surface_graph", "labels": {"en": "surface graph"}},
        "privacy": {"concept_id": "privacy", "labels": {"en": "privacy"}},
    }
    sentence = _english_relation_sentence(primary, context_map)
    assert sentence.startswith("It ")
    assert "a semantic graph" in sentence  # countable object gets a determiner
    assert "requires privacy" in sentence  # uncountable object stays bare
    assert sentence.endswith(".")


def test_compound_clause_uses_oxford_comma() -> None:
    # M1.5: avoid run-on "uses X and Y and requires Z".
    primary = {
        "concept_id": "atanor",
        "labels": {"en": "ATANOR"},
        "relations": [
            {"relation": "uses", "target": "semantic_graph"},
            {"relation": "uses", "target": "surface_graph"},
            {"relation": "requires", "target": "privacy"},
        ],
    }
    context_map = {
        "semantic_graph": {"concept_id": "semantic_graph", "labels": {"en": "semantic graph"}},
        "surface_graph": {"concept_id": "surface_graph", "labels": {"en": "surface graph"}},
        "privacy": {"concept_id": "privacy", "labels": {"en": "privacy"}},
    }
    sentence = _english_relation_sentence(primary, context_map)
    assert "a semantic graph and a surface graph, and requires privacy" in sentence
    assert " and a surface graph and requires" not in sentence  # no run-on


def test_contrasts_with_takes_a_determiner() -> None:
    # M1.5: "contrasts with surface graph" -> "contrasts with a surface graph".
    primary = {
        "concept_id": "semantic_graph",
        "labels": {"en": "semantic graph"},
        "relations": [{"relation": "contrasts_with", "target": "surface_graph"}],
    }
    context_map = {"surface_graph": {"concept_id": "surface_graph", "labels": {"en": "surface graph"}}}
    sentence = _english_relation_sentence(primary, context_map)
    assert "contrasts with a surface graph" in sentence


def test_second_hop_chains_a_verified_fact() -> None:
    # M2: A→B→C reasoning, stating only relations that exist in the graph.
    primary = {
        "concept_id": "graphrag",
        "labels": {"en": "GraphRAG"},
        "relations": [{"relation": "requires", "target": "semantic_graph"}],
    }
    context_map = {
        "semantic_graph": {
            "concept_id": "semantic_graph",
            "labels": {"en": "semantic graph"},
            "relations": [{"relation": "contrasts_with", "target": "surface_graph"}],
        },
        "surface_graph": {"concept_id": "surface_graph", "labels": {"en": "surface graph"}},
    }
    hop = _english_second_hop(primary, context_map)
    assert hop == "A semantic graph, in turn, contrasts with a surface graph."


def test_second_hop_does_not_loop_back_to_primary() -> None:
    primary = {
        "concept_id": "a",
        "labels": {"en": "A"},
        "relations": [{"relation": "requires", "target": "b"}],
    }
    context_map = {
        "b": {"concept_id": "b", "labels": {"en": "B"}, "relations": [{"relation": "requires", "target": "a"}]},
    }
    assert _english_second_hop(primary, context_map) == ""  # b→a loops back, skip


def test_second_hop_needs_relevant_intermediate() -> None:
    # If the intermediate concept was not retrieved (not in context_map), no hop.
    primary = {
        "concept_id": "graphrag",
        "labels": {"en": "GraphRAG"},
        "relations": [{"relation": "requires", "target": "semantic_graph"}],
    }
    assert _english_second_hop(primary, {}) == ""


def test_real_query_includes_second_hop_reasoning(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    answer = answer_with_base_brain("What is GraphRAG?", language="en", audience_level="beginner")["answer"]
    assert "in turn" in answer  # multi-hop reasoning surfaced


def test_precision_gate_abstains_on_loose_false_match(tmp_path, monkeypatch) -> None:
    # The pack has no concept for these; a loose match must abstain instead of confidently
    # describing the wrong concept. ('Bitcoin' was here but is now correctly answered from the
    # grounded Kaikki primary-gloss sidecar; 'capital of France' was here but is now correctly
    # answered from an ingested Wikidata `capital` edge — so the relational abstention example is a
    # fictional entity the graph holds no capital edge for, and the define example a coinage.)
    monkeypatch.chdir(tmp_path)
    for query in ["What is the capital of Wakanda?", "What is Zylophthegorn?"]:
        result = answer_with_base_brain(query, language="en", audience_level="beginner")
        assert result["confidence"] <= 0.2, f"{query!r} should abstain, got {result['answer']!r}"


def test_reasoning_certificate_traces_the_derivation(tmp_path, monkeypatch) -> None:
    # Every claim must be traceable to the ontology concept + graph edges it came
    # from (the "reasoning certificate"): no opaque generation.
    monkeypatch.chdir(tmp_path)
    cert = answer_with_base_brain("What is GraphRAG?", language="en", audience_level="beginner")[
        "reasoning_certificate"
    ]
    assert cert["derivation_kind"] == "ontology_graph_derivation"
    assert cert["anchor_concept"]["id"] == "graphrag"
    assert cert["anchor_concept"]["match"] == "named_in_query"
    assert cert["steps"][0]["type"] == "anchor_definition"
    edges = [s["edge"] for s in cert["steps"] if s["type"].startswith("graph_relation")]
    assert "graphrag --requires--> semantic_graph" in edges
    assert cert["guarantees"]["external_llm"] is False
    assert cert["guarantees"]["fabricated_facts"] is False
    assert cert["guarantees"]["ontology_traceable"] is True


def test_reasoning_certificate_abstains_cleanly(tmp_path, monkeypatch) -> None:
    # Owner directive 2026-07-09: no cold forfeit — an unanswerable knowledge question
    # now engages (hedged inference) instead of abstaining. The certificate must still be
    # CLEAN: honestly labeled (abstained OR engaged_fact_inference), never a confident
    # single-concept derivation with a fabricated anchor.
    result = answer_with_base_brain("What is Bitcoin?", language="en", audience_level="beginner")
    cert = result["reasoning_certificate"]
    assert cert["derivation_kind"] in ("abstained", "engaged_fact_inference")
    assert result["confidence"] <= 0.2


def test_atanor_product_concepts_are_answered(tmp_path, monkeypatch) -> None:
    # ATANOR's own sidebar features must be answerable from the graph.
    monkeypatch.chdir(tmp_path)
    for query, needle in [("What is Graph Hub?", "cartridge"), ("What is Atlas?", "relay")]:
        result = answer_with_base_brain(query, language="en", audience_level="beginner")
        assert needle in result["answer"].lower(), result["answer"]
        assert result["confidence"] >= 0.5


def test_undocumented_feature_still_abstains(tmp_path, monkeypatch) -> None:
    # AGORA has no documented definition — never fabricate one.
    monkeypatch.chdir(tmp_path)
    result = answer_with_base_brain("What is AGORA?", language="en", audience_level="beginner")
    assert result["confidence"] <= 0.2


def test_identity_question_answers_as_atanor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for query, lang in [("Who are you?", "en"), ("너는 누구야?", "ko")]:
        result = answer_with_base_brain(query, language=lang, audience_level="beginner")
        assert "ATANOR" in result["answer"]


def test_precision_gate_keeps_directly_named_concept(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for query in ["What is GraphRAG?", "How does a CPU work?"]:
        result = answer_with_base_brain(query, language="en", audience_level="beginner")
        assert result["confidence"] >= 0.5
        assert "enough" not in result["answer"].lower()  # not the abstain message


def test_korean_named_concept_is_confident(tmp_path, monkeypatch) -> None:

    # still recognise it, so confidence is high (was wrongly 0.45 before).
    monkeypatch.chdir(tmp_path)
    result = answer_with_base_brain("양자컴퓨터가 뭐야?", language="ko", audience_level="beginner")
    assert result["confidence"] >= 0.5


def test_confidence_is_honest_not_a_constant(tmp_path, monkeypatch) -> None:
    # M5: confidence reflects grounding strength.
    monkeypatch.chdir(tmp_path)
    grounded = answer_with_base_brain("What is GraphRAG?", language="en", audience_level="beginner")
    ungrounded = answer_with_base_brain(
        "What is the weather today?", language="en", audience_level="beginner"
    )
    assert grounded["confidence"] > 0.5, "a directly named concept should be confident"
    assert ungrounded["confidence"] < 0.3, "an ungrounded / real-time answer should be low confidence"
    assert grounded["confidence"] != ungrounded["confidence"]  # not a fixed constant


def test_noun_phrase_determiner_rules() -> None:
    assert _en_noun_phrase("semantic graph", with_article=True) == "a semantic graph"
    assert _en_noun_phrase("ontology", with_article=True) == "an ontology"
    assert _en_noun_phrase("privacy", with_article=True) == "privacy"  # uncountable
    assert _en_noun_phrase("GraphRAG", with_article=True) == "GraphRAG"  # proper noun
    assert _en_noun_phrase("semantic graph", with_article=False) == "semantic graph"


@pytest.mark.parametrize(
    "query",
    [
        "What is GraphRAG?",
        "What is a semantic graph?",
        "What is an ontology graph?",
        "What is Kubernetes?",
        "Why does evidence matter for reducing hallucination?",
    ],
)
def test_general_english_answers_are_graph_derived_not_hand_authored(query, tmp_path, monkeypatch) -> None:
    # M3: general questions must be realized from the graph, not pulled from a
    # hand-authored canned-answer table. This is what makes ATANOR "not rule-based".
    monkeypatch.chdir(tmp_path)
    result = answer_with_base_brain(query, language="en", audience_level="beginner")
    assert result["hand_authored_answer_used"] is False, f"{query!r} used a canned answer"
    assert str(result["answer"]).strip(), f"{query!r} produced an empty answer"


def test_english_label_never_returns_hangul() -> None:
    concept = {
        "concept_id": "local_brain",
        "canonical_name": "Local Brain",
        "labels": {"ko": "저장된 개인 맥락", "en": "Local Brain"},
    }
    assert _label(concept, "en") == "Local Brain"

    # Even when the English label is missing/corrupted, EN mode must stay ASCII.
    broken = {"concept_id": "local_brain", "canonical_name": "저장된 개인 맥락", "labels": {"ko": "저장된 개인 맥락"}}
    resolved = _label(broken, "en")
    assert not _HANGUL.search(resolved), f"label leaked Hangul: {resolved!r}"
    assert resolved == "local brain"


@pytest.mark.parametrize("query,needle", [
    ("What is machine learning?", "pattern"),
    ("What is a neural network?", "layer"),
    ("What is HTTP?", "protocol"),
    ("What is encryption?", "data"),
])
def test_expanded_seed_concepts_answer_in_english(query, needle, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = answer_with_base_brain(query, language="en", audience_level="beginner")
    assert result["confidence"] >= 0.5, f"{query!r} should be confident, got {result['answer']!r}"
    assert needle in result["answer"].lower()
    assert not _HANGUL.search(result["answer"])  # no Korean leak


def test_expanded_seed_concepts_answer_in_clean_korean(tmp_path, monkeypatch) -> None:
    import re as _re
    monkeypatch.chdir(tmp_path)
    for query in ("리눅스 설명해줘", "암호화가 뭐야", "파이썬이 뭐야"):
        answer = answer_with_base_brain(query, language="ko", audience_level="beginner")["answer"]
        # the Korean answer must not fall back to the English short_description
        assert not _re.search(r"[A-Za-z]{4,}", answer), f"English leaked into KO answer: {answer!r}"
