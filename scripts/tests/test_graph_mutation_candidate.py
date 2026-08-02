from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.graph_scale.mutation_batch import (
    GraphAddition,
    GraphRetraction,
    MutationStage,
    create_mutation_batch,
    record_lifecycle_receipt,
    validate_mutation_batch,
)
from packages.graph_scale.triple_store import TripleStore
from scripts import landing_chain_lib as landing


def _close(store: TripleStore) -> None:
    store.flush()
    if hasattr(store.terms, "close"):
        store.terms.close()


def _live_store(root: Path) -> None:
    store = TripleStore(root)
    source = store.intern_source("curated:test", "urn:test:base")
    assert store.add("France", "capital", "Paris", source=source)
    assert store.add("Korea", "capital", "Seoul", source=source)
    store.flush()
    store.rebuild_index()
    _close(store)


def _proposed_batch(
    root: Path,
    *,
    base_digest: str,
    additions=(
        GraphAddition(
            "Germany",
            "capital",
            "Berlin",
            "curated:test",
            ("urn:test:germany",),
        ),
    ),
    retractions=(
        GraphRetraction(
            "France",
            "capital",
            "Paris",
            "superseded test assertion",
            ("urn:test:review",),
        ),
    ),
):
    batch = create_mutation_batch(
        producer_id="candidate_test",
        producer_run_id="run-001",
        base_digest_sha256=base_digest,
        additions=additions,
        retractions=retractions,
        created_at="2026-07-25T01:00:00.000000Z",
        sealed_at="2026-07-25T01:00:01.000000Z",
        batches_root=root,
    )
    record_lifecycle_receipt(
        batch.root,
        stage="detected",
        evidence={"operations": batch.addition_count + batch.retraction_count},
    )
    record_lifecycle_receipt(
        batch.root,
        stage="proposed",
        evidence={"manifest_sha256": batch.manifest_sha256},
    )
    return batch


def _setup(tmp_path: Path, monkeypatch):
    live = tmp_path / "kg_triples"
    _live_store(live)
    monkeypatch.setattr(landing, "CANONICAL_SHIPPED_ROOT", live.resolve())
    base_digest = landing._tree_sha256(live)
    batch = _proposed_batch(
        tmp_path / "batches",
        base_digest=base_digest,
    )
    candidate = live.parent / f"{live.name}.staged_merge.mutation01"
    return live, base_digest, batch, candidate


def test_mixed_batch_builds_verified_candidate_without_mutating_live(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live, base_digest, batch, candidate = _setup(tmp_path, monkeypatch)
    merger = landing.StoreMerger(live, live)

    result = merger.build_mutation_candidate(
        candidate,
        mutation_batch_root=batch.root,
    )

    assert result["built"] is True
    assert result["verified"] is True
    assert result["staged"] is True
    assert result["production_store_mutated"] is False
    assert result["mutation_batch_manifest_sha256"] == batch.manifest_sha256
    assert landing._tree_sha256(live) == base_digest

    candidate_store = TripleStore(candidate)
    try:
        assert (
            "Germany",
            "capital",
            "Berlin",
        ) in candidate_store.facts_about("Germany", limit=10)
        assert (
            "France",
            "capital",
            "Paris",
        ) not in candidate_store.facts_about("France", limit=10)
        assert (
            "Korea",
            "capital",
            "Seoul",
        ) in candidate_store.facts_about("Korea", limit=10)
    finally:
        _close(candidate_store)

    verification = json.loads(
        (candidate / "VERIFY_REPORT.json").read_text(encoding="utf-8")
    )
    assert verification["ok"] is True
    assert (
        verification["mutation_batch_manifest_sha256"]
        == batch.manifest_sha256
    )
    batch_validation = validate_mutation_batch(batch.root)
    assert batch_validation.ok
    assert batch_validation.latest_stage is MutationStage.STAGED


def test_stale_base_batch_is_refused_and_live_is_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live = tmp_path / "kg_triples"
    _live_store(live)
    monkeypatch.setattr(landing, "CANONICAL_SHIPPED_ROOT", live.resolve())
    before = landing._tree_sha256(live)
    batch = _proposed_batch(
        tmp_path / "batches",
        base_digest="f" * 64,
    )
    candidate = live.parent / f"{live.name}.staged_merge.stale01"

    with pytest.raises(Exception, match="base"):
        landing.StoreMerger(live, live).build_mutation_candidate(
            candidate,
            mutation_batch_root=batch.root,
        )
    assert not candidate.exists()
    assert landing._tree_sha256(live) == before
    assert (
        validate_mutation_batch(batch.root).latest_stage
        is MutationStage.PROPOSED
    )


def test_missing_retraction_target_fails_atomically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live = tmp_path / "kg_triples"
    _live_store(live)
    monkeypatch.setattr(landing, "CANONICAL_SHIPPED_ROOT", live.resolve())
    before = landing._tree_sha256(live)
    batch = _proposed_batch(
        tmp_path / "batches",
        base_digest=before,
        additions=(),
        retractions=(
            GraphRetraction(
                "Atlantis",
                "capital",
                "Poseidon",
                "invalid target",
            ),
        ),
    )
    candidate = live.parent / f"{live.name}.staged_merge.missing01"

    with pytest.raises(RuntimeError, match="absent"):
        landing.StoreMerger(live, live).build_mutation_candidate(
            candidate,
            mutation_batch_root=batch.root,
        )
    assert not candidate.exists()
    assert landing._tree_sha256(live) == before


def test_tombstoned_readdition_is_refused(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live = tmp_path / "kg_triples"
    _live_store(live)
    (live / "retractions.jsonl").write_text(
        json.dumps(
            {
                "s": "France",
                "p": "capital",
                "o": "Paris",
                "reason": "prior decision",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(landing, "CANONICAL_SHIPPED_ROOT", live.resolve())
    before = landing._tree_sha256(live)
    batch = _proposed_batch(
        tmp_path / "batches",
        base_digest=before,
        additions=(
            GraphAddition(
                "France",
                "capital",
                "Paris",
                "curated:test",
            ),
        ),
        retractions=(),
    )
    candidate = live.parent / f"{live.name}.staged_merge.resurrect01"

    with pytest.raises(RuntimeError, match="resurrect"):
        landing.StoreMerger(live, live).build_mutation_candidate(
            candidate,
            mutation_batch_root=batch.root,
        )
    assert not candidate.exists()
    assert landing._tree_sha256(live) == before


def test_add_failure_leaves_no_candidate_and_no_staged_credit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live, before, batch, candidate = _setup(tmp_path, monkeypatch)

    def fail_add(*args, **kwargs):
        raise RuntimeError("injected add failure")

    monkeypatch.setattr(TripleStore, "add", fail_add)
    with pytest.raises(RuntimeError, match="injected add failure"):
        landing.StoreMerger(live, live).build_mutation_candidate(
            candidate,
            mutation_batch_root=batch.root,
        )
    assert not candidate.exists()
    assert landing._tree_sha256(live) == before
    assert (
        validate_mutation_batch(batch.root).latest_stage
        is MutationStage.PROPOSED
    )


def test_embedded_manifest_tamper_breaks_fresh_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live, _before, batch, candidate = _setup(tmp_path, monkeypatch)
    merger = landing.StoreMerger(live, live)
    merger.build_mutation_candidate(
        candidate,
        mutation_batch_root=batch.root,
    )
    embedded = candidate / landing.MUTATION_BINDING_DIRECTORY / "manifest.json"
    embedded.write_bytes(embedded.read_bytes() + b" ")

    report = merger._evaluate_verification(candidate)
    assert report["ok"] is False
