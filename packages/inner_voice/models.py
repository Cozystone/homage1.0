from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


InnerVoiceMode = Literal["private_debug", "lab_visible", "product_summary"]


def inner_voice_safety_flags() -> dict[str, bool]:
    return {
        "external_llm": False,
        "external_sllm": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_used": False,
        "consciousness_claim": False,
        "real_emotion_claim": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "auto_commit": False,
        "auto_push": False,
        "inner_voice_is_explicit_generated_channel": True,
        "raw_hidden_cot_claim": False,
        "product_safe": True,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class InnerVoiceFrame:
    frame_id: str
    source_event_id: str
    timestamp: str
    mode: InnerVoiceMode
    goal: str
    felt_state_label: str
    tension: str
    candidate_actions: list[str]
    chosen_action: str
    blocked_actions: list[str]
    uncertainty: str
    next_intent: str
    monologue_text: str
    safety_flags: dict[str, bool] = field(default_factory=inner_voice_safety_flags)
    act: str = "goal_selection"
    construction_id: str = "iv.goal.select.v1"
    construction_stance: str = "steady_orientation"
    surface_score: float = 1.0
    generation_basis: str = "asm_cgsr_construction_conditioned_inner_voice_v1"
    act_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InnerVoiceLog:
    max_entries: int = 200
    frames: list[InnerVoiceFrame] = field(default_factory=list)

    def append(self, frame: InnerVoiceFrame) -> InnerVoiceFrame:
        self.frames.append(frame)
        if len(self.frames) > self.max_entries:
            self.frames = self.frames[-self.max_entries :]
        return frame

    def summarize(self, limit: int = 5) -> dict[str, Any]:
        recent = self.frames[-max(1, limit) :]
        return {
            "available": True,
            "count": len(self.frames),
            "latest": recent[-1].to_dict() if recent else None,
            "recent_goals": [frame.goal for frame in recent],
            "recent_next_intents": [frame.next_intent for frame in recent],
            "safety_flags": inner_voice_safety_flags(),
        }

    def redact_for_product(self) -> dict[str, Any]:
        latest = self.frames[-1] if self.frames else None
        return {
            "available": True,
            "raw_inner_voice_hidden": True,
            "inner_voice_is_explicit_generated_channel": True,
            "visible_self_narration": latest.monologue_text if latest else "지금은 조용히 대기하고 있습니다.",
            "summary": (
                f"{latest.felt_state_label}: {latest.next_intent}"
                if latest
                else "아직 표시할 자기-서술 프레임이 없습니다."
            ),
            "act": latest.act if latest else "waiting",
            "construction_id": latest.construction_id if latest else "",
            "generation_basis": latest.generation_basis if latest else "asm_cgsr_construction_conditioned_inner_voice_v1",
            "safety_flags": inner_voice_safety_flags(),
        }

    def export_lab_brief(self, limit: int = 8) -> dict[str, Any]:
        recent = self.frames[-max(1, limit) :]
        return {
            "available": True,
            "mode": "lab_visible",
            "count": len(self.frames),
            "frames": [frame.to_dict() for frame in recent],
            "brief": "\n".join(f"- {frame.monologue_text}" for frame in recent),
            "safety_flags": inner_voice_safety_flags(),
        }
