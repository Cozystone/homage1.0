from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packages.graph_scale.mutation_batch import (
    GraphAddition,
    GraphRetraction,
    MutationBatchError,
    MutationStage,
    create_mutation_batch,
    record_applied_receipt,
    record_lifecycle_receipt,
    validate_mutation_batch,
)


BASE = "a" * 64
CREATED = "2026-07-25T00:00:00.000000Z"
SEALED = "2026-07-25T00:00:01.000000Z"


def _addition(
    subject: str = "France",
    predicate: str = "capital",
    object_: str = "Paris",
) -> GraphAddition:
    return GraphAddition(
        subject=subject,
        predicate=predicate,
        object=object_,
        provenance="curated:test",
        source_refs=("urn:test:2", "urn:test:1"),
    )


def _retraction(
    subject: str = "France",
    predicate: str = "capital",
    object_: str = "Lyon",
) -> GraphRetraction:
    return GraphRetraction(
        subject=subject,
        predicate=predicate,
        object=object_,
        reason="functional-predicate contradiction",
        evidence_refs=("urn:test:truth",),
    )


def _create(
    root: Path,
    *,
    additions=(_addition(),),
    retractions=(_retraction(),),
):
    return create_mutation_batch(
        producer_id="unit_test",
        producer_run_id="run-001",
        base_digest_sha256=BASE,
        additions=additions,
        retractions=retractions,
        created_at=CREATED,
        sealed_at=SEALED,
        batches_root=root,
    )


def test_manifest_identity_is_input_order_independent(tmp_path: Path) -> None:
    additions = (
        _addition("Korea", "capital", "Seoul"),
        _addition(),
    )
    retractions = (
        _retraction(),
        _retraction("Korea", "capital", "Busan"),
    )
    first = _create(
        tmp_path / "first",
        additions=additions,
        retractions=retractions,
    )
    second = _create(
        tmp_path / "second",
        additions=reversed(additions),
        retractions=reversed(retractions),
    )

    assert first.batch_id == second.batch_id
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["base_digest_sha256"] == BASE
    assert manifest["counts"] == {"additions": 2, "retractions": 2}
    assert manifest["production_store_mutated"] is False
    assert manifest["additions"][0]["source_refs"] == [
        "urn:test:1",
        "urn:test:2",
    ]
    assert first.manifest_path.read_bytes() == json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert validate_mutation_batch(
        first.root,
        expected_base_digest_sha256=BASE,
    ).ok


@pytest.mark.parametrize(
    ("additions", "retractions"),
    [
        ((), ()),
        ((_addition(), _addition()), ()),
        ((), (_retraction(), _retraction())),
        (
            (_addition(),),
            (
                GraphRetraction(
                    "France",
                    "capital",
                    "Paris",
                    "overlap",
                ),
            ),
        ),
        (
            (GraphAddition("x", "p", "y", ""),),
            (),
        ),
        (
            (),
            (GraphRetraction("x", "p", "y", "  "),),
        ),
    ],
)
def test_invalid_mutation_sets_are_rejected(
    tmp_path: Path,
    additions,
    retractions,
) -> None:
    with pytest.raises(MutationBatchError):
        _create(
            tmp_path / "batches",
            additions=additions,
            retractions=retractions,
        )


def test_invalid_base_digest_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(MutationBatchError):
        create_mutation_batch(
            producer_id="unit_test",
            producer_run_id="run-001",
            base_digest_sha256="A" * 64,
            additions=(_addition(),),
            batches_root=tmp_path,
        )


def test_batch_collision_preserves_first_bytes(tmp_path: Path) -> None:
    first = _create(tmp_path / "batches")
    before = first.manifest_path.read_bytes()
    with pytest.raises(MutationBatchError):
        _create(tmp_path / "batches")
    assert first.manifest_path.read_bytes() == before


@pytest.mark.parametrize("target", ["manifest.json", "seal.json"])
def test_manifest_or_seal_tampering_is_detected(
    tmp_path: Path,
    target: str,
) -> None:
    batch = _create(tmp_path / "batches")
    path = batch.root / target
    path.write_bytes(path.read_bytes() + b" ")
    validation = validate_mutation_batch(batch.root)
    assert not validation.ok
    assert any("canonical" in error or "contract" in error for error in validation.errors)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    batch = _create(tmp_path / "batches")
    raw = batch.manifest_path.read_text(encoding="utf-8")
    batch.manifest_path.write_text(
        raw[:-1] + ',"batch_id":"gmb_' + "0" * 32 + '"}',
        encoding="utf-8",
    )
    validation = validate_mutation_batch(batch.root)
    assert not validation.ok
    assert "manifest is unreadable" in validation.errors


def test_expected_base_mismatch_is_detected(tmp_path: Path) -> None:
    batch = _create(tmp_path / "batches")
    validation = validate_mutation_batch(
        batch.root,
        expected_base_digest_sha256="b" * 64,
    )
    assert not validation.ok
    assert "manifest base digest does not match expected base" in validation.errors


def test_lifecycle_is_strict_and_truthful(tmp_path: Path) -> None:
    batch = _create(tmp_path / "batches")
    with pytest.raises(MutationBatchError):
        record_lifecycle_receipt(batch.root, stage="proposed")

    detected = record_lifecycle_receipt(
        batch.root,
        stage="detected",
        occurred_at="2026-07-25T00:00:02.000000Z",
        evidence={"candidate_count": 2},
    )
    proposed = record_lifecycle_receipt(
        batch.root,
        stage="proposed",
        occurred_at="2026-07-25T00:00:03.000000Z",
        evidence={"manifest_sha256": batch.manifest_sha256},
    )
    staged = record_lifecycle_receipt(
        batch.root,
        stage="staged",
        occurred_at="2026-07-25T00:00:04.000000Z",
        evidence={"seal_validated": True},
    )
    with pytest.raises(MutationBatchError):
        record_lifecycle_receipt(batch.root, stage="staged")

    validation = validate_mutation_batch(batch.root)
    assert validation.ok
    assert validation.latest_stage is MutationStage.STAGED
    previous = None
    for path in (detected, proposed, staged):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        assert receipt["production_store_mutated"] is False
        assert receipt["previous_receipt_sha256"] == previous
        previous = hashlib.sha256(path.read_bytes()).hexdigest()


def test_receipt_chain_tampering_is_detected(tmp_path: Path) -> None:
    batch = _create(tmp_path / "batches")
    first = record_lifecycle_receipt(
        batch.root,
        stage="detected",
        evidence={"candidate_count": 1},
    )
    record_lifecycle_receipt(batch.root, stage="proposed")
    first.write_bytes(first.read_bytes().replace(b'"candidate_count"', b'"other_count"'))
    validation = validate_mutation_batch(batch.root)
    assert not validation.ok
    assert any("chain" in error for error in validation.errors)


def test_applied_refuses_unbound_or_uncommitted_evidence(
    tmp_path: Path,
) -> None:
    batch = _create(tmp_path / "batches")
    for stage in ("detected", "proposed", "staged"):
        record_lifecycle_receipt(batch.root, stage=stage)
    with pytest.raises(
        MutationBatchError,
        match="does not bind this mutation batch",
    ):
        record_applied_receipt(
            batch.root,
            committed_promotion={
                "swapped": True,
                "mutation_batch_manifest_sha256": "b" * 64,
            },
        )


def test_creation_does_not_touch_unrelated_shipped_snapshot(
    tmp_path: Path,
) -> None:
    fake_shipped = tmp_path / "shipped"
    fake_shipped.mkdir()
    sentinel = fake_shipped / "sentinel.bin"
    sentinel.write_bytes(b"immutable-live-bytes")
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    _create(tmp_path / "batches")
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before
