"""Deterministic natural-language to typed-goal compiler for DELIBERATOR.

This is intentionally a narrow M1 compiler, not a general language understanding
claim. It recognizes only an explicit MCQ category-membership family and emits
typed ``(choice, is_a, target)`` proof goals. Unsupported language abstains with
an inspectable reason. Later compiler families can be added behind independent
tests and paired capability gates without changing the proof engine.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


COMPILER_SCHEMA = "atanor.deliberator.mcq_compiler.v1"
MAX_GOAL_CANDIDATES = 6

_WORD = r"[A-Za-z][A-Za-z-]{2,}"
_TARGET = rf"(?P<target>{_WORD}(?:\s+{_WORD}){{0,3}})"
_CATEGORY_PATTERNS = (
    re.compile(
        rf"\bwhich\s+of\s+(?:the\s+)?(?:following|these)\s+"
        rf"(?:items?\s+)?(?:is|are)\s+(?:not\s+)?(?:an?\s+){_TARGET}"
        rf"\s*[?.]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bwhich\s+(?:one\s+)?is\s+(?:not\s+)?(?:an?\s+){_TARGET}"
        rf"\s*[?.]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bwhich\s+of\s+(?:the\s+)?(?:following|these)\s+(?:is|are)\s+"
        rf"(?:not\s+)?(?:an?\s+)?(?:example|type|kind|member)\s+of\s+{_TARGET}"
        rf"\s*[?.]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bwhich\s+of\s+(?:the\s+)?(?:following|these)\s+(?:is|are)\s+"
        rf"(?:not\s+)?classified\s+as\s+(?:an?\s+)?{_TARGET}"
        rf"\s*[?.]?\s*$",
        re.IGNORECASE,
    ),
)
_INVALID_TARGET_WORDS = {
    "after",
    "answer",
    "answers",
    "associated",
    "before",
    "caused",
    "causes",
    "causing",
    "claim",
    "claims",
    "classified",
    "connected",
    "conclusion",
    "conclusions",
    "contains",
    "containing",
    "correct",
    "explanation",
    "explanations",
    "example",
    "false",
    "following",
    "from",
    "greater",
    "higher",
    "incorrect",
    "kind",
    "larger",
    "least",
    "less",
    "likely",
    "lower",
    "most",
    "member",
    "option",
    "options",
    "produced",
    "produces",
    "related",
    "responsible",
    "smaller",
    "statement",
    "statements",
    "type",
    "true",
    "unlikely",
    "with",
    "than",
    "through",
}


@dataclass(frozen=True)
class TypedMCQGoal:
    """A typed proof obligation whose subject is supplied by each answer choice."""

    relation: str
    target: str
    subject_source: str
    negated: bool
    compiler_rule: str
    confidence: float

    def __post_init__(self) -> None:
        if self.relation != "is_a":
            raise ValueError("M1 MCQ compiler permits only the is_a relation")
        if not self.target.strip():
            raise ValueError("typed goal target must be non-empty")
        if self.subject_source != "choice_text":
            raise ValueError("typed goal subject must come from choice_text")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("compiler confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MCQCompilation:
    """Bounded compiler receipt; empty goals mean explicit abstention."""

    schema_version: str
    status: str
    surface_family: str | None
    goals: tuple[TypedMCQGoal, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != COMPILER_SCHEMA:
            raise ValueError("unsupported compiler schema")
        if self.status not in {"compiled", "abstain"}:
            raise ValueError("compiler status must be compiled or abstain")
        if self.status == "compiled" and not self.goals:
            raise ValueError("compiled receipt requires at least one goal")
        if self.status == "abstain" and self.goals:
            raise ValueError("abstention receipt cannot carry goals")
        if len(self.goals) > MAX_GOAL_CANDIDATES:
            raise ValueError("compiler goal budget exceeded")

    @property
    def compiled(self) -> bool:
        return self.status == "compiled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "surface_family": self.surface_family,
            "goals": [goal.to_dict() for goal in self.goals],
            "reason": self.reason,
        }


def compile_mcq_goals(stem: str) -> MCQCompilation:
    """Compile the single supported category-membership family or abstain."""
    from packages.reasoning_vm.discrimination import _neg_signal

    text = str(stem or "")
    target = None
    for pattern in _CATEGORY_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            candidate = " ".join(match.group("target").split())
            words = {word.casefold() for word in candidate.split()}
            if words and not words.intersection(_INVALID_TARGET_WORDS):
                target = candidate
                break
    if target is None:
        return MCQCompilation(
            schema_version=COMPILER_SCHEMA,
            status="abstain",
            surface_family=None,
            goals=(),
            reason="unsupported_surface_family",
        )
    negated = _neg_signal(text)
    return MCQCompilation(
        schema_version=COMPILER_SCHEMA,
        status="compiled",
        surface_family="category_membership",
        goals=(
            TypedMCQGoal(
                relation="is_a",
                target=target,
                subject_source="choice_text",
                negated=negated,
                compiler_rule="explicit_category_membership_v1",
                confidence=0.95,
            ),
        ),
        reason="typed_goal_candidates_emitted",
    )
