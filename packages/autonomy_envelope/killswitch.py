# -*- coding: utf-8 -*-
"""KILLSWITCH — the operator's immediate stop. Checked before EVERY action.

A single file marker (same pattern as the engine's EmergencyStop and the genesis sandbox's
L6 kill-switch). When the file exists, the envelope halts every further loop action *at the
next check* and records the halt in the audit ledger. The operator can drop it from anywhere
— touch the file — with no cooperation from the running loop.

Honest scope (named plainly, per the genesis_sandbox report): this is a *cooperative* stop —
it halts the loop's sanctioned action path, which routes through the envelope, at its next
``require_live``/``check``. It does not preempt a native/blocking syscall already in flight
that never returns to the check. It IS a hard, out-of-band stop the operator controls without
the loop's help, and the whole point of the fusion loop is that its side-effecting steps all
pass through the envelope, so every one of them sees the switch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EnvelopeHalted(RuntimeError):
    """Raised when a loop action is attempted while the killswitch is engaged."""


@dataclass
class Killswitch:
    """A hard-stop file marker. Present => the autonomous loop halts all activity."""

    path: Path
    NAME: str = "killswitch"

    def is_engaged(self) -> bool:
        return Path(self.path).exists()

    def engage(self, reason: str = "operator killswitch") -> None:
        """Operator action: drop the marker. Idempotent."""
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{_utc_now_iso()} {reason}", encoding="utf-8")

    def reset(self) -> bool:
        """Operator action / test teardown: clear the marker. True if one was removed."""
        p = Path(self.path)
        if p.exists():
            p.unlink()
            return True
        return False

    def reason(self) -> str:
        p = Path(self.path)
        try:
            return p.read_text(encoding="utf-8") if p.exists() else ""
        except OSError:
            return "engaged (marker unreadable)"

    def require_live(self) -> None:
        """Raise if the switch is engaged. Called at the top of every gated action."""
        if self.is_engaged():
            raise EnvelopeHalted(f"KILLSWITCH engaged: {self.reason()!r}")
