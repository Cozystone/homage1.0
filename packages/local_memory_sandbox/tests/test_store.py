from __future__ import annotations

import pytest

from packages.local_memory_sandbox.store import compute_store_hash, init_sandbox_store, list_collections, read_collection, write_collection


def test_init_sandbox_store_creates_collections(tmp_path) -> None:
    root = init_sandbox_store(tmp_path / "sandbox")

    assert (root / "preferences.json").exists()
    assert "project_context" in list_collections(root)
    assert read_collection(root, "preferences") == []
    assert compute_store_hash(root)


def test_write_collection_changes_hash(tmp_path) -> None:
    root = init_sandbox_store(tmp_path / "sandbox")
    before = compute_store_hash(root)
    write_collection(root, "preferences", {"normalized_summary": "prefers concise answers", "sensitivity": "personal"})
    after = compute_store_hash(root)

    assert before != after
    assert len(read_collection(root, "preferences")) == 1


def test_rejects_raw_sensitive_and_voice(tmp_path) -> None:
    root = init_sandbox_store(tmp_path / "sandbox")

    with pytest.raises(ValueError, match="raw sensitive"):
        write_collection(root, "sensitive_hold", {"normalized_summary": "private", "sensitivity": "sensitive", "raw_text": "secret"})
    with pytest.raises(ValueError, match="raw voice"):
        write_collection(root, "preferences", {"normalized_summary": "Voice transcript: raw", "source_type": "voice_transcript"})


def test_rejects_real_local_brain_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="non-sandbox"):
        init_sandbox_store("data/memory")
