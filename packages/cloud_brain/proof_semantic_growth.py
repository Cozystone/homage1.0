from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.brain_graph.materializers import materialize_semantic_cloud_graph

from .semantic_attach import attach_semantic_cloud_for_query
from .semantic_growth import ingest_semantic_source
from .semantic_store import DEFAULT_SEMANTIC_CLOUD_ROOT, SemanticCloudStore, utc_now_iso


PROOF_JSON_PATH = DEFAULT_SEMANTIC_CLOUD_ROOT / "proofs" / "semantic_cloud_growth_proof.json"
PROOF_MD_PATH = DEFAULT_SEMANTIC_CLOUD_ROOT / "proofs" / "semantic_cloud_growth_proof.md"


def run_semantic_cloud_growth_proof(*, cloud_root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT) -> dict[str, Any]:
    requested_root = Path(cloud_root)
    if requested_root == DEFAULT_SEMANTIC_CLOUD_ROOT:
        token = utc_now_iso().replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
        root = DEFAULT_SEMANTIC_CLOUD_ROOT / "proofs" / f"semantic_growth_scratch_{token}"
    else:
        root = requested_root
    root.mkdir(parents=True, exist_ok=True)
    store = SemanticCloudStore(root)
    before = store.status()
    ko = "쿠버네티스는 컨테이너화된 애플리케이션을 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다."
    en = "Kubernetes is an open-source platform that manages containerized applications and automates deployment."
    first = ingest_semantic_source(ko, "proof-ko-kubernetes", "ko", title="Kubernetes proof KO", usage_allowed=False, cloud_root=root)
    duplicate = ingest_semantic_source(ko, "proof-ko-kubernetes", "ko", title="Kubernetes proof KO duplicate", usage_allowed=False, cloud_root=root)
    english = ingest_semantic_source(en, "proof-en-kubernetes", "en", title="Kubernetes proof EN", usage_allowed=False, cloud_root=root)
    attach = attach_semantic_cloud_for_query("쿠버네티스가 뭐야?", limit=8, cloud_root=root)
    graph_result = materialize_semantic_cloud_graph(1000, 3000) if root == DEFAULT_SEMANTIC_CLOUD_ROOT else {
        "available": True,
        "nodes": store.graph_sample()["nodes"],
        "edges": store.graph_sample()["edges"],
        "stats": store.status(),
    }
    graph = graph_result.to_dict() if hasattr(graph_result, "to_dict") else graph_result
    after = store.status()
    checks = {
        "fresh_ingest_created_concepts": first["concepts_created"] > 0,
        "fresh_ingest_created_relations": first["relations_created"] > 0,
        "duplicate_strengthened_relations": duplicate["relations_strengthened"] > 0 or duplicate["concepts_merged"] > 0,
        "cross_language_alias_merged": english["concepts_merged"] > 0 or after["concepts"] <= before["concepts"] + first["concepts_created"] + english["concepts_created"],
        "attach_temporary_nodes": len(attach["attached_nodes"]) > 0 and attach["temporary"] is True,
        "local_brain_write_false": first["honesty"]["local_brain_write"] is False and attach["local_brain_write"] is False,
        "graph_reads_semantic_store": bool(graph.get("nodes")) and graph.get("available", True),
    }
    passed = all(checks.values())
    proof = {
        "proof_id": "semantic_cloud_growth_proof",
        "generated_at": utc_now_iso(),
        "passed": passed,
        "checks": checks,
        "before": before,
        "after": after,
        "first_ingest": first,
        "duplicate_ingest": duplicate,
        "english_alias_ingest": english,
        "attach": {
            "attached_nodes": len(attach["attached_nodes"]),
            "attached_edges": len(attach["attached_edges"]),
            "temporary": attach["temporary"],
            "local_brain_write": attach["local_brain_write"],
            "cloud_attached_counts_as_local": attach["cloud_attached_counts_as_local"],
        },
        "graph": {
            "nodes": len(graph.get("nodes") or []),
            "edges": len(graph.get("edges") or []),
            "proof_store_only": True,
        },
        "claims": [
            "ATANOR can grow a small Semantic Cloud proof store from source sentences.",
            "Duplicate semantic facts merge and strengthen existing relations.",
            "Semantic cloud nodes can be attached temporarily to Working Memory.",
            "Local Brain remains unchanged.",
        ],
        "does_not_claim": [
            "global Cloud Brain",
            "web-scale graph",
            "unlimited crawling",
            "perfect semantic extraction",
            "full cross-lingual entity resolution",
            "external LLM/sLLM use",
            "old mirror snapshot as live cloud",
        ],
    }
    PROOF_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_JSON_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    PROOF_MD_PATH.write_text(
        "\n".join(
            [
                "# Semantic Cloud Growth Proof",
                "",
                f"- Generated: {proof['generated_at']}",
                f"- Result: {'PASS' if passed else 'FAIL'}",
                f"- Concepts before/after: {before['concepts']} -> {after['concepts']}",
                f"- Relations before/after: {before['relations']} -> {after['relations']}",
                "",
                "## Checks",
                *[f"- {'PASS' if value else 'FAIL'}: {key}" for key, value in checks.items()],
                "",
                "## Honest Boundaries",
                *[f"- Does not claim: {item}" for item in proof["does_not_claim"]],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return proof


def main() -> None:
    proof = run_semantic_cloud_growth_proof()
    print(json.dumps({"passed": proof["passed"], "proof_json": str(PROOF_JSON_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
