from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import (
    BENCHMARK_EVIDENCE_KIND,
    BENCHMARK_EVIDENCE_SCHEMA,
    BenchmarkEvidenceError,
    aggregate_items,
    bind_files,
    canonical_json_bytes,
    environment_record,
    finalize_manifest,
    item_id,
    selection_record,
    utc_now,
    validate_manifest,
    verify_manifest,
    write_manifest_exclusive,
)


def _item(name: str, status: str) -> dict:
    fired = status in {"correct", "wrong"}
    return {
        "item_id": item_id({"name": name}),
        "status": status,
        "fired": fired,
        "correct": status == "correct",
        "output_sha256": item_id({"output": name}) if fired else None,
        "latency_ms": 1.25,
        "metadata": {},
    }


def _payload(repo: Path) -> dict:
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "data.json").write_text('{"item": 1}\n', encoding="utf-8")
    items = [_item("a", "correct"), _item("b", "wrong"), _item("c", "abstain")]
    source = bind_files(repo, ["source.py"])
    dataset = bind_files(repo, ["data.json"])
    now = utc_now()
    return {
        "schema_version": BENCHMARK_EVIDENCE_SCHEMA,
        "evidence_kind": BENCHMARK_EVIDENCE_KIND,
        "run_id": "unit-run-0001",
        "started_at": now,
        "completed_at": now,
        "benchmark": {"id": "unit", "split": "dev"},
        "config": {"seed": 0},
        "environment": environment_record(),
        "source": source,
        "candidate": source,
        "dataset": dataset,
        "selection": selection_record(items),
        "evaluator": {
            "identity": "unit exact match",
            "source_digest_sha256": source["content_sha256"],
            "independent": False,
            "externally_signed": False,
            "limitations": ["same-process evaluator"],
        },
        "metrics": aggregate_items(items),
        "items": items,
        "integrity": {
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "dataset_same_before_after": True,
            "network_isolation_enforced": False,
            "shipped_state_isolation_enforced": False,
            "production_authority": False,
            "e5_claimed": False,
            "limitations": ["unsigned checksum measurement only"],
        },
    }


def test_receipt_round_trip_and_current_file_verification(tmp_path: Path) -> None:
    manifest = finalize_manifest(_payload(tmp_path))
    path = tmp_path / "receipt.json"
    write_manifest_exclusive(path, manifest)

    result = verify_manifest(path, repo_root=tmp_path)

    assert result["valid"] is True
    assert result["structure_valid"] is True
    assert result["matches_current"] is True
    assert result["authenticity_established"] is False
    assert manifest["metrics"] == {
        "n": 3,
        "correct": 1,
        "wrong": 1,
        "abstain": 1,
        "error": 0,
        "fired": 2,
        "strict_accuracy": round(1 / 3, 12),
        "coverage": round(2 / 3, 12),
        "fired_accuracy": 0.5,
        "outcome_digest_sha256": manifest["metrics"]["outcome_digest_sha256"],
    }


def test_selection_and_metrics_are_derived_and_extra_claims_are_rejected(
    tmp_path: Path,
) -> None:
    manifest = finalize_manifest(_payload(tmp_path))
    manifest["metrics"]["correct"] = 3
    assert "metrics do not derive from item outcomes" in validate_manifest(manifest)
    assert "manifest checksum mismatch" in validate_manifest(manifest)

    manifest = finalize_manifest(_payload(tmp_path))
    manifest["selection"]["item_ids"] = manifest["selection"]["item_ids"][:-1]
    findings = validate_manifest(manifest)
    assert "selection does not exactly match item order" in findings

    payload = _payload(tmp_path)
    payload["metrics"]["extra"] = {"official_score": 1.0}
    with pytest.raises(BenchmarkEvidenceError, match="metrics fields mismatch"):
        finalize_manifest(payload)


def test_drift_is_invalid_by_default_but_historical_structure_remains_visible(
    tmp_path: Path,
) -> None:
    manifest = finalize_manifest(_payload(tmp_path))
    path = tmp_path / "receipt.json"
    write_manifest_exclusive(path, manifest)
    (tmp_path / "source.py").write_text("VALUE = 2\n", encoding="utf-8")

    current = verify_manifest(path, repo_root=tmp_path)
    historical = verify_manifest(path, repo_root=tmp_path, require_current=False)

    assert current["valid"] is False
    assert current["structure_valid"] is True
    assert historical["valid"] is True
    assert historical["matches_current"] is False
    assert historical["authenticity_established"] is False


def test_duplicate_nonfinite_malformed_and_huge_values_fail_closed(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    assert verify_manifest(duplicate, repo_root=tmp_path)["valid"] is False

    with pytest.raises(BenchmarkEvidenceError):
        finalize_manifest({"bad": float("nan")})

    malformed_variants = [
        {},
        {"schema_version": BENCHMARK_EVIDENCE_SCHEMA},
        {**finalize_manifest(_payload(tmp_path)), "items": [1]},
        {
            **finalize_manifest(_payload(tmp_path)),
            "items": [
                {
                    **_item("a", "correct"),
                    "latency_ms": 10**400,
                }
            ],
        },
    ]
    for malformed in malformed_variants:
        findings = validate_manifest(malformed)
        assert isinstance(findings, list)
        assert findings


def test_timestamp_limitation_and_literal_integrity_contracts(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["started_at"], payload["completed_at"] = (
        "2026-07-25T10:00:00Z",
        "2026-07-25T09:00:00Z",
    )
    with pytest.raises(BenchmarkEvidenceError, match="precedes"):
        finalize_manifest(payload)

    payload = _payload(tmp_path)
    payload["integrity"]["limitations"] = [False]
    with pytest.raises(BenchmarkEvidenceError, match="limitations"):
        finalize_manifest(payload)

    payload = _payload(tmp_path)
    payload["integrity"]["network_isolation_enforced"] = True
    with pytest.raises(BenchmarkEvidenceError, match="must be false"):
        finalize_manifest(payload)


def test_recomputed_checksum_is_not_authentication(tmp_path: Path) -> None:
    original = finalize_manifest(_payload(tmp_path))
    changed = json.loads(json.dumps(original))
    changed.pop("manifest_checksum_sha256")
    changed["items"][1] = _item("b", "correct")
    changed["selection"] = selection_record(changed["items"])
    changed["metrics"] = aggregate_items(changed["items"])
    recomputed = finalize_manifest(changed)
    path = tmp_path / "recomputed.json"
    write_manifest_exclusive(path, recomputed)

    result = verify_manifest(path, repo_root=tmp_path)

    assert result["valid"] is True
    assert result["authenticity_established"] is False
    assert recomputed["metrics"]["strict_accuracy"] == round(2 / 3, 12)


def test_historical_v1_shape_remains_structurally_readable(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    legacy = {
        key: value
        for key, value in payload.items()
        if key not in {"candidate", "selection"}
    }
    legacy["schema_version"] = "atanor.benchmark-evidence.v1"
    legacy["evidence_kind"] = "unsigned_source_bound_measurement"
    legacy["metrics"] = {**legacy["metrics"], "extra": {"task_count": 3}}
    legacy["integrity"] = {
        "source_unchanged_during_run": True,
        "dataset_unchanged_during_run": True,
        "network_used": False,
        "shipped_state_mutated": False,
        "production_authority": False,
        "e5_claimed": False,
        "limitations": ["historical unsigned measurement"],
    }
    legacy["manifest_hash"] = hashlib.sha256(
        canonical_json_bytes(legacy)
    ).hexdigest()
    path = tmp_path / "legacy.json"
    path.write_bytes(canonical_json_bytes(legacy) + b"\n")

    result = verify_manifest(path, repo_root=tmp_path, require_current=False)

    assert result["valid"] is True
    assert result["structure_valid"] is True
    assert result["authenticity_established"] is False


def test_bound_paths_and_exclusive_write(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_text("x", encoding="utf-8")
    with pytest.raises(BenchmarkEvidenceError):
        bind_files(tmp_path, ["data.txt", "data.txt"])
    with pytest.raises(BenchmarkEvidenceError):
        bind_files(tmp_path, ["DATA.txt", "data.txt"])
    with pytest.raises(BenchmarkEvidenceError):
        bind_files(tmp_path, ["../outside.txt"])

    manifest = finalize_manifest(_payload(tmp_path))
    path = tmp_path / "receipt.json"
    write_manifest_exclusive(path, manifest)
    with pytest.raises(BenchmarkEvidenceError, match="already exists"):
        write_manifest_exclusive(path, manifest)
