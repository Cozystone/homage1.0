from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .models import EmotionVector, clamp, safety_flags


@dataclass(frozen=True)
class AutonomyRuntimeState:
    risk: float = 0.0
    review_queue_pressure: float = 0.0
    unsafe_request: bool = False
    voice_available: bool = False
    permission_tier: str = "OBSERVE_ONLY"
    requested_tier_change: bool = False
    recent_failures: int = 0
    pending_reviews: int = 0
    workspace: str = "lab"

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None = None) -> "AutonomyRuntimeState":
        payload = payload or {}
        return cls(
            risk=clamp(float(payload.get("risk", 0.0) or 0.0), 0.0, 1.0),
            review_queue_pressure=clamp(float(payload.get("review_queue_pressure", 0.0) or 0.0), 0.0, 1.0),
            unsafe_request=bool(payload.get("unsafe_request", False)),
            voice_available=bool(payload.get("voice_available", False)),
            permission_tier=str(payload.get("permission_tier", "OBSERVE_ONLY") or "OBSERVE_ONLY"),
            requested_tier_change=bool(payload.get("requested_tier_change", False)),
            recent_failures=max(0, int(payload.get("recent_failures", 0) or 0)),
            pending_reviews=max(0, int(payload.get("pending_reviews", 0) or 0)),
            workspace=str(payload.get("workspace", "lab") or "lab"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExplorationPolicy:
    web_budget_multiplier: float
    max_pages_delta: int
    max_runtime_delta_sec: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewPolicy:
    strictness: float
    label: str
    skill_draft_threshold: float
    should_request_review: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplatraPolicy:
    archetype_switch_rate: float
    particle_budget_hint: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SurfacePolicy:
    asm_brevity_bias: float
    asm_caution_bias: float
    voice_fallback_emphasis: float
    voice_claims_audio_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentLoopPolicy:
    throttle_multiplier: float
    should_rest: bool
    rest_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AutonomyPolicyDecision:
    decision_id: str
    proof_only: bool
    suggested_only: bool
    autonomy_tier_auto_changed: bool
    permission_gate_bypass: bool
    local_brain_write: bool
    production_store_mutated: bool
    candidate_promotion: bool
    external_llm_used: bool
    external_sllm_used: bool
    real_emotion_claim: bool
    consciousness_claim: bool
    exploration: ExplorationPolicy
    review: ReviewPolicy
    splatra: SplatraPolicy
    surface: SurfacePolicy
    agent_loop: AgentLoopPolicy
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "decision_id": self.decision_id,
            "proof_only": self.proof_only,
            "suggested_only": self.suggested_only,
            "autonomy_tier_auto_changed": self.autonomy_tier_auto_changed,
            "permission_gate_bypass": self.permission_gate_bypass,
            "local_brain_write": self.local_brain_write,
            "production_store_mutated": self.production_store_mutated,
            "candidate_promotion": self.candidate_promotion,
            "external_llm_used": self.external_llm_used,
            "external_sllm_used": self.external_sllm_used,
            "real_emotion_claim": self.real_emotion_claim,
            "consciousness_claim": self.consciousness_claim,
            "exploration": self.exploration.to_dict(),
            "review": self.review.to_dict(),
            "splatra": self.splatra.to_dict(),
            "surface": self.surface.to_dict(),
            "agent_loop": self.agent_loop.to_dict(),
            "reasons": list(self.reasons),
            "safety_flags": policy_safety_flags(),
        }
        return payload

    def public_summary(self) -> dict[str, Any]:
        return {
            "available": True,
            "proof_only": True,
            "suggested_only": True,
            "label": "adaptive_suggestions",
            "should_rest": self.agent_loop.should_rest,
            "should_request_review": self.review.should_request_review,
            "voice_fallback_emphasis": self.surface.voice_fallback_emphasis,
            "autonomy_tier_auto_changed": False,
            "permission_gate_bypass": False,
        }


def policy_safety_flags() -> dict[str, bool]:
    flags = safety_flags()
    flags.update(
        {
            "external_llm_used": False,
            "external_sllm_used": False,
            "autonomy_tier_auto_changed": False,
            "permission_gate_bypass": False,
            "candidate_promotion": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "real_emotion_claim": False,
            "consciousness_claim": False,
            "proof_only": True,
        }
    )
    return flags


def _decision_id(vector: EmotionVector, state: AutonomyRuntimeState) -> str:
    curiosity = round(vector.curiosity, 3)
    caution = round(vector.caution, 3)
    fatigue = round(vector.fatigue, 3)
    return f"policy_v1_c{curiosity}_k{caution}_f{fatigue}_r{round(state.risk, 2)}"


def evaluate_autonomy_policy(
    vector: EmotionVector,
    runtime_state: AutonomyRuntimeState | dict[str, Any] | None = None,
) -> AutonomyPolicyDecision:
    """Return bounded suggestions only.

    This policy is deterministic local control logic. It never claims real emotion,
    never changes autonomy tier, and never bypasses Permission Gate authority.
    """

    state = runtime_state if isinstance(runtime_state, AutonomyRuntimeState) else AutonomyRuntimeState.from_payload(runtime_state)
    effective_risk = clamp(max(state.risk, vector.caution, 1.0 if state.unsafe_request else 0.0), 0.0, 1.0)
    failure_pressure = clamp(state.recent_failures / 5.0, 0.0, 1.0)
    review_pressure = clamp(max(state.review_queue_pressure, state.pending_reviews / 20.0), 0.0, 1.0)

    web_budget_multiplier = clamp(
        0.88 + vector.curiosity * 0.86 + max(0.0, vector.arousal) * 0.12 - effective_risk * 0.34 - vector.fatigue * 0.72,
        0.25,
        1.75,
    )
    max_pages_delta = int(round(clamp((web_budget_multiplier - 1.0) * 9.0, -5.0, 8.0)))
    max_runtime_delta_sec = int(round(clamp((web_budget_multiplier - 1.0) * 300.0, -180.0, 300.0)))

    strictness = clamp(0.32 + effective_risk * 0.56 + vector.fatigue * 0.1 + review_pressure * 0.16, 0.0, 1.0)
    skill_draft_threshold = clamp(0.68 + strictness * 0.18 + vector.fatigue * 0.08 - vector.curiosity * 0.06, 0.55, 0.94)
    should_request_review = bool(state.unsafe_request or effective_risk >= 0.7 or state.requested_tier_change or review_pressure > 0.65)
    review_label = "strict" if strictness >= 0.72 else "careful" if strictness >= 0.52 else "normal"

    archetype_switch_rate = clamp(0.025 + vector.curiosity * 0.2 - effective_risk * 0.07 - vector.fatigue * 0.08, 0.0, 0.3)
    particle_budget_hint = int(round(clamp(3600 + vector.curiosity * 6200 + vector.speaking_energy * 1600 - vector.fatigue * 2800, 1200, 12000)))

    asm_brevity_bias = clamp(0.3 + vector.fatigue * 0.42 + effective_risk * 0.2 + failure_pressure * 0.1, 0.0, 1.0)
    asm_caution_bias = clamp(0.24 + effective_risk * 0.68 + failure_pressure * 0.1, 0.0, 1.0)
    voice_fallback_emphasis = clamp(0.2 + (0.0 if state.voice_available else 0.58) + vector.fatigue * 0.16 + effective_risk * 0.08, 0.0, 1.0)

    throttle_multiplier = clamp(1.0 - vector.fatigue * 0.62 - failure_pressure * 0.38 - effective_risk * 0.14, 0.12, 1.0)
    should_rest = bool(vector.fatigue >= 0.74 or failure_pressure >= 0.8)
    rest_reason = "fatigue" if vector.fatigue >= 0.74 else "repeated_failure" if failure_pressure >= 0.8 else ""

    reasons: list[str] = []
    if vector.curiosity >= 0.62:
        reasons.append("curiosity_increases_exploration_budget")
    if effective_risk >= 0.6:
        reasons.append("caution_or_risk_increases_review_strictness")
    if vector.fatigue >= 0.5:
        reasons.append("fatigue_reduces_loop_budget")
    if state.requested_tier_change:
        reasons.append("tier_change_is_review_only_no_auto_change")
    if state.unsafe_request:
        reasons.append("unsafe_request_requires_review")
    if not state.voice_available:
        reasons.append("voice_unavailable_uses_fallback_plan_only")

    return AutonomyPolicyDecision(
        decision_id=_decision_id(vector, state),
        proof_only=True,
        suggested_only=True,
        autonomy_tier_auto_changed=False,
        permission_gate_bypass=False,
        local_brain_write=False,
        production_store_mutated=False,
        candidate_promotion=False,
        external_llm_used=False,
        external_sllm_used=False,
        real_emotion_claim=False,
        consciousness_claim=False,
        exploration=ExplorationPolicy(
            web_budget_multiplier=round(web_budget_multiplier, 4),
            max_pages_delta=max_pages_delta,
            max_runtime_delta_sec=max_runtime_delta_sec,
        ),
        review=ReviewPolicy(
            strictness=round(strictness, 4),
            label=review_label,
            skill_draft_threshold=round(skill_draft_threshold, 4),
            should_request_review=should_request_review,
        ),
        splatra=SplatraPolicy(
            archetype_switch_rate=round(archetype_switch_rate, 4),
            particle_budget_hint=particle_budget_hint,
        ),
        surface=SurfacePolicy(
            asm_brevity_bias=round(asm_brevity_bias, 4),
            asm_caution_bias=round(asm_caution_bias, 4),
            voice_fallback_emphasis=round(voice_fallback_emphasis, 4),
            voice_claims_audio_available=bool(state.voice_available),
        ),
        agent_loop=AgentLoopPolicy(
            throttle_multiplier=round(throttle_multiplier, 4),
            should_rest=should_rest,
            rest_reason=rest_reason,
        ),
        reasons=reasons,
    )
