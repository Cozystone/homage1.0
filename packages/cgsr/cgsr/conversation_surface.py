from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.cgsr.cgsr.asm_v0 import (
    ASM_GENERATION_BASIS,
    generate_surface,
    result_to_public_diagnostics,
)


@dataclass(frozen=True)
class ConversationSurfaceResult:
    """Public result of local construction-conditioned surface generation."""

    answer: str | None
    confidence: float
    diagnostics: dict[str, Any]


def _confidence_from_score(score: float | None) -> float:
    if score is None:
        return 0.0
    return round(max(0.0, min(0.78, 0.36 + score * 0.16)), 4)


def generate_conversation_surface(
    query: str,
    *,
    language: str = "ko",
    max_tokens: int = 18,
    context: dict[str, Any] | None = None,
) -> ConversationSurfaceResult:
    """Generate a short conversational surface without LLMs or answer templates.

    The compatibility API is intentionally small: callers provide text and get
    one safe public utterance plus bounded diagnostics. Internally ASM-v0
    performs conversation-act inference, construction-frame conditioning, local
    corpus transition generation, and an RHFC-compatible cleanup score. It does
    not read or write Local Brain / Cloud Brain state.
    """

    del max_tokens  # ASM-v0 frame constraints define length; keep API stable.
    asm_context = {"language": language, **(context or {})}
    asm_result = generate_surface(query, asm_context)
    diagnostics = {
        **result_to_public_diagnostics(asm_result),
        "generation_basis": ASM_GENERATION_BASIS,
        "template_free_surface": True,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "rule_based_answer_used": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "internal_trace_exposed": asm_result.internal_trace_exposed,
    }
    if not asm_result.answer:
        return ConversationSurfaceResult(
            answer=None,
            confidence=0.0,
            diagnostics={**diagnostics, "abstain_reason": "no_safe_construction_surface"},
        )
    top_score = asm_result.candidates[0].score if asm_result.candidates else None
    return ConversationSurfaceResult(
        answer=asm_result.answer,
        confidence=_confidence_from_score(top_score),
        diagnostics=diagnostics,
    )
