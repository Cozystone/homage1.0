from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.spark_chamber.chamber import SparkChamber
from packages.spark_chamber.contradiction import detect_contradictions
from packages.spark_chamber.entropy import collect_environmental_entropy
from packages.spark_chamber.homeostasis import decide_homeostasis
from packages.spark_chamber.models import ChaosBudget, SparkInput
from packages.spark_chamber.mutation import apply_mutation
from packages.spark_chamber.strange_loop import probe_strange_loop


def _fixture(seed: int = 42) -> SparkInput:
    return SparkInput(
        "spark_fixture",
        "proof_fixture",
        {
            "phase": 0.5,
            "relations": ["supports", "contradicts"],
            "priorities": [1, 2, 3],
            "optional_fields": ["weak_evidence"],
            "contradictions": [{"claim": "A", "negates": "A", "fixture_only": True}],
            "self_reference": {"self_reference": {"self_reference": {}}},
        },
        deterministic_seed=seed,
        metadata={"uncertainty": 0.6, "user_goal_pressure": 0.6},
    )


def triage_items() -> list[dict[str, str]]:
    return [
        {"concept": "prediction error as deficit source", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "deficit pressure source"},
        {"concept": "stochastic noise", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "bounded stochastic fixture only"},
        {"concept": "hardware entropy / jitter seed", "classification": "DEFER_UNTIL_PROMOTION_GATE", "safe_rewording": "optional environmental jitter, disabled by default"},
        {"concept": "virtual bit flip", "classification": "DEFER_UNTIL_PROMOTION_GATE", "safe_rewording": "virtual fixture bit flip behind explicit budget"},
        {"concept": "mutational imperfection", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "sandboxed bounded mutation"},
        {"concept": "edge of chaos", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "bounded uncertainty band"},
        {"concept": "strange loop / self-reference", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "bounded self-reference probe"},
        {"concept": "IIT-inspired integration score", "classification": "DEFER_UNTIL_ANSWER_QUALITY", "safe_rewording": "IIT-inspired integration metric"},
        {"concept": "free-energy / prediction-error minimization", "classification": "ALREADY_EXISTS_PARTIALLY", "safe_rewording": "deficit minimization policy"},
        {"concept": "self-healing", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "proposal-only review suggestion"},
        {"concept": "self-generated patch", "classification": "DEFER_UNTIL_PROMOTION_GATE", "safe_rewording": "proposal-only patch requiring review"},
        {"concept": "production code replacement", "classification": "REJECT_OR_REWORD", "safe_rewording": "blocked production code replacement"},
        {"concept": "autonomous refusal / homeostasis", "classification": "ADOPT_NOW_PROOF_ONLY", "safe_rewording": "bounded homeostasis control policy"},
        {"concept": "non-human internal protocol", "classification": "DEFER_UNTIL_ANSWER_QUALITY", "safe_rewording": "internal review protocol"},
    ]


def run_proof(output_dir: str | Path = "data/audits/spark_chamber") -> dict[str, Any]:
    budget = ChaosBudget(max_mutation_rate=0.2, max_mutated_fields=2, max_risk_score=0.25)
    chamber = SparkChamber()
    first = chamber.run(_fixture(123), budget)
    second = chamber.run(_fixture(123), budget)
    phase_event = apply_mutation(_fixture(123), budget, "phase_jitter")
    contradiction = detect_contradictions(_fixture().content)
    loop = probe_strange_loop(_fixture().content, max_depth=3)
    homeostasis = decide_homeostasis({"disk_free_gib": 80.0}, 0.8, 0.8, 0.2, 0.2)
    risky_rejected = False
    try:
        apply_mutation(_fixture(), budget, "virtual_bit_flip")
    except ValueError:
        risky_rejected = True
    proof = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "triage": triage_items(),
        "environmental_entropy": collect_environmental_entropy(),
        "scenarios": {
            "deterministic_spark": first.to_dict() == second.to_dict(),
            "bounded_phase_jitter": {
                "changed": phase_event.before["phase"] != phase_event.after["phase"],
                "original_unchanged": _fixture(123).content["phase"] == 0.5,
                "risk_score": phase_event.risk_score,
            },
            "contradiction_probe": contradiction,
            "strange_loop_bounded": loop,
            "homeostasis": homeostasis.to_dict(),
            "risky_mutation_rejected": risky_rejected,
            "candidate_insight": first.insights[0].to_dict() if first.insights else None,
        },
        "report": first.to_dict(),
        "invariants": first.invariants,
        "passed": first.passed and risky_rejected and first.to_dict() == second.to_dict(),
    }
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_root / f"spark_chamber_proof_{stamp}.json"
    md_path = output_root / f"spark_chamber_proof_{stamp}.md"
    triage_path = output_root / f"spark_hypothesis_triage_{stamp}.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_proof_markdown(proof), encoding="utf-8")
    triage_path.write_text(_triage_markdown(proof["triage"]), encoding="utf-8")
    proof["outputs"] = {"json": str(json_path), "md": str(md_path), "triage": str(triage_path)}
    return proof


def _proof_markdown(proof: dict[str, Any]) -> str:
    lines = ["# Spark Chamber Proof", "", f"- passed: `{proof['passed']}`", "", "## Invariants"]
    lines.extend(f"- {key}: `{value}`" for key, value in proof["invariants"].items())
    lines.extend(["", "## Scenarios"])
    for key, value in proof["scenarios"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("Generated proof output is audit data and must not be committed.")
    return "\n".join(lines) + "\n"


def _triage_markdown(items: list[dict[str, str]]) -> str:
    lines = ["# Spark / Gap / Controlled Chaos Hypothesis Triage", ""]
    for item in items:
        lines.append(f"- {item['concept']}: `{item['classification']}` -> {item['safe_rewording']}")
    lines.append("")
    lines.append("This triage rewords broad metaphors into proof-only engineering controls.")
    return "\n".join(lines) + "\n"


def main() -> None:
    proof = run_proof()
    print(json.dumps({"verdict": "PASS" if proof["passed"] else "FAIL", "outputs": proof["outputs"], "invariants": proof["invariants"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
