from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .asm_inner_voice import generate_construction_conditioned_surface
from .models import InnerVoiceFrame, inner_voice_safety_flags, utc_now


@dataclass(frozen=True)
class InnerVoiceInput:
    source_event_id: str = ""
    mode: str = "lab_visible"
    emotion_snapshot: dict[str, Any] = field(default_factory=dict)
    policy_decision: dict[str, Any] = field(default_factory=dict)
    agent_loop_state: dict[str, Any] = field(default_factory=dict)
    permission_tier: str = "OBSERVE_ONLY"
    latest_user_input: str = ""
    latest_action_result: dict[str, Any] = field(default_factory=dict)
    review_queue_pressure: float = 0.0
    splatra_state: dict[str, Any] = field(default_factory=dict)
    #: English-only has been binding since 2026-07-18. This defaulted to "ko", so every caller that
    #: did not think about language got the retired lane.
    language: str = "en"


def _frame_id(seed: str) -> str:
    return "iv_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _emotion_label(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("label") or "steady")


def generate_inner_voice_frame(input_data: InnerVoiceInput | dict[str, Any]) -> InnerVoiceFrame:
    data = input_data if isinstance(input_data, InnerVoiceInput) else InnerVoiceInput(**dict(input_data))
    surface = generate_construction_conditioned_surface(data)
    timestamp = utc_now()
    seed = (
        f"{data.source_event_id}|{data.latest_user_input}|{timestamp}|"
        f"{surface.monologue_text}|{surface.construction.construction_id}"
    )
    return InnerVoiceFrame(
        frame_id=_frame_id(seed),
        source_event_id=data.source_event_id or "inner_voice_manual_emit",
        timestamp=timestamp,
        mode=data.mode if data.mode in {"private_debug", "lab_visible", "product_summary"} else "lab_visible",
        goal=surface.goal,
        felt_state_label=_emotion_label(dict(data.emotion_snapshot or {})),
        tension=surface.tension,
        candidate_actions=surface.candidate_actions,
        chosen_action=surface.chosen_action,
        blocked_actions=surface.blocked_actions,
        uncertainty=surface.uncertainty,
        next_intent=surface.next_intent,
        monologue_text=surface.monologue_text,
        safety_flags=inner_voice_safety_flags(),
        act=surface.construction.act,
        construction_id=surface.construction.construction_id,
        construction_stance=surface.construction.stance,
        surface_score=surface.surface_score,
        generation_basis="asm_cgsr_construction_conditioned_inner_voice_v1",
        act_scores=surface.act_scores,
    )
