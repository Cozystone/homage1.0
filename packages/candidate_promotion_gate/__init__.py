from .gate import (
    REQUIRED_CONFIRMATION_PHRASE,
    CandidateIntentPlan,
    CandidatePromotionGate,
    PromotionEntry,
    PromotionThresholds,
    evaluate_candidate_item,
)

__all__ = [
    "REQUIRED_CONFIRMATION_PHRASE",
    "CandidateIntentPlan",
    "CandidatePromotionGate",
    "PromotionEntry",
    "PromotionThresholds",
    "evaluate_candidate_item",
]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Default-deny on every shipped-graph mutation. A gate the orchestrator could talk round is
# not a gate.
ATANOR_TIER = "reflex"
