from __future__ import annotations

from packages.ego_network.cartridge import build_ego_cartridge
from packages.ego_network.midnight_congress import DETERMINISTIC_ROLES, MidnightCongressSimulator
from packages.ego_network.models import MidnightCongressTopic


def test_midnight_congress_uses_deterministic_local_roles() -> None:
    topic = MidnightCongressTopic("t", "Public", "knowledge_gap", ["d1"], True, "synthetic", "proposed")
    run = MidnightCongressSimulator().deliberate(topic)
    assert [arg.speaker_role for arg in run.arguments] == DETERMINISTIC_ROLES
    assert run.external_llm_used is False
    assert run.real_p2p_used is False
    assert run.synthesis.requires_user_approval is True
    assert run.synthesis.mutates_production is False
    assert run.synthesis.mutates_local_brain is False


def test_private_cartridge_blocked_in_congress() -> None:
    cartridge = build_ego_cartridge(
        cartridge_id="p",
        owner_did="owner",
        version=1,
        world_model_hash="w",
        self_model_hash="s",
        privacy_grade="private_local_only",
    )
    topic = MidnightCongressTopic("private", "Private", "privacy_risk", ["d"], False, "private_local_only", "proposed")
    run = MidnightCongressSimulator().deliberate(topic, cartridge)
    assert run.synthesis.proposed_cartridge_id is None
    assert run.raw_private_data_exported is False
    assert any("private_local_only_export_blocked" in arg.objections for arg in run.arguments)
