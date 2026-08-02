"""Identity questions (" ?") must be answered from the GRAPH, not from a
curated self-model answer table. The old `atanor_self_knowledge` module (a regex
that picked rows from a hand-authored fact list) was removed: it was rule-based,
which contradicts ATANOR's "no canned answers" philosophy. Identity is now realized
from the "atanor" concept and its relations, exactly like any other concept.
"""
from __future__ import annotations

from packages.base_brain.zero_user_answer import _is_identity_question, answer_with_base_brain


def test_identity_questions_are_graph_derived_not_canned():
    for q in ["너는 누구야?", "넌 누구야", "너 누구니", "ATANOR가 뭐야", "자기소개", "who are you?", "what are you?"]:
        assert _is_identity_question(q) or "atanor" in q.lower(), q
        lang = "ko" if any("가" <= c <= "힣" for c in q) else "en"
        result = answer_with_base_brain(q, lang)
        answer = str(result.get("answer") or "")
        assert "ATANOR" in answer, q
        # The honesty flag must prove this was realized from the graph, not a
        # hand-authored canned string.
        assert result.get("hand_authored_answer_used") is False, q


def test_attribution_and_factual_are_not_identity():
    # these must NOT be treated as self/identity questions (they go to attribution / web)
    for q in ["엔비디아 창립자가 누구야?", "전화기를 발명한 사람은 누구야?", "광합성이 뭐야?", "모나리자를 그린 사람은 누구야?"]:
        assert not _is_identity_question(q), q
