"""English-first canonical CGSR components.

The English package is intentionally additive: it does not replace the Korean
CGSR path or the existing RHFC core.  It provides a canonical construction
layer that can be evaluated before any default answer-path integration.
"""

from .canonical_frames import CanonicalAnswerPlan, EnglishConstructionFrame, RealizedAnswer
from .construction_patterns import core_english_frames
from .factual_decomposition import EnglishFactualFrame, decompose_english_fact, evaluate_fixture_set
from .realizer import realize_answer_plan

__all__ = [
    "CanonicalAnswerPlan",
    "EnglishFactualFrame",
    "EnglishConstructionFrame",
    "RealizedAnswer",
    "core_english_frames",
    "decompose_english_fact",
    "evaluate_fixture_set",
    "realize_answer_plan",
]
