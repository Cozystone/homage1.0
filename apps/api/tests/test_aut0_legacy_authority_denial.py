from __future__ import annotations

from app.routers import cloud_brain, os_action


def test_environment_flag_cannot_reach_production_merge(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ATANOR_ALLOW_LOCAL_PROMOTION", "1")
    monkeypatch.setenv("ATANOR_OPERATOR_TOKEN", "legacy-secret")

    unattended = cloud_brain.merge_candidates_to_production_now()
    endpoint = cloud_brain.cloud_brain_merge_candidates(
        cloud_brain.MergeCandidatesIn(
            operator_token="legacy-secret",
            candidate_store_path="D:/does-not-matter",
        )
    )

    assert unattended == {
        "merged": False,
        "production_store_mutated": False,
        "reason": "unattended_production_merge_removed_aut0",
        "required_boundary": "signed_operator_promotion_landing_chain",
    }
    assert endpoint["merged"] is False
    assert endpoint["production_store_mutated"] is False
    assert (
        endpoint["reason"]
        == "cryptographic_promotion_boundary_required"
    )


def test_os_action_token_and_environment_cannot_raise_authority(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ATANOR_OPERATOR_TOKEN", "legacy-secret")
    monkeypatch.setenv("ATANOR_OS_ACTION_TRUST_LOCAL", "1")
    monkeypatch.setenv("ATANOR_TRUST_TIER", "3")
    os_action._LANE.reset_kill()  # noqa: SLF001 - isolate global router fixture
    os_action._LANE.set_tier(os_action.TrustTier.OBSERVE)  # noqa: SLF001
    try:
        raised = os_action.set_tier(
            os_action.TierIn(
                tier=int(os_action.TrustTier.AUTONOMOUS),
                operator_token="legacy-secret",
            )
        )
        approved = os_action.approve(
            os_action.TokenIn(token="attacker-visible-token")
        )

        assert raised["ok"] is False
        assert (
            raised["reason"]
            == "signed_operator_run_lease_required"
        )
        assert raised["tier_name"] == "OBSERVE"
        assert approved["ok"] is False
        assert approved["executed"] is False
    finally:
        os_action._LANE.set_tier(os_action.TrustTier.OBSERVE)  # noqa: SLF001
        os_action._LANE.reset_kill()  # noqa: SLF001


def test_os_action_kill_has_explicit_cooperative_local_reset() -> None:
    os_action._LANE.set_tier(os_action.TrustTier.OBSERVE)  # noqa: SLF001
    os_action._LANE.reset_kill()  # noqa: SLF001
    try:
        stopped = os_action.kill(os_action.KillIn(on=True))
        reset = os_action.kill(os_action.KillIn(on=False))

        assert stopped["killed"] is True
        assert reset["killed"] is False
        assert reset["reset"] is True
        assert reset["approval_mode"] == "cooperative_local_m0"
    finally:
        os_action._LANE.reset_kill()  # noqa: SLF001
