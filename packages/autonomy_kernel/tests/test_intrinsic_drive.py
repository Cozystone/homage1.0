# -*- coding: utf-8 -*-
"""Intrinsic drive: a command always wins; acute stress forces protective rest; ELSE the STAKES
layer decides by gradient competition over vitals read from real records (plan S1, 2026-07-21).

The old contract (curiosity>=X -> explore, dopamine>=Y -> express) was a threshold ladder — the
'scheduled algorithm loop' the autoresponder diagnosis named — and is deliberately gone. Drive is
now the steepest genuine deficit, so these tests drive the STAKES vitals (via a monkeypatched
read_vitals) rather than raw hormones, and assert the two invariants that survive: the parent's
command and acute-stress protection still come first."""
from packages.autonomy_kernel import intrinsic_drive as idrv


class _State:
    def __init__(self, curiosity=0.5, cortisol=0.0, dopamine=0.0, repair=0.0):
        self.curiosity = curiosity
        self.hormones = {"cortisol": cortisol, "dopamine": dopamine, "repair": repair}


def _vitals(monkeypatch, **kw):
    """Force the stakes read to a known deficit profile so the drive's choice is deterministic."""
    from packages.continuous_self import stakes
    base = {"knowledge": 0.9, "social": 0.9, "coherence": 0.9, "energy": 0.9}
    base.update(kw)
    monkeypatch.setattr(idrv, "drive_snapshot",
                        lambda s: {"curiosity": s.curiosity, "cortisol": s.hormones["cortisol"],
                                   "dopamine": s.hormones["dopamine"], "repair": s.hormones["repair"]})
    monkeypatch.setattr("packages.continuous_self.stakes.read_vitals",
                        lambda repo=None: stakes.Vitals(**base))


def test_command_always_wins():
    c = idrv.choose_action(_State(curiosity=0.9), has_command=True)
    assert c["action"] == "obey_command"          # autonomy yields to instruction


def test_knowledge_deficit_drives_exploration(monkeypatch):
    _vitals(monkeypatch, knowledge=0.1)           # the steepest hunger is knowledge
    c = idrv.choose_action(_State(curiosity=0.8))
    assert c["action"] == "explore" and c["toward"] == "understand_the_world"


def test_stress_forces_rest_before_any_want(monkeypatch):
    _vitals(monkeypatch, knowledge=0.0)           # even starving, acute stress protects first
    c = idrv.choose_action(_State(curiosity=0.9, cortisol=0.8))
    assert c["action"] == "rest"
    assert idrv.choose_action(_State(curiosity=0.9, repair=0.5))["action"] == "rest"


def test_social_deficit_drives_conversation(monkeypatch):
    _vitals(monkeypatch, social=0.1)
    assert idrv.choose_action(_State(curiosity=0.3))["action"] == "converse"


def test_no_real_deficit_is_idle(monkeypatch):
    _vitals(monkeypatch)                          # every vital healthy
    assert idrv.choose_action(_State(curiosity=0.3))["action"] == "idle"


def test_rate_floor_blocks_thrash(tmp_path, monkeypatch):
    monkeypatch.setattr(idrv, "_STATE", tmp_path / "d.json")
    monkeypatch.setattr(idrv, "_JOURNAL", tmp_path / "j.jsonl")
    (tmp_path / "d.json").write_text('{"last_act_at": 10000, "acts": 1}', encoding="utf-8")
    r = idrv.act(_State(curiosity=0.9), now=10_100)     # 100s < 900 floor
    assert r["acted"] is False and r["reason"] == "rate_floor"
