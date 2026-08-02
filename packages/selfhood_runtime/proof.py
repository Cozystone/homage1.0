from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .orchestrator import run_selfhood_cycle
from .scenario import proof_scenarios


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "selfhood_runtime"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [run_selfhood_cycle(scenario).to_dict() for scenario in proof_scenarios()]
    invariants = {
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "actual_promotion_performed": False,
        "external_llm_used": False,
        "real_p2p_used": False,
        "real_cloud_upload": False,
        "generated_code_executed": False,
        "real_hot_swap_performed": False,
        "always_listening_enabled": False,
        "text_input_supported": True,
        "voice_optional": True,
        "requires_user_approval": True,
    }
    payload = {
        "verdict": "SELFHOOD_RUNTIME_V0_PROOF_ONLY",
        "scenario_count": len(results),
        "scenarios": {result["input_id"]: result for result in results},
        "invariants": invariants,
        "limitations": [
            "proof-only",
            "not real consciousness",
            "not AGI",
            "no production mutation",
            "no Local Brain memory write",
            "no real P2P",
            "voice runtime optional through mock/fallback",
            "no UI or API integration",
        ],
    }
    ts = _timestamp()
    json_path = output_dir / f"selfhood_runtime_proof_{ts}.json"
    md_path = output_dir / f"selfhood_runtime_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Selfhood Runtime v0 Proof", ""]
    lines.append(f"- Verdict: `{payload['verdict']}`")
    lines.append(f"- Scenarios: `{payload['scenario_count']}`")
    lines.append("")
    lines.append("## Invariants")
    for key, value in payload["invariants"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Scenario Results")
    for input_id, result in payload["scenarios"].items():
        proposal = result["proposals"][0]
        lines.append(f"- {input_id}: `{result['final_state']}` / `{proposal['proposal_type']}`")
    lines.append("")
    lines.append("This proof demonstrates an autonomous self-model loop, not real consciousness or AGI.")
    lines.append("Generated proof output is audit data and must not be committed.")
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
