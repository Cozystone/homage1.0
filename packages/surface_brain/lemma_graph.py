from __future__ import annotations

from typing import Any


DEFAULT_LEMMAS = {
    "kubernetes": {"ko": "쿠버네티스", "en": "Kubernetes"},
    "containers": {"ko": "컨테이너", "en": "containers"},
    "operations manager": {"ko": "운영 관리자", "en": "operations manager"},
    "GraphRAG": {"ko": "GraphRAG", "en": "GraphRAG"},
    "Evidence": {"ko": "근거 문서", "en": "evidence documents"},
}


def lemma_candidates(semantic_context: dict[str, Any], language: str) -> list[dict[str, Any]]:
    concepts = list(semantic_context.get("concepts") or [])
    for relation in semantic_context.get("relations") or []:
        for key in ("source", "target"):
            value = relation.get(key)
            if value and value not in concepts:
                concepts.append(value)
    rows = []
    for concept in concepts[:16]:
        normalized = str(concept)
        lookup = DEFAULT_LEMMAS.get(normalized, DEFAULT_LEMMAS.get(normalized.lower()))
        label = lookup.get(language, normalized) if lookup else normalized
        rows.append(
            {
                "id": f"lemma.{normalized}",
                "concept": normalized,
                "label": label,
                "language": language,
                "fit_score": 0.78,
                "style_score": 0.7,
                "language_score": 0.9,
                "repetition_penalty": 0.0,
                "prior_success_weight": 0.7,
                "user_preference_weight": 0.7,
            }
        )
    return rows
