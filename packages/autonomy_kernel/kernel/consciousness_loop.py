from __future__ import annotations

from packages.autonomy_kernel.congress import SandboxCongress
from packages.autonomy_kernel.deficit import compute_deficit
from packages.autonomy_kernel.event_stream import AutonomyEvent, InMemoryEventStream, utc_now
from packages.autonomy_kernel.models import SelfModelSnapshot, WorldModelSnapshot
from packages.autonomy_kernel.state_machine import AutonomyState, AutonomyStateMachine, SafetyPolicy


class AutonomyKernel:
    """Proof-only autonomous self-model loop.

    This is not a proof of consciousness. It is a deterministic local loop for
    observation, deficit computation, proposal generation, and morning briefs.
    """

    def __init__(self, world: WorldModelSnapshot, self_model: SelfModelSnapshot, policy: SafetyPolicy | None = None) -> None:
        self.world = world
        self.self_model = self_model
        self.machine = AutonomyStateMachine(policy)
        self.stream = InMemoryEventStream()
        self.congress = SandboxCongress()
        self.deficits = []
        self.proposals = []

    def step(self) -> AutonomyState:
        state = self.machine.step()
        if state == "compute_deficit":
            self.deficits = compute_deficit(self.world, self.self_model)
            for deficit in self.deficits:
                self.stream.append_event(
                    AutonomyEvent(
                        f"event_{deficit.signal_id}",
                        utc_now(),
                        "autonomy_kernel",
                        "autonomy.deficit_detected",
                        5,
                        f"Deficit detected: {deficit.deficit_type}",
                        deficit.source,
                        deficit.to_dict(),
                        False,
                    )
                )
        elif state == "sandbox_congress":
            self.proposals = self.congress.deliberate(self.deficits)
            self.stream.append_event(
                AutonomyEvent(
                    "event_congress_summary",
                    utc_now(),
                    "sandbox_congress",
                    "autonomy.congress_summary",
                    4,
                    "Sandbox congress completed",
                    f"{len(self.proposals)} proposal(s) generated.",
                    {"proposal_count": len(self.proposals)},
                    False,
                )
            )
        elif state == "present_morning_brief":
            self.stream.append_event(
                AutonomyEvent(
                    "event_morning_brief",
                    utc_now(),
                    "autonomy_kernel",
                    "autonomy.morning_brief",
                    3,
                    "Morning autonomy brief",
                    f"{len(self.deficits)} deficit(s), {len(self.proposals)} proposal(s).",
                    {"deficits": len(self.deficits), "proposals": [proposal.to_dict() for proposal in self.proposals]},
                    bool(self.proposals),
                )
            )
        return state

    def run_until_brief(self, max_steps: int = 16) -> list[AutonomyEvent]:
        for _ in range(max_steps):
            state = self.step()
            if state == "present_morning_brief":
                break
            if state in {"blocked", "safety_stop"}:
                break
        return self.get_events()

    def get_state(self) -> AutonomyState:
        return self.machine.state

    def get_events(self) -> list[AutonomyEvent]:
        return self.stream.list_events()

