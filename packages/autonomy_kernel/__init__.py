"""Proof-only ATANOR autonomy kernel.

The package models an autonomous self-model loop. It is not real consciousness,
not AGI, not a production self-modifying system, and does not touch active
Cloud Brain, candidate learning, API, UI, production store, or Local Brain code.
"""

from .deficit import compute_deficit
from .event_stream import AutonomyEvent, InMemoryEventStream
from .models import (
    AutonomyProposal,
    DeficitSignal,
    MorningBriefEvent,
    SelfModelSnapshot,
    WorldModelSnapshot,
)
from .state_machine import AutonomyState, AutonomyStateMachine, SafetyPolicy

__all__ = [
    "AutonomyEvent",
    "AutonomyProposal",
    "AutonomyState",
    "AutonomyStateMachine",
    "DeficitSignal",
    "InMemoryEventStream",
    "MorningBriefEvent",
    "SafetyPolicy",
    "SelfModelSnapshot",
    "WorldModelSnapshot",
    "compute_deficit",
]

