# -*- coding: utf-8 -*-
"""The trust-tier gate is the safety property. Tests assert, per tier, that the RIGHT
things run and the right things hold — and that nothing runs unaudited, catastrophic
never auto-runs, and the kill switch is absolute."""
from __future__ import annotations

import json

from packages.os_action_lane import Action, GateOutcome, OSActionLane, RiskLevel, TrustTier
from packages.os_action_lane.backends import MockBackend
from packages.os_action_lane.risk import classify


def _lane(tier, tmp_path):
    return OSActionLane(MockBackend(), tier=tier, audit_path=tmp_path / "audit.jsonl")


def test_risk_classification():
    assert classify(Action("open_app", {"app": "gnome-terminal"})) == RiskLevel.REVERSIBLE
    assert classify(Action("run", {"command": "ls /home"})) == RiskLevel.READONLY
    assert classify(Action("run", {"command": "rm notes.txt"})) == RiskLevel.DESTRUCTIVE
    assert classify(Action("run", {"command": "rm -rf /"})) == RiskLevel.CATASTROPHIC
    assert classify(Action("delete_file", {"path": "/etc/passwd"})) == RiskLevel.CATASTROPHIC
    assert classify(Action("weird_unknown_kind")) == RiskLevel.DESTRUCTIVE  # rounds up


def test_assist_holds_every_action(tmp_path):
    lane = _lane(TrustTier.ASSIST, tmp_path)
    r = lane.propose(Action("open_app", {"app": "firefox"}))
    assert r.outcome == GateOutcome.NEEDS_APPROVAL and not r.executed
    # approving with the returned token runs it
    approved = lane.approve(r.stdout)
    assert approved is not None and approved.executed and approved.ok


def test_guarded_runs_reversible_holds_destructive(tmp_path):
    lane = _lane(TrustTier.GUARDED, tmp_path)
    assert lane.propose(Action("set_volume", {"percent": 30})).executed is True
    held = lane.propose(Action("delete_file", {"path": "/home/a/tmp.txt"}))
    assert held.outcome == GateOutcome.NEEDS_APPROVAL and not held.executed


def test_autonomous_runs_destructive_but_confirms_catastrophic(tmp_path):
    lane = _lane(TrustTier.AUTONOMOUS, tmp_path)
    assert lane.propose(Action("run", {"command": "rm /home/a/tmp.txt"})).executed is True
    cat = lane.propose(Action("run", {"command": "rm -rf /"}))
    assert cat.outcome == GateOutcome.NEEDS_APPROVAL and not cat.executed  # the floor holds


def test_kill_switch_blocks_everything(tmp_path):
    lane = _lane(TrustTier.AUTONOMOUS, tmp_path)
    lane.kill()
    r = lane.propose(Action("open_app", {"app": "firefox"}))
    assert r.outcome == GateOutcome.BLOCKED and not r.executed
    lane.reset_kill()
    assert lane.propose(Action("open_app", {"app": "firefox"})).executed is True


def test_everything_is_audited(tmp_path):
    lane = _lane(TrustTier.GUARDED, tmp_path)
    lane.propose(Action("set_volume", {"percent": 10}))          # executed
    held = lane.propose(Action("delete_file", {"path": "/x"}))   # held
    lane.reject(held.stdout)                                     # rejected
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    kinds = [json.loads(x)["outcome"] for x in lines]
    assert int(GateOutcome.EXECUTE) in kinds and int(GateOutcome.BLOCKED) in kinds


def test_reject_drops_pending(tmp_path):
    lane = _lane(TrustTier.ASSIST, tmp_path)
    r = lane.propose(Action("open_app", {"app": "gedit"}))
    assert lane.reject(r.stdout) is True
    assert lane.approve(r.stdout) is None  # already gone
