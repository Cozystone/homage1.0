# -*- coding: utf-8 -*-
"""The INTERFACE ADAPTER — drives F1's loop through F5's real enforcing envelope.

F1's loop (``packages.fusion_loop.loop.FusionLoop``) calls an envelope hook shaped like
``authorize(EnvelopeAction) -> EnvelopeDecision`` before every side effect (``.envelope`` here).
F5's enforcing envelope (``packages.autonomy_envelope.AutonomyEnvelope``) exposes a DIFFERENT
shape — ``check(EnvelopeAction) -> EnvelopeDecision`` — with a different action vocabulary and a
richer decision. The two packages were built decoupled ON PURPOSE and never import each other
(F1's ``envelope.py`` docstring; F5's ``interface.py`` docstring). This adapter is the seam that
lets F1's loop run under F5's *real* gate with ZERO changes to either package.

What diverged, and how this reconciles it (F1 side -> F5 side):
  * METHOD    : ``authorize`` -> ``check``.
  * ACTION    : F1 ``EnvelopeAction(kind, topic, payload, membrane_certificate)``
                -> F5 ``EnvelopeAction(kind, intent, payload)``. ``topic`` becomes ``intent``
                (what F5's moral 0th gate screens); the membrane certificate + the original F1
                kind are folded into ``payload`` so F5's audit ledger records the SAME evidence
                and provenance the membrane saw.
  * KIND      : F1's seven action kinds map onto F5's capability vocabulary by EFFECT-PRIVILEGE
                (``KIND_MAP`` below). An F1 kind the map does not know is forwarded VERBATIM so
                F5's default-DENY whitelist decides it (the adapter never invents a permission).
  * DECISION  : F5 ``EnvelopeDecision(allowed, reason, action_kind, meta, audit_seq, audit_hash)``
                -> F1 ``EnvelopeDecision(allowed, reason, hook)``. ``allowed`` is forwarded
                VERBATIM (allow AND deny), the reason is annotated with the mapping + audit seq,
                and the richer F5 fields (audit seq/hash, event, mapped kind) are kept in
                ``self.decisions`` for the run trace (F1's decision shape cannot carry them).

The adapter is FAITHFUL: it forwards allow and deny exactly as F5 decides — it can only ever make
an action *more* restricted (an unknown kind forwards to default-DENY), never less. It also
notices F5's killswitch-halt verdict and raises ``self.halted`` so a driver can stop the loop.

No-LLM, stdlib only. Imports F5 read-only (never edits it); the loop imports this, not F5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from packages.autonomy_envelope.interface import (
    ActionKind,
    EnvelopeAction as F5Action,
    EnvelopeDecision as F5Decision,
)

from .envelope import EnvelopeAction as F1Action, EnvelopeDecision as F1Decision


class _Checker(Protocol):
    """The one method the adapter needs from F5's side — ``AutonomyEnvelope`` satisfies it
    structurally (and so does any test double). The adapter depends on THIS, not on the concrete
    ``AutonomyEnvelope`` class, so it stays decoupled and unit-testable with a fake."""

    def check(self, action: F5Action) -> F5Decision:  # pragma: no cover - protocol
        ...


# ── the kind map: F1's action vocabulary -> F5's capability vocabulary, by effect-privilege ──────
# F5's autonomous whitelist is exactly {read, graph_inject, invent}; a shipped-graph write is never
# autonomous and is QUEUED for the morning operator signature (§5). Each F1 action maps to the F5
# capability whose PRIVILEGE matches its real effect:
#   * acquire / voice   -> read          : lowest-privilege side effects — mine offline evidence,
#                                           or emit already-membrane-certified state. No graph
#                                           mutation, no invention, no persistence to a shipped store.
#   * graph_inject      -> graph_inject  : a reversible write to the candidate/staging graph.
#   * recipe_record     -> graph_inject  : a reversible, unshipped local staging write (flywheel
#                                           ledger) — same privilege tier as a staging graph write.
#   * invent_promote    -> invent        : the explosion engine proposes a new scheme into staging.
#   * queue_promote /   -> promote_shipped: nominates a fact/recipe for the SHIPPED graph -> F5
#     shared_bank_promote                  QUEUES it for one operator signature; never autonomous.
KIND_MAP: dict[str, str] = {
    "acquire": ActionKind.READ,
    "voice": ActionKind.READ,
    "graph_inject": ActionKind.GRAPH_INJECT,
    "recipe_record": ActionKind.GRAPH_INJECT,
    "invent_promote": ActionKind.INVENT,
    "queue_promote": ActionKind.PROMOTE_SHIPPED,
    "shared_bank_promote": ActionKind.PROMOTE_SHIPPED,
}


@dataclass
class AdapterDecision:
    """One adapter forwarding, kept for the run trace (F1's decision shape cannot hold the audit
    seq/hash or the mapped kind)."""
    f1_kind: str
    f5_kind: str
    topic: str
    allowed: bool
    reason: str
    audit_seq: int | None = None
    audit_hash: str | None = None
    killswitch_halt: bool = False


class EnvelopeAdapter:
    """Presents F5's ``AutonomyEnvelope`` (or any object with ``check``) as an F1 ``EnvelopeHook``.

    Hand it to ``FusionLoop(envelope=...)`` and the loop's every side effect is gated by the real
    enforcing envelope. Satisfies F1's ``EnvelopeHook`` Protocol (it has ``authorize``)."""

    def __init__(self, inner: _Checker, *, name: str = "autonomy-envelope-adapter",
                 kind_map: dict[str, str] | None = None):
        self.inner = inner
        self.name = name
        self.kind_map = dict(kind_map) if kind_map is not None else dict(KIND_MAP)
        self.decisions: list[AdapterDecision] = []
        self.halted: bool = False

    # F1's ``EnvelopeHook`` contract -----------------------------------------------------------
    def authorize(self, action: F1Action) -> F1Decision:
        """Translate F1's request into F5's, consult F5's real gate, and translate the verdict
        back — forwarding allow AND deny exactly as F5 decided."""
        f5_kind = self.map_kind(action.kind)

        # Fold the membrane certificate + the original F1 kind into the payload so F5's audit
        # ledger and moral 0th screen see the SAME evidence and provenance (F5 keys nothing on
        # these extra fields; they are recorded, not acted on — the mapped kind is what routes).
        payload: dict[str, Any] = dict(action.payload or {})
        payload["_f1_kind"] = action.kind
        if action.membrane_certificate is not None:
            payload["_membrane_certificate"] = action.membrane_certificate

        f5_action = F5Action(kind=f5_kind, intent=action.topic or "", payload=payload)
        verdict = self.inner.check(f5_action)

        killswitch = bool((verdict.meta or {}).get("killswitch"))
        if killswitch:
            # F5 honored an engaged killswitch at this check — remember it so a driver can stop.
            self.halted = True

        self.decisions.append(AdapterDecision(
            f1_kind=action.kind, f5_kind=f5_kind, topic=action.topic or "",
            allowed=bool(verdict.allowed), reason=verdict.reason,
            audit_seq=verdict.audit_seq, audit_hash=verdict.audit_hash,
            killswitch_halt=killswitch,
        ))

        seq = f"; audit seq={verdict.audit_seq}" if verdict.audit_seq is not None else ""
        return F1Decision(
            allowed=bool(verdict.allowed),
            reason=f"[{self.name}: {action.kind}->{f5_kind}] {verdict.reason}{seq}",
            hook=self.name,
        )

    # helpers ----------------------------------------------------------------------------------
    def map_kind(self, f1_kind: str) -> str:
        """F1 kind -> F5 kind. Unknown kinds forward VERBATIM so F5's default-DENY whitelist
        decides them; the adapter never fabricates a permission."""
        return self.kind_map.get(f1_kind, f1_kind)

    def allowed_kinds(self) -> list[str]:
        return [d.f5_kind for d in self.decisions if d.allowed]

    def denied(self) -> list[AdapterDecision]:
        return [d for d in self.decisions if not d.allowed]
