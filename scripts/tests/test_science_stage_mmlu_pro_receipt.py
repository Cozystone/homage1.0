from __future__ import annotations

from copy import deepcopy

import pytest

from packages.eval_evidence.receipt import (
    canonical_json_bytes,
    write_manifest_exclusive,
)
from scripts import science_stage_mmlu_pro_receipt as receipt


def _exact_dataset_available() -> bool:
    path = receipt.REPO / receipt.DATASET_PATH
    try:
        return receipt._sha256(path.read_bytes()) == (
            receipt.EXPECTED_DATASET_SHA256
        )
    except OSError:
        return False


_SKIP_REASON = (
    "exact local data/benchmarks/mmlu_pro/slice_5.jsonl with pinned "
    f"SHA-256 {receipt.EXPECTED_DATASET_SHA256} is absent"
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not _exact_dataset_available():
        pytest.skip(_SKIP_REASON)
    return receipt.build_receipt()


def _rechecksum(manifest: dict) -> dict:
    manifest.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = receipt._checksum(manifest)
    return manifest


def test_exact_statistics_helpers_cover_the_zero_of_40_case() -> None:
    assert receipt._exact_binomial_ci95(0, 40) == [
        0.0,
        0.088097302879,
    ]
    assert receipt._exact_mcnemar_p(0, 0) == 1.0
    assert receipt._exact_mcnemar_p(0, 5) == 0.0625


def test_current_pair_is_fixed_argument_separated_and_development_only(
    manifest: dict,
) -> None:
    assert receipt.validate_receipt(manifest, require_current=True) == []
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
    assert overall["off"]["n"] == overall["on"]["n"] == 40
    assert overall["off"]["input_valid"] == overall["on"]["input_valid"] == 40
    assert overall["off"]["compiler_reach"] == 0
    assert overall["on"]["compiler_reach"] == 0
    assert overall["off"]["strict_accuracy"] == 0.0
    assert overall["on"]["strict_accuracy"] == 0.0
    assert overall["paired"] == {
        "strict_accuracy_delta": 0.0,
        "transition_counts": {"abstain_to_abstain": 40},
        "off_correct_on_incorrect": 0,
        "off_incorrect_on_correct": 0,
        "discordant_pairs": 0,
        "exact_two_sided_mcnemar_p": 1.0,
    }
    assert overall["off"]["strict_accuracy_exact_binomial_95_ci"] == [
        0.0,
        0.088097302879,
    ]
    assert set(manifest["metrics"]["categories"]) == set(receipt.CATEGORIES)
    assert all(
        row["n"] == 5
        for row in manifest["metrics"]["categories"].values()
    )
    assert manifest["metrics"][
        "paired_development_measurement_gate_passed"
    ] is True

    assert manifest["claims"]["development_only"] is True
    assert manifest["claims"]["e5_claimed"] is False
    assert manifest["claims"]["independent"] is False
    assert manifest["claims"]["external_authenticity_established"] is False
    assert manifest["claims"]["process_resource_curve_claimed"] is False
    assert manifest["seal"]["sealed"] is True
    assert manifest["seal"]["e5_equivalent"] is False
    assert "environment" not in manifest
    assert "started_at" not in manifest
    assert "completed_at" not in manifest
    assert manifest["e4_prerequisite_contract"]["schema_version"] == (
        receipt.e4.SCHEMA_VERSION
    )
    assert manifest["e4_prerequisite_contract"][
        "generated_external_receipt_required"
    ] is False

    for index, row in enumerate(manifest["items"]):
        assert row["ordinal"] == index
        assert row["evaluator_eligible"] is True
        assert row["gold_absent_from_candidate_arguments"] is True
        assert row["primary_execution_order"] == (
            ["off", "on"] if index % 2 == 0 else ["on", "off"]
        )
        assert row["replay_execution_order"] == list(
            reversed(row["primary_execution_order"])
        )
        off = row["conditions"]["off"]["result"]
        on = row["conditions"]["on"]["result"]
        assert off["stage_digest_sha256"] is None
        assert off["stage_snapshot_bound_bytes"] == 0
        assert off["stage_hit_count"] == 0
        assert on["stage_digest_sha256"] == (
            manifest["stage_snapshot"]["stage_digest_sha256"]
        )
        assert on["stage_snapshot_bound_bytes"] == (
            manifest["stage_snapshot"]["bound_bytes"]
        )
        assert off["rss_delta_bytes"] is None
        assert on["rss_delta_bytes"] is None
        assert row["replay"]["off_semantic_outcome_same"] is True
        assert row["replay"]["on_semantic_outcome_same"] is True


def test_historical_structure_never_becomes_verified_seal(
    manifest: dict, tmp_path
) -> None:
    path = tmp_path / "receipt.json"
    write_manifest_exclusive(path, manifest)
    result = receipt.verify_receipt(path, require_current=False)
    assert result["valid"] is True
    assert result["structure_valid"] is True
    assert result["declared_sealed"] is True
    assert result["verified_sealed"] is False
    assert result["sealed"] is False
    assert result["matches_current"] is None


def test_recomputed_checksum_outcome_tamper_fails_current_replay(
    manifest: dict,
) -> None:
    tampered = deepcopy(manifest)
    tampered["items"][0]["conditions"]["on"]["result"]["reason"] = (
        "tampered-but-rechecksummed"
    )
    _rechecksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=True)
    assert any(
        "conditions.on does not reproduce" in finding for finding in findings
    )


def test_recomputed_checksum_replay_tamper_is_rejected(
    manifest: dict,
) -> None:
    tampered = deepcopy(manifest)
    tampered["items"][0]["replay"]["on_replay_digest_sha256"] = "0" * 64
    _rechecksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=False)
    assert any("replay ON digest mismatch" in finding for finding in findings)


def test_recomputed_checksum_process_resource_injection_is_rejected(
    manifest: dict,
) -> None:
    tampered = deepcopy(manifest)
    tampered["items"][0]["conditions"]["on"]["result"][
        "rss_delta_bytes"
    ] = 123456
    _rechecksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=True)
    assert any(
        "process resource telemetry must be omitted" in finding
        for finding in findings
    )


def test_recomputed_checksum_order_tamper_is_rejected(
    manifest: dict,
) -> None:
    tampered = deepcopy(manifest)
    tampered["items"][0]["primary_execution_order"] = ["on", "off"]
    tampered["items"][0]["replay_execution_order"] = ["off", "on"]
    _rechecksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=False)
    assert any("primary_execution_order mismatch" in item for item in findings)


@pytest.mark.parametrize("section", ["claims", "seal", "integrity", "selection"])
def test_recomputed_checksum_authority_injection_is_rejected(
    manifest: dict,
    section: str,
) -> None:
    tampered = deepcopy(manifest)
    tampered[section]["unauthorized_capability_claim"] = True
    _rechecksum(tampered)
    findings = receipt.validate_receipt(tampered, require_current=True)
    assert findings


def test_current_dataset_scope_mismatch_is_rejected(
    manifest: dict, monkeypatch
) -> None:
    original = receipt._current_scopes

    def mismatched(repo_root):
        scopes = deepcopy(original(repo_root))
        scopes["dataset"]["files"][0]["sha256"] = "0" * 64
        scopes["dataset"]["content_sha256"] = receipt._sha256(
            canonical_json_bytes(scopes["dataset"]["files"])
        )
        return scopes

    monkeypatch.setattr(receipt, "_current_scopes", mismatched)
    findings = receipt.validate_receipt(manifest, require_current=True)
    assert "dataset scope differs from current bytes" in findings


def test_current_replay_rebinds_scopes_after_execution(
    manifest: dict, monkeypatch
) -> None:
    original = receipt._current_scopes
    calls = 0

    def changes_during_replay(repo_root):
        nonlocal calls
        calls += 1
        scopes = deepcopy(original(repo_root))
        if calls >= 2:
            scopes["candidate"]["files"][0]["sha256"] = "0" * 64
            scopes["candidate"]["content_sha256"] = receipt._sha256(
                canonical_json_bytes(scopes["candidate"]["files"])
            )
        return scopes

    monkeypatch.setattr(receipt, "_current_scopes", changes_during_replay)
    findings = receipt.validate_receipt(manifest, require_current=True)
    assert "bound bytes changed during current semantic replay" in findings
    assert "candidate scope differs after current semantic replay" in findings
