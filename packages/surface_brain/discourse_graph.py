from __future__ import annotations


def discourse_candidates(intent: str, audience_level: str = "beginner") -> list[dict]:
    order = ["direct_answer", "explanation", "example", "caveat", "conclusion"]
    if intent == "summarize":
        order = ["direct_answer", "summary", "conclusion"]
    elif intent == "compare":
        order = ["direct_answer", "contrast", "example", "conclusion"]
    elif intent == "plan":
        order = ["direct_answer", "step_by_step", "caveat", "conclusion"]
    return [
        {
            "id": f"move.{move}",
            "move": move,
            "fit_score": max(0.4, 0.9 - index * 0.08),
            "style_score": 0.82 if audience_level in {"beginner", "general"} else 0.7,
            "language_score": 0.8,
            "repetition_penalty": 0.0,
            "prior_success_weight": 0.72,
            "user_preference_weight": 0.7,
        }
        for index, move in enumerate(order)
    ]
