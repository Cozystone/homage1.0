"""Korean realizer golden tests (Korean phase / Korean M1).

Locks the fix for the double-particle bug (" ") and subject
repetition. Each relation carries its own connecting particle, applied to the
bare label with the correct allomorph (/, /) by final consonant.
"""

from __future__ import annotations

import re

from packages.base_brain.zero_user_answer import (
    _korean_relation_sentence,
    _ko_relation_clause,
    answer_with_base_brain,
)


_DOUBLE_PARTICLE = re.compile(r"[을를](\s+)[을를에의]\b")


def test_object_particle_agrees_with_final_consonant() -> None:
    assert _ko_relation_clause("requires", "의미 그래프") == "의미 그래프를 필요로 합니다"  # vowel
    assert _ko_relation_clause("uses", "표면 그래프합") == "표면 그래프합을 사용합니다"  # consonant


def test_relation_particles_by_kind() -> None:
    assert _ko_relation_clause("is_a", "시스템") == "시스템의 한 종류입니다"  # genitive
    assert _ko_relation_clause("used_for", "환각 감소") == "환각 감소에 쓰입니다"  # locative
    assert _ko_relation_clause("contrasts_with", "표면 그래프") == "표면 그래프와 대비됩니다"  # comitative


def test_no_double_particle_in_real_answer(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for query in ["GraphRAG가 뭐야?", "쿠버네티스가 뭐야?", "ATANOR가 뭔가요?"]:
        answer = answer_with_base_brain(query, language="ko", audience_level="beginner")["answer"]
        assert not _DOUBLE_PARTICLE.search(answer), f"double particle in {query!r}: {answer!r}"


def test_relation_sentence_aggregates_without_subject_repetition() -> None:
    primary = {
        "concept_id": "graphrag",
        "labels": {"ko": "GraphRAG"},
        "relations": [
            {"relation": "requires", "target": "semantic_graph"},
            {"relation": "used_for", "target": "hallucination_reduction"},
        ],
    }
    context_map = {
        "semantic_graph": {"concept_id": "semantic_graph", "labels": {"ko": "의미 그래프"}},
        "hallucination_reduction": {"concept_id": "hallucination_reduction", "labels": {"ko": "환각 감소"}},
    }
    sentence = _korean_relation_sentence(primary, context_map)
    assert sentence == "이는 의미 그래프를 필요로 합니다. 또한 환각 감소에 쓰입니다."
    assert "GraphRAG" not in sentence  # subject not repeated
