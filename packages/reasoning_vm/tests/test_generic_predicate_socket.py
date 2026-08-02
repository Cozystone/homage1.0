from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import struct

import pytest

from packages.graph_scale.triple_store import TripleStore
from packages.reasoning_vm.deliberator.generic_predicate_socket import (
    CompositePredicateSocket,
    PREDICATE_NAMESPACE,
    PredicateStageSpec,
    StageBindingError,
)


def _build_stage(
    root: Path,
    rows: tuple[tuple[str, str, str], ...],
    *,
    source_name: str,
    source_pattern: str,
    build_index: bool = True,
    manifest_name: str | None = None,
    qid_pid_rows: tuple[tuple[int, int], ...] | None = None,
    completion_state: str = "complete",
    declared_sidecar_digest: str | None = None,
) -> None:
    store = TripleStore(root)
    source_id = store.intern_source(source_name, source_pattern)
    for subject, predicate, object_value in rows:
        assert store.add(
            subject,
            predicate,
            object_value,
            source=source_id,
        )
    store.flush()
    if build_index:
        store.rebuild_index()
    store.close()
    sidecar_raw = None
    if qid_pid_rows is not None:
        assert len(qid_pid_rows) == len(rows)
        sidecar_raw = b"".join(
            struct.pack("<QI", qid, pid) for qid, pid in qid_pid_rows
        )
        (root / "qid_pid.col").write_bytes(sidecar_raw)
    if manifest_name is not None:
        manifest = {
            "completion_state": completion_state,
            "fixture": root.name,
        }
        if qid_pid_rows is not None:
            profile = {}
            for (_subject, predicate, _object), (_qid, pid) in zip(
                rows,
                qid_pid_rows,
            ):
                profile[f"P{pid}"] = {"predicate": predicate}
            sidecar = {
                "path": "qid_pid.col",
                "record_format": (
                    "little-endian uint64 QID number + uint32 PID number"
                ),
                "record_bytes": 12,
                "records": len(rows),
            }
            if declared_sidecar_digest is not None:
                sidecar["sha256"] = (
                    hashlib.sha256(sidecar_raw).hexdigest()
                    if declared_sidecar_digest == "auto"
                    else declared_sidecar_digest
                )
            manifest.update(
                {
                    "mode": "wikidata-truthy-literal-only",
                    "promotion_eligible": completion_state == "complete",
                    "property_profile": profile,
                    "qid_pid_sidecar": sidecar,
                }
            )
        (root / manifest_name).write_text(
            json.dumps(manifest, sort_keys=True),
            encoding="utf-8",
        )


def _tree_snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    rows = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.as_posix(),
    ):
        raw = path.read_bytes()
        stat = path.stat()
        rows.append(
            (
                path.relative_to(root).as_posix(),
                stat.st_size,
                stat.st_mtime_ns,
                hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(rows)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_composite_context_reads_dynamic_entity_and_literal_predicates_without_writes(
    tmp_path: Path,
) -> None:
    entity_root = tmp_path / "b1_entity"
    literal_root = tmp_path / "s1_literal"
    _build_stage(
        entity_root,
        (
            ("Europa", "orbits", "Jupiter"),
            ("Europa", "P31", "moon"),
            ("Io", "orbits", "Jupiter"),
        ),
        source_name="wikidata-truthy",
        source_pattern="https://example.test/entity/{s}",
        manifest_name="B1_WIKIDATA_MANIFEST.json",
    )
    _build_stage(
        literal_root,
        (
            ("Europa", "discovery_year", "1610"),
            ("Europa", "orbital_resonance_signature", "2:1"),
        ),
        source_name="wikidata-truthy-literal",
        source_pattern="https://example.test/literal/{s}",
        manifest_name="S1_WIKIDATA_LITERAL_MANIFEST.json",
        qid_pid_rows=((3143, 575), (3143, 2146)),
        declared_sidecar_digest="auto",
    )
    before = {
        "entity": _tree_snapshot(entity_root),
        "literal": _tree_snapshot(literal_root),
    }

    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="b1-entity",
                role="entity",
                root=entity_root,
            ),
            PredicateStageSpec(
                stage_id="s1-literal",
                role="literal",
                root=literal_root,
                expected_qid_pid_sidecar_digest_sha256=(
                    _sha256_file(literal_root / "qid_pid.col")
                ),
            ),
        ),
        max_facts_per_stage=8,
        max_rows_examined_per_stage=16,
    ) as socket:
        first = socket.context_for_subject("Europa")
        second = socket.context_for_subject("Europa")

    after = {
        "entity": _tree_snapshot(entity_root),
        "literal": _tree_snapshot(literal_root),
    }
    assert after == before
    assert first.status == "ready"
    assert first.complete is True
    assert first.context_digest_sha256 == second.context_digest_sha256
    assert tuple(row.predicate.name for row in first.facts) == (
        "orbits",
        "P31",
        "discovery_year",
        "orbital_resonance_signature",
    )
    assert tuple(row.name for row in first.predicates_for_subject("Europa")) == (
        "P31",
        "discovery_year",
        "orbital_resonance_signature",
        "orbits",
    )
    assert first.predicates_for_subject("Io") == ()
    p31 = next(row for row in first.predicate_vocabulary if row.name == "P31")
    assert p31.canonical_id == "stage:P31"
    assert p31.namespace == PREDICATE_NAMESPACE
    assert p31.wikidata_property_id is None
    assert {
        (row.stage_id, row.object_kind)
        for row in first.facts
    } == {
        ("b1-entity", "entity"),
        ("s1-literal", "literal"),
    }
    assert {
        row.object_value
        for row in first.facts_for_subject("Europa", "orbits")
    } == {"Jupiter"}
    assert all(row.fact_digest_sha256 for row in first.facts)
    bindings = {row.stage_id: row for row in first.stage_bindings}
    assert {
        row.predicate.canonical_id
        for row in first.facts
    } == {
        "stage:P31",
        "stage:discovery_year",
        "stage:orbital_resonance_signature",
        "stage:orbits",
    }
    assert all(
        row.source_subject_entity_id is None
        and row.source_property_id is None
        and row.source_qid_pid_sidecar_digest_sha256 is None
        for row in first.facts
        if row.stage_id == "b1-entity"
    )
    literal_sources = {
        row.predicate.name: (
            row.source_subject_entity_id,
            row.source_property_id,
        )
        for row in first.facts
        if row.stage_id == "s1-literal"
    }
    assert literal_sources == {
        "discovery_year": ("Q3143", "P575"),
        "orbital_resonance_signature": ("Q3143", "P2146"),
    }
    assert (
        bindings["b1-entity"].stage_digest_sha256
        == _sha256_file(entity_root / "B1_WIKIDATA_MANIFEST.json")
    )
    assert (
        bindings["b1-entity"].source_digest_sha256
        == _sha256_file(entity_root / "sources.txt")
    )
    assert (
        bindings["s1-literal"].stage_digest_sha256
        == _sha256_file(literal_root / "S1_WIKIDATA_LITERAL_MANIFEST.json")
    )
    assert (
        bindings["s1-literal"].source_digest_sha256
        == _sha256_file(literal_root / "sources.txt")
    )
    assert bindings["b1-entity"].qid_pid_sidecar_digest_sha256 is None
    assert (
        bindings["s1-literal"].qid_pid_sidecar_digest_sha256
        == _sha256_file(literal_root / "qid_pid.col")
    )
    assert bindings["s1-literal"].qid_pid_sidecar_records == 2
    assert first.authority_claims["wikidata_pid_binding_established"] is False
    with pytest.raises(FrozenInstanceError):
        first.status = "overflow"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        p31.name = "instance_of"  # type: ignore[misc]


def test_subject_overflow_is_fail_closed_and_exposes_no_partial_vocabulary(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bounded"
    _build_stage(
        root,
        (
            ("hub", "predicate_a", "a"),
            ("hub", "predicate_b", "b"),
            ("hub", "predicate_c", "c"),
        ),
        source_name="fixture",
        source_pattern="",
    )
    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="bounded-stage",
                role="generic",
                root=root,
            ),
        ),
        max_facts_per_stage=2,
        max_rows_examined_per_stage=3,
    ) as socket:
        context = socket.context_for_subject("hub")

    assert context.status == "overflow"
    assert context.complete is False
    assert context.overflow_stage_ids == ("bounded-stage",)
    assert context.facts == ()
    assert context.predicate_vocabulary == ()
    assert context.facts_for_subject("hub") == ()


def test_raw_subject_row_cap_is_fail_closed_before_partial_decoding(
    tmp_path: Path,
) -> None:
    root = tmp_path / "row_cap"
    _build_stage(
        root,
        tuple(("hub", f"predicate_{index}", str(index)) for index in range(4)),
        source_name="fixture",
        source_pattern="",
    )
    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="row-cap-stage",
                role="generic",
                root=root,
            ),
        ),
        max_facts_per_stage=3,
        max_rows_examined_per_stage=3,
    ) as socket:
        context = socket.context_for_subject("hub")

    assert context.status == "overflow"
    assert context.facts == ()
    assert context.predicate_vocabulary == ()


def test_stage_without_complete_subject_index_is_rejected_instead_of_scanned(
    tmp_path: Path,
) -> None:
    root = tmp_path / "unindexed"
    _build_stage(
        root,
        (("Europa", "orbits", "Jupiter"),),
        source_name="fixture",
        source_pattern="",
        build_index=False,
    )
    before = _tree_snapshot(root)

    with pytest.raises(
        StageBindingError,
        match="no subject index",
    ):
        CompositePredicateSocket.open(
            (
                PredicateStageSpec(
                    stage_id="unindexed-stage",
                    role="generic",
                    root=root,
                ),
            )
        )

    assert _tree_snapshot(root) == before


def test_expected_stage_and_source_digests_are_checked_exactly(
    tmp_path: Path,
) -> None:
    root = tmp_path / "attested"
    _build_stage(
        root,
        (("Europa", "orbits", "Jupiter"),),
        source_name="fixture",
        source_pattern="",
    )
    stage_digest = _sha256_file(root / "meta.json")
    source_digest = _sha256_file(root / "sources.txt")

    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="attested-stage",
                role="generic",
                root=root,
                expected_stage_digest_sha256=stage_digest,
                expected_source_digest_sha256=source_digest,
            ),
        )
    ) as socket:
        assert (
            socket.stage_bindings[0].qid_pid_sidecar_digest_sha256
            is None
        )
        assert socket.context_for_subject("missing").status == "not_found"

    with pytest.raises(StageBindingError, match="descriptor digest"):
        CompositePredicateSocket.open(
            (
                PredicateStageSpec(
                    stage_id="wrong-digest-stage",
                    role="generic",
                    root=root,
                    expected_stage_digest_sha256="0" * 64,
                    expected_source_digest_sha256=source_digest,
                ),
            )
        )


def test_literal_qid_pid_sidecar_digest_tampering_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tampered_literal"
    _build_stage(
        root,
        (("Europa", "discovery_year", "1610"),),
        source_name="wikidata-truthy-literal",
        source_pattern="",
        manifest_name="S1_WIKIDATA_LITERAL_MANIFEST.json",
        qid_pid_rows=((3143, 575),),
        declared_sidecar_digest="auto",
    )
    sidecar = root / "qid_pid.col"
    raw = bytearray(sidecar.read_bytes())
    raw[0] ^= 1
    sidecar.write_bytes(raw)
    before = _tree_snapshot(root)

    with pytest.raises(StageBindingError, match="digest does not match"):
        CompositePredicateSocket.open(
            (
                PredicateStageSpec(
                    stage_id="tampered-literal",
                    role="literal",
                    root=root,
                ),
            )
        )

    assert _tree_snapshot(root) == before


def test_partial_literal_qid_pid_sidecar_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "partial_literal"
    _build_stage(
        root,
        (("Europa", "discovery_year", "1610"),),
        source_name="wikidata-truthy-literal",
        source_pattern="",
        manifest_name="S1_WIKIDATA_LITERAL_MANIFEST.json",
        qid_pid_rows=((3143, 575),),
        declared_sidecar_digest="auto",
    )
    sidecar = root / "qid_pid.col"
    sidecar.write_bytes(sidecar.read_bytes()[:-1])

    with pytest.raises(StageBindingError, match="torn or row-misaligned"):
        CompositePredicateSocket.open(
            (
                PredicateStageSpec(
                    stage_id="partial-literal",
                    role="literal",
                    root=root,
                ),
            )
        )


def test_literal_qid_pid_row_reordering_fails_closed_on_lookup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "reordered_literal"
    _build_stage(
        root,
        (
            ("Europa", "discovery_year", "1610"),
            ("Europa", "orbital_period", "3.55 days"),
        ),
        source_name="wikidata-truthy-literal",
        source_pattern="",
        manifest_name="S1_WIKIDATA_LITERAL_MANIFEST.json",
        qid_pid_rows=((3143, 575), (3143, 2146)),
        declared_sidecar_digest="auto",
    )
    sidecar = root / "qid_pid.col"
    first, second = struct.iter_unpack("<QI", sidecar.read_bytes())
    reordered = struct.pack("<QI", *second) + struct.pack("<QI", *first)
    sidecar.write_bytes(reordered)
    manifest_path = root / "S1_WIKIDATA_LITERAL_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["qid_pid_sidecar"]["sha256"] = hashlib.sha256(
        reordered
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )

    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="reordered-literal",
                role="literal",
                root=root,
            ),
        )
    ) as socket:
        with pytest.raises(
            StageBindingError,
            match="does not match the staged predicate",
        ):
            socket.context_for_subject("Europa")
