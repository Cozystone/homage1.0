from __future__ import annotations

from typing import Any

from .storage import bounded_float


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    text = str(candidate.get("idea") or candidate.get("candidate") or "")
    novelty = 0.72 if candidate.get("mode") in {"far_walk", "analogy_walk", "counterfactual_walk"} else 0.42
    usefulness = 0.56 + min(0.22, len(text) / 600)
    feasibility = 0.76 if candidate.get("mode") in {"near_walk", "constraint_walk"} else 0.48
    philosophy_fit = 0.82 if "graph" in text.casefold() or "trace" in text.casefold() else 0.55
    cost = 0.2 if "local" in text.casefold() or "bounded" in text.casefold() else 0.46
    security_risk = 0.12 if "private" not in text.casefold() else 0.44
    implementation_difficulty = 0.36 if candidate.get("mode") in {"near_walk", "constraint_walk"} else 0.62
    total = bounded_float(
        novelty * 0.18
        + usefulness * 0.22
        + feasibility * 0.2
        + philosophy_fit * 0.18
        - cost * 0.1
        - security_risk * 0.07
        - implementation_difficulty * 0.05
    )
    return {
        "candidate_id": candidate.get("candidate_id"),
        "novelty": round(novelty, 4),
        "usefulness": round(usefulness, 4),
        "feasibility": round(feasibility, 4),
        "atanor_philosophy_fit": round(philosophy_fit, 4),
        "cost": round(cost, 4),
        "security_risk": round(security_risk, 4),
        "implementation_difficulty": round(implementation_difficulty, 4),
        "score": round(total, 4),
    }
