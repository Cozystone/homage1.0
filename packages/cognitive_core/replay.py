"""Pure structural replay for canonical cycle receipts."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.cognitive_core.cycle import CycleReceipt, apply_state_patch


@dataclass(frozen=True, kw_only=True)
class SharedCognitiveStateView:
    """Read-only projection reconstructed from a receipt's event chain."""

    cycle_id: str
    receipt_id: str
    event_count: int
    last_event_id: str
    state: FrozenMap
    state_hash: str
    observer_only: bool = True
    authoritative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "cycle_id": self.cycle_id,
            "event_count": self.event_count,
            "last_event_id": self.last_event_id,
            "observer_only": self.observer_only,
            "receipt_id": self.receipt_id,
            "state": self.state.to_dict(),
            "state_hash": self.state_hash,
        }


def replay_cycle(
    value: CycleReceipt | Mapping[str, Any],
) -> SharedCognitiveStateView:
    """Rebuild the observer state without executing models, tools, or networks."""

    receipt = value if isinstance(value, CycleReceipt) else CycleReceipt.from_dict(value)
    state = FrozenMap(receipt.initial_state)
    parent_event_id: str | None = None
    for expected_sequence, event in enumerate(receipt.events):
        if event.sequence != expected_sequence:
            raise ValueError("cycle event sequence is not contiguous")
        if event.parent_event_id != parent_event_id:
            raise ValueError("cycle event parent linkage is invalid")
        before_hash = canonical_digest(state)
        if before_hash != event.state_before_hash:
            raise ValueError("cycle event state_before_hash does not match replay state")
        state = apply_state_patch(state, event.state_patch)
        after_hash = canonical_digest(state)
        if after_hash != event.state_after_hash:
            raise ValueError("cycle event state_after_hash does not match replay state")
        parent_event_id = event.event_id
    if canonical_digest(state) != receipt.terminal_state_hash:
        raise ValueError("terminal state hash does not match replayed state")
    return SharedCognitiveStateView(
        cycle_id=receipt.request_cycle.cycle_id,
        receipt_id=receipt.receipt_id,
        event_count=len(receipt.events),
        last_event_id=receipt.events[-1].event_id,
        state=state,
        state_hash=receipt.terminal_state_hash,
    )
