from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any

from .models import MemoryApprovalDecision, MemoryApprovalSession, MemoryCandidate, MemoryManifestDraft, utc_now_iso


EXCLUDED_HASH_FIELDS = {"created_at", "signed", "signature", "signer_id", "canonical_hash"}


def _canonicalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _canonicalize(value[key])
            for key in sorted(value)
            if key not in EXCLUDED_HASH_FIELDS and value[key] is not None
        }
    return value


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(_canonicalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _manifest_id(canonical_hash: str) -> str:
    return f"local-memory-manifest:{canonical_hash[:16]}"


def _decisions_by_candidate(session: MemoryApprovalSession) -> dict[str, MemoryApprovalDecision]:
    return {decision.candidate_id: decision for decision in session.decisions}


def _candidate_by_id(session: MemoryApprovalSession) -> dict[str, MemoryCandidate]:
    return {candidate.candidate_id: candidate for candidate in session.candidates}


def _summary_for_manifest(candidate: MemoryCandidate, decision: MemoryApprovalDecision) -> str:
    if decision.edited_summary:
        return decision.edited_summary.strip()
    return candidate.normalized_summary


def build_memory_manifest_draft(
    session: MemoryApprovalSession,
    *,
    local_brain_hash_before: str | None = None,
    created_at: str | None = None,
) -> MemoryManifestDraft:
    decisions = _decisions_by_candidate(session)
    candidates = _candidate_by_id(session)
    approved_ids: list[str] = []
    rejected_ids: list[str] = []
    deferred_ids: list[str] = []
    summaries: dict[str, str] = {}

    for decision in sorted(session.decisions, key=lambda item: (item.decision, item.candidate_id, item.decision_id)):
        if decision.decision == "approve_for_future_memory_manifest":
            approved_ids.append(decision.candidate_id)
            summaries[decision.candidate_id] = _summary_for_manifest(candidates[decision.candidate_id], decision)
        elif decision.decision == "reject" or decision.decision == "sensitive_block":
            rejected_ids.append(decision.candidate_id)
        else:
            deferred_ids.append(decision.candidate_id)

    base_payload = {
        "source_session_id": session.session_id,
        "approved_candidate_ids": sorted(approved_ids),
        "rejected_candidate_ids": sorted(rejected_ids),
        "deferred_candidate_ids": sorted(deferred_ids),
        "local_brain_hash_before": local_brain_hash_before,
        "approved_memory_summaries": summaries,
        "ready_for_memory_write": False,
        "apply_enabled": False,
        "local_brain_write": False,
    }
    canonical_hash = sha256_hex(base_payload)
    return MemoryManifestDraft(
        manifest_id=_manifest_id(canonical_hash),
        source_session_id=session.session_id,
        approved_candidate_ids=sorted(approved_ids),
        rejected_candidate_ids=sorted(rejected_ids),
        deferred_candidate_ids=sorted(deferred_ids),
        local_brain_hash_before=local_brain_hash_before,
        created_at=created_at or utc_now_iso(),
        canonical_hash=canonical_hash,
        approved_memory_summaries=summaries,
        ready_for_memory_write=False,
        apply_enabled=False,
        local_brain_write=False,
    )


def validate_memory_manifest(session: MemoryApprovalSession, manifest: MemoryManifestDraft) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    decisions = _decisions_by_candidate(session)
    candidates = _candidate_by_id(session)

    if manifest.ready_for_memory_write:
        errors.append("ready_for_memory_write_must_be_false_in_v0")
    if manifest.apply_enabled:
        errors.append("apply_enabled_must_be_false_in_v0")
    if manifest.local_brain_write:
        errors.append("local_brain_write_must_be_false")

    for candidate_id in manifest.approved_candidate_ids:
        candidate = candidates.get(candidate_id)
        decision = decisions.get(candidate_id)
        if candidate is None:
            errors.append(f"{candidate_id}:missing_candidate")
            continue
        if decision is None:
            errors.append(f"{candidate_id}:missing_decision")
            continue
        if decision.decision != "approve_for_future_memory_manifest":
            errors.append(f"{candidate_id}:not_approved")
        if candidate.sensitivity in {"sensitive", "secret"} and not decision.edited_summary:
            errors.append(f"{candidate_id}:sensitive_requires_edited_summary")
        if candidate.source_type == "voice_transcript" and not decision.edited_summary:
            errors.append(f"{candidate_id}:voice_transcript_requires_edited_summary")
        if not candidate.source_refs:
            warnings.append(f"{candidate_id}:missing_source_refs")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "ready_for_memory_write": False,
        "apply_enabled": False,
        "local_brain_write": False,
        "required_future_gates": {
            "local_backup_exists": False,
            "rollback_plan_exists": False,
            "operator_confirmation": False,
            "sensitivity_approval": False,
            "per_source_provenance_verified": False,
        },
    }


def proof_sign_manifest(manifest: MemoryManifestDraft, signer_id: str) -> MemoryManifestDraft:
    if not signer_id:
        raise ValueError("proof signer_id is required")
    return replace(
        manifest,
        signed=True,
        signature=f"proof-memory-signature:{manifest.canonical_hash}",
        signer_id=signer_id,
        ready_for_memory_write=False,
        apply_enabled=False,
        local_brain_write=False,
    )
