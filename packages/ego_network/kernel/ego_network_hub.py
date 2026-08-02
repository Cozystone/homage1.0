from __future__ import annotations

from packages.ego_network.cartridge import build_ego_cartridge
from packages.ego_network.models import EgoDevice, MidnightCongressTopic
from packages.ego_network.relay import LocalRelaySimulator
from packages.ego_network.seed_identity import create_seed_identity
from packages.ego_network.state_machine import EgoNetworkStateMachine


class EgoNetworkHub:
    """Thin proof-only hub for the ego sync package.

    The hub intentionally has no API, Cloud Brain, Local Brain, daemon, or UI
    dependency. It is a local fixture coordinator only.
    """

    def __init__(self, seed_phrase: str, device: EgoDevice | None = None) -> None:
        self.identity = create_seed_identity(seed_phrase)
        self.device = device or EgoDevice("desktop", "Desktop Main Brain", "main_brain", 1.0, True, None, {"proof": True})
        self.relay = LocalRelaySimulator()
        self.machine = EgoNetworkStateMachine(self.identity, self.device)

    def run_public_checkout_and_congress(self):
        cartridge = build_ego_cartridge(
            cartridge_id="hub_public_fixture",
            owner_did=self.identity.did,
            version=1,
            world_model_hash="sha256:world",
            self_model_hash="sha256:self",
            privacy_grade="synthetic",
            metadata={"hub": "proof"},
        )
        request = self.machine.predictive_checkout(cartridge)
        checkout = self.machine.dry_run_checkout(request, cartridge, self.relay)
        topic = MidnightCongressTopic("hub_topic", "Morning proof topic", "knowledge_gap", ["gap_1"], True, "synthetic", "proposed")
        synthesis = self.machine.run_midnight_congress(topic, cartridge)
        return {"checkout": checkout, "synthesis": synthesis.to_dict()}
