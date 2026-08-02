from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    canonical_json_bytes,
)
from scripts import science_stage_composite_e4_receipt as receipt


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
    "packages/reasoning_vm/deduction.py",
    "packages/reasoning_vm/deliberator/__init__.py",
    "packages/reasoning_vm/deliberator/back_chain.py",
    "packages/reasoning_vm/deliberator/reasoner.py",
    "packages/reasoning_vm/deliberator/science_goal.py",
    "packages/reasoning_vm/deliberator/science_quantity_goal.py",
    "packages/reasoning_vm/deliberator/science_quantity_resolver.py",
    "packages/reasoning_vm/quantity.py",
    "packages/reasoning_vm/scalar_quantity.py",
    "packages/reasoning_vm/science_candidate.py",
    "packages/reasoning_vm/science_exam.py",
    "packages/reasoning_vm/science_quantity_exam.py",
    "packages/reasoning_vm/science_quantity_staging.py",
    "packages/reasoning_vm/science_route.py",
    "packages/reasoning_vm/science_staging.py",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return receipt.build_receipt(repo_root=receipt.REPO)


def _detached(value: dict) -> dict:
    return json.loads(canonical_json_bytes(value))


def _write_canonical(path: Path, value: dict) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _rechecksum(value: dict) -> None:
    value["manifest_checksum_sha256"] = receipt._checksum(value)


def test_composite_contract_uses_real_fixtures_and_exact_candidate_closure(
) -> None:
    assert receipt.SCHEMA_VERSION == (
        "atanor.science-stage-composite-preservation-e4-receipt.v1"
    )
    assert receipt.ATOMIC_FIXTURE_PATH.endswith(
        "science_staging_e4_holdout_v1.json"
    )
    assert receipt.SCALAR_FIXTURE_PATH.endswith(
        "science_scalar_neutralization_e4_v1.json"
    )
    assert set(receipt.CANDIDATE_PATHS) == EXPECTED_CANDIDATE_CLOSURE
    assert len(receipt.CANDIDATE_PATHS) == 27
    assert receipt.CONDITION_IDS == ("O", "A", "S", "B")
    assert receipt.WILLIAMS_SEQUENCES == (
        ("O", "A", "B", "S"),
        ("A", "S", "O", "B"),
        ("S", "B", "A", "O"),
        ("B", "O", "S", "A"),
    )


def test_composite_control_fixture_is_frozen_minimal_and_gold_free() -> None:
    fixture, payload = receipt._fixture(receipt.REPO)
    assert receipt._sha256(payload) == receipt.FROZEN_FIXTURE_SHA256
    assert payload == canonical_json_bytes(fixture) + b"\n"
    assert len(fixture["router_reclassifications"]) == 3
    assert {
        row["control_id"]
        for row in fixture["router_reclassifications"]
    } == {
        "science-e4-negative-unsupported-001",
        "scalar-control-pH",
        "scalar-control-partial",
    }
    assert "gold" not in canonical_json_bytes(fixture).decode("utf-8")


def test_composite_receipt_has_fixed_denominators_and_bound_scopes(
    manifest: dict,
) -> None:
    assert manifest["schema_version"] == receipt.SCHEMA_VERSION
    assert manifest["evidence_kind"] == receipt.EVIDENCE_KIND
    assert len(manifest["items"]) == receipt.EXPECTED_ITEMS == 27
    assert len(manifest["controls"]) == receipt.EXPECTED_CONTROLS == 9
    for name in ("source", "candidate", "dataset", "stage"):
        assert manifest[name]["files"]
        assert len(manifest[name]["content_sha256"]) == 64
        assert all(
            len(row["sha256"]) == 64
            for row in manifest[name]["files"]
        )
    assert {
        row["path"] for row in manifest["candidate"]["files"]
    } == EXPECTED_CANDIDATE_CLOSURE
    assert manifest["manifest_checksum_sha256"] == receipt._checksum(
        manifest
    )


def test_composite_receipt_preserves_all_native_item_semantics(
    manifest: dict,
) -> None:
    preservation = manifest["metrics"]["preservation"]
    assert preservation == {
        "item_legacy_comparisons": 108,
        "item_legacy_semantics_same": 108,
        "native_control_comparisons": 24,
        "native_control_semantics_same": 24,
        "preservation_gate_passed": True,
    }
    for row in manifest["items"]:
        expected = (
            {"O": "off", "A": "on", "S": "off", "B": "on"}
            if row["family"] == "atomic"
            else {"O": "off", "A": "off", "S": "on", "B": "on"}
        )
        for condition_id, legacy_condition in expected.items():
            condition = row["conditions"][condition_id]
            assert condition["expected_legacy_condition"] == legacy_condition
            assert condition["legacy_semantic_outcome_same"] is True
            assert len(
                condition["native_semantic_outcome_digest_sha256"]
            ) == 64
        assert row["replay"]["all_conditions_same"] is True
        assert row["original_mapping_read_count"] == 1
        assert row["gold_absent_from_candidate_arguments"] is True


def test_composite_receipt_separates_capability_from_mechanism(
    manifest: dict,
) -> None:
    metrics = manifest["metrics"]
    capability = metrics["capability"]
    expected_correct = {
        "atomic": {"O": 0, "A": 15, "S": 0, "B": 15},
        "scalar": {"O": 0, "A": 0, "S": 12, "B": 12},
    }
    for family, counts in expected_correct.items():
        for condition_id, correct in counts.items():
            record = capability["by_family"][family][condition_id]
            assert record["n"] == (15 if family == "atomic" else 12)
            assert record["correct"] == correct
            assert record["wrong"] == 0
            assert record["strict_accuracy"] == (
                1.0 if correct == record["n"] else 0.0
            )
    combined = capability["all_items"]
    assert {
        key: combined[key]["correct"] for key in receipt.CONDITION_IDS
    } == {"O": 0, "A": 15, "S": 12, "B": 27}
    assert combined["A"]["strict_accuracy"] == 0.555555555556
    assert combined["S"]["strict_accuracy"] == 0.444444444444

    mechanism = metrics["mechanism"]
    assert mechanism["primary_item_condition_executions"] == 108
    assert mechanism["replay_item_condition_executions"] == 108
    assert mechanism["primary_control_condition_executions"] == 36
    assert mechanism["replay_control_condition_executions"] == 36
    assert mechanism["semantic_replay_comparisons"] == 144
    assert mechanism["semantic_replay_matches"] == 144
    assert mechanism["main_source_mapping_reads"] == 27
    assert mechanism["main_prepared_condition_executions"] == 216
    assert mechanism["control_source_mapping_reads"] == 9
    assert mechanism["control_prepared_condition_executions"] == 72
    assert mechanism["source_mapping_read_once_per_row_all"] is True


def test_composite_receipt_measures_noninterference_not_synergy(
    manifest: dict,
) -> None:
    interaction = manifest["metrics"]["interaction"]
    assert interaction["irrelevant_stage_comparisons"] == 54
    assert interaction["irrelevant_stage_semantics_same"] == 54
    assert interaction["cross_lane_interference_observed"] == 0
    assert interaction["factorial_correct_interaction_zero_count"] == 27
    assert interaction["factorial_correct_interaction_values"] == [0] * 27
    assert interaction["both_matches_legacy_on_count"] == 27
    assert interaction["unselected_stage_passed_count"] == 0
    assert interaction["fallback_attempted_count"] == 0
    assert interaction["interaction_gate_passed"] is True
    for row in manifest["items"]:
        conditions = row["conditions"]
        pairs = (
            (("O", "S"), ("A", "B"))
            if row["family"] == "atomic"
            else (("O", "A"), ("S", "B"))
        )
        for left, right in pairs:
            assert receipt._condition_behavior_digest(
                conditions[left]
            ) == receipt._condition_behavior_digest(conditions[right])
        assert all(
            condition["unselected_stage_passed"] is False
            and condition["fallback_attempted"] is False
            for condition in conditions.values()
        )


def test_composite_williams_order_and_reverse_replay_are_bounded(
    manifest: dict,
) -> None:
    order = manifest["metrics"]["order_balance"]
    assert order["items"]["williams_sequence_counts"] == {
        "W0": 7,
        "W1": 7,
        "W2": 7,
        "W3": 6,
    }
    assert order["items"]["maximum_position_imbalance"] == 1
    assert order["items"]["reverse_replay_exact_all"] is True
    assert order["items"]["counterbalance_gate_passed"] is True
    assert order["controls"]["maximum_position_imbalance"] <= 1
    assert order["controls"]["counterbalance_gate_passed"] is True
    assert order["order_gate_passed"] is True
    for row in (*manifest["items"], *manifest["controls"]):
        assert row["replay_execution_order"] == list(
            reversed(row["primary_execution_order"])
        )


def test_composite_prerequisites_and_controls_are_fresh_and_explicit(
    manifest: dict,
) -> None:
    prerequisites = manifest["prerequisites"]
    assert "no report file is trusted" in prerequisites["scope"]
    assert prerequisites["atomic"]["verified_current"] is True
    assert prerequisites["atomic"]["verified_sealed"] is True
    assert prerequisites["atomic"]["item_count"] == 15
    assert prerequisites["atomic"]["control_count"] == 3
    assert prerequisites["atomic"]["staging_control_count"] == 2
    assert prerequisites["scalar"]["verified_current"] is True
    assert prerequisites["scalar"]["verified_sealed"] is True
    assert prerequisites["scalar"]["item_count"] == 12
    assert prerequisites["scalar"]["control_count"] == 6
    assert prerequisites["scalar"]["staging_control_count"] == 3
    for family in ("atomic", "scalar"):
        for field in (
            "manifest_checksum_sha256",
            "fixture_sha256",
            "stage_digest_sha256",
            "selection_digest_sha256",
            "item_semantics_digest_sha256",
            "control_semantics_digest_sha256",
            "staging_controls_digest_sha256",
        ):
            assert len(prerequisites[family][field]) == 64

    controls = manifest["metrics"]["controls"]
    assert controls["candidate_control_count"] == 9
    assert controls["legacy_native_control_count"] == 6
    assert controls["router_reclassification_control_count"] == 3
    assert controls["router_reclassification_condition_comparisons"] == 12
    assert controls["candidate_controls_passed"] == 9
    assert controls["staging_control_count"] == 5
    assert (
        controls["prerequisite_staging_controls_digest_bound"] is True
    )
    assert controls["control_probe_gate_passed"] is True
    assert all(row["contract_passed"] for row in manifest["controls"])
    assert sum(
        row["expectation_kind"] == "router_reclassification"
        for row in manifest["controls"]
    ) == 3
    assert receipt._sha256(
        canonical_json_bytes([row["item_id"] for row in manifest["items"]])
    ) == receipt.EXPECTED_ITEM_IDS_SHA256
    assert receipt._sha256(
        canonical_json_bytes(
            [row["control_id"] for row in manifest["controls"]]
        )
    ) == receipt.EXPECTED_CONTROL_IDS_SHA256
    reclassified = [
        row
        for row in manifest["controls"]
        if row["expectation_kind"] == "router_reclassification"
    ]
    assert {
        (row["family"], row["control_id"]) for row in reclassified
    } == receipt.RECLASSIFICATION_CONTROLS
    for row in reclassified:
        for condition in row["conditions"].values():
            assert condition["compiled"] is False
            assert condition["raw_fired"] is False
            assert condition["accepted_fire"] is False
            assert condition["grounded"] is False
    for family in ("atomic", "scalar"):
        assert prerequisites[family]["benchmark_capability_claimed"] is False
        assert prerequisites[family]["e5_claimed"] is False
        assert prerequisites[family]["independent"] is False
        assert (
            prerequisites[family]["external_authenticity_established"]
            is False
        )
        assert prerequisites[family]["resource_curve_established"] is False


def test_composite_development_seal_does_not_claim_public_capability(
    manifest: dict,
) -> None:
    gates = manifest["metrics"]["gates"]
    assert gates == {
        "prerequisite_gate_passed": True,
        "mechanism_gate_passed": True,
        "replay_gate_passed": True,
        "preservation_gate_passed": True,
        "interaction_gate_passed": True,
        "control_probe_gate_passed": True,
        "order_gate_passed": True,
        "composite_e4_development_gate_passed": True,
        "public_capability_gate_passed": False,
        "public_capability_gate_evaluated": False,
    }
    claims = manifest["claims"]
    assert claims["e4_development_gate_passed"] is True
    assert claims["mechanism_evidence"] is True
    assert claims["mechanism_gate_passed"] is True
    assert claims["preservation_gate_passed"] is True
    assert claims["interaction_gate_passed"] is True
    assert claims["control_probe_gate_passed"] is True
    for field in (
        "public_capability_gate_evaluated",
        "public_capability_gate_passed",
        "e5_claimed",
        "independent",
        "externally_signed",
        "hidden_holdout_claimed",
        "external_authenticity_established",
        "benchmark_capability_claimed",
        "process_resource_curve_claimed",
        "coordinated_stage_rewrite_resistance_claimed",
        "shipped_graph_immutability_claimed",
        "shipped_graph_write_authority",
        "production_authority",
    ):
        assert claims[field] is False
    seal = manifest["seal"]
    assert seal["sealed"] is True
    for field in (
        "hidden_holdout_claimed",
        "independent_evaluation_claimed",
        "authenticity_established",
        "public_capability_established",
        "coordinated_stage_rewrite_resistance_claimed",
        "shipped_graph_immutability_claimed",
        "resource_curve_established",
        "e5_equivalent",
    ):
        assert seal[field] is False
    inference = manifest["metrics"]["inference"]
    assert inference["development_preservation_interaction_only"] is True
    assert all(
        inference[field] is False
        for field in (
            "independent_evaluation",
            "hidden_holdout",
            "external_authenticity",
            "public_capability_inference",
            "e5_inference",
            "resource_curve_inference",
        )
    )


def test_composite_integrity_binds_exact_fresh_candidate_closure(
    manifest: dict,
) -> None:
    integrity = manifest["integrity"]
    assert integrity[
        "fresh_process_candidate_closure_expected_path_count"
    ] == 27
    assert integrity[
        "fresh_process_candidate_closure_actual_path_count"
    ] == 27
    assert integrity["fresh_process_candidate_closure_exact"] is True
    assert len(
        integrity["fresh_process_candidate_closure_paths_sha256"]
    ) == 64
    assert integrity["candidate_prepared_once_per_row"] is True
    assert integrity["main_source_mapping_reads"] == 27
    assert integrity["main_prepared_condition_executions"] == 216
    assert integrity["control_source_mapping_reads"] == 9
    assert integrity["control_prepared_condition_executions"] == 72
    assert integrity["selected_lane_only_all"] is True
    assert integrity["fallback_attempted_count"] == 0
    assert integrity["process_resource_telemetry_omitted"] is True


def test_composite_receipt_validates_without_current_replay(
    manifest: dict,
) -> None:
    assert receipt.validate_receipt(
        manifest,
        repo_root=receipt.REPO,
        require_current=False,
    ) == []


def test_composite_receipt_canonical_write_once_and_current_verification(
    tmp_path: Path,
    manifest: dict,
) -> None:
    path = tmp_path / "composite-receipt.json"
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
        "valid": True,
        "structure_valid": True,
        "matches_current": True,
        "declared_sealed": True,
        "verified_sealed": True,
        "sealed": True,
        "e5_claimed": False,
        "public_capability_gate_passed": False,
        "checksum_sha256": manifest["manifest_checksum_sha256"],
        "source_matches_current": True,
        "candidate_matches_current": True,
        "dataset_matches_current": True,
        "stage_matches_current": True,
        "prerequisite_matches_current": True,
        "findings": [],
    }
    with pytest.raises(BenchmarkEvidenceError, match="already exists"):
        receipt.write_receipt_exclusive(
            path,
            manifest,
            repo_root=receipt.REPO,
        )


def test_composite_receipt_without_current_replay_is_not_verified_sealed(
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
    assert report == {
        "valid": True,
        "structure_valid": True,
        "matches_current": None,
        "declared_sealed": True,
        "verified_sealed": False,
        "sealed": False,
        "e5_claimed": False,
        "public_capability_gate_passed": False,
        "checksum_sha256": manifest["manifest_checksum_sha256"],
        "source_matches_current": None,
        "candidate_matches_current": None,
        "dataset_matches_current": None,
        "stage_matches_current": None,
        "prerequisite_matches_current": None,
        "findings": [],
    }


@pytest.mark.parametrize(
    "variant",
    (
        "authority",
        "result",
        "order",
        "prerequisite",
        "resource",
        "scope",
        "replay",
    ),
)
def test_composite_verifier_rejects_rechecksummed_nested_tampering(
    tmp_path: Path,
    manifest: dict,
    variant: str,
) -> None:
    tampered = _detached(manifest)
    if variant == "authority":
        tampered["claims"]["independent"] = True
    elif variant == "result":
        tampered["items"][0]["conditions"]["B"]["accepted_fire"] = False
    elif variant == "order":
        tampered["items"][0]["primary_execution_order"] = [
            "A",
            "O",
            "B",
            "S",
        ]
    elif variant == "prerequisite":
        tampered["prerequisites"]["atomic"][
            "manifest_checksum_sha256"
        ] = "0" * 64
    elif variant == "resource":
        tampered["resources"] = {"rss_delta_bytes": 1}
    elif variant == "scope":
        tampered["candidate"]["files"][0]["sha256"] = "0" * 64
        tampered["candidate"]["content_sha256"] = receipt._sha256(
            canonical_json_bytes(tampered["candidate"]["files"])
        )
    elif variant == "replay":
        tampered["items"][0]["replay"]["conditions"]["B"][
            "replay_digest_sha256"
        ] = "0" * 64
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


def test_composite_verifier_fails_closed_on_malformed_seal(
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


def test_composite_verifier_rejects_noncanonical_receipt_bytes(
    tmp_path: Path,
    manifest: dict,
) -> None:
    path = tmp_path / "pretty.json"
    path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkEvidenceError, match="not canonical"):
        receipt.read_receipt(path)
    report = receipt.verify_receipt(path, repo_root=receipt.REPO)
    assert report["valid"] is False
    assert report["structure_valid"] is False
    assert report["sealed"] is False
    assert report["findings"] == [
        "composite receipt is not canonical JSON with one newline"
    ]


def test_composite_verifier_rebinds_scopes_after_current_replay(
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
    assert all(
        report[f"{name}_matches_current"] is False
        for name in ("source", "candidate", "dataset", "stage")
    )
    assert any(
        "scope differs after current semantic replay" in finding
        for finding in report["findings"]
    )


def test_composite_builder_rebinds_scopes_across_fresh_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = receipt._bind_scopes
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
        "_bind_scopes",
        changes_after_worker,
    )
    with pytest.raises(
        BenchmarkEvidenceError,
        match="bound bytes changed across fresh composite worker: stage",
    ):
        receipt.build_receipt(repo_root=receipt.REPO)
