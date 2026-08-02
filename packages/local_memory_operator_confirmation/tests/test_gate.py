from __future__ import annotations

from packages.local_memory_operator_confirmation.gate import evaluate_confirmation_gate
from packages.local_memory_operator_confirmation.models import OperatorConfirmationDecision, OperatorConfirmationRequest
from packages.local_memory_operator_confirmation.validator import default_safety_requirements


def _request() -> OperatorConfirmationRequest:
    return OperatorConfirmationRequest(
        request_id="operator_confirmation_test",
        source_memory_manifest_id="manifest",
        source_write_plan_id="plan",
        source_sandbox_transaction_id="sandbox",
        local_brain_hash_before=None,
        required_phrase="PHRASE",
        risk_summary=[],
        safety_requirements=default_safety_requirements(),
        created_at="2026-01-01T00:00:00Z",
        expires_at=None,
        status="pending_confirmation",
    )


def test_gate_requires_decision() -> None:
    result = evaluate_confirmation_gate(_request())

    assert result.allowed_to_prepare_real_write is False
    assert "operator_confirmation_required" in result.reasons
    assert result.allowed_to_apply_real_write is False


def test_gate_allows_preparation_only_after_matching_confirm() -> None:
    decision = OperatorConfirmationDecision(
        decision_id="decision",
        request_id="operator_confirmation_test",
        decision="confirm",
        typed_phrase="PHRASE",
        phrase_matches=True,
    )
    result = evaluate_confirmation_gate(_request(), decision)

    assert result.allowed_to_prepare_real_write is True
    assert result.allowed_to_apply_real_write is False
    assert result.apply_enabled is False
    assert result.local_brain_write is False


def test_gate_blocks_wrong_phrase() -> None:
    decision = OperatorConfirmationDecision(
        decision_id="decision",
        request_id="operator_confirmation_test",
        decision="confirm",
        typed_phrase="WRONG",
        phrase_matches=False,
    )
    result = evaluate_confirmation_gate(_request(), decision)

    assert result.allowed_to_prepare_real_write is False
    assert "required_phrase_mismatch" in result.reasons
