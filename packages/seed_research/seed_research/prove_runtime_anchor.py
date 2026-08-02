from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import seed_root
from .runtime_anchor import align_cloud_candidates, resolve_seed_concepts


DEFAULT_QUERIES = [
    "How does GraphRAG use evidence to verify claims?",
    "What is the difference between Local Brain and Cloud Brain?",
    "How does Payload Vault protect private project memory?",
    "How should unverified public fragments be handled?",
    "What does Ghost Shell keep in memory?",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_runtime_anchor_proof(root: str | Path | None = None, cloud_root: str | Path = "data/cloud_brain") -> dict[str, Any]:
    base = seed_root(root)
    traces: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        resolved = resolve_seed_concepts(query, base)
        cloud_alignment = align_cloud_candidates(resolved, cloud_root)
        traces.append(
            {
                "query": query,
                "seed_used": bool(resolved.get("matched_seed_concepts")),
                "matched_seed_concepts": resolved.get("matched_seed_concepts", []),
                "matched_seed_edges": resolved.get("matched_seed_edges", []),
                "cloud_alignment_trace": cloud_alignment,
                "final_answer_generation_claimed": False,
                "external_llm_used": False,
                "external_sllm_used": False,
                "rule_based_answer_engine": False,
            }
        )

    return {
        "schema": "atanor.seed-runtime-anchor-proof.v1",
        "created_at": _now_iso(),
        "seed_root": str(base),
        "local_graph_state": {
            "local_brain_initialized": False,
            "local_total_nodes": 0,
            "local_total_edges": 0,
            "seed_written_to_local_brain": False,
            "seed_counted_as_learned_memory": False,
        },
        "claims": {
            "seed_graph_participates_in_runtime_retrieval": any(trace["seed_used"] for trace in traces),
            "final_answer_generation_quality_claimed": False,
            "sllm_replacement_claimed": False,
            "autonomous_cloud_brain_growth_claimed": False,
            "broad_web_crawling_claimed": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_engine": False,
        },
        "traces": traces,
    }


def _write_markdown(proof: dict[str, Any], path: Path) -> None:
    lines = [
        "# ATANOR Seed Runtime Anchor Proof",
        "",
        f"- Created: `{proof['created_at']}`",
        f"- Seed root: `{proof['seed_root']}`",
        "- Local Brain initialized: `false`",
        "- Local Brain nodes/edges: `0 / 0`",
        "- Seed written to Local Brain: `false`",
        "",
        "## Scope",
        "",
        "This proof shows that the Seed Graph can participate in runtime retrieval and verification traces as a concept-alignment anchor.",
        "It does not claim final natural-language generation quality, autonomous Cloud Brain growth, broad web crawling, or sLLM replacement.",
        "",
        "## Safety Claims",
        "",
        f"- External LLM used: `{str(proof['claims']['external_llm_used']).lower()}`",
        f"- External sLLM used: `{str(proof['claims']['external_sllm_used']).lower()}`",
        f"- Rule-template answer engine: `{str(proof['claims']['rule_based_answer_engine']).lower()}`",
        f"- Final answer generation claimed: `{str(proof['claims']['final_answer_generation_quality_claimed']).lower()}`",
        "",
        "## Runtime Query Traces",
        "",
    ]
    for index, trace in enumerate(proof["traces"], start=1):
        lines.extend(
            [
                f"### Trace {index}",
                "",
                f"- Query: `{trace['query']}`",
                f"- Seed used: `{str(trace['seed_used']).lower()}`",
                f"- Matched concepts: `{len(trace['matched_seed_concepts'])}`",
                f"- Matched edges: `{len(trace['matched_seed_edges'])}`",
                f"- Cloud candidates checked: `{trace['cloud_alignment_trace']['candidate_fragments_checked']}`",
                f"- Cloud fragments aligned: `{trace['cloud_alignment_trace']['fragments_aligned_to_seed']}`",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_runtime_anchor_proof(root: str | Path | None = None, cloud_root: str | Path = "data/cloud_brain") -> dict[str, Any]:
    base = seed_root(root)
    current = base / "current"
    current.mkdir(parents=True, exist_ok=True)
    proof = build_runtime_anchor_proof(base, cloud_root)
    json_path = current / "seed_runtime_anchor_proof.json"
    md_path = current / "seed_runtime_anchor_proof.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(proof, md_path)
    return {
        "proof": proof,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write ATANOR Seed Runtime Anchor proof artifacts.")
    parser.add_argument("--root", default=None, help="Seed research root. Defaults to data/seed_research.")
    parser.add_argument("--cloud-root", default="data/cloud_brain", help="Cloud Brain candidate fragment root.")
    args = parser.parse_args()
    result = write_runtime_anchor_proof(args.root, args.cloud_root)
    print(json.dumps({k: v for k, v in result.items() if k != "proof"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
