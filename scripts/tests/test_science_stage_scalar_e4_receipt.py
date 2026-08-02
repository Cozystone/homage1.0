from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    canonical_json_bytes,
)
from scripts import science_stage_scalar_e4_receipt as receipt


EXPECTED_CANDIDATE_CLOSURE = {
    "packages/__init__.py",
    "packages/cognitive_core/__init__.py",
    "packages/cognitive_core/adapters.py",
    "packages/cognitive_core/canonical.py",
    "packages/cognitive_core/chat_shadow.py",
    "packages/cognitive_core/contracts.py",
    "packages/cognitive_core/cycle.py",
    "packages/cognitive_core/cycle_ledger.py",
    "packages/cognitive_core/replay.py",
    "packages/cognitive_core/shadow.py",
    "packages/evolution/rational_evolver.py",
    "packages/reasoning_vm/__init__.py",
    "packages/reasoning_vm/deliberator/__init__.py",
    "packages/reasoning_vm/deliberator/science_quantity_goal.py",
    "packages/reasoning_vm/deliberator/science_quantity_resolver.py",
    "packages/reasoning_vm/quantity.py",
    "packages/reasoning_vm/scalar_quantity.py",
    "packages/reasoning_vm/science_quantity_exam.py",
    "packages/reasoning_vm/science_quantity_staging.py",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return receipt.build_receipt(repo_root=receipt.REPO)


def _write_canonical(path: Path, value: dict) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _rechecksum(value: dict) -> dict:
    value["manifest_checksum_sha256"] = receipt._checksum(value)
    return value


def _detached(value: dict) -> dict:
    return json.loads(canonical_json_bytes(value))


def test_scalar_receipt_binds_exact_fresh_process_candidate_closure(
    manifest: dict,
) -> None:
    assert set(receipt.CANDIDATE_PATHS) == EXPECTED_CANDIDATE_CLOSURE
    assert {
        row["path"] for row in manifest["candidate"]["files"]
    } == EXPECTED_CANDIDATE_CLOSURE

    code = r"""
import sys
from pathlib import Path
from packages.reasoning_vm.science_quantity_exam import answer_scalar_science_mcq
from packages.reasoning_vm.science_quantity_staging import load_science_quantity_stage
root = Path.cwd().resolve()
stage = load_science_quantity_stage(
    root / "packages/reasoning_vm/tests/fixtures/science_stage_scalar_quantity_v1"
)
answer_scalar_science_mcq(
    "What volume of 0.30 M NaOH is required to completely neutralize "
    "25.0 mL of 0.18 M HCl?",
    {"A": "12 mL", "B": "15 mL", "C": "18 mL", "D": "30 mL"},
    stage,
    overlay_enabled=True,
)
paths = set()
for module in tuple(sys.modules.values()):
    value = getattr(module, "__file__", None)
    if not value:
        continue
    try:
        relative = Path(value).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        continue
    if relative.endswith(".py"):
        paths.add(relative)
print("\n".join(sorted(paths)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=receipt.REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    assert set(completed.stdout.splitlines()) == EXPECTED_CANDIDATE_CLOSURE


def test_scalar_receipt_measures_paired_capability_curve(
    manifest: dict,
) -> None:
    assert receipt.validate_receipt(manifest) == []
    metrics = manifest["metrics"]
    off = metrics["off"]
    on = metrics["on"]

    assert off["n"] == on["n"] == 12
    assert off["input_valid"] == off["compiled"] == 12
    assert (
        off["raw_fired"]
        == off["formula_fired"]
        == off["resolver_grounded"]
        == off["proof_replayed"]
        == off["accepted_fired"]
        == off["correct"]
        == off["wrong_fire"]
        == 0
    )
    assert off["abstain"] == 12
    assert (
        on["input_valid"]
        == on["compiled"]
        == on["raw_fired"]
        == on["formula_fired"]
        == on["resolver_grounded"]
        == on["proof_replayed"]
        == on["accepted_fired"]
        == on["grounded"]
        == on["correct"]
        == on["provenance_bound_fires"]
        == 12
    )
    assert on["wrong_fire"] == on["abstain"] == on["error"] == 0
    assert on["grounded_leaf_count_total"] == 36
    assert on["grounded_stage_leaf_count_total"] == 36
    assert on["evidence_id_count_total"] == 36
    assert metrics["off_to_on"]["transition_counts"] == {
        "abstain_to_correct": 12
    }
    assert metrics["off_to_on"]["strict_accuracy_delta"] == 1.0
    assert metrics["e4_development_gate_passed"] is True


def test_scalar_receipt_keeps_correlated_groups_and_proof_counts_explicit(
    manifest: dict,
) -> None:
    metamorphic = manifest["metrics"]["metamorphic"]
    assert metamorphic["semantic_group_count"] == 6
    assert metamorphic["passed"] == 6
    assert metamorphic["all_passed"] is True
    assert metamorphic["inferential_independence_claimed"] is False
    assert len(metamorphic["groups"]) == 6

    for row in manifest["items"]:
        expected_primary = (
            ["off", "on"]
            if row["ordinal"] % 2 == 0
            else ["on", "off"]
        )
        assert row["primary_execution_order"] == expected_primary
        assert row["replay_execution_order"] == list(
            reversed(expected_primary)
        )
        assert row["gold_absent_from_candidate_arguments"] is True
        assert row["on_output_matches_expected_answer"] is True
        assert row["conditions"]["on"]["output_value_liters"] == row[
            "expected_answer_liters"
        ]
        assert all(row["replay"][field] is True for field in (
            "input_fingerprint_same",
            "goal_digest_same",
            "off_semantic_outcome_same",
            "on_semantic_outcome_same",
        ))
        off = row["conditions"]["off"]
        on = row["conditions"]["on"]
        assert off["stage_structurally_absent"] is True
        assert off["stage_digest_sha256"] is None
        assert off["stage_snapshot_bound_bytes"] == 0
        assert off["stage_bytes_read"] == 0
        assert on["raw_fired"] is True
        assert on["formula_fired"] is True
        assert on["resolver_grounded"] is True
        assert on["proof_replayed"] is True
        assert on["accepted_fire"] is True
        assert on["provenance_bound"] is True
        assert on["grounded_leaf_count"] == 3
        assert on["grounded_stage_leaf_count"] == 3
        assert len(on["evidence_ids"]) == 3
        assert on["external_authenticity_established"] is False


def test_scalar_receipt_candidate_and_partial_stage_controls_pass(
    manifest: dict,
) -> None:
    controls = manifest["metrics"]["controls"]
    assert controls == {
        "candidate_accepted_fires": 0,
        "candidate_condition_executions": 12,
        "candidate_contract_passed": 6,
        "candidate_control_count": 6,
        "candidate_controls_all_passed": True,
        "candidate_raw_fires": 0,
        "control_probe_gate_passed": True,
        "staging_control_count": 3,
        "staging_controls_all_passed": True,
        "staging_rejections_observed": 3,
    }
    assert {
        row["control_type"] for row in manifest["staging_controls"]
    } == {"species_claim", "formula_ast", "external_auth_flag"}
    for row in manifest["staging_controls"]:
        assert row["loader_accepted"] is False
        assert row["snapshot_returned"] is False
        assert row["expected_rejection_observed"] is True
        assert row["semantic_replay_same"] is True
        assert row["contract_passed"] is True
        assert row["error_kind"] == "ScienceQuantityStageError"
        assert len(row["mutated_stage_content_sha256"]) == 64
        assert len(row["observed_loader_error_sha256"]) == 64


def test_scalar_receipt_candidate_boundary_rejects_gold(manifest: dict) -> None:
    stage = receipt.load_science_quantity_stage(receipt.REPO / receipt.STAGE_ROOT)
    with pytest.raises(
        BenchmarkEvidenceError,
        match="only question and choices",
    ):
        receipt.run_candidate(
            {
                "question": "forbidden",
                "choices": {"A": "1 mL", "B": "2 mL"},
                "gold": "A",
            },
            stage=stage,
            overlay_enabled=True,
            base_state_digest=lambda: "0" * 64,
        )


def test_scalar_evaluator_does_not_trust_candidate_choice_value() -> None:
    outcome = {
        "choice_key": "B",
        "compiler": {
            "choice_items": [
                {"key": "B", "value_liters": "999"},
            ],
        },
    }
    assert receipt._evaluator_output_value_liters(
        outcome,
        {
            "A": "12 mL",
            "B": "15 mL",
            "C": "18 mL",
            "D": "30 mL",
        },
    ) == "3/200"


def test_scalar_fixture_requires_gold_to_be_unique_exact_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = receipt.REPO / receipt.FIXTURE_PATH
    fixture = json.loads(source.read_bytes())
    fixture["paired_items"][0]["gold"] = "A"
    payload = canonical_json_bytes(fixture) + b"\n"
    target = tmp_path / receipt.FIXTURE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    monkeypatch.setattr(
        receipt,
        "FROZEN_FIXTURE_SHA256",
        receipt._sha256(payload),
    )
    with pytest.raises(
        BenchmarkEvidenceError,
        match="gold is not the unique exact answer",
    ):
        receipt._fixture(tmp_path)


def test_scalar_receipt_is_deterministic_and_seal_is_local_only(
    manifest: dict,
) -> None:
    replayed = receipt.build_receipt(repo_root=receipt.REPO)
    assert replayed == manifest
    assert manifest["claims"] == {
        "benchmark_capability_claimed": False,
        "classification": (
            "bounded_scalar_neutralization_with_controls_development_only"
        ),
        "control_probe_evidence": True,
        "control_probe_gate_passed": True,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "e4_development_evidence": True,
        "e4_development_gate_passed": True,
        "e5_claimed": False,
        "external_authenticity_established": False,
        "externally_signed": False,
        "hidden_holdout_claimed": False,
        "independent": False,
        "process_resource_curve_claimed": False,
        "shipped_graph_immutability_claimed": False,
    }
    assert manifest["seal"]["sealed"] is True
    assert manifest["seal"]["hidden_holdout_claimed"] is False
    assert manifest["seal"]["independent_evaluation_claimed"] is False
    assert manifest["seal"]["authenticity_established"] is False
    assert (
        manifest["seal"]["coordinated_stage_rewrite_resistance_claimed"]
        is False
    )
    assert manifest["seal"]["shipped_graph_immutability_claimed"] is False
    assert manifest["integrity"]["shipped_graph_immutability_observed"] is False
    assert manifest["seal"]["resource_curve_established"] is False
    assert manifest["seal"]["e5_equivalent"] is False
    assert manifest["protocol"]["fresh_process_current_replay_enforced"] is True
    assert (
        manifest["integrity"]["fresh_process_current_replay_enforced"]
        is True
    )


def test_scalar_receipt_canonical_write_once_and_current_verification(
    tmp_path: Path,
    manifest: dict,
) -> None:
    path = tmp_path / "scalar-receipt.json"
    receipt.write_receipt_exclusive(
        path,
        manifest,
        repo_root=receipt.REPO,
    )
    assert path.read_bytes() == canonical_json_bytes(manifest) + b"\n"
    assert receipt.read_receipt(path) == manifest
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=True,
    )
    assert report == {
        "authenticity_established": False,
        "candidate_matches_current": True,
        "checksum_sha256": manifest["manifest_checksum_sha256"],
        "dataset_matches_current": True,
        "declared_sealed": True,
        "e5_claimed": False,
        "findings": [],
        "matches_current": True,
        "resource_curve_established": False,
        "sealed": True,
        "source_matches_current": True,
        "stage_matches_current": True,
        "structure_valid": True,
        "valid": True,
        "verified_sealed": True,
    }
    with pytest.raises(BenchmarkEvidenceError, match="already exists"):
        receipt.write_receipt_exclusive(
            path,
            manifest,
            repo_root=receipt.REPO,
        )


def test_scalar_receipt_without_current_replay_is_not_verified_sealed(
    tmp_path: Path,
    manifest: dict,
) -> None:
    path = tmp_path / "historical.json"
    _write_canonical(path, manifest)
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=False,
    )
    assert report["valid"] is True
    assert report["structure_valid"] is True
    assert report["declared_sealed"] is True
    assert report["verified_sealed"] is False
    assert report["sealed"] is False


@pytest.mark.parametrize(
    "variant",
    ("authority", "result", "resource", "scope"),
)
def test_scalar_verifier_rejects_rechecksummed_nested_tampering(
    tmp_path: Path,
    manifest: dict,
    variant: str,
) -> None:
    tampered = _detached(manifest)
    if variant == "authority":
        tampered["claims"]["independent"] = True
    elif variant == "result":
        tampered["items"][0]["conditions"]["on"]["accepted_fire"] = False
    elif variant == "resource":
        tampered["resources"] = {"rss_delta_bytes": 1}
    elif variant == "scope":
        tampered["candidate"]["files"][0]["sha256"] = "0" * 64
        tampered["candidate"]["content_sha256"] = receipt._sha256(
            canonical_json_bytes(tampered["candidate"]["files"])
        )
    _rechecksum(tampered)
    path = tmp_path / f"{variant}.json"
    _write_canonical(path, tampered)

    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=True,
    )
    assert report["valid"] is False
    assert report["verified_sealed"] is False
    assert report["sealed"] is False
    assert report["findings"]
    assert any(
        "current deterministic payload mismatch" in finding
        for finding in report["findings"]
    )


def test_scalar_verifier_fails_closed_on_malformed_seal(
    tmp_path: Path,
    manifest: dict,
) -> None:
    tampered = _detached(manifest)
    tampered["seal"] = []
    _rechecksum(tampered)
    path = tmp_path / "malformed-seal.json"
    _write_canonical(path, tampered)
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=True,
    )
    assert report["valid"] is False
    assert report["declared_sealed"] is False
    assert report["verified_sealed"] is False
    assert report["sealed"] is False
    assert report["findings"]


def test_scalar_verifier_rebinds_scopes_after_current_replay(
    tmp_path: Path,
    manifest: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "current.json"
    _write_canonical(path, manifest)
    original = receipt._scope_matches_current
    calls = 0

    def changes_after_initial_binding(scope, repo_root):
        nonlocal calls
        calls += 1
        return calls <= 4 and original(scope, repo_root)

    monkeypatch.setattr(
        receipt,
        "_scope_matches_current",
        changes_after_initial_binding,
    )
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=True,
    )
    assert report["valid"] is False
    assert report["sealed"] is False
    assert any(
        "scope differs after current semantic replay" in finding
        for finding in report["findings"]
    )


def test_scalar_builder_rebinds_scopes_across_fresh_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = receipt._bind_receipt_scopes
    calls = 0

    def changes_after_worker(repo_root):
        nonlocal calls
        calls += 1
        scopes = original(repo_root)
        if calls == 2:
            scopes["stage"] = _detached(scopes["stage"])
            scopes["stage"]["content_sha256"] = "0" * 64
        return scopes

    monkeypatch.setattr(
        receipt,
        "_bind_receipt_scopes",
        changes_after_worker,
    )
    with pytest.raises(
        BenchmarkEvidenceError,
        match="changed across fresh scalar worker: stage",
    ):
        receipt.build_receipt(repo_root=receipt.REPO)


def test_scalar_reader_requires_canonical_json_and_one_newline(
    tmp_path: Path,
    manifest: dict,
) -> None:
    pretty = tmp_path / "pretty.json"
    pretty.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(BenchmarkEvidenceError, match="not canonical"):
        receipt.read_receipt(pretty)

    duplicate = tmp_path / "duplicate.json"
    payload = canonical_json_bytes(manifest).decode("utf-8")
    duplicate_payload = payload.replace(
        '{"candidate":',
        '{"schema_version":"duplicate","candidate":',
        1,
    )
    duplicate.write_bytes(
        duplicate_payload.encode("utf-8") + b"\n"
    )
    with pytest.raises(BenchmarkEvidenceError, match="duplicate JSON key"):
        receipt.read_receipt(duplicate)
