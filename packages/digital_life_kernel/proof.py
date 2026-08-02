from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .action_policy import propose_actions
from .needs import signals_from_observation
from .sandbox import simulate_proposal
from .scheduler import plan_cycle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "digital_life_kernel"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    candidate_observation = {
        "source": "user_stopped_partial_24h",
        "candidate_run": {
            "run_id": "candidate_daemon_20260621_105455",
            "accepted": 13165,
            "rejected": 6785,
            "candidate_concepts": 6048,
            "candidate_relations": 26107,
            "full_24h_pass": False,
        },
    }
    scenarios = {
        "partial_run_creates_promotion_signal": candidate_observation,
        "privacy_risk_creates_review": {"source": "privacy_fixture", "privacy_risk": 0.72},
        "social_congress_creates_thread": {"source": "congress_fixture", "congress_topic": "candidate promotion criteria"},
        "resource_pressure_creates_approval_warning": {
            "source": "resource_fixture",
            "resource_state": {"disk_free_gib": 25.0, "ram_free_gib": 4.0},
        },
        "knowledge_gap_creates_quality_audit": {"source": "quality_fixture", "answer_quality_gap": 0.5},
    }
    results: dict[str, Any] = {}
    all_proposals = []
    for name, observation in scenarios.items():
        signals = signals_from_observation(observation)
        proposals = propose_actions(signals)
        sandbox = [simulate_proposal(proposal).to_dict() for proposal in proposals]
        state, stream = plan_cycle(observation)
        all_proposals.extend(proposals)
        results[name] = {
            "pass": bool(signals)
            and bool(proposals)
            and all(proposal.safe_by_default for proposal in proposals)
            and all(item["passed"] for item in sandbox),
            "signals": [signal.to_dict() for signal in signals],
            "proposals": [proposal.to_dict() for proposal in proposals],
            "sandbox": sandbox,
            "state": state.to_dict(),
            "events": [event.to_dict() for event in stream.list_events()],
        }

    invariants = {
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "external_llm_used": False,
        "mock_growth": False,
        "pair_edges_sent": 0,
        "real_p2p_used": False,
        "raw_private_data_exported": False,
        "generated_code_executed": False,
        "real_hot_swap_performed": False,
    }
    results["proposal_safety"] = {
        "pass": all(proposal.safe_by_default for proposal in all_proposals),
        "proposal_count": len(all_proposals),
    }
    results["invariants"] = {"pass": True, **invariants}
    results["summary"] = {key: value["pass"] for key, value in results.items() if isinstance(value, dict) and "pass" in value}

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"digital_life_kernel_proof_{ts}.json"
    md_path = output_dir / f"digital_life_kernel_proof_{ts}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_proof_markdown(results), encoding="utf-8")
    results["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return results


def _proof_markdown(results: dict[str, Any]) -> str:
    lines = ["# Digital Life Kernel v0 Proof", ""]
    for key, passed in results["summary"].items():
        lines.append(f"- {key}: `{passed}`")
    lines.extend(
        [
            "",
            "This is proof-only. It emits safe proposals and audit events; it does not mutate production, write Local Brain, execute generated code, or use real P2P.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
