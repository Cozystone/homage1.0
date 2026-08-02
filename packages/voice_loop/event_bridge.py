from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from packages.voice_loop.intent import detect_intent
from packages.voice_loop.models import TranscriptSegment, VoiceIntent, VoiceOutputEvent, VoiceResponsePlan
from packages.voice_loop.response_planner import plan_response
from packages.voice_loop.tts_adapter import TTSAdapter


RouteTarget = Literal["working_memory", "autonomy_kernel", "user_review", "blocked"]


@dataclass(frozen=True)
class VoiceEventBridgeResult:
    transcript: TranscriptSegment
    intent: VoiceIntent
    plan: VoiceResponsePlan
    output: VoiceOutputEvent | None
    route_target: RouteTarget
    writes_local_brain: bool
    writes_cloud_brain: bool
    candidate_ingestion: bool
    requires_user_review: bool

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["transcript"] = self.transcript.to_dict()
        data["intent"] = self.intent.to_dict()
        data["plan"] = self.plan.to_dict()
        data["output"] = self.output.to_dict() if self.output else None
        return data


def route_for_intent(intent: VoiceIntent) -> RouteTarget:
    if intent.intent_type in {"ignore_noise", "stop_speaking", "interruption"}:
        return "blocked" if intent.intent_type == "ignore_noise" else "user_review"
    if intent.intent_type in {"autonomy_status_request", "morning_brief_request"}:
        return "autonomy_kernel"
    if intent.intent_type == "command":
        return "user_review"
    return "working_memory"


def process_transcript(
    segment: TranscriptSegment,
    tts: TTSAdapter,
    status_summary: str | None = None,
    autonomy_summary: str | None = None,
) -> VoiceEventBridgeResult:
    """Run Transcript -> Intent -> Plan -> Output without memory mutation."""

    intent = detect_intent(segment)
    plan = plan_response(intent, status_summary=status_summary, autonomy_summary=autonomy_summary, language=segment.language or "ko-KR")
    output = tts.synthesize(plan.text, plan.language, plan.speaking_style) if plan.can_speak else None
    return VoiceEventBridgeResult(
        transcript=segment,
        intent=intent,
        plan=plan,
        output=output,
        route_target=route_for_intent(intent),
        writes_local_brain=False,
        writes_cloud_brain=False,
        candidate_ingestion=False,
        requires_user_review=True,
    )
