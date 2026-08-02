from __future__ import annotations

from packages.voice_loop.models import VoiceIntent, VoiceResponsePlan


def plan_response(
    intent: VoiceIntent,
    status_summary: str | None = None,
    autonomy_summary: str | None = None,
    language: str = "ko-KR",
) -> VoiceResponsePlan:
    """Create proof-only response text without querying stores or LLMs."""

    base_metadata = {
        "external_llm_used": False,
        "candidate_ingestion": False,
        "production_store_mutated": False,
        "local_brain_write": False,
        "cloud_brain_write": False,
    }
    if intent.intent_type == "ignore_noise":
        text = ""
        return VoiceResponsePlan("plan_ignore", intent.intent_id, text, language, "concise", False, True, metadata=base_metadata)
    if intent.intent_type == "stop_speaking":
        return VoiceResponsePlan("plan_stop", intent.intent_id, "알겠어. 지금 말하기를 멈출게.", language, "concise", True, True, metadata=base_metadata)
    if intent.intent_type == "interruption":
        return VoiceResponsePlan("plan_interrupt", intent.intent_id, "잠깐 멈출게. 이어서 말해줘.", language, "calm", True, True, metadata=base_metadata)
    if intent.intent_type == "autonomy_status_request":
        text = status_summary or "지금은 후보 학습을 보호 모드로 지켜보는 중이고, production 저장소와 Local Brain은 건드리지 않고 있어."
        return VoiceResponsePlan("plan_status", intent.intent_id, text, language, "calm", True, True, metadata=base_metadata)
    if intent.intent_type == "morning_brief_request":
        text = autonomy_summary or "오늘 아침 브리프는 proof-only 요약이야. 실제 반영 전에는 사용자 검토가 필요해."
        return VoiceResponsePlan("plan_morning", intent.intent_id, text, language, "morning_brief", True, True, metadata=base_metadata)
    if intent.intent_type == "command":
        text = "그 요청은 기억하거나 실행하기 전에 사용자 승인 경로가 필요해. 지금은 Local Brain이나 Cloud Brain에 쓰지 않을게."
        return VoiceResponsePlan("plan_command_review", intent.intent_id, text, language, "friendly", True, True, metadata=base_metadata | {"approval_required": True})
    text = "지금 음성 루프는 proof-only라서 안전한 안내만 할 수 있어. 답변이나 실행은 검토 경로를 거쳐야 해."
    return VoiceResponsePlan("plan_safe_answer", intent.intent_id, text, language, "friendly", True, True, metadata=base_metadata)
