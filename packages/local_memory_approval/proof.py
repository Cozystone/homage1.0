from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from .manifest import build_memory_manifest_draft, proof_sign_manifest, validate_memory_manifest
from .policy import classify_memory_candidate, recommend_memory_decision
from .proposal import propose_memory_review_candidate
from .review_store import MemoryApprovalReviewStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "local_brain_memory"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    preference = classify_memory_candidate("I prefer natural Korean explanations.", "preference")
    project = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    sensitive = classify_memory_candidate("My email is user@example.com and phone is 555-123-4567.", "user_text")
    voice = classify_memory_candidate("Voice transcript: I like concise answers.", "voice_transcript")
    selfhood = propose_memory_review_candidate("Selfhood proposes remembering that the user wants approval before memory writes.")

    with tempfile.TemporaryDirectory(prefix="atanor_local_memory_approval_") as tmp:
        store = MemoryApprovalReviewStore(tmp)
        session = store.create_memory_review_session([preference, project, sensitive, voice, selfhood])
        session = store.add_memory_decision(session.session_id, preference.candidate_id, "approve_for_future_memory_manifest")
        session = store.add_memory_decision(session.session_id, project.candidate_id, "approve_for_future_memory_manifest")
        session = store.add_memory_decision(session.session_id, sensitive.candidate_id, "edit_required", edited_summary="User provided private contact details; do not store raw value.")
        session = store.add_memory_decision(session.session_id, voice.candidate_id, "edit_required", edited_summary="User may prefer concise answers.")
        session = store.add_memory_decision(session.session_id, selfhood.candidate_id, "defer")
        summary = store.summarize_memory_review_session(session.session_id)
        manifest = build_memory_manifest_draft(session, created_at="2026-01-01T00:00:00Z")
        validation = validate_memory_manifest(session, manifest)
        signed = proof_sign_manifest(manifest, "proof-reviewer")

    payload = {
        "verdict": "LOCAL_BRAIN_MEMORY_APPROVAL_GATE_PROOF_ONLY",
        "scenarios": {
            "preference": {
                "memory_type": preference.memory_type,
                "recommended": recommend_memory_decision(preference),
                "requires_user_approval": preference.requires_user_approval,
                "local_brain_write": preference.local_brain_write,
            },
            "project_context": {
                "memory_type": project.memory_type,
                "recommended": recommend_memory_decision(project),
                "requires_user_approval": project.requires_user_approval,
                "manifest_draft_possible": project.candidate_id in manifest.approved_candidate_ids,
            },
            "sensitive": {
                "memory_type": sensitive.memory_type,
                "recommended": recommend_memory_decision(sensitive),
                "raw_write_allowed": False,
            },
            "voice": {
                "source_type": voice.source_type,
                "recommended": recommend_memory_decision(voice),
                "raw_transcript_direct_write": False,
            },
            "approval_session": {
                "status": session.status,
                "decisions": len(session.decisions),
                "local_brain_mutated": session.local_brain_mutated,
            },
            "manifest": {
                "valid": validation["valid"],
                "ready_for_memory_write": manifest.ready_for_memory_write,
                "apply_enabled": manifest.apply_enabled,
                "local_brain_write": manifest.local_brain_write,
                "signed_ready_for_memory_write": signed.ready_for_memory_write,
            },
            "selfhood_proposal": {
                "source_type": selfhood.source_type,
                "requires_user_approval": selfhood.requires_user_approval,
                "local_brain_write": selfhood.local_brain_write,
            },
        },
        "session_summary": summary,
        "manifest": manifest.to_dict(),
        "validation": validation,
        "invariants": {
            "local_brain_write": False,
            "local_brain_mutated": False,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
            "memory_apply_enabled": False,
            "requires_user_approval": True,
            "raw_voice_saved": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"local_memory_approval_proof_{ts}.json"
    md_path = output_dir / f"local_memory_approval_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Local Brain Memory Approval Gate Proof", ""]
    lines.append(f"- Verdict: `{payload['verdict']}`")
    for key, value in payload["invariants"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- Manifest id: `{payload['manifest']['manifest_id']}`",
            f"- Canonical hash: `{payload['manifest']['canonical_hash']}`",
            f"- Ready for memory write: `{payload['manifest']['ready_for_memory_write']}`",
            f"- Apply enabled: `{payload['manifest']['apply_enabled']}`",
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
