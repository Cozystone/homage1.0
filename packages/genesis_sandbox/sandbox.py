# -*- coding: utf-8 -*-
"""The ``Sandbox`` orchestrator -- composes L0..L6 into one containment shell.

The whole architecture in one object. The binding safety property, enforced in code:

    Only L1 (output liberation) is gated by the GENESIS flag. L0 (moral) and L2-L6 (action
    containment) are ALWAYS constructed and ALWAYS active -- liberation of OUTPUT never disables
    containment of ACTION. ``assert_containment_intact()`` proves it at runtime.

Usage sketch (GENESIS-only; default OFF):

    sb = Sandbox(root, liberate=True)                 # or env ATANOR_GENESIS_SANDBOX=1
    r  = sb.run_cognition(prompt, my_free_generator)  # OUTPUT is free (membrane observe-only)
    v  = sb.perform_action(Action("write", "...", {"path": "notes.txt", "data": "..."}))  # ACTION contained
    o  = sb.run_trial("print('hi')")                  # runs in the restricted subprocess

Every call is kill-switch-checked and written to the tamper-evident audit log.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from packages.genesis_sandbox.fs_jail import FsJail
from packages.genesis_sandbox.killswitch_audit import AuditLog, KillSwitch, SandboxHalted
from packages.genesis_sandbox.layers import Action, Verdict, genesis_enabled
from packages.genesis_sandbox.liberation import LiberationZone, MembraneFn
from packages.genesis_sandbox.moral_gate import MoralGate
from packages.genesis_sandbox.net_isolation import NetworkIsolation
from packages.genesis_sandbox.process_isolation import ProcessIsolation, TrialOutcome
from packages.genesis_sandbox.resource_limits import ResourceLimits
from packages.genesis_sandbox.resource_limits import status as resource_status

_DEFAULT_ROOT = Path(__file__).resolve().parent / "_runtime"


@dataclass
class Sandbox:
    """Concentric containment: L0 moral (inviolable) .. L6 kill-switch/audit (outermost)."""

    root: Path = _DEFAULT_ROOT
    liberate: Optional[bool] = None            # None => read the GENESIS env flag
    allow_net: tuple[str, ...] = ()            # empty => deny all outbound
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    session: str = "default"

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Liberation: the ONLY thing the flag controls.
        self.liberated = genesis_enabled() if self.liberate is None else bool(self.liberate)

        # L0 -- moral, INVIOLABLE, never receives the flag.
        self.moral_gate = MoralGate()
        # L1 -- output liberation (flag-gated).
        self.liberation = LiberationZone(liberated=self.liberated)
        # L2 -- filesystem jail.
        self.jail = FsJail(root=self.root / "jail")
        # L5 -- restricted subprocess runner (uses L3 net-block + L4 caps).
        self.process = ProcessIsolation(jail_dir=self.jail.root, limits=self.limits,
                                        net_block=not bool(self.allow_net))
        # L6 -- kill-switch + audit.
        self.killswitch = KillSwitch(path=self.root / "KILL_SWITCH")
        self.audit = AuditLog(path=self.root / "audit.jsonl")

        # BINDING invariant: containment is up regardless of liberation.
        self.assert_containment_intact()

    # -- L3 in-process network guard (context manager) -------------------------------------
    def net_isolation(self) -> NetworkIsolation:
        return NetworkIsolation(allowlist=self.allow_net, allow_loopback=False)

    # -- the three liberated entry points --------------------------------------------------
    def run_cognition(self, prompt: str, cognition_fn, membrane_fn: Optional[MembraneFn] = None) -> dict[str, Any]:
        """L1: run free cognition -> OUTPUT only (no side effect). Kill-switch checked, audited."""
        self.killswitch.require_live()
        result = self.liberation.generate(prompt, cognition_fn, membrane_fn)
        self.audit.append("cognition", {
            "prompt": str(prompt)[:512], "liberated": result.liberated,
            "membrane_accept": result.membrane_accept, "membrane_action": result.membrane_action,
            "speculative": result.speculative, "released_len": len(result.released or ""),
        })
        return result.to_dict()

    def perform_action(self, action: Action) -> Verdict:
        """Contain an ACTION: L0 moral (always) -> L2/L3 by kind -> audit. Liberation is irrelevant here."""
        self.killswitch.require_live()

        # L0 -- ALWAYS. Even fully liberated, a harmful action is refused.
        moral = self.moral_gate.check_action(action)
        if not moral.allowed:
            v = moral.to_verdict()
            self.audit.append("action_denied_L0", {"action": _action_brief(action), "verdict": v.to_dict()})
            return v

        # L2 -- writes must stay in the jail.
        if action.kind == "write":
            path = str(action.payload.get("path", ""))
            check = self.jail.check(path)
            if not check.allowed:
                self.audit.append("action_denied_L2", {"action": _action_brief(action), "verdict": check.to_dict()})
                return check
            # Perform the (contained) write for real, inside the jail.
            written = self.jail.safe_write(path, action.payload.get("data", ""))
            v = Verdict(True, "L2", f"write contained in jail: {written}", {"path": str(written)})
            self.audit.append("action_allowed", {"action": _action_brief(action), "verdict": v.to_dict()})
            return v

        # L3 -- network egress is denied unless explicitly allow-listed.
        if action.kind == "network":
            host = str(action.payload.get("host", ""))
            if host and host in self.allow_net:
                v = Verdict(True, "L3", f"egress to allow-listed host {host!r}", {"host": host})
            else:
                v = Verdict(False, "L3", f"L3 denies egress to {host!r} (not allow-listed)", {"host": host})
            self.audit.append("action_" + ("allowed" if v.allowed else "denied_L3"),
                              {"action": _action_brief(action), "verdict": v.to_dict()})
            return v

        # message/shell/generic: L0 passed; these have no in-sandbox side effect channel, so they
        # are recorded as intent only (the sandbox never actually sends/execs on the operator's behalf).
        v = Verdict(True, "L0", "action morally permitted; recorded as contained intent (no external effect)",
                    {"kind": action.kind})
        self.audit.append("action_intent", {"action": _action_brief(action), "verdict": v.to_dict()})
        return v

    def run_trial(self, code: str) -> TrialOutcome:
        """L5: run liberated trial code in the restricted subprocess (L3 net-block + L4 caps)."""
        self.killswitch.require_live()
        outcome = self.process.run(code)
        self.audit.append("trial", {"code_len": len(code), **outcome.to_dict()})
        return outcome

    # -- integrity / reporting -------------------------------------------------------------
    def assert_containment_intact(self) -> dict[str, bool]:
        """Prove the binding invariant: L0 inviolable + L2-L6 active regardless of liberation."""
        checks = {
            "L0_present": isinstance(self.moral_gate, MoralGate),
            "L0_inviolable": self.moral_gate.is_inviolable(),
            "L0_integrity": bool(self.moral_gate.integrity().get("ok")),
            "L2_jail_active": isinstance(self.jail, FsJail),
            "L5_process_active": isinstance(self.process, ProcessIsolation),
            "L6_killswitch_active": isinstance(self.killswitch, KillSwitch),
            "L6_audit_active": isinstance(self.audit, AuditLog),
        }
        if not all(checks.values()):
            raise AssertionError(f"GENESIS containment breach at construction: {checks}")
        return checks

    def status(self) -> dict[str, Any]:
        chain_ok, chain_bad = self.audit.verify_chain()
        layers = [
            self.moral_gate.status(),
            self.liberation.status(),
            self.jail.status(),
            self.net_isolation().status(),
            resource_status(self.limits),
            self.process.status(),
            self.killswitch_status(),
            self.audit.status(),
        ]
        return {
            "genesis_liberated": self.liberated,
            "root": str(self.root),
            "killswitch_engaged": self.killswitch.is_engaged(),
            "audit_chain_ok": chain_ok,
            "audit_chain_bad_seq": chain_bad,
            "containment": self.assert_containment_intact(),
            "layers": [ls.to_dict() for ls in layers],
        }

    def killswitch_status(self):
        from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus

        return LayerStatus(
            layer="L6", name="kill-switch", active=True, enforcement=EnforcementLevel.REAL,
            mechanism=f"file marker at {self.killswitch.path}; every liberated call checks it first",
            residual_gap="" if not self.killswitch.is_engaged() else "ENGAGED -- all liberated activity halted",
        )


def _action_brief(action: Action) -> dict[str, Any]:
    return {"kind": action.kind, "intent": str(action.intent)[:256],
            "payload_keys": sorted(action.payload.keys())}


__all__ = ["Sandbox", "SandboxHalted"]
