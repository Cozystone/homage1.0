from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.cgsr.cgsr.asm_v0 import (
    ASM_GENERATION_BASIS,
    generate_surface,
    result_to_public_diagnostics,
)
from packages.cgsr.cgsr.conversation_grounding import (
    GroundedContext,
    HONESTY_NOTE,
    answer_mode_for_route,
    grounded_discourse_metadata,
    honesty_metadata,
    realize_grounded_context,
)
from packages.cgsr.cgsr.conversation_router import ConversationRoute
from packages.construction_bank.retriever import retrieve_constructions


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


def _construction_retrieval_metadata(
    *,
    route: ConversationRoute | None,
    language: str,
    context: dict[str, Any] | None,
    grounding_context: GroundedContext | None,
    fallback_answer: str | None = None,
) -> dict[str, Any]:
    route_type = route.route_type if route else "unknown"
    audience = str((context or {}).get("audience") or (context or {}).get("workspace") or "product")
    disabled = bool((context or {}).get("disable_self_grown_construction"))
    if disabled:
        return {
            "self_grown_construction_retrieved": False,
            "self_grown_construction_used": False,
            "construction_candidate_id": None,
            "construction_status": "disabled",
            "construction_production_active": False,
            "construction_auto_promoted": False,
            "production_construction_activation": False,
            "human_review_required": True,
            "hand_authored_construction_used": True,
            "hand_authored_construction_used_disclosed": True,
            "hand_authored_fallback_used": True,
            "self_grown_candidate_preview_only": False,
            "construction_retrieval": {"retrieval_disabled": True},
        }
    retrieval = retrieve_constructions(
        route_type=route_type,
        language=language,
        act=route_type,
        audience="lab" if audience == "lab" else "product",
        grounding_context=grounding_context.to_dict() if grounding_context else {},
        fallback_answer=fallback_answer,
    )
    return {
        "self_grown_construction_retrieved": retrieval["retrieved_self_grown_construction"],
        "self_grown_construction_used": retrieval["self_grown_construction_used"],
        "construction_candidate_id": retrieval["construction_candidate_id"],
        "construction_status": retrieval["candidate_status"],
        "construction_production_active": False,
        "construction_auto_promoted": False,
        "production_construction_activation": False,
        "self_grown_candidate_preview_only": retrieval["retrieved_self_grown_construction"]
        and not retrieval["self_grown_construction_used"],
        "human_review_required": True,
        "hand_authored_construction_used": retrieval["hand_authored_construction_used"],
        "hand_authored_construction_used_disclosed": True,
        "hand_authored_fallback_used": retrieval["hand_authored_fallback_used"],
        "retrieval_mode": retrieval["retrieval_mode"],
        "activation_reason": retrieval["activation_reason"],
        "rejection_reasons": retrieval["rejection_reasons"],
        "template_risk": retrieval["template_risk"],
        "grounding_score": retrieval["grounding_score"],
        "safety_risk": retrieval["safety_risk"],
        "construction_retrieval": retrieval,
    }


def generate_conversation_surface(
    query: str,
    *,
    language: str = "ko",
    max_tokens: int = 18,
    context: dict[str, Any] | None = None,
    route: ConversationRoute | None = None,
    grounded_context: GroundedContext | None = None,
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
    if route is not None and grounded_context is not None and route.route_type != "greeting_smalltalk":
        grounded_answer = realize_grounded_context(query, grounded_context, language=language)
        grounded = bool(grounded_answer and grounded_context.grounding_quality != "none")
        answer_mode = answer_mode_for_route(route.route_type, grounded=grounded)
        metadata = honesty_metadata(
            route=route,
            grounded_context=grounded_context,
            semantic_grounding_used=grounded,
            answer_mode=answer_mode,
        )
        discourse_metadata = grounded_discourse_metadata(query, grounded_context) if grounded else {}
        diagnostics = {
            "generation_basis": "semantic_grounded_conversation_router_v0",
            "template_free_surface": True,
            "fact_bound_surface": True,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_engine": False,
            "rule_based_answer_used": False,
            "internal_trace_exposed": False,
            "semantic_grounding": grounded_context.to_dict(),
            "route": route.to_dict(),
            **discourse_metadata,
            **metadata,
        }
        if not grounded_answer:
            diagnostics.update(
                _construction_retrieval_metadata(
                    route=route,
                    language=language,
                    context=context,
                    grounding_context=grounded_context,
                )
            )
            return ConversationSurfaceResult(
                answer=None,
                confidence=0.0,
                diagnostics={**diagnostics, "abstain_reason": "no_grounded_answer_available"},
            )
        construction_metadata = _construction_retrieval_metadata(
            route=route,
            language=language,
            context=context,
            grounding_context=grounded_context,
            fallback_answer=grounded_answer,
        )
        diagnostics.update(construction_metadata)
        quality_confidence = {"none": 0.0, "low": 0.48, "medium": 0.64, "high": 0.76}.get(
            grounded_context.grounding_quality,
            0.42,
        )
        selected_answer = (
            diagnostics["construction_retrieval"].get("candidate_answer")
            if diagnostics.get("self_grown_construction_used")
            else grounded_answer
        )
        return ConversationSurfaceResult(answer=selected_answer, confidence=quality_confidence, diagnostics=diagnostics)

    asm_result = generate_surface(query, asm_context)
    fallback_context = grounded_context
    fallback_route = route
    diagnostics = {
        **result_to_public_diagnostics(asm_result),
        "generation_basis": ASM_GENERATION_BASIS,
        "template_free_surface": True,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "rule_based_answer_used": False,
        "direct_prompt_answer_table_used": False,
        "hand_authored_construction_used": True,
        "heuristic_act_inference_used": True,
        "local_transition_surface_used": True,
        "semantic_grounding_used": False,
        "grounding_source": "none",
        "grounding_quality": "none",
        "answer_mode": "greeting_surface" if route and route.route_type == "greeting_smalltalk" else "unknown_fallback",
        "honesty_note": HONESTY_NOTE,
        "consciousness_claim": False,
        "raw_hidden_cot_claim": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "internal_trace_exposed": asm_result.internal_trace_exposed,
    }
    diagnostics.update(
        _construction_retrieval_metadata(
            route=route,
            language=language,
            context=context,
            grounding_context=grounded_context,
            fallback_answer=asm_result.answer,
        )
    )
    if fallback_route is not None:
        diagnostics["route"] = fallback_route.to_dict()
    if fallback_context is not None:
        diagnostics["semantic_grounding"] = fallback_context.to_dict()
    if not asm_result.answer:
        return ConversationSurfaceResult(
            answer=None,
            confidence=0.0,
            diagnostics={**diagnostics, "abstain_reason": "no_safe_construction_surface"},
        )
    top_score = asm_result.candidates[0].score if asm_result.candidates else None
    selected_answer = (
        diagnostics["construction_retrieval"].get("candidate_answer")
        if diagnostics.get("self_grown_construction_used")
        else asm_result.answer
    )
    return ConversationSurfaceResult(
        answer=selected_answer,
        confidence=_confidence_from_score(top_score),
        diagnostics=diagnostics,
    )
