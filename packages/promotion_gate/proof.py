from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .dry_run import run_promotion_dry_run


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "promotion_gate"
DEFAULT_CANDIDATE = PROJECT_ROOT / "data" / "cloud_brain" / "candidate_runs" / "candidate_24h_1pps_20260621_195246"
DEFAULT_VERIFIED = PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    candidate_store: Path = DEFAULT_CANDIDATE,
    verified_store: Path = DEFAULT_VERIFIED,
) -> dict[str, Any]:
    report = run_promotion_dry_run(candidate_store, verified_store)
    payload = {
        "summary": {
            "actual_promotion_enabled_false": report.actual_promotion_enabled is False,
            "manual_approval_required": report.manual_approval_required is True,
            "production_store_mutated_false": report.production_store_mutated is False,
            "local_brain_write_false": report.local_brain_write is False,
            "candidate_promotion_false": report.candidate_promotion is False,
        },
        "report": report.to_dict(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"candidate_promotion_gate_proof_{ts}.json"
    md_path = output_dir / f"candidate_promotion_gate_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    report = payload["report"]
    lines = ["# Candidate Promotion Gate Dry-Run Proof", ""]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- New verified nodes estimate: {report['new_verified_nodes']}",
            f"- Merged existing nodes estimate: {report['merged_existing_nodes']}",
            f"- New relations estimate: {report['new_relations']}",
            f"- Strengthened relations estimate: {report['strengthened_relations']}",
            f"- New evidence estimate: {report['new_evidence']}",
            f"- New case frames estimate: {report['new_case_frames']}",
            f"- Rejected candidates: {report['rejected_candidates']}",
            f"- Conflicts: {report['conflicts']}",
            f"- Risky items: {report['risky_items']}",
            "",
            "This is generated audit output and must not be committed.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    payload = run_proof()
    report = payload["report"]
    compact = {
        "summary": payload["summary"],
        "counts": {
            "new_verified_nodes": report["new_verified_nodes"],
            "merged_existing_nodes": report["merged_existing_nodes"],
            "new_relations": report["new_relations"],
            "strengthened_relations": report["strengthened_relations"],
            "new_evidence": report["new_evidence"],
            "new_case_frames": report["new_case_frames"],
            "rejected_candidates": report["rejected_candidates"],
            "conflicts": report["conflicts"],
            "risky_items": report["risky_items"],
        },
        "outputs": payload["outputs"],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
