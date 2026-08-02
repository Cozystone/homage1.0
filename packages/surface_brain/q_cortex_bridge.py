from __future__ import annotations

from typing import Any


def _score(item: dict[str, Any]) -> float:
    return (
        float(item.get("fit_score") or 0.0) * 1.15
        + float(item.get("style_score") or 0.0) * 0.8
        + float(item.get("language_score") or 0.0) * 0.9
        + float(item.get("prior_success_weight") or 0.0) * 0.35
        + float(item.get("user_preference_weight") or 0.0) * 0.45
        - float(item.get("repetition_penalty") or 0.0) * 1.1
    )


def select_surface_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_selected: int = 5,
    seed: int = 42,
    q_cortex_enabled: bool = True,
) -> dict[str, Any]:
    if not candidates:
        return {
            "selected": [],
            "rejected": [],
            "q_cortex_used": False,
            "q_cortex_run_id": None,
            "fallback": "empty_candidates",
            "honesty": {
                "real_quantum_hardware_used": False,
                "quantum_inspired_only": True,
                "local_brain_write": False,
            },
        }
    if q_cortex_enabled:
        try:
            from packages.q_cortex.salience_optimizer import optimize_salience_workspace

            q_candidates = [
                {
                    **candidate,
                    "kind": "node",
                    "id": candidate.get("construction_id") or candidate.get("id"),
                    "layer": "surface_brain",
                    "query_relevance": candidate.get("fit_score", 0.5),
                    "activation": candidate.get("style_score", 0.5),
                    "trust": candidate.get("language_score", 0.5),
                    "novelty": candidate.get("prior_success_weight", 0.5),
                    "user_goal_fit": candidate.get("user_preference_weight", 0.5),
                    "risk": candidate.get("repetition_penalty", 0.0),
                    "fatigue": candidate.get("repetition_penalty", 0.0),
                    "source_id": candidate.get("semantic_function") or candidate.get("move") or candidate.get("concept") or "surface",
                    "concept_id": candidate.get("pattern_family") or candidate.get("label") or candidate.get("id"),
                    "temporary": True,
                }
                for candidate in candidates
            ]
            result = optimize_salience_workspace(q_candidates, max_nodes=max_selected, max_edges=0, seed=seed)
            selected_ids = {str(item.get("id")) for item in result.get("selected_items", [])}
            selected = [candidate for candidate in candidates if str(candidate.get("construction_id") or candidate.get("id")) in selected_ids]
            if selected:
                return {
                    "selected": selected[:max_selected],
                    "rejected": [candidate for candidate in candidates if candidate not in selected],
                    "q_cortex_used": True,
                    "q_cortex_run_id": result.get("run_id"),
                    "q_cortex": result,
                    "honesty": result.get("honesty", {}),
                }
        except Exception as exc:
            fallback_error = str(exc)
        else:
            fallback_error = "q_cortex_returned_no_selection"
    else:
        fallback_error = "q_cortex_disabled"
    ranked = sorted(candidates, key=_score, reverse=True)
    return {
        "selected": ranked[:max_selected],
        "rejected": ranked[max_selected:],
        "q_cortex_used": False,
        "q_cortex_run_id": None,
        "fallback": fallback_error,
        "honesty": {
            "real_quantum_hardware_used": False,
            "quantum_inspired_only": True,
            "local_brain_write": False,
        },
    }
