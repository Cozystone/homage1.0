from __future__ import annotations

import copy

import pytest

from packages.cognitive_core import EpistemicTier
from packages.cognitive_core.canonical import canonical_digest
from packages.world4d import (
    CheckScope,
    CheckVerdict,
    Direction,
    ProviderResultStatus,
    World4DCheck,
    World4DProviderResult,
    World4DRequest,
    World4DShadowReceipt,
    World4DStep,
    World4DTrajectory,
)


def _request() -> World4DRequest:
    return World4DRequest(
        request_id="request_fixture",
        source_kind="temporal_text_query",
        source_digest=canonical_digest("secret source"),
        direction=Direction.FORWARD,
        horizon=2,
        branch_limit=2,
        source_refs=("fixture",),
    )


def _trajectory() -> World4DTrajectory:
    return World4DTrajectory(
        branch_id="branch_fixture",
        initial_state_digest=canonical_digest({"state": "initial"}),
        steps=(
            World4DStep(
                step_index=1,
                state_digest=canonical_digest({"state": "future"}),
                confidence=0.7,
                tier=EpistemicTier.PREDICTED,
            ),
        ),
        checks=(
            World4DCheck(
                check_id="physics",
                scope=CheckScope.PHYSICAL,
                verdict=CheckVerdict.NOT_RUN,
            ),
        ),
    )


def _result() -> World4DProviderResult:
    return World4DProviderResult(
        provider_id="fixture_provider",
        provider_version="v1",
        status=ProviderResultStatus.PROPOSED,
        trajectories=(_trajectory(),),
        limitations=("fixture_only",),
    )


def _receipt() -> World4DShadowReceipt:
    result = _result()
    return World4DShadowReceipt(
        request_digest=canonical_digest(_request().to_dict()),
        provider_descriptor_digest=canonical_digest({"provider": "fixture"}),
        provider_result_digest=canonical_digest(result.to_dict()),
        provider_status=result.status.value,
        trajectory_count=1,
        step_count=1,
        check_summary={
            "not_run": 1,
            "not_contradicted": 0,
            "contradicted": 0,
        },
        created_at_utc="2026-07-25T00:00:00.000000Z",
        limitations=("no_e4_or_e5_claim",),
    )


def test_request_and_receipt_have_fixed_non_authority_flags():
    request = World4DRequest.from_dict(_request().to_dict())
    assert request.read_only is True
    assert request.truth_mutation_allowed is False
    assert request.action_authority is False

    receipt = World4DShadowReceipt.from_dict(_receipt().to_dict())
    assert receipt.observer_only is True
    assert receipt.adapter_answer_influenced is False
    assert receipt.adapter_output_applied is False
    assert receipt.provider_effects_attested is False
    assert receipt.provider_isolation_enforced is False
    assert receipt.capability_claims == ()
    assert receipt.e4_claimed is False
    assert receipt.e5_claimed is False


def test_only_predictive_tiers_and_finite_confidence_are_accepted():
    with pytest.raises(ValueError, match="predicted or retrodicted"):
        World4DStep(
            step_index=1,
            state_digest="a" * 64,
            confidence=0.5,
            tier=EpistemicTier.OBSERVED,
        )
    for value in (float("nan"), float("inf"), -0.1, 1.1):
        with pytest.raises(ValueError):
            World4DStep(
                step_index=1,
                state_digest="a" * 64,
                confidence=value,
                tier=EpistemicTier.PREDICTED,
            )


def test_bounds_and_digest_validation_fail_closed():
    with pytest.raises(ValueError):
        World4DRequest(
            request_id="bad_horizon",
            source_kind="text",
            source_digest="a" * 64,
            direction=Direction.FORWARD,
            horizon=4,
        )
    with pytest.raises(ValueError):
        World4DRequest(
            request_id="bad_branch",
            source_kind="text",
            source_digest="not-a-digest",
            direction=Direction.FORWARD,
            branch_limit=5,
        )
    with pytest.raises(ValueError, match="512 UTF-8 bytes"):
        World4DRequest(
            request_id="x" * 513,
            source_kind="text",
            source_digest="a" * 64,
            direction=Direction.FORWARD,
        )


def test_contradiction_requires_quarantine_and_positive_check_is_not_truth():
    contradicted = World4DCheck(
        check_id="physics",
        scope=CheckScope.PHYSICAL,
        verdict=CheckVerdict.CONTRADICTED,
    )
    with pytest.raises(ValueError, match="must be quarantined"):
        World4DTrajectory(
            branch_id="bad",
            initial_state_digest="a" * 64,
            steps=(
                World4DStep(
                    step_index=1,
                    state_digest="b" * 64,
                    confidence=None,
                    tier=EpistemicTier.PREDICTED,
                ),
            ),
            checks=(contradicted,),
        )
    assert CheckVerdict.NOT_CONTRADICTED.value != "true"
    assert CheckVerdict.NOT_CONTRADICTED.value != "verified"


def test_quarantine_status_cannot_be_hidden_inside_proposed_result():
    trajectory = World4DTrajectory(
        branch_id="quarantined",
        initial_state_digest="a" * 64,
        steps=(
            World4DStep(
                step_index=1,
                state_digest="b" * 64,
                confidence=None,
                tier=EpistemicTier.PREDICTED,
            ),
        ),
        checks=(
            World4DCheck(
                check_id="physics",
                scope=CheckScope.PHYSICAL,
                verdict=CheckVerdict.CONTRADICTED,
            ),
        ),
        quarantined=True,
    )
    with pytest.raises(ValueError, match="cannot contain quarantine"):
        World4DProviderResult(
            provider_id="fixture",
            provider_version="v1",
            status=ProviderResultStatus.PROPOSED,
            trajectories=(trajectory,),
        )


def test_contract_metadata_and_check_collections_are_bounded():
    checks = tuple(
        World4DCheck(
            check_id=f"check_{index}",
            scope=CheckScope.PHYSICAL,
            verdict=CheckVerdict.NOT_RUN,
        )
        for index in range(9)
    )
    with pytest.raises(ValueError, match="more than 8 items"):
        World4DTrajectory(
            branch_id="too_many_checks",
            initial_state_digest="a" * 64,
            steps=(
                World4DStep(
                    step_index=1,
                    state_digest="b" * 64,
                    confidence=None,
                    tier=EpistemicTier.PREDICTED,
                ),
            ),
            checks=checks,
        )
    with pytest.raises(ValueError, match="more than 16 items"):
        World4DProviderResult(
            provider_id="fixture",
            provider_version="v1",
            status=ProviderResultStatus.ABSTAINED,
            trajectories=(),
            limitations=tuple(f"limit_{index}" for index in range(17)),
        )


def test_round_trip_rejects_forged_authority_and_fact_status():
    trajectory = _trajectory().to_dict()
    trajectory["authoritative"] = True
    with pytest.raises(ValueError, match="authoritative"):
        World4DTrajectory.from_dict(trajectory)

    step = _trajectory().steps[0].to_dict()
    step["accepted_as_fact"] = True
    with pytest.raises(ValueError, match="accepted_as_fact"):
        World4DStep.from_dict(step)

    receipt = copy.deepcopy(_receipt().to_dict())
    receipt["capability_claims"] = ["world_prediction"]
    with pytest.raises(ValueError, match="capability claims"):
        World4DShadowReceipt.from_dict(receipt)


def test_provider_result_round_trip_preserves_digest_identity():
    result = _result()
    rebuilt = World4DProviderResult.from_dict(result.to_dict())
    assert rebuilt.to_dict() == result.to_dict()
    tampered = copy.deepcopy(result.to_dict())
    tampered["trajectories"][0]["steps"][0]["state_digest"] = "f" * 64
    with pytest.raises(ValueError):
        World4DProviderResult.from_dict(tampered)


def test_round_trip_contracts_reject_unknown_fields_and_schema_drift():
    request = _request().to_dict()
    request["raw_prompt"] = "must not be retained"
    with pytest.raises(ValueError, match="keys invalid"):
        World4DRequest.from_dict(request)

    receipt = _receipt().to_dict()
    receipt["schema_version"] = "atanor.world4d.shadow.v999"
    with pytest.raises(ValueError, match="schema_version"):
        World4DShadowReceipt.from_dict(receipt)


def test_receipt_status_counts_and_privacy_codes_are_strict():
    impossible = _receipt().to_dict()
    impossible["trajectory_count"] = 0
    impossible["step_count"] = 0
    impossible["check_summary"] = {
        "not_run": 0,
        "not_contradicted": 0,
        "contradicted": 0,
    }
    with pytest.raises(ValueError, match="counts are inconsistent"):
        World4DShadowReceipt.from_dict(impossible)

    leaked = _receipt().to_dict()
    leaked["limitations"] = ["raw prompt: secret"]
    with pytest.raises(ValueError, match="frozen codes"):
        World4DShadowReceipt.from_dict(leaked)

    non_error_with_error = _receipt().to_dict()
    non_error_with_error["error_kind"] = "provider_observation_error"
    with pytest.raises(ValueError, match="cannot carry error_kind"):
        World4DShadowReceipt.from_dict(non_error_with_error)

    custom_exception_name = _receipt().to_dict()
    custom_exception_name["provider_status"] = "error"
    custom_exception_name["provider_result_digest"] = None
    custom_exception_name["trajectory_count"] = 0
    custom_exception_name["step_count"] = 0
    custom_exception_name["check_summary"] = {
        "not_run": 0,
        "not_contradicted": 0,
        "contradicted": 0,
    }
    custom_exception_name["error_kind"] = "password_supersecret"
    with pytest.raises(ValueError, match="privacy-safe code"):
        World4DShadowReceipt.from_dict(custom_exception_name)

    impossible_proposal = _receipt().to_dict()
    impossible_proposal["check_summary"] = {
        "not_run": 0,
        "not_contradicted": 0,
        "contradicted": 1,
    }
    with pytest.raises(ValueError, match="cannot report contradicted"):
        World4DShadowReceipt.from_dict(impossible_proposal)
