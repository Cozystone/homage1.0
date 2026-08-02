from __future__ import annotations

from packages.local_memory_approval.models import MemoryApprovalSession, MemoryManifestDraft

from .models import LocalMemoryBackupPlan, LocalMemoryRollbackPlan, LocalMemoryWritePlan, LocalMemoryWriteValidation


REQUIRED_GATES = {
    "backup_plan_required": True,
    "rollback_plan_required": True,
    "backup_created": False,
    "rollback_available": False,
    "operator_confirmation": False,
    "edited_summary_for_sensitive_or_voice": False,
    "provenance_verified": False,
    "local_only_write_transaction": False,
}


def validate_write_plan(
    manifest: MemoryManifestDraft,
    plan: LocalMemoryWritePlan,
    backup_plan: LocalMemoryBackupPlan,
    rollback_plan: LocalMemoryRollbackPlan,
    session: MemoryApprovalSession | None = None,
) -> LocalMemoryWriteValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if not manifest.manifest_id:
        errors.append("missing_source_manifest")
    if plan.source_manifest_id != manifest.manifest_id:
        errors.append("source_manifest_mismatch")
    if not plan.backup_plan_id or plan.backup_plan_id != backup_plan.backup_plan_id:
        errors.append("backup_plan_required")
    if not plan.rollback_plan_id or plan.rollback_plan_id != rollback_plan.rollback_plan_id:
        errors.append("rollback_plan_required")
    if plan.apply_enabled:
        errors.append("apply_enabled_must_be_false_in_v0")
    if plan.local_brain_write:
        errors.append("local_brain_write_must_be_false")
    if plan.local_brain_mutated:
        errors.append("local_brain_mutated_must_be_false")
    if not plan.requires_user_approval:
        errors.append("requires_user_approval_must_be_true")
    if backup_plan.backup_created:
        errors.append("backup_must_not_be_created_in_dry_run")
    if rollback_plan.rollback_executed:
        errors.append("rollback_must_not_execute_in_dry_run")

    for write in plan.writes:
        if write.write_allowed:
            errors.append(f"{write.write_id}:write_allowed_must_be_false")
        if write.sensitivity in {"sensitive", "secret"} and write.target_collection != "sensitive_hold":
            errors.append(f"{write.write_id}:sensitive_must_target_hold")
        if not write.source_refs:
            warnings.append(f"{write.write_id}:missing_source_refs")

    if session is None and manifest.approved_candidate_ids:
        warnings.append("session_context_missing_for_candidate_policy_validation")

    return LocalMemoryWriteValidation(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        apply_enabled=False,
        local_brain_write=False,
        required_gates=dict(REQUIRED_GATES),
    )
