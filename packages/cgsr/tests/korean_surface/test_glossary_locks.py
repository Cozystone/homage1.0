from __future__ import annotations

from cgsr.korean_surface.glossary import apply_glossary_locks, glossary_violations


def test_glossary_locks_preserve_atanor_terms() -> None:
    text = apply_glossary_locks("Local Brain and Cloud Brain use RHFC and CGSR.")
    assert "로컬 브레인" in text
    assert "클라우드 브레인" in text
    assert "RHFC" in text
    assert "CGSR" in text


def test_glossary_violation_detects_unlocked_source_term() -> None:
    assert "Local Brain" in glossary_violations("Local Brain은 저장소입니다.")
