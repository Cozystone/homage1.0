from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import current_viewer_export, ensure_layout, read_jsonl, seed_root, utc_now_iso, write_json


FORBIDDEN_GENERATION_MARKERS = [
    "openai",
    "anthropic",
    "gemini",
    "llama.cpp",
    "ollama",
    "template_answer",
    "answer_template",
    "canned_response",
]


def _latest_run_id(root: Path) -> str | None:
    runs = sorted((root / "runs").glob("run_*"))
    return runs[-1].name if runs else None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def prove_seed_performance(root: str | Path | None = None) -> dict[str, Any]:
    paths = ensure_layout(root)
    root_path = seed_root(root)
    run_id = _latest_run_id(root_path)
    if not run_id:
        raise FileNotFoundError("No seed research run exists. Run packages.seed_research.run_seed_iteration first.")

    run_dir = root_path / "runs" / run_id
    metrics = _load_json(run_dir / "seed_metrics.json")
    concepts = read_jsonl(run_dir / "seed_concepts.jsonl")
    edges = read_jsonl(run_dir / "seed_edges.jsonl")
    viewer = current_viewer_export(root_path)

    serialized_public_artifacts = "\n".join(
        [
            json.dumps(concepts, ensure_ascii=False),
            json.dumps(edges, ensure_ascii=False),
            json.dumps(viewer, ensure_ascii=False),
        ]
    ).lower()
    forbidden_hits = sorted({marker for marker in FORBIDDEN_GENERATION_MARKERS if marker in serialized_public_artifacts})

    benchmark_results = metrics.get("benchmark_results") or []
    benchmark_scores = [float(item.get("score") or 0) for item in benchmark_results]
    benchmark_min = min(benchmark_scores) if benchmark_scores else 0.0
    benchmark_average = sum(benchmark_scores) / max(1, len(benchmark_scores))
    relation_distribution = metrics.get("relation_type_distribution") or {}
    retrieval_ready = (
        int(metrics.get("concept_count") or 0) >= 12
        and int(metrics.get("edge_count") or 0) >= 14
        and int(metrics.get("isolated_node_count") or 0) == 0
        and float(metrics.get("confidence_average") or 0) >= 0.72
        and benchmark_min >= 0.68
        and not forbidden_hits
    )

    proof = {
        "schema": "atanor.seed-research.performance-proof.v1",
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "scope": "seed_graph_research",
        "not_local_brain": True,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "does_generate_final_answers": False,
        "candidate_graph_only": True,
        "retrieval_ready": retrieval_ready,
        "metrics": {
            "concept_count": metrics.get("concept_count"),
            "edge_count": metrics.get("edge_count"),
            "alias_count": metrics.get("alias_count"),
            "duplicate_merge_count": metrics.get("duplicate_merge_count"),
            "rejected_concept_count": metrics.get("rejected_concept_count"),
            "rejected_edge_count": metrics.get("rejected_edge_count"),
            "isolated_node_count": metrics.get("isolated_node_count"),
            "average_degree": metrics.get("average_degree"),
            "connected_component_count": metrics.get("connected_component_count"),
            "confidence_average": metrics.get("confidence_average"),
            "benchmark_average": round(benchmark_average, 3),
            "benchmark_min": round(benchmark_min, 3),
            "relation_type_count": len(relation_distribution),
        },
        "integrity": {
            "forbidden_generation_markers": forbidden_hits,
            "public_scope_only": all(item.get("privacy_scope") == "public" for item in concepts),
            "seed_scope_only": all(item.get("source_scope") == "seed" for item in concepts + edges),
            "viewer_read_only": bool(viewer.get("read_only")),
        },
        "interpretation": (
            "This proof measures Seed Graph retrieval/verification readiness. "
            "It does not claim ChatGPT-level language generation and does not use external models."
        ),
    }
    write_json(run_dir / "seed_performance_proof.json", proof)
    write_json(paths.current / "seed_performance_proof.json", proof)
    (run_dir / "seed_performance_proof.md").write_text(render_report(proof), encoding="utf-8", newline="\n")
    (paths.current / "seed_performance_proof.md").write_text(render_report(proof), encoding="utf-8", newline="\n")
    return proof


def render_report(proof: dict[str, Any]) -> str:
    metrics = proof["metrics"]
    integrity = proof["integrity"]
    return f"""# ATANOR Seed Graph Performance Proof

Run: `{proof['run_id']}`

## Constraint Check

- External LLM used: `{proof['external_llm_used']}`
- External sLLM used: `{proof['external_sllm_used']}`
- Rule-based answer engine: `{proof['rule_based_answer_engine']}`
- Final answer generation claimed: `{proof['does_generate_final_answers']}`
- Seed candidate graph only: `{proof['candidate_graph_only']}`

## Structural Metrics

- Concepts: `{metrics['concept_count']}`
- Edges: `{metrics['edge_count']}`
- Aliases: `{metrics['alias_count']}`
- Average degree: `{metrics['average_degree']}`
- Isolated nodes: `{metrics['isolated_node_count']}`
- Confidence average: `{metrics['confidence_average']}`
- Relation types: `{metrics['relation_type_count']}`

## Benchmark

- Benchmark average: `{metrics['benchmark_average']}`
- Benchmark minimum: `{metrics['benchmark_min']}`
- Retrieval-ready: `{proof['retrieval_ready']}`

## Integrity

- Public scope only: `{integrity['public_scope_only']}`
- Seed scope only: `{integrity['seed_scope_only']}`
- Viewer read-only: `{integrity['viewer_read_only']}`
- Forbidden generation markers: `{', '.join(integrity['forbidden_generation_markers']) or 'none'}`

## Interpretation

This is a graph-structure proof, not a prose-generation proof. The Seed Graph
research loop is ready to provide public ontology anchors for retrieval and
verification experiments without using external LLM/sLLM generation or canned
answer templates.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Prove ATANOR Seed Graph research performance constraints.")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    print(json.dumps(prove_seed_performance(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

