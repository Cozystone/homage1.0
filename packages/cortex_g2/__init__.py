"""CORTEX-G2: transparent neuromorphic graph loop for ATANOR.

This package implements bounded graph activation, salience gating,
predictive comparison, candidate crystal storage, dream questions, and
creative graph walks. It does not claim consciousness, final answer
quality, unrestricted self-learning, or external model use.
"""

from .activation_engine import run_graph_activation
from .creative_walk import run_creative_walk
from .crystal_store import get_crystal, list_crystals, maybe_create_crystal, promote_crystal, reuse_crystal, weaken_crystal
from .dream_loop import run_self_dream_cycle
from .predictive_engine import compare_predictions_to_evidence, generate_prediction_paths
from .salience_gate import select_global_workspace

__all__ = [
    "compare_predictions_to_evidence",
    "generate_prediction_paths",
    "get_crystal",
    "list_crystals",
    "maybe_create_crystal",
    "promote_crystal",
    "reuse_crystal",
    "run_creative_walk",
    "run_graph_activation",
    "run_self_dream_cycle",
    "select_global_workspace",
    "weaken_crystal",
]
