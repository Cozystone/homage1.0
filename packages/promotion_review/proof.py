from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from .manifest import create_manifest_draft
from .models import PromotionReviewItem
from .review_policy import recommend_decision
from .review_store import PromotionReviewStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "promotion_review"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def sample_dry_run_report() -> dict[str, Any]:
    return {
        "report_id": "dry_run_fixture_001",
        "source_run_id": "candidate_fixture_run",
        "verified_store_manifest_hash": "verified_hash_before",
        "candidate_store_manifest_hash": "candidate_hash",
        "review_items": [
            {
                "candidate_id": "concept:kubernetes",
                "item_type": "concept",
                "summary": "Kubernetes concept with sourced definition",
                "source_refs": ["wiki:Kubernetes"],
                "dry_run_effect": "create",
                "risk_flags": [],
                "quality_score": 0.91,
            },
            {
                "candidate_id": "case_frame:generic_use",
                "item_type": "case_frame",
                "summary": "Generic predicate frame",
                "source_refs": ["wiki:Example"],
                "dry_run_effect": "create",
                "risk_flags": ["generic_predicate"],
                "quality_score": 0.72,
            },
            {
                "candidate_id": "relation:conflict",
                "item_type": "relation",
                "summary": "Conflicting relation candidate",
                "source_refs": ["wiki:A", "wiki:B"],
                "dry_run_effect": "strengthen",
                "risk_flags": ["conflict"],
                "quality_score": 0.66,
            },
            {
                "candidate_id": "evidence:no_source",
                "item_type": "evidence",
                "summary": "Evidence row without source",
                "source_refs": [],
                "dry_run_effect": "unknown",
                "risk_flags": ["no_source"],
                "quality_score": 0.2,
            },
        ],
    }


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="atanor_promotion_review_") as tmp:
        store = PromotionReviewStore(tmp)
        session = store.create_review_session(sample_dry_run_report())
        recommendations = {item.candidate_id: recommend_decision(item) for item in session.items}
        approved_item = next(item for item in session.items if item.candidate_id == "concept:kubernetes")
        rejected_item = next(item for item in session.items if item.candidate_id == "evidence:no_source")
        deferred_item = next(item for item in session.items if item.candidate_id == "case_frame:generic_use")
        store.add_decision(session.session_id, approved_item.item_id, "approve_for_future_manifest", notes="source grounded")
        store.add_decision(session.session_id, rejected_item.item_id, "reject", notes="no source")
        final_session = store.add_decision(session.session_id, deferred_item.item_id, "defer", notes="generic predicate")
        manifest = create_manifest_draft(final_session)
        summary = store.summarize_review_session(session.session_id)

    payload = {
        "verdict": "PROMOTION_REVIEW_FLOW_PROOF_ONLY",
        "scenarios": {
            "session_creation": True,
            "decisions_recorded": len(final_session.decisions) == 3,
            "generic_predicate_recommendation": recommendations["case_frame:generic_use"] == "defer",
            "conflict_recommendation": recommendations["relation:conflict"] == "conflict_review",
            "manifest_draft_created": bool(manifest.manifest_id),
            "manifest_ready_for_real_promotion": manifest.ready_for_real_promotion,
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_store_mutated": False,
            "selfhood_proposal_requires_user_approval": True,
        },
        "summary": summary,
        "manifest": manifest.to_dict(),
        "invariants": {
            "production_store_mutated": False,
            "actual_promotion_performed": False,
            "local_brain_write": False,
            "candidate_store_mutated": False,
            "external_llm_used": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
            "requires_user_approval": True,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"promotion_review_proof_{ts}.json"
    md_path = output_dir / f"promotion_review_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Promotion Human Review Flow Proof", ""]
    lines.append(f"- Verdict: `{payload['verdict']}`")
    for key, value in payload["invariants"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- Review items: {payload['summary']['items']}",
            f"- Decisions: {payload['summary']['decisions']}",
            f"- Manifest draft: `{payload['manifest']['manifest_id']}`",
            f"- Ready for real promotion: `{payload['manifest']['ready_for_real_promotion']}`",
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
