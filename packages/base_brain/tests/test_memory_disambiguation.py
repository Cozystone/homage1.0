from __future__ import annotations

from packages.base_brain.zero_user_answer import answer_with_base_brain


def test_atanor_local_memory_context_does_not_match_ram(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = answer_with_base_brain("내 로컬 메모리 구조 설명", language="ko")

    assert "RAM" not in result["answer"]
    assert "SSD" not in result["answer"]
    assert all(item["concept_id"] != "ram" for item in result["trace"]["matched_concepts"])


def test_computer_memory_question_still_matches_ram(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = answer_with_base_brain("RAM은 뭐야?", language="ko")

    assert any(item["concept_id"] == "ram" for item in result["trace"]["matched_concepts"])
    assert "RAM" in result["answer"]
    assert "를 와" not in result["answer"]


def test_computer_memory_storage_comparison_still_works(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = answer_with_base_brain("컴퓨터 메모리와 SSD 차이", language="ko")

    matched = {item["concept_id"] for item in result["trace"]["matched_concepts"]}
    assert "ram" in matched
    assert "ssd" in matched
    assert "를 와" not in result["answer"]
