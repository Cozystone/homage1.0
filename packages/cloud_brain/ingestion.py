from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PACKAGES_ROOT = Path(__file__).resolve().parents[1]
_SEED_RESEARCH_ROOT = _PACKAGES_ROOT / "seed_research"
if _SEED_RESEARCH_ROOT.exists() and str(_SEED_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEED_RESEARCH_ROOT))

from seed_research.cloud_fragment_alignment import align_cloud_fragment_to_seed, ensure_deterministic_fixture


DEFAULT_CLOUD_ROOT = Path("data/cloud_brain")
STORE_BACKEND = "local_proof_store"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store_paths(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Path]:
    base = Path(root)
    store = base / "store"
    store.mkdir(parents=True, exist_ok=True)
    return {
        "root": base,
        "store": store,
        "fragments": store / "cloud_fragments.jsonl",
        "nodes": store / "cloud_graph_nodes.jsonl",
        "edges": store / "cloud_graph_edges.jsonl",
        "state": store / "cloud_ingestion_state.json",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_state(paths: dict[str, Path]) -> dict[str, Any]:
    if paths["state"].exists():
        try:
            state = json.loads(paths["state"].read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except Exception:
            pass
    return {
        "schema": "atanor.cloud-brain-ingestion-state.v1",
        "cloud_store_backend": STORE_BACKEND,
        "cloud_total_nodes": len(_read_jsonl(paths["nodes"])),
        "cloud_total_edges": len(_read_jsonl(paths["edges"])),
        "proof_ingested_fragments": len(_read_jsonl(paths["fragments"])),
        "last_ingestion_success": False,
        "last_ingested_fragment_id": None,
        "updated_at": None,
        "autonomous_broad_crawling": False,
        "mode": "controlled_fixture_only",
    }


def cloud_store_status(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    paths = _store_paths(root)
    state = _load_state(paths)
    nodes = _read_jsonl(paths["nodes"])
    edges = _read_jsonl(paths["edges"])
    fragments = _read_jsonl(paths["fragments"])
    state.update(
        {
            "cloud_store_backend": STORE_BACKEND,
            "cloud_total_nodes": len(nodes),
            "cloud_total_edges": len(edges),
            "proof_ingested_fragments": len(fragments),
            "autonomous_broad_crawling": False,
            "mode": "controlled_fixture_only",
        }
    )
    return state


def _existing_hashes(paths: dict[str, Path]) -> set[str]:
    return {str(row.get("content_hash")) for row in _read_jsonl(paths["fragments"]) if row.get("content_hash")}


def ingest_aligned_cloud_fragment(
    fragment: dict[str, Any],
    *,
    seed_root: str | Path | None = "data/seed_research",
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
) -> dict[str, Any]:
    paths = _store_paths(cloud_root)
    previous = cloud_store_status(cloud_root)
    previous_nodes = int(previous.get("cloud_total_nodes") or 0)
    previous_edges = int(previous.get("cloud_total_edges") or 0)
    content_hash = str(fragment.get("content_hash") or "")
    fragment_id = str(fragment.get("fragment_id") or content_hash or "unknown")
    alignment = align_cloud_fragment_to_seed(fragment, seed_root)

    base = {
        "fragment_id": fragment_id,
        "content_hash": content_hash,
        "ingestion_attempted": True,
        "alignment_success": bool(alignment.get("alignment_success")),
        "matched_seed_concepts": alignment.get("matched_seed_concepts", []),
        "matched_seed_edges": alignment.get("matched_seed_edges", []),
        "nodes_added": 0,
        "edges_added": 0,
        "duplicate_fragment": False,
        "previous_cloud_nodes": previous_nodes,
        "new_cloud_nodes": previous_nodes,
        "previous_cloud_edges": previous_edges,
        "new_cloud_edges": previous_edges,
        "trust_state": fragment.get("trust_state", "unverified"),
        "verification_state": fragment.get("verification_state", "web_seed_pending"),
        "ingestion_state": fragment.get("ingestion_state", "pending"),
        "writes_to_local_brain": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "final_answer_generation_claimed": False,
    }

    if alignment.get("rejected"):
        result = {
            **base,
            "ingestion_success": False,
            "rejected": True,
            "reject_reason": alignment.get("reject_reason"),
            "ingestion_state": "rejected",
        }
        _write_json(paths["state"], {**previous, "last_ingestion_success": False, "last_ingestion_error": alignment.get("reject_reason"), "updated_at": _now_iso()})
        return result
    if not alignment.get("alignment_success"):
        result = {
            **base,
            "ingestion_success": False,
            "rejected": False,
            "reject_reason": "seed_alignment_failed",
            "ingestion_state": "rejected",
        }
        _write_json(paths["state"], {**previous, "last_ingestion_success": False, "last_ingestion_error": "seed_alignment_failed", "updated_at": _now_iso()})
        return result

    duplicate = bool(content_hash and content_hash in _existing_hashes(paths))
    if duplicate:
        existing_state = cloud_store_status(cloud_root)
        return {
            **base,
            "ingestion_success": True,
            "duplicate_fragment": True,
            "previous_cloud_nodes": int(existing_state.get("cloud_total_nodes") or previous_nodes),
            "new_cloud_nodes": int(existing_state.get("cloud_total_nodes") or previous_nodes),
            "previous_cloud_edges": int(existing_state.get("cloud_total_edges") or previous_edges),
            "new_cloud_edges": int(existing_state.get("cloud_total_edges") or previous_edges),
            "trust_state": "seed_aligned",
            "verification_state": "seed_aligned_pending_verification",
            "ingestion_state": "ingested",
        }

    ingested_at = _now_iso()
    matched_concepts = list(alignment.get("matched_seed_concepts") or [])
    matched_edges = list(alignment.get("matched_seed_edges") or [])
    stored_fragment = {
        **fragment,
        "trust_state": "seed_aligned",
        "verification_state": "seed_aligned_pending_verification",
        "ingestion_state": "ingested",
        "ingested_at": ingested_at,
        "matched_seed_concepts": matched_concepts,
        "matched_seed_edges": matched_edges,
        "writes_to_local_brain": False,
    }
    _append_jsonl(paths["fragments"], stored_fragment)
    for concept in matched_concepts:
        _append_jsonl(
            paths["nodes"],
            {
                "fragment_id": fragment_id,
                "content_hash": content_hash,
                "concept_id": concept.get("concept_id"),
                "label": concept.get("label"),
                "matched_text": concept.get("matched_text"),
                "confidence": concept.get("confidence"),
                "ingested_at": ingested_at,
                "source_scope": "cloud",
                "privacy_scope": "public",
            },
        )
    for edge in matched_edges:
        _append_jsonl(
            paths["edges"],
            {
                "fragment_id": fragment_id,
                "content_hash": content_hash,
                "source": edge.get("source"),
                "relation": edge.get("relation"),
                "target": edge.get("target"),
                "matched_text": edge.get("matched_text"),
                "confidence": edge.get("confidence"),
                "ingested_at": ingested_at,
                "source_scope": "cloud",
                "privacy_scope": "public",
            },
        )

    new_nodes = previous_nodes + len(matched_concepts)
    new_edges = previous_edges + len(matched_edges)
    state = {
        "schema": "atanor.cloud-brain-ingestion-state.v1",
        "cloud_store_backend": STORE_BACKEND,
        "cloud_total_nodes": new_nodes,
        "cloud_total_edges": new_edges,
        "proof_ingested_fragments": len(_read_jsonl(paths["fragments"])),
        "last_ingestion_success": True,
        "last_ingested_fragment_id": fragment_id,
        "last_ingested_content_hash": content_hash,
        "updated_at": ingested_at,
        "autonomous_broad_crawling": False,
        "mode": "controlled_fixture_only",
    }
    _write_json(paths["state"], state)
    return {
        **base,
        "ingestion_success": True,
        "nodes_added": len(matched_concepts),
        "edges_added": len(matched_edges),
        "new_cloud_nodes": new_nodes,
        "new_cloud_edges": new_edges,
        "trust_state": "seed_aligned",
        "verification_state": "seed_aligned_pending_verification",
        "ingestion_state": "ingested",
    }


def query_ingested_fragments(
    query: str,
    *,
    limit: int = 5,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
) -> dict[str, Any]:
    terms = set(token.casefold() for token in query.replace("_", " ").split() if token.strip())
    rows = _read_jsonl(_store_paths(cloud_root)["fragments"])
    results: list[dict[str, Any]] = []
    for row in rows:
        haystack = json.dumps(
            {
                "title": row.get("title"),
                "text": row.get("text"),
                "matched_seed_concepts": row.get("matched_seed_concepts"),
                "matched_seed_edges": row.get("matched_seed_edges"),
            },
            ensure_ascii=False,
        ).casefold()
        if not terms or any(term.casefold() in haystack for term in terms):
            results.append(
                {
                    "fragment_id": row.get("fragment_id"),
                    "content_hash": row.get("content_hash"),
                    "text": row.get("text"),
                    "matched_seed_concepts": row.get("matched_seed_concepts", []),
                    "matched_seed_edges": row.get("matched_seed_edges", []),
                    "trust_state": row.get("trust_state"),
                    "verification_state": row.get("verification_state"),
                    "ingestion_state": row.get("ingestion_state"),
                }
            )
        if len(results) >= limit:
            break
    return {
        "query": query,
        "results": results,
        "query_readback_success": bool(results),
        "matches": len(results),
        "external_llm_used": False,
        "external_sllm_used": False,
        "final_answer_generation_claimed": False,
    }


def ensure_fixture_and_ingest(
    *,
    seed_root: str | Path | None = "data/seed_research",
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
) -> dict[str, Any]:
    fixture_path = ensure_deterministic_fixture(Path(cloud_root) / "inbox" / "test_seed_alignment_fragment.json")
    fragment = json.loads(fixture_path.read_text(encoding="utf-8"))
    return ingest_aligned_cloud_fragment(fragment, seed_root=seed_root, cloud_root=cloud_root)
