from __future__ import annotations

from packages.answer_quality.evaluators import evaluate_answer_quality, evaluate_template_smell, evaluate_trace_hygiene


def test_trace_leakage_detected_in_default_mode_and_allowed_in_research() -> None:
    answer = "Local Brain → Cloud Brain → Working Memory 경로를 사용합니다."

    default_score, flags, _ = evaluate_trace_hygiene(answer, "default")
    research_score, research_flags, _ = evaluate_trace_hygiene(answer, "research")

    assert default_score < 0.2
    assert "trace_leakage" in flags
    assert research_score == 1.0
    assert research_flags == []


def test_repeated_construction_is_penalized() -> None:
    score, flags, _ = evaluate_template_smell(
        "쉽게 말하면 네 번째 답입니다.",
        ["쉽게 말하면 첫 답입니다.", "쉽게 말하면 두 번째 답입니다.", "쉽게 말하면 세 번째 답입니다."],
    )

    assert score < 0.7
    assert "template_opening_overused" in flags


def test_language_and_grounding_scores_are_bounded() -> None:
    score = evaluate_answer_quality(
        candidate_id="c1",
        answer="GraphRAG는 근거 문서를 그래프 경로로 찾아 답변을 검증합니다.",
        query="GraphRAG가 근거를 어떻게 써?",
        language="ko",
        semantic_context=[{"concept": "GraphRAG", "claims": ["retrieves evidence"]}],
    )

    for key in ("naturalness", "grounding", "overall", "language_native"):
        assert 0.0 <= score[key] <= 1.0
    assert "not perfect factuality" in " ".join(score["notes"]).lower()


def test_mojibake_is_penalized() -> None:
    score = evaluate_answer_quality(
        candidate_id="bad",
        answer="荑좊쾭?ㅽ떚?? 吏?앹쓣 援ъ“?⑸땲??",
        query="쿠버네티스가 뭐야?",
        language="ko",
        semantic_context=[{"concept": "Kubernetes"}],
    )

    assert score["naturalness"] < 0.65
    assert "encoding_artifact" in score["flags"]
