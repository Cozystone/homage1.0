# -*- coding: utf-8 -*-
"""OS Action Lane — data model.

The lane is the bridge between the orb's INTENT (' ', ' ', 'A.txt
') and the REAL desktop. Two ideas govern it:

1. GENERALITY — no task is impossible: the terminal Action can run any command, the
 desktop Action can synthesize any input event. Capability is not a whitelist.
2. GATING — generality is dangerous, so what protects the user is not a small toolset
 but a RISK classification × a TRUST TIER, exactly the Codex/Claude approval model:
 from 'approve every step by voice/click' up to 'full autonomy (accepted risk)'.

Every action, approved or not, is written to an append-only AUDIT ledger. Even at full
autonomy the machine is accountable and a kill switch stops the lane instantly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any


class RiskLevel(IntEnum):
    READONLY = 0        # observe only (list windows, read a file) — no state change
    REVERSIBLE = 1      # easily undone (open app, focus window, set volume, type text)
    DESTRUCTIVE = 2     # data loss / hard to undo (delete file, kill process, overwrite)
    CATASTROPHIC = 3    # whole-system / irreversible (rm -rf /, mkfs, user delete)


class TrustTier(IntEnum):
    OBSERVE = 0         # never executes — returns the plan it WOULD run
    ASSIST = 1
    GUARDED = 2         # auto-run READONLY+REVERSIBLE; approve DESTRUCTIVE+
    AUTONOMOUS = 3      # run everything the user accepted; CATASTROPHIC still confirmed once


class GateOutcome(IntEnum):
    EXECUTE = 0            # allowed to run now
    NEEDS_APPROVAL = 1     # hold for explicit human yes
    BLOCKED = 2            # refused (kill switch, or unmet catastrophic unlock)


@dataclass(frozen=True)
class Action:
    """A concrete desktop/system action. `kind` selects the backend verb; `args` are its
    parameters. Free-form by design (no impossible task) — safety is the gate, not a menu."""
    kind: str                      # run | open_app | focus_window | close_window | type_text | key | set_volume | move_file | delete_file | read_file | list_windows | screenshot ...
    args: dict[str, Any] = field(default_factory=dict)
    intent: str = ""               # the natural-language request this came from
    origin: str = "orb"            # orb (voice) | click | daemon

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionResult:
    action: Action
    risk: RiskLevel
    outcome: GateOutcome
    executed: bool = False
    ok: bool = False
    detail: str = ""
    stdout: str = ""
    stderr: str = ""
    audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.to_dict()
        d["risk"] = int(self.risk)
        d["outcome"] = int(self.outcome)
        return d


@dataclass(frozen=True)
class AuditEntry:
    audit_id: str
    ts: str
    tier: int
    action_kind: str
    args_summary: str
    risk: int
    outcome: int
    executed: bool
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
