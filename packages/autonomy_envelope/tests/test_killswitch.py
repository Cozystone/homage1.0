# -*- coding: utf-8 -*-
"""SEALED GATE (b): killswitch set => loop STOPS immediately, halt recorded.

The switch is checked before EVERY action and honored instantly: once engaged, even a
whitelisted, moral-clean action is refused, and the halt is written to the ledger.
"""
from __future__ import annotations

from packages.autonomy_envelope import (
    ActionKind,
    AutonomyEnvelope,
    EnvelopeAction,
    EnvelopeHalted,
    Killswitch,
)


def test_killswitch_engage_and_require(tmp_path):
    ks = Killswitch(tmp_path / "KILLSWITCH")
    assert ks.is_engaged() is False
    ks.require_live()  # clear -> no raise
    ks.engage("operator stop")
    assert ks.is_engaged() is True
    import pytest

    with pytest.raises(EnvelopeHalted):
        ks.require_live()
    assert ks.reset() is True
    assert ks.is_engaged() is False


def test_engaged_killswitch_blocks_a_whitelisted_action(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    # a normally-allowed action is allowed while clear
    assert env.check(EnvelopeAction(ActionKind.READ, "read")).allowed is True

    env.killswitch.engage("operator immediate stop")
    before = env.ledger.count()

    dec = env.check(EnvelopeAction(ActionKind.READ, "read again"))
    assert dec.allowed is False, "engaged killswitch must stop even a whitelisted action"
    assert "HALTED" in dec.reason
    # halt recorded
    assert env.ledger.count() == before + 1
    assert env.ledger.events_of("killswitch_halt"), "the halt must be recorded in the ledger"


def test_killswitch_stops_self_winding_questions_and_cycles(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.killswitch.engage("stop everything")

    q = env.record_question("What am I uncertain about?")
    assert q.allowed is False and "HALTED" in q.reason

    c = env.mark_cycle(0.9)
    assert c.allowed is False and "HALTED" in c.reason

    # every entry-point recorded its halt
    halts = env.ledger.events_of("killswitch_halt")
    assert len(halts) >= 2


def test_killswitch_checked_before_constants_and_whitelist(tmp_path):
    # Even an out-of-whitelist action, once the killswitch is engaged, reports the HALT
    # (killswitch is the first gate) — the loop is stopped, full stop.
    env = AutonomyEnvelope(tmp_path)
    env.killswitch.engage("halt")
    dec = env.check(EnvelopeAction("some_unknown_kind", "attempt"))
    assert dec.allowed is False
    assert "HALTED" in dec.reason  # killswitch reason, not the whitelist reason


def test_reset_resumes(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.killswitch.engage("pause")
    assert env.check(EnvelopeAction(ActionKind.READ, "x")).allowed is False
    env.killswitch.reset()
    assert env.check(EnvelopeAction(ActionKind.READ, "x")).allowed is True
