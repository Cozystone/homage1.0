from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from packages.promotion_review.review_store import PromotionReviewStore

from .canonicalize import canonical_json_bytes
from .signer import proof_sign
from .validator import build_manifest_from_review_session, validate_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "promotion_manifest"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def sample_review_report() -> dict[str, Any]:
    return {
        "report_id": "manifest_gate_fixture",
        "source_run_id": "candidate_fixture_run",
        "verified_store_manifest_hash": "verified_hash_before",
        "candidate_store_manifest_hash": "candidate_hash",
        "review_items": [
            {"candidate_id": "concept:good", "item_type": "concept", "summary": "Good sourced concept", "source_refs": ["wiki:good"], "dry_run_effect": "create", "risk_flags": [], "quality_score": 0.93},
            {"candidate_id": "evidence:no_source", "item_type": "evidence", "summary": "No source", "source_refs": [], "dry_run_effect": "unknown", "risk_flags": ["no_source"], "quality_score": 0.2},
            {"candidate_id": "relation:conflict", "item_type": "relation", "summary": "Conflict", "source_refs": ["wiki:a", "wiki:b"], "dry_run_effect": "strengthen", "risk_flags": ["conflict"], "quality_score": 0.6},
            {"candidate_id": "case_frame:generic", "item_type": "case_frame", "summary": "Generic predicate", "source_refs": ["wiki:g"], "dry_run_effect": "create", "risk_flags": ["generic_predicate"], "quality_score": 0.7},
        ],
    }


def _reviewed_session(tmp: str):
    store = PromotionReviewStore(tmp)
    session = store.create_review_session(sample_review_report())
    by_candidate = {item.candidate_id: item for item in session.items}
    session = store.add_decision(session.session_id, by_candidate["concept:good"].item_id, "approve_for_future_manifest", notes="source grounded")
    session = store.add_decision(session.session_id, by_candidate["evidence:no_source"].item_id, "reject", notes="no source")
    session = store.add_decision(session.session_id, by_candidate["relation:conflict"].item_id, "conflict_review", notes="conflicting evidence")
    session = store.add_decision(session.session_id, by_candidate["case_frame:generic"].item_id, "needs_more_evidence", notes="generic predicate")
    return session


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="atanor_promotion_manifest_") as tmp:
        session = _reviewed_session(tmp)
        manifest = build_manifest_from_review_session(session, created_at="2026-01-01T00:00:00Z")
        validation = validate_manifest(manifest)
        signed = proof_sign(manifest, "proof-reviewer")
        signed_validation = validate_manifest(signed)

        stable_hash = manifest.canonical_hash == build_manifest_from_review_session(session, created_at="2026-12-31T00:00:00Z").canonical_hash
        signature_excluded = canonical_json_bytes(manifest.to_dict()) == canonical_json_bytes(signed.to_dict())

        bad_no_source = replace(manifest, items=[replace(item, approved_for_manifest=True) if item.candidate_id == "evidence:no_source" else item for item in manifest.items])
        bad_conflict = replace(manifest, items=[replace(item, approved_for_manifest=True) if item.candidate_id == "relation:conflict" else item for item in manifest.items])
        bad_generic = replace(manifest, items=[replace(item, approved_for_manifest=True) if item.candidate_id == "case_frame:generic" else item for item in manifest.items])

    payload = {
        "verdict": "SIGNED_PROMOTION_MANIFEST_GATE_PROOF_ONLY",
        "scenarios": {
            "build_manifest": validation.valid,
            "canonical_hash_stable": stable_hash,
            "signature_excluded_from_hash": signature_excluded,
            "proof_signature_does_not_enable_promotion": signed.ready_for_real_promotion is False and signed.apply_enabled is False and signed_validation.ready_for_real_promotion is False,
            "no_source_item_cannot_be_approved": any("approved_no_source" in error for error in validate_manifest(bad_no_source).errors),
            "conflict_item_cannot_be_approved": any("approved_conflict" in error for error in validate_manifest(bad_conflict).errors),
            "generic_predicate_requires_more_evidence": any("approved_generic_predicate_without_explicit_note" in error for error in validate_manifest(bad_generic).errors),
            "apply_enabled": manifest.apply_enabled,
            "production_store_mutated": manifest.production_store_mutated,
            "local_brain_write": manifest.local_brain_write,
            "candidate_store_mutated": manifest.candidate_store_mutated,
        },
        "manifest": manifest.to_dict(),
        "signed_manifest": signed.to_dict(),
        "validation": validation.to_dict(),
        "invariants": {
            "production_store_mutated": False,
            "actual_promotion_performed": False,
            "local_brain_write": False,
            "candidate_store_mutated": False,
            "external_llm_used": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
            "manifest_apply_enabled": False,
            "requires_user_approval": True,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"promotion_manifest_proof_{ts}.json"
    md_path = output_dir / f"promotion_manifest_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Signed Promotion Manifest Gate Proof", ""]
    lines.append(f"- Verdict: `{payload['verdict']}`")
    for key, value in payload["invariants"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- Manifest id: `{payload['manifest']['manifest_id']}`",
            f"- Canonical hash: `{payload['manifest']['canonical_hash']}`",
            f"- Proof signed: `{payload['signed_manifest']['signed']}`",
            f"- Ready for real promotion: `{payload['signed_manifest']['ready_for_real_promotion']}`",
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
