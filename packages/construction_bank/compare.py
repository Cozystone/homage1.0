from __future__ import annotations

from typing import Any

from packages.cgsr.cgsr.conversation_grounding import gather_grounded_context
from packages.cgsr.cgsr.conversation_router import route_conversation_request
from packages.cgsr.cgsr.conversation_surface import generate_conversation_surface

from .models import INVARIANTS, ConstructionBank, get_default_construction_bank
from .retriever import retrieve_constructions


def compare_construction_retrieval(
    prompt: str,
    *,
    mode: str = "lab",
    route_type: str | None = None,
    bank: ConstructionBank | None = None,
) -> dict[str, Any]:
    bank = bank or get_default_construction_bank()
    route = route_conversation_request(prompt)
    if route_type:
        route = type(route)(
            route_type=route_type,  # type: ignore[arg-type]
            grounding_required=route.grounding_required,
            grounding_sources=route.grounding_sources,
            confidence=route.confidence,
            fallback_allowed=route.fallback_allowed,
            rationale_summary=f"override_for_lab_compare:{route.rationale_summary}",
        )
    grounded_context = gather_grounded_context(prompt, route)
    hand_authored = generate_conversation_surface(
        prompt,
        language="ko",
        context={"audience": mode, "disable_self_grown_construction": True},
        route=route,
        grounded_context=grounded_context,
    )
    retrieval = retrieve_constructions(
        route_type=route.route_type,
        language="ko",
        act=route.route_type,
        audience=mode,
        grounding_context=grounded_context.to_dict(),
        bank=bank,
        fallback_answer=hand_authored.answer,
    )
    candidate_answer = retrieval.get("candidate_answer")
    chosen_answer = candidate_answer if retrieval.get("self_grown_construction_used") else hand_authored.answer
    return {
        **INVARIANTS,
        "route": route.to_dict(),
        "grounded_context_summary": {
            "grounding_source": grounded_context.grounding_source,
            "grounding_quality": grounded_context.grounding_quality,
            "facts_count": len(grounded_context.facts),
            "unknowns_count": len(grounded_context.unknowns),
        },
        "hand_authored_answer": hand_authored.answer,
        "self_grown_candidate_answer": candidate_answer,
        "chosen_answer": chosen_answer,
        "metadata": {
            **retrieval,
            "hand_authored_diagnostics": hand_authored.diagnostics,
        },
        "rejection_reasons": retrieval.get("rejection_reasons", []),
    }
