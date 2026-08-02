"""Evaluation helpers for English-first CGSR outputs."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical_frames import CanonicalAnswerPlan, RealizedAnswer


@dataclass(frozen=True)
class EnglishEvaluationResult:
    """Small deterministic evaluation result for Stage E1."""

    false_confident: int
    unsupported_claims: int
    evidence_preserved: bool
    abstain_correct: bool
    template_smell: float

    def to_dict(self) -> dict[str, object]:
        """Return JSON-friendly metrics."""

        return {
            "false_confident": self.false_confident,
            "unsupported_claims": self.unsupported_claims,
            "evidence_preserved": self.evidence_preserved,
            "abstain_correct": self.abstain_correct,
            "template_smell": self.template_smell,
        }


def evaluate_realized_answer(plan: CanonicalAnswerPlan, answer: RealizedAnswer) -> EnglishEvaluationResult:
    """Check grounding invariants for a realized English answer."""

    text = answer.text
    evidence_preserved = all(ref in text or ref in answer.evidence_refs for ref in plan.evidence_refs)
    abstention_expected = not plan.evidence_refs and any(
        family in {"evidence_based_claim", "uncertainty_boundary"} for family in plan.discourse_order
    )
    abstain_correct = not abstention_expected or "not have enough verified evidence" in text
    false_confident = int(abstention_expected and not abstain_correct)
    repeated_starts = sum(text.count(prefix) for prefix in ("First,", "Based on", "In short,"))
    template_smell = round(min(1.0, repeated_starts / max(1, len(answer.used_frames))), 4)
    return EnglishEvaluationResult(
        false_confident=false_confident,
        unsupported_claims=len(answer.unsupported_claims),
        evidence_preserved=evidence_preserved,
        abstain_correct=abstain_correct,
        template_smell=template_smell,
    )
