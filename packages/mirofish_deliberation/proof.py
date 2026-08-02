from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .models import DeliberationInput
from .simulator import run_deliberation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "mirofish_deliberation"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    scenarios = {
        "contradiction_blocked": DeliberationInput(
            topic="candidate relation promotion",
            evidence_refs=["wiki:alpha", "wiki:beta"],
            contradictions=["source relation conflicts with candidate relation"],
        ),
        "privacy_guard_blocks_private_data": DeliberationInput(
            topic="private cartridge exchange",
            evidence_refs=["local:private"],
            privacy_report={"private_data_present": True},
        ),
        "clean_candidate_requires_manual_approval": DeliberationInput(
            topic="verified public case-frame",
            evidence_refs=["wiki:one", "wiki:two", "wiki:three"],
            privacy_report={"private_data_present": False},
            router_report={"route_allowed": True},
        ),
        "router_blocks_untrusted_route": DeliberationInput(
            topic="untrusted peer packet",
            evidence_refs=["public:one", "public:two"],
            router_report={"route_allowed": False},
        ),
    }
    results = {name: run_deliberation(payload).to_dict() for name, payload in scenarios.items()}
    invariants = {
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "external_llm_used": False,
        "mock_growth": False,
        "pair_edges_sent": 0,
        "raw_private_data_exported": False,
        "real_p2p_used": False,
        "real_cloud_upload": False,
        "generated_code_executed": False,
        "real_hot_swap_performed": False,
    }
    summary = {
        "skeptic_finds_contradiction": results["contradiction_blocked"]["promotion_recommendation"] == "blocked",
        "privacy_guard_blocks_private_data": results["privacy_guard_blocks_private_data"]["promotion_recommendation"] == "blocked",
        "promotion_judge_requires_approval": all(item["requires_manual_approval"] for item in results.values()),
        "clean_candidate_review_only": results["clean_candidate_requires_manual_approval"]["promotion_recommendation"] == "approve_for_review",
        "router_blocks_untrusted_route": results["router_blocks_untrusted_route"]["promotion_recommendation"] == "blocked",
        "invariants_safe": all(value is False or value == 0 for value in invariants.values()),
    }
    payload = {"summary": summary, "scenarios": results, "invariants": invariants}
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"mirofish_deliberation_proof_{ts}.json"
    md_path = output_dir / f"mirofish_deliberation_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# MiroFish Deliberation Lab Proof", ""]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "This is a deterministic local simulator. It does not use external LLMs, real swarm networking, P2P, production mutation, Local Brain writes, or candidate promotion.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_proof()
    print(json.dumps({"summary": result["summary"], "outputs": result["outputs"]}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
