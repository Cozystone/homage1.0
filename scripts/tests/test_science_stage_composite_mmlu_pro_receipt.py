from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    canonical_json_bytes,
)
from scripts import science_stage_composite_mmlu_pro_receipt as receipt


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

EXPECTED_PREREQUISITE_FIXTURES = {
    "packages/reasoning_vm/tests/fixtures/"
    "science_composite_controls_e4_v1.json",
    "packages/reasoning_vm/tests/fixtures/"
    "science_scalar_neutralization_e4_v1.json",
    "packages/reasoning_vm/tests/fixtures/"
    "science_staging_e4_holdout_v1.json",
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


def _redigest_summary(value: dict) -> None:
    core = dict(value)
    core.pop("summary_digest_sha256", None)
    value["summary_digest_sha256"] = receipt._sha256(
        canonical_json_bytes(core)
    )


def test_contract_binds_exact_public_dataset_and_complete_scopes(
    manifest: dict,
) -> None:
    assert receipt.SCHEMA_VERSION == (
        "atanor.science-stage-composite-mmlu-pro-exposed-receipt.v1"
    )
    assert manifest["schema_version"] == receipt.SCHEMA_VERSION
    assert manifest["evidence_kind"] == receipt.EVIDENCE_KIND
    assert manifest["manifest_checksum_sha256"] == receipt._checksum(
        manifest
    )
    assert manifest["selection"]["expected_item_count"] == 40
    assert manifest["selection"]["actual_dataset_sha256"] == (
        receipt.EXPECTED_DATASET_SHA256
    )
    assert manifest["selection"]["item_ids_sha256"] == (
        receipt.EXPECTED_ITEM_IDS_SHA256
    )
    assert manifest["selection"]["input_choice_pairs_sha256"] == (
        "1b2dcb477752398153c2a9d9a9151baaacea0acdcbe9d712793b439bbbb4c69b"
    )
    assert manifest["selection"]["category_counts"] == {
        category: 5 for category in receipt.CATEGORIES
    }
    assert {
        row["path"] for row in manifest["dataset"]["files"]
    } == {receipt.DATASET_PATH}
    assert set(receipt.CANDIDATE_PATHS) == EXPECTED_CANDIDATE_CLOSURE
    assert {
        row["path"] for row in manifest["candidate"]["files"]
    } == EXPECTED_CANDIDATE_CLOSURE
    assert set(receipt.PREREQUISITE_FIXTURE_PATHS) == (
        EXPECTED_PREREQUISITE_FIXTURES
    )
    assert {
        row["path"]
        for row in manifest["prerequisite_fixtures"]["files"]
    } == EXPECTED_PREREQUISITE_FIXTURES
    for name in (
        "source",
        "candidate",
        "dataset",
        "prerequisite_fixtures",
        "stage",
    ):
        assert receipt._scope_paths(manifest[name])


def test_route_census_is_separate_from_compilation_and_exact(
    manifest: dict,
) -> None:
    assert len(manifest["items"]) == receipt.EXPECTED_ITEMS == 40
    assert manifest["selection"]["route_distribution"] == (
        receipt.EXPECTED_ROUTE_DISTRIBUTION
    )
    mechanism = manifest["metrics"]["mechanism"]
    assert mechanism["route_distribution"] == (
        receipt.EXPECTED_ROUTE_DISTRIBUTION
    )
    assert mechanism["strict_route_distribution_passed"] is True
    assert mechanism["selected_item_count"] == 1
    assert mechanism["selected_primary_condition_executions"] == 4
    assert mechanism["compiled_primary_condition_executions"] == 4

    selected = manifest["items"][receipt.TARGET_ORDINAL]
    assert selected["ordinal"] == 7
    assert selected["category"] == "chemistry"
    assert selected["route_status"] == "selected"
    assert selected["route_lane"] == "scalar"
    assert selected["route_reason"] == "scalar_profile_selected"
    assert selected["post_hoc_targeted_item"] is True

    unsupported = [
        row for row in manifest["items"] if row["route_status"] == "unsupported"
    ]
    assert len(unsupported) == 39
    assert all(row["route_lane"] is None for row in unsupported)
    assert all(
        row["route_reason"] == "unsupported_science_profile"
        for row in unsupported
    )


def test_four_condition_curve_is_exact_and_not_a_capability_gate(
    manifest: dict,
) -> None:
    overall = manifest["metrics"]["capability"]["overall"]
    for condition_id in receipt.CONDITION_IDS:
        row = overall[condition_id]
        expected_fire = 1 if condition_id in {"S", "B"} else 0
        assert row["n"] == 40
        assert row["selected_routes"] == 1
        assert row["unsupported_routes"] == 39
        assert row["compiled"] == 1
        assert row["correct"] == expected_fire
        assert row["raw_fired"] == expected_fire
        assert row["formula_fired"] == expected_fire
        assert row["resolver_grounded"] == expected_fire
        assert row["proof_replayed"] == expected_fire
        assert row["accepted_fired"] == expected_fire
        assert row["grounded"] == expected_fire
        assert row["wrong_fire"] == 0
        assert row["error"] == 0
        assert row["abstain"] == 40 - expected_fire
        assert row["strict_accuracy"] == (
            0.025 if expected_fire else 0.0
        )
        assert row["answered_accuracy"] == (
            1.0 if expected_fire else None
        )
        assert row["strict_accuracy_exact_binomial_95_ci"] == (
            [0.000632744932, 0.131585858483]
            if expected_fire
            else [0.0, 0.088097302879]
        )

    gates = manifest["metrics"]["gates"]
    assert gates[
        "composite_public_development_measurement_protocol_gate_passed"
    ] is True
    assert gates["public_capability_gate_evaluated"] is False
    assert gates["public_capability_gate_passed"] is False
    assert gates["e5_gate_evaluated"] is False
    assert gates["e5_gate_passed"] is False
    assert "no capability threshold" in manifest["protocol"][
        "measurement_protocol_gate_meaning"
    ]


def test_descriptive_contrasts_and_category_curve_are_exact(
    manifest: dict,
) -> None:
    contrasts = manifest["metrics"]["capability"]["contrasts"]
    for name in ("O_to_A", "S_to_B"):
        assert contrasts[name]["strict_accuracy_delta"] == 0.0
        assert contrasts[name]["discordant_pairs"] == 0
        assert contrasts[name]["exact_two_sided_mcnemar_p"] == 1.0
    for name in ("O_to_S", "O_to_B", "A_to_B"):
        assert contrasts[name]["strict_accuracy_delta"] == 0.025
        assert contrasts[name]["left_correct_right_incorrect"] == 0
        assert contrasts[name]["left_incorrect_right_correct"] == 1
        assert contrasts[name]["discordant_pairs"] == 1
        assert contrasts[name]["exact_two_sided_mcnemar_p"] == 1.0

    chemistry = manifest["metrics"]["capability"]["categories"][
        "chemistry"
    ]
    assert chemistry["O"]["correct"] == chemistry["A"]["correct"] == 0
    assert chemistry["S"]["correct"] == chemistry["B"]["correct"] == 1
    assert chemistry["S"]["strict_accuracy"] == 0.2
    assert chemistry["B"]["strict_accuracy"] == 0.2
    for category in set(receipt.CATEGORIES) - {"chemistry"}:
        rows = manifest["metrics"]["capability"]["categories"][category]
        assert all(rows[condition_id]["correct"] == 0 for condition_id in rows)
        assert all(
            rows[condition_id]["selected_routes"] == 0
            for condition_id in rows
        )


def test_prepare_once_williams_reverse_and_replay_are_exact(
    manifest: dict,
) -> None:
    mechanism = manifest["metrics"]["mechanism"]
    assert mechanism["prepared_row_count"] == 40
    assert mechanism["source_mapping_reads"] == 40
    assert mechanism["source_mapping_read_once_per_row_all"] is True
    assert mechanism["prepared_condition_executions"] == 320
    assert mechanism["primary_condition_executions"] == 160
    assert mechanism["replay_condition_executions"] == 160
    assert mechanism["primary_routes_revalidated"] == 160
    assert mechanism["semantic_replay_comparisons"] == 160
    assert mechanism["semantic_replay_matches"] == 160
    assert mechanism["condition_routes_match_prepared_all"] is True
    assert mechanism["mechanism_gate_passed"] is True

    order = manifest["metrics"]["order_balance"]
    assert order["williams_sequence_counts"] == {
        "W0": 10,
        "W1": 10,
        "W2": 10,
        "W3": 10,
    }
    assert order["maximum_position_imbalance"] == 0
    assert order["maximum_directed_carryover_imbalance"] == 0
    assert order["reverse_replay_exact_all"] is True
    assert order["counterbalance_gate_passed"] is True

    for index, row in enumerate(manifest["items"]):
        expected_order = list(receipt.WILLIAMS_SEQUENCES[index % 4])
        assert row["original_mapping_read_count"] == 1
        assert row["williams_sequence_id"] == f"W{index % 4}"
        assert row["primary_execution_order"] == expected_order
        assert row["replay_execution_order"] == list(
            reversed(expected_order)
        )
        assert row["replay"]["all_conditions_same"] is True
        assert all(
            replay["semantic_outcome_same"] is True
            and replay["native_semantic_outcome_same"] is True
            for replay in row["replay"]["conditions"].values()
        )


def test_candidate_boundary_and_condition_routes_are_exact(
    manifest: dict,
) -> None:
    for row in manifest["items"]:
        assert row["gold_absent_from_candidate_arguments"] is True
        assert (
            row["evaluator_metadata_absent_from_candidate_arguments"] is True
        )
        for condition_id, condition in row["conditions"].items():
            assert condition["condition_id"] == condition_id
            assert condition["route_status"] == row["route_status"]
            assert condition["route_lane"] == row["route_lane"]
            assert condition["route_reason"] == row["route_reason"]
            assert condition["route_revalidated"] is True
            assert condition["original_mapping_read_count"] == 1
            assert condition["unselected_stage_passed"] is False
            assert condition["fallback_attempted"] is False
            assert condition["error_kind"] is None
            assert condition["wrong_fire"] is False
    mechanism = manifest["metrics"]["mechanism"]
    assert mechanism["gold_absent_from_candidate_arguments_all"] is True
    assert (
        mechanism["evaluator_metadata_absent_from_candidate_arguments_all"]
        is True
    )
    assert mechanism["error_primary_condition_executions"] == 0


def test_scalar_native_mapping_and_noninterference_are_bounded(
    manifest: dict,
) -> None:
    target = manifest["items"][receipt.TARGET_ORDINAL]
    scalar_reference = manifest["prerequisites"]["scalar_public"][
        "selected_item"
    ]
    for condition_id in ("O", "A"):
        condition = target["conditions"][condition_id]
        assert condition["expected_native_condition"] == "off"
        assert condition["native_semantic_outcome_digest_sha256"] == (
            scalar_reference["off_semantic_outcome_digest_sha256"]
        )
        assert condition["native_semantic_preservation_same"] is True
        assert condition["status"] == "abstain"
    for condition_id in ("S", "B"):
        condition = target["conditions"][condition_id]
        assert condition["expected_native_condition"] == "on"
        assert condition["native_semantic_outcome_digest_sha256"] == (
            scalar_reference["on_semantic_outcome_digest_sha256"]
        )
        assert condition["native_semantic_preservation_same"] is True
        assert condition["status"] == "correct"
        assert condition["evidence_ids"] == list(
            receipt.TARGET_EVIDENCE_IDS
        )

    preservation = manifest["metrics"]["preservation"]
    assert preservation == {
        "atomic_native_mapping_evaluated": False,
        "atomic_native_mapping_denominator": 0,
        "scalar_selected_item_count": 1,
        "scalar_native_comparisons": 4,
        "scalar_native_semantics_same": 4,
        "scalar_O_A_map_to_leaf_off": True,
        "scalar_S_B_map_to_leaf_on": True,
        "preservation_gate_passed": True,
    }
    interaction = manifest["metrics"]["interaction"]
    assert interaction["atomic_stage_irrelevance_comparisons"] == 80
    assert interaction["atomic_stage_irrelevance_matches"] == 80
    assert interaction["unsupported_all_stage_invariance_comparisons"] == 117
    assert interaction["unsupported_all_stage_invariance_matches"] == 117
    assert interaction["factorial_correct_interaction_values"] == [0] * 40
    assert interaction["factorial_correct_interaction_zero_count"] == 40
    assert interaction["unselected_stage_passed_count"] == 0
    assert interaction["fallback_attempted_count"] == 0
    assert interaction["noninterference_gate_passed"] is True


def test_unsupported_rows_are_fail_closed_in_all_conditions(
    manifest: dict,
) -> None:
    unsupported = [
        row for row in manifest["items"] if row["route_status"] == "unsupported"
    ]
    assert len(unsupported) == 39
    for row in unsupported:
        for condition in row["conditions"].values():
            assert condition["status"] == "abstain"
            assert condition["choice_key"] is None
            assert condition["native_semantic_outcome_digest_sha256"] is None
            assert condition["expected_native_condition"] is None
            assert (
                condition[
                    "expected_native_semantic_outcome_digest_sha256"
                ]
                is None
            )
            assert condition["native_semantic_preservation_same"] is None
            assert condition["proof_digest_sha256"] is None
            assert condition["provenance_digest_sha256"] is None
            assert condition["stage_digest_sha256"] is None
            assert condition["evidence_ids"] == []
            assert condition["grounded_leaf_count"] == 0
            assert condition["grounded_stage_leaf_count"] == 0
            assert condition["reason"] == "unsupported_science_profile"
            for field in (
                "compiled",
                "raw_fired",
                "formula_fired",
                "resolver_grounded",
                "proof_replayed",
                "accepted_fire",
                "grounded",
                "provenance_bound",
                "lane_entered",
                "selected_stage_passed",
                "unselected_stage_passed",
                "fallback_attempted",
            ):
                assert condition[field] is False


def test_three_fresh_prerequisites_bind_identity_semantics_and_limits(
    manifest: dict,
) -> None:
    prerequisites = manifest["prerequisites"]
    assert "no report file is trusted" in prerequisites["scope"]
    assert set(prerequisites) == {
        "scope",
        "composite_e4",
        "atomic_public",
        "scalar_public",
    }
    for name in ("composite_e4", "atomic_public", "scalar_public"):
        summary = prerequisites[name]
        assert receipt._summary_digest_valid(summary)
        assert summary["verified_current"] is True
        assert summary["verified_sealed"] is True
        assert summary["e5_claimed"] is False
        assert summary["independent"] is False
        assert summary["external_authenticity_established"] is False
        assert summary["process_resource_curve_claimed"] is False
        assert summary["resource_curve_established"] is False
        assert len(summary["manifest_checksum_sha256"]) == 64

    composite = prerequisites["composite_e4"]
    assert composite["development_gate_passed"] is True
    assert composite["candidate_closure_path_count"] == 27
    assert composite["candidate_closure_exact"] is True
    assert composite["public_capability_gate_evaluated"] is False
    assert composite["public_capability_gate_passed"] is False

    atomic = prerequisites["atomic_public"]
    scalar = prerequisites["scalar_public"]
    assert atomic["dataset_sha256"] == scalar["dataset_sha256"] == (
        receipt.EXPECTED_DATASET_SHA256
    )
    assert atomic["item_count"] == scalar["item_count"] == 40
    assert atomic["off_correct"] == atomic["on_correct"] == 0
    assert scalar["off_correct"] == 0
    assert scalar["on_correct"] == 1
    assert atomic["benchmark_capability_claimed"] is False
    assert scalar["benchmark_capability_claimed"] is False
    assert scalar["post_hoc_targeting_disclosed"] is True
    assert scalar["unbiased_generalization_claimed"] is False
    assert scalar[
        "targeted_partial_inconsistency_control_passed"
    ] is True
    assert manifest["adaptation_disclosure"] == (
        receipt.scalar_public._adaptation_disclosure()
    )


def test_development_seal_never_promotes_public_capability_or_e5(
    manifest: dict,
) -> None:
    gates = manifest["metrics"]["gates"]
    for field in (
        "prerequisite_gate_passed",
        "route_distribution_gate_passed",
        "mechanism_gate_passed",
        "replay_gate_passed",
        "preservation_gate_passed",
        "noninterference_gate_passed",
        "zero_wrong_fire_gate_passed",
        "zero_condition_error_gate_passed",
        "candidate_boundary_gate_passed",
        "targeted_observation_gate_passed",
        "order_gate_passed",
        "composite_public_development_measurement_protocol_gate_passed",
    ):
        assert gates[field] is True
    for field in (
        "public_capability_gate_evaluated",
        "public_capability_gate_passed",
        "e5_gate_evaluated",
        "e5_gate_passed",
    ):
        assert gates[field] is False

    claims = manifest["claims"]
    assert claims["development_only"] is True
    assert claims["exposed_slice"] is True
    assert claims["post_hoc_targeting_disclosed"] is True
    assert claims[
        "composite_public_development_measurement_protocol_gate_passed"
    ] is True
    assert claims["atomic_native_mapping_evaluated"] is False
    for field in (
        "public_capability_gate_evaluated",
        "public_capability_gate_passed",
        "public_capability_evidence",
        "e5_gate_evaluated",
        "e5_gate_passed",
        "e5_claimed",
        "e5_equivalent",
        "independent",
        "independent_evaluation_claimed",
        "externally_signed",
        "hidden_holdout_claimed",
        "external_authenticity_established",
        "unbiased_generalization_claimed",
        "benchmark_capability_claimed",
        "process_resource_curve_claimed",
        "resource_curve_established",
        "synergy_claimed",
        "generalization_claimed",
        "firing_only_progress_claimed",
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
        "unbiased_generalization_established",
        "public_capability_established",
        "benchmark_capability_established",
        "coordinated_stage_rewrite_resistance_claimed",
        "shipped_graph_immutability_claimed",
        "resource_curve_established",
        "e5_equivalent",
    ):
        assert seal[field] is False
    assert "resources" not in manifest
    assert "environment" not in manifest
    assert "started_at" not in manifest
    assert "completed_at" not in manifest


def test_integrity_and_structure_validate_exactly(
    manifest: dict,
) -> None:
    assert receipt.validate_receipt(
        manifest,
        repo_root=receipt.REPO,
        require_current=False,
    ) == []
    integrity = manifest["integrity"]
    assert integrity["candidate_prepared_once_per_row"] is True
    assert integrity["prepared_row_count"] == 40
    assert integrity["source_mapping_reads"] == 40
    assert integrity["prepared_condition_executions"] == 320
    assert integrity["primary_condition_executions"] == 160
    assert integrity["replay_condition_executions"] == 160
    assert integrity["condition_routes_match_prepared_all"] is True
    assert integrity["semantic_replay_all"] is True
    assert integrity["strict_route_distribution_exact"] is True
    assert integrity["scalar_native_semantic_preservation_all"] is True
    assert integrity["atomic_native_mapping_evaluated"] is False
    assert integrity["atomic_native_mapping_denominator"] == 0
    assert integrity["prerequisite_fixture_union_exact"] is True
    assert integrity[
        "fresh_process_candidate_closure_expected_path_count"
    ] == 27
    assert integrity[
        "fresh_process_candidate_closure_actual_path_count"
    ] == 27
    assert integrity["fresh_process_candidate_closure_exact"] is True
    assert integrity["process_resource_telemetry_omitted"] is True


@pytest.mark.parametrize(
    "variant",
    (
        "mapping",
        "condition_route",
        "error",
        "gold",
        "evaluator_boundary",
        "native_digest",
        "target_choice",
        "proof_binding",
        "stage_binding",
        "leaf_count",
        "formula_flag",
        "unsupported_internal_evidence",
        "prerequisite",
        "metrics",
        "selection",
        "closure",
        "stage_snapshot",
        "authority",
        "resource",
        "fixture_scope",
    ),
)
def test_rechecksummed_tampering_fails_closed(
    manifest: dict,
    variant: str,
) -> None:
    tampered = _detached(manifest)
    require_current = False
    if variant == "mapping":
        tampered["items"][0]["original_mapping_read_count"] = 2
    elif variant == "condition_route":
        tampered["items"][0]["conditions"]["O"]["route_status"] = "selected"
    elif variant == "error":
        tampered["items"][0]["conditions"]["O"]["error_kind"] = "Injected"
    elif variant == "gold":
        tampered["items"][0]["gold"] = "A"
    elif variant == "evaluator_boundary":
        tampered["items"][0][
            "evaluator_metadata_absent_from_candidate_arguments"
        ] = False
    elif variant == "native_digest":
        tampered["items"][receipt.TARGET_ORDINAL]["conditions"]["B"][
            "native_semantic_outcome_digest_sha256"
        ] = "0" * 64
    elif variant == "target_choice":
        condition = tampered["items"][receipt.TARGET_ORDINAL][
            "conditions"
        ]["S"]
        condition["choice_key"] = next(
            key
            for key in "ABCDEFGHIJ"
            if key != condition["choice_key"]
        )
    elif variant == "proof_binding":
        tampered["items"][receipt.TARGET_ORDINAL]["conditions"]["S"][
            "proof_digest_sha256"
        ] = "0" * 64
    elif variant == "stage_binding":
        tampered["items"][receipt.TARGET_ORDINAL]["conditions"]["S"][
            "stage_digest_sha256"
        ] = "0" * 64
    elif variant == "leaf_count":
        condition = tampered["items"][receipt.TARGET_ORDINAL][
            "conditions"
        ]["S"]
        condition["grounded_leaf_count"] += 1
    elif variant == "formula_flag":
        tampered["items"][receipt.TARGET_ORDINAL]["conditions"]["S"][
            "formula_fired"
        ] = False
    elif variant == "unsupported_internal_evidence":
        condition = tampered["items"][0]["conditions"]["O"]
        condition["proof_digest_sha256"] = "0" * 64
        condition["provenance_digest_sha256"] = "1" * 64
        condition["stage_digest_sha256"] = "2" * 64
        condition["grounded_leaf_count"] = 999
        condition["grounded_stage_leaf_count"] = 999
        condition["reason"] = "forged_unsupported_evidence"
    elif variant == "prerequisite":
        summary = tampered["prerequisites"]["scalar_public"]
        summary["e5_claimed"] = True
        _redigest_summary(summary)
    elif variant == "metrics":
        tampered["metrics"]["capability"]["overall"]["B"][
            "strict_accuracy"
        ] = 0.0
    elif variant == "selection":
        tampered["selection"]["route_distribution"]["unsupported"] = 40
    elif variant == "closure":
        tampered["integrity"][
            "fresh_process_candidate_closure_paths_sha256"
        ] = "0" * 64
    elif variant == "stage_snapshot":
        tampered["stage_snapshots"]["scalar"][
            "stage_digest_sha256"
        ] = "0" * 64
    elif variant == "authority":
        tampered["claims"]["public_capability_gate_passed"] = True
    elif variant == "resource":
        tampered["resources"] = {"rss_delta_bytes": 1}
    elif variant == "fixture_scope":
        scope = tampered["prerequisite_fixtures"]
        scope["files"][0]["sha256"] = "0" * 64
        scope["content_sha256"] = receipt._sha256(
            canonical_json_bytes(scope["files"])
        )
        require_current = True
    _rechecksum(tampered)
    findings = receipt.validate_receipt(
        tampered,
        repo_root=receipt.REPO,
        require_current=require_current,
    )
    assert findings, variant


@pytest.mark.parametrize(
    ("section", "replacement"),
    (
        ("items", [None] * 40),
        ("prerequisites", []),
        ("metrics", []),
        ("seal", []),
    ),
)
def test_malformed_nested_roots_fail_closed_without_exceptions(
    tmp_path: Path,
    manifest: dict,
    section: str,
    replacement: object,
) -> None:
    malformed = _detached(manifest)
    malformed[section] = replacement
    _rechecksum(malformed)
    findings = receipt.validate_receipt(
        malformed,
        repo_root=receipt.REPO,
        require_current=False,
    )
    assert findings

    path = tmp_path / f"malformed-{section}.json"
    _write_canonical(path, malformed)
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=False,
    )
    assert report["valid"] is False
    assert report["structure_valid"] is False
    assert report["verified_sealed"] is False
    assert report["sealed"] is False
    assert report["findings"]


def test_rechecksummed_opaque_semantic_digest_requires_current_replay(
    tmp_path: Path,
    manifest: dict,
) -> None:
    tampered = _detached(manifest)
    forged_digest = "0" * 64
    tampered["items"][0]["conditions"]["O"][
        "routed_semantic_outcome_digest_sha256"
    ] = forged_digest
    tampered["items"][0]["replay"]["conditions"]["O"][
        "replay_digest_sha256"
    ] = forged_digest
    _rechecksum(tampered)
    assert receipt.validate_receipt(tampered) == []
    path = tmp_path / "semantic-tamper.json"
    _write_canonical(path, tampered)
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=True,
    )
    assert report["valid"] is False
    assert report["matches_current"] is False
    assert report["verified_sealed"] is False
    assert report["sealed"] is False
    assert any(
        "current deterministic payload mismatch" in finding
        for finding in report["findings"]
    )


def test_canonical_write_once_and_current_verification(
    tmp_path: Path,
    manifest: dict,
) -> None:
    path = tmp_path / "composite-public.json"
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
        "e5_gate_passed": False,
        "public_capability_gate_passed": False,
        "checksum_sha256": manifest["manifest_checksum_sha256"],
        "source_matches_current": True,
        "candidate_matches_current": True,
        "dataset_matches_current": True,
        "prerequisite_fixtures_matches_current": True,
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


def test_historical_structure_never_becomes_verified_seal(
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
        "e5_gate_passed": False,
        "public_capability_gate_passed": False,
        "checksum_sha256": manifest["manifest_checksum_sha256"],
        "source_matches_current": None,
        "candidate_matches_current": None,
        "dataset_matches_current": None,
        "prerequisite_fixtures_matches_current": None,
        "stage_matches_current": None,
        "prerequisite_matches_current": None,
        "findings": [],
    }


def test_reader_and_verifier_reject_noncanonical_receipt(
    tmp_path: Path,
    manifest: dict,
) -> None:
    path = tmp_path / "pretty.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(BenchmarkEvidenceError, match="not canonical"):
        receipt.read_receipt(path)
    report = receipt.verify_receipt(path, repo_root=receipt.REPO)
    assert report["valid"] is False
    assert report["structure_valid"] is False
    assert report["sealed"] is False
    assert report["findings"] == [
        "composite public receipt is not canonical JSON with one newline"
    ]


def test_verifier_rebinds_every_scope_after_current_replay(
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
        return calls <= 5 and original(scope, repo_root)

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
    assert report["matches_current"] is False
    assert report["sealed"] is False
    assert all(
        report[f"{name}_matches_current"] is False
        for name in ("source", "candidate", "dataset", "stage")
    )
    assert report["prerequisite_fixtures_matches_current"] is False
    assert any(
        "scope differs after current replay" in finding
        for finding in report["findings"]
    )


def test_builder_rebinds_scopes_across_fresh_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = receipt._bind_scopes
    calls = 0

    def changes_after_worker(repo_root):
        nonlocal calls
        calls += 1
        scopes = original(repo_root)
        if calls == 2:
            scopes["prerequisite_fixtures"] = _detached(
                scopes["prerequisite_fixtures"]
            )
            scopes["prerequisite_fixtures"]["content_sha256"] = "0" * 64
        return scopes

    monkeypatch.setattr(receipt, "_bind_scopes", changes_after_worker)
    with pytest.raises(
        BenchmarkEvidenceError,
        match=(
            "bound bytes changed across fresh composite public worker: "
            "prerequisite_fixtures"
        ),
    ):
        receipt.build_receipt(repo_root=receipt.REPO)
