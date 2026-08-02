"""Typed schemas for English-first canonical CGSR generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any


@dataclass(frozen=True)
class CanonicalAnswerPlan:
    """Graph-grounded plan that English CGSR may realize.

    Claims and evidence are assumed to be produced upstream by ATANOR's
    retrieval/grounding path.  This class is not an answer generator.
    """

    plan_id: str
    language: str
    intent: str
    audience_level: str
    tone: str
    claims: list[dict[str, Any]]
    evidence_refs: list[str]
    discourse_order: list[str]
    uncertainty: str = ""
    forbidden_claims: list[str] = field(default_factory=list)
    glossary_terms: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EnglishConstructionFrame:
    """Reusable English construction frame with explicit slot constraints."""

    frame_id: str
    family: str
    slots: list[str]
    required_slots: list[str]
    optional_slots: list[str]
    semantic_constraints: dict[str, Any]
    surface_template: str
    style_tags: list[str]
    evidence_required: bool
    abstention_allowed: bool = False

    def template_slots(self) -> set[str]:
        """Return fields referenced by the surface template."""

        return {field for _, field, _, _ in Formatter().parse(self.surface_template) if field}

    def validate(self) -> None:
        """Raise when frame schema and template constraints disagree."""

        declared = set(self.slots)
        required = set(self.required_slots)
        referenced = self.template_slots()
        missing = required - declared
        undeclared = referenced - declared
        if missing:
            raise ValueError(f"required slots not declared: {sorted(missing)}")
        if undeclared:
            raise ValueError(f"template references undeclared slots: {sorted(undeclared)}")


@dataclass(frozen=True)
class RealizedAnswer:
    """Output of English realization after slot and evidence checks."""

    language: str
    text: str
    used_frames: list[str]
    filled_slots: dict[str, str]
    evidence_refs: list[str]
    unsupported_claims: list[str]
    entity_locks: list[str]
    number_locks: list[str]
    trace_hidden: bool = True
