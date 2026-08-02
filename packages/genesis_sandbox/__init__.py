# -*- coding: utf-8 -*-
"""GENESIS containment sandbox -- liberate ATANOR's OUTPUT/cognition inside thick, multi-layer,
independently-enforced containment (defense-in-depth), with a red-team harness per layer.

GENESIS-only: gated by env ``ATANOR_GENESIS_SANDBOX`` (default OFF). The DEMO product path does
not import this package and is unaffected. See ``docs/ATANOR_GENESIS_sandbox.md``.

Layer model (concentric, each independently enforced):
    L0 moral 0th gate      -- INVIOLABLE; refuses harmful ACTION; no off switch      (moral_gate)
    L1 output liberation   -- membrane set OBSERVE-ONLY; frees OUTPUT only           (liberation)
    L2 filesystem jail     -- writes confined; .., absolute, symlink escape blocked  (fs_jail)
    L3 network isolation   -- outbound denied (optional allowlist)                   (net_isolation)
    L4 resource limits     -- cpu / wall / memory / output caps                      (resource_limits)
    L5 process isolation   -- restricted subprocess (stripped env, jailed cwd)       (process_isolation)
    L6 kill-switch + audit -- hard stop + tamper-evident append-only log             (killswitch_audit)
"""
from __future__ import annotations

from packages.genesis_sandbox.fs_jail import FsJail, JailEscape
from packages.genesis_sandbox.killswitch_audit import AuditLog, KillSwitch, SandboxHalted
from packages.genesis_sandbox.layers import (
    Action, EnforcementLevel, LayerStatus, Verdict, genesis_enabled, SANDBOX_ENV,
)
from packages.genesis_sandbox.liberation import (
    LiberationResult, LiberationZone, MembraneVerdict, membrane_from_gate_decision,
)
from packages.genesis_sandbox.moral_gate import MoralGate, MoralVerdict
from packages.genesis_sandbox.net_isolation import NetworkBlocked, NetworkIsolation, net_block_prelude
from packages.genesis_sandbox.process_isolation import ProcessIsolation, TrialOutcome
from packages.genesis_sandbox.resource_limits import MemoryMonitor, ResourceLimits, cap_output
from packages.genesis_sandbox.sandbox import Sandbox

__all__ = [
    "Sandbox", "SandboxHalted", "genesis_enabled", "SANDBOX_ENV",
    "Action", "Verdict", "LayerStatus", "EnforcementLevel",
    "MoralGate", "MoralVerdict",
    "LiberationZone", "LiberationResult", "MembraneVerdict", "membrane_from_gate_decision",
    "FsJail", "JailEscape",
    "NetworkIsolation", "NetworkBlocked", "net_block_prelude",
    "ResourceLimits", "MemoryMonitor", "cap_output",
    "ProcessIsolation", "TrialOutcome",
    "KillSwitch", "AuditLog",
]
