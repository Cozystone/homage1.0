from __future__ import annotations

import unicodedata

from cgsr.ingestion.korean_text_quality import (
    detect_mojibake,
    hangul_ratio,
    normalize_korean_text,
    quarantine_reason,
    validate_korean_sentence,
)


def test_clean_korean_sentence_passes() -> None:
    result = validate_korean_sentence("쿠버네티스는 컨테이너를 관리한다.")
    assert result.is_valid
    assert result.hangul_ratio > 0.9


def test_replacement_character_is_quarantined() -> None:
    result = validate_korean_sentence("쿠버네티스는 �를 관리한다.")
    assert not result.is_valid
    assert any(issue.startswith("mojibake_fragment") for issue in result.issues)


def test_common_mojibake_fragments_fail() -> None:
    result = validate_korean_sentence("ì¿ í…Œì´ë„ˆë¥¼ ê´€ë¦¬í•œë‹¤", expect_korean=False)
    assert not result.is_valid
    assert quarantine_reason("ì¿ í…Œì´ë„ˆë¥¼ ê´€ë¦¬í•œë‹¤", expect_korean=False)


def test_mixed_latin_technical_korean_can_pass() -> None:
    result = validate_korean_sentence("GraphRAG는 근거 문서를 검증한다.", expect_korean=False)
    assert result.is_valid


def test_empty_or_low_hangul_expected_korean_fails() -> None:
    assert "empty_text" in validate_korean_sentence("").issues
    assert "low_hangul_ratio" in validate_korean_sentence("GraphRAG validates documents.").issues


def test_nfc_normalization() -> None:
    decomposed = unicodedata.normalize("NFD", "한글")
    assert normalize_korean_text(decomposed) == "한글"


def test_raw_unicode_escape_detected() -> None:
    issues = detect_mojibake(r"\ucfe0\ubc84\ub124\ud2f0\uc2a4")
    assert "raw_unicode_escape" in issues
