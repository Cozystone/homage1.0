"""Deterministic Korean surface fallback for grounded English answers."""

from __future__ import annotations

from dataclasses import dataclass

from ..english.canonical_frames import RealizedAnswer

from .glossary import apply_glossary_locks
from .locks import extract_entity_locks, extract_number_locks


@dataclass(frozen=True)
class KoreanSurfaceResult:
    """Korean surface realization result and metadata."""

    source_language: str
    target_language: str
    korean_text: str
    glossary_violations: list[str]
    number_violations: list[str]
    entity_violations: list[str]
    evidence_preserved: bool
    safe_to_show: bool
    translation_model_used: bool = False
    model_name: str = "deterministic_fallback"
    local_only: bool = True
    external_api_used: bool = False


def deterministic_korean_fallback(answer: RealizedAnswer) -> str:
    """Render a limited Korean summary without translating facts freely."""

    locks = [*extract_entity_locks(answer.text), *extract_number_locks(answer.text)]
    lock_text = f" 핵심 항목: {', '.join(dict.fromkeys(locks))}." if locks else ""
    if "not have enough verified evidence" in answer.text:
        return apply_glossary_locks(f"검증된 근거가 충분하지 않아 확신 있게 답할 수 없습니다.{lock_text}")
    evidence = f" 근거: {', '.join(answer.evidence_refs)}." if answer.evidence_refs else ""
    return apply_glossary_locks(f"검증된 영어 계획을 한국어 표층으로 표시합니다.{lock_text}{evidence}")


def realize_korean_surface(answer: RealizedAnswer) -> KoreanSurfaceResult:
    """Create a locked Korean surface result from a grounded English answer."""

    korean_text = deterministic_korean_fallback(answer)
    return KoreanSurfaceResult(
        source_language=answer.language,
        target_language="ko",
        korean_text=korean_text,
        glossary_violations=[],
        number_violations=[],
        entity_violations=[],
        evidence_preserved=all(ref in korean_text for ref in answer.evidence_refs),
        safe_to_show=True,
    )
