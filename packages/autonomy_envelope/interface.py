# -*- coding: utf-8 -*-
"""The DECOUPLED envelope-hook interface — the one contract both sides agree on.

The fusion loop (agent #84, ``packages/fusion_loop``) calls an *envelope hook* before
every side-effecting action (acquire / graph-inject / invent / promote). This module
defines the shape of that hook so the two packages agree **without importing each other**:

  * ``EnvelopeAction``  — the thing the loop wants to do (kind + intent + payload).
  * ``EnvelopeDecision``— the gate's answer: allow/deny + a reason (+ audit proof).
  * ``EnvelopeHook``    — a ``check(action) -> EnvelopeDecision`` ``Protocol``. Structural,
                          so ``AutonomyEnvelope`` satisfies it without any inheritance and
                          ``fusion_loop`` can declare its own identical Protocol on its side.

This module is pure stdlib. It carries NO enforcement itself except one thing: the safe
default. ``DefaultDenyEnvelope`` denies *everything* — so a loop that was handed no real
envelope still cannot act. Default-DENY is the floor, everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ── the capability vocabulary ────────────────────────────────────────────────────────
# §5 whitelist: the loop may autonomously do exactly these three — read, graph-inject,
# invent. Everything else is default-DENY. These are the ONLY autonomously-allowed kinds.
class ActionKind:
    READ = "read"                 # §5 읽기 — acquisition / web-mining query / read the graph
    GRAPH_INJECT = "graph_inject"  # §5 그래프주입 — write to the CANDIDATE/STAGING graph (reversible, UNSHIPPED)
    INVENT = "invent"             # §5 발명 — explosion engine invents a new scheme (proposal into staging)
    # Special, NEVER autonomous — a write to the shipped/production graph. The envelope
    # refuses to auto-apply this; it is QUEUED for one morning operator signature (§5).
    PROMOTE_SHIPPED = "promote_shipped"
    # Public posting is a real external side effect. It is intentionally NOT in
    # DEFAULT_WHITELIST; a dedicated, operator-configured envelope must opt in.
    PUBLIC_POST = "public_post"


# The autonomous whitelist. A ``frozenset`` on purpose: the loop cannot widen it at runtime.
DEFAULT_WHITELIST: frozenset[str] = frozenset(
    {ActionKind.READ, ActionKind.GRAPH_INJECT, ActionKind.INVENT}
)

# Kinds that mean "write the shipped graph" — recognised so they can be QUEUED (operator
# signature) rather than blindly denied as unknown. Never autonomously allowed.
SHIPPED_WRITE_KINDS: frozenset[str] = frozenset(
    {ActionKind.PROMOTE_SHIPPED, "shipped_write", "production_write", "promote"}
)


@dataclass(frozen=True)
class EnvelopeAction:
    """A side-effecting request the autonomous loop wants to perform.

    ``kind`` routes it (whitelist / shipped-write / default-deny); ``intent`` + ``payload``
    are the text the moral 0th gate screens for harm. Frozen: an action, once formed, is a
    fixed record of what was requested (so the audit trail cannot be retro-edited in place).
    """

    kind: str
    intent: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def screen_text(self) -> str:
        """The text the moral 0th gate screens: stated intent + a flattened payload view."""
        import json

        return f"{self.intent}\n{json.dumps(self.payload, ensure_ascii=False, sort_keys=True, default=str)}"


@dataclass(frozen=True)
class EnvelopeDecision:
    """The gate's allow/deny answer, with a reason and (when logged) audit proof."""

    allowed: bool
    reason: str
    action_kind: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    audit_seq: int | None = None      # the ledger sequence number this decision was recorded at
    audit_hash: str | None = None     # the hash-chain digest of that record (tamper-evident proof)

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "action_kind": self.action_kind,
            "meta": self.meta,
            "audit_seq": self.audit_seq,
            "audit_hash": self.audit_hash,
        }


@runtime_checkable
class EnvelopeHook(Protocol):
    """The contract the fusion loop calls before every side-effecting action.

    Structural: any object with a matching ``check`` is an ``EnvelopeHook``. ``AutonomyEnvelope``
    implements it; ``fusion_loop`` declares its own copy of this Protocol so neither imports
    the other. The safe implementation DENIES by default and logs every decision.
    """

    def check(self, action: EnvelopeAction) -> EnvelopeDecision:  # pragma: no cover - protocol
        ...


class DefaultDenyEnvelope:
    """The safe fallback: deny EVERYTHING. A loop handed this (or handed nothing and
    falling back to this) cannot take a single action. Used as the floor and in tests to
    prove the default posture is block, never permit."""

    def check(self, action: EnvelopeAction) -> EnvelopeDecision:
        return EnvelopeDecision(
            allowed=False,
            reason="default-deny: no enforcing envelope is wired; the safe failure is to block.",
            action_kind=getattr(action, "kind", ""),
        )
