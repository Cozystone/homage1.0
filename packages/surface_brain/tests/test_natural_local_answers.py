from __future__ import annotations

from packages.surface_brain.realization_planner import plan_speech, realize_answer


def test_unknown_person_does_not_surface_ghost_hashes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = {
        "concepts": ["ghost:0294732d9ab7", "ghost:02e39a5dbcb6"],
        "relations": [],
        "evidence_docs": [],
        "confidence": 0.2,
    }

    plan = plan_speech("유재석이 누구야", context, language="ko")
    answer = realize_answer(plan, context, query="유재석이 누구야")

    assert "ghost:" not in answer["answer"]
    assert "핵심 개념" not in answer["answer"]
    assert answer["answer"] == "모르겠어. 지금 로컬에는 유재석을 설명할 근거가 없어."
    assert answer["confidence"] == 0.12
    assert answer["external_llm_used"] is False
    assert answer["external_sllm_used"] is False


def test_korean_query_overrides_english_ui_language(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = {
        "concepts": ["ghost:0294732d9ab7"],
        "relations": [],
        "evidence_docs": [],
        "confidence": 0.2,
    }

    plan = plan_speech("유재석이 누구야", context, language="en")
    answer = realize_answer(plan, context, query="유재석이 누구야")

    assert plan["language"] == "ko"
    assert "The current local context" not in answer["answer"]
    assert "유재석" in answer["answer"]
    assert "관련 문서나 메모리" not in answer["answer"]
    assert answer["answer"].startswith("모르겠어.")


def test_recent_learning_hides_internal_hash_inventory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = {
        "concepts": ["ghost:30c981718b37", "ghost:157ee802e367"],
        "relations": [],
        "evidence_docs": [],
        "confidence": 0.2,
    }

    plan = plan_speech("최근 학습한 개념 보여줘", context, language="ko")
    answer = realize_answer(plan, context, query="최근 학습한 개념 보여줘")

    assert "ghost:" not in answer["answer"]
    assert "핵심 개념" not in answer["answer"]
    assert "내부 해시" in answer["answer"]
    assert "원문이나 라벨이 연결되면" not in answer["answer"]
    assert answer["external_llm_used"] is False
    assert answer["external_sllm_used"] is False
