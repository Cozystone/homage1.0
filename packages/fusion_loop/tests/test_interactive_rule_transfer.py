from __future__ import annotations

import copy

import pytest

from packages.cognitive_core import GoalIR, GoalOrigin
from packages.cognitive_core.canonical import canonical_digest
from packages.fusion_loop.interactive_organs import (
    LEGACY_MEMORY_SCHEMA_VERSION,
    MAX_RULE_HYPOTHESES,
    MEMORY_SCHEMA_VERSION,
    ActionOption,
    AtanorInteractivePolicy,
    InteractivePolicyMemory,
    action_payload_signature,
    evaluate_rule_ir,
    extract_goal_constraints,
    normalize_valid_actions,
    numeric_feature_projection,
    perceive_observation,
    validate_rule_ir,
    verify_learning_proof,
    verify_rule_plan_proof,
    _rule_key,
)


SOURCE_MODULUS = 7
TARGET_MODULUS = 11
VALUE_PATH = "/typed/slot/0"
CONTEXT_PATH = "/typed/base"
PROGRAMS = ((1, 1), (2, 1), (-1, 2), (3, -2))


def _observation(value: int, modulus: int) -> dict:
    return {
        "opaque_label": f"local-{modulus}-{value}",
        "done_marker": False,
        "typed": {"base": modulus, "slot": [value]},
    }


def _goal(value: int) -> GoalIR:
    return GoalIR(
        statement="Satisfy the structured target constraint.",
        origin=GoalOrigin.EXPLICIT_USER,
        metadata={
            "target_constraints": [
                {"path": VALUE_PATH, "op": "eq", "value": value}
            ]
        },
    )


def _action(action_id: str, cue: str) -> ActionOption:
    return ActionOption(
        action_id=action_id,
        payload={"opaque_semantic": cue},
    )


def _digest_actions(actions: tuple[ActionOption, ...]) -> str:
    return canonical_digest([item.to_dict() for item in actions])


def _learn_edge(
    policy: AtanorInteractivePolicy,
    *,
    action: ActionOption,
    before_value: int,
    after_value: int,
    modulus: int = SOURCE_MODULUS,
) -> tuple[str, object, dict, dict]:
    perception = perceive_observation(_observation(before_value, modulus))
    memory_before = policy.export_memory()
    edge_ref, proof = policy.learn(
        perception=perception,
        action_id=action.action_id,
        action=action,
        post_observation=_observation(after_value, modulus),
        success=False,
        goal=_goal(after_value),
    )
    memory_after = policy.export_memory()
    return edge_ref, proof, memory_before, memory_after


def test_numeric_projection_and_action_signature_are_schema_neutral() -> None:
    projected = numeric_feature_projection(
        {
            "verified": 1,
            "name": "ignored",
            "nested": {"count": 4, "items": [3, False, "ignored"]},
        },
        root_path="/nested",
    )
    assert projected.to_dict() == {
        "/nested/count": 4,
        "/nested/items/0": 3,
    }

    source = _action("source-local-id", "shared-opaque-cue")
    renamed = _action("renamed-target-id", "shared-opaque-cue")
    different = _action("other-id", "other-opaque-cue")
    assert action_payload_signature(source) == action_payload_signature(renamed)
    assert action_payload_signature(source) != action_payload_signature(different)
    assert action_payload_signature(ActionOption(action_id="legacy")) is None


def test_goal_constraints_and_rule_ir_reject_noncanonical_or_untyped_inputs() -> None:
    constraints = extract_goal_constraints(_goal(5))
    assert [item.to_dict() for item in constraints] == [
        {"op": "eq", "path": VALUE_PATH, "value": 5}
    ]

    malformed = {
        "schema_version": "atanor.gwip-feature-rule.v1",
        "action_signature": "a" * 64,
        "input_path": "/typed/slot/00",
        "output_path": VALUE_PATH,
        "context_path": CONTEXT_PATH,
        "expression": {"op": "copy", "path": VALUE_PATH},
        "support_edge_refs": ["one", "two", "three"],
        "hypothesis": True,
    }
    with pytest.raises(ValueError, match="numeric token"):
        validate_rule_ir(malformed)

    malformed["input_path"] = VALUE_PATH
    malformed["expression"] = {"op": "const", "value": True}
    with pytest.raises(ValueError, match="exact integer"):
        validate_rule_ir(malformed)


def test_v1_memory_migrates_deterministically_to_bounded_v2() -> None:
    legacy = {
        "action_sets": [],
        "attempts": [],
        "concepts_by_state": [],
        "schema_version": LEGACY_MEMORY_SCHEMA_VERSION,
        "target_state_digest": None,
        "transitions": [],
    }
    migrated = InteractivePolicyMemory.load(legacy).export()
    assert migrated["schema_version"] == MEMORY_SCHEMA_VERSION
    assert migrated["feature_edges"] == []
    assert migrated["rule_records"] == []
    assert migrated["semantic_attempts"] == []
    assert InteractivePolicyMemory.load(migrated).export() == migrated


def test_rule_is_emitted_provisionally_then_confirmed_by_a_later_edge() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")

    third = None
    for value in (0, 1, 2):
        third = _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    assert third is not None
    third_edge, third_proof, third_before, third_after = third
    provisional = third_proof.metadata["provisional_transition_rule_hypotheses"]
    assert len(provisional) == 1
    assert (
        third_proof.metadata["transition_rule_hypotheses"]
        == provisional
    )
    assert verify_learning_proof(
        proof=third_proof,
        before_observation=_observation(2, SOURCE_MODULUS),
        action=action,
        after_observation=_observation(5, SOURCE_MODULUS),
        edge_ref=third_edge,
        memory_before=third_before,
        memory_after=third_after,
        goal=_goal(5),
    )["passed"]

    fourth_edge, fourth_proof, fourth_before, fourth_after = _learn_edge(
        policy,
        action=action,
        before_value=3,
        after_value=0,
    )
    usable = fourth_proof.metadata["transition_rule_hypotheses"]
    assert len(usable) == 1
    assert fourth_proof.metadata["provisional_transition_rule_hypotheses"] == ()
    assert canonical_digest(provisional[0]) == canonical_digest(usable[0])
    assert fourth_proof.metadata["confirmed_rule_digests"] == (
        canonical_digest(usable[0]),
    )
    assert verify_learning_proof(
        proof=fourth_proof,
        before_observation=_observation(3, SOURCE_MODULUS),
        action=action,
        after_observation=_observation(0, SOURCE_MODULUS),
        edge_ref=fourth_edge,
        memory_before=fourth_before,
        memory_after=fourth_after,
        goal=_goal(0),
    )["passed"]

    predicted = evaluate_rule_ir(
        usable[0],
        numeric_feature_projection(
            _observation(4, TARGET_MODULUS),
            root_path="/typed",
        ),
    )
    assert predicted[VALUE_PATH] == 9
    assert predicted[CONTEXT_PATH] == TARGET_MODULUS


def test_provisional_rule_cannot_plan_and_goal_backed_plan_transfers_across_ids() -> None:
    policy = AtanorInteractivePolicy()
    source_action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2):
        _learn_edge(
            policy,
            action=source_action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )

    target_action = _action("renamed-target-operation", "shared-operation")
    actions = (target_action,)
    perception = perceive_observation(_observation(4, TARGET_MODULUS))
    before_confirmation = policy.select(
        perception=perception,
        valid_actions=actions,
        valid_actions_digest=_digest_actions(actions),
        policy_seed=5,
        goal=_goal(9),
    )
    assert before_confirmation is not None
    assert before_confirmation.strategy != "typed_rule_goal_plan"

    _learn_edge(
        policy,
        action=source_action,
        before_value=3,
        after_value=0,
    )
    one_step = policy.select(
        perception=perception,
        valid_actions=actions,
        valid_actions_digest=_digest_actions(actions),
        policy_seed=5,
        goal=_goal(9),
    )
    assert one_step is not None
    assert one_step.strategy == "typed_rule_goal_plan"
    assert one_step.action_id == target_action.action_id
    assert len(one_step.deliberator_proof["selected_plan"]) == 1
    assert len(one_step.deliberator_proof["transition_rule_hypotheses"]) == 1
    assert verify_rule_plan_proof(
        proof=one_step.deliberator_proof,
        goal=_goal(9),
        observation=perception.observation,
        action=target_action,
        memory=policy.export_memory(),
    )["passed"]

    two_step = policy.select(
        perception=perception,
        valid_actions=actions,
        valid_actions_digest=_digest_actions(actions),
        policy_seed=5,
        goal=_goal(8),
    )
    assert two_step is not None
    assert two_step.strategy == "typed_rule_goal_plan"
    assert len(two_step.deliberator_proof["selected_plan"]) == 2


def test_later_counterexample_invalidates_a_previously_usable_rule() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2, 3):
        _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    assert len(policy.memory.usable_rules()) == 1

    _edge, proof, _before, _after = _learn_edge(
        policy,
        action=action,
        before_value=4,
        after_value=3,
    )
    assert policy.memory.usable_rules() == ()
    assert proof.metadata["transition_rule_hypotheses"] == ()


def test_repeating_a_fitting_edge_cannot_confirm_its_own_rule() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2):
        _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    assert len(policy.memory.provisional_rules()) == 1

    _edge, repeated, _before, _after = _learn_edge(
        policy,
        action=action,
        before_value=2,
        after_value=5,
    )
    assert repeated.metadata["confirmed_rule_digests"] == ()
    assert len(policy.memory.provisional_rules()) == 1
    assert policy.memory.usable_rules() == ()

    _learn_edge(
        policy,
        action=action,
        before_value=3,
        after_value=0,
    )
    assert len(policy.memory.usable_rules()) == 1


def test_rule_induction_is_not_proportional_to_an_observed_modulus() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")
    huge_modulus = 10**30 + 151
    for value in (0, 1, 2):
        _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=2 * value + 1,
            modulus=huge_modulus,
        )
    assert len(policy.memory.provisional_rules()) == 1


def test_memory_rejects_confirmation_reusing_a_fitting_support_edge() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2, 3):
        _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    forged = policy.export_memory()
    record = forged["rule_records"][0]
    record["confirmation_edge_refs"] = [record["rule"]["support_edge_refs"][0]]
    with pytest.raises(ValueError, match="distinct from fitting support"):
        InteractivePolicyMemory.load(forged)


def test_memory_rejects_caller_supplied_hypotheses_above_the_bound() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2, 3):
        _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    forged = policy.export_memory()
    forged["rule_records"] = (
        forged["rule_records"] * (MAX_RULE_HYPOTHESES + 1)
    )
    with pytest.raises(ValueError, match="bounded count"):
        InteractivePolicyMemory.load(forged)


def test_memory_recomputes_rule_instead_of_trusting_usable_status() -> None:
    policy = AtanorInteractivePolicy()
    action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2, 3):
        _learn_edge(
            policy,
            action=action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    forged = policy.export_memory()
    record = forged["rule_records"][0]
    coefficient = (
        record["rule"]["expression"]["args"][0]["args"][0]["args"][1]
    )
    coefficient["value"] = 3
    record["rule_key"] = _rule_key(record["rule"])
    with pytest.raises(ValueError, match="reconstruct from its observed support"):
        InteractivePolicyMemory.load(forged)


def test_rule_plan_verifier_rejects_changed_plan_goal_or_action_payload() -> None:
    policy = AtanorInteractivePolicy()
    source_action = _action("source-operation", "shared-operation")
    for value in (0, 1, 2, 3):
        _learn_edge(
            policy,
            action=source_action,
            before_value=value,
            after_value=(2 * value + 1) % SOURCE_MODULUS,
        )
    target_action = _action("renamed-target-operation", "shared-operation")
    actions = normalize_valid_actions((target_action.to_dict(),))
    perception = perceive_observation(_observation(4, TARGET_MODULUS))
    proposal = policy.select(
        perception=perception,
        valid_actions=actions,
        valid_actions_digest=_digest_actions(actions),
        policy_seed=5,
        goal=_goal(9),
    )
    assert proposal is not None and proposal.strategy == "typed_rule_goal_plan"

    forged = copy.deepcopy(proposal.deliberator_proof.to_dict())
    forged["selected_plan"][0]["after"][VALUE_PATH] = 10
    assert not verify_rule_plan_proof(
        proof=forged,
        goal=_goal(9),
        observation=perception.observation,
        action=target_action,
        memory=policy.export_memory(),
    )["passed"]
    assert not verify_rule_plan_proof(
        proof=proposal.deliberator_proof,
        goal=_goal(8),
        observation=perception.observation,
        action=target_action,
        memory=policy.export_memory(),
    )["passed"]
    assert not verify_rule_plan_proof(
        proof=proposal.deliberator_proof,
        goal=_goal(9),
        observation=perception.observation,
        action=_action(target_action.action_id, "forged-operation"),
        memory=policy.export_memory(),
    )["passed"]


def test_bounded_acquisition_learns_four_rules_then_transfers_all_four() -> None:
    policy = AtanorInteractivePolicy()
    source_actions = tuple(
        _action(f"source-{index}", f"opaque-operation-{index}")
        for index in range(len(PROGRAMS))
    )
    source_by_id = {item.action_id: item for item in source_actions}
    support_episodes = ((0, 6), (1, 5), (2, 4), (3, 0))
    for episode, (start, target) in enumerate(support_episodes):
        value = start
        source_goal = _goal(target)
        succeeded = False
        for _step in range(24):
            perception = perceive_observation(
                _observation(value, SOURCE_MODULUS)
            )
            proposal = policy.select(
                perception=perception,
                valid_actions=source_actions,
                valid_actions_digest=_digest_actions(source_actions),
                    policy_seed=100 + episode,
                goal=source_goal,
            )
            assert proposal is not None
            action = source_by_id[proposal.action_id]
            index = int(action.action_id.rsplit("-", 1)[1])
            multiplier, offset = PROGRAMS[index]
            after = (multiplier * value + offset) % SOURCE_MODULUS
            succeeded = after == target
            policy.learn(
                perception=perception,
                action_id=action.action_id,
                action=action,
                post_observation=_observation(after, SOURCE_MODULUS),
                success=succeeded,
                goal=source_goal,
            )
            value = after
            if succeeded:
                break
        assert succeeded

    assert len(policy.memory.usable_rules()) == len(PROGRAMS)
    policy = AtanorInteractivePolicy.from_memory(policy.export_memory())
    target_start = 2
    target_actions = tuple(
        _action(f"target-{index}", f"opaque-operation-{index}")
        for index in range(len(PROGRAMS))
    )
    for expected_index, (multiplier, offset) in enumerate(PROGRAMS):
        target = (multiplier * target_start + offset) % TARGET_MODULUS
        proposal = policy.select(
            perception=perceive_observation(
                _observation(target_start, TARGET_MODULUS)
            ),
            valid_actions=target_actions,
            valid_actions_digest=_digest_actions(target_actions),
            policy_seed=31,
            goal=_goal(target),
        )
        assert proposal is not None
        assert proposal.strategy == "typed_rule_goal_plan"
        assert proposal.action_id == f"target-{expected_index}"
