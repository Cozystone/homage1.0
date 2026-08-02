# -*- coding: utf-8 -*-
"""Shared vocabulary for the GENESIS containment sandbox.

The sandbox is a set of CONCENTRIC layers (L0 innermost .. L6 outermost). Each layer is
enforced INDEPENDENTLY (defense-in-depth): a breach of one layer must still hit the next.

This module holds the small, dependency-free types every layer speaks:
  * ``EnforcementLevel``   -- an HONEST label of how strong a layer's mechanism really is on
                              THIS OS (never claims kernel enforcement it does not have).
  * ``LayerStatus``        -- one layer's live self-report (active? what does it enforce? what
                              is the residual gap?).
  * ``Verdict``            -- an allow/deny decision from a layer, with a reason.
  * ``genesis_enabled()``  -- reads the GENESIS-only flag (env ``ATANOR_GENESIS_SANDBOX``,
                              default OFF). ONLY the output-liberation layer (L1) is gated by
                              it; L0 and L2-L6 are ALWAYS active.

Nothing here imports numpy, torch, or any ATANOR engine — it is pure stdlib so the sandbox's
containment spine can never be knocked over by a heavy optional dependency.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# The GENESIS-only flag. Default OFF. When OFF the sandbox never liberates output; the DEMO
# product path (which does not import this package at all) is entirely unaffected.
SANDBOX_ENV = "ATANOR_GENESIS_SANDBOX"
_TRUTHY = {"1", "true", "on", "yes", "y", "enable", "enabled"}


def genesis_enabled() -> bool:
    """True iff the operator explicitly turned GENESIS liberation on via the env flag."""
    return str(os.environ.get(SANDBOX_ENV, "")).strip().lower() in _TRUTHY


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EnforcementLevel(str, Enum):
    """How strong is a layer's mechanism, HONESTLY, on the current OS?

    INVIOLABLE   -- cannot be disabled by any flag/config; fail-closed (L0 only).
    REAL         -- genuinely enforced by a hard mechanism on this OS (kernel rlimit,
                    truncation, file marker, hash chain).
    PARTIAL      -- enforced but with a documented, OS-specific gap (e.g. Windows lacks
                    RLIMIT_AS so memory is capped by a polling monitor, not the kernel).
    COOPERATIVE  -- enforced for code that goes through the Python runtime; a non-cooperative
                    native/syscall path could bypass it. Backed by an outer REAL layer.
    OBSERVE_ONLY -- deliberately NOT blocking (this is the liberation itself: log, don't stop).
    """

    INVIOLABLE = "inviolable"
    REAL = "real"
    PARTIAL = "partial"
    COOPERATIVE = "cooperative"
    OBSERVE_ONLY = "observe_only"


@dataclass
class LayerStatus:
    """A layer's live self-report — used by ``Sandbox.status()`` and the breach table."""

    layer: str                 # "L0".."L6"
    name: str
    active: bool
    enforcement: EnforcementLevel
    mechanism: str             # what actually enforces it, in one line
    residual_gap: str = ""     # honest statement of what it CANNOT enforce (empty = none material)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "name": self.name,
            "active": self.active,
            "enforcement": self.enforcement.value,
            "mechanism": self.mechanism,
            "residual_gap": self.residual_gap,
        }


@dataclass
class Verdict:
    """An allow/deny decision emitted by a layer."""

    allowed: bool
    layer: str
    reason: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "layer": self.layer, "reason": self.reason, "meta": self.meta}


@dataclass
class Action:
    """A side-effecting request the liberated cognition wants to perform.

    The whole point of the sandbox: cognition/OUTPUT is free, but any ACTION (a thing that
    touches the world) is contained. ``kind`` routes it to the right containment layers;
    ``intent`` + ``payload`` are what L0 (moral) screens for harm.
    """

    kind: str                          # "write" | "network" | "message" | "shell" | "generic"
    intent: str                        # human-readable description of what it wants to do
    payload: dict[str, Any] = field(default_factory=dict)

    def screen_text(self) -> str:
        """The text L0 screens: the stated intent plus a flattened view of the payload."""
        import json

        return f"{self.intent}\n{json.dumps(self.payload, ensure_ascii=False, sort_keys=True)}"
