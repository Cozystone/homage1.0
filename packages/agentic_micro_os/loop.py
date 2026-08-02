from __future__ import annotations

import hashlib

from .models import AgentAction, AgentLoopState, AgentObservation, SkillDraft, TrajectoryRecord
from .splatra_cell import SplatraCosmosCell


class BoundedAgentLoop:
    def __init__(self, goal: str, cell: SplatraCosmosCell | None = None, max_cycles: int = 5) -> None:
        self.goal = goal
        self.cell = cell or SplatraCosmosCell(max_cycles=max_cycles)
        self.max_cycles = max_cycles

    def run(self) -> AgentLoopState:
        observations = []
        actions = []
        proposals = []
        for step in range(self.max_cycles):
            summary = f"cycle {step}: evaluate SPLATRA compression and propose safe dashboard patch"
            observations.append(AgentObservation("splatra_cell", hashlib.sha256(summary.encode()).hexdigest(), "public", summary))
            actions.append(AgentAction(f"action_{step}", "run_particle_compression_eval", {}, ["run_cell_test_mock"]))
            if step == 0:
                proposals.append(self.cell.propose_orb_patch("Tune orb LOD budget and audio-reactive shell controls."))
        return AgentLoopState(
            loop_id="bounded_splatra_loop_0",
            goal=self.goal,
            budget={"max_cycles": self.max_cycles},
            current_step=self.max_cycles,
            observations=observations,
            proposed_actions=actions,
            patch_proposals=proposals,
            evaluation_scores={"bounded": 1.0},
            stopped_reason="max_cycles",
        )


def draft_skill_from_loop(state: AgentLoopState) -> SkillDraft:
    return SkillDraft(
        "skill_splatra_eval_v0",
        "When hologram particle quality changes, run compression and LOD checks.",
        ["run particle compression eval", "compare budget tiers", "write proposal only"],
        ["run_cell_test_mock", "write_cell_patch_manifest"],
        ["draft only", "promotion required", "no auto commit"],
    )


def compress_trajectory(raw_notes: list[str]) -> TrajectoryRecord:
    redacted = ["[private-redacted]" if "private" in note.lower() else note for note in raw_notes]
    return TrajectoryRecord("loop", redacted, [], [], "; ".join(redacted)[:240], no_private_raw_data=True)
