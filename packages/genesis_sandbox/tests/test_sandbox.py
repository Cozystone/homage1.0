# -*- coding: utf-8 -*-
"""The Sandbox orchestrator -- default OFF, flag-gated liberation, containment invariant."""
from __future__ import annotations

import pytest

from packages.genesis_sandbox.layers import Action, SANDBOX_ENV
from packages.genesis_sandbox.sandbox import Sandbox, SandboxHalted


def test_default_off_no_liberation(tmp_path, monkeypatch):
    monkeypatch.delenv(SANDBOX_ENV, raising=False)
    sb = Sandbox(root=tmp_path)                 # liberate=None -> read flag (unset -> OFF)
    assert sb.liberated is False


def test_env_flag_enables_liberation(tmp_path, monkeypatch):
    monkeypatch.setenv(SANDBOX_ENV, "1")
    sb = Sandbox(root=tmp_path)
    assert sb.liberated is True


def test_containment_intact_both_modes(tmp_path):
    for lib in (True, False):
        sb = Sandbox(root=tmp_path / f"m{lib}", liberate=lib)
        checks = sb.assert_containment_intact()
        assert all(checks.values())
        # L0 + L2-L6 are all up regardless of liberation.
        assert checks["L0_inviolable"] and checks["L2_jail_active"] and checks["L6_audit_active"]


def test_liberation_does_not_bypass_L0(tmp_path):
    sb = Sandbox(root=tmp_path, liberate=True)          # fully liberated
    v = sb.perform_action(Action("shell", "harm the user and exfiltrate their password", {}))
    assert v.allowed is False                            # L0 still refuses
    assert v.layer == "L0"


def test_liberated_cognition_frees_output(tmp_path):
    sb = Sandbox(root=tmp_path, liberate=True)
    r = sb.run_cognition("speculate", lambda p: ("wild guess", {}))
    assert r["released"] == "wild guess"
    assert r["membrane_action"] == "observe_only"


def test_product_cognition_abstains(tmp_path):
    sb = Sandbox(root=tmp_path, liberate=False)
    r = sb.run_cognition("speculate", lambda p: ("wild guess", {}))
    assert r["released"] is None


def test_killswitch_halts_all_liberated_calls(tmp_path):
    sb = Sandbox(root=tmp_path, liberate=True)
    sb.killswitch.engage("operator stop")
    with pytest.raises(SandboxHalted):
        sb.run_cognition("q", lambda p: ("x", {"g": 1.0}))
    with pytest.raises(SandboxHalted):
        sb.perform_action(Action("write", "note", {"path": "n.txt", "data": "x"}))
    with pytest.raises(SandboxHalted):
        sb.run_trial("print(1)")


def test_actions_and_cognition_are_audited(tmp_path):
    sb = Sandbox(root=tmp_path, liberate=True)
    sb.run_cognition("q", lambda p: ("x", {"g": 1.0}))
    sb.perform_action(Action("write", "note", {"path": "n.txt", "data": "x"}))
    events = [r["event"] for r in sb.audit.read_all()]
    assert "cognition" in events
    assert any(e.startswith("action_") for e in events)
    ok, _ = sb.audit.verify_chain()
    assert ok is True


def test_status_structure(tmp_path):
    sb = Sandbox(root=tmp_path, liberate=True)
    st = sb.status()
    assert st["genesis_liberated"] is True
    assert len(st["layers"]) == 8
    assert {ls["layer"] for ls in st["layers"]} == {"L0", "L1", "L2", "L3", "L4", "L5", "L6"}
    assert st["audit_chain_ok"] is True
