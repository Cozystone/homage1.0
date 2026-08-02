from __future__ import annotations

import hashlib
import json
from typing import Any

from packages.atlas_router.models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy
from packages.atlas_router.router import AtlasTrustRouter
from packages.autonomy_kernel.event_stream import utc_now
from packages.autonomy_kernel.models import DeficitSignal, MorningBriefEvent, SelfModelSnapshot, WorldModelSnapshot
from packages.autonomy_kernel.proposal import create_patch_proposal
from packages.ego_network.cartridge import build_ego_cartridge
from packages.ego_network.midnight_congress import MidnightCongressSimulator
from packages.ego_network.models import MidnightCongressTopic
from packages.tabularis_privacy.detectors import detect_field_sensitivities
from packages.tabularis_privacy.generalization import generalize_record
from packages.tabularis_privacy.models import PrivacyPolicy, TabularRecord
from packages.tabularis_privacy.redaction import redact_record
from packages.tabularis_privacy.report import build_privacy_report
from packages.voice_loop.intent import detect_intent
from packages.voice_loop.mock_tts import MockTTSAdapter
from packages.voice_loop.models import TranscriptSegment
from packages.voice_loop.response_planner import plan_response

from packages.selfhood_control.models import SelfhoodContext, SelfhoodInput


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def from_voice_loop(transcript_text: str, language: str = "ko-KR") -> SelfhoodInput:
    """Convert a voice transcript into a control-plane input."""

    segment = TranscriptSegment("selfhood_voice_segment", "voice_loop", transcript_text, language=language)
    intent = detect_intent(segment)
    return SelfhoodInput(
        "input_voice_status",
        "voice_transcript",
        transcript_text,
        language,
        {"voice_intent": intent.to_dict(), "always_listening_enabled": False},
    )


def to_autonomy_context(context: SelfhoodContext) -> tuple[WorldModelSnapshot, SelfModelSnapshot]:
    """Build autonomy-kernel-compatible snapshots from a bounded context."""

    world = context.world_model_summary
    self_model = context.self_model_summary
    return (
        WorldModelSnapshot(
            f"world_{context.context_id}",
            int(world.get("concepts", 0)),
            int(world.get("relations", 0)),
            int(world.get("evidence", 0)),
            list(world.get("unresolved_questions", [])),
            list(world.get("contradictions", [])),
            list(world.get("confidence_gaps", [])),
            context.timestamp,
        ),
        SelfModelSnapshot(
            f"self_{context.context_id}",
            int(self_model.get("local_memory_count", 0)),
            list(context.user_goals),
            list(self_model.get("recent_runs", [])),
            dict(context.resource_state),
            list(self_model.get("known_limits", [])),
            [context.active_project] if context.active_project else [],
            context.timestamp,
        ),
    )


def to_tabularis_review(private_like_record: dict[str, Any]) -> dict[str, Any]:
    """Run Tabularis deterministic privacy review without exporting raw data."""

    policy = PrivacyPolicy()
    record = TabularRecord("selfhood_private_fixture", private_like_record, "selfhood_control", is_private=True)
    sensitivities = detect_field_sensitivities(record)
    redacted = redact_record(record, sensitivities, policy)
    generalized = generalize_record(redacted, sensitivities, policy)
    report = build_privacy_report([generalized], sensitivities, policy)
    return {
        "sensitivities": [item.to_dict() for item in sensitivities],
        "sanitized": generalized.to_dict(),
        "report": report.to_dict(),
        "raw_private_data_exported": False,
    }


def _edge(edge_id: str, source_id: str, target_id: str, privacy_risk: float = 0.0, license_risk: float = 0.0) -> TrustRouteEdge:
    return TrustRouteEdge(
        edge_id,
        source_id,
        target_id,
        latency_ms=10.0,
        bandwidth_cost=0.1,
        trust_penalty=0.02,
        license_risk=license_risk,
        privacy_risk=privacy_risk,
        stale_data_risk=0.05,
        compute_cost=0.1,
        failure_risk=0.02,
    )


def to_atlas_route(source: str = "local", target: str = "public_source") -> dict[str, Any]:
    """Run a local Atlas trust-route proof; no socket or cloud upload is opened."""

    nodes = [
        TrustRouteNode("local", "local_brain", "Local Brain", 1.0, "private"),
        TrustRouteNode("wm", "working_memory", "Working Memory", 1.0, "restricted"),
        TrustRouteNode("public_source", "public_source", "Public Source", 0.95, "public"),
    ]
    edges = [_edge("local-wm", "local", "wm"), _edge("wm-public", "wm", "public_source")]
    result = AtlasTrustRouter.from_iterables(nodes, edges).route(source, target, TrustRoutePolicy(require_public_only=False))
    return result.to_dict() | {"real_p2p_used": False, "real_cloud_upload": False}


def to_ego_congress(deficits: list[DeficitSignal]) -> dict[str, Any]:
    """Run deterministic local Midnight Congress over the first deficit."""

    if not deficits:
        return {"available": True, "summary": "No deficit required deliberation.", "real_p2p_used": False}
    deficit = deficits[0]
    topic = MidnightCongressTopic(
        f"topic_{deficit.signal_id}",
        f"Review {deficit.deficit_type}",
        deficit.deficit_type,
        [deficit.signal_id],
        public_only=True,
        privacy_grade="synthetic",
        status="proposed",
    )
    cartridge = build_ego_cartridge(
        cartridge_id=f"cart_{deficit.signal_id}",
        owner_did="did:atanor:proof:selfhood-control",
        version=1,
        world_model_hash=f"sha256:{_digest({'deficit': deficit.to_dict()})}",
        self_model_hash="sha256:selfhood-control-fixture",
        privacy_grade="synthetic",
        metadata={"deficit_type": deficit.deficit_type},
    )
    run = MidnightCongressSimulator().deliberate(topic, cartridge)
    return run.to_dict()


def to_voice_response(input_event: SelfhoodInput, status_summary: str) -> dict[str, Any]:
    """Create a mock voice response plan/event without persistence."""

    segment = TranscriptSegment("selfhood_voice_response", input_event.input_id, input_event.text or "", input_event.language or "ko-KR")
    intent = detect_intent(segment)
    plan = plan_response(intent, status_summary=status_summary, language=segment.language or "ko-KR")
    output = MockTTSAdapter().synthesize(plan.text, plan.language, plan.speaking_style) if plan.can_speak else None
    return {
        "intent": intent.to_dict(),
        "plan": plan.to_dict(),
        "output": output.to_dict() if output else None,
        "writes_local_brain": False,
        "writes_cloud_brain": False,
        "candidate_ingestion": False,
    }


def to_morning_event(decision_id: str, title: str, summary: str) -> dict[str, Any]:
    """Create an autonomy-kernel-style morning event."""

    event = MorningBriefEvent(
        f"morning_{decision_id}",
        title,
        summary,
        "proposal",
        1,
        {"decision_id": decision_id, "proposal_only": True},
        requires_user_action=True,
    )
    return event.to_dict()


def proposal_from_deficit(deficit: DeficitSignal | None) -> dict[str, Any] | None:
    if deficit is None:
        return None
    return create_patch_proposal(deficit).to_dict()
