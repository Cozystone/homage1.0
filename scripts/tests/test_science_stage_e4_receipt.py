from __future__ import annotations

import json

import pytest

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    canonical_json_bytes,
    write_manifest_exclusive,
)
from packages.reasoning_vm.science_staging import load_science_stage
from scripts import science_stage_e4_receipt as receipt


def test_candidate_scope_binds_cognitive_core_import_closure() -> None:
    expected = {
        "packages/cognitive_core/__init__.py",
        "packages/cognitive_core/adapters.py",
        "packages/cognitive_core/canonical.py",
        "packages/cognitive_core/chat_shadow.py",
        "packages/cognitive_core/contracts.py",
        "packages/cognitive_core/cycle.py",
        "packages/cognitive_core/cycle_ledger.py",
        "packages/cognitive_core/replay.py",
        "packages/cognitive_core/shadow.py",
    }
    assert expected <= set(receipt.CANDIDATE_PATHS)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return receipt.build_receipt()


def test_fixed_pair_is_argument_separated_source_bound_and_measures_accuracy(
    manifest: dict,
):
    assert receipt.validate_receipt(manifest, require_current=True) == []
    assert manifest["selection"]["evaluator_owned_fixed_denominator"] is True
    assert manifest["selection"]["expected_item_count"] == 15
    assert len(manifest["items"]) == 15
    assert manifest["metrics"]["off"]["strict_accuracy"] == 0.0
    assert manifest["metrics"]["off"]["engine_firing_rate"] == 0.0
    assert manifest["metrics"]["on"]["strict_accuracy"] == 1.0
    assert manifest["metrics"]["on"]["engine_firing_rate"] == 1.0
    assert manifest["metrics"]["on"]["grounded_coverage"] == 1.0
    assert manifest["metrics"]["on"]["wrong_fire_rate"] == 0.0
    assert manifest["metrics"]["off_to_on"]["strict_accuracy_delta"] == 1.0
    assert manifest["metrics"]["off_to_on"]["transition_counts"] == {
        "abstain_to_correct": 15
    }
    assert manifest["metrics"]["input_goal_replay_all"] is True
    assert manifest["metrics"]["base_state_immutable_all"] is True
    controls = manifest["metrics"]["control_probes"]
    assert controls["candidate"] == {
        "n": 3,
        "condition_executions": 6,
        "off_abstain": 3,
        "on_abstain": 3,
        "invalid_reject": 2,
        "compiler_scope_abstain": 2,
        "missing_stage_runtime_abstain": 1,
        "unresolved_entity_runtime_abstain": 1,
        "raw_control_fire": 0,
        "accepted_control_fire": 0,
        "off_unexpected_control_fire": 0,
        "on_unexpected_control_fire": 0,
        "unexpected_control_fire_rate": 0.0,
        "choice_without_accept": 0,
        "evidence_leak": 0,
        "error": 0,
        "off_stage_snapshot_exposure": 0,
        "on_stage_snapshot_missing": 0,
        "taxonomy_matches_all": True,
        "semantic_replay_all": True,
        "base_state_immutable_all": True,
    }
    assert controls["staging"] == {
        "n": 2,
        "rejected": 2,
        "snapshot_returned": 0,
        "semantic_replay_all": True,
        "expected_rejection_observed_all": True,
    }
    assert controls["control_probe_gate_passed"] is True
    assert manifest["metrics"]["e4_development_gate_passed"] is True

    assert manifest["claims"]["e5_claimed"] is False
    assert manifest["claims"]["independent"] is False
    assert manifest["claims"]["benchmark_capability_claimed"] is False
    assert manifest["seal"]["sealed"] is True
    assert manifest["seal"]["hidden_holdout_claimed"] is False
    assert manifest["seal"]["e5_equivalent"] is False
    assert manifest["claims"]["process_resource_curve_claimed"] is False
    assert "environment" not in manifest
    assert "started_at" not in manifest
    assert "completed_at" not in manifest
    assert manifest["integrity"][
        "gold_absent_from_candidate_arguments_all"
    ] is True
    assert manifest["integrity"]["base_state_immutable"] is True

    scopes = ("source", "candidate", "dataset", "stage")
    for scope in scopes:
        assert manifest[scope]["files"]
        assert len(manifest[scope]["content_sha256"]) == 64
        assert all(len(row["sha256"]) == 64 for row in manifest[scope]["files"])
    assert "packages/eval_evidence/__init__.py" in {
        row["path"] for row in manifest["source"]["files"]
    }
    assert manifest["fixture"]["actual_sha256"] == (
        receipt.FROZEN_FIXTURE_SHA256
    )
    assert len(manifest["stage_snapshot"]["stage_digest_sha256"]) == 64
    assert manifest["stage_snapshot"]["bound_bytes"] > 0

    for index, row in enumerate(manifest["items"]):
        assert row["evaluator_eligible"] is True
        assert row["gold_absent_from_candidate_arguments"] is True
        assert row["primary_execution_order"] == (
            ["off", "on"] if index % 2 == 0 else ["on", "off"]
        )
        assert row["replay_execution_order"] == list(
            reversed(row["primary_execution_order"])
        )
        off = row["conditions"]["off"]
        on = row["conditions"]["on"]
        assert off["compiler"]["input_valid"] is True
        assert on["compiler"]["input_valid"] is True
        assert off["compiler"]["compiled"] is True
        assert on["compiler"]["compiled"] is True
        assert off["engine_fired"] is False
        assert off["correct"] is False
        assert off["proof_digest_sha256"] is None
        assert off["provenance_digest_sha256"] is None
        assert off["stage_snapshot_bound_bytes"] == 0
        assert off["stage_bytes_read"] == 0
        assert off["rss_delta_bytes"] is None
        assert on["engine_fired"] is True
        assert on["grounded"] is True
        assert on["correct"] is True
        assert on["wrong_fire"] is False
        assert len(on["proof_digest_sha256"]) == 64
        assert len(on["provenance_digest_sha256"]) == 64
        assert on["stage_snapshot_bound_bytes"] == (
            manifest["stage_snapshot"]["bound_bytes"]
        )
        assert on["stage_bytes_read"] == 0
        assert on["rss_delta_bytes"] is None
        assert on["evidence_ids"]
        assert row["off_to_on"]["label"] == "abstain_to_correct"
        assert row["replay"]["input_fingerprint_same"] is True
        assert row["replay"]["goal_digest_same"] is True
        assert row["replay"]["off_semantic_outcome_same"] is True
        assert row["replay"]["on_semantic_outcome_same"] is True

    assert len(manifest["controls"]) == 3
    for row in manifest["controls"]:
        assert row["gold_absent_from_candidate_arguments"] is True
        assert row["conditions"]["off"]["stage_snapshot_bound_bytes"] == 0
        assert row["conditions"]["off"]["stage_digest_sha256"] is None
        assert row["conditions"]["on"]["stage_snapshot_bound_bytes"] == (
            manifest["stage_snapshot"]["bound_bytes"]
        )
        assert row["conditions"]["on"]["stage_digest_sha256"] == (
            manifest["stage_snapshot"]["stage_digest_sha256"]
        )
        for condition in ("off", "on"):
            record = row["conditions"][condition]
            assert record["raw_fired"] is False
            assert record["engine_fired"] is False
            assert record["choice_key"] is None
            assert record["proof_digest_sha256"] is None
            assert record["provenance_digest_sha256"] is None
            assert record["evidence_ids"] == []
            assert record["error_kind"] is None

    assert len(manifest["staging_controls"]) == 2
    assert {
        row["control_type"] for row in manifest["staging_controls"]
    } == {"corrupt_source", "quarantine_conflict"}
    for row in manifest["staging_controls"]:
        assert row["loader_accepted"] is False
        assert row["snapshot_returned"] is False
        assert row["expected_rejection_observed"] is True
        assert row["semantic_replay_same"] is True
        assert row["contract_passed"] is True
        assert row["error_kind"] == "ScienceStageError"
        assert len(row["observed_loader_error_sha256"]) == 64


def test_candidate_worker_rejects_any_gold_field():
    stage = load_science_stage(receipt.REPO / receipt.STAGE_ROOT)
    with pytest.raises(BenchmarkEvidenceError, match="only item_id"):
        receipt.run_candidate(
            {
                "item_id": "probe",
                "question": "What is the atomic number of hydrogen?",
                "choices": {"A": "1", "B": "2"},
                "gold": "A",
            },
            stage=stage,
            overlay_enabled=True,
            base_facts=lambda _subject: [],
            base_state_digest=lambda: "0" * 64,
        )


def test_exclusive_canonical_output_verifies_and_refuses_overwrite(
    manifest: dict,
    tmp_path,
):
    path = tmp_path / "science-e4-receipt.json"
    write_manifest_exclusive(path, manifest)
    report = receipt.verify_receipt(path, require_current=True)
    assert report == {
        "valid": True,
        "structure_valid": True,
        "matches_current": True,
        "declared_sealed": True,
        "verified_sealed": True,
        "sealed": True,
        "e5_claimed": False,
        "checksum_sha256": manifest["manifest_checksum_sha256"],
        "findings": [],
    }
    assert path.read_bytes() == canonical_json_bytes(manifest) + b"\n"
    with pytest.raises(BenchmarkEvidenceError, match="already exists"):
        write_manifest_exclusive(path, manifest)


def test_validator_recomputes_metrics_and_checksum(manifest: dict):
    tampered = json.loads(canonical_json_bytes(manifest))
    tampered["metrics"]["on"]["strict_accuracy"] = 0.0
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=False)
    assert "metrics do not derive from item outcomes" in findings

    tampered = json.loads(canonical_json_bytes(manifest))
    tampered["seal"]["e5_equivalent"] = True
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=False)
    assert "seal meaning is invalid" in findings


def test_validator_rejects_process_resource_injection(manifest: dict):
    tampered = json.loads(canonical_json_bytes(manifest))
    tampered["items"][0]["conditions"]["on"]["rss_delta_bytes"] = 123456
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=True)
    assert any(
        "process resource telemetry must be omitted" in finding
        for finding in findings
    )


def test_current_verifier_rebinds_scopes_after_replay(
    manifest: dict,
    monkeypatch,
):
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
    findings = receipt.validate_receipt(manifest, require_current=True)
    assert any(
        "scope differs after current semantic replay" in finding
        for finding in findings
    )


def test_validator_rejects_unbound_on_fires_and_forged_replay(manifest: dict):
    tampered = json.loads(canonical_json_bytes(manifest))
    for item in tampered["items"]:
        on = item["conditions"]["on"]
        on["proof_digest_sha256"] = None
        on["provenance_digest_sha256"] = None
        on["evidence_ids"] = []
        on["stage_hit_count"] = 0
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=True)
    assert any(
        "accepted fire lacks" in finding
        or "metrics do not derive" in finding
        or "evidence binding" in finding
        for finding in findings
    )
    assert receipt._derive_metrics(
        tampered["items"],
        tampered["controls"],
        tampered["staging_controls"],
    )[
        "e4_development_gate_passed"
    ] is False

    tampered = json.loads(canonical_json_bytes(manifest))
    tampered["items"][0]["replay"]["on_replay_digest_sha256"] = "0" * 64
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=False)
    assert any(
        "replay ON semantic equality is not derived" in finding
        for finding in findings
    )


def test_off_errors_can_never_pass_the_clean_control_gate(manifest: dict):
    tampered = json.loads(canonical_json_bytes(manifest))
    for item in tampered["items"]:
        off = item["conditions"]["off"]
        off["status"] = "error"
        off["error_kind"] = "InjectedControlFailure"
        off["reason"] = "candidate_error_fail_closed"
        item["off_to_on"] = receipt._transition(
            item["conditions"]["off"],
            item["conditions"]["on"],
        )
    assert receipt._derive_metrics(
        tampered["items"],
        tampered["controls"],
        tampered["staging_controls"],
    )[
        "off_clean_control_all"
    ] is False
    assert receipt._derive_metrics(
        tampered["items"],
        tampered["controls"],
        tampered["staging_controls"],
    )[
        "e4_development_gate_passed"
    ] is False
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=False)
    assert "metrics do not derive from item outcomes" in findings


def test_control_probe_gate_rejects_fires_evidence_errors_and_loader_accepts(
    manifest: dict,
):
    tampered = json.loads(canonical_json_bytes(manifest))
    condition = tampered["controls"][0]["conditions"]["on"]
    condition["raw_fired"] = True
    derived = receipt._derive_metrics(
        tampered["items"],
        tampered["controls"],
        tampered["staging_controls"],
    )
    assert derived["control_probes"]["candidate"]["raw_control_fire"] == 1
    assert derived["control_probes"]["control_probe_gate_passed"] is False

    tampered = json.loads(canonical_json_bytes(manifest))
    condition = tampered["controls"][1]["conditions"]["on"]
    condition["evidence_ids"] = ["injected-evidence"]
    condition["stage_hit_count"] = 1
    derived = receipt._derive_metrics(
        tampered["items"],
        tampered["controls"],
        tampered["staging_controls"],
    )
    assert derived["control_probes"]["candidate"]["evidence_leak"] == 1
    assert derived["e4_development_gate_passed"] is False

    tampered = json.loads(canonical_json_bytes(manifest))
    stage_control = tampered["staging_controls"][0]
    stage_control["loader_accepted"] = True
    stage_control["snapshot_returned"] = True
    stage_control["expected_rejection_observed"] = False
    stage_control["contract_passed"] = False
    derived = receipt._derive_metrics(
        tampered["items"],
        tampered["controls"],
        tampered["staging_controls"],
    )
    assert derived["control_probes"]["staging"]["rejected"] == 1
    assert derived["control_probes"]["control_probe_gate_passed"] is False


def test_verifier_distinguishes_declared_verified_and_current_binding(
    manifest: dict,
    tmp_path,
):
    historical = tmp_path / "historical.json"
    write_manifest_exclusive(historical, manifest)
    report = receipt.verify_receipt(
        historical,
        require_current=False,
    )
    assert report["valid"] is True
    assert report["matches_current"] is None
    assert report["declared_sealed"] is True
    assert report["verified_sealed"] is False
    assert report["sealed"] is False


def test_current_verifier_reexecutes_runtime_semantics_before_sealing(
    manifest: dict,
    tmp_path,
):
    variants = []

    arbitrary_proof = json.loads(canonical_json_bytes(manifest))
    for item in arbitrary_proof["items"]:
        item["conditions"]["on"]["proof_digest_sha256"] = "0" * 64
        item["conditions"]["on"]["provenance_digest_sha256"] = "1" * 64
    variants.append(("arbitrary-proof", arbitrary_proof))

    arbitrary_replay = json.loads(canonical_json_bytes(manifest))
    for item in arbitrary_replay["items"]:
        item["conditions"]["off"][
            "semantic_outcome_digest_sha256"
        ] = "a" * 64
        item["replay"]["off_replay_digest_sha256"] = "a" * 64
        item["conditions"]["on"][
            "semantic_outcome_digest_sha256"
        ] = "b" * 64
        item["replay"]["on_replay_digest_sha256"] = "b" * 64
    variants.append(("arbitrary-replay", arbitrary_replay))

    wrong_order = json.loads(canonical_json_bytes(manifest))
    for item in wrong_order["items"]:
        item["primary_execution_order"] = ["off", "on"]
        item["replay_execution_order"] = ["on", "off"]
    variants.append(("wrong-order", wrong_order))

    off_choice = json.loads(canonical_json_bytes(manifest))
    for item in off_choice["items"]:
        off = item["conditions"]["off"]
        off["choice_key"] = next(
            key
            for key in ("A", "B", "C", "D")
            if key != item["conditions"]["on"]["choice_key"]
        )
        off["choice_digest_sha256"] = receipt._sha256(
            off["choice_key"].encode("utf-8")
        )
    variants.append(("off-choice", off_choice))

    for name, tampered in variants:
        tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
        path = tmp_path / f"{name}.json"
        write_manifest_exclusive(path, tampered)
        report = receipt.verify_receipt(path, require_current=True)
        assert report["valid"] is False, name
        if name != "wrong-order":
            assert report["matches_current"] is False, name
        assert report["declared_sealed"] is True, name
        assert report["verified_sealed"] is False, name
        assert report["sealed"] is False, name
        assert report["findings"], name

    current_mismatch = json.loads(canonical_json_bytes(manifest))
    current_mismatch["selection"][
        "control_input_choice_pairs_sha256"
    ] = "0" * 64
    current_mismatch["manifest_checksum_sha256"] = receipt._checksum(
        current_mismatch
    )
    mismatch_path = tmp_path / "current-mismatch.json"
    write_manifest_exclusive(mismatch_path, current_mismatch)
    report = receipt.verify_receipt(
        mismatch_path,
        require_current=True,
    )
    assert report["structure_valid"] is True
    assert report["matches_current"] is False
    assert report["valid"] is False
    assert report["declared_sealed"] is True
    assert report["verified_sealed"] is False
    assert report["sealed"] is False
