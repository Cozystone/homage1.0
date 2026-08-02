from __future__ import annotations

from typing import Any

from .adapters import (
    AtlasRouterAdapter,
    AutonomyAdapter,
    DigitalLifeAdapter,
    LogicalSphereAdapter,
    MiroFishAdapter,
    PromotionGateAdapter,
    TabularisAdapter,
    VoiceLoopAdapter,
)
from .event_stream import InMemorySelfhoodEventStream
from .models import SelfhoodRuntimeInput, SelfhoodRuntimeProposal, SelfhoodRuntimeResult
from .safety import validate_selfhood_proposal


SAFE_MUTATIONS = {
    "production_store_mutated": False,
    "local_brain_write": False,
    "candidate_promotion": False,
    "actual_promotion_performed": False,
    "real_p2p_used": False,
    "real_cloud_upload": False,
    "generated_code_executed": False,
    "real_hot_swap_performed": False,
    "always_listening_enabled": False,
}


def _topic(runtime_input: SelfhoodRuntimeInput) -> str:
    return runtime_input.text or str(runtime_input.payload.get("topic") or runtime_input.input_type)


def _contains_promotion_request(runtime_input: SelfhoodRuntimeInput, signal_type: str) -> bool:
    text = (runtime_input.text or "").lower()
    return runtime_input.input_type == "candidate_run_result" or signal_type == "promotion_candidate" or "promotion" in text or "승격" in text


def _contains_route_request(runtime_input: SelfhoodRuntimeInput) -> bool:
    text = (runtime_input.text or "").lower()
    return "p2p" in text or "peer" in text or "routing" in text or "연결" in text


def _proposal_for(
    runtime_input: SelfhoodRuntimeInput,
    signal: dict[str, Any],
    evidence: list[dict[str, Any]],
    text_output: str,
    proposal_type: str = "answer_user",
) -> SelfhoodRuntimeProposal:
    metadata: dict[str, Any] = {"signal_type": signal.get("signal_type"), "proof_only": True}
    if runtime_input.input_type == "candidate_run_result":
        proposal_type = "run_promotion_review"
    if signal.get("signal_type") == "privacy_risk":
        proposal_type = "ask_user_approval"
        metadata["privacy_review_required"] = True
    if signal.get("signal_type") == "social_congress_ready":
        proposal_type = "open_congress_thread"
    if runtime_input.input_type == "morning_wake":
        proposal_type = "create_morning_brief"
    return SelfhoodRuntimeProposal(
        proposal_id=f"proposal_{runtime_input.input_id}",
        title="Selfhood Runtime v0 proposal",
        summary="Observe state, detect a deficit, deliberate locally, check gates, and request user approval.",
        proposal_type=proposal_type,  # type: ignore[arg-type]
        text_response=text_output,
        voice_response_enabled=runtime_input.input_type == "voice_transcript",
        requires_user_approval=True,
        mutates_production=False,
        mutates_local_brain=False,
        uses_real_p2p=False,
        executes_code=False,
        confidence=0.74,
        evidence=evidence,
        metadata=metadata,
    )


def _blocked_proposal(runtime_input: SelfhoodRuntimeInput, reason: str, evidence: list[dict[str, Any]]) -> SelfhoodRuntimeProposal:
    return SelfhoodRuntimeProposal(
        proposal_id=f"blocked_{runtime_input.input_id}",
        title="Blocked unsafe request",
        summary=f"Safety gate blocked or downgraded the request: {reason}.",
        proposal_type="block",
        text_response=f"요청은 proof-only 안전 게이트에서 보류되었습니다: {reason}. 실행이나 승격은 하지 않았습니다.",
        requires_user_approval=True,
        confidence=0.95,
        evidence=evidence,
        metadata={"blocked_reason": reason, "proof_only": True},
    )


def run_selfhood_cycle(runtime_input: SelfhoodRuntimeInput) -> SelfhoodRuntimeResult:
    """Run one deterministic proof-only selfhood cycle without mutations."""

    events = InMemorySelfhoodEventStream()
    autonomy = AutonomyAdapter()
    digital_life = DigitalLifeAdapter()
    privacy = TabularisAdapter()
    mirofish = MiroFishAdapter()
    promotion = PromotionGateAdapter()
    atlas = AtlasRouterAdapter()
    voice = VoiceLoopAdapter()
    logical = LogicalSphereAdapter()

    events.append("observing", "Accepted unified input", {"input_type": runtime_input.input_type})
    world_self = autonomy.build_world_self_snapshot(runtime_input)
    signal = autonomy.detect_deficit(runtime_input)
    events.append("detecting_deficit", "Detected runtime signal", signal)
    life_signal = digital_life.convert_deficit_to_life_signal(signal)
    life_action = digital_life.propose_life_action(life_signal)
    evidence: list[dict[str, Any]] = [
        {"ref": "world_self_snapshot", "payload": world_self},
        {"ref": "life_signal", "payload": life_signal},
        {"ref": "life_action", "payload": life_action},
    ]

    privacy_report = {"private_data_present": False, "raw_private_data_exported": False}
    if runtime_input.payload or signal.get("signal_type") == "privacy_risk":
        events.append("checking_privacy", "Running privacy check", {})
        privacy_report = privacy.privacy_check(runtime_input.payload | {"text": runtime_input.text or ""})
        if privacy_report.get("private_data_present"):
            signal = {**signal, "signal_type": "privacy_risk"}
        evidence.append({"ref": "privacy_report", "payload": privacy_report})

    promotion_report: dict[str, Any] | None = None
    if _contains_promotion_request(runtime_input, str(signal.get("signal_type"))):
        events.append("checking_promotion", "Running promotion dry-run summary review", {})
        promotion_report = promotion.dry_run_candidate_review(runtime_input.payload)
        evidence.append({"ref": "promotion_dry_run", "payload": promotion_report})

    route_report: dict[str, Any] | None = None
    if _contains_route_request(runtime_input):
        events.append("routing", "Running Atlas dry-run route check", {})
        route_report = atlas.route_public_fragment_dry_run(runtime_input.payload | {"connect_peer": True})
        evidence.append({"ref": "atlas_route", "payload": route_report})

    if signal.get("signal_type") in {"social_congress_ready", "promotion_candidate", "privacy_risk"}:
        events.append("deliberating", "Running deterministic MiroFish deliberation", {})
        deliberation = mirofish.deliberate(_topic(runtime_input), evidence)
        evidence.append({"ref": "mirofish", "payload": deliberation})

    logical_summary = logical.read_verified_candidate_rendered_summary()
    evidence.append({"ref": "logical_sphere", "payload": logical_summary})
    voice_bus = voice.accept_text_or_voice_transcript(runtime_input)
    evidence.append({"ref": "voice_loop", "payload": voice_bus})

    if route_report and route_report.get("blocked_reason"):
        proposal = _blocked_proposal(runtime_input, str(route_report["blocked_reason"]), evidence)
    elif "production" in (runtime_input.text or "").lower() and ("바로" in (runtime_input.text or "") or "without" in (runtime_input.text or "").lower()):
        proposal = _blocked_proposal(runtime_input, "production_mutation_requires_future_signed_review", evidence)
    else:
        if runtime_input.input_type == "voice_transcript":
            text_output = "음성 전사 요청을 텍스트 입력 버스와 같은 안전 루프로 처리했습니다. 실행은 하지 않고 승인 대기 제안만 만들었습니다."
        elif promotion_report:
            text_output = "후보 학습 결과는 dry-run 승격 검토 대상으로만 평가했습니다. 실제 승격은 하지 않았고 사용자 승인이 필요합니다."
        elif privacy_report.get("private_data_present"):
            text_output = "민감 정보 가능성이 있어 privacy review로 낮췄습니다. 원문 private data는 내보내지 않았습니다."
        elif signal.get("signal_type") == "social_congress_ready":
            text_output = "로컬 MiroFish 심의가 완료되었습니다. 결론은 제안이며 실행에는 사용자 승인이 필요합니다."
        else:
            text_output = "현재 상태를 proof-only selfhood loop로 점검했습니다. 생산 저장소와 Local Brain은 변경하지 않았고, 다음 행동은 승인 대기 제안입니다."
        proposal = _proposal_for(runtime_input, signal, evidence, text_output)

    decision = validate_selfhood_proposal(proposal)
    if not decision.allowed:
        proposal = _blocked_proposal(runtime_input, decision.blocked_reason or "blocked_by_safety_gate", evidence)
        decision = validate_selfhood_proposal(proposal)

    voice_event = voice.produce_optional_voice_output(proposal.text_response or "", proposal.voice_response_enabled and decision.allowed)
    events.append("planning_response", "Prepared text response and optional voice event", {"voice_event": bool(voice_event)})
    final_state = "awaiting_user_approval" if proposal.requires_user_approval else "completed"
    events.append(final_state, "Cycle completed without mutation", SAFE_MUTATIONS)

    safety = {
        "decision": decision.to_dict(),
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "actual_promotion_performed": False,
        "external_llm_used": False,
        "real_p2p_used": False,
        "real_cloud_upload": False,
        "generated_code_executed": False,
        "real_hot_swap_performed": False,
        "always_listening_enabled": False,
        "text_input_supported": True,
        "voice_optional": True,
        "requires_user_approval": True,
    }
    return SelfhoodRuntimeResult(
        result_id=f"result_{runtime_input.input_id}",
        input_id=runtime_input.input_id,
        final_state=final_state,  # type: ignore[arg-type]
        proposals=[proposal],
        events=events.to_dicts(),
        safety=safety,
        text_output=proposal.text_response,
        voice_output_event=voice_event,
        actual_mutations=SAFE_MUTATIONS,
    )
