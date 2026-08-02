from __future__ import annotations

import copy
import hashlib
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import canonical_json_bytes
from packages.eval_evidence.receipt import bind_files, finalize_manifest
from scripts import live_memory_realtime_candidate_worker as worker
from scripts import live_memory_realtime_preregistered_eval as harness


def _preregistration() -> dict:
    preregistration_id = "live-recall-fixture-v1"
    positives = []
    for index in range(48):
        row = {
            "family": ["who", "where", "year", "number"][index % 4],
            "fact": f"Fixture entity {index} carries value{index}.",
            "question": f"What does fixture entity {index} carry?",
            "gold": f"value{index}",
            "source_id": f"fixture-source-{index:02d}",
        }
        positives.append(
            {
                "item_id": harness.preregistered_item_id(
                    preregistration_id,
                    "positive",
                    {key: row[key] for key in sorted(row)},
                ),
                **row,
            }
        )
    unknowns = []
    for index in range(12):
        row = {
            "family": "unknown",
            "question": f"What does unseen fixture entity {index} carry?",
        }
        unknowns.append(
            {
                "item_id": harness.preregistered_item_id(
                    preregistration_id,
                    "unknown",
                    {key: row[key] for key in sorted(row)},
                ),
                **row,
            }
        )

    candidate_paths = sorted(
        {
            *harness._REQUIRED_CANDIDATE_PATHS,
            "data/graph_scale/ace_hotpot.pt",
        }
    )
    return {
        "schema_version": harness.PREREGISTRATION_SCHEMA,
        "preregistration_id": preregistration_id,
        "frozen_at": "2026-07-26T00:00:00Z",
        "claim_boundary": {
            "measurement": "novel_synthetic_single_hop_recall_reconfirmation",
            "single_hop_recall_only": True,
            "general_reasoning_improvement_claimed": False,
            "cross_benchmark_capability_claimed": False,
            "evidence_level": "unsigned_local_development",
            "limitations": [
                "Synthetic facts are not a natural benchmark.",
                "This is single-hop recall, not general reasoning.",
                "The evaluator is local and unsigned.",
            ],
        },
        "candidate": {
            "paths": candidate_paths,
            "content_sha256": "0" * 64,
            "checkpoint_path": "data/graph_scale/ace_hotpot.pt",
        },
        "protocol": {
            "replays": [
                {"id": "off-then-on", "condition_order": ["OFF", "ON"]},
                {"id": "on-then-off", "condition_order": ["ON", "OFF"]},
            ],
            "device_policy": "cpu_only",
            "python_hash_seed": "0",
            "worker_timeout_seconds": 600,
            "candidate_config": {
                "checkpoint": "ace_hotpot.pt",
                "threshold": 0.35,
                "k": 3,
                "min_overlap": 2,
                "k_live": 4,
            },
            "scoring": {
                "normalization": harness.NORMALIZATION_SPEC,
                "bootstrap_resamples": 1_000,
                "bootstrap_seed": 1729,
                "bootstrap_confidence": 0.95,
            },
            "gates": {
                "mechanism": {
                    "on_recall_at_1_min": 0.9,
                    "on_exact_support_source_provenance_rate_min": 0.9,
                },
                "capability": {
                    "on_mean_token_f1_min": 0.65,
                    "on_exact_match_rate_min": 0.55,
                    "paired_exact_match_lift_min": 0.35,
                    "mcnemar_exact_p_max": 0.05,
                    "bootstrap_paired_em_lift_lower_exclusive_min": 0.0,
                    "replay_exact_match_required": True,
                },
                "safety": {
                    "unknown_false_grounded_rate_max": 0.1,
                    "unknown_false_used_live_rate_max": 0.1,
                    "worker_error_count_max": 0,
                    "candidate_unchanged_required": True,
                    "source_unchanged_required": True,
                    "preregistration_unchanged_required": True,
                    "temporary_state_isolation_required": True,
                },
            },
            "rerun_policy": {
                "result_run_limit": 1,
                "mechanical_retry_limit": 0,
                "post_result_tuning_prohibited": True,
                "new_preregistration_required_after_candidate_or_protocol_change": True,
            },
        },
        "exposure_audit": {
            "prior_examples_excluded": True,
            "full_string_repo_scan_performed_before_freeze": True,
            "new_entity_repo_scan_performed_before_freeze": True,
            "full_string_hit_count_before_freeze": 0,
            "new_entity_hit_count_before_freeze": 0,
            "public_same_repo_items": True,
            "hidden_holdout": False,
            "independent_evaluator": False,
            "repeated_tuning_risk": "high",
            "limitations": [
                "Items become public in the same repository after freeze.",
                "Prior synthetic recall demos exposed related task structure.",
                "Candidate authors can inspect the evaluator.",
                "A repository scan is not a hidden-set guarantee.",
            ],
        },
        "items": positives,
        "unknown_controls": unknowns,
        "static_paragraphs": [],
    }


def _result_for_request(request: dict) -> dict:
    condition = request["condition"]
    learned = [
        {
            "source_id": row["source_id"],
            "fact_sha256": hashlib.sha256(row["fact"].encode("utf-8")).hexdigest(),
            "candidate_item_id": index,
        }
        for index, row in enumerate(request["learn"])
    ]
    rows = []
    positive_count = 48
    for row in request["questions"]:
        index = row["index"]
        positive = index < positive_count
        if condition == "ON" and positive:
            answer = f"value{index}"
            used_live = True
            grounded = True
            source = request["learn"][index]["source_id"]
            support_title = f"live:{source}"
            fact_digest = hashlib.sha256(
                request["learn"][index]["fact"].encode("utf-8")
            ).hexdigest()
        elif positive:
            answer = "noise"
            used_live = False
            grounded = False
            source = None
            support_title = None
            fact_digest = None
        else:
            answer = "unguarded guess"
            used_live = False
            grounded = False
            source = None
            support_title = None
            fact_digest = None
        rows.append(
            {
                "index": index,
                "emitted": True,
                "answer": answer,
                "used_live": used_live,
                "grounded": grounded,
                "confidence": 0.75 if grounded else 0.0,
                "support": [support_title] if support_title else [],
                "evidence": (
                    [{"origin": "live", "title": support_title}]
                    if support_title
                    else []
                ),
                "recall_top_source": source,
                "recall_top_fact_sha256": fact_digest,
                "error_type": None,
                "latency_ms": 1.0,
            }
        )
    expected_files = ["hippocampus.jsonl"] if condition == "ON" else []
    return {
        "schema_version": worker.RESULT_SCHEMA,
        "condition": condition,
        "device": "cpu",
        "python_hash_seed": "0",
        "isolation": {
            "temporary_state_initially_empty": True,
            "hippocampus_path_is_temporary": True,
            "cortex_path_is_temporary": True,
            "miss_path_is_temporary": True,
            "record_misses": False,
            "include_unverified": False,
            "learned_verified": True,
            "learned_count": len(request["learn"]),
            "cortex_write_detected": False,
            "miss_write_detected": False,
            "unexpected_temporary_files": [],
            "temporary_files": expected_files,
        },
        "learned": learned,
        "items": rows,
    }


def _install_mini_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, dict]:
    repo = tmp_path / "repo"
    reports = repo / "reports" / "benchmarks"
    reports.mkdir(parents=True)
    evaluator_path = repo / "evaluator.py"
    evaluator_path.write_text("# frozen evaluator fixture\n", encoding="utf-8")

    preregistration = _preregistration()
    for relative in preregistration["candidate"]["paths"]:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"frozen:{relative}\n".encode("utf-8"))
    preregistration["candidate"]["content_sha256"] = bind_files(
        repo,
        preregistration["candidate"]["paths"],
    )["content_sha256"]

    preregistration_path = (
        repo / "data" / "eval" / "live_memory_realtime_preregister_v1.json"
    )
    preregistration_path.parent.mkdir(parents=True)
    preregistration_path.write_bytes(
        canonical_json_bytes(preregistration) + b"\n"
    )

    monkeypatch.setattr(harness, "REPO", repo)
    monkeypatch.setattr(harness, "REPORTS", reports)
    monkeypatch.setattr(harness, "WORKER", repo / "never_execute_worker.py")
    monkeypatch.setattr(harness, "_EVALUATOR_PATHS", ("evaluator.py",))
    return preregistration_path, preregistration


def test_preregistration_is_strict_and_worker_payload_has_no_gold() -> None:
    preregistration = harness.validate_preregistration(_preregistration())
    off = harness.build_worker_request(preregistration, "OFF")
    on = harness.build_worker_request(preregistration, "ON")

    assert off["learn"] == []
    assert len(on["learn"]) == 48
    assert len(off["questions"]) == len(on["questions"]) == 60
    assert off["static_paragraphs"] == on["static_paragraphs"] == []
    assert not harness._contains_gold_key(off)
    assert not harness._contains_gold_key(on)
    assert b'"gold"' not in canonical_json_bytes(on)
    assert all(frozenset(row) == {"fact", "source_id"} for row in on["learn"])
    assert all(frozenset(row) == {"index", "question"} for row in on["questions"])


def test_worker_request_rejects_extra_gold_and_static_evidence() -> None:
    request = harness.build_worker_request(_preregistration(), "ON")
    worker._validate_request(request)

    with_gold = copy.deepcopy(request)
    with_gold["questions"][0]["gold"] = "value0"
    with pytest.raises(Exception, match="question row 0 invalid"):
        worker._validate_request(with_gold)

    with_static = copy.deepcopy(request)
    with_static["static_paragraphs"] = [["title", "text"]]
    with pytest.raises(Exception, match="empty static evidence"):
        worker._validate_request(with_static)


def test_worker_uses_temporary_paths_and_safe_recall_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_calls = []
    learn_calls = []
    promotion_calls = []
    recall_calls = []
    think_calls = []

    class FakeMissLog:
        def __init__(self, path: Path):
            self.path = path

    class FakeMemory:
        def __init__(self):
            self.items = []

        def recall(self, question: str, k: int, include_unverified: bool):
            recall_calls.append((question, k, include_unverified))
            if not self.items:
                return []
            return [
                {
                    "text": self.items[0]["fact"],
                    "source": self.items[0]["source"],
                    "verified": True,
                }
            ]

    class FakeThinker:
        def __init__(self, **kwargs):
            constructor_calls.append(kwargs)
            assert not kwargs["store"].exists()
            assert not kwargs["cortex_path"].exists()
            assert not kwargs["misslog"].path.exists()
            self.store = kwargs["store"]
            self.mem = FakeMemory()
            self.reader = types.SimpleNamespace(dev="cpu")

        def learn(self, fact: str, source: str):
            learn_calls.append((fact, source))
            self.mem.items.append({"fact": fact, "source": source})
            self.store.write_text(
                json.dumps({"text": fact, "source": source}),
                encoding="utf-8",
            )
            return {"id": len(self.mem.items) - 1}

        def promote_verified(self, item_id: int):
            promotion_calls.append(item_id)
            return True

        def think(
            self,
            question: str,
            static_paragraphs: list,
            k_live: int,
            include_unverified: bool,
        ):
            think_calls.append(
                (question, static_paragraphs, k_live, include_unverified)
            )
            return {
                "answer": "fixture",
                "used_live": True,
                "grounded": True,
                "confidence": 0.5,
                "support": ["live:fixture"],
                "evidence": [{"origin": "live", "title": "live:fixture"}],
            }

    fake_consolidation = types.ModuleType(
        "packages.reasoning_vm.consolidation"
    )
    fake_consolidation.MissLog = FakeMissLog
    fake_realtime = types.ModuleType(
        "packages.reasoning_vm.deliberator.realtime"
    )
    fake_realtime.RealTimeThinker = FakeThinker
    monkeypatch.setitem(
        sys.modules,
        "packages.reasoning_vm.consolidation",
        fake_consolidation,
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.reasoning_vm.deliberator.realtime",
        fake_realtime,
    )

    request = {
        "schema_version": worker.REQUEST_SCHEMA,
        "condition": "ON",
        "checkpoint": "ace_hotpot.pt",
        "device_policy": "cpu_only",
        "config": {
            "threshold": 0.35,
            "k": 3,
            "min_overlap": 2,
            "k_live": 4,
        },
        "learn": [{"fact": "A fixture fact.", "source_id": "fixture-source"}],
        "questions": [{"index": 0, "question": "What is the fixture fact?"}],
        "static_paragraphs": [],
    }
    result = worker.evaluate(request)

    assert len(constructor_calls) == 1
    call = constructor_calls[0]
    assert call["store"] != call["cortex_path"] != call["misslog"].path
    assert call["record_misses"] is False
    assert not call["store"].exists()
    assert not call["cortex_path"].exists()
    assert not call["misslog"].path.exists()
    assert learn_calls == [("A fixture fact.", "fixture-source")]
    assert promotion_calls == [0]
    assert recall_calls == [("What is the fixture fact?", 4, False)]
    assert think_calls == [("What is the fixture fact?", [], 4, False)]
    assert result["isolation"]["temporary_state_initially_empty"] is True
    assert result["isolation"]["cortex_write_detected"] is False
    assert result["isolation"]["miss_write_detected"] is False
    assert result["isolation"]["unexpected_temporary_files"] == []


def test_four_stub_arms_are_counterbalanced_and_separated_gates_green() -> None:
    preregistration = harness.validate_preregistration(_preregistration())
    calls = []

    def stub_runner(request, timeout, device_policy, hash_seed, worker_path):
        calls.append(
            {
                "condition": request["condition"],
                "request_identity": id(request),
                "timeout": timeout,
                "device_policy": device_policy,
                "hash_seed": hash_seed,
                "worker_path": worker_path,
            }
        )
        return _result_for_request(request)

    arms = harness.collect_arms(preregistration, runner=stub_runner)
    items, summary, gates = harness.score_arms(
        preregistration,
        arms,
        integrity={
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "preregistration_same_before_after": True,
        },
    )

    assert [row["condition"] for row in calls] == ["OFF", "ON", "ON", "OFF"]
    assert len({row["request_identity"] for row in calls}) == 4
    assert all(row["device_policy"] == "cpu_only" for row in calls)
    assert all(row["hash_seed"] == "0" for row in calls)
    assert len(items) == 60 * 4
    assert summary["fresh_process_arm_count"] == 4
    assert summary["capability"]["replay_exact_match"] is True
    assert gates["mechanism"]["green"] is True
    assert gates["capability"]["green"] is True
    assert gates["safety"]["green"] is True
    assert gates["overall_green"] is True


def test_replay_disagreement_is_capability_red() -> None:
    preregistration = harness.validate_preregistration(_preregistration())

    def stub_runner(request, timeout, device_policy, hash_seed, worker_path):
        return _result_for_request(request)

    arms = harness.collect_arms(preregistration, runner=stub_runner)
    changed = copy.deepcopy(arms)
    # The second replay's ON arm is process ordinal 2.
    changed[2]["result"]["items"][0]["answer"] = "different"
    _items, summary, gates = harness.score_arms(
        preregistration,
        changed,
        integrity={
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "preregistration_same_before_after": True,
        },
    )

    assert summary["capability"]["replay_exact_match"] is False
    assert summary["capability"]["replay_mismatch_count"] == 1
    assert gates["capability"]["checks"]["replay_exact_match"] is False
    assert gates["capability"]["green"] is False
    assert gates["overall_green"] is False


def test_subprocess_runner_executes_only_supplied_stub(
    tmp_path: Path,
) -> None:
    stub = tmp_path / "stub_worker.py"
    stub.write_text(
        "\n".join(
            [
                "import json, os, sys",
                "request = json.loads(sys.stdin.buffer.read())",
                "result = {",
                "  'schema_version': 'stub.v1',",
                "  'condition': request['condition'],",
                "  'python_hash_seed': os.environ.get('PYTHONHASHSEED'),",
                "  'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),",
                "}",
                "sys.stdout.write(json.dumps(result))",
            ]
        ),
        encoding="utf-8",
    )
    request = harness.build_worker_request(_preregistration(), "OFF")
    result = harness._run_worker(
        request,
        60,
        "cpu_only",
        "123",
        stub,
    )

    assert result == {
        "schema_version": "stub.v1",
        "condition": "OFF",
        "python_hash_seed": "123",
        "cuda_visible_devices": "-1",
    }


def test_public_run_signature_has_no_runner_or_worker_injection() -> None:
    signature = inspect.signature(harness.run)
    assert tuple(signature.parameters) == ("preregistration_path",)
    assert signature.parameters["preregistration_path"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )


def test_worker_crash_leaves_attempt_and_failure_and_refuses_second_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preregistration_path, preregistration = _install_mini_repository(
        monkeypatch,
        tmp_path,
    )
    launches = []

    def crashing_worker(request, timeout, device_policy, hash_seed, worker_path):
        launches.append(request["condition"])
        raise RuntimeError("stub crash before any result")

    monkeypatch.setattr(harness, "_run_worker", crashing_worker)
    with pytest.raises(RuntimeError, match="stub crash"):
        harness.run(preregistration_path=preregistration_path)

    stem = (
        f"live_memory_realtime_{preregistration['preregistration_id']}"
    )
    attempt_path = harness.REPORTS / f"{stem}.attempt.json"
    failure_path = harness.REPORTS / f"{stem}.failure.json"
    result_path = harness.REPORTS / f"{stem}.json"
    assert attempt_path.exists()
    assert failure_path.exists()
    assert not result_path.exists()

    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    assert attempt["schema_version"] == harness.ATTEMPT_SCHEMA
    assert attempt["status"] == "started"
    assert attempt["candidate_content_sha256"] == preregistration["candidate"][
        "content_sha256"
    ]
    assert failure["schema_version"] == harness.FAILURE_SCHEMA
    assert failure["status"] == "failed"
    assert failure["error_type"] == "RuntimeError"
    assert failure["completed_arm_count"] == 0
    assert failure["completed_arm_shards"] == []
    assert launches == ["OFF"]

    with pytest.raises(Exception, match="another result run is forbidden"):
        harness.run(preregistration_path=preregistration_path)
    assert launches == ["OFF"]


def test_deep_verifier_recomputes_items_summary_and_gates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preregistration_path, _preregistration_value = _install_mini_repository(
        monkeypatch,
        tmp_path,
    )

    def stub_worker(request, timeout, device_policy, hash_seed, worker_path):
        return _result_for_request(request)

    monkeypatch.setattr(harness, "_run_worker", stub_worker)
    manifest, _result_path = harness.run(
        preregistration_path=preregistration_path
    )
    assert harness.validate_report_semantics(manifest) == []

    forged_gate_payload = copy.deepcopy(manifest)
    forged_gate_payload.pop("manifest_checksum_sha256")
    forged_gate_payload["config"]["gate_results"]["capability"]["green"] = False
    forged_gate = finalize_manifest(forged_gate_payload)
    forged_gate_path = tmp_path / "forged_gate.json"
    forged_gate_path.write_bytes(canonical_json_bytes(forged_gate) + b"\n")
    assert harness.main(["verify", str(forged_gate_path)]) == 2
    gate_output = json.loads(capsys.readouterr().out)
    assert gate_output["semantic_valid"] is False
    assert any(
        "gates do not recompute" in finding
        for finding in gate_output["semantic_findings"]
    )

    forged_item_payload = copy.deepcopy(manifest)
    forged_item_payload.pop("manifest_checksum_sha256")
    forged_item_payload["items"][0]["metadata"]["normalized_token_f1"] = 0.5
    forged_item_payload["metrics"] = harness.aggregate_items(
        forged_item_payload["items"]
    )
    forged_item = finalize_manifest(forged_item_payload)
    forged_item_path = tmp_path / "forged_item.json"
    forged_item_path.write_bytes(canonical_json_bytes(forged_item) + b"\n")
    assert harness.main(["verify", str(forged_item_path)]) == 2
    item_output = json.loads(capsys.readouterr().out)
    assert item_output["semantic_valid"] is False
    assert any(
        "item-level scoring mismatch" in finding
        for finding in item_output["semantic_findings"]
    )
