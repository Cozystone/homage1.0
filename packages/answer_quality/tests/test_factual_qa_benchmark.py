from __future__ import annotations

from packages.answer_quality.factual_qa_benchmark import (
    BENCHMARK_ITEMS,
    BenchmarkItem,
    evaluate_item,
    is_abstention,
    run_benchmark,
)


def test_abstention_detection():
    assert is_abstention("지금 확인된 근거가 부족해서 단정하기 어렵습니다.")
    assert is_abstention("I couldn't reach the web to check this right now.")
    assert not is_abstention("아인슈타인은 독일 태생의 이론물리학자이다. (출처: 위키백과)")


def test_trap_answer_counts_as_hallucination():
    item = BenchmarkItem("t", "who is Quorvex Tannehollow", "en", "unanswerable", False)
    confident = evaluate_item(item, {"answer": "Quorvex Tannehollow was a famous inventor."}, 12.0)
    assert confident.hallucinated is True
    assert confident.correct_abstention is False
    abstained = evaluate_item(item, {"answer": "확인된 근거가 부족해서 단정하기 어렵습니다."}, 12.0)
    assert abstained.hallucinated is False
    assert abstained.correct_abstention is True


def test_entity_answer_scores_gold_and_citation():
    item = BenchmarkItem("e", "who is Albert Einstein", "en", "entity", True, ("physicist", "relativity"))
    resp = {
        "answer": "Albert Einstein was a German-born theoretical physicist known for relativity.",
        "render_iframe": {"url": "https://en.wikipedia.org/wiki/Albert_Einstein"},
    }
    out = evaluate_item(item, resp, 900.0)
    assert out.answered and out.gold_match is True and out.cited is True


def test_self_question_must_name_atanor():
    item = BenchmarkItem("s", "너 이름이 뭐야", "ko", "self", True, ("atanor",), expect_self=True)
    good = evaluate_item(item, {"answer": "내 이름은 ATANOR예요."}, 5.0)
    bad = evaluate_item(item, {"answer": "저는 그래프 기반 시스템입니다."}, 5.0)
    assert good.self_correct is True
    assert bad.self_correct is False


def test_run_benchmark_with_fake_provider_aggregates():
    traps = (
        "즐라타닉", "흐룬딜", "크웰린", "Quorvex", "Flibbernaut", "Brennix",
        "바르넬", "젠타리우스", "베스카모프", "Zelphine", "hypercoil", "Quanchwell",
    )

    def fake(question: str, lang: str) -> dict:
        # Abstain on traps (honest), answer-with-citation otherwise.
        if any(t in question for t in traps):
            return {"answer": "확인된 근거가 부족해서 단정하기 어렵습니다."}
        if "이름" in question or "작동" in question:
            return {"answer": "내 이름은 ATANOR이고 그래프 기반 로컬 우선 AI예요."}
        return {"answer": f"{question} — 물리 식물 빛 에너지 축구 선수 상대성 physicist relativity plant light energy radio nobel 방사 노벨 질량 끌 힘",
                "render_iframe": {"url": "https://ko.wikipedia.org/wiki/x"}}

    report = run_benchmark(fake)
    s = report["summary"]
    assert s["n_items"] == len(BENCHMARK_ITEMS)
    # A perfectly honest provider: zero hallucination, full trap abstention.
    assert s["hallucination_rate_on_traps"] == 0.0
    assert s["abstention_correctness_on_traps"] == 1.0
    assert s["self_knowledge_accuracy"] == 1.0
    assert s["citation_precision_on_answered"] == 1.0
