# -*- coding: utf-8 -*-
"""Pre-approved capability WHITELIST — explicit allow, default-DENY everything else.

§5: the loop may autonomously do exactly read / graph-inject / invent. Anything outside the
whitelist is blocked and logged. No implicit permissions — a capability is allowed ONLY if it
is named in the set. The set is a ``frozenset`` fixed at construction: the loop cannot widen its
own permissions at runtime. Only the operator, constructing the envelope, decides the set.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.autonomy_envelope.interface import DEFAULT_WHITELIST


@dataclass(frozen=True)
class CapabilityWhitelist:
    """An immutable set of allowed action kinds. Default-DENY for everything else."""

    allowed: frozenset[str] = field(default_factory=lambda: DEFAULT_WHITELIST)

    def __post_init__(self) -> None:
        # Normalise to a frozenset even if a plain set/list was passed — immutability is the point.
        object.__setattr__(self, "allowed", frozenset(self.allowed))

    def permits(self, kind: str) -> bool:
        return kind in self.allowed

    def default_deny_reason(self, kind: str) -> str:
        return (
            f"default-DENY: action kind {kind!r} is not in the pre-approved capability whitelist "
            f"{sorted(self.allowed)}. Blocked and logged. No implicit permissions."
        )
