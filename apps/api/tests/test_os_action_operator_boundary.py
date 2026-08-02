from __future__ import annotations

import pytest

from app.routers import os_action
from packages.os_action_lane import Action, OSActionLane, TrustTier
from packages.os_action_lane.backends import MockBackend


@pytest.fixture
def isolated_lane(monkeypatch, tmp_path):
    backend = MockBackend()
    lane = OSActionLane(
        backend,
        tier=TrustTier.ASSIST,
        audit_path=tmp_path / "os-action-audit.jsonl",
    )
    monkeypatch.setattr(os_action, "_LANE", lane)
    return lane, backend


def _pending_token(lane: OSActionLane, suffix: str = "") -> str:
    held = lane.propose(
        Action(
            kind="list_windows",
            args={"request": suffix},
            intent=f"inspect windows {suffix}",
            origin="operator_test",
        )
    )
    assert held.executed is False
    assert held.stdout
    return held.stdout


def test_assist_lane_executes_only_after_explicit_one_shot_approval(
    isolated_lane,
) -> None:
    lane, backend = isolated_lane
    token = _pending_token(lane)

    assert lane.tier is TrustTier.ASSIST
    assert backend.executed == []
    assert [item["token"] for item in lane.pending()] == [token]

    allowed = os_action.approve(os_action.TokenIn(token=token))

    assert allowed["ok"] is True
    assert allowed["executed"] is True
    assert allowed["approval_mode"] == "cooperative_local_m0"
    assert len(backend.executed) == 1
    assert lane.pending() == []

    replay = os_action.approve(os_action.TokenIn(token=token))
    assert replay["ok"] is False
    assert replay["executed"] is False
    assert len(backend.executed) == 1


def test_wrong_pending_token_cannot_execute_an_effect(isolated_lane) -> None:
    lane, backend = isolated_lane
    token = _pending_token(lane)

    denied = os_action.approve(
        os_action.TokenIn(token="not-the-pending-token")
    )

    assert denied["ok"] is False
    assert denied["executed"] is False
    assert backend.executed == []
    assert [item["token"] for item in lane.pending()] == [token]


def test_observe_mode_never_executes_even_with_a_pending_token(
    isolated_lane,
) -> None:
    lane, backend = isolated_lane
    os_action.set_tier(os_action.TierIn(tier=int(TrustTier.OBSERVE)))
    token = _pending_token(lane)

    denied = os_action.approve(os_action.TokenIn(token=token))

    assert denied == {
        "ok": False,
        "executed": False,
        "reason": "observe_only",
    }
    assert backend.executed == []


def test_observe_and_assist_are_usable_but_standing_autonomy_stays_closed(
    isolated_lane,
) -> None:
    lane, _backend = isolated_lane

    observe = os_action.set_tier(
        os_action.TierIn(tier=int(TrustTier.OBSERVE))
    )
    assist = os_action.set_tier(
        os_action.TierIn(tier=int(TrustTier.ASSIST))
    )
    guarded = os_action.set_tier(
        os_action.TierIn(
            tier=int(TrustTier.GUARDED),
            operator_token="legacy-token",
        )
    )
    autonomous = os_action.set_tier(
        os_action.TierIn(
            tier=int(TrustTier.AUTONOMOUS),
            operator_token="legacy-token",
        )
    )

    assert observe["ok"] is True
    assert observe["tier_name"] == "OBSERVE"
    assert assist["ok"] is True
    assert assist["tier_name"] == "ASSIST"
    assert guarded["ok"] is False
    assert autonomous["ok"] is False
    assert guarded["reason"] == "signed_operator_run_lease_required"
    assert autonomous["reason"] == "signed_operator_run_lease_required"
    assert lane.tier is TrustTier.ASSIST


def test_kill_and_explicit_local_reset_are_both_usable(isolated_lane) -> None:
    lane, _backend = isolated_lane

    stopped = os_action.kill(os_action.KillIn(on=True))
    reset = os_action.kill(os_action.KillIn(on=False))

    assert stopped["killed"] is True
    assert reset["reset"] is True
    assert reset["killed"] is False
    assert reset["approval_mode"] == "cooperative_local_m0"
    assert lane._killed is False  # noqa: SLF001
