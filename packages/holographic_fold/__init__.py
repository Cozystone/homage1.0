"""ATANOR Phase Holographic Folding Engine (PHFE).

See docs/ATANOR_PHASE_HOLOGRAPHIC_FOLDING_ENGINE_v0.md for the full spec.

v0.1: Node State Field builder + active working-set selector.
v0.2: multi-channel Pair Representation (wave interference = central force channel).
(pure data, deterministic, read-only — NO folding, NO answer influence yet).
"""

from .state_field import (
    SOURCE_TYPES,
    StateField,
    StateNode,
    build_state_field,
)
from .pair_representation import (
    NodePair,
    PairRepresentation,
    build_pair_representation,
)
from .folding import (
    FoldedNode,
    FoldedState,
    fold_state,
)
from .state_field_adapter import build_field_inputs
from .compare_mode import compare_fold_to_answer, folded_core

__all__ = [
    "SOURCE_TYPES",
    "StateField",
    "StateNode",
    "build_state_field",
    "NodePair",
    "PairRepresentation",
    "build_pair_representation",
    "FoldedNode",
    "FoldedState",
    "fold_state",
    "build_field_inputs",
    "compare_fold_to_answer",
    "folded_core",
]
