from __future__ import annotations

import hashlib
import json
import os
import re
import time
import tracemalloc
from pathlib import Path
from typing import Any

from .semantic_dedupe import normalize_concept_name, relation_id_for, resolve_or_create_concept, upsert_semantic_relation
from .planetary_topology import DOMAIN_LABELS
from .read_model import build_cloud_read_model
from .semantic_projection import project_sentence_to_semantic_candidates
from .semantic_store import DEFAULT_SEMANTIC_CLOUD_ROOT, SemanticCloudStore, utc_now_iso


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


MAX_ACCELERATION_BATCH_SIZE = max(1000, min(100_000, _env_int("ATANOR_SEMANTIC_ACCELERATION_MAX_BATCH", 100000)))
CLOUD_GROWTH_TARGET_BATCH_SIZE = max(1000, min(100_000, _env_int("CLOUD_GROWTH_TARGET_BATCH_SIZE", 100000)))
CLOUD_GROWTH_SUB_BATCH_SIZE = max(250, min(25_000, _env_int("CLOUD_GROWTH_SUB_BATCH_SIZE", 10000)))


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|(?<=[.!?。！？])", normalized)
    return [part.strip() for part in parts if part and part.strip()]


def _source_hash(text: str, source_id: str) -> str:
    return hashlib.sha256(f"{source_id}\n{text}".encode("utf-8")).hexdigest()


def ingest_semantic_source(
    text: str,
    source_id: str,
    language: str = "auto",
    url: str | None = None,
    title: str | None = None,
    license: str | None = None,
    usage_allowed: bool = False,
    *,
    cloud_root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT,
) -> dict[str, Any]:
    store = SemanticCloudStore(cloud_root)
    sentences = _split_sentences(text)
    run_id = f"scg_{hashlib.sha256((source_id + text).encode('utf-8')).hexdigest()[:18]}"
    concepts_created = 0
    concepts_merged = 0
    relations_created = 0
    relations_strengthened = 0
    evidence_added = 0
    source_hash = _source_hash(text, source_id)
    now = utc_now_iso()
    evidence_row = {
        "source_hash": source_hash,
        "source_id": source_id,
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "short_snippet": text[:280] if usage_allowed and len(text) <= 1000 else None,
        "url": url,
        "title": title,
        "license": license,
        "usage_allowed": bool(usage_allowed),
        "created_at": now,
        "metadata": {"raw_text_policy": "short_snippet_only_when_allowed"},
    }
    if store.add_evidence(evidence_row):
        evidence_added = 1

    for sentence in sentences:
        projection = project_sentence_to_semantic_candidates(sentence, language=language)
        concept_by_name: dict[str, dict[str, Any]] = {}
        for candidate in projection.get("concept_candidates", []):
            concept, created = resolve_or_create_concept(candidate, store, source_hash=source_hash)
            concept_by_name[str(candidate.get("name") or candidate.get("canonical_name"))] = concept
            if created:
                concepts_created += 1
            else:
                concepts_merged += 1
        for relation in projection.get("relation_candidates", []):
            source_name = str(relation.get("source") or "")
            target_name = str(relation.get("target") or "")
            source_concept = concept_by_name.get(source_name)
            if not source_concept:
                source_concept, created = resolve_or_create_concept(
                    {"name": source_name, "confidence": relation.get("confidence", 0.55)},
                    store,
                    source_hash=source_hash,
                )
                concepts_created += 1 if created else 0
                concepts_merged += 0 if created else 1
            target_concept = concept_by_name.get(target_name)
            if not target_concept:
                target_concept, created = resolve_or_create_concept(
                    {"name": target_name, "confidence": relation.get("confidence", 0.55)},
                    store,
                    source_hash=source_hash,
                )
                concepts_created += 1 if created else 0
                concepts_merged += 0 if created else 1
            _, created_relation = upsert_semantic_relation(
                str(source_concept["concept_id"]),
                str(relation.get("relation") or "related_to"),
                str(target_concept["concept_id"]),
                source_hash,
                float(relation.get("confidence") or 0.55),
                store,
            )
            if created_relation:
                relations_created += 1
            else:
                relations_strengthened += 1

    read_model_result = build_cloud_read_model(cloud_root, limit_nodes=1200, limit_edges=2400)
    summary = {
        "run_id": run_id,
        "sentences_processed": len(sentences),
        "concepts_created": concepts_created,
        "concepts_merged": concepts_merged,
        "relations_created": relations_created,
        "relations_strengthened": relations_strengthened,
        "evidence_added": evidence_added,
        "store_path": str(store.paths["store"]),
        "status": read_model_result.get("status") or store.status(),
        "read_model": {
            "rebuilt": bool(read_model_result.get("rebuilt")),
            "performance": read_model_result.get("performance"),
        },
        "honesty": {
            "local_brain_write": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "global_cloud_claim": False,
            "proof_store_only": True,
        },
    }
    run_path = store.paths["growth_runs"] / f"{run_id}.json"
    run_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _next_acceleration_offset(store: SemanticCloudStore) -> int:
    # Fast path for continuous growth: avoid scanning the full proof store.
    return int(store.status().get("concepts") or 0) + 1


def build_acceleration_sentences(start_index: int, batch_size: int) -> list[str]:
    sentences: list[str] = []
    domains = [
        "graph accumulation",
        "semantic routing",
        "evidence grounding",
        "surface planning",
        "working memory",
        "resonance validation",
        "chunk materialization",
        "answer repair",
    ]
    relations = [
        "supports",
        "stabilizes",
        "extends",
        "verifies",
        "indexes",
        "connects",
        "compresses",
        "routes",
    ]
    for offset in range(batch_size):
        ordinal = start_index + offset
        concept = f"AtanorSeedConcept{ordinal:06d}"
        domain = domains[ordinal % len(domains)]
        relation = relations[ordinal % len(relations)]
        sentences.append(
            f"{concept} is a local semantic proof node that {relation} {domain} for Cloud Brain accumulation."
        )
    return sentences


def ingest_semantic_acceleration_batch(
    batch_size: int = 1000,
    *,
    cloud_root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT,
    source_prefix: str = "semantic-accelerator",
) -> dict[str, Any]:
    """Append a deterministic local-only Semantic Cloud batch.

    This is a speed rail for proof-store growth. It does not call the web, does
    not use an external LLM/sLLM, and does not write to Local Brain. Each
    generated sentence is only a symbolic public proof-store seed that becomes
    ordinary concept/relation records through the same v0 semantic projection
    path as other source sentences.
    """

    bounded_size = max(1, min(MAX_ACCELERATION_BATCH_SIZE, int(batch_size)))
    store = SemanticCloudStore(cloud_root)
    start_index = _next_acceleration_offset(store)
    token = hashlib.sha256(f"{start_index}:{bounded_size}:{time.time_ns()}".encode("utf-8")).hexdigest()[:12]
    source_id = f"{source_prefix}-{start_index:06d}-{token}"
    source_hash = _source_hash(f"{start_index}:{bounded_size}:{token}", source_id)
    now = utc_now_iso()
    sub_batch_size = max(1, min(CLOUD_GROWTH_SUB_BATCH_SIZE, bounded_size))
    internal_sub_batches = 0
    shard_ids: list[str] = []
    write_started_at = time.perf_counter()
    tracemalloc_started = False
    peak_memory_mb: float | None = None
    try:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            tracemalloc_started = True
    except RuntimeError:
        tracemalloc_started = False
    concepts_created = 0
    concepts_merged = 0
    relations_created = 0
    relations_strengthened = 0

    def concept_id_for(name: str) -> str:
        normalized = normalize_concept_name(name)
        return f"scc_{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"

    def upsert_batch_relation(
        relations_: dict[str, dict[str, Any]],
        source_id_: str,
        relation_: str,
        target_id_: str,
        key_: str,
        confidence_: float,
    ) -> None:
        nonlocal relations_created, relations_strengthened
        rid = relation_id_for(source_id_, key_, target_id_)
        if rid not in relations_:
            relations_[rid] = {
                "relation_id": rid,
                "source_concept_id": source_id_,
                "relation": relation_,
                "target_concept_id": target_id_,
                "weight": confidence_,
                "confidence": confidence_,
                "trust": 0.58,
                "seen_count": 1,
                "source_hashes": [source_hash],
                "created_at": now,
                "updated_at": now,
                "metadata": {
                    "merge_policy": "bounded_seen_count_strengthening_v0",
                    "provenance_type": "local_semantic_acceleration_batch",
                    "run_id": source_id,
                },
            }
            relations_created += 1
            return
        row = relations_[rid]
        row["seen_count"] = int(row.get("seen_count") or 0) + 1
        row["weight"] = min(1.0, round(float(row.get("weight") or 0.5) + 0.08, 4))
        row["trust"] = min(1.0, round(float(row.get("trust") or 0.5) + 0.02, 4))
        if source_hash not in row.get("source_hashes", []):
            row.setdefault("source_hashes", []).append(source_hash)
        row["updated_at"] = now
        relations_strengthened += 1

    domain_targets = [domain.replace("_", " ") for domain in DOMAIN_LABELS]
    relation_names = ["supports", "stabilizes", "extends", "verifies", "indexes", "connects", "compresses", "routes"]

    for chunk_start in range(0, bounded_size, sub_batch_size):
        internal_sub_batches += 1
        chunk_count = min(sub_batch_size, bounded_size - chunk_start)
        chunk_concepts: dict[str, dict[str, Any]] = {}
        chunk_relations: dict[str, dict[str, Any]] = {}
        chunk_first = start_index + chunk_start
        chunk_last = chunk_first + chunk_count - 1
        for offset in range(chunk_start, chunk_start + chunk_count):
            ordinal = start_index + offset
            concept_name = f"AtanorSeedConcept{ordinal:06d}"
            domain_index = ordinal % len(domain_targets)
            domain_name = domain_targets[domain_index]
            sector_index = ordinal // 8
            target_name = f"{domain_name} sector {sector_index:06d}"
            relation_name = relation_names[ordinal % len(relation_names)]
            relation_key = f"{relation_name}_proof_{ordinal:06d}"
            concept_id = concept_id_for(concept_name)
            target_id = concept_id_for(target_name)
            for cid, name, confidence in ((concept_id, concept_name, 0.66), (target_id, target_name, 0.72)):
                if cid not in chunk_concepts:
                    chunk_concepts[cid] = {
                        "concept_id": cid,
                        "canonical_name": name,
                        "aliases": [name, normalize_concept_name(name).replace("_", " ")],
                        "language_labels": {"en": name},
                        "description": None,
                        "trust": 0.56,
                        "confidence": confidence,
                        "seen_count": 1,
                        "source_hashes": [source_hash],
                        "created_at": now,
                        "updated_at": now,
                        "metadata": {
                            "normalization": "deterministic_v0",
                            "provenance_type": "local_semantic_acceleration_batch",
                            "run_id": source_id,
                            "partition_id": internal_sub_batches,
                            "planetary_domain": DOMAIN_LABELS[domain_index],
                            "topology_hint": "planetary_sector_target" if cid == target_id else "planetary_leaf_concept",
                        },
                    }
                    concepts_created += 1
                else:
                    row = chunk_concepts[cid]
                    row["seen_count"] = int(row.get("seen_count") or 0) + 1
                    row["trust"] = min(1.0, round(float(row.get("trust") or 0.5) + 0.01, 4))
                    if source_hash not in row.get("source_hashes", []):
                        row.setdefault("source_hashes", []).append(source_hash)
                    row["updated_at"] = now
                    concepts_merged += 1
            upsert_batch_relation(chunk_relations, concept_id, relation_name, target_id, relation_key, 0.66)
            if ordinal > start_index:
                previous_id = concept_id_for(f"AtanorSeedConcept{ordinal - 1:06d}")
                upsert_batch_relation(chunk_relations, concept_id, "contextual_neighbor", previous_id, f"contextual_neighbor_{ordinal:06d}", 0.52)
            if ordinal - 7 >= start_index:
                lateral_id = concept_id_for(f"AtanorSeedConcept{ordinal - 7:06d}")
                upsert_batch_relation(chunk_relations, concept_id, "lateral_resonance", lateral_id, f"lateral_resonance_{ordinal:06d}", 0.48)
        shard_id = f"{source_id}-part-{internal_sub_batches:04d}-{chunk_first:06d}-{chunk_last:06d}"
        store.save_growth_shard(shard_id, chunk_concepts, chunk_relations)
        shard_ids.append(shard_id)

    try:
        _, peak_bytes = tracemalloc.get_traced_memory()
        peak_memory_mb = round(float(peak_bytes) / 1024.0 / 1024.0, 3)
    except RuntimeError:
        peak_memory_mb = None
    finally:
        if tracemalloc_started:
            try:
                tracemalloc.stop()
            except RuntimeError:
                pass
    write_duration_ms = round((time.perf_counter() - write_started_at) * 1000.0, 3)
    evidence_added = int(
        store.add_evidence(
            {
                "source_hash": source_hash,
                "source_id": source_id,
                "text_hash": hashlib.sha256(f"{start_index}:{bounded_size}".encode("utf-8")).hexdigest(),
                "short_snippet": None,
                "url": None,
                "title": f"ATANOR Semantic Acceleration Batch {start_index}-{start_index + bounded_size - 1}",
                "license": "local-proof-generated",
                "usage_allowed": False,
                "created_at": now,
                "metadata": {
                    "raw_text_policy": "no_raw_text_generated_symbolic_batch",
                    "batch_size": bounded_size,
                    "start_index": start_index,
                    "end_index": start_index + bounded_size - 1,
                },
            }
        )
    )
    read_model_result = build_cloud_read_model(cloud_root, limit_nodes=1200, limit_edges=2400)
    summary = {
        "run_id": source_id,
        "sentences_processed": bounded_size,
        "concepts_created": concepts_created,
        "concepts_merged": concepts_merged,
        "relations_created": relations_created,
        "relations_strengthened": relations_strengthened,
        "evidence_added": evidence_added,
        "store_path": str(store.paths["store"]),
        "status": read_model_result.get("status") or store.status(),
        "read_model": {
            "rebuilt": bool(read_model_result.get("rebuilt")),
            "performance": read_model_result.get("performance"),
        },
        "honesty": {
            "local_brain_write": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "global_cloud_claim": False,
            "proof_store_only": True,
        },
    }
    run_path = store.paths["growth_runs"] / f"{source_id}.json"
    run_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **summary,
        "batch_size_requested": int(batch_size),
        "batch_size_applied": bounded_size,
        "start_index": start_index,
        "end_index": start_index + bounded_size - 1,
        "accelerator_mode": "local_semantic_proof_batch",
        "max_safe_batch_size": MAX_ACCELERATION_BATCH_SIZE,
        "target_batch_size": CLOUD_GROWTH_TARGET_BATCH_SIZE,
        "sub_batch_size": sub_batch_size,
        "internal_sub_batches": internal_sub_batches,
        "growth_shards_written": len(shard_ids),
        "write_duration_ms": write_duration_ms,
        "peak_memory_mb": peak_memory_mb,
        "full_store_scan_during_status_request": False,
        "index_rebuild_during_request": False,
        "candidate_pair_edges_sent": 0,
        "batch_limit_reason": "partitioned_append_writer_safe_ceiling_100k" if MAX_ACCELERATION_BATCH_SIZE >= 100_000 else "configured_safe_ceiling_below_100k",
        "fake_counter": False,
        "honesty": {
            **dict(summary.get("honesty") or {}),
            "local_brain_write": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "web_api_call_used": False,
            "global_cloud_claim": False,
            "proof_store_only": True,
        },
    }
