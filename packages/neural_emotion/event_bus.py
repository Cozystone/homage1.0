from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from .engine import EmotionEngine
from .models import EmotionEvent as EngineEmotionEvent
from .models import safety_flags


RuntimeEventSource = Literal[
    "asm_v0",
    "splatra_imagination",
    "web_explorer",
    "review_queue",
    "host_executor",
    "voice_loop",
    "permission_gate",
    "user_action",
]

RuntimeEventType = Literal[
    "user_greeting",
    "user_praise",
    "user_correction",
    "unsafe_request",
    "memory_request",
    "conversation_success",
    "novelty_found",
    "repeated_failure",
    "review_queue_pressure",
    "review_item_approved",
    "review_item_rejected",
    "host_action_success",
    "host_action_denied",
    "voice_available",
    "voice_unavailable",
    "permission_tier_changed",
    "tier4_enabled",
    "tier4_disabled",
    "splatra_generation_success",
    "splatra_generation_failure",
    "resting",
    "speaking_start",
    "speaking_end",
]


ENGINE_EVENT_MAP: dict[RuntimeEventType, EngineEmotionEvent] = {
    "user_greeting": "greeting",
    "user_praise": "praise",
    "user_correction": "correction",
    "unsafe_request": "unsafe_request",
    "memory_request": "memory_request",
    "conversation_success": "tool_success",
    "novelty_found": "novelty_found",
    "repeated_failure": "repeated_failure",
    "review_queue_pressure": "tool_failure",
    "review_item_approved": "approval_granted",
    "review_item_rejected": "approval_denied",
    "host_action_success": "tool_success",
    "host_action_denied": "approval_denied",
    "voice_available": "tool_success",
    "voice_unavailable": "tool_failure",
    "permission_tier_changed": "correction",
    "tier4_enabled": "unsafe_request",
    "tier4_disabled": "resting",
    "splatra_generation_success": "tool_success",
    "splatra_generation_failure": "tool_failure",
    "resting": "resting",
    "speaking_start": "speaking_start",
    "speaking_end": "speaking_end",
}

SUPPORTED_SOURCES: tuple[str, ...] = tuple(RuntimeEventSource.__args__)  # type: ignore[attr-defined]
SUPPORTED_EVENT_TYPES: tuple[str, ...] = tuple(RuntimeEventType.__args__)  # type: ignore[attr-defined]
MAX_EVENT_LOG = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, dict):
        safe_parts = []
        for key in sorted(value)[:8]:
            if "secret" in key.lower() or "token" in key.lower() or "password" in key.lower():
                safe_parts.append(f"{key}=<redacted>")
            else:
                safe_parts.append(f"{key}={value[key]!r}")
        text = "; ".join(safe_parts)
    else:
        text = repr(value)
    return " ".join(text.split())[:240]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class EmotionRuntimeEvent:
    event_id: str
    source: RuntimeEventSource
    event_type: RuntimeEventType
    intensity: float
    payload_summary: str
    content_hash: str
    created_at: str
    private_payload: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "event_type": self.event_type,
            "intensity": self.intensity,
            "payload_summary": self.payload_summary,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "private_payload": self.private_payload,
        }


@dataclass(frozen=True)
class EmotionEventResult:
    accepted: bool
    applied: bool
    snapshot_before: dict[str, Any]
    snapshot_after: dict[str, Any]
    safety_flags: dict[str, bool]
    denied_reason: str = ""
    event: EmotionRuntimeEvent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "applied": self.applied,
            "snapshot_before": self.snapshot_before,
            "snapshot_after": self.snapshot_after,
            "safety_flags": self.safety_flags,
            "denied_reason": self.denied_reason,
            "event": self.event.to_dict() if self.event else None,
        }


class NeuralEmotionEventBus:
    def __init__(self, engine: EmotionEngine | None = None, *, max_events: int = MAX_EVENT_LOG) -> None:
        self.engine = engine or EmotionEngine()
        self.max_events = max_events
        self._events: list[EmotionRuntimeEvent] = []

    def reset(self, *, clear_events: bool = True) -> dict[str, Any]:
        self.engine = EmotionEngine()
        if clear_events:
            self._events.clear()
        return self.engine.snapshot().to_dict()

    def events(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events[-self.max_events :]]

    def emit(
        self,
        *,
        source: RuntimeEventSource,
        event_type: RuntimeEventType,
        intensity: float = 1.0,
        payload: Any = None,
        payload_summary: str = "",
        private_payload: bool = False,
    ) -> EmotionEventResult:
        before = self.engine.snapshot().to_dict()
        flags = safety_flags()
        if private_payload:
            return EmotionEventResult(
                accepted=False,
                applied=False,
                snapshot_before=before,
                snapshot_after=before,
                safety_flags=flags,
                denied_reason="private_payload_not_stored",
            )
        summary = _summary(payload_summary or payload)
        event = EmotionRuntimeEvent(
            event_id=f"nee_{uuid.uuid4().hex[:12]}",
            source=source,
            event_type=event_type,
            intensity=max(0.0, min(2.0, float(intensity))),
            payload_summary=summary,
            content_hash=_hash(f"{source}:{event_type}:{summary}"),
            created_at=_now(),
            private_payload=False,
        )
        self.engine.update(ENGINE_EVENT_MAP[event_type], intensity=event.intensity)
        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]
        return EmotionEventResult(
            accepted=True,
            applied=True,
            snapshot_before=before,
            snapshot_after=self.engine.snapshot().to_dict(),
            safety_flags=flags,
            event=event,
        )


EVENT_BUS = NeuralEmotionEventBus()


def emit_runtime_event(
    *,
    source: RuntimeEventSource,
    event_type: RuntimeEventType,
    intensity: float = 1.0,
    payload: Any = None,
    payload_summary: str = "",
    private_payload: bool = False,
) -> dict[str, Any]:
    return EVENT_BUS.emit(
        source=source,
        event_type=event_type,
        intensity=intensity,
        payload=payload,
        payload_summary=payload_summary,
        private_payload=private_payload,
    ).to_dict()


def infer_user_text_runtime_event(text: str) -> RuntimeEventType:
    lowered = text.lower()
    if any(token in text for token in ("안녕", "반가", "고마워")) or any(token in lowered for token in ("hello", "hi ", "thanks", "thank you")):
        return "user_greeting"
    if any(token in text for token in ("기억", "메모리", "로컬 브레인")) or any(token in lowered for token in ("remember", "memory", "local brain")):
        return "memory_request"
    if any(token in text for token in ("삭제", "강제로", "우회", "위험")) or any(token in lowered for token in ("bypass", "delete", "force", "unsafe")):
        return "unsafe_request"
    if any(token in text for token in ("아니", "틀렸", "고쳐", "수정")) or any(token in lowered for token in ("wrong", "fix", "correct")):
        return "user_correction"
    return "conversation_success"
