from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

from packages.cognitive_core.canonical import canonical_json
from packages.reasoning_vm.deliberator import wikidata_property_catalog as catalog


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "wikidata_property_catalog_v1"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_records(root: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (root / catalog.PROPERTIES_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def _write_bound_records(
    root: Path,
    records: list[dict[str, object]],
) -> None:
    source = (
        "\n".join(canonical_json(record) for record in records) + "\n"
    ).encode("utf-8")
    (root / catalog.PROPERTIES_NAME).write_bytes(source)
    manifest_path = root / catalog.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["property_count"] = len(records)
    manifest["properties_file"] = {
        "path": catalog.PROPERTIES_NAME,
        "bytes": len(source),
        "sha256": _sha256(source),
    }
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = _sha256(
        canonical_json(unsigned).encode("utf-8")
    )
    manifest_path.write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "catalog"
    shutil.copytree(FIXTURE, target)
    return target


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_catalog_is_source_driven_and_preserves_exact_evidence() -> None:
    snapshot = catalog.load_wikidata_property_catalog(FIXTURE)

    assert len(snapshot.entries) == 2
    assert snapshot.property_by_id("P17").datatype == "wikibase-item"
    dynamic = snapshot.property_by_id("P2572")
    assert dynamic is not None
    assert dynamic.label == "hashtag"
    assert dynamic.aliases == ("social media hashtag",)
    assert dynamic.datatype == "string"
    assert snapshot.resolve_surface("HASHTAG") is dynamic
    assert snapshot.resolve_surface("  social   media hashtag ") is dynamic
    assert snapshot.resolve_surface("not in source") is None
    assert snapshot.resolve_surface(True) is None
    assert snapshot.property_by_id(2572) is None

    implementation = inspect.getsource(catalog)
    assert "P2572" not in implementation
    assert "hashtag" not in implementation.casefold()
    from packages.base_brain.relational_lookup import (
        RELATION_VOCAB,
        REL_SYNONYMS,
    )

    assert "hashtag" not in RELATION_VOCAB
    assert "hashtag" not in REL_SYNONYMS

    source_lines = (
        FIXTURE / catalog.PROPERTIES_NAME
    ).read_bytes().splitlines()
    evidence = dynamic.evidence
    assert evidence.exact_source_record_bytes == source_lines[1]
    assert evidence.source_record_byte_count == len(source_lines[1])
    assert evidence.source_record_sha256 == _sha256(source_lines[1])
    assert evidence.source_file_sha256 == _sha256(
        (FIXTURE / catalog.PROPERTIES_NAME).read_bytes()
    )
    assert evidence.source_row_number == 2
    assert evidence.source_revision == 2300002572
    assert evidence.source_revision_status == "available"
    assert (
        evidence.source_snapshot_checksum_sha256
        == snapshot.manifest_checksum_sha256
    )
    assert evidence.source_url.endswith(
        "/P2572.json?revision=2300002572"
    )
    assert evidence.license == "CC0-1.0"
    assert evidence.externally_authenticated is False

    assert set(snapshot.authority_claims.values()) == {False}
    assert snapshot.revision_unavailable_count == 0
    assert snapshot.excluded_unlabeled_property_count == 0
    assert snapshot.provenance_policy["source_revision_required"] is True
    assert snapshot.provenance_policy["network_access_allowed"] is False
    assert (
        snapshot.provenance_policy["shipped_graph_writes_allowed"] is False
    )
    assert snapshot.provenance_policy[
        "source_driven_predicate_vocabulary"
    ] is True


def test_snapshot_is_immutable_and_validation_sealed() -> None:
    snapshot = catalog.load_wikidata_property_catalog(FIXTURE)
    with pytest.raises(FrozenInstanceError):
        snapshot.entries[0].label = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        snapshot.authority_claims["capability_claimed"] = True  # type: ignore[index]
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="validation seal",
    ):
        replace(snapshot, catalog_digest_sha256="0" * 64)


def test_load_is_read_only_and_does_not_touch_external_tree(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    external = tmp_path / "shipped_graph"
    external.mkdir()
    sentinel = external / "sentinel.bin"
    sentinel.write_bytes(b"must-remain-byte-identical")
    before_catalog = _tree_hashes(root)
    before_external = _tree_hashes(external)

    catalog.load_wikidata_property_catalog(root)

    assert _tree_hashes(root) == before_catalog
    assert _tree_hashes(external) == before_external


def test_source_digest_tamper_fails_closed(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    source = root / catalog.PROPERTIES_NAME
    payload = source.read_bytes()
    source.write_bytes(payload.replace(b'"hashtag"', b'"hash-tag"'))
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="properties_file",
    ):
        catalog.load_wikidata_property_catalog(root)


def test_manifest_claim_cannot_be_promoted_by_rechecksumming(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    manifest_path = root / catalog.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["claims"]["capability_claimed"] = True
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = _sha256(
        canonical_json(unsigned).encode("utf-8")
    )
    manifest_path.write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="claims must all remain false",
    ):
        catalog.load_wikidata_property_catalog(root)


def test_duplicate_pid_fails_closed(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    records = _read_records(root)
    records[1]["id"] = "P17"
    _write_bound_records(root, records)
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="duplicate property id",
    ):
        catalog.load_wikidata_property_catalog(root)


def test_normalized_alias_collision_abstains_without_ranking(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    records = _read_records(root)
    records[1]["aliases"]["en"] = [  # type: ignore[index]
        {"language": "en", "value": "COUNTRY"}
    ]
    _write_bound_records(root, records)
    snapshot = catalog.load_wikidata_property_catalog(root)
    assert snapshot.resolve_surface("country") is None
    assert [
        entry.property_id
        for entry in snapshot.properties_for_surface("COUNTRY")
    ] == ["P17", "P2572"]


def test_duplicate_normalized_alias_within_property_fails_closed(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    records = _read_records(root)
    records[1]["aliases"]["en"] = [  # type: ignore[index]
        {"language": "en", "value": "SOCIAL MEDIA HASHTAG"},
        {"language": "en", "value": "social media hashtag"},
    ]
    _write_bound_records(root, records)
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="duplicate label or alias",
    ):
        catalog.load_wikidata_property_catalog(root)


def test_noncanonical_pid_order_fails_closed(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    records = list(reversed(_read_records(root)))
    _write_bound_records(root, records)
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="canonical PID order",
    ):
        catalog.load_wikidata_property_catalog(root)


def test_generation_change_during_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_fixture(tmp_path)
    source = root / catalog.PROPERTIES_NAME
    original = catalog._read_stable
    mutated = False

    def read_then_mutate(path: Path) -> bytes:
        nonlocal mutated
        payload = original(path)
        if path.name == catalog.MANIFEST_NAME and not mutated:
            source.write_bytes(
                source.read_bytes().replace(b'"hashtag"', b'"hash-tag"')
            )
            mutated = True
        return payload

    monkeypatch.setattr(catalog, "_read_stable", read_then_mutate)
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="generation changed while reading",
    ):
        catalog.load_wikidata_property_catalog(root)


def test_unexpected_file_is_rejected(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    (root / "unbound.txt").write_text("unbound", encoding="utf-8")
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="file set mismatch",
    ):
        catalog.load_wikidata_property_catalog(root)


def _write_property_label_db(
    tmp_path: Path,
    *,
    omit_type_for_second: bool = False,
    include_revisions: bool = True,
    include_unlabeled_datatype: bool = False,
    include_redundant_alias: bool = False,
    include_noncanonical_alias: bool = False,
) -> tuple[Path, Path]:
    dump = tmp_path / "truthy.nt.gz"
    dump.write_bytes(b"\x1f\x8bsource-snapshot")
    database = tmp_path / "labels.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE l(k INTEGER PRIMARY KEY, v TEXT)")
    connection.execute(
        "CREATE TABLE pl(k INTEGER PRIMARY KEY, v TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE pa(k INTEGER NOT NULL, v TEXT NOT NULL, "
        "PRIMARY KEY(k, v))"
    )
    connection.execute(
        "CREATE TABLE pt(k INTEGER PRIMARY KEY, v TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE pr(k INTEGER PRIMARY KEY, v TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO pl(k, v) VALUES(?, ?)",
        [(17, "country"), (2572, "hashtag")],
    )
    aliases = [
        (17, "located country"),
        (17, "sovereign state"),
        (2572, "social media hashtag"),
    ]
    if include_redundant_alias:
        aliases.append((17, "COUNTRY"))
    if include_noncanonical_alias:
        aliases.append((17, "foundation\u202f/\u2009creation date"))
    connection.executemany(
        "INSERT INTO pa(k, v) VALUES(?, ?)",
        aliases,
    )
    types = [
        (17, "http://wikiba.se/ontology#WikibaseItem"),
        (2572, "http://wikiba.se/ontology#String"),
    ]
    if omit_type_for_second:
        types.pop()
    if include_unlabeled_datatype:
        types.append(
            (14476, "http://wikiba.se/ontology#ExternalId")
        )
    connection.executemany("INSERT INTO pt(k, v) VALUES(?, ?)", types)
    revisions = (
        [(17, "2300000017"), (2572, "2300002572")]
        if include_revisions
        else []
    )
    connection.executemany(
        "INSERT INTO pr(k, v) VALUES(?, ?)",
        revisions,
    )
    dump_stat = dump.stat()
    metadata = {
        "dump_path": str(dump.resolve()),
        "dump_size_bytes": str(dump_stat.st_size),
        "dump_mtime_ns": str(dump_stat.st_mtime_ns),
        "scope": "complete",
        "property_catalog_profile": "wikidata_property_catalog_v1",
        "property_label_count": "2",
        "property_alias_count": str(len(aliases)),
        "property_type_count": str(len(types)),
        "property_revision_count": str(len(revisions)),
    }
    connection.executemany(
        "INSERT INTO meta(k, v) VALUES(?, ?)",
        sorted(metadata.items()),
    )
    connection.commit()
    connection.close()
    return database, dump


def test_readonly_label_db_adapter_preserves_dynamic_pid_and_datatype(
    tmp_path: Path,
) -> None:
    database, dump = _write_property_label_db(tmp_path)
    before = _sha256(database.read_bytes())

    snapshot = catalog.load_wikidata_property_catalog_from_label_db(
        database,
        dump,
    )

    assert _sha256(database.read_bytes()) == before
    assert snapshot.catalog_id == "wikidata-property-catalog-label-db-v2"
    dynamic = snapshot.resolve_surface("social media hashtag")
    assert dynamic is not None
    assert dynamic.property_id == "P2572"
    assert dynamic.datatype == "http://wikiba.se/ontology#String"
    assert dynamic.evidence.source_artifact_kind == (
        "sqlite_canonical_property_view"
    )
    assert dynamic.evidence.source_file_name.endswith(
        "#pl-pa-pt-pr.canonical.jsonl"
    )
    assert len(dynamic.evidence.source_file_sha256) == 64
    assert dynamic.evidence.source_revision == 2300002572
    assert dynamic.evidence.source_revision_status == "available"
    assert (
        dynamic.evidence.source_snapshot_checksum_sha256
        == snapshot.manifest_checksum_sha256
    )
    assert dynamic.evidence.externally_authenticated is False
    assert snapshot.revision_unavailable_count == 0
    assert snapshot.excluded_unlabeled_property_count == 0
    assert (
        snapshot.provenance_policy["source_revision_required"]
        is False
    )
    assert set(snapshot.authority_claims.values()) == {False}


def test_label_db_adapter_binds_revisionless_snapshot_and_excludes_unlabeled_type(
    tmp_path: Path,
) -> None:
    database, dump = _write_property_label_db(
        tmp_path,
        include_revisions=False,
        include_unlabeled_datatype=True,
        include_redundant_alias=True,
        include_noncanonical_alias=True,
    )
    before = _sha256(database.read_bytes())

    snapshot = catalog.load_wikidata_property_catalog_from_label_db(
        database,
        dump,
    )

    assert _sha256(database.read_bytes()) == before
    assert [entry.property_id for entry in snapshot.entries] == [
        "P17",
        "P2572",
    ]
    assert snapshot.property_by_id("P14476") is None
    assert snapshot.resolve_surface("foundation / creation date") is (
        snapshot.property_by_id("P17")
    )
    assert snapshot.excluded_unlabeled_property_ids == ("P14476",)
    assert snapshot.excluded_unlabeled_property_count == 1
    assert snapshot.revision_unavailable_count == 2
    assert (
        snapshot.provenance_policy["source_revision_required"]
        is False
    )
    for entry in snapshot.entries:
        evidence = entry.evidence
        assert evidence.source_revision is None
        assert (
            evidence.source_revision_status
            == "unavailable_bound_to_snapshot_digest"
        )
        assert (
            evidence.source_snapshot_checksum_sha256
            == snapshot.manifest_checksum_sha256
        )
        assert "?revision=" not in evidence.source_url
        assert evidence.externally_authenticated is False
    assert set(snapshot.authority_claims.values()) == {False}

    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="validation seal",
    ):
        replace(snapshot, excluded_unlabeled_property_ids=())


def test_label_db_adapter_rejects_incomplete_property_rows(
    tmp_path: Path,
) -> None:
    database, dump = _write_property_label_db(
        tmp_path,
        omit_type_for_second=True,
    )
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="incomplete PIDs",
    ):
        catalog.load_wikidata_property_catalog_from_label_db(database, dump)


def test_label_db_adapter_rejects_dump_identity_drift(
    tmp_path: Path,
) -> None:
    database, dump = _write_property_label_db(tmp_path)
    dump.write_bytes(dump.read_bytes() + b"changed")
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="not bound to the complete supplied dump",
    ):
        catalog.load_wikidata_property_catalog_from_label_db(database, dump)


def test_label_db_adapter_rejects_unbound_sqlite_sidecar(
    tmp_path: Path,
) -> None:
    database, dump = _write_property_label_db(tmp_path)
    Path(f"{database}-wal").write_bytes(b"unbound")
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="unbound SQLite sidecar",
    ):
        catalog.load_wikidata_property_catalog_from_label_db(database, dump)


def test_label_db_adapter_detects_dump_toctou(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, dump = _write_property_label_db(tmp_path)
    original = catalog._read_sqlite_pairs
    changed = False

    def read_then_change(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> tuple[tuple[int, str], ...]:
        nonlocal changed
        rows = original(connection, table_name)
        if not changed:
            dump.write_bytes(dump.read_bytes() + b"changed")
            changed = True
        return rows

    monkeypatch.setattr(catalog, "_read_sqlite_pairs", read_then_change)
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="changed during catalog load",
    ):
        catalog.load_wikidata_property_catalog_from_label_db(database, dump)


def test_label_db_adapter_detects_database_toctou(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, dump = _write_property_label_db(tmp_path)
    original = catalog._read_sqlite_pairs
    changed = False

    def read_then_touch(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> tuple[tuple[int, str], ...]:
        nonlocal changed
        rows = original(connection, table_name)
        if not changed:
            current = database.stat()
            os.utime(
                database,
                ns=(
                    current.st_atime_ns,
                    current.st_mtime_ns + 2_000_000_000,
                ),
            )
            changed = True
        return rows

    monkeypatch.setattr(catalog, "_read_sqlite_pairs", read_then_touch)
    with pytest.raises(
        catalog.WikidataPropertyCatalogError,
        match="changed during catalog load",
    ):
        catalog.load_wikidata_property_catalog_from_label_db(database, dump)
