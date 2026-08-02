from __future__ import annotations

from cgsr.english.canonical_frames import CanonicalAnswerPlan
from cgsr.english.evaluation import evaluate_realized_answer
from cgsr.english.realizer import realize_answer_plan


def test_english_definition_realizer_is_grounded() -> None:
    plan = CanonicalAnswerPlan(
        plan_id="p1",
        language="en",
        intent="definition",
        audience_level="general",
        tone="plain",
        claims=[{"family": "definition", "x": "ATANOR", "category": "system", "y": "uses verified evidence"}],
        evidence_refs=["ev:1"],
        discourse_order=["definition"],
        glossary_terms={"ATANOR": "ATANOR"},
    )
    answer = realize_answer_plan(plan)
    assert answer.text == "ATANOR is a system that uses verified evidence."
    assert answer.unsupported_claims == []
    assert answer.trace_hidden


def test_comparison_preserves_contrast() -> None:
    plan = CanonicalAnswerPlan(
        plan_id="p2",
        language="en",
        intent="comparison",
        audience_level="general",
        tone="plain",
        claims=[{"family": "comparison", "x": "CGSR", "a": "construction choice", "y": "RHFC", "b": "memory recall"}],
        evidence_refs=["ev:2"],
        discourse_order=["comparison"],
    )
    assert "while" in realize_answer_plan(plan).text


def test_procedure_preserves_order() -> None:
    plan = CanonicalAnswerPlan(
        plan_id="p3",
        language="en",
        intent="procedure",
        audience_level="general",
        tone="plain",
        claims=[{"family": "procedure", "step1": "retrieve evidence", "step2": "select a frame", "step3": "check locks"}],
        evidence_refs=["ev:3"],
        discourse_order=["procedure"],
    )
    text = realize_answer_plan(plan).text
    assert text.index("First") < text.index("Then") < text.index("Finally")


def test_evidence_answer_does_not_invent_when_evidence_missing() -> None:
    plan = CanonicalAnswerPlan(
        plan_id="p4",
        language="en",
        intent="evidence_based_claim",
        audience_level="general",
        tone="plain",
        claims=[{"family": "evidence_based_claim", "claim": "ATANOR is supported"}],
        evidence_refs=[],
        discourse_order=["evidence_based_claim"],
    )
    answer = realize_answer_plan(plan)
    evaluation = evaluate_realized_answer(plan, answer)
    assert "not have enough verified evidence" in answer.text
    assert evaluation.false_confident == 0
    assert evaluation.abstain_correct


def test_abstention_frame_stays_abstaining() -> None:
    plan = CanonicalAnswerPlan(
        plan_id="p5",
        language="en",
        intent="unknown claim",
        audience_level="general",
        tone="plain",
        claims=[],
        evidence_refs=[],
        discourse_order=["abstention"],
    )
    assert "not have enough verified evidence" in realize_answer_plan(plan).text
