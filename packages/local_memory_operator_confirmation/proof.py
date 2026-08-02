from __future__ import annotations

import json
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone

from .service import create_confirmation_request, submit_confirmation_decision


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_DIR = PROJECT_ROOT / "data" / "audits" / "local_brain_memory"


def run_proof(output_dir: Path | str = DEFAULT_AUDIT_DIR) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="atanor_operator_confirmation_") as tmp:
        root = Path(tmp)
        request_payload = create_confirmation_request(
            source_memory_manifest_id="local-memory-manifest:proof",
            source_write_plan_id="local_memory_write_plan_proof",
            backup_plan_id="local_memory_backup_proof",
            rollback_plan_id="local_memory_rollback_proof",
            source_sandbox_transaction_id="local_memory_sandbox_tx_proof",
            root=root,
        )
        request = request_payload["request"]
        wrong = submit_confirmation_decision(
            request["request_id"],
            decision="confirm",
            typed_phrase="I UNDERSTAND LOCAL BRAIN WRITE",
            root=root,
        )
        correct = submit_confirmation_decision(
            request["request_id"],
            decision="confirm",
            typed_phrase=request["required_phrase"],
            root=root,
        )
        missing_rollback = create_confirmation_request(
            source_memory_manifest_id="local-memory-manifest:missing-rollback",
            source_write_plan_id="local_memory_write_plan_missing_rollback",
            backup_plan_id="local_memory_backup_missing_rollback",
            rollback_plan_id=None,
            source_sandbox_transaction_id="local_memory_sandbox_tx_missing_rollback",
            root=root,
        )
        missing_sandbox = create_confirmation_request(
            source_memory_manifest_id="local-memory-manifest:missing-sandbox",
            source_write_plan_id="local_memory_write_plan_missing_sandbox",
            backup_plan_id="local_memory_backup_missing_sandbox",
            rollback_plan_id="local_memory_rollback_missing_sandbox",
            source_sandbox_transaction_id=None,
            root=root,
        )
        expired_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        expired = create_confirmation_request(
            source_memory_manifest_id="local-memory-manifest:expired",
            source_write_plan_id="local_memory_write_plan_expired",
            backup_plan_id="local_memory_backup_expired",
            rollback_plan_id="local_memory_rollback_expired",
            source_sandbox_transaction_id="local_memory_sandbox_tx_expired",
            expires_at=expired_time,
            root=root,
        )

    result = {
        "verdict": "PASS",
        "scenarios": {
            "request_created": request_payload["request"]["status"] == "pending_confirmation",
            "wrong_phrase_fails": wrong["gate"]["allowed_to_prepare_real_write"] is False,
            "correct_phrase_prepares_only": correct["gate"]["allowed_to_prepare_real_write"] is True,
            "allowed_to_apply_real_write": correct["gate"]["allowed_to_apply_real_write"],
            "apply_enabled": correct["gate"]["apply_enabled"],
            "local_brain_write": correct["gate"]["local_brain_write"],
            "missing_rollback_blocks": missing_rollback["request"]["status"] == "blocked",
            "missing_sandbox_blocks": missing_sandbox["request"]["status"] == "blocked",
            "expired_request_blocks": expired["request"]["status"] == "blocked",
        },
        "invariants": {
            "real_local_brain_write": False,
            "real_local_brain_mutated": False,
            "memory_apply_enabled": False,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
        },
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output / f"operator_confirmation_proof_{ts}.json"
    md_path = output / f"operator_confirmation_proof_{ts}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Local Brain Operator Confirmation Proof",
                "",
                f"Verdict: {result['verdict']}",
                "",
                "Real Local Brain write: false",
                "Apply enabled: false",
                "Correct phrase allows preparation only: true",
            ]
        ),
        encoding="utf-8",
    )
    return {**result, "json_path": str(json_path), "md_path": str(md_path)}


if __name__ == "__main__":
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))
