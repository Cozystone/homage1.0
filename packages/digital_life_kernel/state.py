from __future__ import annotations

from .models import LifeActionProposal, LifeKernelState, LifeSignal


def transition(
    state: LifeKernelState,
    *,
    signals: list[LifeSignal] | None = None,
    proposals: list[LifeActionProposal] | None = None,
    last_event_id: str | None = None,
) -> LifeKernelState:
    """Return the next kernel state without mutating external stores."""

    next_signals = signals if signals is not None else state.active_signals
    next_proposals = proposals if proposals is not None else state.active_proposals
    if any(not proposal.safe_by_default for proposal in next_proposals):
        name = "safety_stop"
    elif next_proposals:
        name = "awaiting_review"
    elif next_signals:
        name = "planning"
    else:
        name = "idle"
    return LifeKernelState(name, next_signals, next_proposals, last_event_id or state.last_event_id, dict(state.metadata))
