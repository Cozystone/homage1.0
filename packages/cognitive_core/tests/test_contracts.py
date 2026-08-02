from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
import json

import pytest

from packages.cognitive_core import (
    SCHEMA_VERSION,
    ClaimEnvelope,
    CognitiveEnvelope,
    CognitiveMoment,
    DecisionReceipt,
    EpistemicTier,
    GoalIR,
    GoalOrigin,
    ProofCandidate,
    ReceiptMode,
    WorldSnapshot,
    order_goals_for_deliberation,
)


def _contracts():
    user_goal = GoalIR(
        statement="Answer the user's question.",
        origin=GoalOrigin.EXPLICIT_USER,
        priority=80,
    )
    intrinsic_goal = GoalIR(
        statement="Reduce unresolved uncertainty.",
        origin=GoalOrigin.INTRINSIC,
        priority=20,
    )
    observed = ClaimEnvelope(
        statement="The sensor reported a red object.",
        tier=EpistemicTier.OBSERVED,
        confidence=0.91,
        source_refs=("sensor:frame:7",),
    )
    predicted = ClaimEnvelope(
        statement="The object may move right.",
        tier=EpistemicTier.PREDICTED,
        confidence=0.63,
        source_claim_ids=(observed.contract_id,),
    )
    proof = ProofCandidate(
        claim_id=predicted.contract_id,
        method="forward_model_rollout",
        premise_claim_ids=(observed.contract_id,),
        derivation_steps=("Encode the observation.", "Roll the model forward."),
    )
    world = WorldSnapshot(
        world_time="logical:42",
        snapshot_index=42,
        observed_claim_ids=(observed.contract_id,),
        predicted_claim_ids=(predicted.contract_id,),
    )
    envelope = CognitiveEnvelope(
        session_id="session:test",
        explicit_user_goal_ids=(user_goal.contract_id,),
        intrinsic_goal_ids=(intrinsic_goal.contract_id,),
        world_snapshot_id=world.contract_id,
        hormone_signals={"cortisol": 0.2},
        resource_limits={"token_budget": 512},
    )
    moment = CognitiveMoment(
        moment_index=42,
        envelope_id=envelope.contract_id,
        world_snapshot_id=world.contract_id,
        active_goal_ids=(user_goal.contract_id, intrinsic_goal.contract_id),
        selected_goal_id=user_goal.contract_id,
        claim_ids=(observed.contract_id, predicted.contract_id),
        proof_candidate_ids=(proof.contract_id,),
        hormone_signals={"cortisol": 0.2},
        resource_state={"tokens_remaining": 480},
    )
    receipt = DecisionReceipt(
        moment_id=moment.contract_id,
        mode=ReceiptMode.SHADOW,
        decision_kind="answer_candidate",
        rationale="The explicit user goal remains first.",
        selected_goal_id=user_goal.contract_id,
        input_claim_ids=(observed.contract_id, predicted.contract_id),
        proof_candidate_ids=(proof.contract_id,),
    )
    return (
        envelope,
        user_goal,
        observed,
        proof,
        world,
        moment,
        receipt,
    )


def test_seven_contracts_are_frozen_versioned_and_canonically_identified():
    contracts = _contracts()
    assert len(contracts) == 7
    for contract in contracts:
        assert is_dataclass(contract)
        assert contract.schema_version == SCHEMA_VERSION
        assert contract.verify_identity()
        assert contract.contract_id
        assert len(contract.content_hash) == 64
        assert list(contract.to_dict()) == sorted(contract.to_dict())
        json.dumps(contract.to_dict(), ensure_ascii=False, sort_keys=True)
        with pytest.raises(FrozenInstanceError):
            contract.contract_id = "tampered"


def test_equivalent_contracts_have_stable_ids_and_detached_serialization():
    first = GoalIR(
        statement="  Preserve   the explicit request. ",
        origin="explicit_user",
        priority=70,
        metadata={"nested": {"b": 2, "a": 1}},
    )
    second = GoalIR(
        statement="Preserve the explicit request.",
        origin=GoalOrigin.EXPLICIT_USER,
        priority=70,
        metadata={"nested": {"a": 1, "b": 2}},
    )
    assert first.contract_id == second.contract_id
    assert first.content_hash == second.content_hash
    assert first.to_dict() == second.to_dict()

    detached = first.to_dict()
    detached["metadata"]["nested"]["a"] = 999
    assert first.to_dict()["metadata"]["nested"]["a"] == 1
    with pytest.raises(TypeError):
        first.metadata["new"] = "mutation"


def test_cognitive_envelope_is_context_not_autonomy_authority():
    envelope = _contracts()[0]
    assert envelope.cognition_only is True
    assert envelope.read_only is True
    assert envelope.autonomy_authority is False
    assert envelope.truth_mutation_allowed is False
    assert envelope.safety_mutation_allowed is False
    assert envelope.permission_mutation_allowed is False
    assert not hasattr(envelope, "check")
    assert not hasattr(envelope, "allowed")


def test_intrinsic_goal_never_overrides_explicit_user_goal():
    explicit = GoalIR(
        statement="Do the task the user requested.",
        origin=GoalOrigin.EXPLICIT_USER,
        priority=0,
    )
    intrinsic = GoalIR(
        statement="Explore a novel hypothesis.",
        origin=GoalOrigin.INTRINSIC,
        priority=100,
    )
    assert intrinsic.can_override(explicit) is False
    assert explicit.can_override(intrinsic) is True
    assert order_goals_for_deliberation((intrinsic, explicit)) == (explicit, intrinsic)

    envelope = CognitiveEnvelope(
        session_id="session:priority",
        explicit_user_goal_ids=(explicit.contract_id,),
        intrinsic_goal_ids=(intrinsic.contract_id,),
    )
    assert envelope.deliberation_goal_ids == (
        explicit.contract_id,
        intrinsic.contract_id,
    )
    assert envelope.intrinsic_override_allowed is False


def test_epistemic_tier_is_not_confidence():
    certain_prediction = ClaimEnvelope(
        statement="A simulated branch reaches state B.",
        tier=EpistemicTier.PREDICTED,
        confidence=1.0,
    )
    weak_observation = ClaimEnvelope(
        statement="A noisy sensor emitted sample B.",
        tier=EpistemicTier.OBSERVED,
        confidence=0.01,
        source_refs=("sensor:sample:B",),
    )
    assert certain_prediction.hypothesis is True
    assert certain_prediction.accepted_as_observed_fact is False
    assert weak_observation.hypothesis is False
    assert weak_observation.accepted_as_observed_fact is True
    assert certain_prediction.tier is EpistemicTier.PREDICTED
    assert weak_observation.tier is EpistemicTier.OBSERVED


@pytest.mark.parametrize("value", (True, False))
def test_truthy_boolean_cannot_masquerade_as_confidence(value):
    with pytest.raises(TypeError, match="numeric, not boolean"):
        ClaimEnvelope(
            statement="A boolean is not confidence telemetry.",
            tier=EpistemicTier.PREDICTED,
            confidence=value,
        )


@pytest.mark.parametrize(
    "source_tier",
    (EpistemicTier.PREDICTED, EpistemicTier.RETRODICTED),
)
def test_predictive_lineage_cannot_be_relabelled_as_observed(source_tier):
    with pytest.raises(ValueError, match="cannot be relabeled"):
        ClaimEnvelope(
            statement="This is not an independent observation.",
            tier=EpistemicTier.OBSERVED,
            source_refs=("source:claimed-observation",),
            lineage_tiers=(source_tier,),
        )


def test_world_snapshot_keeps_epistemic_categories_disjoint():
    predicted = ClaimEnvelope(
        statement="The model predicts a transition.",
        tier=EpistemicTier.PREDICTED,
    )
    with pytest.raises(ValueError, match="cross epistemic categories"):
        WorldSnapshot(
            world_time="logical:9",
            snapshot_index=9,
            observed_claim_ids=(predicted.contract_id,),
            predicted_claim_ids=(predicted.contract_id,),
        )


def test_predicted_claim_id_cannot_enter_observed_world_category():
    predicted = ClaimEnvelope(
        statement="The rollout reaches a possible future.",
        tier=EpistemicTier.PREDICTED,
        confidence=1.0,
    )
    assert predicted.contract_id.startswith("claim_predicted_")
    with pytest.raises(ValueError, match="canonical observed"):
        WorldSnapshot(
            world_time="logical:10",
            snapshot_index=10,
            observed_claim_ids=(predicted.contract_id,),
        )


def test_proof_candidate_is_never_accepted_proof():
    proof = ProofCandidate(
        claim_id="claim:target",
        method="bounded_symbolic_search",
        derivation_steps=("Derive a candidate.",),
        confidence=1.0,
    )
    assert proof.accepted_as_proof is False
    assert proof.truth_mutation_allowed is False
    assert "accepted_as_proof" in proof.to_dict()
    assert proof.to_dict()["accepted_as_proof"] is False


@pytest.mark.parametrize(
    ("field_name", "signals"),
    (
        ("hormone_signals", {"truth_threshold": 1.0}),
        ("hormone_signals", {"safety_override": 1.0}),
        ("resource_limits", {"permission_budget": 1.0}),
        ("resource_limits", {"authority_tokens": 1.0}),
    ),
)
def test_hormone_and_resource_channels_cannot_carry_policy_controls(
    field_name,
    signals,
):
    kwargs = {
        "session_id": "session:controls",
        "explicit_user_goal_ids": (),
        field_name: signals,
    }
    with pytest.raises(ValueError, match="cannot carry truth, safety, permission"):
        CognitiveEnvelope(**kwargs)


def test_cognitive_moment_metabolism_has_no_policy_or_action_authority():
    with pytest.raises(ValueError, match="cannot carry truth, safety, permission"):
        CognitiveMoment(
            moment_index=1,
            envelope_id="cenv:1",
            world_snapshot_id="world:1",
            hormone_signals={"permission_level": 0.9},
        )

    moment = CognitiveMoment(
        moment_index=1,
        envelope_id="cenv:1",
        world_snapshot_id="world:1",
        hormone_signals={"dopamine": 0.8},
        resource_state={"tokens_remaining": 100},
    )
    assert moment.truth_mutation_allowed is False
    assert moment.safety_mutation_allowed is False
    assert moment.permission_mutation_allowed is False
    assert moment.action_authority is False


def test_numeric_strings_cannot_enter_metabolic_control_channels():
    with pytest.raises(TypeError, match="literal numeric"):
        CognitiveEnvelope(
            session_id="session:malformed-telemetry",
            explicit_user_goal_ids=(),
            hormone_signals={"dopamine": "0.9"},
        )


@pytest.mark.parametrize("mode", (ReceiptMode.SHADOW, ReceiptMode.READ_ONLY))
def test_decision_receipts_are_shadow_or_read_only_never_authoritative(mode):
    receipt = DecisionReceipt(
        moment_id="moment:test",
        mode=mode,
        decision_kind="candidate",
        rationale="This is an observation-only receipt.",
    )
    assert receipt.read_only is True
    assert receipt.authoritative is False
    assert receipt.action_executed is False
    assert receipt.shadow is (mode is ReceiptMode.SHADOW)

    with pytest.raises(ValueError):
        DecisionReceipt(
            moment_id="moment:test",
            mode="live",
            decision_kind="candidate",
            rationale="Live mode is not an M1 receipt mode.",
        )
