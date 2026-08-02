from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .feedback_adapter import convert_feedback_and_enqueue_candidates
from .monitor import repair_answer_for_mode
from .repair_rules import RepairRule
from .review_queue import approve_repair_candidate, enqueue_repair_candidates, reject_repair_candidate
from .rule_registry import load_production_rules, rollback_rule
from .storage import SURFACE_ROOT, ensure_dirs, write_json


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# ATANOR Surface Repair Review Queue Proof",
        "",
        f"- PASS: {payload['pass']}",
        f"- Candidates created: {payload['candidates_created']}",
        f"- Candidates approved: {payload['candidates_approved']}",
        f"- Candidates rejected: {payload['candidates_rejected']}",
        f"- Production rules created: {payload['production_rules_created']}",
        f"- Rollback tested: {payload['rollback_tested']}",
        f"- Audit events written: {payload['audit_events_written']}",
        "",
        "## This proof claims",
        "- ATANOR can queue repair candidates generated from answer-quality feedback.",
        "- A human/operator can approve or reject candidates.",
        "- Only approved rules can enter the production repair registry.",
        "- Approved rules can be used by the Surface Repair Loop.",
        "- Rules can be disabled or rolled back.",
        "- All actions are audit logged.",
        "",
        "## This proof does NOT claim",
        "- automatic safe self-improvement",
        "- GPT-level language quality",
        "- perfect factuality repair",
        "- external LLM judging",
        "- autonomous production mutation without review",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_surface_repair_review_queue_proof() -> dict[str, Any]:
    ensure_dirs()
    run_id = "review_queue_proof_" + hashlib.sha256(b"atanor-review-queue").hexdigest()[:10]
    feedback_result = convert_feedback_and_enqueue_candidates(
        [{
            "feedback_id": "proof_trace_leakage",
            "type": "trace_leakage",
            "suggestion": "Move internal route terms out of the default answer.",
            "flags": ["trace_leakage"],
        }],
        run_id,
    )
    candidate_id = feedback_result["candidate_ids"][0]
    production_rule = approve_repair_candidate(candidate_id, reviewer="proof_operator", comment="Approve deterministic trace leakage guard.")

    custom_rule = RepairRule(
        rule_id="proof_public_route_phrase",
        name="proof_public_route_phrase",
        description="Proof-only production rule that removes a specific internal route phrase.",
        trigger_terms=["INTERNAL_ROUTE_TOKEN"],
        mode_scope="default_only",
        action="replace",
        replacement="근거",
        severity="high",
        enabled=True,
        source="proof",
    )
    custom_candidate = enqueue_repair_candidates([custom_rule], source_run_id=run_id)[0]
    custom_production_rule = approve_repair_candidate(custom_candidate["candidate_id"], reviewer="proof_operator", comment="Approve proof-specific rule.")
    repaired = repair_answer_for_mode("INTERNAL_ROUTE_TOKEN 기준으로 설명하면 쿠버네티스는 컨테이너 관리 시스템입니다.", mode="default", trace={})

    rejected_candidate = enqueue_repair_candidates([
        RepairRule(
            rule_id="proof_rejected_style_rule",
            name="proof_rejected_style_rule",
            description="Rejected style rewrite should never enter production.",
            trigger_terms=["쉽게 말하면"],
            mode_scope="default_only",
            action="rewrite_sentence",
            severity="low",
            enabled=False,
            source="proof",
        )
    ], source_run_id=run_id)[0]
    rejected = reject_repair_candidate(rejected_candidate["candidate_id"], reviewer="proof_operator", comment="Style rule requires human copy review.")
    rollback = rollback_rule(str(custom_production_rule["rule_id"]), actor="proof_operator")

    production_rules = load_production_rules()
    audit_path = SURFACE_ROOT / "rule_audit" / "repair_audit_log.jsonl"
    audit_events_written = len(audit_path.read_text(encoding="utf-8").splitlines()) if audit_path.exists() else 0
    payload = {
        "pass": bool(
            feedback_result["created_candidates"] >= 1
            and production_rule.get("enabled") is True
            and custom_production_rule.get("enabled") is True
            and "proof_public_route_phrase" in repaired.get("production_rules_used", [])
            and rejected.get("status") == "rejected"
            and rollback.get("enabled") is False
            and audit_events_written >= 5
        ),
        "run_id": run_id,
        "candidates_created": feedback_result["created_candidates"] + 2,
        "candidates_approved": 2,
        "candidates_rejected": 1,
        "production_rules_created": len(production_rules),
        "rollback_tested": rollback.get("rolled_back") is True,
        "audit_events_written": audit_events_written,
        "approved_candidate_id": candidate_id,
        "custom_candidate_id": custom_candidate["candidate_id"],
        "rejected_candidate_id": rejected_candidate["candidate_id"],
        "repair_result": repaired,
        "production_rule": production_rule,
        "custom_production_rule": custom_production_rule,
        "rollback": rollback,
        "honesty": {
            "auto_promoted": False,
            "external_llm_judge_used": False,
            "autonomous_production_mutation": False,
            "manual_review_required": True,
        },
    }
    json_path = SURFACE_ROOT / "proofs" / "surface_repair_review_queue_proof.json"
    md_path = SURFACE_ROOT / "proofs" / "surface_repair_review_queue_proof.md"
    write_json(json_path, payload)
    _write_markdown(md_path, payload)
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(md_path)
    return payload


if __name__ == "__main__":
    result = run_surface_repair_review_queue_proof()
    print("PASS" if result["pass"] else "FAIL")
    print(result["json_path"])
    print(result["markdown_path"])
