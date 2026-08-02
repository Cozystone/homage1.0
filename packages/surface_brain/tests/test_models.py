from __future__ import annotations

from packages.surface_brain.models import SourceSentence, detect_language, hash_text


def test_source_sentence_hash_and_language_are_stable() -> None:
    text = "쉽게 말하면, 쿠버네티스는 컨테이너를 관리합니다."
    source = SourceSentence.from_text(text, source_id="s1")

    assert source.source_hash == hash_text(text)
    assert source.language == "ko"
    assert detect_language("Kubernetes manages containers.") == "en"
    assert source.raw_text_stored is False
    assert source.raw_text_policy == "hash_only"

