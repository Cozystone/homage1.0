from __future__ import annotations

import hashlib
from pathlib import Path

from packages.cloud_brain import bounded_learning_runner
from packages.cloud_brain.bounded_learning_runner import BoundedLearningRunConfig, run_bounded_candidate_learning
from packages.cloud_brain.verified_payload_feeder import payload_from_mapping


def _payloads(count: int) -> list:
    rows = []
    templates = [
        "쿠버네티스는 컨테이너화된 애플리케이션을 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다.",
        "그래프는 개념과 관계를 연결하여 지식 구조를 표현합니다.",
        "공개 말뭉치는 출처와 라이선스를 포함하는 검증된 학습 자료입니다.",
        "검증된 문장은 후보 그래프 학습에서 출처 보존을 지원합니다.",
    ]
    for index in range(count):
        text = templates[index % len(templates)]
        rows.append(
            payload_from_mapping(
                {
                    "payload_id": f"rate_test_{index}",
                    "source_type": "local_public_corpus_shard",
                    "source_id": f"fixture:rate-test:{index}",
                    "source_url_or_path": f"file://fixture/public.jsonl#L{index}",
                    "provenance_hash": hashlib.sha256(f"{index}:{text}".encode("utf-8")).hexdigest(),
                    "license_hint": "CC BY-SA 4.0 test fixture",
                    "language": "ko",
                    "text": text,
                    "is_private": False,
                    "is_generated": False,
                    "is_eval_row": False,
                    "is_mock": False,
                    "source_mode": "local_dump_shard",
                    "target_store": "verified_store_v0_candidate",
                }
            )
        )
    return rows


def _config(tmp_path: Path, **overrides) -> BoundedLearningRunConfig:
    payload = {
        "profile": "interactive_safe",
        "max_payloads": 10,
        "max_seconds": 60,
        "max_store_mb": 64.0,
        "min_ram_free_gb": 0.0,
        "min_disk_free_gb": 0.0,
        "max_cpu_percent": None,
        "max_candidate_files": None,
        "target_candidate_store": str(tmp_path / "candidate"),
        "dry_run": False,
        "execute": True,
        "batch_size": 2,
    }
    payload.update(overrides)
    return BoundedLearningRunConfig(**payload)


def test_runner_refuses_full_duration_when_source_rows_are_insufficient(tmp_path: Path) -> None:
    result = run_bounded_candidate_learning(
        _config(
            tmp_path,
            max_payloads=10,
            target_payloads_per_second=5.0,
            target_duration_seconds=6 * 60 * 60,
            pacing_mode="sleep_between_batches",
        ),
        payloads=_payloads(10),
    )

    assert result.state == "paused"
    assert result.stop_reason == "insufficient_source_rows_for_target_duration"
    assert result.payloads_seen == 0
    assert result.payloads_accepted == 0
    assert result.production_store_mutated is False
    assert result.source_capacity_plan["required_rows_for_duration"] == 108000
    assert result.source_capacity_plan["available_rows"] == 10


def test_target_rate_pacing_does_not_fake_accepted_rows(tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(bounded_learning_runner.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = run_bounded_candidate_learning(
        _config(
            tmp_path,
            max_payloads=4,
            batch_size=1,
            target_payloads_per_second=0.5,
            pacing_mode="sleep_between_batches",
        ),
        payloads=_payloads(4),
    )

    assert result.state == "completed"
    assert result.stop_reason == "payload_cap_reached"
    assert result.payloads_seen == 4
    assert result.payloads_accepted == 4
    assert result.production_store_mutated is False
    assert result.invariants["pair_edges_sent"] == 0
    assert sleeps
