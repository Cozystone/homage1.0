from __future__ import annotations

from .models import OperatorConfirmationDecision, OperatorConfirmationGateResult, OperatorConfirmationRequest
from .validator import is_expired


NEXT_GATES = [
    "real_local_brain_backup",
    "rollback_verified",
    "transaction_lock",
    "final_operator_confirmation",
    "audit_log",
    "local_only_write_transaction",
]


def evaluate_confirmation_gate(
    request: OperatorConfirmationRequest,
    decision: OperatorConfirmationDecision | None = None,
) -> OperatorConfirmationGateResult:
    reasons: list[str] = []
    if request.status == "blocked":
        reasons.append("request_blocked")
    if request.status == "expired" or is_expired(request.expires_at):
        reasons.append("request_expired")
    if decision is None:
        reasons.append("operator_confirmation_required")
    elif decision.decision != "confirm":
        reasons.append(f"operator_decision_{decision.decision}")
    elif not decision.phrase_matches:
        reasons.append("required_phrase_mismatch")

    allowed_prepare = not reasons and decision is not None and decision.decision == "confirm" and decision.phrase_matches
    if allowed_prepare:
        reasons.append("operator_confirmed_preparation_only")

    return OperatorConfirmationGateResult(
        request_id=request.request_id,
        allowed_to_prepare_real_write=allowed_prepare,
        allowed_to_apply_real_write=False,
        apply_enabled=False,
        local_brain_write=False,
        reasons=reasons,
        required_next_gates=list(NEXT_GATES),
    )
