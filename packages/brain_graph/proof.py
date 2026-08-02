from __future__ import annotations

import json
from typing import Any

from .aggregator import aggregate_brain_graph, brain_graph_status
from .models import CLOUD_LAYERS, LOCAL_LAYERS, PROOF_JSON_PATH, PROOF_MD_PATH, ensure_brain_graph_dirs, utc_now_iso


def run_tab_aware_brain_graph_proof() -> dict[str, Any]:
    ensure_brain_graph_dirs()
    local_graph = aggregate_brain_graph(view="local", layers=[*LOCAL_LAYERS, "invalid_local_layer"], max_nodes=500, max_edges=1000)
    cloud_graph = aggregate_brain_graph(view="cloud", layers=[*CLOUD_LAYERS, "invalid_cloud_layer"], max_nodes=500, max_edges=1000)
    local_layers = set(local_graph["stats"]["layer_counts"].keys())
    cloud_layers = set(cloud_graph["stats"]["layer_counts"].keys())
    checks = {
        "local_view_has_no_semantic_cloud_nodes": "semantic_cloud" not in local_layers,
        "local_view_has_no_cloud_attached_counted_as_local": local_graph["stats"].get("cloud_attached_counts_as_local") is False,
        "cloud_view_can_show_cloud_layers": bool(cloud_layers & {"semantic_cloud", "cloud_attached", "working_memory_cloud", "contributor"}),
        "surface_graph_summary_only": cloud_graph["honesty"].get("surface_graph_full_render_disabled") is True,
        "missing_layers_reported": bool(local_graph["layers_missing"]) and bool(cloud_graph["layers_missing"]),
        "overlay_local_write_false": local_graph["stats"]["overlay"].get("local_brain_write") is False,
    }
    passed = all(checks.values())
    proof = {
        "proof_id": "tab_aware_brain_graph_proof",
        "generated_at": utc_now_iso(),
        "passed": passed,
        "checks": checks,
        "local_graph_summary": {
            "rendered_nodes": local_graph["stats"]["rendered_nodes"],
            "rendered_edges": local_graph["stats"]["rendered_edges"],
            "layers": local_graph["stats"]["layer_counts"],
            "missing": local_graph["layers_missing"],
        },
        "cloud_graph_summary": {
            "rendered_nodes": cloud_graph["stats"]["rendered_nodes"],
            "rendered_edges": cloud_graph["stats"]["rendered_edges"],
            "layers": cloud_graph["stats"]["layer_counts"],
            "missing": cloud_graph["layers_missing"],
        },
        "honesty": {
            "tab_aware_pipeline": True,
            "surface_graph_full_render_disabled": True,
            "cloud_attached_counts_as_local": False,
            "missing_layers_are_not_silent": True,
            "external_llm_used": False,
            "external_sllm_used": False,
        },
        "claim": "Local and Cloud Brain tabs receive separate renderable graph layers. Missing layers are reported instead of silently falling back.",
        "does_not_claim": [
            "Surface Cloud Graph is fully rendered",
            "Cloud attached nodes are Local Brain memory",
            "remote global Cloud Brain is verified",
        ],
    }
    PROOF_JSON_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# ATANOR Tab-Aware Brain Graph Proof",
        "",
        f"- Generated: {proof['generated_at']}",
        f"- Result: {'PASS' if passed else 'FAIL'}",
        "",
        "## Checks",
        *[f"- {'PASS' if value else 'FAIL'}: {key}" for key, value in checks.items()],
        "",
        "## Honest Scope",
        "- Local Brain render view excludes Semantic Cloud Graph nodes.",
        "- Cloud attached nodes remain temporary Working Memory overlays.",
        "- Surface Brain is summarized in the side panel, not fully rendered as graph nodes.",
    ]
    PROOF_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return proof


def main() -> None:
    proof = run_tab_aware_brain_graph_proof()
    print(json.dumps({"passed": proof["passed"], "proof_json": str(PROOF_JSON_PATH), "status": brain_graph_status()["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
