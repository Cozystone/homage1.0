from __future__ import annotations

from cgsr.english.canonical_frames import RealizedAnswer
from cgsr.korean_surface.consistency_gate import check_korean_surface
from cgsr.korean_surface.translate_surface import KoreanSurfaceResult, realize_korean_surface


def _answer(text: str = "ATANOR preserves 42 evidence refs in Cloud Brain.") -> RealizedAnswer:
    return RealizedAnswer(
        language="en",
        text=text,
        used_frames=["en_summary_v1"],
        filled_slots={"summary": text},
        evidence_refs=["ev:42"],
        unsupported_claims=[],
        entity_locks=["ATANOR", "Cloud Brain"],
        number_locks=["42"],
        trace_hidden=True,
    )


def test_korean_surface_preserves_numbers_and_glossary() -> None:
    answer = _answer()
    surface = check_korean_surface(answer, realize_korean_surface(answer))
    assert surface.safe_to_show
    assert surface.number_violations == []
    assert surface.glossary_violations == []
    assert surface.evidence_preserved
    assert not surface.external_api_used


def test_korean_surface_rejects_number_drift() -> None:
    answer = _answer()
    bad = KoreanSurfaceResult(
        source_language="en",
        target_language="ko",
        korean_text="ATANOR는 클라우드 브레인에서 43 근거를 보존합니다. ev:42",
        glossary_violations=[],
        number_violations=[],
        entity_violations=[],
        evidence_preserved=True,
        safe_to_show=True,
    )
    checked = check_korean_surface(answer, bad)
    assert not checked.safe_to_show
    assert "extra_number:43" in checked.number_violations


def test_korean_surface_rejects_mojibake() -> None:
    answer = _answer("ATANOR preserves 42.")
    bad = KoreanSurfaceResult(
        source_language="en",
        target_language="ko",
        korean_text="ATANOR는 �를 보존합니다. 42",
        glossary_violations=[],
        number_violations=[],
        entity_violations=[],
        evidence_preserved=True,
        safe_to_show=True,
    )
    assert not check_korean_surface(answer, bad).safe_to_show
