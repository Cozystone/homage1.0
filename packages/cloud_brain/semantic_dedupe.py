from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .semantic_store import SemanticCloudStore, utc_now_iso


def _append_history(store: SemanticCloudStore, kind: str, event: dict[str, Any]) -> None:
    """Append-only temporal-event sidecar for 4D permanent memory (BLOCKER #2).

    When an existing concept/relation row is updated in place (confidence/trust/
    seen_count), the prior state would otherwise be lost. This records each change
    as an append-only event in ``<store>/<kind>_history.jsonl`` so the timeline is
    preserved and ``V(t)`` is reconstructable.

    Pure observability: it does NOT change upsert semantics, is NOT part of the
    answer-path ``STORE_FILES`` (filename differs from ``concepts.jsonl`` /
    ``relations.jsonl``), and any failure is swallowed so it can never break the
    live write path.
    """
    try:
        path = store.paths["store"] / f"{kind}_history.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


ALIAS_CANONICAL: dict[str, str] = {
    "kubernetes": "kubernetes",
    "쿠버네티스": "kubernetes",
    "container": "container",
    "containers": "container",
    "컨테이너": "container",
    "containerized application": "containerized_application",
    "containerized applications": "containerized_application",
    "컨테이너화된 애플리케이션": "containerized_application",
    "ai": "ai",
    "인공지능": "ai",
    "ontology": "ontology",
    "온톨로지": "ontology",
    "graphrag": "graphrag",
    "그래프rag": "graphrag",
    "그래프 rag": "graphrag",
    "sqlite": "sqlite",
    "database": "database",
    "데이터베이스": "database",
    "quantum computer": "quantum_computer",
    "양자컴퓨터": "quantum_computer",
    "open-source platform": "open_source_platform",
    "open source platform": "open_source_platform",
    "오픈소스 플랫폼": "open_source_platform",
    "automatic deployment": "automatic_deployment",
    "자동 배포": "automatic_deployment",
    "management": "management",
    "관리": "management",
}


def normalize_concept_name(text: str) -> str:
    value = re.sub(r"[\s\-_]+", " ", str(text or "").strip().casefold())
    value = re.sub(r"[^\w\s가-힣+#]", "", value).strip()
    if value in ALIAS_CANONICAL:
        return ALIAS_CANONICAL[value]
    return re.sub(r"\s+", "_", value)


def _concept_id(normalized: str) -> str:
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"scc_{digest}"


def _merge_aliases(existing: list[str], *values: str) -> list[str]:
    merged: list[str] = []
    for value in [*existing, *values]:
        text = str(value or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged[:24]


def resolve_or_create_concept(candidate: dict[str, Any], store: SemanticCloudStore, *, source_hash: str) -> tuple[dict[str, Any], bool]:
    concepts = store.load_concepts()
    raw_name = str(candidate.get("name") or candidate.get("canonical_name") or "")
    normalized = normalize_concept_name(raw_name)
    concept_id = candidate.get("concept_id") or _concept_id(normalized)
    now = utc_now_iso()
    created = concept_id not in concepts
    if created:
        concepts[concept_id] = {
            "concept_id": concept_id,
            "canonical_name": raw_name.strip() or normalized.replace("_", " "),
            "aliases": _merge_aliases([], raw_name, normalized.replace("_", " ")),
            "language_labels": candidate.get("language_labels") or {},
            "description": candidate.get("description"),
            "trust": float(candidate.get("trust") or 0.55),
            "confidence": float(candidate.get("confidence") or 0.6),
            "seen_count": 1,
            "source_hashes": [source_hash] if source_hash else [],
            "created_at": now,
            "updated_at": now,
            "metadata": {"normalization": "deterministic_v0", **(candidate.get("metadata") or {})},
        }
    else:
        row = concepts[concept_id]
        _prev = {"confidence": row.get("confidence"), "trust": row.get("trust"), "seen_count": row.get("seen_count")}
        seen = int(row.get("seen_count") or 0) + 1
        old_conf = float(row.get("confidence") or 0.5)
        new_conf = float(candidate.get("confidence") or old_conf)
        row["aliases"] = _merge_aliases(list(row.get("aliases") or []), raw_name, normalized.replace("_", " "))
        labels = dict(row.get("language_labels") or {})
        labels.update(candidate.get("language_labels") or {})
        row["language_labels"] = labels
        row["seen_count"] = seen
        row["confidence"] = round(((old_conf * (seen - 1)) + new_conf) / seen, 4)
        row["trust"] = min(1.0, round(float(row.get("trust") or 0.5) + 0.015, 4))
        if source_hash and source_hash not in row.get("source_hashes", []):
            row.setdefault("source_hashes", []).append(source_hash)
        row["updated_at"] = now
        _append_history(store, "concept", {
            "t_observed": now, "concept_id": concept_id, "reason": "dedupe_upsert",
            "prev": _prev,
            "next": {"confidence": row["confidence"], "trust": row["trust"], "seen_count": row["seen_count"]},
            "source_hash": source_hash,
        })
    store.save_concepts(concepts)
    return concepts[concept_id], created


def relation_id_for(source_concept_id: str, relation: str, target_concept_id: str) -> str:
    key = f"{source_concept_id}|{relation}|{target_concept_id}"
    return f"scr_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:18]}"


def upsert_semantic_relation(
    source_concept_id: str,
    relation: str,
    target_concept_id: str,
    source_hash: str,
    confidence: float,
    store: SemanticCloudStore,
) -> tuple[dict[str, Any], bool]:
    relations = store.load_relations()
    rel = re.sub(r"\s+", "_", str(relation or "related_to").strip().casefold())
    relation_id = relation_id_for(source_concept_id, rel, target_concept_id)
    now = utc_now_iso()
    created = relation_id not in relations
    if created:
        relations[relation_id] = {
            "relation_id": relation_id,
            "source_concept_id": source_concept_id,
            "relation": rel,
            "target_concept_id": target_concept_id,
            "weight": min(1.0, max(0.1, float(confidence or 0.6))),
            "confidence": min(1.0, max(0.1, float(confidence or 0.6))),
            "trust": 0.58,
            "seen_count": 1,
            "source_hashes": [source_hash] if source_hash else [],
            "created_at": now,
            "updated_at": now,
            "metadata": {"merge_policy": "bounded_seen_count_strengthening_v0"},
        }
    else:
        row = relations[relation_id]
        _prev = {"confidence": row.get("confidence"), "trust": row.get("trust"),
                 "weight": row.get("weight"), "seen_count": row.get("seen_count")}
        seen = int(row.get("seen_count") or 0) + 1
        old_conf = float(row.get("confidence") or 0.5)
        new_conf = float(confidence or old_conf)
        row["seen_count"] = seen
        row["weight"] = min(1.0, round(float(row.get("weight") or 0.5) + 0.08, 4))
        row["confidence"] = round(((old_conf * (seen - 1)) + new_conf) / seen, 4)
        row["trust"] = min(1.0, round(float(row.get("trust") or 0.5) + 0.02, 4))
        if source_hash and source_hash not in row.get("source_hashes", []):
            row.setdefault("source_hashes", []).append(source_hash)
        row["updated_at"] = now
        _append_history(store, "relation", {
            "t_observed": now, "relation_id": relation_id, "reason": "dedupe_upsert",
            "prev": _prev,
            "next": {"confidence": row["confidence"], "trust": row["trust"],
                     "weight": row["weight"], "seen_count": row["seen_count"]},
            "source_hash": source_hash,
        })
    store.save_relations(relations)
    return relations[relation_id], created
