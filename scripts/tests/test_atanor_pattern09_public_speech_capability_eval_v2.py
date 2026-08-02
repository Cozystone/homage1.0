"""Adversarial and positive controls for the Pattern #9 v2 verifier."""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import BenchmarkEvidenceError
from scripts import atanor_pattern09_public_speech_capability_eval_v2 as p09


def _fixture() -> dict:
    return json.loads(p09.ADVERSARIAL_FIXTURE.read_text(encoding="utf-8"))


def _requests() -> list[dict]:
    requests = []
    for condition, block_id in (
        ("OFF", "OFF_BASELINE"),
        ("ON", "ON_CANDIDATE"),
    ):
        requests.append(
            {
                "schema_version": p09.WORKER_REQUEST_SCHEMA,
                "preregistration_id": p09.PREREGISTRATION_ID,
                "block_id": block_id,
                "condition": condition,
                "python_hash_seed": "0",
                "items": [
                    {
                        "index": index,
                        "item_key": f"{index + 1:064x}",
                        "query": f"opaque query {index}",
                        "semantic_context": {},
                        "surface_plan": None,
                    }
                    for index in range(12)
                ],
            }
        )
    return requests


def _worker_result(request: dict, binding: dict) -> dict:
    condition = request["condition"]
    result = {
        "schema_version": p09.WORKER_RESULT_SCHEMA,
        "preregistration_id": p09.PREREGISTRATION_ID,
        "block_id": request["block_id"],
        "condition": condition,
        "python_hash_seed": "0",
        "python": "synthetic",
        "source_root": {
            "kind": "ephemeral_arm_root",
            "condition": condition,
        },
        "loaded_modules": dict(p09._DURABLE_MODULES),
        "application_isolation": {
            "router_only": True,
            "global_app_main_loaded": False,
            "startup_handler_count": 0,
            "shutdown_handler_count": 0,
            "target_routes_present": [
                "/api/speech/plan",
                "/api/speech/realize",
            ],
        },
        "repo_import_closure": {
            "source_module_count": 2,
            "source_modules_sha256": "0" * 64,
            "outside_source_repo_modules": [],
            "forbidden_source_modules_loaded": [],
        },
        "environment": {
            "keys": [
                "ATANOR_PATTERN09_SOURCE_ROOT",
                "PATH",
                "PYTHONHASHSEED",
            ],
            "unexpected_atanor_keys": [],
        },
        "network_guard": {
            "external_socket_create_connection_blocked": True,
            "external_socket_connect_blocked": True,
            "external_socket_connect_ex_blocked": True,
            "loopback_only": True,
        },
        "runtime_isolation": {
            "temporary_root_outside_source": True,
            "files": [],
        },
        "items": [
            {
                "index": item["index"],
                "item_key": item["item_key"],
                "condition": condition,
                "plan_status": 200,
                "answer_status": 200,
                "field_presence": {
                    field: True for field in p09._v1._PRESENCE_FIELDS
                },
                "plan_relation_count": 0,
                "plan_evidence_count": 0,
                "plan_input_trust": p09.PUBLIC_TRUST,
                "answer": "I do not have enough local evidence.",
                "semantic_sources": [],
                "answer_no_evidence": True,
                "answer_input_trust": p09.PUBLIC_TRUST,
                "surface_plan_id": f"synthetic-{item['index']}",
                "error": None,
            }
            for item in request["items"]
        ],
        p09._RECEIPT_FIELD: {
            "schema_version": p09._RECEIPT_SCHEMA,
            "condition": condition,
            "before": binding,
            "after": binding,
            "same_before_after": True,
        },
    }
    return result


def _report(path: Path, requests: list[dict], bindings: dict[str, dict]) -> dict:
    report = {
        "schema_version": p09.REPORT_SCHEMA,
        "execution_seal": {},
        "arms": [
            {
                "condition": request["condition"],
                "source_binding": bindings[request["condition"]],
                "result": _worker_result(
                    request, bindings[request["condition"]]
                ),
            }
            for request in requests
        ],
    }
    report["checksum_sha256"] = p09._checksum(report)
    path.write_bytes(p09.canonical_json_bytes(report) + b"\n")
    return report


def _install_receipt_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, dict, list[dict], dict[str, dict]]:
    path = tmp_path / "pattern09-v2.json"
    requests = _requests()
    bindings = {
        "OFF": {
            "files": [{"path": "off", "bytes": 1, "sha256": "0" * 64}],
            "content_sha256": "1" * 64,
        },
        "ON": {
            "files": [{"path": "on", "bytes": 1, "sha256": "2" * 64}],
            "content_sha256": "3" * 64,
        },
    }
    report = _report(path, requests, bindings)
    monkeypatch.setattr(p09, "REPORT", path)
    monkeypatch.setattr(
        p09,
        "load_preregistration",
        lambda *_args, **_kwargs: ({}, "preregister-v2.json"),
    )
    monkeypatch.setattr(
        p09,
        "load_dataset",
        lambda _prereg: ({}, [], "dataset-v1.json"),
    )
    monkeypatch.setattr(
        p09, "build_worker_requests", lambda _prereg, _cases: requests
    )
    monkeypatch.setattr(
        p09._v1,
        "_validate_recorded_execution_seal",
        lambda _seal: "a" * 40,
    )
    monkeypatch.setattr(
        p09,
        "_bind_git_commit",
        lambda commit, _paths: (
            bindings["OFF"] if commit == p09.OFF_COMMIT else bindings["ON"]
        ),
    )
    return path, report, requests, bindings


def _rewrite(path: Path, report: dict) -> None:
    report["checksum_sha256"] = p09._checksum(report)
    path.write_bytes(p09.canonical_json_bytes(report) + b"\n")


def test_adversarial_fixture_freezes_three_rejections() -> None:
    fixture = _fixture()
    assert fixture["preregistration_id"] == p09.PREREGISTRATION_ID
    assert [attack["attack_id"] for attack in fixture["attacks"]] == [
        "arm_source_binding_wrong_condition",
        "worker_isolation_self_attestation",
        "post_execution_source_mutation",
    ]
    assert {attack["expected_result"] for attack in fixture["attacks"]} == {
        "REJECT"
    }


def test_v2_seal_binds_reused_v1_evaluator_dependency() -> None:
    dependencies = {
        "scripts/atanor_pattern09_public_speech_capability_eval.py": (
            "1b387baba85135775ccabe63faebb0190e9c7d53"
        ),
        "packages/eval_evidence/receipt.py": "1b387bab",
    }
    preregistration = json.loads(p09.PREREG.read_text(encoding="utf-8"))
    binding = p09.bind_files(p09.REPO, p09._EVALUATOR_PATHS)

    for dependency, reference in dependencies.items():
        assert dependency in p09._EVALUATOR_PATHS
        assert dependency in p09._EXECUTION_SEAL_PATHS
        assert dependency in preregistration["evaluator"]["paths"]
        assert any(
            item["path"] == dependency for item in binding["files"]
        )
        assert (p09.REPO / dependency).read_bytes() == p09._v1._git_bytes(
            reference, dependency
        )


def test_forensic_v1_verifier_accepted_binding_and_isolation_tamper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reproduce the two checksum-resealed v1 bypasses without touching v1."""
    report_path = tmp_path / "pattern09-v1-forensic.json"
    attempt_path = tmp_path / "pattern09-v1-forensic.attempt.json"
    failure_path = tmp_path / "pattern09-v1-forensic.failure.json"
    report = json.loads(p09.V1_REPORT.read_text(encoding="utf-8"))
    report["arms"][0]["source_binding"] = copy.deepcopy(
        report["on_candidate"]
    )
    raw = report["arms"][0]["result"]
    raw["application_isolation"]["global_app_main_loaded"] = True
    raw["repo_import_closure"]["outside_source_repo_modules"] = [
        "app.main"
    ]
    raw["network_guard"]["external_socket_connect_blocked"] = False
    report["checksum_sha256"] = p09._v1._checksum(report)
    report_path.write_bytes(p09.canonical_json_bytes(report) + b"\n")
    attempt_path.write_bytes(p09.V1_ATTEMPT.read_bytes())
    monkeypatch.setattr(p09._v1, "REPORT", report_path)
    monkeypatch.setattr(p09._v1, "ATTEMPT", attempt_path)
    monkeypatch.setattr(p09._v1, "FAILURE", failure_path)

    result = p09._V1_VERIFY(report_path)

    assert result["valid"] is True
    assert result["capability_lift_established"] is True


def test_verifier_rejects_arm_binding_for_wrong_condition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path, report, _, bindings = _install_receipt_probe(
        monkeypatch, tmp_path
    )
    report["arms"][0]["source_binding"] = bindings["ON"]
    _rewrite(path, report)

    with pytest.raises(BenchmarkEvidenceError, match="binding/condition"):
        p09._verify_v2_receipts(path)


def test_verifier_revalidates_raw_worker_isolation_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path, report, _, _ = _install_receipt_probe(monkeypatch, tmp_path)
    raw = report["arms"][0]["result"]
    raw["application_isolation"]["global_app_main_loaded"] = True
    raw["repo_import_closure"]["outside_source_repo_modules"] = [
        "app.main"
    ]
    raw["network_guard"]["external_socket_connect_blocked"] = False
    _rewrite(path, report)

    with pytest.raises(BenchmarkEvidenceError, match="identity/isolation"):
        p09._verify_v2_receipts(path)


def test_verifier_accepts_valid_durable_worker_and_rebind_receipts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path, _, _, _ = _install_receipt_probe(monkeypatch, tmp_path)
    p09._verify_v2_receipts(path)


def test_runtime_validator_normalizes_deleted_temp_identity_durably() -> None:
    request = _requests()[0]
    binding = {
        "files": [{"path": "off", "bytes": 1, "sha256": "0" * 64}],
        "content_sha256": "1" * 64,
    }
    raw = _worker_result(request, binding)
    raw.pop(p09._RECEIPT_FIELD)
    raw["source_root"] = str(p09.REPO)
    raw["loaded_modules"] = {
        name: str((p09.REPO / relative).resolve(strict=True))
        for name, relative in p09._DURABLE_MODULES.items()
    }
    key = str(p09.REPO.resolve(strict=True))
    p09._ACTIVE_ARMS[key] = {
        "condition": "OFF",
        "before": binding,
        "worker_result": None,
    }
    try:
        durable = p09.validate_worker_result(raw, request, p09.REPO)
    finally:
        p09._ACTIVE_ARMS.pop(key, None)

    assert durable["source_root"] == {
        "kind": "ephemeral_arm_root",
        "condition": "OFF",
    }
    assert durable["loaded_modules"] == p09._DURABLE_MODULES
    assert not any(
        str(p09.REPO) in path for path in durable["loaded_modules"].values()
    )


def test_run_rebinds_arm_source_after_worker_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    assert fixture["attacks"][2]["attack_id"] == (
        "post_execution_source_mutation"
    )
    arm_root = tmp_path / "arm"
    for relative in p09._CANDIDATE_PATHS:
        destination = arm_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((p09.REPO / relative).read_bytes())

    @contextlib.contextmanager
    def arm_source(_condition: str, _sealed_head: str):
        yield arm_root

    monkeypatch.setattr(p09, "_V1_TEMPORARY_ARM_SOURCE", arm_source)
    with pytest.raises(BenchmarkEvidenceError, match="changed after execution"):
        with p09._temporary_arm_source("OFF", "a" * 40) as source_root:
            state = p09._ACTIVE_ARMS[str(source_root.resolve(strict=True))]
            state["worker_result"] = {}
            target = source_root / p09._CANDIDATE_PATHS[0]
            target.write_bytes(target.read_bytes() + b"\n# mutation\n")


def test_run_records_matching_before_and_after_source_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    arm_root = tmp_path / "stable-arm"
    for relative in p09._CANDIDATE_PATHS:
        destination = arm_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((p09.REPO / relative).read_bytes())

    @contextlib.contextmanager
    def arm_source(_condition: str, _sealed_head: str):
        yield arm_root

    monkeypatch.setattr(p09, "_V1_TEMPORARY_ARM_SOURCE", arm_source)
    worker_result: dict = {}
    with p09._temporary_arm_source("ON", "a" * 40) as source_root:
        state = p09._ACTIVE_ARMS[str(source_root.resolve(strict=True))]
        state["worker_result"] = worker_result

    receipt = worker_result[p09._RECEIPT_FIELD]
    assert receipt["condition"] == "ON"
    assert receipt["same_before_after"] is True
    assert receipt["before"] == receipt["after"]


def test_v1_evaluator_and_receipts_remain_byte_identical() -> None:
    expected = {
        "scripts/atanor_pattern09_public_speech_capability_eval.py": (
            "1b387baba85135775ccabe63faebb0190e9c7d53"
        ),
        "scripts/atanor_pattern09_public_speech_capability_worker.py": (
            "1b387baba85135775ccabe63faebb0190e9c7d53"
        ),
        "scripts/tests/test_atanor_pattern09_public_speech_capability_eval.py": (
            "1b387baba85135775ccabe63faebb0190e9c7d53"
        ),
        (
            "reports/benchmarks/"
            "atanor_pattern09_public_speech_capability_v1_20260727.json"
        ): "8b703e1b",
        (
            "reports/benchmarks/"
            "atanor_pattern09_public_speech_capability_v1_20260727.attempt.json"
        ): "8b703e1b",
    }
    for relative, commit in expected.items():
        assert (p09.REPO / relative).read_bytes() == p09._v1._git_bytes(
            commit, relative
        )
