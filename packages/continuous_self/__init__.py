"""Continuously-alive self-model (: continuity, not cron)."""
from .self_state import (
    Observation,
    SelfState,
    Thought,
    evolve,
    load_or_begin,
    save_state,
)

__all__ = ["Observation", "SelfState", "Thought", "evolve", "load_or_begin", "save_state"]
