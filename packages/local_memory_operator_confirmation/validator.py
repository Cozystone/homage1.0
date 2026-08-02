from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .models import OperatorConfirmationRequest


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_expired(expires_at: str | None, *, now: datetime | None = None) -> bool:
    expiry = _parse_time(expires_at)
    if expiry is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current >= expiry


def default_safety_requirements() -> dict[str, Any]:
    return {
        "real_local_brain_write": False,
        "real_local_brain_mutated": False,
        "memory_apply_enabled": False,
        "operator_confirmation_required": True,
        "operator_confirmation_recorded": False,
        "backup_plan_required": True,
        "rollback_plan_required": True,
        "sandbox_transaction_required": True,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "external_llm_used": False,
        "real_p2p_used": False,
        "generated_code_executed": False,
        "requires_user_approval": True,
        "text_input_supported": True,
        "voice_optional": True,
    }


@dataclass(frozen=True)
class PreconditionsValidation:
    valid: bool
    errors: list[str]
    warnings: list[str]
    safety_requirements: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "safety_requirements": dict(self.safety_requirements),
            "apply_enabled": False,
            "local_brain_write": False,
            "allowed_to_apply_real_write": False,
        }


def validate_preconditions(
    *,
    memory_manifest_id: str | None,
    write_plan_id: str | None,
    backup_plan_id: str | None,
    rollback_plan_id: str | None,
    sandbox_transaction_id: str | None,
    sandbox_transaction_deferred: bool = False,
    sensitive_raw_write_absent: bool = True,
    raw_voice_write_absent: bool = True,
    apply_enabled: bool = False,
    local_brain_write: bool = False,
    user_approval_decisions_exist: bool = True,
    expires_at: str | None = None,
    now: datetime | None = None,
) -> PreconditionsValidation:
    errors: list[str] = []
    warnings: list[str] = []
    safety = default_safety_requirements()

    if not memory_manifest_id:
        errors.append("memory_manifest_required")
    if not write_plan_id:
        errors.append("write_plan_required")
    if not backup_plan_id:
        errors.append("backup_plan_required")
    if not rollback_plan_id:
        errors.append("rollback_plan_required")
    if not sandbox_transaction_id:
        if sandbox_transaction_deferred:
            warnings.append("sandbox_transaction_proof_deferred")
        else:
            errors.append("sandbox_transaction_proof_required")
    if not sensitive_raw_write_absent:
        errors.append("sensitive_raw_write_must_be_absent")
    if not raw_voice_write_absent:
        errors.append("raw_voice_write_must_be_absent")
    if apply_enabled:
        errors.append("apply_enabled_must_be_false")
    if local_brain_write:
        errors.append("local_brain_write_must_be_false")
    if not user_approval_decisions_exist:
        errors.append("user_approval_decisions_required")
    if is_expired(expires_at, now=now):
        errors.append("operator_confirmation_request_expired")

    return PreconditionsValidation(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        safety_requirements=safety,
    )


def validate_request_not_expired(request: OperatorConfirmationRequest, *, now: datetime | None = None) -> PreconditionsValidation:
    return validate_preconditions(
        memory_manifest_id=request.source_memory_manifest_id,
        write_plan_id=request.source_write_plan_id,
        backup_plan_id=str(request.safety_requirements.get("backup_plan_id") or ""),
        rollback_plan_id=str(request.safety_requirements.get("rollback_plan_id") or ""),
        sandbox_transaction_id=request.source_sandbox_transaction_id,
        sensitive_raw_write_absent=True,
        raw_voice_write_absent=True,
        apply_enabled=False,
        local_brain_write=False,
        user_approval_decisions_exist=True,
        expires_at=request.expires_at,
        now=now,
    )
