from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from packages.cognitive_core.canonical import canonical_json
from packages.reasoning_vm.deliberator.science_relation_goal import (
    compile_typed_relation_select,
)
from packages.reasoning_vm.deliberator.science_relation_staging import (
    RELATION_PROPERTY_ID,
    ScienceRelationStageError,
    _manifest_checksum,
    load_science_relation_stage,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures/science_stage_typed_relation_v1"
)
CHOICES = {
    "A": "France",
    "B": "Greece",
    "C": "Italy",
}


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "stage"
    shutil.copytree(FIXTURE, target)
    return target


def _write_manifest(root: Path, manifest: dict) -> None:
    manifest["manifest_checksum_sha256"] = _manifest_checksum(manifest)
    (root / "manifest.json").write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_frozen_fixture_loads_with_no_authority_claim() -> None:
    stage = load_science_relation_stage(FIXTURE)

    assert stage.stage_id == "science-relation-stage-p17-diagnostic-v1"
    assert len(stage.entities) == 4
    assert len(stage.relations) == 1
    assert stage.bound_bytes > 0
    assert len(stage.stage_digest_sha256) == 64
    assert len(stage.manifest_checksum_sha256) == 64
    assert stage.authority_claims
    assert all(value is False for value in stage.authority_claims.values())
    assert stage.relations[0].proof_fact == ("Q1524", "P17", "Q41")


def test_compiler_goal_yields_one_unranked_property_preserving_proof() -> None:
    stage = load_science_relation_stage(FIXTURE)
    compilation = compile_typed_relation_select(
        "Which country is Athens located in?",
        CHOICES,
    )

    proofs = stage.proof_candidates(compilation)

    assert len(proofs) == 1
    proof = proofs[0]
    assert proof.choice_key == "B"
    assert proof.answer_type == "country"
    assert proof.proof_fact == ("Q1524", RELATION_PROPERTY_ID, "Q41")
    assert proof.to_dict()["semantic_fact"] == [
        "Q1524",
        "located_in",
        "Q41",
    ]
    assert [row.property_id for row in proof.evidence] == [
        "rdfs:label",
        "P31",
        "rdfs:label",
        "P31",
        "P17",
    ]
    assert all(
        row.externally_authenticated is False for row in proof.evidence
    )
    assert len(proof.provenance_digest_sha256) == 64


def test_stage_abstains_outside_its_country_nation_p17_profile() -> None:
    stage = load_science_relation_stage(FIXTURE)
    province = compile_typed_relation_select(
        "Which province is Athens located in?",
        CHOICES,
    )
    unknown = compile_typed_relation_select(
        "Which country is Atlantis located in?",
        CHOICES,
    )

    assert province.compiled is True
    assert unknown.compiled is True
    assert stage.proof_candidates(province) == ()
    assert stage.proof_candidates(unknown) == ()


def test_fixture_contains_no_forbidden_collapsed_location_property() -> None:
    source = (FIXTURE / "wikidata_truthy_rows.nt").read_text(
        encoding="utf-8"
    )
    relations = (FIXTURE / "relations.jsonl").read_text(
        encoding="utf-8"
    )

    assert "/P17>" in source
    assert '"source_property_id":"P17"' in relations
    for property_id in ("P30", "P131", "P159", "P276"):
        assert f"/{property_id}>" not in source
        assert f'"source_property_id":"{property_id}"' not in relations


@pytest.mark.parametrize(
    "filename",
    [
        "entities.jsonl",
        "relations.jsonl",
        "evidence.jsonl",
        "wikidata_truthy_rows.nt",
    ],
)
def test_any_bound_payload_drift_fails_closed(
    tmp_path: Path,
    filename: str,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / filename
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(ScienceRelationStageError):
        load_science_relation_stage(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capability_claimed", True),
        ("e4_claimed", True),
        ("external_authenticity_established", True),
    ],
)
def test_authority_claims_cannot_be_forged_even_with_fresh_checksum(
    tmp_path: Path,
    field: str,
    value: bool,
) -> None:
    root = _copy_fixture(tmp_path)
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["claims"][field] = value
    _write_manifest(root, manifest)

    with pytest.raises(
        ScienceRelationStageError,
        match="authority claims",
    ):
        load_science_relation_stage(root)


def test_manifest_integer_counts_reject_boolean_coercion(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["relation_count"] = True
    _write_manifest(root, manifest)

    with pytest.raises(ScienceRelationStageError, match="row counts"):
        load_science_relation_stage(root)


def test_detached_snapshot_detects_in_memory_fact_forgery() -> None:
    stage = load_science_relation_stage(FIXTURE)
    object.__setattr__(stage.relations[0], "source_property_id", "P131")

    with pytest.raises(ScienceRelationStageError, match="seal"):
        stage.assert_validated()
