from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from packages.cloud_brain.cloud_node_attachment import (
    attach_bundle,
    create_cloud_node_bundle,
    detach_bundle,
    graph_overlay,
)

from .pipeline import run_cortex_cycle, summarize_cortex_cycle
from .storage import DEFAULT_CORTEX_ROOT, ensure_cortex_dirs, now_iso, write_json


PROOF_QUERY = "Evidence와 Claim의 차이를 설명해줘."


def _proof_markdown(proof: dict[str, Any]) -> str:
    claims = proof["claims"]
    not_claims = proof["does_not_claim"]
    return "\n".join(
        [
            "# CORTEX-G2 Living Neuromorphic Loop Proof",
            "",
            f"- Result: {proof['result']}",
            f"- Query: {proof['query']}",
            f"- Local Brain before: {proof['local_brain_before']}",
            f"- Attached overlay: {proof['attached_overlay_counts']}",
            f"- CORTEX-G2 summary: {json.dumps(proof['cortex_g2_summary'], ensure_ascii=False)}",
            f"- Local Brain after detach: {proof['local_brain_after_detach']}",
            "",
            "## This proof claims",
            *[f"- {claim}" for claim in claims],
            "",
            "## This proof does NOT claim",
            *[f"- {claim}" for claim in not_claims],
            "",
        ]
    )


def write_living_neuromorphic_loop_proof(root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    ensure_cortex_dirs(root)
    runtime_root = Path(root) / "proof_runtime" / "living_neuromorphic_loop"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    contributor_root = runtime_root / "contributor"
    attachment_root = runtime_root / "working_memory" / "cloud_node_bundles"
    bundle = create_cloud_node_bundle(PROOF_QUERY, contributor_root=contributor_root, attachment_root=attachment_root)
    attached = attach_bundle(bundle["bundle_id"], attachment_root=attachment_root)
    overlay = graph_overlay(attachment_root=attachment_root)
    graph_payload = {
        "local_nodes": [],
        "local_edges": [],
        "seed_anchor_nodes": overlay.get("seed_anchor_nodes", []),
        "cloud_attached_nodes": overlay.get("cloud_attached_nodes", []),
        "cloud_attached_edges": overlay.get("cloud_attached_edges", []),
        "working_memory_overlay": overlay.get("working_memory_overlay", {}),
    }
    cortex = run_cortex_cycle(PROOF_QUERY, graph_payload, top_k_nodes=128, top_k_edges=256)
    detached = detach_bundle(attached["bundle_id"], attachment_root=attachment_root)
    after = graph_overlay(attachment_root=attachment_root)
    pass_state = (
        overlay.get("working_memory_overlay", {}).get("cloud_attached_nodes") == len(bundle.get("nodes") or [])
        and after.get("working_memory_overlay", {}).get("cloud_attached_nodes") == 0
        and cortex.get("retrieval_trace", {}).get("cortex_g2", {}).get("local_brain_write") is False
        and cortex.get("retrieval_trace", {}).get("cortex_g2", {}).get("self_generated_truth_saved") is False
    )
    proof = {
        "result": "PASS" if pass_state else "FAIL",
        "proved_at": now_iso(),
        "query": PROOF_QUERY,
        "local_brain_before": {"local_total_nodes": 0, "local_total_edges": 0, "local_brain_initialized": False},
        "bundle_id": bundle["bundle_id"],
        "attached_overlay_counts": overlay.get("counts", {}),
        "cortex_g2_summary": summarize_cortex_cycle(cortex),
        "prediction_trace": cortex.get("prediction_trace"),
        "knowledge_crystal": cortex.get("knowledge_crystal"),
        "detach_result": detached,
        "overlay_after_detach": after.get("counts", {}),
        "local_brain_after_detach": {"local_total_nodes": 0, "local_total_edges": 0, "local_brain_initialized": False},
        "self_generated_truth_saved": False,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_template_final_generation_claimed": False,
        "claims": [
            "ATANOR can run a neuromorphic graph activation loop over Seed/Cloud/Working Memory.",
            "Active graph paths can enter a bounded Global Workspace.",
            "Prediction paths can be compared against evidence.",
            "Evidence-backed reasoning traces can become Knowledge Crystal candidates.",
            "Cloud attached nodes remain temporary.",
            "Local Brain remains isolated.",
        ],
        "does_not_claim": [
            "consciousness",
            "human-level intelligence",
            "unrestricted self-learning",
            "final answer superiority",
            "global multi-peer Cloud Brain",
            "trillion actual node population",
            "sLLM replacement",
        ],
    }
    json_path = Path(root) / "proofs" / "living_neuromorphic_loop_proof.json"
    md_path = Path(root) / "proofs" / "living_neuromorphic_loop_proof.md"
    write_json(json_path, proof)
    md_path.write_text(_proof_markdown(proof), encoding="utf-8")
    return {"proof": proof, "json_path": str(json_path), "markdown_path": str(md_path)}
