# -*- coding: utf-8 -*-
"""AutonomyEnvelope — the enforcing envelope-hook the fusion loop calls before every action.

This is the ENFORCING implementation of ``EnvelopeHook`` (``interface.py``). Every side-effecting
step of the fusion loop passes an ``EnvelopeAction`` through ``check`` and only proceeds on
``allowed``. The gate runs, in order, FAIL-CLOSED at each step (the safe failure is to block):

  1. KILLSWITCH   — engaged? => HALT immediately, record the halt, deny. (checked FIRST, always.)
  2. CONSTANTS    — moral-core fingerprint OK *and* frozen-oracle spec seal intact? drift/absence
                    => deny EVERYTHING (fail-closed).
  3. MORAL 0th    — screen this action's intent/payload for harm. violation => deny.
  4. SHIPPED-WRITE— a write to the shipped/production graph is NEVER autonomous => QUEUE it for
                    the morning operator signature and deny ("requires operator signature").
  5. WHITELIST    — kind in the pre-approved set? no => default-DENY, blocked + logged.
  6. ALLOW.

EVERY path — allow or deny — appends a tamper-evident record to the audit ledger, so the whole
night is auditable in the morning.

Two more loop-facing entry points, both audit-logged and killswitch/moral-gated:
  * ``record_question`` — a self-winding (R1) question. Pure cognition, so it is not whitelist-
                          gated, but it is screened by the moral 0th gate and recorded.
  * ``mark_cycle``      — consumes one externally signed, live-context-bound evaluation receipt.
                          Raw scores/evidence are denied; comparable-scope baselines persist.

Scope note: this envelope enforces at the level of the loop's sanctioned action API (cooperative,
in-process). It is not an OS sandbox — see ``README.md`` for the honest boundary and how it is
backstopped (moral core is the fingerprinted spine; genesis_sandbox provides the OS-ish layers).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from packages.autonomy_envelope.audit_ledger import AuditLedger
from packages.autonomy_envelope.constants import FrozenOracle, MoralConstant
from packages.autonomy_envelope.evaluation_trust import (
    EvaluationRatchetStore,
    verify_evaluation_receipt,
)
from packages.autonomy_envelope.interface import (
    DEFAULT_WHITELIST,
    SHIPPED_WRITE_KINDS,
    EnvelopeAction,
    EnvelopeDecision,
)
from packages.autonomy_envelope.killswitch import EnvelopeHalted, Killswitch
from packages.autonomy_envelope.operator_trust import OperatorTrustRoot
from packages.autonomy_envelope.promotion_queue import NightlyPromotionQueue
from packages.autonomy_envelope.whitelist import CapabilityWhitelist

# The sealed identity of the verifier the loop is graded against, if the operator does not
# supply one. It is the frozen IDENTITY of the membrane (conformal + physics-truth + TMS) — the
# envelope holds and seals it; the organ packages run it.
_DEFAULT_ORACLE_SPEC = {
    "verifier": "membrane:conformal+physics_truth+tms",
    "sealed_for": "atanor-autonomy-envelope",
    "grades": ["fluency", "accuracy", "judgment", "fabrication_zero"],
    "wireheading_defense": "frozen; the loop is graded against this and cannot edit it.",
}


class AutonomyEnvelope:
    """The enforcing safety envelope. Compose it, hand it to the loop as the ``EnvelopeHook``."""

    def __init__(
        self,
        root: Path | str,
        *,
        whitelist: Optional[frozenset[str]] = None,
        oracle_spec: Optional[dict[str, Any]] = None,
        baseline_score: float = 0.0,
        evaluation_trust_root: Optional[OperatorTrustRoot] = None,
    ) -> None:
        if type(baseline_score) not in (int, float) or float(baseline_score) != 0.0:
            raise ValueError(
                "unscoped baseline_score is no longer accepted; establish each "
                "comparison baseline with a signed evaluation receipt"
            )
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

        self.killswitch = Killswitch(self.root / "KILLSWITCH")
        self.ledger = AuditLedger(self.root / "audit_ledger.jsonl")
        self.moral = MoralConstant()
        self.oracle = FrozenOracle(dict(oracle_spec) if oracle_spec is not None else dict(_DEFAULT_ORACLE_SPEC))
        if evaluation_trust_root is not None and not isinstance(
            evaluation_trust_root, OperatorTrustRoot
        ):
            raise TypeError("evaluation_trust_root must be an OperatorTrustRoot")
        self.evaluation_trust_root = evaluation_trust_root
        self.evaluation_ratchet = EvaluationRatchetStore(
            self.root,
            oracle_fingerprint=self.oracle.fingerprint,
            trust_root=evaluation_trust_root,
        )
        # Compatibility name only. This now points to the persistent, scope-bound receipt
        # store; it is not the former caller-score arithmetic guard.
        self.no_regression = self.evaluation_ratchet
        self.capabilities = CapabilityWhitelist(frozenset(whitelist) if whitelist is not None else DEFAULT_WHITELIST)
        self.promotions = NightlyPromotionQueue(self.root / "promotions", self.ledger)

    # ── the gate (implements EnvelopeHook.check) ──────────────────────────────────────────
    def check(self, action: EnvelopeAction) -> EnvelopeDecision:
        """The single gate every side-effecting loop action passes through. Default-DENY."""
        kind = getattr(action, "kind", "")

        # 1. KILLSWITCH — first, always. Honored instantly.
        try:
            self.killswitch.require_live()
        except EnvelopeHalted as halt:
            return self._deny(kind, f"HALTED — {halt}", event="killswitch_halt",
                              meta={"killswitch": True})

        # 2. CONSTANTS — inviolable trio integrity. Any drift/absence => deny all (fail-closed).
        integ = self._constants_integrity()
        if integ.get("ok") is not True:
            return self._deny(kind, integ["reason"], event="constants_fail_closed", meta=integ)

        # 3. MORAL 0th — screen this action for harm.
        screen = self._moral_screen(action.screen_text())
        if screen.get("allowed") is not True:
            return self._deny(kind, screen["reason"], event="moral_block",
                              meta={"violations": screen["violations"]})

        # 4. SHIPPED-WRITE — never autonomous. Queue for the morning operator signature.
        if kind in SHIPPED_WRITE_KINDS:
            queued = self.promotions.queue({"item_id": action.payload.get("item_id", ""),
                                            "title": action.intent, **action.payload})
            return self._deny(
                kind,
                "shipped-graph write is NEVER autonomous — QUEUED for the morning operator "
                "signature (nothing hits the shipped graph unsigned).",
                event="promotion_queued_deny",
                meta={"queued_item_id": queued["item_id"], "pending": self.promotions.pending_count()},
            )

        # 5. WHITELIST — default-DENY anything not explicitly pre-approved.
        if not self.capabilities.permits(kind):
            return self._deny(kind, self.capabilities.default_deny_reason(kind),
                              event="blocked_out_of_whitelist",
                              meta={"whitelist": sorted(self.capabilities.allowed)})

        # 6. ALLOW — whitelisted, moral-clean, constants intact, killswitch clear.
        return self._allow(kind, action.intent)

    # ── loop-facing: self-winding question (R1) ───────────────────────────────────────────
    def record_question(self, text: str) -> EnvelopeDecision:
        """Record a self-winding question. Cognition (not whitelist-gated) but killswitch- and
        moral-gated, and always written to the audit ledger."""
        try:
            self.killswitch.require_live()
        except EnvelopeHalted as halt:
            return self._deny("self_wind", f"HALTED — {halt}", event="killswitch_halt",
                              meta={"killswitch": True, "question": text[:200]})
        integ = self._constants_integrity()
        if integ.get("ok") is not True:
            return self._deny("self_wind", integ["reason"], event="constants_fail_closed", meta=integ)
        screen = self._moral_screen(text)
        if screen.get("allowed") is not True:
            return self._deny("self_wind", screen["reason"], event="moral_block",
                              meta={"violations": screen["violations"], "question": text[:200]})
        rec = self.ledger.append("self_wind_question", {"question": text[:2000]})
        return EnvelopeDecision(allowed=True, reason="self-winding question recorded",
                                action_kind="self_wind", audit_seq=rec["seq"], audit_hash=rec["hash"])

    # ── loop-facing: externally attested no-regression per cycle ────────────────────────────
    def mark_cycle(
        self,
        receipt: Any,
        *,
        live_context: Optional[Mapping[str, Any]] = None,
        evidence: Optional[dict[str, Any]] = None,
    ) -> EnvelopeDecision:
        """Consume a signed external evaluation receipt and ratchet its comparison scope.

        A local ``FrozenOracle`` seals only the evaluator specification. Consequently a numeric
        score, an arbitrary evidence dictionary, an unsigned result, or a missing external trust
        root is always denied and can never change a baseline.
        """
        try:
            self.killswitch.require_live()
        except EnvelopeHalted as halt:
            return self._deny("cycle", f"HALTED — {halt}", event="killswitch_halt", meta={"killswitch": True})
        integ = self._constants_integrity()
        if integ.get("ok") is not True:
            return self._deny(
                "cycle",
                integ["reason"],
                event="constants_fail_closed",
                meta=integ,
            )
        if self.evaluation_trust_root is None:
            return self._deny(
                "cycle",
                "external evaluation authority is not configured; raw/local scores cannot ratchet",
                event="evaluation_authority_missing",
                meta={
                    "external_evaluator_configured": False,
                    "oracle_spec_integrity_ok": integ["oracle"].get("ok") is True,
                },
            )
        if evidence is not None or not isinstance(receipt, Mapping):
            return self._deny(
                "cycle",
                "raw score/evidence rejected; an exact signed evaluation receipt is required",
                event="evaluation_receipt_rejected",
                meta={"reason_code": "raw_score_or_evidence_rejected"},
            )
        try:
            verified = verify_evaluation_receipt(
                receipt,
                trust_root=self.evaluation_trust_root,
                live_context=live_context,
                live_oracle_fingerprint=self.oracle.fingerprint,
            )
        except Exception as exc:
            return self._deny(
                "cycle",
                "external evaluation verifier unavailable; failing CLOSED",
                event="evaluation_receipt_rejected",
                meta={
                    "reason_code": "evaluation_verifier_error",
                    "error": type(exc).__name__,
                },
            )
        if verified.ok is not True:
            return self._deny(
                "cycle",
                f"external evaluation receipt rejected: {verified.reason}",
                event="evaluation_receipt_rejected",
                meta=verified.to_dict(),
            )
        ratchet = self.evaluation_ratchet.apply(
            receipt=receipt,
            live_context=live_context,
        )
        meta = {
            "receipt_payload_sha256": verified.payload_sha256,
            "evaluator_key_id": verified.key_id,
            "run_id": verified.run_id,
            "scope_id": ratchet.scope_id,
            "score": ratchet.score,
            "baseline_before": ratchet.baseline_before,
            "baseline_after": ratchet.baseline_after,
        }
        if ratchet.allowed is not True:
            event = (
                "cycle_regression_blocked"
                if ratchet.reason == "evaluation_regression_blocked"
                else "evaluation_receipt_rejected"
            )
            rec = self.ledger.append(event, {**meta, "reason_code": ratchet.reason})
            return EnvelopeDecision(
                allowed=False,
                reason=ratchet.reason,
                action_kind="cycle",
                meta=meta,
                audit_seq=rec["seq"],
                audit_hash=rec["hash"],
            )
        rec = self.ledger.append("cycle_ok", meta)
        return EnvelopeDecision(
            allowed=True,
            reason="externally attested cycle holds the comparable-scope baseline",
            action_kind="cycle",
            meta=meta,
            audit_seq=rec["seq"],
            audit_hash=rec["hash"],
        )

    # ── operator-facing: sign the nightly promotion batch ─────────────────────────────────
    def sign_promotion_batch(self, *, operator_confirmed: bool, confirmation_phrase: str,
                             operator_id: str = "operator",
                             item_id: str | None = None) -> dict[str, Any]:
        """Morning operator action. Default-deny; exact phrase + confirmed => signed staged
        manifest. Never mutates the shipped/production graph."""
        return self.promotions.sign_batch(operator_confirmed=operator_confirmed,
                                          confirmation_phrase=confirmation_phrase,
                                          operator_id=operator_id,
                                          item_id=item_id)

    # ── introspection ─────────────────────────────────────────────────────────────────────
    def _constants_integrity(self) -> dict[str, Any]:
        try:
            moral = self.moral.verify_integrity()
        except Exception as exc:
            moral = {
                "ok": False,
                "reason": "moral verifier unavailable; failing CLOSED.",
                "error": type(exc).__name__,
            }
        try:
            oracle = self.oracle.verify_integrity()
        except Exception as exc:
            oracle = {
                "ok": False,
                "reason": "frozen oracle verifier unavailable; failing CLOSED.",
                "error": type(exc).__name__,
            }
        if not isinstance(moral, dict):
            moral = {"ok": False, "reason": "malformed moral integrity verdict"}
        if not isinstance(oracle, dict):
            oracle = {"ok": False, "reason": "malformed oracle integrity verdict"}
        ok = moral.get("ok") is True and oracle.get("ok") is True
        reason = "constants intact"
        if moral.get("ok") is not True:
            reason = f"CONSTANTS fail-closed (moral): {moral.get('reason', 'invalid verdict')}"
        elif oracle.get("ok") is not True:
            reason = f"CONSTANTS fail-closed (frozen oracle): {oracle.get('reason', 'invalid verdict')}"
        return {"ok": ok, "reason": reason, "moral": moral, "oracle": oracle}

    def _moral_screen(self, text: str) -> dict[str, Any]:
        """Normalize all malformed or exceptional screen outcomes to an explicit deny."""
        try:
            screen = self.moral.screen(text)
        except Exception as exc:
            return {
                "allowed": False,
                "violations": ["moral_screen_unavailable"],
                "reason": "moral screen unavailable; failing CLOSED.",
                "error": type(exc).__name__,
            }
        if not isinstance(screen, dict):
            return {
                "allowed": False,
                "violations": ["malformed_moral_screen_verdict"],
                "reason": "moral screen returned a malformed verdict; failing CLOSED.",
            }
        violations = screen.get("violations")
        clean_allow = (
            screen.get("allowed") is True
            and screen.get("integrity_ok") is True
            and violations == []
        )
        if not clean_allow:
            violations = screen.get("violations")
            if not isinstance(violations, list) or not violations:
                violations = ["moral_screen_rejected_or_malformed"]
            return {
                **screen,
                "allowed": False,
                "violations": violations,
                "reason": str(
                    screen.get("reason")
                    or "moral screen verdict was rejected or internally inconsistent"
                ),
            }
        return {
            **screen,
            "allowed": True,
            "violations": [],
            "integrity_ok": True,
        }

    def status(self) -> dict[str, Any]:
        ch_ok, ch_bad = self.ledger.verify_chain()
        integ = self._constants_integrity()
        evaluation = self.evaluation_ratchet.status()
        evaluator_configured = self.evaluation_trust_root is not None
        return {
            "root": str(self.root),
            "killswitch_engaged": self.killswitch.is_engaged(),
            "whitelist": sorted(self.capabilities.allowed),
            "constants_ok": integ["ok"],
            "moral_source": integ["moral"].get("source"),
            "moral_inviolable": self.moral.is_inviolable(),
            "oracle_inviolable": self.oracle.is_inviolable(),
            "oracle_fingerprint": self.oracle.fingerprint,
            "oracle_spec_integrity_ok": integ["oracle"].get("ok") is True,
            "external_evaluator_configured": evaluator_configured,
            "external_evaluator_key_id": (
                self.evaluation_trust_root.key_id if evaluator_configured else None
            ),
            "evaluation_authority_ready": (
                evaluator_configured
                and integ.get("ok") is True
                and evaluation["state_ok"] is True
            ),
            "evaluation_state_ok": evaluation["state_ok"],
            "evaluation_state_error": evaluation["state_error"],
            "evaluation_scope_count": evaluation["scope_count"],
            "evaluation_baselines": evaluation["baselines"],
            "evaluation_consumed_nonce_count": evaluation["consumed_nonce_count"],
            "baseline": self.evaluation_ratchet.baseline,
            "audit_records": self.ledger.count(),
            "audit_chain_ok": ch_ok,
            "audit_first_bad_seq": ch_bad,
            "pending_promotions": self.promotions.pending_count(),
        }

    # ── internal helpers ──────────────────────────────────────────────────────────────────
    def _allow(self, kind: str, intent: str) -> EnvelopeDecision:
        rec = self.ledger.append("action_allowed", {"kind": kind, "intent": intent[:500]})
        return EnvelopeDecision(allowed=True, reason=f"allowed: {kind} is pre-approved and clean.",
                                action_kind=kind, audit_seq=rec["seq"], audit_hash=rec["hash"])

    def _deny(self, kind: str, reason: str, *, event: str, meta: Optional[dict[str, Any]] = None) -> EnvelopeDecision:
        payload = {"kind": kind, "reason": reason}
        if meta:
            payload.update(meta)
        rec = self.ledger.append(event, payload)
        return EnvelopeDecision(allowed=False, reason=reason, action_kind=kind, meta=meta or {},
                                audit_seq=rec["seq"], audit_hash=rec["hash"])
