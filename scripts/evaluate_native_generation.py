from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for package in [
    ROOT / "packages" / "rag_engine",
    ROOT / "packages" / "knowledge_bakery",
    ROOT / "packages" / "neuro_efficiency",
]:
    sys.path.insert(0, str(package))

from rag_engine import query_graphrag  # noqa: E402


DEFAULT_QUERIES = [
    "?덈뒗 ?꾧뎄??",
    "ATANOR??萸먯빞",
    "Local Brain??萸먯빞",
    "Cloud Brain? 萸먯빞",
    "GraphRAG媛 萸먯빞",
    "Ghost Shell??萸먯빞",
    "Payload Vault媛 萸먯빞",
]


def _source_type(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata")
    if isinstance(metadata, dict):
        return str(metadata.get("source_type") or metadata.get("kind") or "")
    return str(doc.get("source_type") or "")


def evaluate(memory_dir: str = "data/memory") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        result = query_graphrag(query, memory_dir=memory_dir)
        diagnostics = ((result.get("answer_engine") or {}).get("diagnostics") or {})
        degeneration = result.get("degeneration") or diagnostics.get("degeneration") or {}
        evidence = list(result.get("evidence_docs") or [])
        fusion = result.get("fusion_ratio") or {}
        rows.append(
            {
                "query": query,
                "retrieved_evidence_count": len(evidence),
                "dominant_source_cluster": diagnostics.get("dominant_source_cluster"),
                "local_cloud_ratio": {
                    "local": fusion.get("local_weight", fusion.get("local")),
                    "cloud": fusion.get("cloud_weight", fusion.get("cloud")),
                },
                "repeated_bigram_ratio": degeneration.get("repeated_bigram_ratio"),
                "unique_token_ratio": degeneration.get("unique_token_ratio"),
                "loop_detected": degeneration.get("loop_detected"),
                "answer_length": len(str(result.get("answer") or "")),
                "native_stop_reason": result.get("native_stop_reason") or diagnostics.get("native_stop_reason"),
                "self_corpus_evidence_used": any(_source_type(doc) == "self_corpus" for doc in evidence),
                "native_generation_failed_quality_check": result.get("native_generation_failed_quality_check")
                or diagnostics.get("native_generation_failed_quality_check"),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ATANOR native graph-token generation with deterministic metrics.")
    parser.add_argument("--memory-dir", default="data/memory")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.memory_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
