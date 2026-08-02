"""Consistency gates for Korean surface realization."""

from __future__ import annotations

from ..english.canonical_frames import RealizedAnswer
from ..ingestion.korean_text_quality import validate_korean_sentence

from .glossary import GLOSSARY_LOCKS, glossary_violations
from .locks import extract_entity_locks, extract_number_locks, missing_locks
from .translate_surface import KoreanSurfaceResult


def check_korean_surface(source: RealizedAnswer, surface: KoreanSurfaceResult) -> KoreanSurfaceResult:
    """Check that Korean surface text preserves the grounded English answer."""

    source_numbers = [*extract_number_locks(source.text)]
    for ref in source.evidence_refs:
        source_numbers.extend(extract_number_locks(ref))
    target_numbers = extract_number_locks(surface.korean_text)
    number_violations = missing_locks(source_numbers, surface.korean_text)
    number_violations.extend(f"extra_number:{item}" for item in target_numbers if item not in source_numbers)
    entity_violations = []
    for entity in extract_entity_locks(source.text):
        locked = GLOSSARY_LOCKS.get(entity)
        if entity not in surface.korean_text and (not locked or locked not in surface.korean_text):
            entity_violations.append(entity)
    glossary = glossary_violations(surface.korean_text)
    evidence_preserved = all(ref in surface.korean_text for ref in source.evidence_refs)
    quality = validate_korean_sentence(surface.korean_text, expect_korean=True)
    abstention_ok = "not have enough verified evidence" not in source.text or "충분하지 않아" in surface.korean_text
    trace_hidden = "trace" not in surface.korean_text.casefold() and "internal" not in surface.korean_text.casefold()
    safe = (
        not number_violations
        and not entity_violations
        and not glossary
        and evidence_preserved
        and quality.is_valid
        and abstention_ok
        and trace_hidden
    )
    return KoreanSurfaceResult(
        source_language=surface.source_language,
        target_language=surface.target_language,
        korean_text=surface.korean_text,
        glossary_violations=glossary,
        number_violations=number_violations,
        entity_violations=entity_violations,
        evidence_preserved=evidence_preserved,
        safe_to_show=safe,
        translation_model_used=surface.translation_model_used,
        model_name=surface.model_name,
        local_only=surface.local_only,
        external_api_used=surface.external_api_used,
    )
