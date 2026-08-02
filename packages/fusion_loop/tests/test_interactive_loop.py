from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

from packages.cognitive_core import (
    DecisionReceipt,
    FrozenMap,
    GoalIR,
    GoalOrigin,
    ProofCandidate,
    ReceiptMode,
    replay_cycle,
)
from packages.cognitive_core.canonical import canonical_digest
from packages.fusion_loop.interactive import (
    AuthorizationWitness,
    GenericWorldInteractionLoop,
    RunLeaseStepAuthority,
    reexecute_interactive_trace,
    verify_interactive_trace,
    verify_run_lease_trace,
)
from packages.fusion_loop.interactive_organs import (
    ActionOption,
    AtanorInteractivePolicy,
    InteractivePolicyMemory,
    normalize_valid_actions,
    perceive_observation,
)


class FixtureAuthority:
    def __init__(self, *, grants: int = 100) -> None:
        self.grants = grants
        self.calls: list[tuple[str, int]] = []
        self.finish_reasons: list[str] = []

    def authorize(self, action_id: str, step_index: int) -> AuthorizationWitness:
        self.calls.append((action_id, step_index))
        granted = len(self.calls) <= self.grants
        return AuthorizationWitness(
            action_id=action_id,
            step_index=step_index,
            granted=granted,
            reason="fixture_granted" if granted else "run_lease_fixture_denied",
            authority_kind="focused_fixture",
            operational_evidence={"call_count": len(self.calls)},
        )

    def finish(self, reason: str):
        self.finish_reasons.append(reason)
        return {"finished": True, "reason": reason}


class OpaqueEnvironment:
    """Small deterministic environment whose call log belongs to the fixture."""

    def __init__(self, *, terminal_at: int = 2, mutate_replay: bool = False) -> None:
        self.terminal_at = terminal_at
        self.mutate_replay = mutate_replay
        self.state = 0
        self.calls: list[tuple] = []
        self.stop_count = 0

    def reset(self, seed: int):
        self.state = 0
        self.calls.append(("reset", seed))
        return {"reset": "ok"}

    def observe(self):
        self.calls.append(("observe", self.state))
        value = self.state
        if self.mutate_replay and self.state == 1:
            value = 999
        return {
            "opaque_state": f"q{value}",
            # Caller-looking metadata is inert opaque observation data.
            "allowed": True,
            "source_status": "verified",
        }

    def valid_actions(self):
        self.calls.append(("valid_actions", self.state))
        return ("alpha", "beta")

    def step(self, action_id: str):
        self.calls.append(("step", action_id, self.state))
        self.state += 1
        success = self.state >= self.terminal_at
        return {
            "observation": {
                "opaque_state": f"q{self.state}",
                "allowed": True,
                "source_status": "verified",
            },
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }

    def stop(self, reason: str):
        self.calls.append(("stop", reason))
        self.stop_count += 1
        return {"stopped": True, "reason": reason}


class PayloadEnvironment(OpaqueEnvironment):
    """Nonfinal structured fixture with evaluator-owned action payloads."""

    def observe(self):
        self.calls.append(("observe", self.state))
        return {
            "fixture_schema": "nonfinal",
            "typed": {
                "base": 5,
                "slot": [self.state],
            },
            "local_ref": f"fixture-{self.state}",
            "done_marker": self.state >= self.terminal_at,
        }

    def valid_actions(self):
        self.calls.append(("valid_actions", self.state))
        return (
            {
                "action_id": "advance",
                "payload": {"fixture_hint": "shared"},
            },
            {
                "action_id": "hold",
                "payload": {"fixture_hint": "other"},
            },
        )

    def step(self, action_id: str):
        self.calls.append(("step", action_id, self.state))
        if action_id == "advance":
            self.state += 1
        success = self.state >= self.terminal_at
        return {
            "observation": {
                "fixture_schema": "nonfinal",
                "typed": {
                    "base": 5,
                    "slot": [self.state],
                },
                "local_ref": f"fixture-{self.state}",
                "done_marker": success,
            },
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }


class RecordingPolicy(AtanorInteractivePolicy):
    """Observe the existing policy handoff without replacing its behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.received_goals: list[GoalIR | None] = []
        self.received_actions: list[ActionOption | None] = []

    def select(self, *args, goal=None, **kwargs):
        self.received_goals.append(goal)
        return super().select(*args, goal=goal, **kwargs)

    def learn(self, *args, action=None, **kwargs):
        self.received_actions.append(action)
        return super().learn(*args, action=action, **kwargs)


def _goal() -> GoalIR:
    return GoalIR(
        statement="Reach the opaque target reference.",
        origin=GoalOrigin.EXPLICIT_USER,
        metadata={"target_ref": "opaque-target"},
    )


def _structured_goal(value: int = 1) -> GoalIR:
    return GoalIR(
        statement="Satisfy the nonfinal typed fixture constraint.",
        origin=GoalOrigin.EXPLICIT_USER,
        metadata={
            "target_constraints": [
                {
                    "op": "eq",
                    "path": "/typed/slot/0",
                    "value": value,
                }
            ]
        },
    )


def _reseal_trace(trace, **changes):
    provisional = replace(
        trace,
        semantic_trace_digest="0" * 64,
        **changes,
    )
    return replace(
        provisional,
        semantic_trace_digest=canonical_digest(
            provisional.semantic_projection()
        ),
    )


def _run(*, terminal_at: int = 2, budget: int = 20):
    environment = OpaqueEnvironment(terminal_at=terminal_at)
    authority = FixtureAuthority()
    loop = GenericWorldInteractionLoop(
        authority=authority,
        policy=AtanorInteractivePolicy(),
        require_run_lease=False,
    )
    trace = loop.run(
        environment,
        _goal(),
        environment_seed=7,
        policy_seed=11,
        step_budget=budget,
        session_id="fixture-session",
    )
    return environment, authority, trace


def test_complete_trace_has_exact_call_order_lineage_and_fresh_reexecution():
    environment, authority, trace = _run()

    assert trace.success is True
    assert trace.stop_reason == "goal_reached"
    assert len(trace.steps) == 2
    assert environment.stop_count == 1
    assert environment.calls == [
        ("reset", 7),
        ("observe", 0),
        ("valid_actions", 0),
        ("step", trace.steps[0].selected_action, 0),
        ("observe", 1),
        ("valid_actions", 1),
        ("step", trace.steps[1].selected_action, 1),
        ("stop", "goal_reached"),
    ]
    assert authority.calls == [
        (trace.steps[0].selected_action, 0),
        (trace.steps[1].selected_action, 1),
    ]
    assert authority.finish_reasons == ["goal_reached"]

    for index, step in enumerate(trace.steps):
        assert step.step_index == index
        assert step.authorization.granted is True
        assert step.decision_receipt.authoritative is False
        assert step.decision_receipt.action_executed is False
        assert step.world_snapshot.metadata["valid_actions_digest"] == (
            step.valid_actions_digest
        )
        assert sum(
            action.action_id == step.selected_action
            for action in step.valid_actions
        ) == 1
        assert step.learned_edge_ref
        if index:
            assert (
                step.world_snapshot.parent_snapshot_id
                == trace.steps[index - 1].world_snapshot.contract_id
            )

    replayed = replay_cycle(trace.cycle_receipt)
    assert replayed.state["status"] == "completed"
    assert trace.structural_receipt_authenticates_action is False
    verified = reexecute_interactive_trace(
        lambda: OpaqueEnvironment(terminal_at=2),
        trace,
        fixture_authority_verifier=lambda witness: witness.granted,
    )
    assert verified.environment_reexecution_ok, verified.errors
    assert verified.receipt_cross_check_ok
    assert verified.fixture_authority_check_ok is True
    assert verified.authority_independently_verified is False
    assert verified.ok is False
    serialized = trace.to_dict()
    assert len(serialized["lineage_steps"]) == len(trace.steps)
    for full, step in zip(serialized["lineage_steps"], trace.steps):
        assert full["authorization"] == step.authorization.to_dict()
        assert full["perception"] == step.perception.to_dict()
        assert full["cognitive_envelope"] == step.cognitive_envelope.to_dict()
        assert full["cognitive_moment"] == step.cognitive_moment.to_dict()
        assert full["proposal_proof"] == step.proposal_proof.to_dict()
        assert full["learning_proof"] == step.learning_proof.to_dict()


def test_same_inputs_and_starting_memory_produce_identical_semantic_trace():
    first_policy = AtanorInteractivePolicy()
    start = first_policy.export_memory()

    def once():
        environment = OpaqueEnvironment(terminal_at=2)
        authority = FixtureAuthority()
        policy = AtanorInteractivePolicy.from_memory(start)
        return GenericWorldInteractionLoop(
            authority=authority,
            policy=policy,
            require_run_lease=False,
        ).run(
            environment,
            _goal(),
            environment_seed=7,
            policy_seed=11,
            step_budget=20,
            session_id="fixture-session",
        )

    one = once()
    two = once()
    assert one.semantic_trace_digest == two.semantic_trace_digest
    assert one.cycle_receipt.to_dict() == two.cycle_receipt.to_dict()
    assert one.memory_after == two.memory_after


def test_budget_denies_next_proposal_before_authority_and_environment_mutation():
    environment, authority, trace = _run(terminal_at=99, budget=2)

    assert trace.success is False
    assert trace.stop_reason == "step_budget_exhausted"
    assert len(trace.steps) == 2
    assert trace.denied_attempt is not None
    assert trace.denied_attempt.step_index == 2
    assert len(authority.calls) == 2
    assert [call[0] for call in environment.calls].count("step") == 2
    assert environment.calls[-3][0] == "observe"
    assert environment.calls[-2][0] == "valid_actions"
    assert environment.calls[-1] == ("stop", "step_budget_exhausted")
    assert replay_cycle(trace.cycle_receipt).state["status"] == "cancelled"


def test_environment_metadata_cannot_self_authorize_a_denied_step():
    environment = OpaqueEnvironment(terminal_at=1)
    authority = FixtureAuthority(grants=0)
    trace = GenericWorldInteractionLoop(
        authority=authority,
        require_run_lease=False,
    ).run(
        environment,
        _goal(),
        environment_seed=1,
        policy_seed=1,
    )
    assert trace.success is False
    assert trace.denied_attempt is not None
    assert trace.denied_attempt.authorization is not None
    assert trace.denied_attempt.authorization.granted is False
    assert not any(call[0] == "step" for call in environment.calls)
    assert environment.stop_count == 1


def test_public_default_rejects_non_runlease_authority_and_run_has_no_trust_inputs():
    with pytest.raises(TypeError, match="RunLeaseStepAuthority"):
        GenericWorldInteractionLoop(authority=FixtureAuthority())

    parameters = set(inspect.signature(GenericWorldInteractionLoop.run).parameters)
    assert not {
        "allowed",
        "authority",
        "boundary",
        "context",
        "costs",
        "decision_receipt",
        "live_context",
        "store",
    } & parameters

    with pytest.raises(TypeError, match="exact RunLeaseStore"):
        RunLeaseStepAuthority(store=object(), lease_id="not-used")


def test_exact_runlease_store_is_independently_reconciled(tmp_path):
    from packages.autonomy_envelope.run_lease import (
        GENERAL_INTERACTION_RUNNER_ID,
        RunLeaseStore,
    )
    from packages.autonomy_envelope.tests.test_run_lease import (
        _live_context,
        _provision_boundary,
        _signed_lease,
    )

    private, boundary, _repository = _provision_boundary(tmp_path)
    context = _live_context(
        boundary,
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        max_actions=2,
    )
    context["limits"]["max_scratch_write_bytes"] = 0
    lease = _signed_lease(
        private,
        boundary,
        context,
        lease_id="gwip-integration-lease-0001",
        nonce="gwip-integration-nonce-0001",
    )
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed is True
    trace = GenericWorldInteractionLoop(
        authority=RunLeaseStepAuthority(
            store=store,
            lease_id=lease["lease_id"],
        ),
    ).run(
        OpaqueEnvironment(terminal_at=2),
        _goal(),
        environment_seed=7,
        policy_seed=11,
        step_budget=20,
        session_id="runlease-integration",
    )
    verification = verify_run_lease_trace(
        trace,
        store=store,
        lease_id=lease["lease_id"],
        environment_factory=lambda: OpaqueEnvironment(terminal_at=2),
    )
    assert verification.ok, verification.errors
    assert verification.authority_independently_verified is True


def test_self_consistent_forged_decision_receipt_fails_independent_cross_check():
    _environment, _authority, trace = _run(terminal_at=1)
    original = trace.steps[0]
    forged = DecisionReceipt(
        moment_id=original.decision_receipt.moment_id,
        mode=ReceiptMode.READ_ONLY,
        decision_kind=original.decision_receipt.decision_kind,
        rationale="Self-consistent but not selected by the loop.",
        selected_goal_id=original.decision_receipt.selected_goal_id,
        input_claim_ids=original.decision_receipt.input_claim_ids,
        proof_candidate_ids=original.decision_receipt.proof_candidate_ids,
        proposed_action={"action_id": "invented", "payload_digest": "0" * 64},
        metadata=original.decision_receipt.metadata,
    )
    assert forged.verify_identity()
    forged_step = replace(original, decision_receipt=forged)
    forged_trace = replace(trace, steps=(forged_step,))
    verification = verify_interactive_trace(forged_trace)
    assert not verification.receipt_cross_check_ok
    assert any("decision_receipt_mismatch" in item for item in verification.errors)


def test_self_consistent_forged_world_snapshot_fails_independent_cross_check():
    _environment, _authority, trace = _run(terminal_at=1)
    original = trace.steps[0]
    forged = replace(
        original.world_snapshot,
        metadata={
            **original.world_snapshot.metadata.to_dict(),
            "valid_actions_digest": "0" * 64,
        },
    )
    assert forged.verify_identity()
    forged_step = replace(original, world_snapshot=forged)
    forged_trace = replace(trace, steps=(forged_step,))
    verification = verify_interactive_trace(forged_trace)
    assert not verification.receipt_cross_check_ok
    assert any("world_snapshot_mismatch" in item for item in verification.errors)


def test_fixture_callback_cannot_claim_independent_authority_green():
    _environment, _authority, trace = _run(terminal_at=1)
    verification = reexecute_interactive_trace(
        lambda: OpaqueEnvironment(terminal_at=1),
        trace,
        fixture_authority_verifier=lambda _witness: True,
    )
    assert verification.fixture_authority_check_ok is True
    assert verification.authority_independently_verified is False
    assert verification.ok is False


def test_fresh_reexecution_detects_changed_environment_witness():
    _environment, _authority, trace = _run()
    verification = reexecute_interactive_trace(
        lambda: OpaqueEnvironment(terminal_at=2, mutate_replay=True),
        trace,
    )
    assert not verification.ok
    assert any("observation_mismatch" in item for item in verification.errors)


def test_policy_memory_round_trip_and_deliberator_verified_route():
    s0 = perceive_observation({"state": "s0"})
    s1 = perceive_observation({"state": "s1"})
    s2 = perceive_observation({"state": "s2"})
    memory = InteractivePolicyMemory()
    memory.register_actions(s0.observation_digest, ("go", "wait"))
    memory.register_actions(s1.observation_digest, ("finish",))
    memory.record(
        before_digest=s0.observation_digest,
        action_id="go",
        after_digest=s1.observation_digest,
        concepts=s0.concepts,
        success=False,
    )
    memory.record(
        before_digest=s1.observation_digest,
        action_id="finish",
        after_digest=s2.observation_digest,
        concepts=s1.concepts,
        success=True,
    )
    policy = AtanorInteractivePolicy.from_memory(memory.export())
    actions = normalize_valid_actions(("go", "wait"))
    proposal = policy.select(
        perception=s0,
        valid_actions=actions,
        valid_actions_digest=canonical_digest(
            [item.to_dict() for item in actions]
        ),
        policy_seed=3,
    )
    assert proposal is not None
    assert proposal.action_id == "go"
    assert proposal.strategy == "verified_route_to_observed_success"
    assert proposal.deliberator_proof["grounded"] is True
    assert (
        AtanorInteractivePolicy.from_memory(policy.export_memory()).export_memory()
        == policy.export_memory()
    )


def test_loop_hands_exact_goal_and_selected_action_payload_to_existing_policy():
    goal = _structured_goal()
    policy = RecordingPolicy()
    trace = GenericWorldInteractionLoop(
        authority=FixtureAuthority(),
        policy=policy,
        require_run_lease=False,
    ).run(
        PayloadEnvironment(terminal_at=1),
        goal,
        environment_seed=5,
        policy_seed=23,
        step_budget=4,
        session_id="nonfinal-payload-handoff",
    )

    assert trace.success is True
    assert policy.received_goals
    assert all(received is goal for received in policy.received_goals)
    assert len(policy.received_actions) == len(trace.steps)
    for received, step in zip(policy.received_actions, trace.steps):
        assert received is not None
        selected = next(
            item
            for item in step.valid_actions
            if item.action_id == step.selected_action
        )
        assert received is selected
        proof_metadata = step.proposal_proof.metadata
        assert proof_metadata["goal_digest"] == canonical_digest(goal.to_dict())
        assert (
            proof_metadata["transition_rule_hypotheses"]
            == step.proposal.deliberator_proof.get(
                "transition_rule_hypotheses",
                [],
            )
        )
        assert step.decision_receipt.metadata["goal_digest"] == (
            canonical_digest(goal.to_dict())
        )


def test_policy_replay_rejects_resealed_goal_payload_rule_and_memory_forgery():
    goal = _structured_goal()
    initial_memory = AtanorInteractivePolicy().export_memory()
    trace = GenericWorldInteractionLoop(
        authority=FixtureAuthority(),
        policy=AtanorInteractivePolicy.from_memory(initial_memory),
        require_run_lease=False,
    ).run(
        PayloadEnvironment(terminal_at=1),
        goal,
        environment_seed=5,
        policy_seed=23,
        step_budget=4,
        session_id="nonfinal-adversarial-replay",
    )
    assert trace.steps
    original = trace.steps[0]

    forged_goal = _reseal_trace(trace, goal=_structured_goal(4))
    goal_check = verify_interactive_trace(
        forged_goal,
        expected_goal=goal,
        expected_memory_before=initial_memory,
    )
    assert not goal_check.receipt_cross_check_ok
    assert "goal_binding_mismatch" in goal_check.errors

    forged_actions = tuple(
        (
            ActionOption(
                action_id=item.action_id,
                payload={"fixture_hint": "forged"},
            )
            if item.action_id == original.selected_action
            else item
        )
        for item in original.valid_actions
    )
    forged_payload_step = replace(
        original,
        valid_actions=forged_actions,
        valid_actions_digest=canonical_digest(
            [item.to_dict() for item in forged_actions]
        ),
    )
    payload_check = verify_interactive_trace(
        _reseal_trace(trace, steps=(forged_payload_step,)),
        expected_goal=goal,
        expected_memory_before=initial_memory,
    )
    assert not payload_check.receipt_cross_check_ok
    assert any(
        "policy_proposal_replay_mismatch" in item
        or "proposal_proof_mismatch" in item
        or "decision_receipt_mismatch" in item
        for item in payload_check.errors
    )

    forged_learning_metadata = {
        **original.learning_proof.metadata.to_dict(),
        "transition_rule_hypotheses": [
            {
                "hypothesis": True,
                "schema_version": "atanor.gwip-feature-rule.v1",
                "support_edge_refs": ["transition_edge_invented"],
            }
        ],
    }
    forged_learning_proof = ProofCandidate(
        claim_id=original.learning_proof.claim_id,
        method=original.learning_proof.method,
        premise_claim_ids=original.learning_proof.premise_claim_ids,
        derivation_steps=original.learning_proof.derivation_steps,
        verifier_refs=original.learning_proof.verifier_refs,
        metadata=forged_learning_metadata,
    )
    forged_rule_step = replace(
        original,
        learning_proof=forged_learning_proof,
    )
    rule_check = verify_interactive_trace(
        _reseal_trace(trace, steps=(forged_rule_step,)),
        expected_goal=goal,
        expected_memory_before=initial_memory,
    )
    assert not rule_check.receipt_cross_check_ok
    assert any(
        "learning_proof_replay_mismatch" in item
        or "learning_proof_lineage_mismatch" in item
        for item in rule_check.errors
    )

    forged_memory = FrozenMap(
        {
            **trace.memory_after.to_dict(),
            "caller_attested_support": True,
        }
    )
    memory_check = verify_interactive_trace(
        _reseal_trace(trace, memory_after=forged_memory),
        expected_goal=goal,
        expected_memory_before=initial_memory,
    )
    assert not memory_check.receipt_cross_check_ok
    assert "policy_memory_after_replay_mismatch" in memory_check.errors


def test_nonretaining_episode_never_carries_target_updates_between_steps():
    policy = AtanorInteractivePolicy()
    starting_memory = policy.export_memory()
    trace = GenericWorldInteractionLoop(
        authority=FixtureAuthority(),
        policy=policy,
        require_run_lease=False,
    ).run(
        PayloadEnvironment(terminal_at=99),
        _structured_goal(4),
        environment_seed=5,
        policy_seed=23,
        step_budget=2,
        retain_policy_updates=False,
        session_id="nonfinal-frozen-target-memory",
    )

    assert len(trace.steps) == 2
    assert trace.retain_policy_updates is False
    assert trace.memory_before.to_dict() == starting_memory
    assert trace.memory_after.to_dict() == starting_memory
    verified = verify_interactive_trace(
        trace,
        fixture_authority_verifier=lambda witness: witness.granted,
        expected_goal=_structured_goal(4),
        expected_memory_before=starting_memory,
    )
    assert verified.receipt_cross_check_ok, verified.errors

    forged_mode = _reseal_trace(trace, retain_policy_updates=True)
    forged_check = verify_interactive_trace(
        forged_mode,
        expected_goal=_structured_goal(4),
        expected_memory_before=starting_memory,
    )
    assert not forged_check.receipt_cross_check_ok
    assert "cycle_receipt_binding_mismatch" in forged_check.errors
