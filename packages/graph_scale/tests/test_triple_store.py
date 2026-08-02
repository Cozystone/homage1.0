"""The trillion-scale substrate: an integer-columnar triple store that ingests curated
(s,p,o) facts fast, de-dupes exactly, survives a reopen, and feeds the answer bridge —
so bulk knowledge is stored densely AND becomes usable answers."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import packages.graph_scale.triple_store as triple_store_module
from packages.graph_scale.triple_store import TripleStore, TermDict


def test_ingest_dedup_and_count():
    root = Path(tempfile.mkdtemp()) / "kg"
    ts = TripleStore(root)
    r = ts.bulk_ingest([("일본", "capital", "도쿄도"), ("캐나다", "capital", "오타와"),
                        ("일본", "capital", "도쿄도")])   # last is a duplicate
    assert r["added"] == 2 and r["duplicates"] == 1
    assert len(ts) == 2


def test_persists_across_reopen():
    root = Path(tempfile.mkdtemp()) / "kg"
    TripleStore(root).bulk_ingest([("프랑스", "capital", "파리")])
    reopened = TripleStore(root)          # fresh instance reads terms + count from disk
    assert len(reopened) == 1
    assert reopened.facts_about("프랑스") == [("프랑스", "capital", "파리")]


def test_reopened_query_does_not_rewrite_store_metadata(monkeypatch):
    root = Path(tempfile.mkdtemp()) / "kg"
    TripleStore(root).bulk_ingest([("france", "capital", "paris")])
    reopened = TripleStore(root)

    def fail_on_query_write(*_args, **_kwargs):
        raise AssertionError("read-only query attempted to rewrite store metadata")

    monkeypatch.setattr(reopened, "_write_meta", fail_on_query_write)
    assert reopened.facts_about("france") == [
        ("france", "capital", "paris")
    ]
    assert reopened.facts_about("definitely absent") == []


def test_facts_about_memmap_scan():
    root = Path(tempfile.mkdtemp()) / "kg"
    ts = TripleStore(root)
    ts.bulk_ingest([("한국", "capital", "서울"), ("한국", "language", "한국어"),
                    ("일본", "capital", "도쿄")])
    facts = ts.facts_about("한국", limit=10)
    assert ("한국", "capital", "서울") in facts and ("한국", "language", "한국어") in facts
    assert all(s == "한국" for s, _, _ in facts)


def test_dense_storage():
    """~12 bytes/triple in the columns (int32 x3) — vastly denser than JSON text rows."""
    root = Path(tempfile.mkdtemp()) / "kg"
    ts = TripleStore(root)
    ts.bulk_ingest([(f"E{i}", "rel", f"O{i}") for i in range(10000)])
    col_bytes = sum((root / f"{n}.col").stat().st_size for n in ("s", "p", "o"))
    assert col_bytes == 10000 * 3 * 4        # exactly 12 bytes/triple in the columns


def test_term_dict_stable_ids():
    d = TermDict(Path(tempfile.mkdtemp()) / "terms.txt")
    a, b = d.intern("서울"), d.intern("도쿄")
    assert d.intern("서울") == a and a != b          # stable, distinct
    assert d.term(a) == "서울"


def test_answer_bridge_reads_stored_facts(monkeypatch):
    root = Path(tempfile.mkdtemp()) / "kg"
    ts = TripleStore(root)
    ts.bulk_ingest([("일본", "capital", "도쿄도"), ("캐나다", "capital", "오타와")])
    import packages.graph_scale.answer_bridge as ab
    monkeypatch.setattr(ab, "_ROOT", root)
    ab._STORE["sig"] = None                          # force reload against the temp store
    r = ab.answer_from_triples("일본의 수도는?", "ko")
    assert r and "도쿄도" in r["answer"]
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False
    # a subject the store doesn't know -> honest None (no fabrication)
    ab._STORE["sig"] = None
    assert ab.answer_from_triples("존재하지않는나라의 수도는?", "ko") is None


@pytest.mark.parametrize("backend", ["ram", "sharded"])
def test_canonical_shipped_root_is_read_only_at_store_substrate(
    tmp_path,
    monkeypatch,
    backend,
):
    shipped = tmp_path / "kg_triples"
    writer = TripleStore(shipped, dict_backend=backend)
    writer.bulk_ingest([("france", "capital", "paris")])
    if hasattr(writer.terms, "close"):
        writer.terms.close()

    monkeypatch.setattr(
        triple_store_module,
        "_CANONICAL_SHIPPED_ROOT",
        shipped,
    )
    store = TripleStore(shipped, dict_backend=backend)
    before = {
        path.relative_to(shipped).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in shipped.rglob("*")
        if path.is_file()
    }

    assert store.facts_about("france") == [
        ("france", "capital", "paris")
    ]
    with pytest.raises(PermissionError, match="signed candidate promotion"):
        store.add("germany", "capital", "berlin")
    with pytest.raises(PermissionError, match="signed candidate promotion"):
        store.bulk_ingest([("germany", "capital", "berlin")])
    with pytest.raises(PermissionError, match="signed candidate promotion"):
        store.intern_source("forged")
    with pytest.raises(PermissionError, match="signed candidate promotion"):
        store.retract("france", "capital", "paris")
    with pytest.raises(PermissionError, match="signed candidate promotion"):
        store.rebuild_index()
    with pytest.raises(PermissionError, match="term dictionary is read-only"):
        store.terms.intern("new unsigned term")

    after = {
        path.relative_to(shipped).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in shipped.rglob("*")
        if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize("backend", ["ram", "sharded"])
def test_explicit_read_only_mode_protects_noncanonical_evaluation_store(
    tmp_path,
    backend,
):
    root = tmp_path / "evaluation_store"
    writer = TripleStore(root, dict_backend=backend)
    writer.bulk_ingest([("whale", "is_a", "mammal")])
    writer.close()
    before = {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
        if path.is_file()
    }

    reader = TripleStore(root, dict_backend=backend, read_only=True)
    assert reader.facts_about("whale") == [("whale", "is_a", "mammal")]
    with pytest.raises(PermissionError):
        reader.add("granite", "is_a", "mammal")
    reader.close()

    after = {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
