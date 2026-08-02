from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore
from packages.local_memory_write_plan.planner import build_write_plan_from_memory_manifest

from .backup import backup_sandbox_store
from .rollback import rollback_sandbox_store
from .store import compute_store_hash, init_sandbox_store, read_collection, write_collection
from .transaction import apply_write_plan_to_sandbox, validate_transaction
from .validator import validate_sandbox_cycle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "local_brain_memory"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _fixture_write_plan(tmp: str):
    preference = classify_memory_candidate("I prefer natural Korean explanations.", "preference")
    project = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    store = MemoryApprovalReviewStore(Path(tmp) / "review")
    session = store.create_memory_review_session([preference, project])
    session = store.add_memory_decision(session.session_id, preference.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, project.candidate_id, "approve_for_future_memory_manifest")
    manifest = build_memory_manifest_draft(session)
    return build_write_plan_from_memory_manifest(manifest, session), preference, project


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="atanor_local_memory_sandbox_") as tmp:
        root = Path(tmp)
        sandbox = root / "sandbox_store"
        backup_path = root / "sandbox_backup"
        write_plan, preference, project = _fixture_write_plan(tmp)
        init_sandbox_store(sandbox)
        hash_initial = compute_store_hash(sandbox)
        backup = backup_sandbox_store(sandbox, backup_path)
        transaction = apply_write_plan_to_sandbox(write_plan, sandbox, backup_path=backup_path)
        tx_validation = validate_transaction(transaction)
        hash_after_apply = compute_store_hash(sandbox)
        preference_items = read_collection(sandbox, "preferences")
        project_items = read_collection(sandbox, "project_context")
        rollback = rollback_sandbox_store(transaction)
        hash_after_rollback = compute_store_hash(sandbox)
        cycle_validation = validate_sandbox_cycle(backup, transaction, rollback)

        sensitive_blocked = False
        voice_blocked = False
        real_path_rejected = False
        try:
            write_collection(sandbox, "sensitive_hold", {"normalized_summary": "raw", "sensitivity": "sensitive", "raw_text": "secret@example.com"})
        except ValueError:
            sensitive_blocked = True
        try:
            write_collection(sandbox, "preferences", {"normalized_summary": "Voice transcript: remember raw audio", "source_type": "voice_transcript"})
        except ValueError:
            voice_blocked = True
        try:
            init_sandbox_store(PROJECT_ROOT / "data" / "memory")
        except ValueError:
            real_path_rejected = True

    payload = {
        "verdict": "LOCAL_BRAIN_SANDBOX_WRITE_TRANSACTION_PROOF_ONLY",
        "scenarios": {
            "initialize_sandbox_store": bool(hash_initial),
            "approved_preference_written_to_sandbox": any(item["source_memory_candidate_id"] == preference.candidate_id for item in preference_items),
            "approved_project_context_written_to_sandbox": any(item["source_memory_candidate_id"] == project.candidate_id for item in project_items),
            "backup_created": backup.backup_created,
            "store_hash_changed": hash_initial != hash_after_apply,
            "rollback_executed": rollback.rollback_executed,
            "store_hash_restored": hash_after_rollback == hash_initial,
            "sensitive_raw_write_blocked": sensitive_blocked,
            "raw_voice_transcript_blocked": voice_blocked,
            "real_local_brain_path_rejected": real_path_rejected,
        },
        "transaction": transaction.to_dict(),
        "backup": backup.to_dict(),
        "rollback": rollback.to_dict(),
        "transaction_validation": tx_validation,
        "cycle_validation": cycle_validation,
        "invariants": {
            "real_local_brain_write": False,
            "real_local_brain_mutated": False,
            "sandbox_local_brain_write": True,
            "sandbox_rollback_verified": rollback.sandbox_rollback_verified,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
            "requires_user_approval": True,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"local_memory_sandbox_proof_{ts}.json"
    md_path = output_dir / f"local_memory_sandbox_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Local Brain Sandbox Write Transaction Proof", ""]
    lines.append(f"- Verdict: `{payload['verdict']}`")
    for key, value in payload["invariants"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- Transaction id: `{payload['transaction']['transaction_id']}`",
            f"- Applied: `{payload['transaction']['applied']}`",
            f"- Rollback verified: `{payload['rollback']['sandbox_rollback_verified']}`",
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
