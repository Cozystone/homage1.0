from __future__ import annotations

import hashlib
import json
from typing import Any

from packages.local_memory_approval.models import MemoryApprovalSession, MemoryCandidate, MemoryManifestDraft

from .backup import create_backup_plan
from .models import LocalMemoryWriteCandidate, LocalMemoryWritePlan, TargetCollection
from .rollback import create_rollback_plan


TARGET_BY_MEMORY_TYPE: dict[str, TargetCollection] = {
    "preference": "preferences",
    "personal_fact": "personal_facts",
    "project_context": "project_context",
    "correction": "corrections",
    "task_goal": "task_goals",
    "relationship": "relationships",
    "sensitive": "sensitive_hold",
}


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def _decisions_by_candidate(session: MemoryApprovalSession | None) -> dict[str, Any]:
    if session is None:
        return {}
    return {decision.candidate_id: decision for decision in session.decisions}


def _candidates_by_id(session: MemoryApprovalSession | None) -> dict[str, MemoryCandidate]:
    if session is None:
        return {}
    return {candidate.candidate_id: candidate for candidate in session.candidates}


def build_write_plan_from_memory_manifest(
    manifest: MemoryManifestDraft,
    session: MemoryApprovalSession | None = None,
    *,
    local_brain_hash_before: str | None = None,
    target_paths: list[str] | None = None,
) -> LocalMemoryWritePlan:
    """Plan future Local Brain writes from an approved manifest without writing."""

    candidates = _candidates_by_id(session)
    decisions = _decisions_by_candidate(session)
    writes: list[LocalMemoryWriteCandidate] = []
    skipped: list[dict[str, Any]] = []

    for candidate_id in sorted(manifest.approved_candidate_ids):
        candidate = candidates.get(candidate_id)
        decision = decisions.get(candidate_id)
        summary = manifest.approved_memory_summaries.get(candidate_id, "")
        if candidate is None or decision is None:
            skipped.append({"candidate_id": candidate_id, "reason": "missing_session_context"})
            continue
        if decision.decision != "approve_for_future_memory_manifest":
            skipped.append({"candidate_id": candidate_id, "reason": "not_approved"})
            continue
        if candidate.sensitivity in {"sensitive", "secret"} and not decision.edited_summary:
            skipped.append({"candidate_id": candidate_id, "reason": "sensitive_raw_memory_blocked"})
            continue
        if candidate.source_type == "voice_transcript" and not decision.edited_summary:
            skipped.append({"candidate_id": candidate_id, "reason": "voice_raw_transcript_blocked"})
            continue
        if candidate.memory_type not in TARGET_BY_MEMORY_TYPE:
            skipped.append({"candidate_id": candidate_id, "reason": "unknown_memory_type"})
            continue

        target_collection = TARGET_BY_MEMORY_TYPE[candidate.memory_type]
        writes.append(
            LocalMemoryWriteCandidate(
                write_id=_stable_id(
                    "local_memory_write",
                    {"manifest_id": manifest.manifest_id, "candidate_id": candidate_id, "summary": summary},
                ),
                source_memory_candidate_id=candidate_id,
                memory_type=candidate.memory_type,
                normalized_summary=summary,
                target_collection=target_collection,
                source_refs=list(candidate.source_refs),
                sensitivity=candidate.sensitivity,
                write_allowed=False,
            )
        )

    backup_plan = create_backup_plan(source_manifest_id=manifest.manifest_id, target_paths=target_paths)
    rollback_plan = create_rollback_plan(backup_plan)
    plan_payload = {
        "source_manifest_id": manifest.manifest_id,
        "local_brain_hash_before": local_brain_hash_before if local_brain_hash_before is not None else manifest.local_brain_hash_before,
        "writes": [write.to_dict() for write in writes],
        "skipped": skipped,
        "backup_plan_id": backup_plan.backup_plan_id,
        "rollback_plan_id": rollback_plan.rollback_plan_id,
        "apply_enabled": False,
        "local_brain_write": False,
        "local_brain_mutated": False,
        "requires_user_approval": True,
    }
    return LocalMemoryWritePlan(
        plan_id=_stable_id("local_memory_write_plan", plan_payload),
        source_manifest_id=manifest.manifest_id,
        local_brain_hash_before=plan_payload["local_brain_hash_before"],
        writes=writes,
        skipped=skipped,
        backup_plan_id=backup_plan.backup_plan_id,
        rollback_plan_id=rollback_plan.rollback_plan_id,
        apply_enabled=False,
        local_brain_write=False,
        local_brain_mutated=False,
        requires_user_approval=True,
    )
