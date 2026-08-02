from __future__ import annotations

from packages.surface_brain.extraction import extract_surface_projection
from packages.surface_brain.models import SourceSentence


def test_korean_simplification_marker_detected() -> None:
    source = SourceSentence.from_text("쉽게 말하면, 쿠버네티스는 운영 관리자에 가깝습니다.")
    projection = extract_surface_projection(source)

    assert "simplification" in projection["discourse_moves"]
    assert "쉽게 말하면" in projection["phrase_patterns"]
    assert projection["language"] == "ko"


def test_english_discourse_marker_detected() -> None:
    source = SourceSentence.from_text("In simple terms, Kubernetes manages containers. However, it is not an app runtime.")
    projection = extract_surface_projection(source)

    assert "simplification" in projection["discourse_moves"]
    assert "caveat" in projection["discourse_moves"]
    assert "in simple terms" in projection["phrase_patterns"]
