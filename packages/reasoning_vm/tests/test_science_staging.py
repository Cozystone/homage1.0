from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from packages.reasoning_vm.science_staging import (
    ScienceStageSnapshot,
    ScienceStageError,
    StagedKnowledgeOverlay,
    load_science_stage,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "science_stage_atomic_number_v1"
)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _refresh_manifest(stage: Path) -> None:
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, name in (("facts_file", "facts.jsonl"), ("evidence_file", "evidence.jsonl")):
        payload = (stage / name).read_bytes()
        manifest[key]["bytes"] = len(payload)
        manifest[key]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest.pop("manifest_checksum_sha256", None)
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    manifest["manifest_checksum_sha256"] = hashlib.sha256(canonical).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_stage_loads_as_complete_provenance_bound_read_only_snapshot():
    before = _tree_digest(FIXTURE)
    stage = load_science_stage(FIXTURE)
    after = _tree_digest(FIXTURE)
    assert before == after
    assert len(stage.facts) == 15
    assert len(stage.stage_digest_sha256) == 64
    assert stage.facts_about("oxygen") == (
        ("oxygen", "atomic_number", "8"),
    )
    evidence = stage.evidence_for(("oxygen", "atomic_number", "8"))
    assert evidence is not None
    assert evidence.evidence_id == "wd-q629-p1086-r2521216193"
    assert evidence.source_revision == "2521216193"
    assert evidence.license == "CC0-1.0"


def test_snapshot_constructor_cannot_mint_validation_authority():
    with pytest.raises(ScienceStageError, match="does not bind"):
        ScienceStageSnapshot(
            stage_id="forged",
            stage_digest_sha256="0" * 64,
            manifest_checksum_sha256="0" * 64,
            bound_bytes=0,
            facts=(),
            _by_subject={},
            _by_triple={},
            _validation_seal="0" * 64,
        )

    valid = load_science_stage(FIXTURE)
    oxygen = next(row for row in valid.facts if row.triple[0] == "oxygen")
    uranium = next(row for row in valid.facts if row.triple[0] == "uranium")
    forged = replace(
        oxygen,
        triple=("oxygen", "atomic_number", "92"),
        evidence=uranium.evidence,
    )
    with pytest.raises(ScienceStageError, match="does not bind"):
        replace(
            valid,
            facts=(forged,),
            _by_subject={"oxygen": (forged,)},
            _by_triple={forged.triple: forged.evidence},
        )


def test_stage_root_junction_or_reparse_point_is_rejected(monkeypatch):
    original = getattr(Path, "is_junction", lambda _path: False)

    def fake_is_junction(path):
        if path == FIXTURE:
            return True
        return original(path)

    monkeypatch.setattr(Path, "is_junction", fake_is_junction, raising=False)
    with pytest.raises(ScienceStageError, match="regular directory"):
        load_science_stage(FIXTURE)


def test_overlay_is_default_off_and_attributes_only_stage_exposed_rows():
    stage = load_science_stage(FIXTURE)
    off = StagedKnowledgeOverlay(lambda _subject: [], None)
    assert off.enabled is False
    assert off.snapshot is None
    assert off.facts_about("oxygen") == []
    assert off.stage_hit_count == 0
    assert off.telemetry()["stage_snapshot_bound_bytes"] == 0
    assert off.telemetry()["stage_digest_sha256"] is None

    with pytest.raises(TypeError, match="must not retain"):
        StagedKnowledgeOverlay(lambda _subject: [], stage)
    with pytest.raises(TypeError, match="requires"):
        StagedKnowledgeOverlay(lambda _subject: [], None, enabled=True)

    on = StagedKnowledgeOverlay(lambda _subject: [], stage, enabled=True)
    assert on.facts_about("oxygen") == [
        ("oxygen", "atomic_number", "8")
    ]
    assert on.facts_about("oxygen") == [
        ("oxygen", "atomic_number", "8")
    ]
    assert on.stage_hit_count == 1
    assert on.evidence_for(("oxygen", "atomic_number", "8")) is not None

    duplicate_base = StagedKnowledgeOverlay(
        lambda subject: (
            [(subject, "atomic_number", "8")]
            if subject == "oxygen"
            else []
        ),
        stage,
        enabled=True,
    )
    assert duplicate_base.facts_about("oxygen") == [
        ("oxygen", "atomic_number", "8")
    ]
    assert duplicate_base.stage_hit_count == 0
    assert duplicate_base.evidence_for(
        ("oxygen", "atomic_number", "8")
    ) is None


def test_proof_binding_rejects_malformed_or_unbounded_leaf_shapes():
    stage = load_science_stage(FIXTURE)
    overlay = StagedKnowledgeOverlay(
        lambda _subject: [],
        stage,
        enabled=True,
    )
    overlay.facts_about("oxygen")

    class MalformedProof:
        def leaves(self):
            return [
                ("oxygen", "atomic_number", "8", "unbound-extra"),
            ]

        def to_dict(self):
            return {"kind": "malformed"}

    with pytest.raises(ScienceStageError, match="exact string triple"):
        overlay.bind_proof(MalformedProof())


def test_torn_or_forged_stage_bytes_fail_closed(tmp_path):
    stage = tmp_path / "stage"
    shutil.copytree(FIXTURE, stage)
    facts = stage / "facts.jsonl"
    facts.write_bytes(facts.read_bytes()[:-1])
    with pytest.raises(ScienceStageError, match="bytes mismatch|sha256 mismatch"):
        load_science_stage(stage)

    shutil.rmtree(stage)
    shutil.copytree(FIXTURE, stage)
    evidence = stage / "evidence.jsonl"
    rows = evidence.read_text(encoding="utf-8").splitlines()
    forged = json.loads(rows[0])
    forged["source_record_id"] = (
        "Q753$4b7c3d50-4c8e-28a1-a0f9-0c97a4fefa1b"
    )
    rows[0] = json.dumps(
        forged,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    evidence.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _refresh_manifest(stage)
    with pytest.raises(ScienceStageError, match="provenance identity mismatch"):
        load_science_stage(stage)


def test_quarantine_and_functional_conflicts_never_reach_reasoner(tmp_path):
    stage = tmp_path / "stage"
    shutil.copytree(FIXTURE, stage)
    facts = stage / "facts.jsonl"
    rows = facts.read_text(encoding="utf-8").splitlines()
    quarantined = json.loads(rows[0])
    quarantined["quarantined"] = True
    rows[0] = json.dumps(
        quarantined,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    facts.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _refresh_manifest(stage)
    with pytest.raises(ScienceStageError, match="is quarantined"):
        load_science_stage(stage)

    shutil.rmtree(stage)
    shutil.copytree(FIXTURE, stage)
    facts = stage / "facts.jsonl"
    rows = facts.read_text(encoding="utf-8").splitlines()
    conflict = json.loads(rows[3])
    conflict["object"] = "7"
    rows[3] = json.dumps(
        conflict,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    facts.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _refresh_manifest(stage)
    with pytest.raises(
        ScienceStageError,
        match="functional predicate conflict|multiple subjects",
    ):
        load_science_stage(stage)
