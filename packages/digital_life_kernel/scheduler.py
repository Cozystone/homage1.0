from __future__ import annotations

from .action_policy import propose_actions
from .event_stream import InMemoryLifeEventStream
from .models import LifeKernelState
from .needs import signals_from_observation
from .sandbox import simulate_proposal
from .state import transition


def plan_cycle(observation: dict) -> tuple[LifeKernelState, InMemoryLifeEventStream]:
    """Run one proof-only observe-plan-sandbox cycle."""

    stream = InMemoryLifeEventStream()
    signals = signals_from_observation(observation)
    for signal in signals:
        stream.emit("life.signal_detected", f"Signal: {signal.signal_type}", signal.to_dict())
    proposals = propose_actions(signals)
    for proposal in proposals:
        stream.emit("life.action_proposed", proposal.title, proposal.to_dict())
        result = simulate_proposal(proposal)
        stream.emit(
            "life.sandbox_passed" if result.passed else "life.sandbox_blocked",
            f"Sandbox {'passed' if result.passed else 'blocked'}",
            result.to_dict(),
        )
        if proposal.requires_user_approval:
            stream.emit("life.user_approval_required", proposal.title, proposal.to_dict())
    state = transition(LifeKernelState("observing"), signals=signals, proposals=proposals, last_event_id=stream.list_events()[-1].event_id)
    return state, stream
