from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.selfhood_control.models import SelfhoodRunReport
from packages.selfhood_control.orchestrator import SelfhoodControlPlane, build_invariants
from packages.selfhood_control.policy import SelfhoodSafetyPolicy
from packages.selfhood_control.scenario import all_scenarios


def run_proof(output_dir: str | Path = "data/audits/selfhood_control") -> dict[str, Any]:
    control = SelfhoodControlPlane(SelfhoodSafetyPolicy())
    reports: list[SelfhoodRunReport] = []
    decisions = []
    for scenario, input_event, context in all_scenarios():
        decision = control.run_once(input_event, context)
        decisions.append(decision)
        reports.append(
            SelfhoodRunReport(
                f"run_{scenario}",
                scenario,
                [decision],
                build_invariants([decision]),
                passed=_invariants_pass(build_invariants([decision])),
                limitations=["proof-only", "not production AGI", "not a consciousness claim"],
            )
        )
    proof = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario_reports": [report.to_dict() for report in reports],
        "invariants": build_invariants(decisions),
        "passed": all(report.passed for report in reports) and _invariants_pass(build_invariants(decisions)),
        "limitations": [
            "proof-only orchestration",
            "not production AGI",
            "not a consciousness claim",
            "no real peer-network transport",
            "no production promotion",
        ],
    }
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_root / f"selfhood_control_proof_{stamp}.json"
    md_path = output_root / f"selfhood_control_proof_{stamp}.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(proof), encoding="utf-8")
    proof["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return proof


def _invariants_pass(invariants: dict[str, object]) -> bool:
    return (
        invariants["production_store_mutated"] is False
        and invariants["local_brain_write"] is False
        and invariants["candidate_promotion"] is False
        and invariants["external_llm_used"] is False
        and invariants["mock_growth"] is False
        and invariants["pair_edges_sent"] == 0
        and invariants["active_24h_run_not_modified"] is True
        and invariants["raw_private_data_exported"] is False
        and invariants["real_p2p_used"] is False
        and invariants["real_cloud_upload"] is False
        and invariants["real_hot_swap_performed"] is False
        and invariants["generated_code_executed"] is False
        and invariants["always_listening_enabled"] is False
    )


def _markdown(proof: dict[str, Any]) -> str:
    lines = ["# ATANOR Selfhood Control Plane Proof", "", f"- passed: `{proof['passed']}`", "", "## Invariants"]
    lines.extend(f"- {key}: `{value}`" for key, value in proof["invariants"].items())
    lines.extend(["", "## Scenarios"])
    for report in proof["scenario_reports"]:
        decision = report["decisions"][0]
        lines.append(f"- {report['scenario']}: `{decision['action']}`")
    lines.append("")
    lines.append("Generated proof output is audit data and must not be committed.")
    return "\n".join(lines) + "\n"


def main() -> None:
    proof = run_proof()
    print(json.dumps({"verdict": "PASS" if proof["passed"] else "FAIL", "outputs": proof["outputs"], "invariants": proof["invariants"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
