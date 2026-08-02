from __future__ import annotations

from packages.ego_network.cartridge import build_ego_cartridge, compare_cartridge_versions, detect_conflict, validate_cartridge_privacy


def test_private_cartridge_not_relay_allowed() -> None:
    cartridge = build_ego_cartridge(
        cartridge_id="c",
        owner_did="did:atanor:proof:x",
        version=1,
        world_model_hash="w",
        self_model_hash="s",
        privacy_grade="private_local_only",
    )
    privacy = validate_cartridge_privacy(cartridge)
    assert privacy["relay_allowed"] is False
    assert privacy["raw_private_data_exported"] is False


def test_compare_and_conflict_are_proposal_only() -> None:
    local = build_ego_cartridge(cartridge_id="c", owner_did="owner", version=1, world_model_hash="w1", self_model_hash="s")
    remote = build_ego_cartridge(cartridge_id="c", owner_did="owner", version=2, world_model_hash="w2", self_model_hash="s")
    assert compare_cartridge_versions(local, remote)["proposal_only"] is True
    conflict = detect_conflict(local, remote)
    assert conflict["conflict"] is True
    assert conflict["automatic_overwrite"] is False
