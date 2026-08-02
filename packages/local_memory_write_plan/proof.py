from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore

from .backup import create_backup_plan
from .planner import build_write_plan_from_memory_manifest
from .rollback import create_rollback_plan
from .validator import validate_write_plan


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "local_brain_memory"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _fixture_session(tmp: str):
    preference = classify_memory_candidate("I prefer natural Korean explanations.", "preference")
    project = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    sensitive = classify_memory_candidate("My email is user@example.com.", "user_text")
    voice_raw = classify_memory_candidate("I like concise voice answers.", "voice_transcript")
    voice_edited = classify_memory_candidate("I prefer brief spoken answers.", "voice_transcript")

    store = MemoryApprovalReviewStore(tmp)
    session = store.create_memory_review_session([preference, project, sensitive, voice_raw, voice_edited])
    session = store.add_memory_decision(session.session_id, preference.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, project.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, sensitive.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, voice_raw.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(
        session.session_id,
        voice_edited.candidate_id,
        "approve_for_future_memory_manifest",
        edited_summary="User may prefer brief spoken answers.",
    )
    return session, {
        "preference": preference,
        "project": project,
        "sensitive": sensitive,
        "voice_raw": voice_raw,
        "voice_edited": voice_edited,
    }


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="atanor_local_memory_write_plan_") as tmp:
        session, candidates = _fixture_session(tmp)
        manifest = build_memory_manifest_draft(session, created_at="2026-01-01T00:00:00Z")
        backup_plan = create_backup_plan(source_manifest_id=manifest.manifest_id)
        rollback_plan = create_rollback_plan(backup_plan)
        plan = build_write_plan_from_memory_manifest(manifest, session)
        validation = validate_write_plan(manifest, plan, backup_plan, rollback_plan, session)

    target_by_candidate = {write.source_memory_candidate_id: write.target_collection for write in plan.writes}
    skipped_by_candidate = {item["candidate_id"]: item["reason"] for item in plan.skipped}
    payload = {
        "verdict": "LOCAL_BRAIN_MEMORY_WRITE_DRY_RUN_PROOF_ONLY",
        "scenarios": {
            "approved_preference_creates_write_candidate": target_by_candidate.get(candidates["preference"].candidate_id) == "preferences",
            "approved_project_context_creates_write_candidate": target_by_candidate.get(candidates["project"].candidate_id) == "project_context",
            "sensitive_raw_memory_skipped": skipped_by_candidate.get(candidates["sensitive"].candidate_id) == "sensitive_raw_memory_blocked",
            "voice_raw_transcript_skipped": skipped_by_candidate.get(candidates["voice_raw"].candidate_id) == "voice_raw_transcript_blocked",
            "voice_edited_summary_planned": candidates["voice_edited"].candidate_id in target_by_candidate,
            "backup_plan_required_not_created": backup_plan.backup_required is True and backup_plan.backup_created is False,
            "rollback_required_not_executable": rollback_plan.rollback_available is False and rollback_plan.rollback_executed is False,
            "validator_keeps_apply_disabled": validation.apply_enabled is False and validation.local_brain_write is False and validation.valid is True,
            "local_brain_unchanged": plan.local_brain_write is False and plan.local_brain_mutated is False,
        },
        "manifest": manifest.to_dict(),
        "write_plan": plan.to_dict(),
        "backup_plan": backup_plan.to_dict(),
        "rollback_plan": rollback_plan.to_dict(),
        "validation": validation.to_dict(),
        "invariants": {
            "local_brain_write": False,
            "local_brain_mutated": False,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
            "memory_apply_enabled": False,
            "backup_plan_required": True,
            "backup_created": False,
            "rollback_plan_required": True,
            "rollback_executed": False,
            "requires_user_approval": True,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"local_memory_write_plan_proof_{ts}.json"
    md_path = output_dir / f"local_memory_write_plan_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Local Brain Memory Write Dry-run Proof", ""]
    lines.append(f"- Verdict: `{payload['verdict']}`")
    for key, value in payload["invariants"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- Plan id: `{payload['write_plan']['plan_id']}`",
            f"- Planned writes: `{len(payload['write_plan']['writes'])}`",
            f"- Skipped: `{len(payload['write_plan']['skipped'])}`",
            f"- Apply enabled: `{payload['write_plan']['apply_enabled']}`",
            "",
            "Generated audit output. Do not commit.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    payload = run_proof()
    print(json.dumps({k: payload[k] for k in ("verdict", "scenarios", "invariants", "outputs")}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
