from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from packages.inner_voice import (
    GLOBAL_INNER_VOICE_LOG,
    InnerVoiceInput,
    build_inner_voice_brief,
    generate_inner_voice_frame,
    inner_voice_safety_flags,
)
from packages.inner_voice.constructions import constructions_payload
from packages.inner_voice.safety import safe_payload
from packages.neural_emotion.autonomy_policy import AutonomyRuntimeState, evaluate_autonomy_policy
from packages.neural_emotion.event_bus import EVENT_BUS


router = APIRouter(prefix="/api/inner-voice", tags=["inner-voice"])


class InnerVoiceEmitRequest(BaseModel):
    mode: str = "lab_visible"
    source_event_id: str = "manual_emit"
    latest_user_input: str = ""
    latest_action_result: dict[str, Any] = Field(default_factory=dict)
    review_queue_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    permission_tier: str = "OBSERVE_ONLY"
    splatra_state: dict[str, Any] = Field(default_factory=dict)


class InnerVoiceBriefRequest(BaseModel):
    workspace: str = "lab"


class InnerVoiceGenerateFrameRequest(InnerVoiceEmitRequest):
    append_to_log: bool = False


def _current_input(request: InnerVoiceEmitRequest | None = None) -> InnerVoiceInput:
    snapshot = EVENT_BUS.engine.snapshot().to_dict()
    assert EVENT_BUS.engine.vector is not None
    runtime = AutonomyRuntimeState(
        review_queue_pressure=float(request.review_queue_pressure if request else 0.0),
        permission_tier=str(request.permission_tier if request else "OBSERVE_ONLY"),
        pending_reviews=0,
        workspace="lab",
    )
    policy = evaluate_autonomy_policy(EVENT_BUS.engine.vector, runtime).to_dict()
    return InnerVoiceInput(
        source_event_id=request.source_event_id if request else "status_snapshot",
        mode=request.mode if request else "lab_visible",
        emotion_snapshot=snapshot,
        policy_decision=policy,
        agent_loop_state={},
        permission_tier=request.permission_tier if request else "OBSERVE_ONLY",
        latest_user_input=request.latest_user_input if request else "",
        latest_action_result=request.latest_action_result if request else {},
        review_queue_pressure=float(request.review_queue_pressure if request else 0.0),
        splatra_state=request.splatra_state if request else {},
    )


@router.get("/status")
def status(workspace: str = Query(default="lab")) -> dict[str, Any]:
    if workspace == "product":
        return safe_payload({"available": True, "product_summary": GLOBAL_INNER_VOICE_LOG.redact_for_product()})
    return safe_payload({"available": True, "log": GLOBAL_INNER_VOICE_LOG.summarize(), "mode": "lab_visible"})


@router.get("/log")
def log(workspace: str = Query(default="lab")) -> dict[str, Any]:
    if workspace == "product":
        return safe_payload({"raw_inner_voice_hidden": True, "product_summary": GLOBAL_INNER_VOICE_LOG.redact_for_product()})
    return safe_payload({"frames": [frame.to_dict() for frame in GLOBAL_INNER_VOICE_LOG.frames], "max_entries": GLOBAL_INNER_VOICE_LOG.max_entries})


@router.post("/emit")
def emit(request: InnerVoiceEmitRequest) -> dict[str, Any]:
    frame = generate_inner_voice_frame(_current_input(request))
    GLOBAL_INNER_VOICE_LOG.append(frame)
    if request.mode == "product_summary":
        return safe_payload({"emitted": True, "raw_inner_voice_hidden": True, "product_summary": GLOBAL_INNER_VOICE_LOG.redact_for_product()})
    return safe_payload({"emitted": True, "frame": frame.to_dict(), "count": len(GLOBAL_INNER_VOICE_LOG.frames)})


@router.post("/generate-frame")
def generate_frame(request: InnerVoiceGenerateFrameRequest) -> dict[str, Any]:
    frame = generate_inner_voice_frame(_current_input(request))
    if request.append_to_log:
        GLOBAL_INNER_VOICE_LOG.append(frame)
    if request.mode == "product_summary":
        product_summary = {
            **GLOBAL_INNER_VOICE_LOG.redact_for_product(),
            "visible_self_narration": frame.monologue_text,
            "act": frame.act,
            "construction_id": frame.construction_id,
            "generation_basis": frame.generation_basis,
        }
        return safe_payload(
            {
                "generated": True,
                "appended": bool(request.append_to_log),
                "raw_inner_voice_hidden": True,
                "product_summary": product_summary,
            }
        )
    return safe_payload(
        {
            "generated": True,
            "appended": bool(request.append_to_log),
            "frame": frame.to_dict(),
            "available_constructions": constructions_payload(),
        }
    )


@router.get("/visible-summary")
def visible_summary(workspace: str = Query(default="product")) -> dict[str, Any]:
    if workspace == "lab":
        return safe_payload({"lab_brief": GLOBAL_INNER_VOICE_LOG.export_lab_brief(limit=5)})
    return safe_payload({"product_summary": GLOBAL_INNER_VOICE_LOG.redact_for_product()})


@router.post("/brief")
def brief(request: InnerVoiceBriefRequest) -> dict[str, Any]:
    return safe_payload(build_inner_voice_brief(GLOBAL_INNER_VOICE_LOG, product=request.workspace == "product"))
