from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts import gwip_capability_verifier as verifier
from scripts.gwip_capability_design import (
    EpisodeOutcome,
    FROZEN_PREREGISTRATION,
    REQUIRED_HARD_GATES,
    RandomControl,
    ReactiveControl,
    canonical_digest,
)


@dataclass(frozen=True)
class _Episode:
    start_ref: str = "p7-state-0"
    goal_ref: str = "p7-state-1"
    optimal_steps: int = 1


class _P7Environment:
    """Hand-authored nonfinal environment; no p13/p17/p19 generator is used."""

    episodes = (_Episode(), _Episode(), _Episode(), _Episode())
    actions = (
        type("_Action", (), {"action_ref": "p7-action-inc"})(),
        type("_Action", (), {"action_ref": "p7-action-stay"})(),
    )

    @staticmethod
    def observation(state_ref: str, *, goal_ref: str) -> dict:
        value = int(state_ref.rsplit("-", 1)[1])
        return {
            "schema_version": "hand.p7.v1",
            "state_ref": state_ref,
            "features": {
                "registers": [value],
                "context": {"modulus": 7},
            },
            "terminal": state_ref == goal_ref,
        }

    @staticmethod
    def public_actions() -> tuple[dict, ...]:
        return (
            {"action_id": "p7-action-inc", "payload": {"cue": "opal"}},
            {"action_id": "p7-action-stay", "payload": {"cue": "cedar"}},
        )

    @staticmethod
    def transition(state_ref: str, action_id: str) -> str:
        if action_id == "p7-action-inc":
            value = (int(state_ref.rsplit("-", 1)[1]) + 1) % 7
        elif action_id == "p7-action-stay":
            value = int(state_ref.rsplit("-", 1)[1])
        else:
            raise ValueError("unknown action")
        return f"p7-state-{value}"


def _rpc_row(index: int, operation: str, payload: dict, result: dict) -> dict:
    return {
        "order_index": index,
        "call_id": index,
        "operation": operation,
        "payload": payload,
        "result": result,
        "result_sha256": canonical_digest(result),
    }


def _successful_parent_log() -> list[dict]:
    environment = _P7Environment()
    before = environment.observation("p7-state-0", goal_ref="p7-state-1")
    after = environment.observation("p7-state-1", goal_ref="p7-state-1")
    step = {
        "observation": after,
        "terminal": True,
        "success": True,
        "stop_reason": "goal_reached",
    }
    return [
        _rpc_row(0, "reset", {"seed": 0}, {"reset": True}),
        _rpc_row(1, "observe", {}, before),
        _rpc_row(2, "valid_actions", {}, list(environment.public_actions())),
        _rpc_row(3, "step", {"action_id": "p7-action-inc"}, step),
        _rpc_row(
            4,
            "stop",
            {"reason": "goal_reached"},
            {
                "stopped": True,
                "reason": "goal_reached",
                "steps": 1,
                "success": True,
            },
        ),
    ]


def test_parent_log_rebuilds_outcome_from_oracle_not_caller_status() -> None:
    rebuilt = verifier.reconstruct_episode_outcome(
        pair_index=0,
        episode_index=0,
        environment=_P7Environment(),
        call_log=_successful_parent_log(),
    )
    assert rebuilt.outcome == EpisodeOutcome(
        pair_index=0,
        episode_index=0,
        success=True,
        optimal_steps=1,
        executed_steps=1,
    )
    assert rebuilt.parent_steps[0]["selected_action"] == "p7-action-inc"

    forged = _successful_parent_log()
    forged[3]["result"]["success"] = False
    forged[3]["result_sha256"] = canonical_digest(forged[3]["result"])
    with pytest.raises(
        verifier.CapabilityVerificationError,
        match="differs from sealed oracle",
    ):
        verifier.reconstruct_episode_outcome(
            pair_index=0,
            episode_index=0,
            environment=_P7Environment(),
            call_log=forged,
        )


def test_parent_parser_allows_budget_stop_after_observe_valid_actions() -> None:
    environment = _P7Environment()
    # A policy can abstain after the evaluator has exposed valid actions.  This
    # is a zero-action failed episode, not a malformed call order.
    before = environment.observation("p7-state-0", goal_ref="p7-state-1")
    log = [
        _rpc_row(0, "reset", {"seed": 0}, {"reset": True}),
        _rpc_row(1, "observe", {}, before),
        _rpc_row(2, "valid_actions", {}, list(environment.public_actions())),
        _rpc_row(
            3,
            "stop",
            {"reason": "policy_abstained"},
            {
                "stopped": True,
                "reason": "policy_abstained",
                "steps": 0,
                "success": False,
            },
        ),
    ]
    rebuilt = verifier.reconstruct_episode_outcome(
        pair_index=0,
        episode_index=0,
        environment=environment,
        call_log=log,
    )
    assert rebuilt.outcome.success is False
    assert rebuilt.outcome.executed_steps == 0
    assert rebuilt.outcome.regret == 1.0


def test_candidate_coordinate_rejects_unsealed_policy_seed() -> None:
    memory = {"schema_version": "fixture-memory"}
    request = {
        "ordinal": 0,
        "phase": "support",
        "pair_index": 0,
        "arm": None,
        "episode_index": 0,
        "environment_seed": 0,
        "policy_seed": 999,
        "step_budget": 24,
        "retain_policy_updates": True,
        "policy_memory": memory,
        "policy_memory_sha256": canonical_digest(memory),
    }
    result = {
        "ordinal": 0,
        "memory_before": memory,
        "memory_before_sha256": canonical_digest(memory),
        "memory_after": memory,
        "memory_after_sha256": canonical_digest(memory),
    }
    expected = {
        "ordinal": 0,
        "phase": "support",
        "pair_index": 0,
        "arm": "source",
        "episode_index": 0,
    }
    with pytest.raises(
        verifier.CapabilityVerificationError,
        match="semantic coordinate mismatch",
    ):
        verifier._check_candidate_coordinate(
            {"ordinal": 0, "request": request, "worker_result": result},
            expected,
        )


def test_control_record_reexecutes_policy_and_rejects_claimed_outcome() -> None:
    environment = _P7Environment()
    observation = environment.observation("p7-state-0", goal_ref="p7-state-1")
    action_ids = [item["action_id"] for item in environment.public_actions()]
    selected = ReactiveControl.choose_action(observation, action_ids)
    if selected != "p7-action-inc":
        pytest.skip("hand fixture digest selected its non-goal action")
    record = {
        "policy": "reactive",
        "random_seed": None,
        "pair_index": 0,
        "episode_index": 0,
        "call_log": verifier._reexecute_control_call_log(
            environment=environment,
            episode_index=0,
            expected_policy=ReactiveControl(),
        ),
        "outcome": {
            "pair_index": 0,
            "episode_index": 0,
            "success": False,
            "optimal_steps": 1,
            "executed_steps": 1,
            "step_budget": 24,
        },
    }

    class _Pair:
        pair_index = 0
        private_ref = "hand-p7-pair"
        source = environment

    with pytest.raises(
        verifier.CapabilityVerificationError,
        match="caller-stored control outcome",
    ):
        verifier._control_record(
            record=record,
            pair=_Pair(),
            episode_index=0,
            expected_policy=ReactiveControl(),
            expected_label="reactive",
            expected_seed=None,
        )


def test_control_record_rejects_caller_truncated_policy_rollout() -> None:
    environment = _P7Environment()
    before = environment.observation("p7-state-0", goal_ref="p7-state-1")
    truncated = [
        _rpc_row(0, "reset", {"seed": 0}, {"reset": True}),
        _rpc_row(1, "observe", {}, before),
        _rpc_row(
            2,
            "valid_actions",
            {},
            list(environment.public_actions()),
        ),
        _rpc_row(
            3,
            "stop",
            {"reason": "policy_abstained"},
            {
                "stopped": True,
                "reason": "policy_abstained",
                "steps": 0,
                "success": False,
            },
        ),
    ]
    record = {
        "policy": "reactive",
        "random_seed": None,
        "pair_index": 0,
        "episode_index": 0,
        "call_log": truncated,
    }

    class _Pair:
        pair_index = 0
        private_ref = "hand-p7-pair"
        source = environment

    with pytest.raises(
        verifier.CapabilityVerificationError,
        match="full frozen-policy reexecution",
    ):
        verifier._control_record(
            record=record,
            pair=_Pair(),
            episode_index=0,
            expected_policy=ReactiveControl(),
            expected_label="reactive",
            expected_seed=None,
        )


def test_control_reexecution_matches_evaluator_log_and_random_stream() -> None:
    from scripts import gwip_capability_eval as evaluator

    environment = _P7Environment()

    class _Pair:
        pair_index = 0
        private_ref = "hand-p7-pair"
        source = environment

    producer = RandomControl(
        policy_seed=7,
        pair_binding=_Pair.private_ref,
    )
    consumer = RandomControl(
        policy_seed=7,
        pair_binding=_Pair.private_ref,
    )
    for episode_index in range(4):
        record = evaluator.run_control_episode(
            pair=_Pair(),
            episode_index=episode_index,
            policy=producer,
            policy_label="random",
            random_seed=7,
        )
        rebuilt = verifier._control_record(
            record=record,
            pair=_Pair(),
            episode_index=episode_index,
            expected_policy=consumer,
            expected_label="random",
            expected_seed=7,
        )
        assert rebuilt.pair_index == 0
        assert rebuilt.episode_index == episode_index


def test_incomplete_final_census_becomes_explicit_capability_red() -> None:
    hard_gates = {name: True for name in REQUIRED_HARD_GATES}
    result = verifier.verify_capability_evidence(
        pairs=(),
        episodes=(),
        parent_evidence={},
        controls={},
        hard_gates=hard_gates,
        preregistration=FROZEN_PREREGISTRATION,
    )
    assert result.derivation_complete is False
    assert result.metrics["verdict"] == "CAPABILITY_RED"
    assert result.metrics["capability_claim"] is False
    assert result.metrics["hard_gates"]["complete_lineage"] is False
    assert "sealed pair census" in result.findings[0]


def test_human_exemplar_uses_only_public_request_and_parent_log() -> None:
    outcomes = tuple(
        EpisodeOutcome(
            pair_index=pair,
            episode_index=episode,
            success=True,
            optimal_steps=1,
            executed_steps=1,
        )
        for pair in range(64)
        for episode in range(4)
    )
    worker_result = {"opaque_worker": True}
    request = {
        "goal_ir": {"metadata": {"target_constraints": [{"value": 1}]}},
        "environment_spec": {
            "schema_version": "hand.p7.public.v1",
            "valid_actions": list(_P7Environment.public_actions()),
        },
    }
    episode = {
        "ordinal": 0,
        "request": request,
        "worker_result": worker_result,
        "shard": {},
        "run_lease": {},
    }
    log = _successful_parent_log()
    evidence = {
        0: {
            "ordinal": 0,
            "status": "complete",
            "worker_result_sha256": canonical_digest(worker_result),
            "environment_sessions": {
                "primary": {
                    "call_log": log,
                    "call_log_sha256": canonical_digest(log),
                }
            },
        }
    }
    rendered = verifier.render_human_exemplar(
        candidate_support=outcomes,
        episodes=[episode],
        parent_evidence=evidence,
    )
    assert rendered["pair_index"] == 0
    assert rendered["episode_index"] == 0
    assert rendered["steps"][0]["selected_action"] == "p7-action-inc"
    assert rendered["private_oracle_fields_included"] is False
    assert "optimal_steps" not in str(rendered)
