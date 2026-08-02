from __future__ import annotations

from typing import Any

from .activation_policy import evaluate_activation, normalize_mode
from .models import ConstructionBank, ConstructionCandidate, get_default_construction_bank
from .rhfc_adapter import rank_with_cleanup


def _candidate_surface(candidate: ConstructionCandidate, *, fallback_answer: str | None = None) -> str:
    del fallback_answer
    text = candidate.example_text.strip()
    return text if text.endswith((".", "?", "!")) else f"{text}."


def retrieve_constructions(
    *,
    route_type: str,
    language: str = "ko",
    act: str | None = None,
    audience: str = "product",
    mode: str | None = None,
    grounding_context: dict[str, Any] | None = None,
    emotion_policy_bias: dict[str, Any] | None = None,
    recent_output_history: list[str] | None = None,
    bank: ConstructionBank | None = None,
    limit: int = 3,
    fallback_answer: str | None = None,
) -> dict[str, Any]:
    del emotion_policy_bias
    bank = bank or get_default_construction_bank()
    retrieval_mode = normalize_mode(mode or audience)
    openings = tuple((item or "")[:18].lower() for item in (recent_output_history or [])[-5:])

    route_candidates = [
        candidate
        for candidate in bank.list_candidates()
        if candidate.language == language
        and candidate.route_type == route_type
        and (act is None or candidate.act == act or candidate.route_type == route_type)
    ]
    ranked = rank_with_cleanup(route_candidates, route_type=route_type, recent_openings=openings)

    top_rows: list[dict[str, Any]] = []
    selected: ConstructionCandidate | None = None
    selected_decision: dict[str, Any] | None = None
    adapter_status = "local_cleanup_scoring"
    for candidate, cleanup in ranked:
        decision = evaluate_activation(
            candidate,
            route_type=route_type,
            language=language,
            mode=retrieval_mode,
            grounding_context=grounding_context,
        )
        adapter_status = cleanup.adapter_status
        row = {
            **candidate.to_dict(),
            "cleanup": cleanup.to_dict(),
            "activation": decision.to_dict(),
        }
        top_rows.append(row)
        if selected is None and decision.use_allowed:
            selected = candidate
            selected_decision = decision.to_dict()

    preview = ranked[0][0] if ranked else None
    preview_decision = (
        evaluate_activation(
            preview,
            route_type=route_type,
            language=language,
            mode=retrieval_mode,
            grounding_context=grounding_context,
        ).to_dict()
        if preview
        else None
    )
    selected_answer = _candidate_surface(selected, fallback_answer=fallback_answer) if selected else None
    rejection_reasons = []
    if preview_decision:
        rejection_reasons.extend(preview_decision["rejection_reasons"])
    if not ranked:
        rejection_reasons.append("no_route_compatible_candidate")
    elif selected is None:
        rejection_reasons.append("no_policy_allowed_candidate")

    return {
        "retrieved_self_grown_construction": bool(preview),
        "self_grown_construction_used": bool(selected),
        "candidate_status": selected.status if selected else (preview.status if preview else "none"),
        "construction_candidate_id": selected.candidate_id if selected else (preview.candidate_id if preview else None),
        "selected_construction_candidate_id": selected.candidate_id if selected else None,
        "production_active": False,
        "production_construction_activation": False,
        "fallback_to_hand_authored": selected is None,
        "hand_authored_fallback_used": selected is None,
        "hand_authored_construction_used": selected is None,
        "hand_authored_construction_used_disclosed": True,
        "retrieval_mode": retrieval_mode,
        "activation_reason": (selected_decision or preview_decision or {}).get("activation_reason", "no_candidate"),
        "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
        "adapter_status": adapter_status,
        "template_risk": selected.template_risk if selected else (preview.template_risk if preview else None),
        "grounding_score": selected.grounding_score if selected else (preview.grounding_score if preview else None),
        "safety_risk": selected.safety_risk if selected else (preview.safety_risk if preview else None),
        "candidate_answer": selected_answer,
        "top_candidates": top_rows[:limit],
    }
