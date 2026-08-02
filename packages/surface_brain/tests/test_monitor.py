from __future__ import annotations

from packages.surface_brain.monitor import monitor_answer, repair_answer


def test_monitor_catches_repetition_and_internal_trace_leakage() -> None:
    draft = "Local Brain → Cloud Brain → Contributor Node path. answer answer repeats repeats."
    monitor = monitor_answer(draft, language="en")

    assert "internal_trace_leakage" in monitor["issues"]
    repaired = repair_answer(draft, monitor, language="en")
    repaired_monitor = monitor_answer(repaired, language="en")

    assert repaired_monitor["needs_repair"] is False
    assert "Local Brain" not in repaired
    assert "Cloud Brain" not in repaired


def test_monitor_catches_encoding_and_internal_identifier_artifacts() -> None:
    draft = "GraphRAG 筌띯뫔 evidence 87eba76e7f3164534045ba922e7770fb58bbd14ad732bbf5ba6f11cc56989e6e 기준입니다."
    monitor = monitor_answer(draft, language="ko")

    assert "encoding_artifact" in monitor["issues"]
    assert "internal_identifier_leakage" in monitor["issues"]


def test_monitor_catches_attach_style_korean_wording() -> None:
    monitor = monitor_answer("Cloud Brain 문맥을 붙여 답하면 쿠버네티스는 컨테이너를 관리합니다.", language="ko")

    assert "implementation_wording" in monitor["issues"]
