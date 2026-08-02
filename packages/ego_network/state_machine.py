from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any

from .cartridge import build_ego_cartridge, detect_conflict
from .event_stream import EgoEvent, InMemoryEgoEventStream, utc_now
from .midnight_congress import MidnightCongressSimulator
from .models import (
    CheckinResult,
    CheckoutRequest,
    ConstellationState,
    EgoCartridge,
    EgoDevice,
    MidnightCongressTopic,
    SeedIdentity,
)
from .relay import LocalRelaySimulator, checkout_to_local_relay, fetch_from_local_relay
from .sync import apply_sync_plan_dry_run, compute_constellation_diff, plan_sync_actions


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:16]}"


@dataclass
class EgoNetworkStateMachine:
    identity: SeedIdentity | None
    local_device: EgoDevice
    stream: InMemoryEgoEventStream = field(default_factory=InMemoryEgoEventStream)
    state: str = "idle"
    block_reason: str | None = None

    def predictive_checkout(self, cartridge: EgoCartridge | None = None) -> CheckoutRequest:
        if self.identity is None:
            self.state = "blocked_no_identity"
            self.block_reason = "missing_seed_identity"
            self.stream.append_event(
                EgoEvent(
                    _stable_id("event", self.local_device.device_id, "blocked_identity"),
                    "ego.checkout_blocked",
                    utc_now(),
                    "Checkout blocked because no proof identity exists.",
                    {"reason": self.block_reason},
                    requires_user_action=True,
                )
            )
            raise ValueError("identity required for checkout")
        self.state = "checkout_ready"
        cartridge_id = cartridge.cartridge_id if cartridge else "pending_cartridge"
        request = CheckoutRequest(
            _stable_id("checkout", self.identity.did, self.local_device.device_id, cartridge_id),
            self.identity.did,
            self.local_device.device_id,
            cartridge_id,
            "local_fake_relay",
            "predicted_shutdown",
            dry_run=True,
        )
        self.stream.append_event(
            EgoEvent(
                request.request_id,
                "ego.checkout_predicted",
                utc_now(),
                "Predictive proof checkout window prepared.",
                request.to_dict(),
            )
        )
        return request

    def dry_run_checkout(self, request: CheckoutRequest, cartridge: EgoCartridge, relay: LocalRelaySimulator) -> dict[str, Any]:
        result = checkout_to_local_relay(request, cartridge, relay)
        self.state = "checked_out" if result["accepted"] else "blocked_privacy"
        self.stream.append_event(
            EgoEvent(
                _stable_id("event", request.request_id, "dry_run"),
                "ego.checked_out_dry_run" if result["accepted"] else "ego.checkout_blocked",
                utc_now(),
                "Dry-run checkout completed." if result["accepted"] else "Dry-run checkout blocked.",
                result,
                requires_user_action=not result["accepted"],
            )
        )
        return result

    def run_midnight_congress(self, topic: MidnightCongressTopic, cartridge: EgoCartridge | None = None):
        self.state = "midnight_congress"
        run = MidnightCongressSimulator(self.stream).deliberate(topic, cartridge)
        self.state = "sleep_mode"
        return run.synthesis

    def wake_up_checkin(
        self,
        owner_did: str,
        remote_content_hash: str,
        relay: LocalRelaySimulator,
        local_cartridge: EgoCartridge | None = None,
    ) -> CheckinResult:
        remote = fetch_from_local_relay(owner_did, remote_content_hash, relay)
        if remote is None:
            return CheckinResult(
                _stable_id("checkin", owner_did, remote_content_hash, "missing"),
                owner_did,
                self.local_device.device_id,
                remote_content_hash,
                False,
                "rejected",
                notes=["remote cartridge not found in local relay simulator"],
            )
        conflict = detect_conflict(local_cartridge, remote) if local_cartridge else {"conflict": False}
        result = CheckinResult(
            _stable_id("checkin", owner_did, remote.content_hash, "proposal"),
            owner_did,
            self.local_device.device_id,
            remote.cartridge_id,
            merged=False,
            merge_mode="proposal_only" if not conflict["conflict"] else "rejected",
            notes=["proposal_only_checkin", "user_approval_required"] + (["conflict_detected"] if conflict["conflict"] else []),
        )
        self.state = "merge_proposal"
        self.stream.append_event(
            EgoEvent(
                result.result_id,
                "ego.checkin_available",
                utc_now(),
                "Wake-up checkin is available as a proposal only.",
                result.to_dict(),
                requires_user_action=True,
            )
        )
        return result

    def sync_constellation_state(
        self,
        local_state: ConstellationState,
        remote_state: ConstellationState,
    ) -> ConstellationState:
        diff = compute_constellation_diff(local_state, remote_state)
        plan = plan_sync_actions(diff)
        dry_run = apply_sync_plan_dry_run(plan)
        conflicts = diff["conflicts"]
        status = "conflict" if conflicts else plan["status"]
        if conflicts:
            self.stream.append_event(
                EgoEvent(
                    _stable_id("event", local_state.owner_did, "conflict"),
                    "ego.sync_conflict",
                    utc_now(),
                    "Constellation sync conflict requires user approval.",
                    {"diff": diff, "plan": plan, "dry_run": dry_run},
                    requires_user_action=True,
                )
            )
        return ConstellationState(local_state.owner_did, local_state.devices, local_state.latest_cartridge_hash, status, conflicts, {"plan": plan, "dry_run": dry_run})


def predictive_checkout(identity: SeedIdentity, device: EgoDevice, cartridge: EgoCartridge) -> CheckoutRequest:
    return EgoNetworkStateMachine(identity, device).predictive_checkout(cartridge)


def wake_up_checkin(
    identity: SeedIdentity,
    device: EgoDevice,
    relay: LocalRelaySimulator,
    remote_content_hash: str,
) -> CheckinResult:
    return EgoNetworkStateMachine(identity, device).wake_up_checkin(identity.did, remote_content_hash, relay)


def sync_constellation_state(local_state: ConstellationState, remote_state: ConstellationState) -> ConstellationState:
    device = local_state.devices[0] if local_state.devices else EgoDevice("test", "Test", "test_peer", 1.0, True, None, {})
    return EgoNetworkStateMachine(None, device).sync_constellation_state(local_state, remote_state)


def run_midnight_congress(topic: MidnightCongressTopic):
    device = EgoDevice("test", "Test", "test_peer", 1.0, True, None, {})
    return EgoNetworkStateMachine(None, device).run_midnight_congress(topic)


def fixture_cartridge(owner_did: str, privacy_grade: str = "synthetic", version: int = 1) -> EgoCartridge:
    return build_ego_cartridge(
        cartridge_id="ego_fixture",
        owner_did=owner_did,
        version=version,
        world_model_hash="sha256:world",
        self_model_hash="sha256:self",
        privacy_grade=privacy_grade,
        metadata={"fixture": True},
    )
