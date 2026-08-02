"""Unified reasoning→utterance orchestrator: one pipeline routes to the right grounded mechanism."""
from __future__ import annotations

import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.services.answer_orchestrator import answer

CORPUS = [
    "엔비디아 코퍼레이션은 미국의 반도체 기업이다.",
    "엔비디아 드라이브는 자율주행 플랫폼이다.",
    "전화는 통신 기기이다.", "카메라는 촬영 기기이다.",
    "스마트폰은 통신 기기이다.", "드론은 촬영 기기이다.",
]


def test_arithmetic_routes_to_deterministic_reasoning():
    r = answer("3 더하기 5는?")
    assert r.kind == "deterministic_reasoning" and "8" in r.answer


def test_transitive_routes_to_deterministic_reasoning():
    r = answer("철수는 영희보다 크고 영희는 민수보다 크다. 가장 큰 사람은?")
    assert r.kind == "deterministic_reasoning" and "철수" in r.answer


def test_entity_routes_to_multisource_synthesis():
    r = answer("엔비디아가 뭐야?", corpus=CORPUS)
    assert r.kind == "multisource_synthesis"
    assert "반도체 기업" in r.answer and "자율주행 플랫폼" in r.answer  # comprehensive, 2 sources
    assert len(r.grounding) == 2


def test_creative_intent_routes_to_creative_engine():
    r = answer("기기에 대한 새로운 개념을 발명해줘", corpus=CORPUS)
    assert r.kind == "creative"
    assert "파괴된 전제" in r.answer and r.grounding  # grounded creativity with XAI


def test_unknown_query_never_dead_abstains_and_never_fabricates():
    # No dead "I don't know": route to a helpful redirect, but still fabricate nothing.
    r = answer("외계인이 어제 뭐 먹었어?", corpus=CORPUS)
    assert r.kind == "needs_more"          # not "abstain" — asks for more, doesn't give up
    assert r.answer and "모른" not in r.answer  # no dead abstention wording
    assert r.guarantees["fabricated_facts"] is False


def test_partial_grounding_when_entity_is_mentioned_but_undefined():
    # Entity appears in corpus but no clean definition → surface the real related sentence, hedged.
    corpus = ["엔비디아는 젠슨 황이 이끈다."]
    r = answer("엔비디아 창업 연도는?", corpus=corpus)
    assert r.kind in {"partial_grounded", "multisource_synthesis"}
    assert r.grounding and r.guarantees["fabricated_facts"] is False


def test_every_result_declares_no_llm():
    for q in ["3 더하기 5는?", "엔비디아가 뭐야?", "외계인이 뭐 먹었어?"]:
        assert answer(q, corpus=CORPUS).guarantees["external_llm"] is False
