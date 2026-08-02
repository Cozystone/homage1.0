from __future__ import annotations

import json
from typing import Any

from packages.answer_quality.comparison import run_repair_comparison

from .models import utc_now_iso
from .monitor import repair_answer_for_mode
from .storage import SURFACE_ROOT, ensure_dirs, write_json


def run_surface_repair_proof() -> dict[str, Any]:
    ensure_dirs()
    scenarios = {
        "cloud_brain_leakage": "Cloud Brain 문맥을 붙이면 쿠버네티스는 컨테이너를 관리하는 시스템이라고 설명할 수 있습니다.",
        "q_cortex_leakage": "Q-Cortex objective가 이 construction을 선택했기 때문에 쉽게 말하면으로 시작합니다.",
        "source_hash_leakage": "source_hash abc123에 따르면 쿠버네티스는 컨테이너 관리 시스템입니다.",
    }
    repaired = {
        name: repair_answer_for_mode(text, mode="default", trace={})
        for name, text in scenarios.items()
    }
    comparison = run_repair_comparison(limit=8)
    pass_state = (
        "Cloud Brain" not in repaired["cloud_brain_leakage"]["repaired_answer"]
        and "Q-Cortex" not in repaired["q_cortex_leakage"]["repaired_answer"]
        and "objective" not in repaired["q_cortex_leakage"]["repaired_answer"]
        and "source_hash" not in repaired["source_hash_leakage"]["repaired_answer"]
        and repaired["cloud_brain_leakage"]["moved_to_trace"]
        and repaired["q_cortex_leakage"]["moved_to_trace"]
        and repaired["source_hash_leakage"]["moved_to_trace"]
        and comparison["trace_hygiene_after"] >= comparison["trace_hygiene_before"]
        and comparison["auto_promoted_feedback"] is False
    )
    proof = {
        "result": "PASS" if pass_state else "FAIL",
        "proved_at": utc_now_iso(),
        "scenarios": repaired,
        "repair_comparison": {
            "run_id": comparison["run_id"],
            "trace_hygiene_before": comparison["trace_hygiene_before"],
            "trace_hygiene_after": comparison["trace_hygiene_after"],
            "trace_hygiene_delta": comparison["trace_hygiene_delta"],
            "overall_delta": comparison["overall_delta"],
            "repairs_applied": comparison["repairs_applied"],
            "remaining_leakages": len(comparison["remaining_leakages"]),
            "json_path": comparison["json_path"],
            "markdown_path": comparison["markdown_path"],
        },
        "claims": [
            "ATANOR can detect and repair internal trace leakage in default answers.",
            "Repair rules can move internal details to trace instead of deleting useful answer content.",
            "Answer Quality Lab can compare before/after repair quality.",
            "Repair candidates are reviewable.",
        ],
        "does_not_claim": [
            "GPT-level answer quality",
            "perfect natural language generation",
            "perfect factuality evaluation",
            "autonomous safe self-improvement",
            "external LLM judging",
        ],
    }
    proof_dir = SURFACE_ROOT / "proofs"
    json_path = proof_dir / "surface_repair_proof.json"
    md_path = proof_dir / "surface_repair_proof.md"
    write_json(json_path, proof)
    md_path.write_text(_markdown(proof), encoding="utf-8")
    return {"proof": proof, "json_path": str(json_path), "markdown_path": str(md_path)}


def _markdown(proof: dict[str, Any]) -> str:
    comparison = proof["repair_comparison"]
    return "\n".join([
        "# Surface Repair Loop Proof",
        "",
        f"- Result: {proof['result']}",
        f"- Trace hygiene before: {comparison['trace_hygiene_before']}",
        f"- Trace hygiene after: {comparison['trace_hygiene_after']}",
        f"- Trace hygiene delta: {comparison['trace_hygiene_delta']}",
        f"- Repairs applied: {comparison['repairs_applied']}",
        f"- Remaining leakages: {comparison['remaining_leakages']}",
        "",
        "## This proof claims",
        *[f"- {claim}" for claim in proof["claims"]],
        "",
        "## This proof does NOT claim",
        *[f"- {claim}" for claim in proof["does_not_claim"]],
        "",
    ])


def main() -> None:
    print(json.dumps(run_surface_repair_proof(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
