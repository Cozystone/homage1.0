from __future__ import annotations

from packages.ego_network.cartridge import build_ego_cartridge
from packages.ego_network.models import EgoDevice
from packages.ego_network.relay import LocalRelaySimulator
from packages.ego_network.seed_identity import create_seed_identity
from packages.ego_network.state_machine import EgoNetworkStateMachine


SEED = "atlas proof morning congress local relay synthetic privacy review device window archive"


def test_wake_up_checkin_is_proposal_only() -> None:
    identity = create_seed_identity(SEED)
    device = EgoDevice("desktop", "Desktop", "main_brain", 1.0, True, None, {})
    machine = EgoNetworkStateMachine(identity, device)
    relay = LocalRelaySimulator()
    cartridge = build_ego_cartridge(cartridge_id="c", owner_did=identity.did, version=1, world_model_hash="w", self_model_hash="s")
    request = machine.predictive_checkout(cartridge)
    checkout = machine.dry_run_checkout(request, cartridge, relay)
    assert checkout["accepted"] is True
    checkin = machine.wake_up_checkin(identity.did, cartridge.content_hash, relay)
    assert checkin.merge_mode == "proposal_only"
    assert checkin.local_brain_mutated is False
    assert checkin.production_mutated is False
