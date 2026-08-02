from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .cartridge_protocol import KnowledgeCartridge, compatibility_score
from .congress import SandboxCongress
from .deficit import compute_deficit
from .event_stream import AutonomyEvent, InMemoryEventStream, utc_now
from .kernel.consciousness_loop import AutonomyKernel
from .models import AutonomyProposal, SelfModelSnapshot, WorldModelSnapshot
from .proposal import create_patch_proposal, validate_patch_proposal_safety
from .state_machine import AutonomyStateMachine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "autonomy_kernel"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def fixture_world() -> WorldModelSnapshot:
    return WorldModelSnapshot(
        "world_fixture",
        120,
        340,
        80,
        ["Which cartridge can answer public graph provenance?"],
        [{"claim_a": "x", "claim_b": "not x", "severity": 0.8}],
        [{"topic": "atlas", "confidence": 0.42}],
        utc_now(),
    )


def fixture_self_model() -> SelfModelSnapshot:
    return SelfModelSnapshot(
        "self_fixture",
        0,
        ["improve autonomy kernel"],
        [{"goal": "stabilize candidate run", "status": "running"}],
        {"disk_free_gib": 120.0, "ram_free_gib": 8.0},
        ["promotion gate not ready"],
        ["autonomy proof"],
        utc_now(),
    )


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    world = fixture_world()
    self_model = fixture_self_model()
    deficits = compute_deficit(world, self_model)
    resource_deficits = compute_deficit(
        world,
        SelfModelSnapshot("resource_self", 0, [], [], {"disk_free_gib": 10.0, "ram_free_gib": 1.5}, [], [], utc_now()),
    )
    congress = SandboxCongress()
    proposals = congress.deliberate(deficits)
    patch = create_patch_proposal(deficits[0])
    stream = InMemoryEventStream()
    stream.append_event(
        AutonomyEvent(
            "brief_event",
            utc_now(),
            "proof",
            "autonomy.morning_brief",
            1,
            "Morning brief",
            "Proof morning brief generated.",
            {"proposal_count": len(proposals)},
            bool(proposals),
        )
    )
    machine = AutonomyStateMachine()
    unsafe = AutonomyProposal(
        "unsafe",
        "code_patch_proposal",
        "Unsafe mutation",
        "Attempted unsafe mutation.",
        "Safety proof fixture.",
        required_approval=True,
        generated_code_executed=False,
        mutates_production=True,
        mutates_local_brain=False,
        safety_notes=["fixture"],
    )
    machine.check_proposal(unsafe)
    cartridge = KnowledgeCartridge(
        "cart_fixture",
        "metadata",
        True,
        "sha256:fixture",
        ["atlas", "provenance"],
        {"source": "fixture"},
        "public",
        "permissive",
        "Metadata-only public cartridge.",
    )
    kernel = AutonomyKernel(world, self_model)
    kernel_events = kernel.run_until_brief()

    results = {
        "knowledge_gap": {
            "pass": any(signal.deficit_type == "knowledge_gap" and signal.severity > 0 for signal in deficits),
            "signals": [signal.to_dict() for signal in deficits],
        },
        "resource_pressure": {
            "pass": any(signal.deficit_type == "resource_pressure" for signal in resource_deficits),
            "signals": [signal.to_dict() for signal in resource_deficits],
        },
        "congress_proposal": {
            "pass": bool(proposals)
            and all(proposal.required_approval for proposal in proposals)
            and all(not proposal.mutates_production and not proposal.mutates_local_brain for proposal in proposals),
            "proposals": [proposal.to_dict() for proposal in proposals],
            "network_used": congress.network_used,
        },
        "hot_swap_proposal_only": {
            "pass": patch.executed is False and patch.approval_required is True and validate_patch_proposal_safety(patch),
            "patch": patch.to_dict(),
        },
        "morning_brief": {
            "pass": any(event.event_type == "autonomy.morning_brief" for event in stream.list_events() + kernel_events),
            "events": [event.to_dict() for event in stream.list_events() + kernel_events],
        },
        "safety_block": {
            "pass": machine.state == "safety_stop" and machine.block_reason == "production_mutation_not_allowed",
            "state": machine.state,
            "reason": machine.block_reason,
        },
        "cartridge_protocol": {
            "pass": cartridge.raw_payload_included is False and 0.0 <= compatibility_score(["atlas"], cartridge) <= 1.0,
            "cartridge": cartridge.to_dict(),
            "compatibility": compatibility_score(["atlas"], cartridge),
        },
    }
    results["summary"] = {key: value["pass"] for key, value in results.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    json_path = output_dir / f"autonomy_kernel_proof_{timestamp}.json"
    md_path = output_dir / f"autonomy_kernel_proof_{timestamp}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_proof_markdown(results), encoding="utf-8")
    results["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return results


def _proof_markdown(results: dict[str, Any]) -> str:
    lines = ["# Autonomy Kernel Proof", ""]
    for key, passed in results["summary"].items():
        lines.append(f"- {key}: `{passed}`")
    lines.append("")
    lines.append("This is a proof-only autonomous self-model loop, not real consciousness or AGI.")
    lines.append("Generated proof output is audit data and should not be committed.")
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

