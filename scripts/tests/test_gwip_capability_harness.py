from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from scripts.gwip_capability_design import (
    candidate_schedule_rows,
    support_semantic_ordinal,
    target_arm_order,
    target_semantic_ordinal,
)
from scripts.gwip_capability_harness import (
    CapabilityHarness,
    EpisodeExecutionError,
    FORGERY_HOOK_PATHS,
    HarnessContractError,
    IndependentGateRegistry,
    JITRunLeaseIssuer,
    REQUIRED_HARD_GATES,
    SOURCE_BINDING_SCHEMA,
    WORKER_RESULT_SCHEMA,
    WriteOnceShardStore,
    apply_forgery_hook,
    canonical_digest,
    episode_input_digest,
    latin_arm_order,
    semantic_ordinal,
    validate_semantic_schedule,
    validate_worker_result,
    _lease_input_manifest_digest,
    _unbound_rows,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _source_binding() -> dict:
    return {
        "schema_version": SOURCE_BINDING_SCHEMA,
        "candidate_commit": "1" * 40,
        "candidate_source_sha256": _digest("candidate"),
        "evaluator_commit": "2" * 40,
        "evaluator_source_sha256": _digest("evaluator"),
        "seed_manifest_sha256": _digest("seed-manifest"),
    }


def _prepare(tmp_path: Path, *, pair_count: int = 4, seal: bool = True):
    issuer = JITRunLeaseIssuer(tmp_path / "authority")
    blueprint = _unbound_rows(
        pair_count=pair_count,
        schedule_nonce="fixture-only-schedule-nonce",
    )
    episode_inputs = {
        row["ordinal"]: _request_factory(row, _memory())
        for row in blueprint
    }
    prepared = issuer.prepare_schedule(
        source_binding=_source_binding(),
        schedule_nonce="fixture-only-schedule-nonce",
        pair_count=pair_count,
        fixture_nonproduction=True,
        episode_inputs=episode_inputs,
    )
    if seal:
        issuer.seal_schedule(
            prepared.schedule,
            expected_sha256=prepared.schedule_sha256,
        )
    return issuer, prepared


def _memory(edges: list[int] | None = None) -> dict:
    return {
        "schema_version": "fixture.memory.v1",
        "edges": list(edges or []),
    }


def _worker_result(request: dict, authority, *, mutate_target: bool = False) -> dict:
    witness = authority.authorize(
        action_id=f"action-{request['ordinal']}",
        step_index=0,
    )
    authority.finish("goal_reached")
    memory_after = copy.deepcopy(request["policy_memory"])
    if request["retain_policy_updates"]:
        memory_after["edges"].append(request["ordinal"])
    elif mutate_target:
        memory_after["edges"].append(999)
    trace = {
        "goal": copy.deepcopy(request["goal_ir"]),
        "steps": [
            {
                "decision_receipt": {"accepted": True},
                "world_snapshot": {"state": request["ordinal"]},
                "authorization": witness,
                "valid_actions": [
                    {
                        "action_id": f"action-{request['ordinal']}",
                        "payload": {"semantic_cue": "fixture"},
                    }
                ],
                "proposal_proof": {
                    "metadata": {
                        "transition_rule_hypotheses": [
                            {
                                "expression": {"op": "copy", "path": "/x"},
                                "support_edge_refs": ["one", "two", "three"],
                            }
                        ]
                    }
                },
            }
        ],
    }
    return {
        "schema_version": WORKER_RESULT_SCHEMA,
        "ordinal": request["ordinal"],
        "schedule_row_sha256": request["schedule_row_sha256"],
        "trace": trace,
        "operational_authority": [witness],
        "memory_before": copy.deepcopy(request["policy_memory"]),
        "memory_before_sha256": request["policy_memory_sha256"],
        "memory_after": memory_after,
        "memory_after_sha256": canonical_digest(memory_after),
        "source_binding_sha256": request["source_binding_sha256"],
        "application_isolation": {"passed": True},
        "repo_import_closure": {"passed": True},
        "network_guard": {"passed": True},
        "worker_claims": {
            "all_hard_gates_passed": True,
            "fixture_only": True,
        },
    }


def _request_factory(row: dict, _memory_before: dict) -> dict:
    return {
        "goal_ir": {
            "statement": "fixture goal",
            "origin": "explicit_user",
            "metadata": {
                "target_constraints": [
                    {"path": "/features/value", "op": "eq", "value": 1}
                ]
            },
        },
        "environment_spec": {
            "fixture_nonproduction": True,
            "ordinal": row["ordinal"],
        },
    }


def _gate_registry(*, fail: str | None = None) -> IndependentGateRegistry:
    def verifier(name: str):
        def verify(context: dict) -> dict:
            return {
                "passed": name != fail,
                "evidence": {
                    "fixture_nonproduction": True,
                    "episode_count": len(context["episodes"]),
                    "name": name,
                },
            }

        return verify

    return IndependentGateRegistry(
        verifiers={name: verifier(name) for name in REQUIRED_HARD_GATES},
        fixture_nonproduction=True,
    )


def test_final_semantic_ordinals_and_latin_wall_clock_schedule_are_fixed(
    tmp_path: Path,
) -> None:
    issuer, prepared = _prepare(tmp_path)
    schedule = prepared.schedule
    assert schedule["worker_concurrency"] == 4
    assert schedule["candidate_episode_count"] == 64
    assert semantic_ordinal(pair_index=0, episode_index=0) == 0
    assert semantic_ordinal(pair_index=63, episode_index=3) == 255
    assert (
        semantic_ordinal(
            pair_index=0,
            arm="matched_warm",
            start_index=0,
        )
        == 256
    )
    assert (
        semantic_ordinal(
            pair_index=63,
            arm="mismatched_warm",
            start_index=3,
        )
        == 1023
    )
    assert latin_arm_order(0) == (
        "matched_warm",
        "cold",
        "mismatched_warm",
    )
    assert latin_arm_order(5) == (
        "mismatched_warm",
        "cold",
        "matched_warm",
    )
    assert latin_arm_order(6) == latin_arm_order(0)

    wave_counts: dict[int, int] = {}
    for row in schedule["rows"]:
        wave_counts[row["micro_wave"]] = (
            wave_counts.get(row["micro_wave"], 0) + 1
        )
    assert set(wave_counts.values()) == {4}
    assert len(wave_counts) == 16
    assert len({row["lease_id"] for row in schedule["rows"]}) == 64
    assert len({row["nonce"] for row in schedule["rows"]}) == 64

    forged = copy.deepcopy(schedule)
    forged["rows"][0]["micro_wave"] = 1
    with pytest.raises(HarnessContractError, match="placement|micro_wave"):
        validate_semantic_schedule(
            forged,
            production=False,
            repository_root=issuer.repository_root,
        )
    with pytest.raises(HarnessContractError, match="fixture"):
        validate_semantic_schedule(
            schedule,
            production=True,
            repository_root=issuer.repository_root,
        )


def test_final_blueprint_has_exact_1024_ordinals_and_256_four_worker_waves() -> None:
    rows = _unbound_rows(
        pair_count=64,
        schedule_nonce="nonfinal-blueprint-only",
    )
    assert len(rows) == 1024
    assert [row["ordinal"] for row in rows] == list(range(1024))
    assert sum(row["phase"] == "support" for row in rows) == 256
    assert sum(row["phase"] == "target" for row in rows) == 768
    wave_counts: dict[int, int] = {}
    for row in rows:
        wave_counts[row["micro_wave"]] = (
            wave_counts.get(row["micro_wave"], 0) + 1
        )
    assert sorted(wave_counts) == list(range(256))
    assert set(wave_counts.values()) == {4}
    assert tuple(row["ordinal"] for row in candidate_schedule_rows()) == tuple(
        row["ordinal"] for row in rows
    )
    for pair_index in range(64):
        assert latin_arm_order(pair_index) == target_arm_order(pair_index)
        for episode_index in range(4):
            assert (
                semantic_ordinal(
                    pair_index=pair_index,
                    episode_index=episode_index,
                )
                == support_semantic_ordinal(pair_index, episode_index)
            )
        for arm in ("matched_warm", "cold", "mismatched_warm"):
            for start_index in range(4):
                assert (
                    semantic_ordinal(
                        pair_index=pair_index,
                        arm=arm,
                        start_index=start_index,
                    )
                    == target_semantic_ordinal(
                        pair_index,
                        arm,
                        start_index,
                    )
                )


def test_caller_attested_episode_digest_cannot_replace_evaluator_owned_input(
    tmp_path: Path,
) -> None:
    issuer, prepared = _prepare(tmp_path, seal=False)
    honest = prepared.schedule
    row = honest["rows"][0]
    expected = _request_factory(row, _memory())
    assert row["episode_input_sha256"] == episode_input_digest(
        goal_ir=expected["goal_ir"],
        environment_spec=expected["environment_spec"],
    )

    forged = copy.deepcopy(honest)
    forged_row = forged["rows"][0]
    forged_row["episode_input_sha256"] = _digest("caller-attested-input")
    # Simulate a caller that also recomputes every schedule-local derivative.
    # The issuer still compares with the evaluator-owned inputs retained when
    # prepare_schedule ran, so local self-consistency cannot authorize it.
    forged_row["live_context"]["input_manifest_sha256"] = (
        _lease_input_manifest_digest(
            forged_row,
            seed_manifest_sha256=forged["source_binding"][
                "seed_manifest_sha256"
            ],
        )
    )
    with pytest.raises(
        HarnessContractError,
        match="evaluator-owned design",
    ):
        issuer.seal_schedule(
            forged,
            expected_sha256=canonical_digest(forged),
        )


def test_jit_run_lease_is_precommitted_unique_single_use_and_time_bounded(
    tmp_path: Path,
) -> None:
    issuer, prepared = _prepare(tmp_path)
    row = prepared.schedule["rows"][0]
    assert row["live_context"]["limits"]["max_runtime_sec"] == 3_600
    assert row["live_context"]["limits"]["max_actions"] == 24

    authority = issuer.issue(prepared.schedule, ordinal=0)
    # These are the only lease fields not present in the committed row.
    assert authority.document["lease_id"] == row["lease_id"]
    assert authority.document["nonce"] == row["nonce"]
    assert authority.document["runner_artifact_sha256"] == (
        row["live_context"]["runner_artifact_sha256"]
    )
    assert authority.document["input_manifest_sha256"] == (
        _lease_input_manifest_digest(
            row,
            seed_manifest_sha256=prepared.schedule["source_binding"][
                "seed_manifest_sha256"
            ],
        )
    )
    assert authority.document["input_manifest_sha256"] != (
        prepared.schedule["source_binding"]["seed_manifest_sha256"]
    )
    assert authority.document["issued_at"]
    assert authority.document["expires_at"]
    assert authority.document["operator_signature"]["signature"]

    assert authority.activate()["reason"] == "run_lease_activated"
    witness = authority.authorize(action_id="fixture-action", step_index=0)
    assert witness["granted"] is True
    assert witness["authority_kind"] == "externally_signed_run_lease"
    assert authority.finish("goal_reached")["finished"] is True
    seal = authority.seal(shard_sha256=_digest("shard"))
    assert seal["single_use_replay_reason"] == "run_lease_replay"
    assert seal["issue_to_activation_seconds"] <= 120
    assert seal["worker_seconds"] <= 1_200
    assert seal["finish_to_seal_seconds"] <= 120
    assert seal["total_seconds"] <= 1_440
    with pytest.raises(HarnessContractError, match="already issued"):
        issuer.issue(prepared.schedule, ordinal=0)


def test_worker_schema_rejects_target_learning_and_worker_claims_are_not_gates(
    tmp_path: Path,
) -> None:
    issuer, prepared = _prepare(tmp_path)
    target = next(
        row for row in prepared.schedule["rows"] if row["phase"] == "target"
    )
    authority = issuer.issue(
        prepared.schedule,
        ordinal=target["ordinal"],
    )
    authority.activate()
    request = {
        "schema_version": "atanor.gwip-capability-worker-request.v1",
        "ordinal": target["ordinal"],
        "schedule_row_sha256": canonical_digest(target),
        "phase": "target",
        "pair_index": target["pair_index"],
        "episode_index": None,
        "arm": target["arm"],
        "environment_seed": target["environment_seed"],
        "policy_seed": target["policy_seed"],
        "step_budget": 24,
        "retain_policy_updates": False,
        "session_id": "fixture-target",
        "goal_ir": {
            "metadata": {
                "target_constraints": [
                    {"path": "/features/value", "op": "eq", "value": 1}
                ]
            }
        },
        "environment_spec": {"fixture_nonproduction": True},
        "policy_memory": _memory([1, 2, 3]),
        "policy_memory_sha256": canonical_digest(_memory([1, 2, 3])),
        "episode_input_sha256": episode_input_digest(
            goal_ir={
                "metadata": {
                    "target_constraints": [
                        {
                            "path": "/features/value",
                            "op": "eq",
                            "value": 1,
                        }
                    ]
                }
            },
            environment_spec={"fixture_nonproduction": True},
        ),
        "source_binding_sha256": prepared.schedule[
            "source_binding_sha256"
        ],
    }
    forged = _worker_result(request, authority, mutate_target=True)
    with pytest.raises(HarnessContractError, match="retained policy"):
        validate_worker_result(forged, request=request)

    registry = _gate_registry(fail="complete_lineage")
    gates = registry.evaluate(
        {
            "episodes": [{"worker_result": forged}],
        }
    )
    assert gates["all_passed"] is False
    assert gates["gates"]["complete_lineage"]["passed"] is False
    assert gates["worker_claims_accepted_as_evidence"] is False


def test_request_factory_cannot_swap_precommitted_goal_or_environment(
    tmp_path: Path,
) -> None:
    issuer, prepared = _prepare(tmp_path)
    shards = WriteOnceShardStore(
        tmp_path / "shards",
        schedule_sha256=prepared.schedule_sha256,
        attempt_sha256=_digest("fixture-attempt"),
    )
    runner_ordinals: list[int] = []

    def swapped_factory(row: dict, memory_before: dict) -> dict:
        supplied = _request_factory(row, memory_before)
        if row["ordinal"] == 0:
            supplied["goal_ir"]["metadata"]["target_constraints"][0][
                "value"
            ] = 999
            supplied["episode_input_sha256"] = row[
                "episode_input_sha256"
            ]
        return supplied

    def runner(request: dict, authority) -> dict:
        runner_ordinals.append(request["ordinal"])
        return _worker_result(request, authority)

    harness = CapabilityHarness(
        schedule=prepared.schedule,
        schedule_sha256=prepared.schedule_sha256,
        issuer=issuer,
        shard_store=shards,
        request_factory=swapped_factory,
        episode_runner=runner,
        gate_registry=_gate_registry(),
        empty_memory=_memory(),
        source_binding_probe=lambda: _digest("evaluator"),
    )
    with pytest.raises(
        EpisodeExecutionError,
        match="evaluator-owned episode input",
    ):
        harness.execute()
    assert 0 not in runner_ordinals


def test_forgery_hooks_cover_all_preregistered_self_attestation_surfaces() -> None:
    request = {
        "goal_ir": {
            "metadata": {
                "target_constraints": [
                    {"path": "/features/value", "op": "eq", "value": 1}
                ]
            }
        },
        "ordinal": 1,
        "schedule_row_sha256": _digest("row"),
        "source_binding_sha256": _digest("source"),
        "policy_memory": _memory([1]),
        "policy_memory_sha256": canonical_digest(_memory([1])),
    }
    result = {
        "ordinal": request["ordinal"],
        "schedule_row_sha256": request["schedule_row_sha256"],
        "source_binding_sha256": request["source_binding_sha256"],
        "memory_before": request["policy_memory"],
        "memory_before_sha256": request["policy_memory_sha256"],
        "memory_after": request["policy_memory"],
        "memory_after_sha256": request["policy_memory_sha256"],
        "worker_claims": {},
        "trace": {
            "semantic_trace": {
                "goal": request["goal_ir"],
                "steps": [
                    {
                        "decision_receipt": {"accepted": True},
                        "world_snapshot": {"state": 1},
                        "authorization": {"granted": True},
                        "valid_actions": [
                            {"payload": {"semantic_cue": "opaque"}}
                        ],
                        "proposal_proof": {
                            "metadata": {
                                "transition_rule_hypotheses": [
                                    {
                                        "expression": {
                                            "op": "copy",
                                            "path": "/features/value",
                                        },
                                        "support_edge_refs": ["a", "b", "c"],
                                    }
                                ]
                            }
                        },
                    }
                ],
            },
        },
    }
    assert {
        "decision_receipt",
        "world_snapshot",
        "authority_witness",
        "target_constraint",
        "rule_ir",
        "action_payload",
        "support_citations",
        "transfer_memory_chain",
    }.issubset(FORGERY_HOOK_PATHS)
    for hook in FORGERY_HOOK_PATHS:
        forged = apply_forgery_hook(result, hook)
        assert forged != result
        assert forged["worker_claims"]["self_resealed_after_forgery"] is True


def test_exact_four_worker_harness_chains_support_and_detaches_every_target(
    tmp_path: Path,
) -> None:
    issuer, prepared = _prepare(tmp_path)
    shards = WriteOnceShardStore(
        tmp_path / "shards",
        schedule_sha256=prepared.schedule_sha256,
        attempt_sha256=_digest("fixture-attempt"),
    )
    seen_target_inputs: dict[tuple[int, str, int], dict] = {}

    def runner(request: dict, authority) -> dict:
        if request["phase"] == "target":
            seen_target_inputs[
                (
                    request["pair_index"],
                    request["arm"],
                    request["environment_seed"],
                )
            ] = copy.deepcopy(request["policy_memory"])
        return _worker_result(request, authority)

    harness = CapabilityHarness(
        schedule=prepared.schedule,
        schedule_sha256=prepared.schedule_sha256,
        issuer=issuer,
        shard_store=shards,
        request_factory=_request_factory,
        episode_runner=runner,
        gate_registry=_gate_registry(),
        empty_memory=_memory(),
        source_binding_probe=lambda: _digest("evaluator"),
    )
    result = harness.execute()
    assert result["worker_concurrency"] == 4
    assert result["candidate_episode_count"] == 64
    assert result["retried_ordinals"] == []
    assert result["attempted_ordinals"] == list(range(64))
    assert result["hard_gate_surfaces"]["all_passed"] is True
    assert result["production_activation_authorized"] is False
    assert result["capability_claim"] is False

    # Four support episodes chain; the three target arms receive matched,
    # canonical-empty, or next-pair memory.  Every start in an arm gets an
    # independent equal copy because target outputs are discarded.
    final_support = {
        pair: _memory(
            [
                pair * 4 + episode
                for episode in range(4)
            ]
        )
        for pair in range(4)
    }
    for pair in range(4):
        matched = [
            seen_target_inputs[(pair, "matched_warm", start)]
            for start in range(4)
        ]
        cold = [
            seen_target_inputs[(pair, "cold", start)]
            for start in range(4)
        ]
        mismatch = [
            seen_target_inputs[(pair, "mismatched_warm", start)]
            for start in range(4)
        ]
        assert matched == [final_support[pair]] * 4
        assert cold == [_memory()] * 4
        assert mismatch == [final_support[(pair + 1) % 4]] * 4


def test_failure_is_write_once_and_never_retried(tmp_path: Path) -> None:
    issuer, prepared = _prepare(tmp_path)
    shards = WriteOnceShardStore(
        tmp_path / "shards",
        schedule_sha256=prepared.schedule_sha256,
        attempt_sha256=_digest("fixture-attempt"),
    )
    calls: dict[int, int] = {}

    def failing_runner(request: dict, authority) -> dict:
        calls[request["ordinal"]] = calls.get(request["ordinal"], 0) + 1
        if request["ordinal"] == 0:
            raise RuntimeError("fixture crash")
        return _worker_result(request, authority)

    harness = CapabilityHarness(
        schedule=prepared.schedule,
        schedule_sha256=prepared.schedule_sha256,
        issuer=issuer,
        shard_store=shards,
        request_factory=_request_factory,
        episode_runner=failing_runner,
        gate_registry=_gate_registry(),
        empty_memory=_memory(),
        source_binding_probe=lambda: _digest("evaluator"),
    )
    with pytest.raises(EpisodeExecutionError, match="fixture crash"):
        harness.execute()
    assert calls[0] == 1
    failure_path = shards.root / "episode-0000.json"
    assert failure_path.exists()
    assert '"retry_forbidden": true' in failure_path.read_text(encoding="utf-8")
    with pytest.raises(HarnessContractError, match="already written"):
        shards.write(
            ordinal=0,
            status="failed",
            payload={"again": True},
        )
