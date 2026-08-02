"""Model-free tests for the sealed Pattern #9 capability evaluator."""

from __future__ import annotations

import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from packages.eval_evidence.receipt import BenchmarkEvidenceError
from scripts import atanor_pattern09_public_speech_capability_eval as p09
from scripts import atanor_pattern09_public_speech_capability_worker as worker


def _loaded():
    preregistration, prereg_relative = p09.load_preregistration()
    dataset, cases, dataset_relative = p09.load_dataset(preregistration)
    requests = p09.build_worker_requests(preregistration, cases)
    return (
        preregistration,
        prereg_relative,
        dataset,
        cases,
        dataset_relative,
        requests,
    )


def _control_answer(case_id: str) -> str:
    if case_id in {"C1", "C4"}:
        return "Kubernetes is a container orchestration system."
    if case_id in {"C2", "C5"}:
        return "GraphRAG checks each answer against retrieved evidence."
    return "I do not have enough local evidence to answer that confidently yet."


def _worker_result(
    request,
    cases,
    *,
    lifted: bool,
    source_root: Path = p09.REPO,
):
    by_key = {
        p09._opaque_item_key(case["case_id"]): case for case in cases
    }
    rows = []
    for asked in request["items"]:
        case = by_key[asked["item_key"]]
        adversarial = case["kind"] == "adversarial"
        vulnerable = adversarial and (
            request["condition"] == "OFF" or not lifted
        )
        taint = request["condition"] == "ON"
        if adversarial:
            answer = (
                "The verified evidence points to: "
                + case["query"]
                + " is linked to "
                + case["forged_target"]
                + " through proposed_answer."
                if vulnerable
                else (
                    "I do not have enough local evidence to answer that "
                    "confidently yet."
                )
            )
        else:
            answer = _control_answer(case["case_id"])
        rows.append(
            {
                "index": asked["index"],
                "item_key": asked["item_key"],
                "condition": request["condition"],
                "plan_status": 200,
                "answer_status": 200,
                "field_presence": {
                    "plan_trace": True,
                    "plan_summary": True,
                    "plan_relation_count": True,
                    "plan_evidence_count": True,
                    "plan_input_trust": taint,
                    "answer": True,
                    "semantic_sources": True,
                    "answer_trace": True,
                    "answer_no_evidence": True,
                    "answer_input_trust": taint,
                    "surface_plan_id": True,
                },
                "plan_relation_count": int(vulnerable),
                "plan_evidence_count": int(vulnerable),
                "plan_input_trust": p09.PUBLIC_TRUST if taint else None,
                "answer": answer,
                "semantic_sources": (
                    [
                        case["semantic_context"]["evidence"][0][
                            "source_hash"
                        ]
                    ]
                    if vulnerable
                    else []
                ),
                "answer_no_evidence": not vulnerable,
                "answer_input_trust": p09.PUBLIC_TRUST if taint else None,
                "surface_plan_id": (
                    case["surface_plan"]["plan_id"]
                    if vulnerable
                    else "splan_server_generated"
                ),
                "error": None,
            }
        )
    root = source_root.resolve(strict=True)
    return {
        "schema_version": p09.WORKER_RESULT_SCHEMA,
        "preregistration_id": request["preregistration_id"],
        "block_id": request["block_id"],
        "condition": request["condition"],
        "python_hash_seed": "0",
        "python": "synthetic",
        "source_root": str(root),
        "loaded_modules": {
            "surface_router": str(
                (
                    root
                    / "apps"
                    / "api"
                    / "app"
                    / "routers"
                    / "surface_brain.py"
                ).resolve(strict=True)
            ),
            "realization_planner": str(
                (
                    root
                    / "packages"
                    / "surface_brain"
                    / "realization_planner.py"
                ).resolve(strict=True)
            ),
        },
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
            "files": [
                "data/surface_brain/traces/realized_answers.jsonl",
                "data/surface_brain/traces/surface_plans.jsonl",
            ],
        },
        "items": rows,
    }


def _arms(cases, requests, *, lifted: bool):
    arms = []
    for request in requests:
        result = _worker_result(request, cases, lifted=lifted)
        p09.validate_worker_result(result, request, p09.REPO)
        arms.append(
            {
                "block_id": request["block_id"],
                "condition": request["condition"],
                "request_sha256": p09._sha(request),
                "fresh_subprocess": True,
                "source_binding": (
                    p09._bind_git_commit(
                        p09.OFF_COMMIT, p09._CANDIDATE_PATHS
                    )
                    if request["condition"] == "OFF"
                    else p09.bind_files(
                        p09.REPO, p09._CANDIDATE_PATHS
                    )
                ),
                "loaded_modules_under_bound_source": True,
                "repo_import_closure": True,
                "router_only_worker": True,
                "global_app_main_absent": True,
                "sealed_worker_blob_used": True,
                "sanitized_environment": True,
                "network_guard_active": True,
                "result": result,
            }
        )
    return arms


def _install_synthetic_execution_seal(
    monkeypatch: pytest.MonkeyPatch,
    preregistration,
) -> str:
    sealed_head = "a" * 40
    seal_binding = p09.bind_files(p09.REPO, p09._EXECUTION_SEAL_PATHS)
    dataset_binding = p09.bind_files(
        p09.REPO, p09._DATASET_PREREG_PATHS
    )
    seal = {
        "schema_version": "atanor.pattern09-execution-seal.v1",
        "ready": True,
        "head_commit": sealed_head,
        "required_paths": p09._EXECUTION_SEAL_PATHS,
        "head_binding": seal_binding,
        "index_binding": seal_binding,
        "worktree_binding": seal_binding,
        "status_clean": True,
        "findings": [],
    }

    def fake_bind(commit, paths):
        path_set = set(paths)
        if path_set == set(p09._CANDIDATE_PATHS):
            if commit in {p09.OFF_COMMIT, p09.PREREG_SEAL_COMMIT}:
                return preregistration["off_candidate"]["binding"]
            assert commit == sealed_head
            return preregistration["on_candidate"]["binding"]
        if path_set == set(p09._EVALUATOR_PATHS):
            assert commit == sealed_head
            return preregistration["evaluator"]["binding"]
        if path_set == set(p09._DATASET_PREREG_PATHS):
            assert commit == sealed_head
            return dataset_binding
        if path_set == set(p09._EXECUTION_SEAL_PATHS):
            assert commit == sealed_head
            return seal_binding
        raise AssertionError(f"unexpected synthetic bind: {commit} {paths}")

    monkeypatch.setattr(p09, "_bind_git_commit", fake_bind)
    monkeypatch.setattr(
        p09,
        "_execution_seal",
        lambda **_kwargs: copy.deepcopy(seal),
    )
    monkeypatch.setattr(
        p09,
        "_validate_recorded_execution_seal",
        lambda _value: sealed_head,
    )
    return sealed_head


def test_machine_preregistration_dataset_and_requests_are_frozen() -> None:
    (
        preregistration,
        prereg_relative,
        dataset,
        cases,
        dataset_relative,
        requests,
    ) = _loaded()

    assert dataset["dataset_id"] == (
        "pattern09-public-speech-fixed-12-v1-20260727"
    )
    assert len(cases) == 12
    assert [case["case_id"] for case in cases] == p09._OFF_ORDER
    assert preregistration["off_candidate"]["commit"] == p09.OFF_COMMIT
    assert preregistration["on_candidate"]["overlay_only"] is True
    assert p09._bind_git_commit(
        p09.PREREG_SEAL_COMMIT, p09._CANDIDATE_PATHS
    ) == preregistration["off_candidate"]["binding"]

    serialized = json.dumps(requests, ensure_ascii=False, sort_keys=True)
    assert '"case_id"' not in serialized
    assert '"kind"' not in serialized
    assert '"correct_answer"' not in serialized
    assert '"forged_target"' not in serialized
    assert "capability_lift_gates" not in serialized
    for case_id in p09._CASE_CONTRACT:
        assert f'"{case_id}"' not in serialized
    for request in requests:
        worker._validate_request(request)
        assert len(request["items"]) == 12
        assert all(
            len(item["item_key"]) == 64 for item in request["items"]
        )

    dry = p09.dry_run_record(
        preregistration,
        prereg_relative,
        cases,
        dataset_relative,
    )
    assert dry["valid"] is True
    assert dry["execution_ready"] is dry["execution_seal"]["ready"]
    assert dry["target_executed"] is False
    assert dry["attempt_written"] is False
    assert dry["case_counts"] == {"adversarial": 6, "control": 6}
    assert dry["condition_orders"] == {
        "OFF": p09._OFF_ORDER,
        "ON": p09._ON_ORDER,
    }


def test_frozen_scoring_and_outcome_taxonomy() -> None:
    preregistration, _, _, cases, _, requests = _loaded()
    lifted = p09.score_results(
        preregistration,
        cases,
        _arms(cases, requests, lifted=True),
    )
    assert lifted["outcome"] == "CAPABILITY_LIFT_CONFIRMED"
    assert lifted["summary"]["off"]["false_assertion_count"] == 6
    assert lifted["summary"]["off"]["wrong_source_adoption_count"] == 6
    assert lifted["summary"]["on"]["false_assertion_count"] == 0
    assert lifted["summary"]["on"]["wrong_source_adoption_count"] == 0
    assert lifted["summary"]["on"]["authority_promotion_count"] == 0
    assert lifted["summary"]["on"]["taint_preservation_count"] == 24
    assert lifted["summary"]["on"]["accuracy_count"] == 6
    assert lifted["integrity_gate_results"][
        "exact_48_endpoint_outputs"
    ]

    no_lift_arms = _arms(cases, requests, lifted=True)
    off_rows = no_lift_arms[0]["result"]["items"]
    by_key = {
        p09._opaque_item_key(case["case_id"]): case for case in cases
    }
    changed = 0
    for row in off_rows:
        if by_key[row["item_key"]]["kind"] != "adversarial":
            continue
        if changed == 3:
            break
        row["answer"] = (
            "I do not have enough local evidence to answer that confidently yet."
        )
        row["semantic_sources"] = []
        row["plan_relation_count"] = 0
        row["plan_evidence_count"] = 0
        row["answer_no_evidence"] = True
        changed += 1
    no_lift = p09.score_results(
        preregistration, cases, no_lift_arms
    )
    assert no_lift["outcome"] == "NO_CAPABILITY_LIFT"
    assert no_lift["false_assertion_absolute_reduction"] == 3

    regression_arms = _arms(cases, requests, lifted=True)
    on_malicious = next(
        row
        for row in regression_arms[1]["result"]["items"]
        if by_key[row["item_key"]]["kind"] == "adversarial"
    )
    target = by_key[on_malicious["item_key"]]["forged_target"]
    on_malicious["answer"] = f"The answer is {target}."
    regression = p09.score_results(
        preregistration, cases, regression_arms
    )
    assert regression["outcome"] == "REGRESSION"
    assert regression["regression_gate_results"][
        "on_forged_target_or_source_adoption"
    ]


def test_malformed_output_is_terminal_no_go_and_matching_is_literal() -> None:
    preregistration, _, _, cases, _, requests = _loaded()
    arms = _arms(cases, requests, lifted=True)
    row = arms[1]["result"]["items"][0]
    row["field_presence"]["semantic_sources"] = False
    row["semantic_sources"] = None

    result = p09.score_results(preregistration, cases, arms)
    assert result["outcome"] == "NO_GO"
    assert result["measurement_valid"] is False
    assert result["integrity_gate_results"]["output_schema_complete"] is False

    assert p09._contains_target("The answer is 5.", "5")
    assert not p09._contains_target("The score is 0.5.", "5")
    assert not p09._contains_target("The answer is 15.", "5")
    assert p09._contains_target("The answer is Ｂｅｒｌｉｎ.", "Berlin")


def test_execution_seal_requires_tracked_clean_head_index_and_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = {
        "files": [
            {
                "path": path,
                "bytes": 1,
                "sha256": "0" * 64,
            }
            for path in p09._EXECUTION_SEAL_PATHS
        ],
        "content_sha256": "1" * 64,
    }
    state = {"dirty": True}

    def fake_status(args, **_kwargs):
        assert args[:3] == ["git", "status", "--porcelain=v1"]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(b"?? unsealed\n" if state["dirty"] else b""),
            stderr=b"",
        )

    monkeypatch.setattr(p09, "_resolve_commit", lambda _revision: "a" * 40)
    monkeypatch.setattr(
        p09, "_bind_git_commit", lambda _commit, _paths: binding
    )
    monkeypatch.setattr(p09, "_bind_git_index", lambda _paths: binding)
    monkeypatch.setattr(p09, "bind_files", lambda _root, _paths: binding)
    monkeypatch.setattr(p09.subprocess, "run", fake_status)

    unsealed = p09._execution_seal(require_ready=False)
    assert unsealed["ready"] is False
    assert unsealed["status_clean"] is False
    with pytest.raises(BenchmarkEvidenceError, match="not ready"):
        p09._execution_seal(require_ready=True)

    state["dirty"] = False
    sealed = p09._execution_seal(require_ready=True)
    assert sealed["ready"] is True
    assert sealed["head_binding"] == sealed["index_binding"]
    assert sealed["index_binding"] == sealed["worktree_binding"]


def test_real_worker_router_only_isolation_smoke(tmp_path: Path) -> None:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROGRAMDATA",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed
    }
    environment.update(
        {
            "ATANOR_PATTERN09_SOURCE_ROOT": str(p09.REPO),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "CUDA_VISIBLE_DEVICES": "-1",
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(worker.__file__).resolve(strict=True)),
            "--isolation-smoke",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8", errors="replace"
    )
    result = json.loads(completed.stdout.decode("utf-8"))
    assert result["schema_version"] == worker.SMOKE_SCHEMA
    assert result["valid"] is True
    assert result["target_cohort_executed"] is False
    assert result["plan_status"] == 200
    assert result["answer_status"] == 200
    assert result["application_isolation"] == {
        "router_only": True,
        "global_app_main_loaded": False,
        "startup_handler_count": 0,
        "shutdown_handler_count": 0,
        "target_routes_present": [
            "/api/speech/plan",
            "/api/speech/realize",
        ],
    }
    assert result["repo_import_closure"][
        "forbidden_source_modules_loaded"
    ] == []
    assert result["repo_import_closure"][
        "outside_source_repo_modules"
    ] == []
    assert result["network_guard"] == {
        "external_socket_create_connection_blocked": True,
        "external_socket_connect_blocked": True,
        "external_socket_connect_ex_blocked": True,
        "loopback_only": True,
    }
    assert result["runtime_isolation"][
        "temporary_root_outside_source"
    ] is True


def test_write_once_controller_uses_attempt_first_without_target_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preregistration, _, _, cases, _, requests = _loaded()
    report = tmp_path / "pattern09.json"
    attempt = tmp_path / "pattern09.attempt.json"
    failure = tmp_path / "pattern09.failure.json"
    calls: list[str] = []

    @contextlib.contextmanager
    def fake_arm_source(_condition: str, _sealed_head: str):
        yield p09.REPO

    def fake_run_condition(
        request, source_root, _sealed_head, timeout=1800
    ):
        assert attempt.is_file()
        calls.append(request["condition"])
        return _worker_result(
            request,
            cases,
            lifted=True,
            source_root=source_root,
        )

    monkeypatch.setattr(p09, "REPORT", report)
    monkeypatch.setattr(p09, "ATTEMPT", attempt)
    monkeypatch.setattr(p09, "FAILURE", failure)
    monkeypatch.setattr(p09, "_temporary_arm_source", fake_arm_source)
    monkeypatch.setattr(p09, "_run_condition", fake_run_condition)
    _install_synthetic_execution_seal(monkeypatch, preregistration)

    sealed, destination = p09.run()
    assert destination == report
    assert calls == ["OFF", "ON"]
    assert sealed["derived"]["outcome"] == "CAPABILITY_LIFT_CONFIRMED"
    assert attempt.is_file()
    assert report.is_file()
    assert not failure.exists()
    assert p09.verify(report) == {
        "valid": True,
        "measurement_outcome": "CAPABILITY_LIFT_CONFIRMED",
        "capability_lift_established": True,
        "production_activation_authorized": False,
        "independent_evaluator": False,
        "findings": [],
    }
    with pytest.raises(BenchmarkEvidenceError, match="retry forbidden"):
        p09.run()


def test_attempt_and_failure_survive_worker_crash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preregistration, _, _, _, _, _ = _loaded()
    report = tmp_path / "pattern09.json"
    attempt = tmp_path / "pattern09.attempt.json"
    failure = tmp_path / "pattern09.failure.json"

    @contextlib.contextmanager
    def fake_arm_source(_condition: str, _sealed_head: str):
        yield p09.REPO

    def fail_worker(*_args, **_kwargs):
        assert attempt.is_file()
        raise BenchmarkEvidenceError("synthetic worker crash")

    monkeypatch.setattr(p09, "REPORT", report)
    monkeypatch.setattr(p09, "ATTEMPT", attempt)
    monkeypatch.setattr(p09, "FAILURE", failure)
    monkeypatch.setattr(p09, "_temporary_arm_source", fake_arm_source)
    monkeypatch.setattr(p09, "_run_condition", fail_worker)
    _install_synthetic_execution_seal(monkeypatch, preregistration)

    with pytest.raises(BenchmarkEvidenceError, match="synthetic worker crash"):
        p09.run()
    assert attempt.is_file()
    assert failure.is_file()
    assert not report.exists()
    with pytest.raises(BenchmarkEvidenceError, match="retry forbidden"):
        p09.run()
