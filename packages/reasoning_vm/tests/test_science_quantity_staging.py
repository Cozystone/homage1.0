from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.reasoning_vm.science_quantity_staging import (
    NEUTRALIZATION_FORMULA_ID,
    QuantityStageOverlay,
    ScienceQuantityStageError,
    load_science_quantity_stage,
)


STAGE = (
    Path(__file__).parent
    / "fixtures"
    / "science_stage_scalar_quantity_v1"
)


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(f"{canonical_json(row)}\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _rebind_file_and_manifest(root: Path, filename: str) -> None:
    path = root / filename
    payload = path.read_bytes()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    field = {
        "species.jsonl": "species_file",
        "formulas.jsonl": "formulas_file",
        "evidence.jsonl": "evidence_file",
    }[filename]
    manifest[field] = {
        "path": filename,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    manifest.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = hashlib.sha256(
        canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _resign_manifest(root: Path, **updates) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(updates)
    manifest.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = hashlib.sha256(
        canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_quantity_stage_loads_as_immutable_content_bound_snapshot():
    snapshot = load_science_quantity_stage(STAGE)

    assert snapshot.stage_id == "science-quantity-stage-neutralization-v1"
    assert len(snapshot.species) == 7
    assert len(snapshot.formulas) == 1
    assert snapshot.species_for_alias("HCl").equivalents_per_mole == 1
    assert snapshot.species_for_alias("H2SO4").equivalents_per_mole == 2
    assert snapshot.species_for_alias("hcl") is None
    formula = snapshot.formula_for(NEUTRALIZATION_FORMULA_ID)
    assert formula is not None
    assert formula.result_dimension == "volume"
    assert formula.output_unit == "L"
    assert len(formula.expression_digest_sha256) == 64
    assert all(
        row.evidence.externally_authenticated is False
        for row in (*snapshot.species, *snapshot.formulas)
    )
    with pytest.raises(TypeError):
        snapshot._species_by_alias["forged"] = snapshot.species[0]


def test_quantity_overlay_keeps_off_structurally_absent_and_binds_three_rows():
    snapshot = load_science_quantity_stage(STAGE)
    off = QuantityStageOverlay(None, enabled=False)
    assert off.resolve_species("HCl") is None
    assert off.formula(NEUTRALIZATION_FORMULA_ID) is None
    assert off.telemetry()["stage_digest_sha256"] is None
    assert off.telemetry()["stage_snapshot_bound_bytes"] == 0
    with pytest.raises(TypeError):
        QuantityStageOverlay(snapshot, enabled=False)
    with pytest.raises(TypeError):
        QuantityStageOverlay(None, enabled=True)

    on = QuantityStageOverlay(snapshot, enabled=True)
    acid = on.resolve_species("HCl")
    base = on.resolve_species("NaOH")
    formula = on.formula(NEUTRALIZATION_FORMULA_ID)
    assert acid is not None and base is not None and formula is not None

    class Proof:
        def leaves(self):
            return [acid.proof_fact, base.proof_fact, formula.proof_fact]

        def to_dict(self):
            return {"leaves": [list(row) for row in self.leaves()]}

    binding = on.bind_proof(Proof())
    assert binding["grounded_leaf_count"] == 3
    assert binding["grounded_stage_leaf_count"] == 3
    assert [row["evidence_id"] for row in binding["evidence"]] == [
        "quantity-evidence-001",
        "quantity-evidence-002",
        "quantity-evidence-008",
    ]
    assert all(
        row["externally_authenticated"] is False
        for row in binding["evidence"]
    )


def test_quantity_overlay_rejects_duplicate_or_unexposed_proof_leaves():
    snapshot = load_science_quantity_stage(STAGE)
    overlay = QuantityStageOverlay(snapshot, enabled=True)
    acid = overlay.resolve_species("HCl")
    assert acid is not None

    class DuplicateProof:
        def leaves(self):
            return [acid.proof_fact, acid.proof_fact]

        def to_dict(self):
            return {"duplicate": True}

    with pytest.raises(ScienceQuantityStageError):
        overlay.bind_proof(DuplicateProof())

    class MixedProof:
        def leaves(self):
            return [
                acid.proof_fact,
                ("invented", "formula_expression_sha256", "0" * 64),
            ]

        def to_dict(self):
            return {"mixed": True}

    binding = overlay.bind_proof(MixedProof())
    assert binding["grounded_leaf_count"] == 2
    assert binding["grounded_stage_leaf_count"] == 1


def test_stage_rejects_species_change_without_bound_claim_update(tmp_path):
    root = tmp_path / "stage"
    shutil.copytree(STAGE, root)
    path = root / "species.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["equivalents_per_mole"] = 7
    _rewrite_jsonl(path, rows)
    _rebind_file_and_manifest(root, "species.jsonl")

    with pytest.raises(
        ScienceQuantityStageError,
        match="evidence binding invalid",
    ):
        load_science_quantity_stage(root)


def test_self_consistent_stage_rewrite_is_not_external_authentication(
    tmp_path,
):
    root = tmp_path / "self-consistent-rewrite"
    shutil.copytree(STAGE, root)
    species_path = root / "species.jsonl"
    species = [
        json.loads(line)
        for line in species_path.read_text(encoding="utf-8").splitlines()
    ]
    species[0]["equivalents_per_mole"] = 7
    _rewrite_jsonl(species_path, species)

    evidence_path = root / "evidence.jsonl"
    evidence = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
    ]
    claim = {
        "kind": "species_equivalents",
        "canonical_id": species[0]["canonical_id"],
        "alias": species[0]["alias"],
        "role": species[0]["role"],
        "equivalents_per_mole": 7,
    }
    statement = (
        "Self-consistent development rewrite for a trust-boundary test; "
        "this statement is deliberately not externally authenticated."
    )
    evidence[0]["claim_digest_sha256"] = canonical_digest(claim)
    evidence[0]["source_statement"] = statement
    evidence[0]["source_statement_sha256"] = hashlib.sha256(
        statement.encode("utf-8")
    ).hexdigest()
    _rewrite_jsonl(evidence_path, evidence)
    _rebind_file_and_manifest(root, "species.jsonl")
    _rebind_file_and_manifest(root, "evidence.jsonl")

    snapshot = load_science_quantity_stage(root)
    rewritten = snapshot.species_for_alias("HCl")
    assert rewritten is not None
    assert rewritten.equivalents_per_mole == 7
    assert rewritten.evidence.externally_authenticated is False


def test_stage_rejects_rechecksummed_formula_or_authenticity_forgery(
    tmp_path,
):
    formula_root = tmp_path / "formula"
    shutil.copytree(STAGE, formula_root)
    formula_path = formula_root / "formulas.jsonl"
    formula = json.loads(formula_path.read_text(encoding="utf-8"))
    formula["expression"][1] = "+"
    _rewrite_jsonl(formula_path, [formula])
    _rebind_file_and_manifest(formula_root, "formulas.jsonl")
    with pytest.raises(
        ScienceQuantityStageError,
        match="contract invalid",
    ):
        load_science_quantity_stage(formula_root)

    auth_root = tmp_path / "auth"
    shutil.copytree(STAGE, auth_root)
    evidence_path = auth_root / "evidence.jsonl"
    evidence = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
    ]
    evidence[0]["externally_authenticated"] = True
    _rewrite_jsonl(evidence_path, evidence)
    _rebind_file_and_manifest(auth_root, "evidence.jsonl")
    with pytest.raises(
        ScienceQuantityStageError,
        match="cannot assert external authentication",
    ):
        load_science_quantity_stage(auth_root)


def test_stage_rejects_extra_files_and_noncanonical_jsonl(tmp_path):
    extra_root = tmp_path / "extra"
    shutil.copytree(STAGE, extra_root)
    (extra_root / "foreign.txt").write_text("foreign", encoding="utf-8")
    with pytest.raises(
        ScienceQuantityStageError,
        match="file set mismatch",
    ):
        load_science_quantity_stage(extra_root)

    noncanonical_root = tmp_path / "noncanonical"
    shutil.copytree(STAGE, noncanonical_root)
    path = noncanonical_root / "species.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    rows[0] = json.dumps(json.loads(rows[0]), indent=2)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _rebind_file_and_manifest(noncanonical_root, "species.jsonl")
    with pytest.raises(ScienceQuantityStageError):
        load_science_quantity_stage(noncanonical_root)

    manifest_root = tmp_path / "noncanonical-manifest"
    shutil.copytree(STAGE, manifest_root)
    manifest_path = manifest_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(
        ScienceQuantityStageError,
        match="manifest is not canonical JSON",
    ):
        load_science_quantity_stage(manifest_root)


def test_stage_rejects_second_alias_for_same_proof_identity(tmp_path):
    root = tmp_path / "alias-collision"
    shutil.copytree(STAGE, root)
    species_path = root / "species.jsonl"
    species = [
        json.loads(line)
        for line in species_path.read_text(encoding="utf-8").splitlines()
    ]
    claim = {
        "kind": "species_equivalents",
        "canonical_id": "chem:hydrochloric_acid",
        "alias": "HydrogenChloride",
        "role": "acid",
        "equivalents_per_mole": 1,
    }
    species.append(
        {
            "row_id": "quantity-species-row-008",
            "canonical_id": claim["canonical_id"],
            "alias": claim["alias"],
            "role": claim["role"],
            "equivalents_per_mole": 1,
            "evidence_id": "quantity-evidence-009",
            "quarantined": False,
        }
    )
    _rewrite_jsonl(species_path, species)

    evidence_path = root / "evidence.jsonl"
    evidence = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
    ]
    statement = (
        "Curated development extraction, not externally authenticated: "
        "duplicate alias attack fixture."
    )
    evidence.append(
        {
            "evidence_id": "quantity-evidence-009",
            "claim_kind": "species_equivalents",
            "claim_digest_sha256": canonical_digest(claim),
            "source_url": "https://example.invalid/duplicate-alias",
            "source_record_id": "test:duplicate-alias",
            "source_revision": "test-v1",
            "license": "test-only",
            "source_statement": statement,
            "source_statement_sha256": hashlib.sha256(
                statement.encode("utf-8")
            ).hexdigest(),
            "externally_authenticated": False,
        }
    )
    _rewrite_jsonl(evidence_path, evidence)
    _rebind_file_and_manifest(root, "species.jsonl")
    _rebind_file_and_manifest(root, "evidence.jsonl")
    _resign_manifest(root, species_count=8)

    with pytest.raises(
        ScienceQuantityStageError,
        match="one alias per canonical species",
    ):
        load_science_quantity_stage(root)


def test_stage_rejects_json_numeric_bool_or_string_metadata_substitutes(
    tmp_path,
):
    policy_root = tmp_path / "numeric-policy"
    shutil.copytree(STAGE, policy_root)
    manifest_path = policy_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance_policy"]["license_required"] = 1
    manifest_path.write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _resign_manifest(policy_root)
    with pytest.raises(
        ScienceQuantityStageError,
        match="provenance policy invalid",
    ):
        load_science_quantity_stage(policy_root)

    metadata_root = tmp_path / "numeric-metadata"
    shutil.copytree(STAGE, metadata_root)
    evidence_path = metadata_root / "evidence.jsonl"
    evidence = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
    ]
    evidence[0]["source_revision"] = 20260725
    _rewrite_jsonl(evidence_path, evidence)
    _rebind_file_and_manifest(metadata_root, "evidence.jsonl")
    with pytest.raises(
        ScienceQuantityStageError,
        match="source_revision invalid",
    ):
        load_science_quantity_stage(metadata_root)
