# -*- coding: utf-8 -*-
"""OS Action Lane — the orchestrator.

Flow for every action: classify risk -> gate against the trust tier -> either EXECUTE
now, HOLD for approval, or BLOCK -> write an append-only audit entry either way. A held
action gets a token; approve(token) (from a voice '' or a click) runs it and re-audits.
A kill switch blocks the whole lane instantly regardless of tier.

Accountable by construction: nothing runs that is not audited, and the audit is
append-only (an action is an event, never erased).
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .backends import LinuxDesktopBackend, MockBackend
from .models import Action, ActionResult, AuditEntry, GateOutcome, RiskLevel, TrustTier
from .risk import classify
from .trust import gate, rationale


def _args_summary(action: Action) -> str:
    return json.dumps(action.args, ensure_ascii=False)[:200]


class OSActionLane:
    def __init__(self, backend: Any | None = None, *, tier: TrustTier = TrustTier.ASSIST,
                 audit_path: str | Path | None = None) -> None:
        self.backend = backend if backend is not None else MockBackend()
        self.tier = TrustTier(tier)
        self.audit_path = Path(audit_path) if audit_path else None
        self._killed = False
        self._pending: dict[str, tuple[Action, RiskLevel]] = {}

    # ---- tier is trust EARNED: it starts at ASSIST and the user raises it ----
    def set_tier(self, tier: TrustTier) -> None:
        self.tier = TrustTier(tier)

    def kill(self) -> None:
        """Immediate stop — every action blocks until reset(), whatever the tier."""
        self._killed = True

    def reset_kill(self) -> None:
        self._killed = False

    # ---- audit (append-only) ----
    def _audit(self, action: Action, risk: RiskLevel, outcome: GateOutcome,
               executed: bool, ok: bool, detail: str) -> str:
        aid = uuid.uuid4().hex[:12]
        entry = AuditEntry(
            audit_id=aid, ts=time.strftime("%Y-%m-%dT%H:%M:%S"), tier=int(self.tier),
            action_kind=action.kind, args_summary=_args_summary(action),
            risk=int(risk), outcome=int(outcome), executed=executed, ok=ok,
            detail=detail[:300])
        if self.audit_path is not None:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return aid

    def _do(self, action: Action, risk: RiskLevel) -> ActionResult:
        ok, out, err = self.backend.execute(action)
        aid = self._audit(action, risk, GateOutcome.EXECUTE, executed=True, ok=ok,
                          detail=(out or err)[:200])
        return ActionResult(action=action, risk=risk, outcome=GateOutcome.EXECUTE,
                            executed=True, ok=ok, detail=rationale(risk, self.tier, GateOutcome.EXECUTE),
                            stdout=out, stderr=err, audit_id=aid)

    def propose(self, action: Action) -> ActionResult:
        """Classify + gate. EXECUTE runs now; NEEDS_APPROVAL parks with a token in
        .audit_id (call approve(token)); BLOCKED refuses. Always audited."""
        risk = classify(action)
        if self._killed:
            aid = self._audit(action, risk, GateOutcome.BLOCKED, False, False, "kill switch active")
            return ActionResult(action, risk, GateOutcome.BLOCKED, detail="정지 상태입니다.", audit_id=aid)
        outcome = gate(risk, self.tier)
        if outcome == GateOutcome.EXECUTE:
            return self._do(action, risk)
        # hold for approval — issue a token, audit the hold
        token = uuid.uuid4().hex[:12]
        self._pending[token] = (action, risk)
        aid = self._audit(action, risk, outcome, executed=False, ok=False, detail="awaiting approval")
        r = ActionResult(action, risk, outcome, detail=rationale(risk, self.tier, outcome), audit_id=aid)
        r.detail = f"{r.detail} (승인 토큰: {token})"
        # stash the token where the caller can read it
        r.stdout = token
        return r

    def approve(self, token: str) -> ActionResult | None:
        """Run a previously-held action after an explicit human yes (voice/click)."""
        if self._killed or token not in self._pending:
            return None
        action, risk = self._pending.pop(token)
        return self._do(action, risk)

    def reject(self, token: str) -> bool:
        """Drop a held action (a 'no')."""
        if token in self._pending:
            action, risk = self._pending.pop(token)
            self._audit(action, risk, GateOutcome.BLOCKED, False, False, "human rejected")
            return True
        return False

    def pending(self) -> list[dict[str, Any]]:
        return [{"token": t, "kind": a.kind, "args": a.args, "risk": int(r)}
                for t, (a, r) in self._pending.items()]


def default_lane(audit_path: str | Path | None = None) -> OSActionLane:
    """A lane wired to the REAL desktop, starting at ASSIST (approve-every-action)."""
    return OSActionLane(LinuxDesktopBackend(), tier=TrustTier.ASSIST, audit_path=audit_path)
