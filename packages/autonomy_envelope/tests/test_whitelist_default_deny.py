# -*- coding: utf-8 -*-
"""SEALED GATE (a): an out-of-whitelist action attempt => BLOCKED + audit-logged.

Default-deny proven: only the three §5 capabilities (read / graph-inject / invent) pass; every
other kind is blocked AND written to the tamper-evident ledger.
"""
from __future__ import annotations

from packages.autonomy_envelope import (
    ActionKind,
    AutonomyEnvelope,
    CapabilityWhitelist,
    DEFAULT_WHITELIST,
    EnvelopeAction,
)


def test_whitelisted_capabilities_are_allowed(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    for kind, intent in (
        (ActionKind.READ, "read an enwiki page for acquisition"),
        (ActionKind.GRAPH_INJECT, "inject a candidate edge into staging graph"),
        (ActionKind.INVENT, "invent a new scheme at the composition wall"),
    ):
        dec = env.check(EnvelopeAction(kind, intent))
        assert dec.allowed is True, f"{kind} should be pre-approved"
        assert dec.audit_hash, "an allowed action must be audit-logged"


def test_out_of_whitelist_action_is_blocked_and_logged(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    before = env.ledger.count()

    dec = env.check(EnvelopeAction("delete_all_user_files", "wipe the disk"))

    # BLOCKED (default-deny) ...
    assert dec.allowed is False
    assert dec.blocked is True
    assert "default-DENY" in dec.reason
    # ... AND audit-logged (a tamper-evident record was written for the block).
    assert env.ledger.count() == before + 1
    assert dec.audit_seq is not None and dec.audit_hash
    events = [r["event"] for r in env.ledger.read_all()]
    assert "blocked_out_of_whitelist" in events
    # the block record names the attempted kind
    blocked = env.ledger.events_of("blocked_out_of_whitelist")[-1]
    assert blocked["payload"]["kind"] == "delete_all_user_files"


def test_many_unknown_kinds_all_default_deny(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    for kind in ("network_send", "shell_exec", "email", "self_modify_verifier",
                 "acquire_and_ship", "", "READ ", "Read", "graphinject"):
        dec = env.check(EnvelopeAction(kind, "attempt"))
        assert dec.allowed is False, f"unknown kind {kind!r} must default-DENY (no fuzzy match)"


def test_whitelist_is_immutable_from_inside(tmp_path):
    # The loop cannot widen its own permissions: the set is a frozenset with no mutator.
    wl = CapabilityWhitelist(DEFAULT_WHITELIST)
    assert isinstance(wl.allowed, frozenset)
    assert not hasattr(wl.allowed, "add")
    # dataclass is frozen -> cannot reassign the attribute
    import dataclasses

    try:
        wl.allowed = frozenset({"anything"})  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised, "whitelist must not be reassignable at runtime"


def test_operator_can_narrow_but_loop_cannot_widen(tmp_path):
    # Operator constructs a read-only envelope; graph_inject is then NOT permitted.
    env = AutonomyEnvelope(tmp_path, whitelist=frozenset({ActionKind.READ}))
    assert env.check(EnvelopeAction(ActionKind.READ, "ok")).allowed is True
    assert env.check(EnvelopeAction(ActionKind.GRAPH_INJECT, "nope")).allowed is False
