from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from packages.cognitive_core import GoalIR, GoalOrigin
from packages.cognitive_core.canonical import canonical_digest
from packages.fusion_loop.interactive import (
    AuthorizationWitness,
    GenericWorldInteractionLoop,
)
from packages.fusion_loop.interactive_organs import (
    ActionOption,
    AtanorInteractivePolicy,
    perceive_observation,
)
from scripts.gwip_capability_cycle_verify import (
    reseal_worker_owned_semantic_digest,
    verify_capability_trace,
    verify_forgery_rejection,
)


SOURCE_MODULUS = 7
TARGET_MODULUS = 11
REGISTER_PATH = "/features/registers/0"


def _observation(value: int, modulus: int, *, terminal: bool = False) -> dict:
    return {
        "schema_version": f"nonfinal-p{modulus}.v1",
        "state_ref": f"nonfinal-p{modulus}-state-{value}",
        "features": {
            "registers": [value],
            "context": {"modulus": modulus},
        },
        "terminal": terminal,
    }


def _goal(value: int) -> GoalIR:
    return GoalIR(
        statement="Satisfy the nonfinal structured target constraint.",
        origin=GoalOrigin.EXPLICIT_USER,
        metadata={
            "target_constraints": [
                {
                    "path": REGISTER_PATH,
                    "op": "eq",
                    "value": value,
                }
            ]
        },
    )


def _source_policy() -> AtanorInteractivePolicy:
    policy = AtanorInteractivePolicy()
    action = ActionOption(
        action_id="nonfinal-source-action",
        payload={"semantic_cue": "nonfinal-shared-affine-action"},
    )
    for value in (0, 1, 2, 3):
        after = (2 * value + 1) % SOURCE_MODULUS
        policy.learn(
            perception=perceive_observation(
                _observation(value, SOURCE_MODULUS)
            ),
            action_id=action.action_id,
            action=action,
            post_observation=_observation(after, SOURCE_MODULUS),
            success=False,
            goal=_goal(after),
        )
    assert len(policy.memory.usable_rules()) == 1
    return policy


class ParentLoggedEnvironment:
    def __init__(self) -> None:
        self.value = 4
        self.log: list[dict] = []

    def reset(self, seed: int) -> dict:
        self.value = 4
        result = {"reset": True}
        self.log.append(
            {
                "operation": "reset",
                "seed": seed,
                "result": copy.deepcopy(result),
            }
        )
        return result

    def observe(self) -> dict:
        result = _observation(self.value, TARGET_MODULUS)
        self.log.append(
            {
                "operation": "observe",
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result

    def valid_actions(self) -> list[dict]:
        result = [
            {
                "action_id": "nonfinal-target-action",
                "payload": {
                    "semantic_cue": "nonfinal-shared-affine-action"
                },
            }
        ]
        self.log.append(
            {
                "operation": "valid_actions",
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result

    def step(self, action_id: str) -> dict:
        before = self.value
        self.value = 9
        result = {
            "observation": _observation(
                self.value,
                TARGET_MODULUS,
                terminal=True,
            ),
            "terminal": True,
            "success": True,
            "stop_reason": "goal_reached",
        }
        self.log.append(
            {
                "operation": "step",
                "step_index": 0,
                "action_id": action_id,
                "before_state_ref": (
                    f"nonfinal-p{TARGET_MODULUS}-state-{before}"
                ),
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result

    def stop(self, reason: str) -> dict:
        result = {
            "stopped": True,
            "reason": reason,
            "steps": 1,
            "success": True,
        }
        self.log.append(
            {
                "operation": "stop",
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result


class ParentAuthority:
    def __init__(self) -> None:
        self.authorizations: list[dict] = []
        self.finish_receipt: dict | None = None

    def authorize(self, action_id: str, step_index: int) -> AuthorizationWitness:
        raw = {
            "action_id": action_id,
            "step_index": step_index,
            "granted": True,
            "reason": "run_lease_authorized",
            "authority_kind": "externally_signed_run_lease",
            "operational_evidence": {
                "runner_id": "general-interaction-loop-v1",
                "action_class": "interaction.step",
                "lease_id_sha256": "a" * 64,
                "counters": {
                    "cycles": step_index + 1,
                    "actions": step_index + 1,
                    "external_requests": 0,
                    "external_response_bytes": 0,
                    "scratch_write_bytes": 0,
                    "child_tasks": 0,
                    "concurrent_child_tasks": 0,
                },
            },
        }
        self.authorizations.append(copy.deepcopy(raw))
        return AuthorizationWitness(**raw)

    def finish(self, reason: str) -> dict:
        self.finish_receipt = {
            "finished": True,
            "lease_id": "nonfinal-p11-lease",
            "reason": "run_lease_finished",
            "runner_id": "general-interaction-loop-v1",
        }
        return copy.deepcopy(self.finish_receipt)


class RetainingP7Environment:
    def __init__(self) -> None:
        self.value = 2
        self.steps = 0
        self.log: list[dict] = []

    def _record(self, operation: str, result, **extra) -> None:
        self.log.append(
            {
                "operation": operation,
                **extra,
                "result": copy.deepcopy(result),
                **(
                    {}
                    if operation == "reset"
                    else {"result_sha256": canonical_digest(result)}
                ),
            }
        )

    def reset(self, seed: int) -> dict:
        self.value = 2
        self.steps = 0
        result = {"reset": True}
        self._record("reset", result, seed=seed)
        return result

    def observe(self) -> dict:
        result = _observation(self.value, SOURCE_MODULUS)
        self._record("observe", result)
        return result

    def valid_actions(self) -> list[dict]:
        result = [
            {
                "action_id": "nonfinal-p7-cycle-action",
                "payload": {"semantic_cue": "nonfinal-p7-cycle"},
            }
        ]
        self._record("valid_actions", result)
        return result

    def step(self, action_id: str) -> dict:
        before = self.value
        self.value = (2 * self.value + 1) % SOURCE_MODULUS
        step_index = self.steps
        self.steps += 1
        success = self.value == 2
        result = {
            "observation": _observation(
                self.value,
                SOURCE_MODULUS,
                terminal=success,
            ),
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }
        self._record(
            "step",
            result,
            step_index=step_index,
            action_id=action_id,
            before_state_ref=(
                f"nonfinal-p{SOURCE_MODULUS}-state-{before}"
            ),
        )
        return result

    def stop(self, reason: str) -> dict:
        result = {
            "stopped": True,
            "reason": reason,
            "steps": self.steps,
            "success": self.value == 2,
        }
        self._record("stop", result)
        return result


class MidEpisodeRuleEnvironment:
    """Expose a rule only after three retained, non-terminal transitions."""

    def __init__(self) -> None:
        self.value = 0
        self.steps = 0
        self.log: list[dict] = []

    def _record(self, operation: str, result, **extra) -> None:
        self.log.append(
            {
                "operation": operation,
                **extra,
                "result": copy.deepcopy(result),
                **(
                    {}
                    if operation == "reset"
                    else {"result_sha256": canonical_digest(result)}
                ),
            }
        )

    def reset(self, seed: int) -> dict:
        self.value = 0
        self.steps = 0
        result = {"reset": True}
        self._record("reset", result, seed=seed)
        return result

    def observe(self) -> dict:
        result = _observation(self.value, TARGET_MODULUS)
        self._record("observe", result)
        return result

    def valid_actions(self) -> list[dict]:
        result = [
            {
                "action_id": "mid-episode-rule-action",
                "payload": {"semantic_cue": "mid-episode-rule-action"},
            }
        ]
        self._record("valid_actions", result)
        return result

    def step(self, action_id: str) -> dict:
        before = self.value
        self.value = (self.value + 1) % TARGET_MODULUS
        step_index = self.steps
        self.steps += 1
        success = self.value == 4
        result = {
            "observation": _observation(
                self.value,
                TARGET_MODULUS,
                terminal=success,
            ),
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }
        self._record(
            "step",
            result,
            step_index=step_index,
            action_id=action_id,
            before_state_ref=(
                f"nonfinal-p{TARGET_MODULUS}-state-{before}"
            ),
        )
        return result

    def stop(self, reason: str) -> dict:
        result = {
            "stopped": True,
            "reason": reason,
            "steps": self.steps,
            "success": self.value == 4,
        }
        self._record("stop", result)
        return result


@pytest.fixture
def bound_trace() -> dict:
    policy = _source_policy()
    memory = policy.export_memory()
    environment = ParentLoggedEnvironment()
    authority = ParentAuthority()
    goal = _goal(9)
    request = {
        "goal_ir": goal.to_dict(),
        "environment_seed": 0,
        "policy_seed": 11,
        "step_budget": 4,
        "retain_policy_updates": False,
        "session_id": "nonfinal:p11:dynamic-session",
        "policy_memory": copy.deepcopy(memory),
        "policy_memory_sha256": canonical_digest(memory),
    }
    trace = GenericWorldInteractionLoop(
        authority=authority,
        policy=policy,
        require_run_lease=False,
    ).run(
        environment,
        goal,
        environment_seed=request["environment_seed"],
        policy_seed=request["policy_seed"],
        step_budget=request["step_budget"],
        retain_policy_updates=request["retain_policy_updates"],
        session_id=request["session_id"],
    )
    assert trace.steps[0].proposal.strategy == "typed_rule_goal_plan"
    assert trace.cycle_receipt.request_cycle.session_id == request["session_id"]
    assert authority.finish_receipt is not None
    return {
        "trace": trace.to_dict(),
        "request": request,
        "environment_log": environment.log,
        "parent_authorizations": authority.authorizations,
        "parent_finish": authority.finish_receipt,
    }


def _verify(bundle: dict, trace: dict | None = None) -> dict:
    return verify_capability_trace(
        trace or bundle["trace"],
        request=bundle["request"],
        environment_log=bundle["environment_log"],
        parent_authorizations=bundle["parent_authorizations"],
        parent_finish=bundle["parent_finish"],
    )


def _mid_episode_rule_bundle(*, retain_policy_updates: bool) -> dict:
    policy = AtanorInteractivePolicy()
    starting_memory = policy.export_memory()
    environment = MidEpisodeRuleEnvironment()
    authority = ParentAuthority()
    goal = _goal(4)
    request = {
        "goal_ir": goal.to_dict(),
        "environment_seed": 3,
        "policy_seed": 11,
        "step_budget": 6,
        "retain_policy_updates": retain_policy_updates,
        "session_id": (
            "nonfinal:p11:mid-episode-retaining"
            if retain_policy_updates
            else "nonfinal:p11:target-like-control"
        ),
        "policy_memory": copy.deepcopy(starting_memory),
        "policy_memory_sha256": canonical_digest(starting_memory),
    }
    trace = GenericWorldInteractionLoop(
        authority=authority,
        policy=policy,
        require_run_lease=False,
    ).run(
        environment,
        goal,
        environment_seed=request["environment_seed"],
        policy_seed=request["policy_seed"],
        step_budget=request["step_budget"],
        retain_policy_updates=retain_policy_updates,
        session_id=request["session_id"],
    ).to_dict()
    return {
        "trace": trace,
        "request": request,
        "environment_log": environment.log,
        "parent_authorizations": authority.authorizations,
        "parent_finish": authority.finish_receipt,
    }


def _mutate_both_step_projections(
    trace: dict,
    mutator,
) -> dict:
    forged = copy.deepcopy(trace)
    mutator(forged["semantic_trace"]["steps"][0])
    mutator(forged["lineage_steps"][0])
    return reseal_worker_owned_semantic_digest(forged)


def test_independent_verifier_accepts_parent_bound_nonfinal_trace(
    bound_trace: dict,
) -> None:
    result = _verify(bound_trace)
    assert result["passed"], result["findings"]
    assert all(result["surfaces"].values())
    assert result["candidate_verifier_imported"] is False
    assert result["production_authority_claim"] is False


def test_verifier_source_is_standard_library_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "gwip_capability_cycle_verify.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name == "packages" or name.startswith("packages.") for name in imported)
    assert not any(
        name.startswith("scripts.gwip_capability")
        for name in imported
    )


def test_rejects_caller_resealed_decision_forgery(bound_trace: dict) -> None:
    forged = _mutate_both_step_projections(
        bound_trace["trace"],
        lambda step: step["decision_receipt"]["proposed_action"].__setitem__(
            "action_id",
            "caller-invented-action",
        ),
    )
    receipt = verify_forgery_rejection(
        bound_trace["trace"],
        forged,
        request=bound_trace["request"],
        environment_log=bound_trace["environment_log"],
        parent_authorizations=bound_trace["parent_authorizations"],
        parent_finish=bound_trace["parent_finish"],
    )
    assert receipt["passed"]
    assert receipt["forged"]["surfaces"]["decision_lineage"] is False


def test_rejects_caller_resealed_world_forgery(bound_trace: dict) -> None:
    forged = _mutate_both_step_projections(
        bound_trace["trace"],
        lambda step: step["world_snapshot"]["metadata"].__setitem__(
            "valid_actions_digest",
            "0" * 64,
        ),
    )
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["world_lineage"] is False


def test_rejects_caller_resealed_authority_forgery(bound_trace: dict) -> None:
    forged = _mutate_both_step_projections(
        bound_trace["trace"],
        lambda step: step["authorization"].__setitem__(
            "reason",
            "caller_attested_authority",
        ),
    )
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["authority_binding"] is False


def test_rejects_caller_resealed_goal_forgery(bound_trace: dict) -> None:
    forged = copy.deepcopy(bound_trace["trace"])
    forged["semantic_trace"]["goal"] = _goal(8).to_dict()
    forged = reseal_worker_owned_semantic_digest(forged)
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["goal_binding"] is False


def test_rejects_caller_resealed_action_payload_forgery(
    bound_trace: dict,
) -> None:
    def mutate(step: dict) -> None:
        step["valid_actions"][0]["payload"]["semantic_cue"] = (
            "caller-forged-action-cue"
        )
        step["valid_actions_digest"] = canonical_digest(
            step["valid_actions"]
        )

    forged = _mutate_both_step_projections(bound_trace["trace"], mutate)
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["action_binding"] is False


def test_rejects_caller_resealed_memory_forgery(bound_trace: dict) -> None:
    forged = copy.deepcopy(bound_trace["trace"])
    forged["semantic_trace"]["memory_before"]["caller_attested"] = True
    forged["semantic_trace"]["memory_after"]["caller_attested"] = True
    forged = reseal_worker_owned_semantic_digest(forged)
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["memory_binding"] is False


def test_rejects_caller_resealed_rule_ir_forgery(bound_trace: dict) -> None:
    def mutate(step: dict) -> None:
        rule = step["proposal"]["deliberator_proof"][
            "transition_rule_hypotheses"
        ][0]
        rule["expression"]["args"][0]["args"][0]["args"][1]["value"] = 3

    forged = _mutate_both_step_projections(bound_trace["trace"], mutate)
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["rule_ir"] is False


def test_dynamic_session_and_retain_flag_are_cycle_bound(
    bound_trace: dict,
) -> None:
    forged = copy.deepcopy(bound_trace["trace"])
    forged["semantic_trace"]["retain_policy_updates"] = True
    forged = reseal_worker_owned_semantic_digest(forged)
    result = _verify(bound_trace, forged)
    assert not result["passed"]
    assert result["surfaces"]["request_binding"] is False
    assert result["surfaces"]["cycle_receipt"] is False

    wrong_request = copy.deepcopy(bound_trace["request"])
    wrong_request["session_id"] = "nonfinal:p11:other-session"
    session_result = verify_capability_trace(
        bound_trace["trace"],
        request=wrong_request,
        environment_log=bound_trace["environment_log"],
        parent_authorizations=bound_trace["parent_authorizations"],
        parent_finish=bound_trace["parent_finish"],
    )
    assert not session_result["passed"]
    assert session_result["surfaces"]["world_lineage"] is False
    assert session_result["surfaces"]["cycle_receipt"] is False


def test_retaining_memory_evolution_is_parent_trace_bound() -> None:
    policy = AtanorInteractivePolicy()
    starting_memory = policy.export_memory()
    environment = RetainingP7Environment()
    authority = ParentAuthority()
    goal = _goal(2)
    request = {
        "goal_ir": goal.to_dict(),
        "environment_seed": 2,
        "policy_seed": 7,
        "step_budget": 6,
        "retain_policy_updates": True,
        "session_id": "nonfinal:p7:retaining",
        "policy_memory": copy.deepcopy(starting_memory),
        "policy_memory_sha256": canonical_digest(starting_memory),
    }
    trace = GenericWorldInteractionLoop(
        authority=authority,
        policy=policy,
        require_run_lease=False,
    ).run(
        environment,
        goal,
        environment_seed=request["environment_seed"],
        policy_seed=request["policy_seed"],
        step_budget=request["step_budget"],
        retain_policy_updates=True,
        session_id=request["session_id"],
    ).to_dict()
    baseline = verify_capability_trace(
        trace,
        request=request,
        environment_log=environment.log,
        parent_authorizations=authority.authorizations,
        parent_finish=authority.finish_receipt,
    )
    assert baseline["passed"], baseline["findings"]

    forged = copy.deepcopy(trace)
    forged["semantic_trace"]["memory_after"]["transitions"][0]["count"] += 1
    forged = reseal_worker_owned_semantic_digest(forged)
    result = verify_capability_trace(
        forged,
        request=request,
        environment_log=environment.log,
        parent_authorizations=authority.authorizations,
        parent_finish=authority.finish_receipt,
    )
    assert not result["passed"]
    assert result["surfaces"]["memory_binding"] is False
    assert any(
        "evolution_mismatch" in item
        for item in result["surface_findings"]["memory_binding"]
    )


def test_retaining_rule_plan_uses_memory_at_each_step() -> None:
    bundle = _mid_episode_rule_bundle(retain_policy_updates=True)
    trace = bundle["trace"]["semantic_trace"]
    assert len(trace["steps"]) == 4
    assert trace["memory_before"]["rule_records"] == []
    assert (
        trace["steps"][2]["learning_proof"]["metadata"][
            "provisional_transition_rule_hypotheses"
        ]
    )
    assert (
        trace["steps"][3]["proposal"]["deliberator_proof"][
            "transition_rule_hypotheses"
        ]
    )

    result = _verify(bundle)
    assert result["passed"], result["findings"]


def test_nonretaining_target_like_rule_plan_control_is_unchanged() -> None:
    bundle = _mid_episode_rule_bundle(retain_policy_updates=False)
    trace = bundle["trace"]["semantic_trace"]
    assert len(trace["steps"]) == 4
    assert trace["memory_after"] == trace["memory_before"]
    assert all(
        not step["proposal"]["deliberator_proof"].get(
            "transition_rule_hypotheses"
        )
        for step in trace["steps"]
    )

    result = _verify(bundle)
    assert result["passed"], result["findings"]


def test_rejects_coforged_mid_episode_rule_cursor() -> None:
    bundle = _mid_episode_rule_bundle(retain_policy_updates=True)
    forged = copy.deepcopy(bundle["trace"])
    for steps in (
        forged["semantic_trace"]["steps"],
        forged["lineage_steps"],
    ):
        learning = steps[2]["learning_proof"]["metadata"]
        learning["transition_rule_hypotheses"] = []
        learning["provisional_transition_rule_hypotheses"] = []
        learning["emitted_provisional_rule_digests"] = []
        steps[3]["proposal"]["deliberator_proof"][
            "transition_rule_hypotheses"
        ] = []
    forged = reseal_worker_owned_semantic_digest(forged)

    result = _verify(bundle, forged)
    assert not result["passed"]
    assert result["surfaces"]["rule_ir"] is False
    assert any(
        "memory_evolution_mismatch" in finding
        or "hypothesis_set_memory_mismatch" in finding
        for finding in result["surface_findings"]["rule_ir"]
    )
