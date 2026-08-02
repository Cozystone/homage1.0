from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import BenchmarkEvidenceError
from scripts import evidence_answer_discrimination_preregistered_eval as E
from scripts import evidence_answer_discrimination_worker as W


def _loaded():
    preregistration, relative = E.load_preregistration(E.DEFAULT_PREREG)
    cases = E.reconstruct_cases(preregistration)
    return preregistration, relative, cases


def _signals(request):
    rows = []
    preregistration, _relative, cases = _loaded()
    by_key = {case["item_key"]: case for case in cases}
    for index, requested in enumerate(request["items"]):
        positive = by_key[requested["item_key"]]["label"]
        if positive:
            p_ans, p_support, p_nei, p_refute = 0.9, 0.9, 0.05, 0.05
        else:
            p_ans, p_support, p_nei, p_refute = 0.1, 0.05, 0.1, 0.85
        rows.append(
            {
                "index": index,
                "item_key": requested["item_key"],
                "p_ans": p_ans,
                "p_support": p_support,
                "p_nei": p_nei,
                "p_refute": p_refute,
                "p_sup_net": p_support - p_refute,
            }
        )
    return {
        "schema_version": W.RESULT_SCHEMA,
        "device": "cpu",
        "python_hash_seed": "0",
        "versions": {"python": "test", "torch": "test", "numpy": "test"},
        "items": rows,
    }


def test_frozen_inputs_and_case_census_validate_without_model():
    preregistration, relative, cases = _loaded()
    dry = E.dry_run_record(preregistration, relative)
    assert dry["candidate_executed"] is False
    assert dry["live_path_imported"] is False
    assert dry["candidate_matches_preregistered_digest"] is True
    assert dry["case_counts"] == {"POS": 20, "WRONG_SOURCE": 20, "UNKNOWN": 12}
    assert len(cases) == 52
    assert len({case["item_key"] for case in cases}) == 52
    assert {case["fold"] for case in cases} == set(range(5))
    assert [sum(case["fold"] == fold for case in cases) for fold in range(5)] == [
        10,
        10,
        11,
        10,
        11,
    ]


def test_worker_boundary_has_no_labels_gates_folds_or_gold():
    preregistration, _relative, cases = _loaded()
    forbidden = {"label", "kind", "gate", "gates", "fold", "threshold", "gold"}
    for replay in preregistration["protocol"]["replays"]:
        request = E.build_worker_request(preregistration, cases, replay["order"])
        assert forbidden.isdisjoint(request)
        assert all(forbidden.isdisjoint(row) for row in request["items"])
        assert all(frozenset(row) == E._WORKER_REQUEST_ITEM_FIELDS for row in request["items"])
        keys = [row["item_key"] for row in request["items"]]
        assert keys == (
            sorted(keys) if replay["order"] == "forward" else sorted(keys, reverse=True)
        )
        W.validate_request(request)
    for case in cases:
        visible = {
            field: case[field]
            for field in ("question", "evidence", "answer_start", "answer_end")
        }
        expected = E.hashlib.sha256(E.canonical_json_bytes(visible)).hexdigest()
        assert case["item_key"] == expected


def test_worker_rejects_noncontiguous_or_extra_fields():
    preregistration, _relative, cases = _loaded()
    request = E.build_worker_request(preregistration, cases, "forward")
    broken = {**request, "items": [dict(row) for row in request["items"]]}
    broken["items"][0]["answer_end"] = len(broken["items"][0]["evidence"]) + 1
    with pytest.raises(BenchmarkEvidenceError, match="exact contiguous"):
        W.validate_request(broken)
    broken = {**request, "items": [dict(row) for row in request["items"]]}
    broken["items"][0]["label"] = True
    with pytest.raises(BenchmarkEvidenceError, match="fields mismatch"):
        W.validate_request(broken)


def test_worker_checks_cpu_environment_before_model_import(
    monkeypatch: pytest.MonkeyPatch,
):
    preregistration, _relative, cases = _loaded()
    request = E.build_worker_request(preregistration, cases, "forward")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    with pytest.raises(BenchmarkEvidenceError, match="before torch import"):
        W.evaluate(request)


def test_public_run_has_no_runner_injection_and_uses_fixed_worker():
    signature = inspect.signature(E.run)
    assert list(signature.parameters) == ["preregistration_path"]
    assert signature.parameters["preregistration_path"].default == E.DEFAULT_PREREG
    assert E.WORKER.name == "evidence_answer_discrimination_worker.py"


def test_grouped_oof_green_and_replay_mismatch_is_red():
    preregistration, _relative, cases = _loaded()
    arms = []
    for replay in preregistration["protocol"]["replays"]:
        request = E.build_worker_request(preregistration, cases, replay["order"])
        result = E.validate_worker_result(_signals(request), request)
        arms.append({"replay_id": replay["id"], "order": replay["order"], "result": result})
    scored = E.score_signals(preregistration, cases, arms)
    assert scored["green"] is True
    assert scored["summary"]["positive_accept"] == 20
    assert scored["summary"]["aggregate_hard_negative_accept"] == 0
    assert len(scored["calibration"]) == 5
    assert all(row["training_feasible"] for row in scored["calibration"])
    assert len(scored["raw_rows"]) == len({row["item_key"] for row in scored["raw_rows"]}) == 52

    # Fold-0 calibration sees only folds 1..4; changing held-out fold 0 in
    # both exact replays cannot alter its selected threshold.
    before_fold_zero = dict(scored["calibration"][0])
    fold_zero_keys = {case["item_key"] for case in cases if case["fold"] == 0}
    for arm in arms:
        for row in arm["result"]["items"]:
            if row["item_key"] in fold_zero_keys:
                row.update(
                    {
                        "p_ans": 0.37,
                        "p_support": 0.4,
                        "p_nei": 0.2,
                        "p_refute": 0.4,
                        "p_sup_net": 0.0,
                    }
                )
    heldout_changed = E.score_signals(preregistration, cases, arms)
    assert heldout_changed["calibration"][0] == before_fold_zero

    arms[1]["result"]["items"][0]["p_ans"] = 0.2
    rescored = E.score_signals(preregistration, cases, arms)
    assert rescored["gate_results"]["replay_exact"] is False
    assert rescored["green"] is False


def test_no_feasible_training_grid_forces_red_even_with_fallback():
    preregistration, _relative, cases = _loaded()
    arms = []
    for replay in preregistration["protocol"]["replays"]:
        request = E.build_worker_request(preregistration, cases, replay["order"])
        result = _signals(request)
        for row in result["items"]:
            row.update(
                {
                    "p_ans": 0.5,
                    "p_support": 0.4,
                    "p_nei": 0.2,
                    "p_refute": 0.4,
                    "p_sup_net": 0.0,
                }
            )
        arms.append({"replay_id": replay["id"], "order": replay["order"], "result": result})
    scored = E.score_signals(preregistration, cases, arms)
    assert not any(row["training_feasible"] for row in scored["calibration"])
    assert {
        (row["p_ans_min"], row["p_sup_net_min"]) for row in scored["calibration"]
    } == {(1.0, 1.0)}, "exact BA/FP/TP ties must choose stricter thresholds"
    assert scored["gate_results"]["all_training_folds_feasible"] is False
    assert scored["green"] is False


def test_attempt_precedes_worker_retry_is_blocked_and_verifier_recomputes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    preregistration, _relative, _cases = _loaded()
    destination = tmp_path / "result.json"
    attempt = tmp_path / "attempt.json"
    failure = tmp_path / "failure.json"
    monkeypatch.setattr(E, "_destinations", lambda _identifier: (destination, attempt, failure))

    def fake_bind(_repo, paths):
        normalized = list(paths)
        content = (
            preregistration["candidate"]["content_sha256"]
            if normalized == preregistration["candidate"]["paths"]
            else E.hashlib.sha256(E.canonical_json_bytes(normalized)).hexdigest()
        )
        return {"files": [{"path": path} for path in normalized], "content_sha256": content}

    calls = []

    def fake_worker(request, _timeout):
        assert attempt.is_file(), "attempt tombstone must precede first worker"
        calls.append(request)
        return _signals(request)

    monkeypatch.setattr(E, "bind_files", fake_bind)
    monkeypatch.setattr(E, "_run_worker", fake_worker)
    report, path = E.run(E.DEFAULT_PREREG)
    assert path == destination
    assert destination.is_file() and attempt.is_file() and not failure.exists()
    assert len(calls) == 2
    assert report["derived"]["green"] is True
    assert E.verify(destination)["valid"] is True
    tampered = dict(report)
    tampered["integrity"] = dict(tampered["integrity"])
    tampered["integrity"]["capability_claimed"] = True
    tampered["checksum_sha256"] = E._checksum(tampered)
    destination.write_bytes(E.canonical_json_bytes(tampered) + b"\n")
    assert E.verify(destination)["valid"] is False
    with pytest.raises(BenchmarkEvidenceError, match="retry is forbidden"):
        E.run(E.DEFAULT_PREREG)
    assert len(calls) == 2


def test_exclusive_writer_refuses_overwrite(tmp_path: Path):
    path = tmp_path / "once.json"
    E._write_exclusive(path, {"first": True})
    with pytest.raises(BenchmarkEvidenceError, match="write-once"):
        E._write_exclusive(path, {"second": True})
