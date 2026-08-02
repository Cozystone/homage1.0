from __future__ import annotations

import re
from typing import Any

from .models import SourceSentence, SurfaceProjection, hash_text, normalize_text


KO_MARKERS = {
    "쉽게 말하면": ("simplification", "beginner analogy"),
    "다만": ("caveat", "caveat transition"),
    "핵심은": ("summary", "concise answer"),
    "즉": ("summary", "concise answer"),
    "예를 들어": ("example", "list explanation"),
    "반면": ("contrast", "contrast frame"),
    "정리하면": ("summary", "concise answer"),
    "주의할 점은": ("warning", "caveat transition"),
}

EN_MARKERS = {
    "in simple terms": ("simplification", "beginner analogy"),
    "however": ("caveat", "caveat transition"),
    "the key point is": ("summary", "concise answer"),
    "for example": ("example", "list explanation"),
    "in contrast": ("contrast", "contrast frame"),
    "to summarize": ("summary", "concise answer"),
    "one caveat is": ("caveat", "caveat transition"),
}


def _sentence_shape(text: str) -> str:
    token_count = len(re.findall(r"[\w\uac00-\ud7a3]+", text, flags=re.UNICODE))
    if token_count <= 10:
        return "short"
    if token_count <= 28:
        return "medium"
    return "long"


def _technicality(text: str) -> float:
    terms = ("GraphRAG", "Kubernetes", "QUBO", "ontology", "컨테이너", "쿠버네티스", "온톨로지", "Graph")
    return min(1.0, sum(1 for term in terms if term.lower() in text.lower()) / 4)


def _lemma_choices(text: str) -> dict[str, list[str]]:
    lower = text.lower()
    lemmas: dict[str, list[str]] = {}
    if "쿠버네티스" in text or "kubernetes" in lower:
        lemmas["kubernetes"] = ["쿠버네티스", "Kubernetes", "컨테이너 오케스트레이션"]
    if "컨테이너" in text or "container" in lower:
        lemmas["container_orchestration"] = ["컨테이너 오케스트레이션", "컨테이너 관리 시스템", "container orchestration"]
    if "graphrag" in lower:
        lemmas["graphrag"] = ["GraphRAG", "그래프 기반 검색 증강 생성", "graph-based retrieval"]
    if "evidence" in lower or "근거" in text:
        lemmas["evidence"] = ["근거", "Evidence", "검증 자료"]
    return lemmas


def extract_surface_projection(sentence: SourceSentence | dict[str, Any]) -> dict[str, Any]:
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
    marker_table = KO_MARKERS if source.language in {"ko", "mixed"} else EN_MARKERS
    lower = text.lower()
    phrase_patterns: list[str] = []
    discourse_moves: list[str] = []
    constructions: list[str] = []
    for marker, (move, construction) in marker_table.items():
        haystack = lower if source.language == "en" else text
        needle = marker.lower() if source.language == "en" else marker
        if needle in haystack:
            phrase_patterns.append(marker)
            discourse_moves.append(move)
            constructions.append(construction)
    if "에 가깝" in text or "is close to" in lower or "is like" in lower:
        discourse_moves.append("analogy")
        constructions.append("beginner analogy")
    if "는 " in text and ("입니다" in text or "한다" in text or "합니다" in text):
        discourse_moves.append("definition")
        constructions.append("simple definition")
    if "because" in lower or "때문" in text:
        discourse_moves.append("cause")
        constructions.append("cause-effect frame")
    if not discourse_moves:
        discourse_moves.append("explanation")
    if not constructions:
        constructions.append("technical explanation" if _technicality(text) > 0.2 else "concise answer")
    token_count = len(re.findall(r"[\w\uac00-\ud7a3]+", text, flags=re.UNICODE))
    style_features = {
        "language": source.language,
        "formality": "polite" if any(token in text for token in ("습니다", "합니다", "입니다")) else "neutral",
        "sentence_length": _sentence_shape(text),
        "density": round(min(1.0, token_count / 36), 4),
        "technicality": round(_technicality(text), 4),
        "warmth": 0.72 if phrase_patterns else 0.48,
        "assertiveness": 0.64 if any(token in text for token in ("입니다", "is", "are")) else 0.46,
        "uncertainty": 0.22 if any(token in text for token in ("가깝", "like", "roughly")) else 0.08,
        "analogy_usage": "analogy" in discourse_moves,
        "bullet_tendency": False,
        "explanation_depth": "beginner" if "simplification" in discourse_moves else "standard",
    }
    projection = SurfaceProjection(
        projection_id=f"surf_{hash_text('surface:' + source.source_hash)[:18]}",
        source_hash=source.source_hash,
        language=source.language,
        discourse_moves=sorted(set(discourse_moves), key=discourse_moves.index),
        constructions=sorted(set(constructions), key=constructions.index),
        phrase_patterns=phrase_patterns,
        lemma_choices=_lemma_choices(text),
        style_features=style_features,
        register="technical-friendly" if _technicality(text) else "general",
        tone="friendly technical explanation" if phrase_patterns else "neutral explanation",
        sentence_shape=_sentence_shape(text),
        repair_patterns=["remove_repetition", "hide_internal_trace", "improve_korean_naturalness"],
        extraction_confidence=0.86 if phrase_patterns or constructions else 0.58,
    )
    return projection.to_dict()
