from __future__ import annotations

from packages.ego_network.models import ConstellationState, EgoDevice
from packages.ego_network.sync import apply_sync_plan_dry_run, compute_constellation_diff, plan_sync_actions


def test_constellation_conflict_detected_and_no_overwrite() -> None:
    device = EgoDevice("desktop", "Desktop", "main_brain", 1.0, True, "now", {})
    local = ConstellationState("owner", [device], "hash-a", "idle", [], {"version": 1})
    remote = ConstellationState("owner", [device], "hash-b", "checkin_available", [], {"version": 2})
    diff = compute_constellation_diff(local, remote)
    plan = plan_sync_actions(diff)
    result = apply_sync_plan_dry_run(plan)
    assert diff["conflict"] is True
    assert plan["requires_user_approval"] is True
    assert result["automatic_overwrite"] is False
    assert result["local_brain_mutated"] is False
    assert result["production_mutated"] is False
