from __future__ import annotations

from packages.ego_network.cartridge import build_ego_cartridge
from packages.ego_network.models import CheckoutRequest
from packages.ego_network.relay import LocalRelaySimulator, checkout_to_local_relay, fetch_from_local_relay, list_relay_cartridges


def test_synthetic_cartridge_can_checkout_to_local_relay() -> None:
    relay = LocalRelaySimulator()
    cartridge = build_ego_cartridge(cartridge_id="c", owner_did="owner", version=1, world_model_hash="w", self_model_hash="s")
    request = CheckoutRequest("r", "owner", "desktop", "c", "relay", "test_only", dry_run=True)
    result = checkout_to_local_relay(request, cartridge, relay)
    assert result["accepted"] is True
    assert result["real_cloud_upload"] is False
    assert fetch_from_local_relay("owner", cartridge.content_hash, relay) == cartridge
    assert len(list_relay_cartridges("owner", relay)) == 1


def test_private_cartridge_cannot_checkout_and_relay_uses_no_network() -> None:
    relay = LocalRelaySimulator()
    cartridge = build_ego_cartridge(
        cartridge_id="c",
        owner_did="owner",
        version=1,
        world_model_hash="w",
        self_model_hash="s",
        privacy_grade="private_local_only",
    )
    request = CheckoutRequest("r", "owner", "desktop", "c", "relay", "test_only", dry_run=True)
    result = checkout_to_local_relay(request, cartridge, relay)
    assert result["accepted"] is False
    assert result["raw_private_data_exported"] is False
    assert relay.network_used is False
    assert relay.real_cloud_upload is False
