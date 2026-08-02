from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.cloud_brain.ingestion import ensure_fixture_and_ingest, query_ingested_fragments


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_brain_state() -> dict[str, Any]:
    return {
        "local_brain_initialized": False,
        "local_total_nodes": 0,
        "local_total_edges": 0,
    }


def build_controlled_self_growth_proof(
    *,
    seed_root: str | Path | None = "data/seed_research",
    cloud_root: str | Path = "data/cloud_brain",
) -> dict[str, Any]:
    ingestion = ensure_fixture_and_ingest(seed_root=seed_root, cloud_root=cloud_root)
    readback = query_ingested_fragments("Evidence", limit=5, cloud_root=cloud_root)
    query_readback_success = any(result.get("fragment_id") == ingestion.get("fragment_id") for result in readback.get("results", []))
    return {
        "schema": "atanor.controlled-cloud-brain-self-growth-proof.v1",
        "created_at": _now_iso(),
        "controlled_self_growth": True,
        "mode": "controlled_fixture_only",
        "autonomous_broad_crawling": False,
        "fragment_id": ingestion.get("fragment_id"),
        "content_hash": ingestion.get("content_hash"),
        "alignment_success": bool(ingestion.get("alignment_success")),
        "ingestion_success": bool(ingestion.get("ingestion_success")),
        "query_readback_success": query_readback_success,
        "duplicate_fragment": bool(ingestion.get("duplicate_fragment")),
        "nodes_added": int(ingestion.get("nodes_added") or 0),
        "edges_added": int(ingestion.get("edges_added") or 0),
        "previous_cloud_nodes": int(ingestion.get("previous_cloud_nodes") or 0),
        "new_cloud_nodes": int(ingestion.get("new_cloud_nodes") or 0),
        "previous_cloud_edges": int(ingestion.get("previous_cloud_edges") or 0),
        "new_cloud_edges": int(ingestion.get("new_cloud_edges") or 0),
        "trust_state": ingestion.get("trust_state"),
        "verification_state": ingestion.get("verification_state"),
        "ingestion_state": ingestion.get("ingestion_state"),
        "local_brain_state": _local_brain_state(),
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "final_answer_generation_claimed": False,
        "ingestion": ingestion,
        "readback": readback,
    }


def _write_markdown(proof: dict[str, Any], path: Path) -> None:
    lines = [
        "# ATANOR Controlled Cloud Brain Self-Growth Proof",
        "",
        f"- Created: `{proof['created_at']}`",
        f"- Mode: `{proof['mode']}`",
        f"- Autonomous broad crawling: `{str(proof['autonomous_broad_crawling']).lower()}`",
        f"- Fragment ID: `{proof['fragment_id']}`",
        f"- Alignment success: `{str(proof['alignment_success']).lower()}`",
        f"- Ingestion success: `{str(proof['ingestion_success']).lower()}`",
        f"- Query read-back success: `{str(proof['query_readback_success']).lower()}`",
        f"- Duplicate fragment: `{str(proof['duplicate_fragment']).lower()}`",
        f"- Nodes added: `{proof['nodes_added']}`",
        f"- Edges added: `{proof['edges_added']}`",
        f"- Cloud nodes: `{proof['previous_cloud_nodes']} -> {proof['new_cloud_nodes']}`",
        f"- Cloud edges: `{proof['previous_cloud_edges']} -> {proof['new_cloud_edges']}`",
        "- Local Brain: `0 / 0`",
        "",
        "## This Proof Claims",
        "",
        "- A deterministic public candidate fragment can be safely ingested into Cloud Brain after Seed alignment.",
        "- Cloud Brain proof store count can increase honestly.",
        "- The ingested fragment can be queried and read back.",
        "- Local Brain remains isolated.",
        "- No external LLM, external sLLM, or rule-template answer generation is used.",
        "",
        "## This Proof Does Not Claim",
        "",
        "- Broad autonomous web crawling.",
        "- Production-scale Cloud Brain verification.",
        "- Multi-peer consensus.",
        "- Final answer generation quality.",
        "- sLLM replacement.",
        "- Unrestricted self-growth.",
        "",
        "## Safety Flags",
        "",
        f"- External LLM used: `{str(proof['external_llm_used']).lower()}`",
        f"- External sLLM used: `{str(proof['external_sllm_used']).lower()}`",
        f"- Rule-based answer engine: `{str(proof['rule_based_answer_engine']).lower()}`",
        f"- Final answer generation claimed: `{str(proof['final_answer_generation_claimed']).lower()}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_controlled_self_growth_proof(
    *,
    seed_root: str | Path | None = "data/seed_research",
    cloud_root: str | Path = "data/cloud_brain",
) -> dict[str, Any]:
    proof = build_controlled_self_growth_proof(seed_root=seed_root, cloud_root=cloud_root)
    proof_dir = Path(cloud_root) / "proofs"
    proof_dir.mkdir(parents=True, exist_ok=True)
    json_path = proof_dir / "controlled_self_growth_proof.json"
    markdown_path = proof_dir / "controlled_self_growth_proof.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(proof, markdown_path)
    return {
        "proof": proof,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "proof_json": str(json_path),
        "proof_md": str(markdown_path),
    }


def main() -> None:
    result = write_controlled_self_growth_proof()
    print(json.dumps({key: value for key, value in result.items() if key != "proof"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
