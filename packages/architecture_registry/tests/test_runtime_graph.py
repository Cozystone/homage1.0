"""The critical runtime graph keeps source, trace, authority, and capability separate."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from packages.architecture_registry.runtime_graph import (
    RuntimeGraphValidationError,
    canonical_manifest_hash,
    format_runtime_summary,
    load_and_validate_runtime_manifest,
    load_runtime_manifest,
    validate_runtime_manifest,
)

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "data" / "architecture" / "catalog" / "runtime_edges_v1.json"


def _manifest() -> dict:
    return load_runtime_manifest(MANIFEST)


def _rehash(manifest: dict) -> None:
    manifest["canonical_hash"] = canonical_manifest_hash(manifest)


def test_checked_in_runtime_graph_is_source_bound_and_honest() -> None:
    manifest = load_and_validate_runtime_manifest(MANIFEST, repo_root=REPO)
    summary = format_runtime_summary(manifest)

    assert summary["binding_count"] == 30
    assert summary["edge_count"] == 29
    assert summary["source_confirmed_calls"] == 28
    assert summary["unknown_calls"] == 1
    assert summary["unresolved_calls"] == 1
    assert summary["production_traces"] == 0
    assert summary["e5_claimed"] is False
    assert summary["benchmark_lift_claimed"] is False
    assert all(edge["capability"]["capability_claims"] == [] for edge in manifest["edges"])


def test_required_critical_paths_and_unresolved_queue_wiring_are_explicit() -> None:
    manifest = _manifest()
    by_id = {edge["id"]: edge for edge in manifest["edges"]}
    assert {
        "chat_boundary_to_cognitive_shadow",
        "cognitive_shadow_to_cycle_ledger",
        "continuous_self_shadow_to_cycle_ledger",
        "continuous_self_step_to_cognitive_shadow",
        "continuous_self_to_intrinsic_drive",
        "deployment_build_to_signed_graph_installer",
        "intrinsic_drive_to_moltbook_autopilot",
        "moltbook_autopilot_to_autonomy_envelope",
        "exam_answer_to_deliberator",
        "fusion_loop_to_envelope_adapter",
        "fusion_adapter_to_autonomy_envelope",
        "installer_to_historical_operator_trust",
        "installer_to_rootfs_shipped_rename",
        "mutation_candidate_builder_to_staged_receipt",
        "mutation_compiler_to_batch_creation",
        "mutation_compiler_to_proposed_receipt",
        "promotion_script_to_applied_receipt",
        "promotion_script_to_mutation_candidate_builder",
        "promotion_script_to_nightly_queue",
        "promotion_script_to_store_merger",
        "response_workspace_to_block_universe_bidder",
        "response_workspace_to_world4d_shadow_adapter",
        "store_merger_to_embedded_mutation_validation",
        "store_merger_to_fixed_operator_boundary",
        "store_merger_to_operator_trust",
        "store_merger_to_shipped_rename",
        "world4d_block_universe_provider_to_block_universe",
        "world4d_shadow_adapter_to_block_universe_provider",
        "world4d_shadow_adapter_to_receipt_sink",
    }.issubset(by_id)

    for edge_id in (
        "chat_boundary_to_cognitive_shadow",
        "cognitive_shadow_to_cycle_ledger",
        "continuous_self_shadow_to_cycle_ledger",
        "continuous_self_step_to_cognitive_shadow",
        "response_workspace_to_world4d_shadow_adapter",
        "world4d_block_universe_provider_to_block_universe",
        "world4d_shadow_adapter_to_block_universe_provider",
        "world4d_shadow_adapter_to_receipt_sink",
    ):
        assert by_id[edge_id]["reachable_call"]["state"] == "source_confirmed"
        assert by_id[edge_id]["exercised_trace"]["state"] == "controlled_test"
        assert by_id[edge_id]["authority"]["state"] == "bounded_guard"
        assert by_id[edge_id]["capability"]["mechanism_stage"] == "M3"

    intrinsic = by_id["continuous_self_to_intrinsic_drive"]
    assert intrinsic["exercised_trace"]["state"] == "not_recorded"
    assert intrinsic["authority"]["state"] == "unattested"
    assert intrinsic["capability"]["mechanism_stage"] == "M1"

    legacy_world4d = by_id["response_workspace_to_block_universe_bidder"]
    assert legacy_world4d["reachable_call"]["state"] == "source_confirmed"
    assert legacy_world4d["exercised_trace"]["state"] == "controlled_test"
    assert legacy_world4d["authority"]["state"] == "conditional_decider"
    assert legacy_world4d["capability"]["mechanism_stage"] == "M3"

    queue_edge = by_id["promotion_script_to_nightly_queue"]
    assert queue_edge["static_import"]["state"] == "not_observed_in_bound_source"
    assert queue_edge["reachable_call"]["state"] == "unknown"
    assert queue_edge["authority"]["state"] == "staging_only"
    for edge_id in (
        "mutation_candidate_builder_to_staged_receipt",
        "mutation_compiler_to_batch_creation",
        "mutation_compiler_to_proposed_receipt",
        "promotion_script_to_mutation_candidate_builder",
    ):
        assert by_id[edge_id]["reachable_call"]["state"] == "source_confirmed"
        assert by_id[edge_id]["exercised_trace"]["state"] == "not_recorded"
        assert by_id[edge_id]["authority"]["state"] == "staging_only"
    applied = by_id["promotion_script_to_applied_receipt"]
    assert applied["reachable_call"]["state"] == "source_confirmed"
    assert applied["exercised_trace"]["state"] == "not_recorded"
    assert applied["authority"]["state"] == "external_signature_required"
    embedded = by_id["store_merger_to_embedded_mutation_validation"]
    assert embedded["reachable_call"]["state"] == "source_confirmed"
    assert embedded["exercised_trace"]["state"] == "not_recorded"
    assert embedded["authority"]["state"] == "bounded_guard"
    assert (
        by_id["store_merger_to_fixed_operator_boundary"]["authority"]["state"]
        == "bounded_guard"
    )
    assert (
        by_id["store_merger_to_fixed_operator_boundary"]["reachable_call"]["state"]
        == "source_confirmed"
    )
    assert (
        by_id["deployment_build_to_signed_graph_installer"]["reachable_call"]["state"]
        == "source_confirmed"
    )
    for edge_id in (
        "installer_to_historical_operator_trust",
        "installer_to_rootfs_shipped_rename",
    ):
        assert by_id[edge_id]["authority"]["state"] == "external_signature_required"
        assert by_id[edge_id]["exercised_trace"]["state"] == "not_recorded"
    assert "v3" in by_id["promotion_script_to_store_merger"]["authority"]["note"]
    assert "v3" in by_id["store_merger_to_operator_trust"]["authority"]["note"]
    assert "v3" in by_id["store_merger_to_shipped_rename"]["reachable_call"]["note"]
    assert any(
        "committed v2 evidence" in limitation
        for limitation in by_id["installer_to_historical_operator_trust"]["limitations"]
    )


def test_static_import_never_promotes_reachability() -> None:
    manifest = _manifest()
    edge = next(
        row for row in manifest["edges"]
        if row["id"] == "moltbook_autopilot_to_autonomy_envelope"
    )
    edge["reachable_call"] = {
        "state": "unknown",
        "binding_refs": [],
        "note": "The test deliberately removes the independent call claim.",
    }
    _rehash(manifest)

    assert validate_runtime_manifest(manifest, repo_root=REPO) == []


def test_source_confirmed_call_requires_its_own_live_source_binding() -> None:
    manifest = _manifest()
    manifest["edges"][0]["reachable_call"]["binding_refs"] = []
    _rehash(manifest)

    issues = validate_runtime_manifest(manifest, repo_root=REPO)

    assert any("binding_refs required for state 'source_confirmed'" in issue for issue in issues)


def test_controlled_test_trace_requires_test_source_and_immutable_report() -> None:
    manifest = _manifest()
    edge = manifest["edges"][0]
    edge["exercised_trace"] = {
        "state": "controlled_test",
        "binding_refs": edge["reachable_call"]["binding_refs"],
        "note": "A live source file alone is not an executed test receipt.",
    }
    _rehash(manifest)

    issues = validate_runtime_manifest(manifest, repo_root=REPO)

    assert any(
        "controlled_test requires test_source and evidence_report bindings" in issue
        for issue in issues
    )


def test_capability_and_e5_overclaims_fail_closed() -> None:
    manifest = _manifest()
    manifest["maturity"]["e5_claimed"] = True
    manifest["maturity"]["capability_claims"] = ["GPQA improved"]
    manifest["edges"][0]["capability"]["mechanism_stage"] = "E5"
    manifest["edges"][0]["capability"]["capability_claims"] = ["AGI"]
    manifest["edges"][0]["capability"]["e5_claimed"] = True
    _rehash(manifest)

    issues = validate_runtime_manifest(manifest, repo_root=REPO)

    assert any("maturity.e5_claimed must be literal false" in issue for issue in issues)
    assert any("maturity.capability_claims must be empty" in issue for issue in issues)
    assert any(".mechanism_stage must be one of" in issue for issue in issues)
    assert any(".capability_claims must be empty" in issue for issue in issues)


def test_source_digest_drift_is_detected() -> None:
    manifest = _manifest()
    manifest["bindings"][0]["sha256"] = "0" * 64
    _rehash(manifest)

    issues = validate_runtime_manifest(manifest, repo_root=REPO)

    assert any(".sha256 mismatch" in issue for issue in issues)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")

    with pytest.raises(RuntimeGraphValidationError, match="duplicate JSON key"):
        load_runtime_manifest(path)


def test_manifest_canonical_hash_detects_claim_mutation() -> None:
    manifest = copy.deepcopy(_manifest())
    manifest["claim_scope"] = "mutated without re-signing the catalog"

    issues = validate_runtime_manifest(manifest, repo_root=REPO)

    assert any("canonical_hash mismatch" in issue for issue in issues)
