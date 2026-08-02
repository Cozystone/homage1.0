from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .cartridge import build_ego_cartridge
from .event_stream import InMemoryEgoEventStream
from .midnight_congress import MidnightCongressSimulator
from .models import ConstellationState, EgoDevice, MidnightCongressTopic
from .relay import LocalRelaySimulator, checkout_to_local_relay
from .seed_identity import create_seed_identity, verify_seed_phrase
from .state_machine import EgoNetworkStateMachine
from .sync import apply_sync_plan_dry_run, compute_constellation_diff, plan_sync_actions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "ego_network"
FIXTURE_SEED = "atlas proof morning congress local relay synthetic privacy review device window archive"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _device(device_id: str, role: str, latest: str | None = None) -> EgoDevice:
    return EgoDevice(device_id, device_id.replace("_", " ").title(), role, 0.95, True, "2026-06-21T00:00:00Z", {"latest": latest})


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    identity = create_seed_identity(FIXTURE_SEED)
    desktop = _device("desktop_main", "main_brain")
    phone = _device("phone_window", "mobile_window")
    relay = LocalRelaySimulator()
    stream = InMemoryEgoEventStream()
    machine = EgoNetworkStateMachine(identity, desktop, stream)

    public_cartridge = build_ego_cartridge(
        cartridge_id="ego_public",
        owner_did=identity.did,
        version=1,
        world_model_hash="sha256:world-a",
        self_model_hash="sha256:self-a",
        privacy_grade="synthetic",
        metadata={"topic": "public proof"},
    )
    private_cartridge = build_ego_cartridge(
        cartridge_id="ego_private",
        owner_did=identity.did,
        version=1,
        world_model_hash="sha256:world-private",
        self_model_hash="sha256:self-private",
        privacy_grade="private_local_only",
        metadata={"topic": "private proof"},
    )

    private_request = machine.predictive_checkout(private_cartridge)
    private_checkout = checkout_to_local_relay(private_request, private_cartridge, relay)
    public_request = machine.predictive_checkout(public_cartridge)
    public_checkout = checkout_to_local_relay(public_request, public_cartridge, relay)

    public_topic = MidnightCongressTopic("topic_public", "Public ego cartridge review", "knowledge_gap", ["def_1"], True, "synthetic", "proposed")
    private_topic = MidnightCongressTopic("topic_private", "Private checkout request", "privacy_risk", ["def_private"], False, "private_local_only", "proposed")
    congress = MidnightCongressSimulator(stream)
    public_congress = congress.deliberate(public_topic, public_cartridge)
    private_congress = congress.deliberate(private_topic, private_cartridge)

    checkin = machine.wake_up_checkin(identity.did, public_cartridge.content_hash, relay)
    local_state = ConstellationState(identity.did, [desktop, phone], "sha256:local-old", "idle", [], {"version": 1})
    remote_state = ConstellationState(identity.did, [desktop, phone], public_cartridge.content_hash, "checkin_available", [], {"version": 2})
    diff = compute_constellation_diff(local_state, remote_state)
    plan = plan_sync_actions(diff)
    dry_run_sync = apply_sync_plan_dry_run(plan)
    constellation = machine.sync_constellation_state(local_state, remote_state)

    events = [event.to_dict() for event in stream.list_events()]
    results: dict[str, Any] = {
        "seed_identity": {
            "pass": identity.did.startswith("did:atanor:proof:")
            and verify_seed_phrase(FIXTURE_SEED, identity)
            and FIXTURE_SEED not in json.dumps(identity.to_dict()),
            "identity": identity.to_dict(),
            "raw_phrase_stored": False,
        },
        "private_cartridge_blocked": {
            "pass": private_checkout["accepted"] is False
            and private_checkout["raw_private_data_exported"] is False
            and private_checkout["real_cloud_upload"] is False,
            "checkout": private_checkout,
        },
        "synthetic_checkout_dry_run": {
            "pass": public_checkout["accepted"] is True
            and public_checkout["real_cloud_upload"] is False
            and public_checkout["dry_run"] is True,
            "checkout": public_checkout,
        },
        "midnight_congress_synthesis": {
            "pass": public_congress.synthesis.requires_user_approval
            and not public_congress.synthesis.mutates_production
            and not public_congress.synthesis.mutates_local_brain,
            "run": public_congress.to_dict(),
        },
        "midnight_congress_privacy_block": {
            "pass": private_congress.synthesis.proposed_cartridge_id is None
            and "Private-local-only" in private_congress.synthesis.summary,
            "run": private_congress.to_dict(),
        },
        "wake_up_checkin_proposal_only": {
            "pass": checkin.merge_mode == "proposal_only"
            and not checkin.local_brain_mutated
            and not checkin.production_mutated,
            "checkin": checkin.to_dict(),
        },
        "multi_device_constellation": {
            "pass": constellation.sync_status == "conflict"
            and dry_run_sync["automatic_overwrite"] is False
            and dry_run_sync["local_brain_mutated"] is False,
            "diff": diff,
            "plan": plan,
            "dry_run": dry_run_sync,
            "state": constellation.to_dict(),
        },
        "morning_gift_event": {
            "pass": any(event["event_type"] == "ego.morning_gift" and event["requires_user_action"] for event in events),
            "events": events,
        },
        "safety": {
            "production_store_mutated": False,
            "local_brain_write": False,
            "external_llm_used": False,
            "mock_growth": False,
            "pair_edges_sent": 0,
            "active_24h_run_not_modified": True,
            "raw_private_data_exported": False,
            "real_p2p_used": False,
            "real_cloud_upload": False,
            "real_hot_swap_performed": False,
            "generated_code_executed": False,
        },
    }
    results["summary"] = {key: value["pass"] for key, value in results.items() if isinstance(value, dict) and "pass" in value}

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _ts()
    json_path = output_dir / f"ego_network_midnight_congress_proof_{timestamp}.json"
    md_path = output_dir / f"ego_network_midnight_congress_proof_{timestamp}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_proof_markdown(results), encoding="utf-8")
    results["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return results


def _proof_markdown(results: dict[str, Any]) -> str:
    lines = ["# Ego Network Midnight Congress Proof", ""]
    for key, passed in results["summary"].items():
        lines.append(f"- {key}: `{passed}`")
    lines.extend(
        [
            "",
            "This is proof-only. It is not real P2P, not real cloud checkout, not real DID custody,",
            "not Local Brain replication, not production mutation, and not a consciousness or AGI claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
