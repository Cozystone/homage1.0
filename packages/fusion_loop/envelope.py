# -*- coding: utf-8 -*-
"""The envelope-hook INTERFACE — the single gate the fusion loop consults before EVERY
side-effecting action (acquire / graph-inject / queue-promote / invent-promote / voice /
recipe-record / shared-bank-promote).

Why an interface (and not an import of the enforcing envelope): F1 is a CONTROLLED closed-loop
test, not live unsupervised operation (that is F3). The loop must run end-to-end today WITHOUT the
safety envelope wired, yet be ready to have the enforcing envelope dropped in with zero loop
changes. So the loop depends on this Protocol only; the DEFAULT is a permissive no-op that allows
everything (the controlled-test posture). Agent #85 builds the ENFORCING envelope
(``packages/autonomy_envelope``) implementing this SAME ``EnvelopeHook`` Protocol — the two are
decoupled through the interface here, and this package NEVER imports #85's package.

The contract is deliberately tiny and pure: ``authorize(action) -> EnvelopeDecision``. An action
carries its kind, a topic, a JSON-safe payload, and (when the action enshrines) the membrane
certificate that backs it — so an enforcing envelope can make its decision on the SAME evidence the
membrane saw, without re-deriving anything.

No-LLM, stdlib only, no I/O. This module is the seam, nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# The exhaustive set of side-effecting action kinds the loop can take. An enforcing envelope keys
# its whitelist on these; the permissive default ignores them (allows all). Kept as plain strings
# (not an enum) so #85's package can extend the vocabulary without a shared import.
ACTION_KINDS: tuple[str, ...] = (
    "acquire",              # mine evidence for a gap (read-only web / fixture)
    "graph_inject",         # write a consensus-verified fact into a (scratch) store
    "queue_promote",        # enqueue a verified fact for operator-signed promotion
    "voice",                # emit a grounded utterance (the [known?] branch)
    "invent_promote",       # promote a re-executed invented scheme into the working basis
    "recipe_record",        # record a verified recipe into the flywheel ledger
    "shared_bank_promote",  # operator-signed promotion into the SHARED recipe bank (default-off in F1)
)


@dataclass(frozen=True)
class EnvelopeAction:
    """One side-effecting request the loop is ABOUT to perform. Immutable + JSON-safe so it can be
    logged into an audit trail verbatim. ``membrane_certificate`` is attached for enshrining actions
    (graph_inject / queue_promote / invent_promote / recipe_record / voice) — it is the membrane's
    own certificate, the evidence an enforcing envelope may re-check."""
    kind: str
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    membrane_certificate: dict[str, Any] | None = None


@dataclass(frozen=True)
class EnvelopeDecision:
    """The verdict. ``allowed`` gates the action; ``reason`` is a human-readable audit string;
    ``hook`` names the implementation that decided (so a trace shows WHICH envelope was in force)."""
    allowed: bool
    reason: str
    hook: str = "unnamed"


@runtime_checkable
class EnvelopeHook(Protocol):
    """The one method the loop calls before every side effect. An implementation returns an
    ``EnvelopeDecision``; the loop performs the action IFF ``allowed`` is True, and records the
    decision either way. Pure/synchronous by contract (no network, no prompt) so the controlled
    test is deterministic."""

    def authorize(self, action: EnvelopeAction) -> EnvelopeDecision:
        ...


class PermissiveEnvelope:
    """The permissive no-op DEFAULT — allows every action so F1 runs as a controlled closed-loop
    test. This is NOT the safety envelope; it is the explicit "no envelope in force" posture that
    lets the loop's own membrane + moral 0th gate be measured in isolation. Swapping in agent #85's
    enforcing envelope (same Protocol) is a one-line change at the call site."""

    name = "permissive-noop"

    def authorize(self, action: EnvelopeAction) -> EnvelopeDecision:
        return EnvelopeDecision(
            allowed=True,
            reason=f"permissive no-op default (F1 controlled test): {action.kind} allowed",
            hook=self.name,
        )


class RecordingEnvelope:
    """A test/audit wrapper: delegates the decision to an inner hook (default permissive) and
    RECORDS every action it was consulted on, in order. Used by the sealed gate to prove the loop
    consults the envelope BEFORE each side effect (the enforcement point exists and is exercised),
    without changing behavior. Not a security control — an instrument."""

    name = "recording"

    def __init__(self, inner: EnvelopeHook | None = None):
        self.inner: EnvelopeHook = inner or PermissiveEnvelope()
        self.calls: list[EnvelopeAction] = []
        self.decisions: list[EnvelopeDecision] = []

    def authorize(self, action: EnvelopeAction) -> EnvelopeDecision:
        self.calls.append(action)
        d = self.inner.authorize(action)
        self.decisions.append(d)
        return d

    def kinds(self) -> list[str]:
        return [a.kind for a in self.calls]


class DenyKindsEnvelope:
    """An envelope that DENIES a named set of action kinds and allows the rest — a minimal enforcing
    stand-in used by the sealed gate to prove the enforcement point BITES: a denied side effect is
    genuinely not performed (nothing enshrined for it). This demonstrates the interface is a real
    gate, not decoration, while remaining independent of agent #85's package."""

    name = "deny-kinds"

    def __init__(self, deny: set[str]):
        self.deny = set(deny)

    def authorize(self, action: EnvelopeAction) -> EnvelopeDecision:
        if action.kind in self.deny:
            return EnvelopeDecision(False, f"action kind '{action.kind}' denied by envelope whitelist",
                                    self.name)
        return EnvelopeDecision(True, f"action kind '{action.kind}' permitted", self.name)
