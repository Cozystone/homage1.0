from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packages.cloud_brain.bounded_learning_runner import (
    BoundedLearningRunConfig,
    assess_24h_readiness,
    run_bounded_candidate_learning,
)
from packages.cloud_brain.verified_payload_feeder import payload_from_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_STORE = PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0"


def _production_identity() -> tuple[str, str, dict[str, int]]:
    manifest_path = PRODUCTION_STORE / "manifest.json"
    schema_path = PRODUCTION_STORE / "schema.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = {key: int(value) for key, value in manifest.get("counts", {}).items()}
    return (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        counts,
    )


def _payloads(count: int) -> list:
    rows = []
    for index in range(count):
        text = f"검증 문장 {index}는 후보 저장소를 안전하게 확인합니다."
        rows.append(
            payload_from_mapping(
                {
                    "payload_id": f"bounded_test_{index}",
                    "source_type": "manual_public_sentence",
                    "source_id": f"manual:bounded-test:{index}",
                    "source_url_or_path": f"manual://bounded-test/{index}",
                    "provenance_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "license_hint": "CC BY-SA 4.0 test fixture",
                    "language": "ko",
                    "text": text,
                    "is_private": False,
                    "is_generated": False,
                    "is_eval_row": False,
                    "target_store": "verified_store_v0_candidate",
                }
            )
        )
    return rows


def _config(tmp_path: Path, **overrides) -> BoundedLearningRunConfig:
    payload = {
        "profile": "interactive_safe",
        "max_payloads": 20,
        "max_seconds": 60,
        "max_store_mb": 64.0,
        "min_ram_free_gb": 0.0,
        "min_disk_free_gb": 0.0,
        "max_cpu_percent": None,
        "max_candidate_files": None,
        "target_candidate_store": str(tmp_path / "candidate"),
        "dry_run": False,
        "execute": True,
        "batch_size": 5,
    }
    payload.update(overrides)
    return BoundedLearningRunConfig(**payload)


def test_execute_false_does_not_process_or_create_candidate_store(tmp_path: Path) -> None:
    config = _config(tmp_path, execute=False, dry_run=True)
    result = run_bounded_candidate_learning(config, payloads=_payloads(5))
    assert result.state == "dry_run"
    assert result.payloads_seen == 0
    assert not (tmp_path / "candidate").exists()
    assert result.production_store_mutated is False


def test_execute_true_processes_candidate_only_and_preserves_production(tmp_path: Path) -> None:
    before = _production_identity()
    result = run_bounded_candidate_learning(_config(tmp_path, max_payloads=10), payloads=_payloads(10))
    after = _production_identity()
    assert result.state == "completed"
    assert result.payloads_accepted == 10
    assert result.concepts_added_candidate > 0
    assert result.surface_candidates == 10
    assert result.cgsr_frames == 10
    assert result.rhfc_candidates == 10
    assert result.production_store_mutated is False
    assert result.local_brain_write is False
    assert result.false_confident == 0
    assert result.forgetting_count == 0
    assert result.invariants["pair_edges_sent"] == 0
    assert before == after


def test_max_payloads_stops_bounded_run(tmp_path: Path) -> None:
    result = run_bounded_candidate_learning(_config(tmp_path, max_payloads=7), payloads=_payloads(20))
    assert result.payloads_seen == 7
    assert result.stop_reason == "payload_cap_reached"


def test_store_cap_pauses_after_candidate_growth(tmp_path: Path) -> None:
    result = run_bounded_candidate_learning(
        _config(tmp_path, max_payloads=50, max_store_mb=0.001, batch_size=5),
        payloads=_payloads(50),
    )
    assert result.state == "paused"
    assert result.stop_reason == "store_cap_reached"
    assert result.payloads_accepted > 0
    assert result.production_store_mutated is False


def test_ram_and_disk_guards_pause_before_learning(tmp_path: Path) -> None:
    ram = run_bounded_candidate_learning(_config(tmp_path / "ram", min_ram_free_gb=999999), payloads=_payloads(5))
    disk = run_bounded_candidate_learning(_config(tmp_path / "disk", min_disk_free_gb=999999), payloads=_payloads(5))
    assert ram.state == "paused"
    assert ram.stop_reason == "ram_pressure"
    assert ram.payloads_accepted == 0
    assert disk.state == "paused"
    assert disk.stop_reason == "disk_pressure"
    assert disk.payloads_accepted == 0


def test_production_promotion_is_rejected(tmp_path: Path) -> None:
    result = run_bounded_candidate_learning(_config(tmp_path, promote_to_verified=True), payloads=_payloads(5))
    assert result.state == "failed"
    assert result.stop_reason == "production_promotion_rejected"
    assert result.production_store_mutated is False


def test_24h_readiness_reports_not_ready_when_resource_thresholds_are_too_high(tmp_path: Path) -> None:
    report = assess_24h_readiness(
        profile="24h_balanced",
        target_candidate_store=tmp_path / "candidate",
        measured_accepted_per_second=10.0,
    )
    assert "safe_to_start_24h_candidate_run" in report
    assert "reason" in report
