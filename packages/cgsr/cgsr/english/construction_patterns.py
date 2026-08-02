"""Core English construction families for Stage E1."""

from __future__ import annotations

from .canonical_frames import EnglishConstructionFrame


def _frame(
    frame_id: str,
    family: str,
    template: str,
    required: list[str],
    *,
    evidence_required: bool = False,
    abstention_allowed: bool = False,
    style_tags: list[str] | None = None,
) -> EnglishConstructionFrame:
    slots = sorted(set(required + ["evidence_ref", "uncertainty", "example"]))
    frame = EnglishConstructionFrame(
        frame_id=frame_id,
        family=family,
        slots=slots,
        required_slots=required,
        optional_slots=[slot for slot in slots if slot not in required],
        semantic_constraints={"grounded_claims_only": True, "external_llm_reasoning": False},
        surface_template=template,
        style_tags=style_tags or [family, "canonical_en"],
        evidence_required=evidence_required,
        abstention_allowed=abstention_allowed,
    )
    frame.validate()
    return frame


def core_english_frames() -> list[EnglishConstructionFrame]:
    """Return the minimum English-first CGSR frame inventory."""

    return [
        _frame("en_definition_v1", "definition", "{x} is a {category} that {y}.", ["x", "category", "y"]),
        _frame(
            "en_comparison_v1",
            "comparison",
            "{x} focuses on {a}, while {y} focuses on {b}.",
            ["x", "a", "y", "b"],
        ),
        _frame(
            "en_procedure_v1",
            "procedure",
            "First, {step1}. Then, {step2}. Finally, {step3}.",
            ["step1", "step2", "step3"],
        ),
        _frame("en_cause_effect_v1", "cause_effect", "{cause} leads to {effect}.", ["cause", "effect"]),
        _frame("en_limitation_v1", "limitation", "The main limitation is {limitation}.", ["limitation"]),
        _frame("en_example_v1", "example", "For example, {example}.", ["example"]),
        _frame("en_summary_v1", "summary", "In short, {summary}.", ["summary"]),
        _frame(
            "en_evidence_claim_v1",
            "evidence_based_claim",
            "Based on {evidence_ref}, {claim}.",
            ["claim", "evidence_ref"],
            evidence_required=True,
        ),
        _frame(
            "en_abstention_v1",
            "abstention",
            "I do not have enough verified evidence to answer {x} confidently.",
            ["x"],
            abstention_allowed=True,
        ),
        _frame(
            "en_uncertainty_boundary_v1",
            "uncertainty_boundary",
            "The supported answer is {claim}; {uncertainty}.",
            ["claim", "uncertainty"],
            evidence_required=True,
        ),
    ]


def frame_by_family(family: str) -> EnglishConstructionFrame:
    """Return the first core frame for ``family``."""

    for frame in core_english_frames():
        if frame.family == family:
            return frame
    raise KeyError(f"unknown English construction family: {family}")
