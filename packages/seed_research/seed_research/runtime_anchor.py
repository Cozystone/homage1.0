from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .core import read_jsonl, seed_root


def _tokens(text: str) -> list[str]:
    tokens = re.findall(r"[0-9A-Za-z_\-\uac00-\ud7a3]+", text.casefold())
    return [token for token in tokens if len(token) > 1]


def _load_current(root: str | Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    current = seed_root(root) / "current"
    concepts = read_jsonl(current / "seed_concepts.jsonl")
    edges = read_jsonl(current / "seed_edges.jsonl")
    aliases = read_jsonl(current / "seed_aliases.jsonl")
    if not concepts:
        viewer_path = current / "viewer_export.json"
        if viewer_path.exists():
            viewer = json.loads(viewer_path.read_text(encoding="utf-8"))
            concepts = [
                {
                    "concept_id": node.get("id"),
                    "label": node.get("label"),
                    "labels": node.get("labels") or {},
                    "aliases": node.get("aliases") or {},
                    "confidence": node.get("confidence", 0.0),
                    "trust_state": node.get("trust_state"),
                    "verification_state": node.get("verification_state"),
                    "source_scope": "seed",
                    "privacy_scope": "public",
                }
                for node in viewer.get("nodes", [])
                if isinstance(node, dict)
            ]
            edges = [edge for edge in viewer.get("edges", []) if isinstance(edge, dict)]
    return concepts, edges, aliases


def _concept_terms(concept: dict[str, Any], alias_rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    label = str(concept.get("label") or "")
    if label:
        terms.append((label, "label"))
    labels = concept.get("labels") if isinstance(concept.get("labels"), dict) else {}
    for value in labels.values():
        if value:
            terms.append((str(value), "label"))
    aliases = concept.get("aliases") if isinstance(concept.get("aliases"), dict) else {}
    for values in aliases.values():
        if isinstance(values, list):
            terms.extend((str(value), "alias") for value in values if value)
    concept_id = str(concept.get("concept_id") or concept.get("id") or "")
    for row in alias_rows:
        if str(row.get("concept_id")) == concept_id and row.get("alias"):
            terms.append((str(row["alias"]), "alias"))
    terms.append((concept_id.removeprefix("seed.core.").replace("_", " "), "label"))
    dedup: dict[str, str] = {}
    for term, reason in terms:
        normalized = " ".join(_tokens(term))
        if normalized:
            dedup.setdefault(normalized, reason)
    return [(term, reason) for term, reason in dedup.items()]


def _append_relation_context(
    matched: list[dict[str, Any]],
    matched_ids: set[str],
    concepts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_concepts: int = 8,
) -> None:
    if not matched_ids or len(matched_ids) > 4:
        return
    concept_by_id = {str(concept.get("concept_id") or concept.get("id") or ""): concept for concept in concepts}
    priority_relations = {
        "belongs_to_layer",
        "depends_on",
        "has_evidence",
        "has_source",
        "produces",
        "requires",
        "verifies",
        "weakens",
    }
    for edge in sorted(edges, key=lambda item: (-float(item.get("confidence") or item.get("weight") or 0.0), str(item.get("relation")))):
        relation = str(edge.get("relation") or "")
        if relation not in priority_relations:
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in matched_ids and target not in matched_ids:
            related_id = target
        elif target in matched_ids and source not in matched_ids:
            related_id = source
        else:
            continue
        concept = concept_by_id.get(related_id)
        if not concept:
            continue
        matched_ids.add(related_id)
        matched.append(
            {
                "concept_id": related_id,
                "label": concept.get("label") or related_id,
                "aliases_matched": [],
                "match_reason": "relation_context",
                "confidence": round(float(edge.get("confidence") or edge.get("weight") or 0.68) * 0.82, 3),
            }
        )
        if len(matched_ids) >= max_concepts:
            break


def resolve_seed_concepts(query: str, root: str | Path | None = None) -> dict[str, Any]:
    concepts, edges, aliases = _load_current(root)
    query_tokens = set(_tokens(query))
    query_text = " ".join(_tokens(query))
    matched: list[dict[str, Any]] = []
    matched_ids: set[str] = set()

    for concept in concepts:
        concept_id = str(concept.get("concept_id") or concept.get("id") or "")
        if not concept_id:
            continue
        term_hits: list[str] = []
        reasons: list[str] = []
        for term, reason in _concept_terms(concept, aliases):
            term_tokens = set(term.split())
            if not term_tokens:
                continue
            phrase_hit = term in query_text and len(term) > 2
            token_hit = bool(term_tokens.intersection(query_tokens))
            if phrase_hit or token_hit:
                term_hits.append(term)
                reasons.append(reason)
        if term_hits:
            confidence = min(0.98, 0.52 + len(set(term_hits)) * 0.12 + float(concept.get("confidence") or 0) * 0.22)
            matched.append(
                {
                    "concept_id": concept_id,
                    "label": concept.get("label") or concept_id,
                    "aliases_matched": sorted(set(term_hits))[:8],
                    "match_reason": "alias" if "alias" in reasons else "label",
                    "confidence": round(confidence, 3),
                }
            )
            matched_ids.add(concept_id)

    _append_relation_context(matched, matched_ids, concepts, edges)

    matched.sort(key=lambda item: (-float(item["confidence"]), item["concept_id"]))
    edge_rows = []
    matched_ids = {item["concept_id"] for item in matched}
    for edge in edges:
        if edge.get("source") in matched_ids and edge.get("target") in matched_ids:
            edge_rows.append(
                {
                    "source": edge.get("source"),
                    "relation": edge.get("relation"),
                    "target": edge.get("target"),
                    "confidence": round(float(edge.get("confidence") or edge.get("weight") or 0.0), 3),
                }
            )
    edge_rows.sort(key=lambda item: (-float(item["confidence"]), str(item["relation"])))

    return {
        "query": query,
        "matched_seed_concepts": matched[:12],
        "matched_seed_edges": edge_rows[:18],
        "seed_anchor_ready": bool(concepts),
    }


def _candidate_fragments(root: str | Path = "data/cloud_brain") -> list[dict[str, Any]]:
    inbox = Path(root) / "inbox"
    if not inbox.exists():
        return []
    fragments: list[dict[str, Any]] = []
    for path in sorted(inbox.glob("candidate_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            fragments.append(payload)
    return fragments


def align_cloud_candidates(seed_trace: dict[str, Any], cloud_root: str | Path = "data/cloud_brain") -> dict[str, Any]:
    fragments = _candidate_fragments(cloud_root)
    if not fragments:
        return {
            "cloud_checked": True,
            "candidate_fragments_checked": 0,
            "fragments_aligned_to_seed": 0,
            "alignment_ready": True,
            "aligned_fragment_ids": [],
        }
    concept_terms = defaultdict(list)
    for concept in seed_trace.get("matched_seed_concepts", []):
        concept_terms[concept["concept_id"]].append(str(concept.get("label") or ""))
        concept_terms[concept["concept_id"]].extend(str(alias) for alias in concept.get("aliases_matched", []))

    aligned_ids: list[str] = []
    for fragment in fragments:
        text = f"{fragment.get('title', '')} {fragment.get('text', '')}".casefold()
        for terms in concept_terms.values():
            if any(term and term.casefold() in text for term in terms):
                aligned_ids.append(str(fragment.get("fragment_id") or fragment.get("content_hash") or "unknown"))
                break
    return {
        "cloud_checked": True,
        "candidate_fragments_checked": len(fragments),
        "fragments_aligned_to_seed": len(set(aligned_ids)),
        "alignment_ready": True,
        "aligned_fragment_ids": sorted(set(aligned_ids))[:12],
    }


def seed_anchor_trace(query: str, root: str | Path | None = None) -> dict[str, Any]:
    resolved = resolve_seed_concepts(query, root)
    return {
        "enabled": True,
        "seed_used": bool(resolved["matched_seed_concepts"]),
        "matched_concepts": resolved["matched_seed_concepts"],
        "matched_edges": resolved["matched_seed_edges"],
        "role": "concept_alignment_and_verification_anchor",
        "final_answer_generation_claimed": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
    }
