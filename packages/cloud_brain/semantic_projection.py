from __future__ import annotations

import hashlib
import re
from typing import Any

from packages.surface_brain.semantic_projection import extract_semantic_projection


HANGUL_RE = re.compile(r"[가-힣]")


def project_semantics(sentence: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(sentence, str):
        return extract_semantic_projection({"text": sentence})
    return extract_semantic_projection(sentence)


def _language_of(text: str, language: str) -> str:
    if language in {"ko", "en"}:
        return language
    return "ko" if HANGUL_RE.search(text) else "en"


def _concept(name: str, *, language: str, confidence: float = 0.68, **metadata: Any) -> dict[str, Any]:
    labels = {"ko" if HANGUL_RE.search(name) else "en": name}
    if language in {"ko", "en"}:
        labels.setdefault(language, name)
    return {
        "name": name,
        "canonical_name": name,
        "language_labels": labels,
        "confidence": confidence,
        "trust": 0.56,
        "metadata": metadata,
    }


def _relation(source: str, relation: str, target: str, confidence: float = 0.66) -> dict[str, Any]:
    return {"source": source, "relation": relation, "target": target, "confidence": confidence}


def project_sentence_to_semantic_candidates(sentence: str, language: str = "auto") -> dict[str, Any]:
    """Project one source sentence into deterministic v0 semantic candidates.

    This is intentionally small, auditable, and local-only. It is not a general
    semantic parser and does not use an external LLM or sLLM.
    """

    text = re.sub(r"\s+", " ", str(sentence or "").strip())
    detected = _language_of(text, language)
    lowered = text.casefold()
    concepts: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    def add_concept(name: str, confidence: float = 0.68) -> None:
        cleaned = str(name or "").strip()
        if cleaned and not any(item["name"] == cleaned for item in concepts):
            concepts.append(_concept(cleaned, language=detected, confidence=confidence))

    def add_relation(source: str, relation: str, target: str, confidence: float = 0.66) -> None:
        source = str(source or "").strip()
        target = str(target or "").strip()
        if not source or not target:
            return
        add_concept(source, confidence)
        add_concept(target, confidence)
        relation_row = _relation(source, relation, target, confidence)
        if relation_row not in relations:
            relations.append(relation_row)

    has_kubernetes = "쿠버네티스" in text or "kubernetes" in lowered
    if has_kubernetes:
        source = "쿠버네티스" if "쿠버네티스" in text else "Kubernetes"
        add_concept(source, 0.84)
        if "오픈소스" in text or "open-source" in lowered or "open source" in lowered:
            add_relation(source, "is_a", "오픈소스 플랫폼" if detected == "ko" else "open-source platform", 0.78)
        if "컨테이너" in text or "container" in lowered:
            target = "컨테이너화된 애플리케이션" if detected == "ko" else "containerized applications"
            add_relation(source, "manages", target, 0.84)
        if "배포" in text or "deployment" in lowered or "deploy" in lowered:
            add_relation(source, "performs", "자동 배포" if detected == "ko" else "automatic deployment", 0.78)
        if "관리" in text or "manages" in lowered or "management" in lowered:
            add_relation(source, "used_for", "관리" if detected == "ko" else "management", 0.72)

    if "graphrag" in lowered or "그래프rag" in lowered or "그래프RAG" in text:
        source = "GraphRAG"
        add_concept(source, 0.74)
        if "근거" in text or "evidence" in lowered:
            add_relation(source, "used_for", "evidence grounding", 0.7)
        if "그래프" in text or "graph" in lowered:
            add_relation(source, "requires", "knowledge graph", 0.68)

    if "sqlite" in lowered:
        add_relation("SQLite", "is_a", "database", 0.72)
    if "양자컴퓨터" in text or "quantum computer" in lowered:
        add_relation("양자컴퓨터" if detected == "ko" else "quantum computer", "is_a", "computing system", 0.62)

    if not relations:
        english_def = re.search(r"\b([A-Z][A-Za-z0-9.+#-]{1,40})\s+is\s+(?:an?\s+|the\s+)?([^.;]{3,80})", text)
        korean_def = re.search(r"(.{2,40}?)(?:은|는)\s+(.{2,80}?)(?:입니다|이다|에 가깝습니다|에 가깝다)", text)
        if english_def:
            add_relation(english_def.group(1).strip(), "is_a", english_def.group(2).strip(), 0.56)
        elif korean_def:
            add_relation(korean_def.group(1).strip(), "is_a", korean_def.group(2).strip(), 0.56)

    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "concept_candidates": concepts,
        "relation_candidates": relations,
        "evidence": {
            "source_hash": source_hash,
            "text_hash": source_hash,
            "short_snippet": text[:240] if len(text) <= 500 else None,
        },
        "extraction_confidence": 0.72 if relations else 0.38,
        "limitations": [
            "deterministic_v0_heuristics",
            "not_general_cross_lingual_entity_resolution",
            "no_external_llm_or_sllm",
        ],
    }
