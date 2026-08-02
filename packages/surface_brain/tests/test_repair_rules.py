from __future__ import annotations

from packages.surface_brain.monitor import repair_answer_for_mode
from packages.surface_brain.repair_rules import builtin_repair_rules, sentence_chunks


def test_default_mode_removes_internal_terms_and_preserves_meaning(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = repair_answer_for_mode(
        "Cloud Brain 문맥을 붙이면 쿠버네티스는 컨테이너를 관리하는 시스템이라고 설명할 수 있습니다.",
        mode="default",
        trace={},
    )

    assert "Cloud Brain" not in result["repaired_answer"]
    assert "붙이면" not in result["repaired_answer"]
    assert "쿠버네티스" in result["repaired_answer"]
    assert "컨테이너" in result["repaired_answer"]
    assert result["changed"] is True
    assert result["moved_to_trace"]


def test_trace_mode_allows_internal_details() -> None:
    text = "Cloud Brain -> Working Memory path is visible in trace mode."
    result = repair_answer_for_mode(text, mode="trace", trace={})

    assert result["repaired_answer"] == text
    assert result["changed"] is False


def test_builtin_rules_include_required_leakage_guards() -> None:
    names = {rule.name for rule in builtin_repair_rules()}

    assert "replace_cloud_brain_user_facing" in names
    assert "replace_local_brain_user_facing" in names
    assert "remove_q_cortex_leakage" in names
    assert "remove_source_hash_leakage" in names


def test_sentence_chunks_do_not_split_inside_korean_words_ending_with_ni() -> None:
    text = "그 설명은 의미 단위로 보니.다음 문장은 여기입니다."

    assert sentence_chunks(text) == ["그 설명은 의미 단위로 보니.다음 문장은 여기입니다."]
