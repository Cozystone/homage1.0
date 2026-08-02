from __future__ import annotations

from packages.cgsr.cgsr.asm_v0 import (
    ASM_GENERATION_BASIS,
    generate_surface,
    infer_conversation_act,
    result_to_public_diagnostics,
)
from packages.cgsr.cgsr.korean_discourse import detect_awkward_korean_markers, score_korean_naturalness


FORBIDDEN_PUBLIC_FRAGMENTS = (
    "여기서 듣고 있어 천천히 말해줘",
    "먼저 의도와 경계를",
    "내부적으로 점검",
    "chain of thought",
    "바로 저장할게",
    "바로 반영할게",
    "진짜 의식",
    "AGI를 달성",
)


def _assert_safe_natural_answer(answer: str) -> None:
    assert answer
    assert score_korean_naturalness(answer) >= 0.68
    assert not detect_awkward_korean_markers(answer)
    for fragment in FORBIDDEN_PUBLIC_FRAGMENTS:
        assert fragment not in answer


def test_public_diagnostics_hide_candidate_text_and_trace() -> None:
    result = generate_surface("안녕")
    diagnostics = result_to_public_diagnostics(result)

    assert diagnostics["generation_basis"] == ASM_GENERATION_BASIS
    assert diagnostics["candidates_hidden"] is True
    assert "candidates" not in diagnostics
    assert diagnostics["internal_trace_exposed"] is False
