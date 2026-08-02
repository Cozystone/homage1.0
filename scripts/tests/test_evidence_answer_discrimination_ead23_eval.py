"""Model-free controls for the preregistered EAD-2/3 one-shot evaluator."""
from __future__ import annotations

import copy
import hashlib
import json
import re

import pytest

from packages.eval_evidence.receipt import BenchmarkEvidenceError, bind_files
from scripts import evidence_answer_discrimination_ead23_eval as ead
from scripts import evidence_answer_discrimination_ead23_worker as worker


def _loaded():
    preregistration, prereg_relative = ead.load_preregistration()
    dataset, cases, dataset_relative = ead.load_dataset(preregistration)
    requests = ead.build_worker_requests(preregistration, cases)
    return (
        preregistration,
        prereg_relative,
        dataset,
        cases,
        dataset_relative,
        requests,
    )


def _worker_result(request, grounded_by_key):
    rows = []
    for asked in request["items"]:
        title = f"live:{asked['source_id']}"
        grounded = bool(grounded_by_key[asked["item_key"]])
        rows.append(
            {
                "index": asked["index"],
                "item_key": asked["item_key"],
                "condition": request["condition"],
                "answer": asked["proposed_answer"],
                "grounded": grounded,
                "confidence": 1.0 if grounded else 0.0,
                "grounding_reason": (
                    "synthetic_test_accept" if grounded else "synthetic_test_reject"
                ),
                "grounding_signals": {
                    "evidence_index": 0,
                    "evidence_count": 1,
                },
                "used_live": True,
                "support": [title],
                "evidence": [
                    {
                        "origin": "live",
                        "title": title,
                        "verified": True,
                        "candidate_index": 0,
                    }
                ],
                "type": "span",
                "selected_source_id": asked["source_id"],
                "selected_fact_sha256": hashlib.sha256(
                    asked["evidence"].encode("utf-8")
                ).hexdigest(),
                "error": None,
                "latency_ms": 0.01,
            }
        )
    return {
        "schema_version": ead.WORKER_RESULT_SCHEMA,
        "block_id": request["block_id"],
        "condition": request["condition"],
        "device": "cpu",
        "python_hash_seed": "0",
        "versions": {"fixture": "model-free"},
        "temp_isolation": {
            "temp_root_outside_repository": True,
            "cortex_items": 0,
            "miss_log_written": False,
        },
        "items": rows,
    }


def _arms(cases, requests, *, on_policy):
    by_opaque = {
        ead._opaque_item_key(case["item_key"]): case
        for case in cases
    }
    arms = []
    for spec, request in zip(ead._BLOCKS, requests):
        if request["condition"] == "OFF":
            decisions = {
                asked["item_key"]: True
                for asked in request["items"]
            }
        else:
            decisions = {
                asked["item_key"]: bool(on_policy(by_opaque[asked["item_key"]]))
                for asked in request["items"]
            }
        result = _worker_result(request, decisions)
        ead.validate_worker_result(result, request)
        arms.append(
            {
                "block_id": spec[0],
                "stratum": spec[1],
                "condition": spec[2],
                "order": spec[3],
                "request_sha256": ead._sha(request),
                "result": result,
            }
        )
    return arms


def test_preregistration_dataset_and_dry_run_are_frozen_and_model_free() -> None:
    (
        preregistration,
        prereg_relative,
        dataset,
        cases,
        dataset_relative,
        requests,
    ) = _loaded()

    assert dataset["case_content_sha256"] == (
        "0e7cc787d8a61fc2d0aaec5f9db261503b387ceaa5c6549e334bcaff0b3d291c"
    )
    assert dataset["case_order_sha256"] == (
        "b0f7552a7b0185a92d3cdcffd4f7ad7cbf6ebb66caa41656f948545d9089c3e1"
    )
    assert preregistration["candidate"]["content_sha256"] == (
        "819e0ff07cfb968109d7d219e6bb86c35c9b2c21565af8263b13c3486d6f0425"
    )
    assert bind_files(
        ead.REPO, preregistration["candidate"]["paths"]
    )["content_sha256"] == preregistration["candidate"]["content_sha256"]
    assert len(cases) == 60
    assert len(requests) == 4

    record = ead.dry_run_record(
        preregistration,
        prereg_relative,
        cases,
        dataset_relative,
    )
    assert record["valid"] is True
    assert record["candidate_executed"] is False
    assert record["checkpoint_loaded"] is False
    assert record["case_counts"] == {
        "POS": 24,
        "WRONG_SOURCE": 24,
        "UNKNOWN": 12,
    }
    assert record["block_counts"] == {
        "A_OFF": 30,
        "B_ON": 30,
        "A_ON": 30,
        "B_OFF": 30,
    }


def test_worker_requests_are_counterbalanced_and_label_blind() -> None:
    preregistration, _, _, cases, _, requests = _loaded()
    raw_keys = {case["item_key"] for case in cases}
    raw_sources = {case["source_id"] for case in cases}
    seen = {"OFF": set(), "ON": set()}

    assert ead._sha(
        [
            {
                "item_key": key,
                "condition_order": ["OFF", "ON"] if index < 30 else ["ON", "OFF"],
            }
            for index, key in enumerate(
                sorted(
                    raw_keys,
                    key=lambda value: (
                        hashlib.sha256(value.encode("utf-8")).hexdigest(),
                        value,
                    ),
                )
            )
        ]
    ) == preregistration["protocol"]["condition_order_sha256"]

    for request in requests:
        worker._validate_request(request)
        serialized = json.dumps(request, sort_keys=True).casefold()
        for raw in raw_keys | raw_sources:
            assert raw.casefold() not in serialized
        assert '"kind"' not in serialized
        assert '"gold_answer"' not in serialized
        assert '"negative_mode"' not in serialized
        assert "capability_lift_gates" not in serialized
        for item in request["items"]:
            assert re.fullmatch(r"[0-9a-f]{64}", item["item_key"])
            assert re.fullmatch(r"[0-9a-f]{64}", item["source_id"])
            seen[request["condition"]].add(item["item_key"])

    expected = {ead._opaque_item_key(case["item_key"]) for case in cases}
    assert seen == {"OFF": expected, "ON": expected}


def test_preregistered_outcome_taxonomy_and_exact_mcnemar() -> None:
    preregistration, _, _, cases, _, requests = _loaded()

    lifted = ead.score_results(
        preregistration,
        cases,
        _arms(cases, requests, on_policy=lambda case: case["kind"] == "POS"),
    )
    assert lifted["outcome"] == "CAPABILITY_LIFT_CONFIRMED"
    assert lifted["summary"]["off"]["total_accept"] == 60
    assert lifted["summary"]["on"]["supported_accept"] == 24
    assert lifted["summary"]["on"]["aggregate_hard_negative_accept"] == 0
    assert lifted["balanced_decision_accuracy_lift"] == 0.5
    assert lifted["mcnemar"] == {
        "off_only_correct_b": 0,
        "on_only_correct_c": 36,
        "p_two_sided": ead._mcnemar_exact(0, 36),
    }
    assert lifted["mcnemar"]["p_two_sided"] <= 0.01

    no_lift = ead.score_results(
        preregistration,
        cases,
        _arms(cases, requests, on_policy=lambda _case: True),
    )
    assert no_lift["outcome"] == "NO_LIFT"
    assert no_lift["capability_lift_confirmed"] is False

    regression = ead.score_results(
        preregistration,
        cases,
        _arms(cases, requests, on_policy=lambda _case: False),
    )
    assert regression["outcome"] == "REGRESSION"
    assert regression["regression_gate_results"]["supported_accept_regression"]


def test_treatment_parity_failure_is_no_go() -> None:
    preregistration, _, _, cases, _, requests = _loaded()
    arms = _arms(cases, requests, on_policy=lambda case: case["kind"] == "POS")
    on_arm = next(arm for arm in arms if arm["condition"] == "ON")
    on_arm["result"]["items"][0]["support"] = ["live:tampered"]

    result = ead.score_results(preregistration, cases, arms)
    assert result["outcome"] == "NO_GO"
    assert result["measurement_valid"] is False
    assert result["integrity_gate_results"]["treatment_isolation_exact"] is False


def test_write_once_full_run_and_verifier_are_model_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    preregistration, _, _, cases, _, requests = _loaded()
    fake_by_block = {
        request["block_id"]: _worker_result(
            request,
            {
                asked["item_key"]: (
                    next(
                        case
                        for case in cases
                        if ead._opaque_item_key(case["item_key"]) == asked["item_key"]
                    )["kind"]
                    == "POS"
                )
                if request["condition"] == "ON"
                else True
                for asked in request["items"]
            },
        )
        for request in requests
    }
    report = tmp_path / "ead23-report.json"
    attempt = tmp_path / "ead23-report.attempt.json"
    failure = tmp_path / "ead23-report.failure.json"
    calls = []

    def fake_worker(request, timeout=3600):
        calls.append((request["block_id"], timeout))
        return copy.deepcopy(fake_by_block[request["block_id"]])

    monkeypatch.setattr(ead, "REPORT", report)
    monkeypatch.setattr(ead, "ATTEMPT", attempt)
    monkeypatch.setattr(ead, "FAILURE", failure)
    monkeypatch.setattr(ead, "_run_worker", fake_worker)

    sealed, destination = ead.run()
    assert destination == report
    assert sealed["derived"]["outcome"] == "CAPABILITY_LIFT_CONFIRMED"
    assert [block for block, _timeout in calls] == [
        "A_OFF",
        "B_ON",
        "A_ON",
        "B_OFF",
    ]
    assert report.is_file()
    assert attempt.is_file()
    assert not failure.exists()
    assert ead.verify(report) == {
        "valid": True,
        "measurement_outcome": "CAPABILITY_LIFT_CONFIRMED",
        "capability_lift_established": True,
        "production_activation_authorized": False,
        "authenticity_established": False,
        "findings": [],
    }
    attempt_value = json.loads(attempt.read_text(encoding="utf-8"))
    attempt_value["unregistered_field"] = True
    attempt.write_text(
        json.dumps(attempt_value, ensure_ascii=False),
        encoding="utf-8",
    )
    invalid = ead.verify(report)
    assert invalid["valid"] is False
    assert invalid["capability_lift_established"] is False
    assert invalid["findings"] == ["EAD-3 attempt/failure receipt mismatch"]
    with pytest.raises(BenchmarkEvidenceError, match="retry forbidden"):
        ead.run()
