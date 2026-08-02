"""Shared CGSR Stage 1 data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Morpheme:
    """Thin morphology wrapper result.

    The morphology analyzer is only an input/output tool.  It does not decide
    answer content and is not a rule-based chatbot path.
    """

    form: str
    tag: str
    start: int = 0
    length: int = 0
    has_final_consonant: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConstructionCandidate:
    """Frequency-induced surface construction candidate."""

    construction_id: str
    surface_pattern: tuple[str, ...]
    tag_pattern: tuple[str, ...]
    abstract_pattern: tuple[str, ...]
    examples: list[str] = field(default_factory=list)
    frequency: int = 0
    canonical_form: str = ""
    family_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "construction_id": self.construction_id,
            "surface_pattern": list(self.surface_pattern),
            "tag_pattern": list(self.tag_pattern),
            "abstract_pattern": list(self.abstract_pattern),
            "examples": self.examples,
            "frequency": self.frequency,
            "canonical_form": self.canonical_form,
            "family_id": self.family_id,
        }


@dataclass(frozen=True)
class RealizationInput:
    """Minimal semantic skeleton for Stage 1 end-to-end proof."""

    concept: str
    predicate: str
    object: str
    formality: str = "formal"
