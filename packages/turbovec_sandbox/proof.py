from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .compression import cosine, quantize_int8, recall_at_k
from .planner import HotColdSplitPlan


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "turbovec_sandbox"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    fixture_vectors = [
        [0.2, 0.8, 0.1, 0.0],
        [0.9, 0.1, 0.0, 0.2],
        [0.0, 0.1, 0.9, 0.2],
    ]
    compressed = [quantize_int8(vector) for vector in fixture_vectors]
    reconstructed = [item.reconstructed for item in compressed]
    query = [0.18, 0.82, 0.08, 0.0]
    plan = HotColdSplitPlan(hot_vectors=1000, cold_vectors=9000, dimension=512)
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
    payload = {
        "summary": {
            "compression_deterministic": quantize_int8(fixture_vectors[0]).quantized == compressed[0].quantized,
            "bounded_distortion": min(cosine(a, b) for a, b in zip(fixture_vectors, reconstructed)) > 0.999,
            "recall_metric_computed": recall_at_k(query, reconstructed, expected_index=0, k=1) == 1.0,
            "compression_ratio_estimated": plan.compression_ratio > 1.0,
            "production_store_mutated_false": plan.production_store_mutated is False,
        },
        "compression": [item.to_dict() for item in compressed],
        "recall_at_1": recall_at_k(query, reconstructed, expected_index=0, k=1),
        "hot_cold_plan": plan.to_dict(),
        "invariants": invariants,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"turbovec_sandbox_proof_{ts}.json"
    md_path = output_dir / f"turbovec_sandbox_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Turbovec Sandbox Proof", ""]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            f"- recall@1: `{payload['recall_at_1']}`",
            f"- hot/cold compression ratio: `{payload['hot_cold_plan']['compression_ratio']:.3f}`",
            "",
            "This is proof-only and does not replace or mutate any production vector store.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_proof()
    print(json.dumps({"summary": result["summary"], "outputs": result["outputs"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
