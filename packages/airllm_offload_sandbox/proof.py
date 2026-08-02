from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .planner import HardwareProfile, ModelProfile, plan_offload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "airllm_offload_sandbox"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    laptop = HardwareProfile(ram_gib=32.0, vram_gib=8.0, disk_free_gib=80.0)
    too_large_laptop = HardwareProfile(ram_gib=16.0, vram_gib=4.0, disk_free_gib=8.0)
    medium_model = ModelProfile("fixture-7b", parameter_billion=7.0, quantization_bits=4, layer_count=32)
    huge_model = ModelProfile("fixture-70b", parameter_billion=70.0, quantization_bits=4, layer_count=80)
    ok_plan = plan_offload(medium_model, laptop)
    blocked_plan = plan_offload(huge_model, too_large_laptop)
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
        "model_downloaded": False,
        "production_answer_path_integrated": False,
    }
    payload = {
        "summary": {
            "medium_model_advisory_ok": ok_plan.status == "advisory_ok",
            "too_large_model_blocked": blocked_plan.status == "blocked",
            "advisory_only": ok_plan.advisory_only and blocked_plan.advisory_only,
            "no_model_download": not ok_plan.model_downloaded and not blocked_plan.model_downloaded,
            "no_production_answer_path": not ok_plan.production_answer_path_integrated
            and not blocked_plan.production_answer_path_integrated,
        },
        "hardware": {"laptop": laptop.to_dict(), "constrained": too_large_laptop.to_dict()},
        "models": {"medium": medium_model.to_dict(), "huge": huge_model.to_dict()},
        "plans": {"medium": ok_plan.to_dict(), "huge": blocked_plan.to_dict()},
        "invariants": invariants,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"airllm_offload_sandbox_proof_{ts}.json"
    md_path = output_dir / f"airllm_offload_sandbox_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# AirLLM Offload Sandbox Proof", ""]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "This is advisory-only. It does not download models, execute model code, or integrate with the production answer path.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_proof()
    print(json.dumps({"summary": result["summary"], "outputs": result["outputs"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
