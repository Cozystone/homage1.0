from __future__ import annotations

import pytest

from packages.local_memory_operator_confirmation.models import (
    OperatorConfirmationDecision,
    OperatorConfirmationGateResult,
    OperatorConfirmationRequest,
)
from packages.local_memory_operator_confirmation.validator import default_safety_requirements


def test_request_requires_safety_locks() -> None:
    safety = default_safety_requirements()
    request = OperatorConfirmationRequest(
        request_id="operator_confirmation_test",
        source_memory_manifest_id="manifest",
        source_write_plan_id="plan",
        source_sandbox_transaction_id="sandbox",
        local_brain_hash_before="hash",
        required_phrase="I UNDERSTAND LOCAL BRAIN WRITE PREPARATION ABC",
        risk_summary=["preparation only"],
        safety_requirements=safety,
        created_at="2026-01-01T00:00:00Z",
        expires_at=None,
        status="pending_confirmation",
    )

    assert request.safety_requirements["real_local_brain_write"] is False
    assert request.safety_requirements["memory_apply_enabled"] is False


def test_request_rejects_apply_enabled_safety() -> None:
    safety = default_safety_requirements()
    safety["memory_apply_enabled"] = True

    with pytest.raises(ValueError, match="memory_apply_enabled"):
        OperatorConfirmationRequest(
            request_id="operator_confirmation_test",
            source_memory_manifest_id="manifest",
            source_write_plan_id="plan",
            source_sandbox_transaction_id="sandbox",
            local_brain_hash_before=None,
            required_phrase="phrase",
            risk_summary=[],
            safety_requirements=safety,
            created_at="2026-01-01T00:00:00Z",
            expires_at=None,
        )


def test_gate_result_cannot_enable_real_apply() -> None:
    with pytest.raises(ValueError, match="never enables real apply"):
        OperatorConfirmationGateResult(
            request_id="operator_confirmation_test",
            allowed_to_prepare_real_write=True,
            allowed_to_apply_real_write=True,
            reasons=[],
            required_next_gates=[],
        )


def test_confirm_decision_requires_phrase() -> None:
    with pytest.raises(ValueError, match="typed_phrase"):
        OperatorConfirmationDecision(
            decision_id="decision",
            request_id="request",
            decision="confirm",
            typed_phrase=None,
            phrase_matches=False,
        )
