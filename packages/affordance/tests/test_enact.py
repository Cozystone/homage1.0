# -*- coding: utf-8 -*-
"""Enactment: a resonant path becomes a REAL action ONLY through the gated OS Action Lane. Trust is
earned — a reversible action waits for a yes until the operator raises the dial; the machine never
raises its own; a kill switch stops everything; only registry-declared actions can run."""
import packages.affordance.enact as en
from packages.os_action_lane.models import GateOutcome, TrustTier


def _fresh(tmp_path):
    en._LANE = None
    en._TIER_FILE = tmp_path / "tier.json"
    en._AUDIT = tmp_path / "audit.jsonl"


def test_reversible_action_is_held_at_assist(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.ASSIST))
    r = en.enact("offer_rest")                          # open_app music = REVERSIBLE
    assert r["enacted"] is False and r["outcome"] == int(GateOutcome.NEEDS_APPROVAL)
    assert r["approval_token"]                          # parked for an explicit yes


def test_approve_runs_the_held_action(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.ASSIST))
    token = en.enact("offer_rest")["approval_token"]
    a = en.approve(token)
    assert a["ok"] and a["executed"]                    # ran only after the human said yes


def test_guarded_tier_auto_runs_reversible(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.GUARDED))                 # the operator raised the dial
    r = en.enact("offer_rest")
    assert r["enacted"] is True and r["outcome"] == int(GateOutcome.EXECUTE)


def test_kill_switch_blocks_everything(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.AUTONOMOUS))
    en.kill()
    r = en.enact("offer_rest")
    assert r["enacted"] is False and r["outcome"] == int(GateOutcome.BLOCKED)
    en.reset_kill()
    assert en.enact("offer_rest")["enacted"] is True


def test_only_registry_actions_run(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.AUTONOMOUS))
    assert en.enact("does_not_exist")["reason"] == "no_action"       # unknown id → nothing
    assert en.enact("warm_good_news")["reason"] == "no_action"       # an utterance path, no OS action


def test_every_enactment_is_audited(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.GUARDED))
    en.enact("offer_rest")
    assert en._AUDIT.exists() and en._AUDIT.read_text(encoding="utf-8").strip()   # append-only trail


def test_machine_never_self_promotes_status_only_recommends(tmp_path):
    _fresh(tmp_path)
    en.set_tier(int(TrustTier.ASSIST))
    st = en.lane_status()
    assert st["tier"] == int(TrustTier.ASSIST)
    assert st["promotion"]["recommend"] is False        # no track record yet → no promotion granted
