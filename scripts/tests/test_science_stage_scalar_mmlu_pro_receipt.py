from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    canonical_json_bytes,
)
from scripts import science_stage_scalar_mmlu_pro_receipt as receipt


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
    value.pop("manifest_checksum_sha256", None)
    value["manifest_checksum_sha256"] = receipt._checksum(value)
    return value


def _detached(value: dict) -> dict:
    return json.loads(canonical_json_bytes(value))


def _redigest_nested(value: dict, digest_field: str) -> None:
    core = dict(value)
    core.pop(digest_field, None)
    value[digest_field] = receipt._sha256(canonical_json_bytes(core))


def test_exact_statistics_cover_observed_low_count_curve() -> None:
    assert receipt._exact_binomial_ci95(0, 40) == [
        0.0,
        0.088097302879,
    ]
    assert receipt._exact_binomial_ci95(1, 40) == [
        0.000632744932,
        0.131585858483,
    ]
    assert receipt._exact_binomial_ci95(1, 5) == [
        0.005050763379,
        0.716417936118,
    ]
    assert receipt._exact_mcnemar_p(0, 1) == 1.0


def test_public_receipt_binds_exact_fresh_process_candidate_closure(
    manifest: dict,
) -> None:
    assert len(receipt.CANDIDATE_PATHS) == 19
    assert set(receipt.CANDIDATE_PATHS) == EXPECTED_CANDIDATE_CLOSURE
    assert {
        row["path"] for row in manifest["candidate"]["files"]
    } == EXPECTED_CANDIDATE_CLOSURE
    contract = manifest["candidate_closure_contract"]
    assert contract["fresh_process_prerequisite_replayed"] is True
    assert contract["expected_path_count"] == 19
    assert contract["actual_path_count"] == 19
    assert contract["exact_closure_bound"] is True

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


def test_current_public_pair_measures_full_scalar_curve(
    manifest: dict,
) -> None:
    assert receipt.validate_receipt(manifest) == []
    assert manifest["selection"]["actual_dataset_sha256"] == (
        receipt.EXPECTED_DATASET_SHA256
    )
    assert manifest["selection"]["expected_item_count"] == 40
    assert manifest["selection"]["category_counts"] == {
        category: 5 for category in receipt.CATEGORIES
    }
    assert manifest["metrics"]["primary_order_counts"] == {
        "off_then_on": 20,
        "on_then_off": 20,
    }

    overall = manifest["metrics"]["overall"]
    off = overall["off"]
    on = overall["on"]
    assert off["n"] == on["n"] == 40
    assert off["input_valid"] == on["input_valid"] == 40
    assert off["compiler_reach"] == on["compiler_reach"] == 1
    assert (
        off["raw_fired"]
        == off["formula_fired"]
        == off["resolver_grounded"]
        == off["proof_replayed"]
        == off["accepted_fired"]
        == off["grounded"]
        == off["correct"]
        == off["wrong_fire"]
        == off["error"]
        == 0
    )
    assert off["abstain"] == 40
    assert (
        on["raw_fired"]
        == on["formula_fired"]
        == on["resolver_grounded"]
        == on["proof_replayed"]
        == on["accepted_fired"]
        == on["grounded"]
        == on["correct"]
        == on["provenance_bound_fires"]
        == 1
    )
    assert on["wrong_fire"] == on["error"] == 0
    assert on["abstain"] == 39
    assert on["grounded_leaf_count_total"] == 3
    assert on["grounded_stage_leaf_count_total"] == 3
    assert on["evidence_id_count_total"] == 3
    assert off["strict_accuracy"] == 0.0
    assert on["strict_accuracy"] == 0.025
    assert off["strict_accuracy_exact_binomial_95_ci"] == [
        0.0,
        0.088097302879,
    ]
    assert on["strict_accuracy_exact_binomial_95_ci"] == [
        0.000632744932,
        0.131585858483,
    ]
    assert overall["paired"] == {
        "accepted_firing_rate_delta": 0.025,
        "compiler_reach_rate_delta": 0.0,
        "discordant_pairs": 1,
        "exact_two_sided_mcnemar_p": 1.0,
        "formula_firing_rate_delta": 0.025,
        "grounded_coverage_delta": 0.025,
        "off_correct_on_incorrect": 0,
        "off_incorrect_on_correct": 1,
        "proof_replay_rate_delta": 0.025,
        "raw_firing_rate_delta": 0.025,
        "resolver_grounding_rate_delta": 0.025,
        "strict_accuracy_delta": 0.025,
        "transition_counts": {
            "abstain_to_abstain": 39,
            "abstain_to_correct": 1,
        },
        "wrong_fire_rate_delta": 0.0,
    }
    assert manifest["metrics"][
        "paired_development_measurement_protocol_gate_passed"
    ] is True


def test_category_curve_and_post_hoc_target_are_explicit(
    manifest: dict,
) -> None:
    categories = manifest["metrics"]["categories"]
    assert set(categories) == set(receipt.CATEGORIES)
    assert all(row["n"] == 5 for row in categories.values())
    assert categories["chemistry"]["on"]["compiler_reach"] == 1
    assert categories["chemistry"]["on"]["accepted_fired"] == 1
    assert categories["chemistry"]["on"]["correct"] == 1
    assert categories["chemistry"]["on"]["strict_accuracy"] == 0.2
    assert categories["chemistry"]["on"][
        "strict_accuracy_exact_binomial_95_ci"
    ] == [0.005050763379, 0.716417936118]
    for category in set(receipt.CATEGORIES) - {"chemistry"}:
        assert categories[category]["on"]["compiler_reach"] == 0
        assert categories[category]["on"]["accepted_fired"] == 0
        assert categories[category]["on"]["correct"] == 0

    target = manifest["metrics"]["targeted_public_observation"]
    assert target == {
        "category": "chemistry",
        "off_status": "abstain",
        "on_evidence_ids": [
            "quantity-evidence-005",
            "quantity-evidence-006",
            "quantity-evidence-008",
        ],
        "on_status": "correct",
        "post_hoc_targeted": True,
        "proof_matches_disclosed_stage_rows": True,
        "unbiased_generalization_observation": False,
        "zero_based_ordinal": 7,
    }
    assert sum(
        int(row["post_hoc_targeted_item"]) for row in manifest["items"]
    ) == 1
    assert manifest["items"][7]["post_hoc_targeted_item"] is True


def test_disclosure_is_exact_digest_bound_and_does_not_claim_generalization(
    manifest: dict,
) -> None:
    disclosure = manifest["adaptation_disclosure"]
    assert disclosure == receipt._adaptation_disclosure()
    assert disclosure["public_slice_exposed_before_profile_freeze"] is True
    assert (
        disclosure["profile_and_stage_selected_after_public_item_inspection"]
        is True
    )
    assert disclosure["pre_targeting_scalar_public_receipt_exists"] is False
    assert disclosure["git_row_addition_timing_treated_as_preregistration"] is (
        False
    )
    assert disclosure["measurement_role"] == (
        "post_selection_confirmation_not_unbiased_generalization"
    )
    assert disclosure["unbiased_generalization_claimed"] is False
    assert disclosure["hiddenness_claimed"] is False
    assert disclosure["independent_evaluation_claimed"] is False
    assert disclosure["external_authenticity_established"] is False
    assert disclosure["e5_claimed"] is False


def test_candidate_boundary_keeps_all_evaluator_metadata_out(
    manifest: dict,
) -> None:
    rows, _ = receipt._load_dataset(receipt.REPO)
    safe = receipt._candidate_payload(rows[receipt.TARGET_ORDINAL])
    assert frozenset(safe) == {"question", "choices"}
    assert "gold" not in safe
    assert "category" not in safe
    assert "ordinal" not in safe
    assert "post_hoc_targeted_item" not in safe

    stage = receipt.load_science_quantity_stage(
        receipt.REPO / receipt.STAGE_ROOT
    )
    with pytest.raises(
        BenchmarkEvidenceError,
        match="only question and choices",
    ):
        receipt.scalar_e4.run_candidate(
            {
                "question": "forbidden",
                "choices": {"A": "1 mL", "B": "2 mL"},
                "gold": "A",
            },
            stage=stage,
            overlay_enabled=True,
            base_state_digest=lambda: "0" * 64,
        )

    for index, row in enumerate(manifest["items"]):
        assert row["ordinal"] == index
        assert row["gold_absent_from_candidate_arguments"] is True
        assert (
            row["evaluator_metadata_absent_from_candidate_arguments"] is True
        )
        expected_order = (
            ["off", "on"] if index % 2 == 0 else ["on", "off"]
        )
        assert row["primary_execution_order"] == expected_order
        assert row["replay_execution_order"] == list(
            reversed(expected_order)
        )
        assert all(
            row["replay"][field] is True
            for field in (
                "input_fingerprint_same",
                "goal_digest_same",
                "off_semantic_outcome_same",
                "on_semantic_outcome_same",
            )
        )


def test_current_e4_prerequisite_is_reexecuted_with_limits(
    manifest: dict,
) -> None:
    contract = manifest["e4_prerequisite_contract"]
    assert contract["schema_version"] == receipt.scalar_e4.SCHEMA_VERSION
    assert contract["evidence_kind"] == receipt.scalar_e4.EVIDENCE_KIND
    assert contract["current_reexecuted"] is True
    assert contract["fresh_process_current_replay_enforced"] is True
    assert contract["e4_development_gate_passed"] is True
    assert contract["candidate_control_count"] == 6
    assert contract["candidate_controls_passed"] == 6
    assert contract["staging_control_count"] == 3
    assert contract["staging_controls_passed"] == 3
    assert contract["stage_controls_scope"] == (
        "manifest-rechecksummed partial-inconsistency rejection only"
    )
    assert (
        contract["coordinated_stage_rewrite_resistance_claimed"] is False
    )
    assert contract["shipped_graph_immutability_claimed"] is False
    assert contract["hidden_holdout_claimed"] is False
    assert contract["independent_evaluation_claimed"] is False
    assert contract["external_authenticity_established"] is False
    assert contract["resource_curve_established"] is False
    assert contract["e5_claimed"] is False


def test_targeted_h3po4_control_is_partial_inconsistency_only(
    manifest: dict,
) -> None:
    control = manifest["targeted_stage_control"]
    assert control["target_row_id"] == "quantity-species-row-005"
    assert control["target_evidence_id"] == "quantity-evidence-005"
    assert control["original_equivalents_per_mole"] == 3
    assert control["mutated_equivalents_per_mole"] == 2
    assert control["loader_accepted"] is False
    assert control["snapshot_returned"] is False
    assert control["expected_rejection_observed"] is True
    assert control["semantic_replay_same"] is True
    assert control["contract_passed"] is True
    assert control["error_kind"] == "ScienceQuantityStageError"
    assert control["control_scope"] == (
        "partial-inconsistency only: species and manifest changed while "
        "evidence claim remained unchanged"
    )
    assert control["coordinated_stage_rewrite_resistance_claimed"] is False
    assert len(control["mutated_stage_content_sha256"]) == 64
    assert len(control["observed_loader_error_sha256"]) == 64


def test_seal_and_authority_limits_are_all_false(
    manifest: dict,
) -> None:
    claims = manifest["claims"]
    assert claims["development_only"] is True
    assert claims["paired_measurement_protocol_gate_passed"] is True
    assert claims["e4_prerequisite_gate_passed"] is True
    assert claims["post_hoc_targeting_disclosed"] is True
    for field in (
        "e5_claimed",
        "independent",
        "externally_signed",
        "hidden_holdout_claimed",
        "external_authenticity_established",
        "unbiased_generalization_claimed",
        "coordinated_stage_rewrite_resistance_claimed",
        "shipped_graph_immutability_claimed",
        "benchmark_capability_claimed",
        "process_resource_curve_claimed",
    ):
        assert claims[field] is False

    seal = manifest["seal"]
    assert seal["sealed"] is True
    for field in (
        "hidden_holdout_claimed",
        "independent_evaluation_claimed",
        "authenticity_established",
        "unbiased_generalization_established",
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


def test_receipt_is_deterministic_write_once_and_current_verified(
    tmp_path: Path,
    manifest: dict,
) -> None:
    assert receipt.build_receipt(repo_root=receipt.REPO) == manifest
    path = tmp_path / "scalar-public.json"
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
    assert report["valid"] is True
    assert report["structure_valid"] is True
    assert report["matches_current"] is True
    assert report["declared_sealed"] is True
    assert report["verified_sealed"] is True
    assert report["sealed"] is True
    assert report["findings"] == []
    assert report["control_fixture_matches_current"] is True
    assert report["e5_claimed"] is False
    assert report["authenticity_established"] is False
    assert report["unbiased_generalization_established"] is False
    assert report["resource_curve_established"] is False
    with pytest.raises(BenchmarkEvidenceError, match="already exists"):
        receipt.write_receipt_exclusive(
            path,
            manifest,
            repo_root=receipt.REPO,
        )


def test_historical_structure_is_never_a_verified_seal(
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
    (
        "authority",
        "disclosure",
        "prerequisite",
        "target_control",
        "replay",
        "order",
        "selection",
        "scope",
        "resource",
        "stage_auth",
        "gold_injection",
        "metrics",
    ),
)
def test_rechecksummed_tampering_fails_closed(
    manifest: dict,
    variant: str,
) -> None:
    tampered = _detached(manifest)
    if variant == "authority":
        tampered["claims"]["independent"] = True
    elif variant == "disclosure":
        disclosure = tampered["adaptation_disclosure"]
        disclosure[
            "profile_and_stage_selected_after_public_item_inspection"
        ] = False
        _redigest_nested(disclosure, "disclosure_digest_sha256")
    elif variant == "prerequisite":
        contract = tampered["e4_prerequisite_contract"]
        contract["coordinated_stage_rewrite_resistance_claimed"] = True
        _redigest_nested(contract, "contract_digest_sha256")
    elif variant == "target_control":
        tampered["targeted_stage_control"][
            "coordinated_stage_rewrite_resistance_claimed"
        ] = True
    elif variant == "replay":
        tampered["items"][0]["replay"][
            "on_replay_digest_sha256"
        ] = "0" * 64
    elif variant == "order":
        tampered["items"][0]["primary_execution_order"] = ["on", "off"]
        tampered["items"][0]["replay_execution_order"] = ["off", "on"]
    elif variant == "selection":
        tampered["selection"]["category_counts"]["chemistry"] = 4
    elif variant == "scope":
        tampered["candidate"]["files"][0]["sha256"] = "0" * 64
        tampered["candidate"]["content_sha256"] = receipt._sha256(
            canonical_json_bytes(tampered["candidate"]["files"])
        )
    elif variant == "resource":
        tampered["resources"] = {"rss_delta_bytes": 1}
    elif variant == "stage_auth":
        tampered["stage_snapshot"][
            "external_authenticity_established"
        ] = True
    elif variant == "gold_injection":
        tampered["items"][0]["gold"] = "A"
    elif variant == "metrics":
        tampered["metrics"]["overall"]["on"]["accepted_fired"] = 2
    _rechecksum(tampered)
    assert receipt.validate_receipt(tampered)


def test_rechecksummed_outcome_tamper_requires_and_fails_current_replay(
    tmp_path: Path,
    manifest: dict,
) -> None:
    tampered = _detached(manifest)
    tampered["items"][0]["conditions"]["on"]["reason"] = (
        "tampered-but-rechecksummed"
    )
    _rechecksum(tampered)
    assert receipt.validate_receipt(tampered) == []
    path = tmp_path / "outcome-tamper.json"
    _write_canonical(path, tampered)
    report = receipt.verify_receipt(
        path,
        repo_root=receipt.REPO,
        require_current=True,
    )
    assert report["valid"] is False
    assert report["verified_sealed"] is False
    assert report["sealed"] is False
    assert any(
        "current deterministic payload mismatch" in finding
        for finding in report["findings"]
    )


def test_verifier_fails_closed_on_malformed_seal(
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


def test_verifier_rebinds_all_scopes_after_current_replay(
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
    assert report["sealed"] is False
    assert any(
        "scope differs after current semantic replay" in finding
        for finding in report["findings"]
    )


def test_builder_rebinds_scopes_across_fresh_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = receipt._current_scopes
    calls = 0

    def changes_after_worker(repo_root):
        nonlocal calls
        calls += 1
        scopes = deepcopy(original(repo_root))
        if calls == 2:
            scopes["stage"]["content_sha256"] = "0" * 64
        return scopes

    monkeypatch.setattr(receipt, "_current_scopes", changes_after_worker)
    with pytest.raises(
        BenchmarkEvidenceError,
        match="changed across fresh scalar public worker: stage",
    ):
        receipt.build_receipt(repo_root=receipt.REPO)


def test_reader_requires_canonical_json_and_exactly_one_newline(
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
        '{"adaptation_disclosure":',
        '{"schema_version":"duplicate","adaptation_disclosure":',
        1,
    )
    duplicate.write_bytes(duplicate_payload.encode("utf-8") + b"\n")
    with pytest.raises(BenchmarkEvidenceError, match="duplicate JSON key"):
        receipt.read_receipt(duplicate)

    extra_newline = tmp_path / "extra-newline.json"
    extra_newline.write_bytes(canonical_json_bytes(manifest) + b"\n\n")
    with pytest.raises(BenchmarkEvidenceError):
        receipt.read_receipt(extra_newline)
