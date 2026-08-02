from __future__ import annotations

from typing import Any

from .storage import FEEDBACK_ROOT, write_json


def generate_surface_feedback(run_id: str, scored_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for item in scored_candidates:
        score = item.get("score", {})
        prompt = item.get("prompt", {})
        candidate = item.get("candidate", {})
        flags = set(score.get("flags", []))
        if "template_opening_overused" in flags or float(score.get("template_smell", 1.0)) < 0.7:
            feedback.append(
                {
                    "type": "construction_diversity",
                    "prompt_id": prompt.get("prompt_id"),
                    "generator": candidate.get("generator"),
                    "suggestion": "Increase diversity penalty for overused openings and rotate construction families.",
                    "auto_promoted": False,
                }
            )
        if "trace_leakage" in flags:
            feedback.append(
                {
                    "type": "repair_pattern",
                    "prompt_id": prompt.get("prompt_id"),
                    "suggestion": "Apply remove_internal_path_leakage before user-facing answer rendering.",
                    "auto_promoted": False,
                }
            )
        if "korean_not_native_enough" in flags or "awkward_korean_particle_or_spacing" in flags:
            feedback.append(
                {
                    "type": "language_native_style",
                    "prompt_id": prompt.get("prompt_id"),
                    "suggestion": "Prefer shorter Korean-native clauses and avoid English word-order transfer.",
                    "auto_promoted": False,
                }
            )
        if "too_verbose" in flags:
            feedback.append(
                {
                    "type": "concision_target",
                    "prompt_id": prompt.get("prompt_id"),
                    "suggestion": "Lower target sentence count for short-answer prompts.",
                    "auto_promoted": False,
                }
            )
        if "semantic_concepts_missing" in flags:
            feedback.append(
                {
                    "type": "grounding_guard",
                    "prompt_id": prompt.get("prompt_id"),
                    "suggestion": "Require semantic support check before final realization.",
                    "auto_promoted": False,
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for row in feedback:
        key = (str(row.get("type")), row.get("prompt_id"))
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    write_json(FEEDBACK_ROOT / f"surface_feedback_{run_id}.json", {"run_id": run_id, "feedback": deduped, "auto_promoted": False})
    return deduped
