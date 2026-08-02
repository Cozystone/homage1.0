from __future__ import annotations

from cgsr.morphology import analyze, analyzer_status, has_final_consonant


def test_kiwi_wrapper_returns_morphemes() -> None:
    rows = analyze("쉽게 말하면 쿠버네티스는 컨테이너를 관리합니다.")

    assert rows
    assert all(row.form for row in rows)
    assert all(row.tag for row in rows)
    assert analyzer_status()["usage"] == "morphology_only"


def test_has_final_consonant() -> None:
    assert has_final_consonant("책") is True
    assert has_final_consonant("나무") is False
