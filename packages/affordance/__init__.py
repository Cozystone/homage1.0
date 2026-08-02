# -*- coding: utf-8 -*-
"""Context → affordance: perceive state, lay walkable paths, resonate (never condition)."""
from .context_affordance import (
    Observation,
    Proposal,
    load_affordances,
    propose,
    resonance,
)

__all__ = ["Observation", "Proposal", "propose", "resonance", "load_affordances"]
