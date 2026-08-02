from __future__ import annotations

import re
from typing import Any

from .models import SemanticProjection, SourceSentence, hash_text, normalize_text


def _concepts(text: str) -> list[str]:
    known = [
        ("쿠버네티스", "Kubernetes"),
        ("kubernetes", "Kubernetes"),
        ("컨테이너", "containers"),
        ("container", "containers"),
        ("GraphRAG", "GraphRAG"),
        ("KnowledgeGraph", "KnowledgeGraph"),
        ("Evidence", "Evidence"),
        ("근거", "Evidence"),
        ("Payload Vault", "Payload Vault"),
        ("Ghost Shell", "Ghost Shell"),
    ]
    found: list[str] = []
    lower = text.lower()
    for needle, concept in known:
        if needle.lower() in lower and concept not in found:
            found.append(concept)
    if not found:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\uac00-\ud7a3]{2,}", text):
            if token not in found:
                found.append(token)
            if len(found) >= 6:
                break
    return found


def extract_semantic_projection(sentence: SourceSentence | dict[str, Any]) -> dict[str, Any]:
    source = sentence if isinstance(sentence, SourceSentence) else SourceSentence.from_text(
        str(sentence.get("text") or ""),
        source_id=sentence.get("source_id"),
        url=sentence.get("url"),
        title=sentence.get("title"),
        license=sentence.get("license", "unknown"),
        usage_allowed=bool(sentence.get("usage_allowed", False)),
        metadata=sentence.get("metadata") if isinstance(sentence.get("metadata"), dict) else {},
    )
    text = normalize_text(source.text)
    concepts = _concepts(text)
    relations: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    lower = text.lower()
    if "kubernetes" in lower or "쿠버네티스" in text:
        if "container" in lower or "컨테이너" in text:
            relations.append({"source": "Kubernetes", "relation": "manages", "target": "containers", "confidence": 0.86})
        if "자동" in text or "automatic" in lower:
            relations.append({"source": "Kubernetes", "relation": "performs", "target": "automatic deployment", "confidence": 0.78})
        if "관리자" in text or "manager" in lower or "가깝" in text:
            relations.append({"source": "Kubernetes", "relation": "analogy", "target": "operations manager", "confidence": 0.74})
    if "graphrag" in lower and ("evidence" in lower or "근거" in text):
        relations.append({"source": "GraphRAG", "relation": "uses", "target": "Evidence", "confidence": 0.84})
    if not relations and len(concepts) >= 2:
        relations.append({"source": concepts[0], "relation": "related_to", "target": concepts[1], "confidence": 0.52})
    if relations:
        claims = [
            {
                "claim_id": f"claim_{hash_text(source.source_hash + relation['source'] + relation['relation'] + relation['target'])[:12]}",
                "text": f"{relation['source']} {relation['relation']} {relation['target']}",
                "relations": [relation],
                "confidence": relation.get("confidence", 0.5),
            }
            for relation in relations
        ]
    projection = SemanticProjection(
        projection_id=f"sem_{hash_text('semantic:' + source.source_hash)[:18]}",
        source_hash=source.source_hash,
        concepts=concepts,
        entities=concepts,
        claims=claims,
        relations=relations,
        evidence=[{"source_hash": source.source_hash, "metadata_only": True, "raw_text_stored": False}],
        trust_score=0.74 if relations else 0.48,
        extraction_confidence=0.82 if relations else 0.56,
    )
    return projection.to_dict()
