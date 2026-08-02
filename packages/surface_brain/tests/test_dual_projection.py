from __future__ import annotations

from packages.surface_brain.dual_projection import ingest_source_sentence_dual_projection
from packages.surface_brain.models import SourceSentence


def test_same_source_creates_semantic_and_surface_projection(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = SourceSentence.from_text("쉽게 말하면, 쿠버네티스는 많은 컨테이너를 자동으로 배치하고 관리하는 운영 관리자에 가깝습니다.")

    result = ingest_source_sentence_dual_projection(source)

    assert result["semantic_projection"]["source_hash"] == source.source_hash
    assert result["surface_projection"]["source_hash"] == source.source_hash
    assert result["linked_source_hash"] == source.source_hash
    assert result["stored_raw_text"] is False
    assert result["privacy"]["private_user_data_uploaded"] is False

