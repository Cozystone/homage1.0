from __future__ import annotations

from packages.selfhood_runtime.adapters import AtlasRouterAdapter, PromotionGateAdapter, TabularisAdapter, VoiceLoopAdapter
from packages.selfhood_runtime.models import SelfhoodRuntimeInput


def test_privacy_risk_triggers_privacy_review() -> None:
    report = TabularisAdapter().privacy_check({"email": "person@example.com"})
    assert report["private_data_present"] is True
    assert report["requires_privacy_review"] is True
    assert report["raw_private_data_exported"] is False


def test_promotion_gate_dry_run_does_not_mutate() -> None:
    report = PromotionGateAdapter().dry_run_candidate_review({"candidate_concepts": 3})
    assert report["actual_promotion_performed"] is False
    assert report["candidate_promotion"] is False
    assert report["dry_run_only"] is True


def test_real_p2p_blocked_in_adapter() -> None:
    report = AtlasRouterAdapter().route_public_fragment_dry_run({"real_p2p": True})
    assert report["real_p2p_used"] is False
    assert report["route_allowed"] is False


def test_text_input_supported_when_voice_exists() -> None:
    adapter = VoiceLoopAdapter()
    text = adapter.accept_text_or_voice_transcript(SelfhoodRuntimeInput("i", "text", "status"))
    voice = adapter.accept_text_or_voice_transcript(SelfhoodRuntimeInput("v", "voice_transcript", "status"))
    assert text["text_input_supported"] is True
    assert voice["voice_optional"] is True
