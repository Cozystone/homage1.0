"""Storage root resolution (external-drive aware) + retriever web-shape bridge. No network, no LLM."""
from __future__ import annotations

import numpy as np

from packages.atanor_index import storage
from packages.atanor_index.disk_index import build_index


def test_index_root_env_override(tmp_path, monkeypatch):
    target = tmp_path / "custom_root"
    monkeypatch.setenv("ATANOR_INDEX_ROOT", str(target))
    storage._CACHE.clear()
    root = storage.index_root(refresh=True)
    assert root == target and root.exists()


def test_index_root_fallback_is_repo_data(tmp_path, monkeypatch):
    monkeypatch.delenv("ATANOR_INDEX_ROOT", raising=False)
    storage._CACHE.clear()
    # Force "no external drive" so it must fall back to the repo data dir.
    monkeypatch.setattr(storage, "external_drive", lambda: None)
    root = storage.index_root(refresh=True)
    assert root.name == "atanor_index" and root.parent.name == "data"


def test_storage_report_shape(monkeypatch):
    monkeypatch.delenv("ATANOR_INDEX_ROOT", raising=False)
    storage._CACHE.clear()
    rep = storage.storage_report()
    assert {"index_root", "on_external", "external_drive", "volumes"} <= set(rep)
    assert isinstance(rep["volumes"], list)


def test_retriever_emits_web_shape(tmp_path, monkeypatch):
    src = tmp_path / "passages.tsv"
    src.write_text("Photosynthesis\tPhotosynthesis is how plants convert light into chemical energy.\n"
                   "Mitochondrion\tThe mitochondrion is the powerhouse of the cell.\n", encoding="utf-8")
    idx_dir = tmp_path / "idx"
    build_index(src, idx_dir, progress_every=0)

    from packages.atanor_index import retriever
    monkeypatch.setenv("ATANOR_INDEX_DIR", str(idx_dir))
    monkeypatch.delenv("ATANOR_DISABLE_LOCAL_INDEX", raising=False)
    retriever._STATE.update({"idx": None, "tried_dir": None})   # drop any cached singleton

    rows = retriever.local_search("what is photosynthesis", count=2)
    assert rows, "expected a local hit"
    r = rows[0]
    assert r["title"] == "Photosynthesis"
    assert r["provider"] == "atanor_index:wiki"
    assert r["source_type"] == "atanor_index"
    assert r["url"].endswith("/wiki/Photosynthesis")
    # exact same keys external providers emit, so the fan-out merge treats it uniformly
    assert {"id", "title", "url", "snippet", "provider", "search_score"} <= set(r)


def test_retriever_dominance_filter(tmp_path, monkeypatch):
    """A clearly-dominant top hit must not drag lower-scoring distractors into the fan-out
    (measured live: 'Capital of Korea' 56 vs 'Capital punishment' 21 → composer picked the distractor)."""
    src = tmp_path / "p.tsv"
    src.write_text(
        "Capital of Korea\tThe capital of Korea is Seoul, the seat of the South Korea government.\n"
        "Capital punishment in South Korea\tCapital punishment in South Korea is a legal penalty.\n"
        "Squatting in South Korea\tSquatting in South Korea is the occupation of derelict buildings.\n",
        encoding="utf-8")
    idx_dir = tmp_path / "idx"
    build_index(src, idx_dir, progress_every=0)
    from packages.atanor_index import retriever
    monkeypatch.setenv("ATANOR_INDEX_DIR", str(idx_dir))
    monkeypatch.delenv("ATANOR_DISABLE_LOCAL_INDEX", raising=False)
    retriever._STATE.update({"idx": None, "tried_dir": None})
    rows = retriever.local_search("capital of South Korea", count=6)
    titles = [r["title"] for r in rows]
    assert titles[0] == "Capital of Korea"
    assert "Capital punishment in South Korea" not in titles   # distractor filtered by dominance


def test_retriever_disabled_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ATANOR_DISABLE_LOCAL_INDEX", "1")
    from packages.atanor_index import retriever
    retriever._STATE.update({"idx": None, "tried_dir": None})
    assert retriever.local_search("anything", 3) == []
