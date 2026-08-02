from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .fusion import fusion_ratio_from_context
from .graph_store import query_lazy_chunks, query_lazy_subgraph
from .synthesizer import LocalSynthesizer

try:
    from seed_research.runtime_anchor import seed_anchor_trace as _seed_anchor_trace
except Exception:  # pragma: no cover - optional research package boundary
    _seed_anchor_trace = None


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
        elif current:
            token = "".join(current).strip("-_")
            if token:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).strip("-_")
        if token:
            tokens.append(token)
    return [token for token in tokens if len(token) > 1 or token.isdigit()]


def _normalized_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _effective_memory_dir(cleaned_dir: str, memory_dir: str) -> str:
    if memory_dir == "data/memory" and Path(cleaned_dir) != Path("data/cleaned"):
        return str(Path(cleaned_dir).parent / "memory")
    return memory_dir


def _is_internal_structure_query(query: str) -> bool:
    normalized = _normalized_query(query)
    return any(word in normalized for word in ["atanor", "rag", "graphrag", "ghost", "shell", "payload", "vault", "architecture", "system", "engine", "\uad6c\uc870"])


def _query_seed_terms(query: str) -> list[str]:
    query_terms = _tokens(query)
    normalized = _normalized_query(query)
    identity_like = any(
        marker in normalized
        for marker in [
            "who are you",
            "what are you",
            "what is atanor",
            "atanor",
            "local brain",
            "cloud brain",
            "ghost shell",
            "payload vault",
            "graph rag",
            "graphrag",
            "꾧뎄",
            "萸먯빞",
        ]
    )
    if identity_like:
        return list(dict.fromkeys([*query_terms, "atanor", "architecture", "ghost", "shell", "payload", "vault", "local", "brain", "cloud", "graphrag"]))
    return query_terms


def _seed_anchor_trace_for_query(query: str) -> dict[str, Any]:
    if _seed_anchor_trace is None:
        return {
            "enabled": False,
            "seed_used": False,
            "matched_concepts": [],
            "matched_edges": [],
            "role": "optional_seed_research_package_unavailable",
            "final_answer_generation_claimed": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_engine": False,
        }
    try:
        return _seed_anchor_trace(query)
    except Exception as exc:
        return {
            "enabled": False,
            "seed_used": False,
            "matched_concepts": [],
            "matched_edges": [],
            "role": "seed_anchor_trace_error",
            "error": str(exc),
            "final_answer_generation_claimed": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_engine": False,
        }


def _lexical_score(query_terms: list[str], chunk: dict[str, Any]) -> float:
    token_counts = chunk.get("tokens") or Counter(_tokens(str(chunk.get("text") or "")))
    if not token_counts or not query_terms:
        return 0.0
    total = float(chunk.get("token_total") or sum(token_counts.values()) or 1)
    score = 0.0
    for term in query_terms:
        score += float(token_counts.get(term, 0)) / total
        if term in str(chunk.get("text") or "").lower():
            score += 0.08
    return score


def _rank_chunks(query: str, chunks: list[dict[str, Any]], expanded_terms: set[str], *, limit: int = 6) -> list[dict[str, Any]]:
    query_terms = _tokens(query)
    expanded = set(expanded_terms)
    ranked: list[dict[str, Any]] = []
    for chunk in chunks:
        lexical = _lexical_score(query_terms, chunk)
        graph_bonus = 0.03 * sum(1 for term in expanded if term and term in str(chunk.get("text") or "").lower())
        temporal = float(chunk.get("temporal_weight") or chunk.get("score") or 0.0)
        score = lexical + graph_bonus + temporal * 0.1
        item = dict(chunk)
        item["score"] = round(score, 6)
        item["lexical_score"] = round(lexical, 6)
        item["graph_score"] = round(graph_bonus, 6)
        ranked.append(item)
    ranked.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("chunk_id") or "")))
    return ranked[:limit]


def _citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": chunk.get("chunk_id"),
            "doc_id": chunk.get("doc_id"),
            "path": chunk.get("path"),
            "score": chunk.get("score", 0),
            "snippet": str(chunk.get("text") or "")[:260],
        }
        for chunk in chunks
    ]


def _confidence(chunks: list[dict[str, Any]], matched_nodes: list[dict[str, Any]], matched_edges: list[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    top_score = max(float(chunk.get("score") or 0.0) for chunk in chunks)
    graph_density = min(1.0, (len(matched_nodes) + len(matched_edges)) / 24.0)
    return round(min(0.98, 0.25 + top_score + graph_density * 0.25), 3)


def query_graphrag(
    query: str,
    cleaned_dir: str = "data/cleaned",
    ontology_dir: str = "data/ontology",
    memory_dir: str = "data/memory",
) -> dict[str, Any]:
    effective_memory = _effective_memory_dir(cleaned_dir, memory_dir)
    query_terms = _tokens(query)
    seed_terms = _query_seed_terms(query)
    seed_anchor = _seed_anchor_trace_for_query(query)

    subgraph = query_lazy_subgraph(seed_terms or [query], effective_memory, max_depth=3, max_nodes=512, max_edges=2048)
    expanded_terms = set(subgraph.get("expanded_terms") or set(query_terms))
    chunks = query_lazy_chunks(query, expanded_terms, effective_memory, limit=48)
    ranked_chunks = _rank_chunks(query, chunks, expanded_terms)

    matched_nodes = list(subgraph.get("nodes") or [])
    matched_edges = list(subgraph.get("edges") or [])
    graph_paths = list(subgraph.get("graph_paths") or [])
    payload_docs = list(subgraph.get("payload_docs") or [])
    if not ranked_chunks and payload_docs:
        ranked_chunks = _rank_chunks(query, payload_docs, expanded_terms)

    resolved_identity_seed = bool(set(seed_terms) - set(query_terms))
    has_direct_lexical_hit = any(float(chunk.get("lexical_score") or 0.0) > 0.0 for chunk in ranked_chunks) or (resolved_identity_seed and bool(ranked_chunks))
    if (not ranked_chunks or not has_direct_lexical_hit) and not _is_internal_structure_query(query):
        utterance = LocalSynthesizer().synthesize(query, [], matched_nodes, matched_edges, graph_paths, memory_dir=effective_memory)
        fusion_ratio = fusion_ratio_from_context(
            query=query,
            matched_nodes=matched_nodes,
            matched_edges=matched_edges,
            evidence_docs=[],
            local_answer_confidence=0.0,
        )
        return {
            "query": query,
            "method": "atanor-research-no-evidence-v1",
            "answer": utterance["answer"],
            "pmv": utterance.get("pmv", {}),
            "claim_plan": utterance.get("claim_plan", []),
            "active_concepts": utterance.get("active_concepts", []),
            "matched_nodes": [],
            "matched_edges": [],
            "evidence_docs": [],
            "citations": [],
            "graph_paths": [],
            "follow_up_questions": [],
            "retrieval_trace": {
                "strategy": "no local evidence; external LLM disabled",
                "query_terms": query_terms,
                "seed_terms": seed_terms,
                "expanded_terms": sorted(expanded_terms),
                "ranked_chunk_ids": [],
                "matched_node_ids": [],
                "fetch_sequence": subgraph.get("fetch_logs", []),
                "fusion_ratio": fusion_ratio,
                "seed_anchor": seed_anchor,
            },
            "fusion_ratio": fusion_ratio,
            "confidence": 0.0,
            "answer_kind": utterance.get("answer_kind", "native_graph_token_generation"),
            "native_generation_failed_quality_check": utterance.get("native_generation_failed_quality_check"),
            "degeneration": utterance.get("degeneration", {}),
            "training_feedback_recorded": utterance.get("training_feedback_recorded", False),
            "raw_native_output": utterance.get("raw_native_output", utterance["answer"]),
            "answer_engine": utterance["answer_engine"],
            "ghost_shell": subgraph.get("ghost_shell", {}),
            "fetch_sequence": subgraph.get("fetch_logs", []),
        }

    synthesis_docs = ranked_chunks
    utterance = LocalSynthesizer().synthesize(query, synthesis_docs, matched_nodes, matched_edges, graph_paths, memory_dir=effective_memory)
    citations = _citations(ranked_chunks)
    confidence = _confidence(ranked_chunks, matched_nodes, matched_edges)
    fusion_ratio = fusion_ratio_from_context(
        query=query,
        matched_nodes=matched_nodes,
        matched_edges=matched_edges,
        evidence_docs=ranked_chunks,
        local_answer_confidence=confidence,
    )
    return {
        "query": query,
        "method": "atanor-graph-token-rag-v1",
        "answer": utterance["answer"],
        "pmv": utterance.get("pmv", {}),
        "claim_plan": utterance.get("claim_plan", []),
        "active_concepts": utterance.get("active_concepts", []),
        "matched_nodes": matched_nodes,
        "matched_edges": matched_edges,
        "evidence_docs": ranked_chunks,
        "citations": citations,
        "graph_paths": graph_paths,
        "follow_up_questions": [],
        "retrieval_trace": {
            "strategy": "lazy Ghost Shell subgraph + Payload Vault fetch + local synthesis",
            "query_terms": query_terms,
            "seed_terms": seed_terms,
            "expanded_terms": sorted(expanded_terms),
            "ranked_chunk_ids": [chunk.get("chunk_id") for chunk in ranked_chunks],
            "matched_node_ids": [node.get("id") or node.get("node_hash") for node in matched_nodes],
            "fetch_sequence": subgraph.get("fetch_logs", []),
            "active_hashes": subgraph.get("active_hashes", []),
            "limits": subgraph.get("limits", {}),
            "fusion_ratio": fusion_ratio,
            "seed_anchor": seed_anchor,
        },
        "fusion_ratio": fusion_ratio,
        "confidence": confidence,
        "answer_kind": utterance.get("answer_kind", "native_graph_token_generation"),
        "native_generation_failed_quality_check": utterance.get("native_generation_failed_quality_check"),
        "degeneration": utterance.get("degeneration", {}),
        "training_feedback_recorded": utterance.get("training_feedback_recorded", False),
        "raw_native_output": utterance.get("raw_native_output", utterance["answer"]),
        "native_stop_reason": utterance.get("native_stop_reason"),
        "source_clusters": utterance.get("source_clusters", []),
        "answer_engine": utterance["answer_engine"],
        "ghost_shell": subgraph.get("ghost_shell", {}),
        "fetch_sequence": subgraph.get("fetch_logs", []),
    }
