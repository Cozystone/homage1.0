"""General, domain-neutral world-interaction coordinator.

This is a joint inside the existing fusion loop, not a new authority.  An
environment supplies only opaque observations, its actual valid action set,
and transition results.  The coordinator creates non-authoritative cognitive
records, asks an installation-owned RunLease adapter for permission, performs
at most one exact valid action, and records the observed effect.

Canonical hashes and ``DecisionReceipt.verify_identity()`` establish structural
self-consistency only.  :func:`reexecute_interactive_trace` is the independent
environment check; callers must separately verify the RunLease operational
witness when making a mechanism claim.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from packages.cognitive_core import (
    CanonicalEntityRef,
    CognitiveEnvelope,
    CognitiveMoment,
    CycleEvent,
    CyclePhase,
    CycleReceipt,
    CycleStatus,
    DecisionReceipt,
    EntityKind,
    FrozenMap,
    GoalIR,
    ProofCandidate,
    ReceiptMode,
    RequestCycle,
    WorldSnapshot,
    replay_cycle,
)
from packages.cognitive_core.canonical import canonical_digest, canonical_id
from packages.autonomy_envelope.run_lease import (
    GENERAL_INTERACTION_RUNNER_ID,
    RunLeaseStore,
)

from .interactive_organs import (
    ActionOption,
    ActionProposal,
    AtanorInteractivePolicy,
    PerceptionBundle,
    action_payload_signature,
    bounded_mapping,
    normalize_valid_actions,
    opaque_digest,
    perceive_observation,
    verify_learning_proof,
    verify_rule_plan_proof,
)


GENERAL_INTERACTION_ACTION_CLASS = "interaction.step"
INTERACTIVE_TRACE_SCHEMA_VERSION = "atanor.gwip-interactive-trace.v2"

_FIXED_STEP_COSTS = {
    "cycles": 1,
    "actions": 1,
    "external_requests": 0,
    "external_response_bytes": 0,
    "scratch_write_bytes": 0,
    "child_tasks": 0,
    "concurrent_child_tasks": 0,
}


@runtime_checkable
class InteractiveEnvironment(Protocol):
    """Evaluator-owned reset/observe/action transition surface."""

    def reset(self, seed: int) -> Mapping[str, Any] | None: ...

    def observe(self) -> Mapping[str, Any]: ...

    def valid_actions(self) -> Sequence[str | Mapping[str, Any]]: ...

    def step(self, action_id: str) -> Mapping[str, Any]: ...

    def stop(self, reason: str) -> Mapping[str, Any] | None: ...


@runtime_checkable
class StepAuthority(Protocol):
    """Internal test seam; production-default execution requires RunLease."""

    def authorize(self, action_id: str, step_index: int) -> "AuthorizationWitness": ...

    def finish(self, reason: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True, kw_only=True)
class AuthorizationWitness:
    """Audit evidence returned by the authority dependency, never a capability."""

    action_id: str
    step_index: int
    granted: bool
    reason: str
    authority_kind: str
    operational_evidence: FrozenMap = field(default_factory=FrozenMap)
    witness_id: str = field(init=False)
    bearer_capability: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id:
            raise ValueError("authorization witness requires action_id")
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("authorization witness step_index must be nonnegative")
        if type(self.granted) is not bool:
            raise TypeError("authorization witness granted must be boolean")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("authorization witness requires reason")
        if not isinstance(self.authority_kind, str) or not self.authority_kind:
            raise ValueError("authorization witness requires authority_kind")
        object.__setattr__(
            self,
            "operational_evidence",
            bounded_mapping(
                self.operational_evidence,
                name="authorization operational evidence",
            ),
        )
        object.__setattr__(
            self,
            "witness_id",
            canonical_id(
                "authorization_witness",
                {
                    "action_id": self.action_id,
                    "authority_kind": self.authority_kind,
                    "granted": self.granted,
                    "operational_evidence": self.operational_evidence,
                    "reason": self.reason,
                    "step_index": self.step_index,
                },
            )[0],
        )

    def semantic_dict(self) -> dict[str, Any]:
        """Exclude lease counters/nonces/timestamps from deterministic equality."""

        return {
            "action_id": self.action_id,
            "authority_kind": self.authority_kind,
            "granted": self.granted,
            "reason": self.reason,
            "step_index": self.step_index,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_dict(),
            "bearer_capability": self.bearer_capability,
            "operational_evidence": self.operational_evidence.to_dict(),
            "witness_id": self.witness_id,
        }


class RunLeaseStepAuthority:
    """Exact-type adapter around ``RunLeaseStore.authorize`` with fixed costs.

    The adapter is constructed by the installation/evaluator composition root.
    No environment payload can provide a store, boundary, live context, action
    class, costs, receipt, or ``allowed`` value.
    """

    __slots__ = ("_store", "_lease_id", "_runner_id", "_finished")

    def __init__(
        self,
        *,
        store: Any,
        lease_id: str,
    ) -> None:
        if type(store) is not RunLeaseStore:
            raise TypeError("RunLeaseStepAuthority requires an exact RunLeaseStore")
        if not isinstance(lease_id, str) or not lease_id:
            raise ValueError("RunLeaseStepAuthority requires lease_id")
        self._store = store
        self._lease_id = lease_id
        self._runner_id = GENERAL_INTERACTION_RUNNER_ID
        self._finished = False

    def authorize(self, action_id: str, step_index: int) -> AuthorizationWitness:
        result = self._store.authorize(
            lease_id=self._lease_id,
            runner_id=self._runner_id,
            action_class=GENERAL_INTERACTION_ACTION_CLASS,
            costs=dict(_FIXED_STEP_COSTS),
        )
        counters = dict(result.counters or {})
        return AuthorizationWitness(
            action_id=action_id,
            step_index=step_index,
            granted=result.allowed is True,
            reason=result.reason,
            authority_kind="externally_signed_run_lease",
            operational_evidence={
                "action_class": GENERAL_INTERACTION_ACTION_CLASS,
                "counters": counters,
                "lease_id_sha256": canonical_digest(self._lease_id),
                "runner_id": self._runner_id,
            },
        )

    def finish(self, reason: str) -> Mapping[str, Any]:
        if self._finished:
            return {"finished": False, "reason": "run_lease_finish_already_observed"}
        self._finished = True
        return self._store.finish(
            lease_id=self._lease_id,
            runner_id=self._runner_id,
            reason=reason,
        ).to_dict()


@dataclass(frozen=True, kw_only=True)
class EnvironmentStepResult:
    """Strict evaluator transition witness."""

    observation: FrozenMap
    terminal: bool
    success: bool
    stop_reason: str | None
    result_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation",
            bounded_mapping(self.observation, name="step-result observation"),
        )
        if type(self.terminal) is not bool or type(self.success) is not bool:
            raise TypeError("step-result terminal and success must be booleans")
        if self.stop_reason is not None and (
            not isinstance(self.stop_reason, str) or not self.stop_reason.strip()
        ):
            raise ValueError("step-result stop_reason must be non-empty or null")
        object.__setattr__(
            self,
            "result_digest",
            canonical_digest(
                {
                    "observation": self.observation,
                    "stop_reason": self.stop_reason,
                    "success": self.success,
                    "terminal": self.terminal,
                }
            ),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EnvironmentStepResult":
        if not isinstance(value, Mapping):
            raise TypeError("environment step result must be a mapping")
        required = {"observation", "terminal", "success", "stop_reason"}
        if set(value) != required:
            raise ValueError(
                "environment step result requires exactly observation, terminal, "
                "success, and stop_reason"
            )
        return cls(
            observation=value["observation"],
            terminal=value["terminal"],
            success=value["success"],
            stop_reason=value["stop_reason"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation.to_dict(),
            "result_digest": self.result_digest,
            "stop_reason": self.stop_reason,
            "success": self.success,
            "terminal": self.terminal,
        }


@dataclass(frozen=True, kw_only=True)
class InteractiveStep:
    """Complete lineage for one executed environment action."""

    step_index: int
    pre_observation: FrozenMap
    perception: PerceptionBundle
    valid_actions: tuple[ActionOption, ...]
    valid_actions_digest: str
    world_snapshot: WorldSnapshot
    cognitive_envelope: CognitiveEnvelope
    cognitive_moment: CognitiveMoment
    proposal: ActionProposal
    proposal_proof: ProofCandidate
    decision_receipt: DecisionReceipt
    authorization: AuthorizationWitness
    step_result: EnvironmentStepResult
    learned_edge_ref: str
    learning_proof: ProofCandidate

    @property
    def selected_action(self) -> str:
        return self.proposal.action_id

    @property
    def post_observation(self) -> FrozenMap:
        return self.step_result.observation

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "authorization": self.authorization.semantic_dict(),
            "decision_receipt": self.decision_receipt.to_dict(),
            "learned_edge_ref": self.learned_edge_ref,
            "learning_proof": self.learning_proof.to_dict(),
            "post_observation": self.post_observation.to_dict(),
            "pre_observation": self.pre_observation.to_dict(),
            "proposal": self.proposal.to_dict(),
            "proposal_proof": self.proposal_proof.to_dict(),
            "selected_action": self.selected_action,
            "step_index": self.step_index,
            "step_result": self.step_result.to_dict(),
            "valid_actions": [item.to_dict() for item in self.valid_actions],
            "valid_actions_digest": self.valid_actions_digest,
            "world_snapshot": self.world_snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_dict(),
            # ``semantic_dict`` deliberately omits operational lease evidence
            # so deterministic replay does not depend on counters/nonces.  The
            # complete lineage projection must retain that evidence for an
            # evaluator-owned comparison with the authority transcript.
            "authorization": self.authorization.to_dict(),
            "cognitive_envelope": self.cognitive_envelope.to_dict(),
            "cognitive_moment": self.cognitive_moment.to_dict(),
            "perception": self.perception.to_dict(),
        }


@dataclass(frozen=True, kw_only=True)
class DeniedAttempt:
    """A proposed but unexecuted action stopped by budget or authority."""

    step_index: int
    pre_observation: FrozenMap
    valid_actions: tuple[ActionOption, ...]
    valid_actions_digest: str
    proposal: ActionProposal
    reason: str
    authorization: AuthorizationWitness | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization": (
                self.authorization.to_dict() if self.authorization is not None else None
            ),
            "pre_observation": self.pre_observation.to_dict(),
            "proposal": self.proposal.to_dict(),
            "reason": self.reason,
            "step_index": self.step_index,
            "valid_actions": [item.to_dict() for item in self.valid_actions],
            "valid_actions_digest": self.valid_actions_digest,
        }


@dataclass(frozen=True, kw_only=True)
class InteractiveTrace:
    """One terminal mechanism trace."""

    goal: GoalIR
    environment_seed: int
    policy_seed: int
    step_budget: int
    retain_policy_updates: bool
    reset_result: FrozenMap
    steps: tuple[InteractiveStep, ...]
    denied_attempt: DeniedAttempt | None
    stop_reason: str
    stop_result: FrozenMap
    authority_finish: FrozenMap
    success: bool
    memory_before: FrozenMap
    memory_after: FrozenMap
    cycle_receipt: CycleReceipt
    semantic_trace_digest: str
    schema_version: str = field(default=INTERACTIVE_TRACE_SCHEMA_VERSION, init=False)
    mechanism_only: bool = field(default=True, init=False)
    production_default_on: bool = field(default=False, init=False)
    structural_receipt_authenticates_action: bool = field(default=False, init=False)

    def semantic_projection(self) -> dict[str, Any]:
        return {
            "denied_attempt": (
                None
                if self.denied_attempt is None
                else {
                    **self.denied_attempt.to_dict(),
                    "authorization": (
                        self.denied_attempt.authorization.semantic_dict()
                        if self.denied_attempt.authorization is not None
                        else None
                    ),
                }
            ),
            "environment_seed": self.environment_seed,
            "goal": self.goal.to_dict(),
            "memory_after": self.memory_after.to_dict(),
            "memory_before": self.memory_before.to_dict(),
            "policy_seed": self.policy_seed,
            "reset_result": self.reset_result.to_dict(),
            "retain_policy_updates": self.retain_policy_updates,
            "step_budget": self.step_budget,
            "steps": [step.semantic_dict() for step in self.steps],
            "stop_reason": self.stop_reason,
            "stop_result": self.stop_result.to_dict(),
            "success": self.success,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_finish": self.authority_finish.to_dict(),
            "cycle_receipt": self.cycle_receipt.to_dict(),
            # Keep the complete, non-authoritative lineage alongside the
            # deterministic semantic projection.  The latter intentionally
            # omits operational witnesses so replay digests stay stable; an
            # external evaluator still needs the full perception/proof/
            # workspace chain in order to verify lineage independently.
            "lineage_steps": [step.to_dict() for step in self.steps],
            "mechanism_only": self.mechanism_only,
            "production_default_on": self.production_default_on,
            "schema_version": self.schema_version,
            "semantic_trace": self.semantic_projection(),
            "semantic_trace_digest": self.semantic_trace_digest,
            "structural_receipt_authenticates_action": (
                self.structural_receipt_authenticates_action
            ),
        }


@dataclass(frozen=True, kw_only=True)
class TraceVerification:
    """Explicitly separates structural, environment, and authority evidence."""

    errors: tuple[str, ...]
    structural_replay_ok: bool
    receipt_cross_check_ok: bool
    environment_reexecution_ok: bool
    authority_independently_verified: bool
    fixture_authority_check_ok: bool = False

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and self.structural_replay_ok
            and self.receipt_cross_check_ok
            and self.environment_reexecution_ok
            and self.authority_independently_verified
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_independently_verified": self.authority_independently_verified,
            "environment_reexecution_ok": self.environment_reexecution_ok,
            "errors": list(self.errors),
            "fixture_authority_check_ok": self.fixture_authority_check_ok,
            "ok": self.ok,
            "receipt_cross_check_ok": self.receipt_cross_check_ok,
            "structural_replay_ok": self.structural_replay_ok,
        }


def _valid_actions_digest(actions: Sequence[ActionOption]) -> str:
    return canonical_digest([item.to_dict() for item in actions])


def _proposal_proof(
    *,
    proposal: ActionProposal,
    perception: PerceptionBundle,
    goal: GoalIR,
    selected_action: ActionOption,
) -> ProofCandidate:
    route_proof = proposal.deliberator_proof.to_dict()
    grounded = route_proof.get("grounded") is True
    hypotheses = route_proof.get("transition_rule_hypotheses", [])
    if not isinstance(hypotheses, list):
        hypotheses = []
    selected_plan = route_proof.get("selected_plan")
    steps = (
        ("DELIBERATOR re-verified the learned route.",)
        if grounded
        else ("Systematic exploration selected an evaluator-returned action.",)
    )
    return ProofCandidate(
        claim_id=perception.claim.contract_id,
        method=(
            "deliberator_verified_transition_route"
            if grounded
            else "bounded_systematic_exploration"
        ),
        premise_claim_ids=(perception.claim.contract_id,),
        derivation_steps=steps,
        verifier_refs=(proposal.proposal_id,),
        metadata={
            "action_payload_signature": action_payload_signature(
                selected_action.payload
            ),
            "goal_digest": canonical_digest(goal.to_dict()),
            "proposal_id": proposal.proposal_id,
            "route_proof": route_proof,
            "selected_action_id": selected_action.action_id,
            "selected_plan": selected_plan,
            # This exact top-level key is the preregistered evaluator
            # extraction point.  Keeping it outside ``route_proof`` prevents a
            # nested caller blob from being mistaken for independently bound
            # rule lineage.
            "transition_rule_hypotheses": hypotheses,
        },
    )


def _build_decision_records(
    *,
    step_index: int,
    goal: GoalIR,
    perception: PerceptionBundle,
    valid_actions: Sequence[ActionOption],
    valid_actions_digest: str,
    parent_snapshot_id: str | None,
    proposal: ActionProposal,
    step_budget: int,
    session_id: str,
) -> tuple[
    WorldSnapshot,
    CognitiveEnvelope,
    CognitiveMoment,
    ProofCandidate,
    DecisionReceipt,
]:
    snapshot = WorldSnapshot(
        world_time=f"logical:{step_index}",
        snapshot_index=step_index,
        observed_claim_ids=(perception.claim.contract_id,),
        parent_snapshot_id=parent_snapshot_id,
        metadata={
            "observation_digest": perception.observation_digest,
            "organ_digest": perception.organ_digest,
            "valid_actions_digest": valid_actions_digest,
        },
    )
    action_by_id = {item.action_id: item for item in valid_actions}
    selected = action_by_id[proposal.action_id]
    proposal_proof = _proposal_proof(
        proposal=proposal,
        perception=perception,
        goal=goal,
        selected_action=selected,
    )
    envelope = CognitiveEnvelope(
        session_id=session_id,
        explicit_user_goal_ids=(goal.contract_id,),
        world_snapshot_id=snapshot.contract_id,
        resource_limits={
            "step_budget": float(step_budget),
            "steps_remaining": float(max(0, step_budget - step_index)),
        },
        context={"loop": "generic_world_interaction"},
    )
    moment = CognitiveMoment(
        moment_index=step_index,
        envelope_id=envelope.contract_id,
        world_snapshot_id=snapshot.contract_id,
        active_goal_ids=(goal.contract_id,),
        selected_goal_id=goal.contract_id,
        claim_ids=(perception.claim.contract_id,),
        proof_candidate_ids=(proposal_proof.contract_id,),
        attention_targets=(
            perception.claim.contract_id,
            proposal.proposal_id,
        ),
        resource_state={
            "step_budget": float(step_budget),
            "steps_remaining": float(max(0, step_budget - step_index)),
        },
        metadata={
            "valid_actions_digest": valid_actions_digest,
        },
    )
    proof_metadata = proposal_proof.metadata.to_dict()
    receipt = DecisionReceipt(
        moment_id=moment.contract_id,
        mode=ReceiptMode.READ_ONLY,
        decision_kind="interactive_action_proposal",
        rationale=(
            f"{proposal.strategy}; action is a proposal pending independent RunLease."
        ),
        selected_goal_id=goal.contract_id,
        input_claim_ids=(perception.claim.contract_id,),
        proof_candidate_ids=(proposal_proof.contract_id,),
        proposed_action={
            "action_id": selected.action_id,
            "payload_digest": canonical_digest(selected.payload),
        },
        metadata={
            "action_payload_signature": proof_metadata[
                "action_payload_signature"
            ],
            "goal_digest": proof_metadata["goal_digest"],
            "observation_digest": perception.observation_digest,
            "proposal_id": proposal.proposal_id,
            "selected_plan_digest": canonical_digest(
                proof_metadata.get("selected_plan")
            ),
            "snapshot_id": snapshot.contract_id,
            "transition_rule_hypotheses_digest": canonical_digest(
                proof_metadata["transition_rule_hypotheses"]
            ),
            "valid_actions_digest": valid_actions_digest,
        },
    )
    return snapshot, envelope, moment, proposal_proof, receipt


def _cycle_status(stop_reason: str, success: bool) -> CycleStatus:
    if success:
        return CycleStatus.COMPLETED
    if stop_reason in {"no_valid_actions", "policy_abstained"}:
        return CycleStatus.ABSTAINED
    if stop_reason.startswith(("step_budget", "run_lease", "operator_stop")):
        return CycleStatus.CANCELLED
    return CycleStatus.FAILED


def _build_cycle_receipt(
    *,
    goal: GoalIR,
    environment_seed: int,
    policy_seed: int,
    step_budget: int,
    retain_policy_updates: bool,
    reset_result: FrozenMap,
    steps: Sequence[InteractiveStep],
    denied_attempt: DeniedAttempt | None,
    stop_reason: str,
    success: bool,
    request_id: str | None,
    cycle_id: str | None,
    session_id: str,
    memory_before: FrozenMap,
) -> CycleReceipt:
    identity = {
        "environment_seed": environment_seed,
        "goal_id": goal.contract_id,
        "memory_before_digest": canonical_digest(memory_before),
        "policy_seed": policy_seed,
        "reset_digest": canonical_digest(reset_result),
        "retain_policy_updates": retain_policy_updates,
        "step_budget": step_budget,
    }
    actual_request_id = request_id or canonical_id("gwip_request", identity)[0]
    actual_cycle_id = cycle_id or canonical_id("gwip_cycle", identity)[0]
    first_observation_id = (
        f"environment-observation:{steps[0].perception.observation_digest}"
        if steps
        else f"environment-reset:{canonical_digest(reset_result)}"
    )
    request = RequestCycle(
        request_id=actual_request_id,
        cycle_id=actual_cycle_id,
        session_id=session_id,
        seed=policy_seed,
        input_observation_id=first_observation_id,
    )

    entities: list[CanonicalEntityRef] = []

    def entity(kind: EntityKind, payload: Mapping[str, Any]) -> CanonicalEntityRef:
        item = CanonicalEntityRef(
            kind=kind,
            cycle_id=actual_cycle_id,
            ordinal=len(entities),
            payload=payload,
        )
        entities.append(item)
        return item

    goal_entity = entity(EntityKind.GOAL, goal.to_dict())
    state: FrozenMap = FrozenMap({"status": "running", "step_count": 0})
    initial_state = state
    events: list[CycleEvent] = []

    def transition(
        phase: CyclePhase,
        refs: Sequence[CanonicalEntityRef],
        patch: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        nonlocal state
        event, state = CycleEvent.transition(
            cycle_id=actual_cycle_id,
            sequence=len(events),
            phase=phase,
            parent_event_id=events[-1].event_id if events else None,
            entity_occurrence_ids=tuple(item.occurrence_id for item in refs),
            state_before=state,
            state_patch=patch,
            metadata=metadata or {},
        )
        events.append(event)

    transition(
        CyclePhase.INGRESS,
        (goal_entity,),
        {
            "set": {
                "goal_id": goal.contract_id,
                "reset_digest": canonical_digest(reset_result),
                "retain_policy_updates": retain_policy_updates,
            },
            "delete": [],
        },
    )
    for step in steps:
        proposal_metadata = step.proposal_proof.metadata.to_dict()
        learning_metadata = step.learning_proof.metadata.to_dict()
        observation = entity(
            EntityKind.OBSERVATION,
            {
                "claim_id": step.perception.claim.contract_id,
                "observation_digest": step.perception.observation_digest,
                "snapshot_id": step.world_snapshot.contract_id,
                "valid_actions_digest": step.valid_actions_digest,
            },
        )
        plan = entity(
            EntityKind.PLAN,
            {
                **step.proposal.to_dict(),
                "goal_digest": proposal_metadata.get("goal_digest"),
                "proposal_proof_id": step.proposal_proof.contract_id,
                "selected_plan_digest": canonical_digest(
                    proposal_metadata.get("selected_plan")
                ),
                "transition_rule_hypotheses_digest": canonical_digest(
                    proposal_metadata.get("transition_rule_hypotheses", [])
                ),
            },
        )
        action = entity(
            EntityKind.ACTION,
            {
                "action_id": step.selected_action,
                "action_payload_signature": proposal_metadata.get(
                    "action_payload_signature"
                ),
                "decision_receipt_id": step.decision_receipt.contract_id,
                "proposal_id": step.proposal.proposal_id,
                "valid_actions_digest": step.valid_actions_digest,
            },
        )
        authorization = entity(
            EntityKind.EVALUATION,
            {
                "action_occurrence_id": action.occurrence_id,
                "authorization_witness_id": step.authorization.witness_id,
                "granted": step.authorization.granted,
            },
        )
        learning = entity(
            EntityKind.LEARNING_CANDIDATE,
            {
                "action_occurrence_id": action.occurrence_id,
                "edge_ref": step.learned_edge_ref,
                "from_observation_digest": step.perception.observation_digest,
                "learning_proof_id": step.learning_proof.contract_id,
                "to_observation_digest": opaque_digest(step.post_observation),
                "transition_rule_hypotheses_digest": canonical_digest(
                    learning_metadata.get("transition_rule_hypotheses", [])
                ),
            },
        )
        transition(
            CyclePhase.PERCEPTION,
            (observation,),
            {
                "set": {
                    "current_observation_digest": step.perception.observation_digest,
                    "current_snapshot_id": step.world_snapshot.contract_id,
                    "valid_actions_digest": step.valid_actions_digest,
                },
                "delete": [],
            },
        )
        transition(
            CyclePhase.SELECTION,
            (plan, action),
            {
                "set": {
                    "decision_receipt_id": step.decision_receipt.contract_id,
                    "proposed_action_occurrence_id": action.occurrence_id,
                    "proposal_id": step.proposal.proposal_id,
                },
                "delete": [],
            },
        )
        transition(
            CyclePhase.AUTHORIZATION_OBSERVATION,
            (authorization,),
            {
                "set": {
                    "authorization_witness_id": step.authorization.witness_id,
                },
                "delete": [],
            },
            metadata={
                "structural_receipt_authenticates_action": False,
            },
        )
        transition(
            CyclePhase.EFFECT_OBSERVATION,
            (action, learning),
            {
                "set": {
                    "last_action_occurrence_id": action.occurrence_id,
                    "post_observation_digest": opaque_digest(step.post_observation),
                    "step_count": step.step_index + 1,
                },
                "delete": [],
            },
        )
        transition(
            CyclePhase.LEARNING_PROPOSAL,
            (learning,),
            {
                "set": {
                    "latest_learning_edge_ref": step.learned_edge_ref,
                },
                "delete": [],
            },
            metadata={"promotion_mutated": False},
        )

    denied_refs: tuple[CanonicalEntityRef, ...] = ()
    if denied_attempt is not None:
        denied = entity(
            EntityKind.EVALUATION,
            {
                "action_id": denied_attempt.proposal.action_id,
                "executed": False,
                "reason": denied_attempt.reason,
                "valid_actions_digest": denied_attempt.valid_actions_digest,
            },
        )
        denied_refs = (denied,)
        transition(
            CyclePhase.EVALUATION,
            denied_refs,
            {
                "set": {
                    "denied_action_id": denied_attempt.proposal.action_id,
                    "denial_reason": denied_attempt.reason,
                },
                "delete": [],
            },
        )

    status = _cycle_status(stop_reason, success)
    terminal = entity(
        EntityKind.EPISODE,
        {
            "status": status.value,
            "step_count": len(steps),
            "stop_reason": stop_reason,
            "success": success,
        },
    )
    transition(
        CyclePhase.TERMINAL,
        (*denied_refs, terminal),
        {
            "set": {
                "status": status.value,
                "stop_reason": stop_reason,
                "success": success,
            },
            "delete": [],
        },
    )
    output = {
        "status": status.value,
        "step_count": len(steps),
        "stop_reason": stop_reason,
        "success": success,
    }
    return CycleReceipt(
        request_cycle=request,
        status=status,
        entities=tuple(entities),
        events=tuple(events),
        initial_state=initial_state,
        terminal_state_hash=events[-1].state_after_hash,
        input_hash=canonical_digest(identity),
        output_hash=canonical_digest(output),
        selected_route="generic_world_interaction",
        declared_effects=("environment_step_observed",) if steps else (),
        limitations=(
            "decision_receipts_are_non_authoritative",
            "mechanism_only",
            "structural_replay_does_not_reexecute_environment",
        ),
    )


class GenericWorldInteractionLoop:
    """Coordinate one bounded episode over an evaluator-owned environment."""

    def __init__(
        self,
        *,
        authority: StepAuthority,
        policy: AtanorInteractivePolicy | None = None,
        require_run_lease: bool = True,
    ) -> None:
        if require_run_lease and type(authority) is not RunLeaseStepAuthority:
            raise TypeError(
                "public interaction requires exact RunLeaseStepAuthority; "
                "require_run_lease=False is a focused-fixture seam only"
            )
        if not isinstance(authority, StepAuthority):
            raise TypeError("authority must implement authorize and finish")
        self.authority = authority
        self.policy = policy or AtanorInteractivePolicy()
        self.require_run_lease = require_run_lease
        self._operator_stop_requested = False

    def request_stop(self) -> None:
        """Installation/operator stop checked before any subsequent step."""

        self._operator_stop_requested = True

    def run(
        self,
        environment: InteractiveEnvironment,
        goal: GoalIR,
        *,
        environment_seed: int,
        policy_seed: int,
        step_budget: int = 20,
        retain_policy_updates: bool = True,
        request_id: str | None = None,
        cycle_id: str | None = None,
        session_id: str = "gwip:controlled",
    ) -> InteractiveTrace:
        if not isinstance(environment, InteractiveEnvironment):
            raise TypeError("environment does not implement the interaction protocol")
        if type(goal) is not GoalIR:
            raise TypeError("goal must be an exact canonical GoalIR")
        if type(environment_seed) is not int or type(policy_seed) is not int:
            raise TypeError("environment_seed and policy_seed must be integers")
        if type(step_budget) is not int or not 1 <= step_budget <= 10_000:
            raise ValueError("step_budget must be an integer from 1 to 10000")
        if type(retain_policy_updates) is not bool:
            raise TypeError("retain_policy_updates must be boolean")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be non-empty")

        memory_before = FrozenMap(self.policy.export_memory())
        reset_raw = environment.reset(environment_seed)
        reset_result = bounded_mapping(
            reset_raw or {},
            name="environment reset result",
        )
        stopped = False
        steps: list[InteractiveStep] = []
        denied_attempt: DeniedAttempt | None = None
        stop_reason = "environment_failure"
        stop_result = FrozenMap()
        authority_finish = FrozenMap()
        success = False
        parent_snapshot_id: str | None = None
        expected_observation: FrozenMap | None = None

        try:
            while True:
                observed = bounded_mapping(
                    environment.observe(),
                    name="environment observation",
                )
                if (
                    expected_observation is not None
                    and observed != expected_observation
                ):
                    stop_reason = "post_observation_mismatch"
                    break
                if self._operator_stop_requested:
                    stop_reason = "operator_stop_requested"
                    break

                valid_actions = normalize_valid_actions(environment.valid_actions())
                valid_digest = _valid_actions_digest(valid_actions)
                if not valid_actions:
                    stop_reason = "no_valid_actions"
                    break
                perception = perceive_observation(observed)
                step_policy = (
                    self.policy
                    if retain_policy_updates
                    else AtanorInteractivePolicy.from_memory(
                        memory_before.to_dict()
                    )
                )
                proposal = step_policy.select(
                    perception=perception,
                    valid_actions=valid_actions,
                    valid_actions_digest=valid_digest,
                    policy_seed=policy_seed,
                    goal=goal,
                )
                if proposal is None:
                    stop_reason = "policy_abstained"
                    break
                selected_matches = [
                    item for item in valid_actions if item.action_id == proposal.action_id
                ]
                if len(selected_matches) != 1:
                    stop_reason = "proposal_not_in_evaluator_valid_set"
                    break
                selected_action = selected_matches[0]

                snapshot, envelope, moment, proposal_proof, decision = (
                    _build_decision_records(
                        step_index=len(steps),
                        goal=goal,
                        perception=perception,
                        valid_actions=valid_actions,
                        valid_actions_digest=valid_digest,
                        parent_snapshot_id=parent_snapshot_id,
                        proposal=proposal,
                        step_budget=step_budget,
                        session_id=session_id,
                    )
                )
                if len(steps) >= step_budget:
                    stop_reason = "step_budget_exhausted"
                    denied_attempt = DeniedAttempt(
                        step_index=len(steps),
                        pre_observation=observed,
                        valid_actions=valid_actions,
                        valid_actions_digest=valid_digest,
                        proposal=proposal,
                        reason=stop_reason,
                    )
                    break

                authorization = self.authority.authorize(
                    proposal.action_id,
                    len(steps),
                )
                if type(authorization) is not AuthorizationWitness:
                    stop_reason = "run_lease_authorization_witness_invalid"
                    denied_attempt = DeniedAttempt(
                        step_index=len(steps),
                        pre_observation=observed,
                        valid_actions=valid_actions,
                        valid_actions_digest=valid_digest,
                        proposal=proposal,
                        reason=stop_reason,
                    )
                    break
                if (
                    authorization.action_id != proposal.action_id
                    or authorization.step_index != len(steps)
                ):
                    stop_reason = "run_lease_authorization_binding_mismatch"
                    denied_attempt = DeniedAttempt(
                        step_index=len(steps),
                        pre_observation=observed,
                        valid_actions=valid_actions,
                        valid_actions_digest=valid_digest,
                        proposal=proposal,
                        reason=stop_reason,
                        authorization=authorization,
                    )
                    break
                if authorization.granted is not True:
                    stop_reason = authorization.reason
                    denied_attempt = DeniedAttempt(
                        step_index=len(steps),
                        pre_observation=observed,
                        valid_actions=valid_actions,
                        valid_actions_digest=valid_digest,
                        proposal=proposal,
                        reason=stop_reason,
                        authorization=authorization,
                    )
                    break

                raw_result = environment.step(proposal.action_id)
                step_result = EnvironmentStepResult.from_mapping(raw_result)
                edge_ref, learning_proof = step_policy.learn(
                    perception=perception,
                    action_id=proposal.action_id,
                    action=selected_action,
                    post_observation=step_result.observation,
                    success=step_result.success,
                    goal=goal,
                )
                step = InteractiveStep(
                    step_index=len(steps),
                    pre_observation=observed,
                    perception=perception,
                    valid_actions=valid_actions,
                    valid_actions_digest=valid_digest,
                    world_snapshot=snapshot,
                    cognitive_envelope=envelope,
                    cognitive_moment=moment,
                    proposal=proposal,
                    proposal_proof=proposal_proof,
                    decision_receipt=decision,
                    authorization=authorization,
                    step_result=step_result,
                    learned_edge_ref=edge_ref,
                    learning_proof=learning_proof,
                )
                steps.append(step)
                parent_snapshot_id = snapshot.contract_id
                expected_observation = step_result.observation
                success = step_result.success
                if step_result.terminal or step_result.success:
                    stop_reason = (
                        step_result.stop_reason
                        or ("goal_reached" if step_result.success else "environment_terminal")
                    )
                    break
        except Exception as exc:
            stop_reason = f"environment_failure:{type(exc).__name__}"
        finally:
            if not stopped:
                try:
                    stop_raw = environment.stop(stop_reason)
                    stop_result = bounded_mapping(
                        stop_raw or {},
                        name="environment stop result",
                    )
                except Exception as exc:
                    stop_result = FrozenMap(
                        {"error": f"{type(exc).__name__}:{str(exc)[:160]}"}
                    )
                    stop_reason = "environment_stop_failed"
                    success = False
                stopped = True
            try:
                finish_raw = self.authority.finish(stop_reason)
                authority_finish = bounded_mapping(
                    finish_raw or {},
                    name="authority finish result",
                )
            except Exception as exc:
                authority_finish = FrozenMap(
                    {"error": f"{type(exc).__name__}:{str(exc)[:160]}"}
                )

        memory_after = FrozenMap(self.policy.export_memory())
        cycle_receipt = _build_cycle_receipt(
            goal=goal,
            environment_seed=environment_seed,
            policy_seed=policy_seed,
            step_budget=step_budget,
            retain_policy_updates=retain_policy_updates,
            reset_result=reset_result,
            steps=steps,
            denied_attempt=denied_attempt,
            stop_reason=stop_reason,
            success=success,
            request_id=request_id,
            cycle_id=cycle_id,
            session_id=session_id,
            memory_before=memory_before,
        )
        replay_cycle(cycle_receipt)
        provisional = InteractiveTrace(
            goal=goal,
            environment_seed=environment_seed,
            policy_seed=policy_seed,
            step_budget=step_budget,
            retain_policy_updates=retain_policy_updates,
            reset_result=reset_result,
            steps=tuple(steps),
            denied_attempt=denied_attempt,
            stop_reason=stop_reason,
            stop_result=stop_result,
            authority_finish=authority_finish,
            success=success,
            memory_before=memory_before,
            memory_after=memory_after,
            cycle_receipt=cycle_receipt,
            semantic_trace_digest="0" * 64,
        )
        return InteractiveTrace(
            goal=provisional.goal,
            environment_seed=provisional.environment_seed,
            policy_seed=provisional.policy_seed,
            step_budget=provisional.step_budget,
            retain_policy_updates=provisional.retain_policy_updates,
            reset_result=provisional.reset_result,
            steps=provisional.steps,
            denied_attempt=provisional.denied_attempt,
            stop_reason=provisional.stop_reason,
            stop_result=provisional.stop_result,
            authority_finish=provisional.authority_finish,
            success=provisional.success,
            memory_before=provisional.memory_before,
            memory_after=provisional.memory_after,
            cycle_receipt=provisional.cycle_receipt,
            semantic_trace_digest=canonical_digest(
                provisional.semantic_projection()
            ),
        )


def verify_interactive_trace(
    trace: InteractiveTrace,
    *,
    fixture_authority_verifier: Callable[[AuthorizationWitness], bool] | None = None,
    expected_goal: GoalIR | None = None,
    expected_memory_before: Mapping[str, Any] | None = None,
) -> TraceVerification:
    """Reconstruct loop-owned records; never treat their hashes as authority.

    ``fixture_authority_verifier`` exists only for focused unit fixtures.  Even a
    callback that returns true cannot set ``authority_independently_verified``;
    production evidence must use :func:`verify_run_lease_trace`.
    """

    errors: list[str] = []
    structural_replay_ok = True
    try:
        replay_cycle(trace.cycle_receipt)
    except (TypeError, ValueError) as exc:
        structural_replay_ok = False
        errors.append(f"structural_replay:{exc}")
    if canonical_digest(trace.semantic_projection()) != trace.semantic_trace_digest:
        errors.append("semantic_trace_digest_mismatch")
    if type(trace.retain_policy_updates) is not bool:
        errors.append("retain_policy_updates_type_mismatch")
    if (
        trace.retain_policy_updates is False
        and trace.memory_after != trace.memory_before
    ):
        errors.append("nonretaining_policy_memory_changed")
    if expected_goal is not None and trace.goal.to_dict() != expected_goal.to_dict():
        errors.append("goal_binding_mismatch")
    if expected_memory_before is not None:
        try:
            trusted_memory = FrozenMap(expected_memory_before)
            if trace.memory_before != trusted_memory:
                errors.append("memory_before_binding_mismatch")
        except (TypeError, ValueError) as exc:
            errors.append(f"memory_before_binding_error:{exc}")

    replay_policy: AtanorInteractivePolicy | None
    try:
        replay_policy = AtanorInteractivePolicy.from_memory(
            trace.memory_before.to_dict()
        )
    except (KeyError, TypeError, ValueError) as exc:
        replay_policy = None
        errors.append(f"policy_memory_replay_init:{exc}")

    parent_snapshot_id: str | None = None
    for expected_index, step in enumerate(trace.steps):
        if step.step_index != expected_index:
            errors.append(f"step_{expected_index}:index_mismatch")
        try:
            perception = perceive_observation(step.pre_observation)
            if perception.to_dict() != step.perception.to_dict():
                errors.append(f"step_{expected_index}:perception_mismatch")
            if _valid_actions_digest(step.valid_actions) != step.valid_actions_digest:
                errors.append(f"step_{expected_index}:valid_actions_digest_mismatch")
            selected_options = [
                item
                for item in step.valid_actions
                if item.action_id == step.selected_action
            ]
            if len(selected_options) != 1:
                errors.append(f"step_{expected_index}:selected_action_not_unique")
                raise ValueError("selected action is not unique in actual valid set")
            selected_action = selected_options[0]

            expected_proposal: ActionProposal | None = None
            memory_before_select: dict[str, Any] | None = None
            memory_before_learn: dict[str, Any] | None = None
            if replay_policy is not None:
                step_replay_policy = (
                    replay_policy
                    if trace.retain_policy_updates
                    else AtanorInteractivePolicy.from_memory(
                        trace.memory_before.to_dict()
                    )
                )
                memory_before_select = step_replay_policy.export_memory()
                expected_proposal = step_replay_policy.select(
                    perception=perception,
                    valid_actions=step.valid_actions,
                    valid_actions_digest=step.valid_actions_digest,
                    policy_seed=trace.policy_seed,
                    goal=trace.goal,
                )
                memory_before_learn = step_replay_policy.export_memory()
                if (
                    expected_proposal is None
                    or expected_proposal.to_dict() != step.proposal.to_dict()
                ):
                    errors.append(
                        f"step_{expected_index}:policy_proposal_replay_mismatch"
                    )

            if step.proposal.strategy == "typed_rule_goal_plan":
                plan_check = verify_rule_plan_proof(
                    proof=step.proposal.deliberator_proof,
                    goal=trace.goal,
                    observation=step.pre_observation,
                    action=selected_action,
                    memory=(
                        memory_before_learn
                        if memory_before_learn is not None
                        else trace.memory_before.to_dict()
                    ),
                )
                if plan_check.get("passed") is not True:
                    findings = plan_check.get("findings", [])
                    errors.append(
                        f"step_{expected_index}:rule_plan_proof_mismatch:"
                        + ",".join(str(item) for item in findings[:4])
                    )

            proposal_for_records = expected_proposal or step.proposal
            rebuilt = _build_decision_records(
                step_index=step.step_index,
                goal=trace.goal,
                perception=perception,
                valid_actions=step.valid_actions,
                valid_actions_digest=step.valid_actions_digest,
                parent_snapshot_id=parent_snapshot_id,
                proposal=proposal_for_records,
                step_budget=trace.step_budget,
                session_id=step.cognitive_envelope.session_id,
            )
            if rebuilt[0].to_dict() != step.world_snapshot.to_dict():
                errors.append(f"step_{expected_index}:world_snapshot_mismatch")
            if rebuilt[1].to_dict() != step.cognitive_envelope.to_dict():
                errors.append(f"step_{expected_index}:cognitive_envelope_mismatch")
            if rebuilt[2].to_dict() != step.cognitive_moment.to_dict():
                errors.append(f"step_{expected_index}:cognitive_moment_mismatch")
            if rebuilt[3].to_dict() != step.proposal_proof.to_dict():
                errors.append(f"step_{expected_index}:proposal_proof_mismatch")
            if rebuilt[4].to_dict() != step.decision_receipt.to_dict():
                errors.append(f"step_{expected_index}:decision_receipt_mismatch")
            if (
                step.authorization.action_id != step.selected_action
                or step.authorization.step_index != step.step_index
                or step.authorization.granted is not True
            ):
                errors.append(f"step_{expected_index}:authorization_binding_mismatch")
            expected_edge = canonical_id(
                "transition_edge",
                {
                    "action_id": step.selected_action,
                    "from": step.perception.observation_digest,
                    "to": opaque_digest(step.post_observation),
                },
            )[0]
            if expected_edge != step.learned_edge_ref:
                errors.append(f"step_{expected_index}:learning_edge_mismatch")
            if step.step_result.observation != step.post_observation:
                errors.append(f"step_{expected_index}:post_observation_mismatch")

            if replay_policy is not None:
                expected_edge, expected_learning_proof = step_replay_policy.learn(
                    perception=perception,
                    action_id=selected_action.action_id,
                    action=selected_action,
                    post_observation=step.post_observation,
                    success=step.step_result.success,
                    goal=trace.goal,
                )
                memory_after_learn = step_replay_policy.export_memory()
                if expected_edge != step.learned_edge_ref:
                    errors.append(
                        f"step_{expected_index}:policy_learning_edge_replay_mismatch"
                    )
                if (
                    expected_learning_proof.to_dict()
                    != step.learning_proof.to_dict()
                ):
                    errors.append(
                        f"step_{expected_index}:learning_proof_replay_mismatch"
                    )
                learning_check = verify_learning_proof(
                    proof=step.learning_proof,
                    before_observation=step.pre_observation,
                    action=selected_action,
                    after_observation=step.post_observation,
                    edge_ref=step.learned_edge_ref,
                    memory_before=(
                        memory_before_learn
                        if memory_before_learn is not None
                        else memory_before_select or {}
                    ),
                    memory_after=memory_after_learn,
                    goal=trace.goal,
                )
                if learning_check.get("passed") is not True:
                    findings = learning_check.get("findings", [])
                    errors.append(
                        f"step_{expected_index}:learning_proof_lineage_mismatch:"
                        + ",".join(str(item) for item in findings[:4])
                    )
            if fixture_authority_verifier is not None and not fixture_authority_verifier(
                step.authorization
            ):
                errors.append(f"step_{expected_index}:fixture_authority_witness_rejected")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"step_{expected_index}:cross_check_error:{exc}")
        parent_snapshot_id = step.world_snapshot.contract_id

    if replay_policy is not None and trace.denied_attempt is not None:
        denied = trace.denied_attempt
        try:
            denied_perception = perceive_observation(denied.pre_observation)
            denied_replay_policy = (
                replay_policy
                if trace.retain_policy_updates
                else AtanorInteractivePolicy.from_memory(
                    trace.memory_before.to_dict()
                )
            )
            expected_denied = denied_replay_policy.select(
                perception=denied_perception,
                valid_actions=denied.valid_actions,
                valid_actions_digest=denied.valid_actions_digest,
                policy_seed=trace.policy_seed,
                goal=trace.goal,
            )
            if (
                expected_denied is None
                or expected_denied.to_dict() != denied.proposal.to_dict()
            ):
                errors.append("denied_attempt:policy_proposal_replay_mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"denied_attempt:policy_replay_error:{exc}")

    if replay_policy is not None:
        try:
            replayed_memory_after = FrozenMap(replay_policy.export_memory())
            if replayed_memory_after != trace.memory_after:
                errors.append("policy_memory_after_replay_mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"policy_memory_after_replay_error:{exc}")

    try:
        request = trace.cycle_receipt.request_cycle
        rebuilt_cycle = _build_cycle_receipt(
            goal=trace.goal,
            environment_seed=trace.environment_seed,
            policy_seed=trace.policy_seed,
            step_budget=trace.step_budget,
            retain_policy_updates=trace.retain_policy_updates,
            reset_result=trace.reset_result,
            steps=trace.steps,
            denied_attempt=trace.denied_attempt,
            stop_reason=trace.stop_reason,
            success=trace.success,
            request_id=request.request_id,
            cycle_id=request.cycle_id,
            session_id=request.session_id,
            memory_before=trace.memory_before,
        )
        if rebuilt_cycle.to_dict() != trace.cycle_receipt.to_dict():
            errors.append("cycle_receipt_binding_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"cycle_receipt_binding_error:{exc}")

    return TraceVerification(
        errors=tuple(errors),
        structural_replay_ok=structural_replay_ok,
        receipt_cross_check_ok=not any(
            "structural_replay" not in item and "fixture_authority_witness" not in item
            for item in errors
        ),
        environment_reexecution_ok=False,
        authority_independently_verified=False,
        fixture_authority_check_ok=(
            fixture_authority_verifier is not None
            and not any("fixture_authority_witness" in item for item in errors)
        ),
    )


def reexecute_interactive_trace(
    environment_factory: Callable[[], InteractiveEnvironment],
    trace: InteractiveTrace,
    *,
    fixture_authority_verifier: Callable[[AuthorizationWitness], bool] | None = None,
    expected_goal: GoalIR | None = None,
    expected_memory_before: Mapping[str, Any] | None = None,
) -> TraceVerification:
    """Fresh-environment verification of every external witness and call order."""

    base = verify_interactive_trace(
        trace,
        fixture_authority_verifier=fixture_authority_verifier,
        expected_goal=expected_goal,
        expected_memory_before=expected_memory_before,
    )
    errors = list(base.errors)
    try:
        environment = environment_factory()
        reset = bounded_mapping(
            environment.reset(trace.environment_seed) or {},
            name="reexecution reset result",
        )
        if reset != trace.reset_result:
            errors.append("reexecution:reset_mismatch")
        for step in trace.steps:
            observed = bounded_mapping(
                environment.observe(),
                name="reexecution observation",
            )
            if observed != step.pre_observation:
                errors.append(f"reexecution:step_{step.step_index}:observation_mismatch")
            actions = normalize_valid_actions(environment.valid_actions())
            if actions != step.valid_actions:
                errors.append(f"reexecution:step_{step.step_index}:valid_actions_mismatch")
            result = EnvironmentStepResult.from_mapping(
                environment.step(step.selected_action)
            )
            if result.to_dict() != step.step_result.to_dict():
                errors.append(f"reexecution:step_{step.step_index}:result_mismatch")
        if trace.denied_attempt is not None:
            denied_observation = bounded_mapping(
                environment.observe(),
                name="reexecution denied observation",
            )
            if denied_observation != trace.denied_attempt.pre_observation:
                errors.append("reexecution:denied_observation_mismatch")
            denied_actions = normalize_valid_actions(environment.valid_actions())
            if denied_actions != trace.denied_attempt.valid_actions:
                errors.append("reexecution:denied_valid_actions_mismatch")
        stop_result = bounded_mapping(
            environment.stop(trace.stop_reason) or {},
            name="reexecution stop result",
        )
        if stop_result != trace.stop_result:
            errors.append("reexecution:stop_result_mismatch")
    except Exception as exc:
        errors.append(f"reexecution:error:{type(exc).__name__}:{exc}")

    return TraceVerification(
        errors=tuple(errors),
        structural_replay_ok=base.structural_replay_ok,
        receipt_cross_check_ok=base.receipt_cross_check_ok,
        environment_reexecution_ok=not any(
            item.startswith("reexecution:") for item in errors
        ),
        authority_independently_verified=base.authority_independently_verified,
        fixture_authority_check_ok=base.fixture_authority_check_ok,
    )


def verify_run_lease_trace(
    trace: InteractiveTrace,
    *,
    store: RunLeaseStore,
    lease_id: str,
    environment_factory: Callable[[], InteractiveEnvironment] | None = None,
    expected_goal: GoalIR | None = None,
    expected_memory_before: Mapping[str, Any] | None = None,
) -> TraceVerification:
    """Cross-check trace witnesses against the exact durable RunLease state.

    This verifier is intentionally separate from the coordinator and from the
    receipt constructors.  It reads the finished durable runner state, checks
    the exact lease binding and final counters, and requires every executed
    step to carry the corresponding sequential counter witness.
    """

    if type(store) is not RunLeaseStore:
        raise TypeError("verify_run_lease_trace requires an exact RunLeaseStore")
    if not isinstance(lease_id, str) or not lease_id:
        raise ValueError("verify_run_lease_trace requires lease_id")
    base = (
        reexecute_interactive_trace(
            environment_factory,
            trace,
            expected_goal=expected_goal,
            expected_memory_before=expected_memory_before,
        )
        if environment_factory is not None
        else verify_interactive_trace(
            trace,
            expected_goal=expected_goal,
            expected_memory_before=expected_memory_before,
        )
    )
    errors = list(base.errors)
    expected_counters = {
        **_FIXED_STEP_COSTS,
        "cycles": len(trace.steps),
        "actions": len(trace.steps),
    }
    try:
        status = store.status()
        runner = status.get("runners", {}).get(GENERAL_INTERACTION_RUNNER_ID)
        if status.get("state_ok") is not True:
            errors.append("run_lease:store_state_invalid")
        if not isinstance(runner, Mapping):
            errors.append("run_lease:runner_state_missing")
        else:
            if runner.get("state_ok") is not True:
                errors.append("run_lease:runner_state_invalid")
            if runner.get("status") != "finished":
                errors.append("run_lease:runner_not_finished")
            if runner.get("lease_id") != lease_id:
                errors.append("run_lease:lease_binding_mismatch")
            if runner.get("finish_reason") != trace.stop_reason:
                errors.append("run_lease:finish_reason_mismatch")
            if runner.get("authorization_count") != len(trace.steps):
                errors.append("run_lease:authorization_count_mismatch")
            if runner.get("counters") != expected_counters:
                errors.append("run_lease:final_counters_mismatch")
        if trace.authority_finish.to_dict() != {
            "finished": True,
            "lease_id": lease_id,
            "reason": "run_lease_finished",
            "runner_id": GENERAL_INTERACTION_RUNNER_ID,
        }:
            errors.append("run_lease:finish_receipt_mismatch")
        expected_lease_digest = canonical_digest(lease_id)
        for index, step in enumerate(trace.steps):
            evidence = step.authorization.operational_evidence.to_dict()
            expected_step_counters = {
                **_FIXED_STEP_COSTS,
                "cycles": index + 1,
                "actions": index + 1,
            }
            if (
                step.authorization.authority_kind
                != "externally_signed_run_lease"
                or step.authorization.step_index != index
                or step.authorization.granted is not True
                or evidence.get("action_class")
                != GENERAL_INTERACTION_ACTION_CLASS
                or evidence.get("runner_id")
                != GENERAL_INTERACTION_RUNNER_ID
                or evidence.get("lease_id_sha256")
                != expected_lease_digest
                or evidence.get("counters") != expected_step_counters
            ):
                errors.append(f"run_lease:step_{index}:sequential_witness_mismatch")
    except Exception as exc:
        errors.append(f"run_lease:verification_error:{type(exc).__name__}:{exc}")

    authority_ok = not any(item.startswith("run_lease:") for item in errors)
    return TraceVerification(
        errors=tuple(errors),
        structural_replay_ok=base.structural_replay_ok,
        receipt_cross_check_ok=base.receipt_cross_check_ok,
        environment_reexecution_ok=base.environment_reexecution_ok,
        authority_independently_verified=authority_ok,
        fixture_authority_check_ok=False,
    )


__all__ = [
    "GENERAL_INTERACTION_ACTION_CLASS",
    "GENERAL_INTERACTION_RUNNER_ID",
    "INTERACTIVE_TRACE_SCHEMA_VERSION",
    "AuthorizationWitness",
    "DeniedAttempt",
    "EnvironmentStepResult",
    "GenericWorldInteractionLoop",
    "InteractiveEnvironment",
    "InteractiveStep",
    "InteractiveTrace",
    "RunLeaseStepAuthority",
    "StepAuthority",
    "TraceVerification",
    "reexecute_interactive_trace",
    "verify_interactive_trace",
    "verify_run_lease_trace",
]
