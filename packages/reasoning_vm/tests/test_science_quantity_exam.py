from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from packages.reasoning_vm.deliberator.science_quantity_goal import (
    compile_neutralization_question,
)
from packages.reasoning_vm.deliberator.science_quantity_resolver import (
    ScalarDerivationProof,
    ScalarQuantityResolver,
    ScalarResolution,
)
from packages.reasoning_vm.science_quantity_exam import (
    answer_scalar_science_mcq,
    scalar_outcome_digest,
)
from packages.reasoning_vm.science_quantity_staging import (
    QuantityStageOverlay,
    load_science_quantity_stage,
)


STAGE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "science_stage_scalar_quantity_v1"
)
STEM = (
    "What volume of 0.200 M NaOH is required to completely neutralize "
    "25.0 mL of 0.100 M HCl?"
)
CHOICES = {
    "A": "6.25 mL",
    "B": "12.5 mL",
    "C": "25.0 mL",
    "D": "50.0 mL",
}


def _empty_state_digest() -> str:
    return hashlib.sha256(
        json.dumps({}, sort_keys=True).encode("utf-8")
    ).hexdigest()


def test_scalar_candidate_measures_strict_off_to_on_accuracy():
    stage = load_science_quantity_stage(STAGE_ROOT)
    off = answer_scalar_science_mcq(
        STEM,
        CHOICES,
        None,
        overlay_enabled=False,
        base_state_digest=_empty_state_digest,
    )
    on = answer_scalar_science_mcq(
        STEM,
        CHOICES,
        stage,
        overlay_enabled=True,
        base_state_digest=_empty_state_digest,
    )

    assert off["compiler"]["compiled"] is True
    assert off["choice_key"] is None
    assert off["reason"] == "required_evidence_unavailable"
    assert off["engine"]["formula_fired"] is False
    assert off["engine"]["accepted_fire"] is False
    assert off["integrity"]["stage_structurally_absent"] is True
    assert off["staging"]["stage_snapshot_bound_bytes"] == 0

    assert on["compiler"]["input_fingerprint"] == (
        off["compiler"]["input_fingerprint"]
    )
    assert on["compiler"]["goal_digest_sha256"] == (
        off["compiler"]["goal_digest_sha256"]
    )
    assert on["choice_key"] == "B"
    assert on["reason"] == "grounded_stage_formula_derivation"
    assert on["engine"]["formula_fired"] is True
    assert on["engine"]["raw_fired"] is True
    assert on["engine"]["accepted_fire"] is True
    assert on["engine"]["grounded"] is True
    assert on["staging"]["grounded_leaf_count"] == 3
    assert on["staging"]["grounded_stage_leaf_count"] == 3
    assert on["staging"]["evidence_ids"] == [
        "quantity-evidence-001",
        "quantity-evidence-002",
        "quantity-evidence-008",
    ]
    assert on["staging"]["external_authenticity_established"] is False
    assert on["integrity"]["base_state_unchanged"] is True


def test_scalar_candidate_counterfactual_changes_answer_exactly():
    stage = load_science_quantity_stage(STAGE_ROOT)
    doubled = answer_scalar_science_mcq(
        (
            "What volume of 0.200 M NaOH is required to completely neutralize "
            "50.0 mL of 0.100 M HCl?"
        ),
        {
            "A": "12.5 mL",
            "B": "25.0 mL",
            "C": "50.0 mL",
            "D": "100.0 mL",
        },
        stage,
        overlay_enabled=True,
    )
    polyprotic = answer_scalar_science_mcq(
        (
            "What volume of 0.200 M NaOH is required to completely neutralize "
            "25.0 mL of 0.100 M H2SO4?"
        ),
        {
            "A": "6.25 mL",
            "B": "12.5 mL",
            "C": "25.0 mL",
            "D": "50.0 mL",
        },
        stage,
        overlay_enabled=True,
    )

    assert doubled["choice_key"] == "B"
    assert polyprotic["choice_key"] == "C"
    assert doubled["engine"]["accepted_fire"] is True
    assert polyprotic["engine"]["accepted_fire"] is True


def test_scalar_candidate_abstains_on_unknown_role_or_missing_exact_choice():
    stage = load_science_quantity_stage(STAGE_ROOT)
    unknown = answer_scalar_science_mcq(
        (
            "What volume of 0.200 M RbOH is required to completely neutralize "
            "25.0 mL of 0.100 M HBr?"
        ),
        CHOICES,
        stage,
        overlay_enabled=True,
    )
    reversed_roles = answer_scalar_science_mcq(
        (
            "What volume of 0.200 M HCl is required to completely neutralize "
            "25.0 mL of 0.100 M NaOH?"
        ),
        CHOICES,
        stage,
        overlay_enabled=True,
    )
    missing_choice = answer_scalar_science_mcq(
        STEM,
        {
            "A": "1 mL",
            "B": "2 mL",
            "C": "3 mL",
            "D": "4 mL",
        },
        stage,
        overlay_enabled=True,
    )

    assert unknown["compiler"]["compiled"] is True
    assert unknown["reason"] == "entity_or_formula_unresolved"
    assert unknown["engine"]["accepted_fire"] is False
    assert reversed_roles["reason"] == "species_roles_invalid"
    assert reversed_roles["engine"]["formula_fired"] is False
    assert missing_choice["reason"] == "no_exact_choice_match"
    assert missing_choice["engine"]["formula_fired"] is True
    assert missing_choice["engine"]["raw_fired"] is False


def test_scalar_candidate_rejects_any_unbound_stage_leaf(monkeypatch):
    stage = load_science_quantity_stage(STAGE_ROOT)
    compilation = compile_neutralization_question(STEM, CHOICES)
    overlay = QuantityStageOverlay(stage, enabled=True)
    genuine = ScalarQuantityResolver().resolve(
        compilation,
        overlay,
        stem=STEM,
    )
    assert genuine.proof is not None
    forged_proof = replace(
        genuine.proof,
        stage_facts=(
            genuine.proof.stage_facts[0],
            genuine.proof.stage_facts[1],
            ("invented", "formula_expression_sha256", "0" * 64),
        ),
    )
    forged = ScalarResolution(
        choice_key=genuine.choice_key,
        answer_liters=genuine.answer_liters,
        raw_fired=True,
        formula_fired=True,
        grounded=True,
        proof=forged_proof,
        reason="forged",
    )
    monkeypatch.setattr(
        ScalarQuantityResolver,
        "resolve",
        lambda self, compilation, overlay, *, stem: forged,
    )

    outcome = answer_scalar_science_mcq(
        STEM,
        CHOICES,
        stage,
        overlay_enabled=True,
    )
    assert outcome["engine"]["raw_fired"] is True
    assert outcome["engine"]["accepted_fire"] is False
    assert outcome["choice_key"] is None
    assert outcome["reason"] == "proof_replay_failed"
    assert outcome["staging"]["grounded_leaf_count"] == 3
    assert outcome["staging"]["grounded_stage_leaf_count"] < 3
    assert outcome["engine"]["grounded"] is False
    assert outcome["engine"]["proof_replayed"] is False


def test_scalar_candidate_replays_formula_even_with_genuine_stage_leaves(
    monkeypatch,
):
    stage = load_science_quantity_stage(STAGE_ROOT)
    compilation = compile_neutralization_question(STEM, CHOICES)
    overlay = QuantityStageOverlay(stage, enabled=True)
    genuine = ScalarQuantityResolver().resolve(
        compilation,
        overlay,
        stem=STEM,
    )
    assert genuine.proof is not None
    forged_proof = replace(
        genuine.proof,
        answer_liters=Fraction(1, 40),
        choice_key="C",
    )
    forged = ScalarResolution(
        choice_key="C",
        answer_liters=Fraction(1, 40),
        raw_fired=True,
        formula_fired=True,
        grounded=True,
        proof=forged_proof,
        reason="forged_with_genuine_stage_leaves",
    )
    monkeypatch.setattr(
        ScalarQuantityResolver,
        "resolve",
        lambda self, compilation, overlay, *, stem: forged,
    )

    outcome = answer_scalar_science_mcq(
        STEM,
        CHOICES,
        stage,
        overlay_enabled=True,
    )
    assert outcome["staging"]["grounded_stage_leaf_count"] == 3
    assert outcome["engine"]["raw_fired"] is True
    assert outcome["engine"]["resolver_grounded"] is True
    assert outcome["engine"]["proof_replayed"] is False
    assert outcome["engine"]["grounded"] is False
    assert outcome["engine"]["accepted_fire"] is False
    assert outcome["choice_key"] is None
    assert outcome["reason"] == "proof_replay_failed"


def test_scalar_candidate_fails_closed_on_state_mutation_or_stage_boundary():
    stage = load_science_quantity_stage(STAGE_ROOT)
    states = iter(("a" * 64, "b" * 64))
    mutated = answer_scalar_science_mcq(
        STEM,
        CHOICES,
        stage,
        overlay_enabled=True,
        base_state_digest=lambda: next(states),
    )
    wrong_boundary = answer_scalar_science_mcq(
        STEM,
        CHOICES,
        stage,
        overlay_enabled=False,
    )

    assert mutated["choice_key"] is None
    assert mutated["reason"] == "base_state_mutated_fail_closed"
    assert mutated["error_kind"] == "BaseStateMutationDetected"
    assert mutated["engine"]["accepted_fire"] is False
    assert wrong_boundary["choice_key"] is None
    assert wrong_boundary["reason"] == "candidate_error_fail_closed"
    assert wrong_boundary["error_kind"] == "TypeError"
    assert wrong_boundary["integrity"]["stage_structurally_absent"] is False


def test_scalar_candidate_reads_choices_once_and_replays_semantically():
    stage = load_science_quantity_stage(STAGE_ROOT)

    class OneReadChoices(Mapping[str, str]):
        def __init__(self):
            self.reads = 0

        def __getitem__(self, key: str) -> str:
            raise AssertionError("candidate must execute compiler snapshot")

        def __iter__(self) -> Iterator[str]:
            raise AssertionError("candidate must use Mapping.items once")

        def __len__(self) -> int:
            return len(CHOICES)

        def items(self):
            self.reads += 1
            if self.reads > 1:
                raise AssertionError("second Mapping read")
            return iter(CHOICES.items())

    choices = OneReadChoices()
    replay_choices = OneReadChoices()
    first = answer_scalar_science_mcq(
        STEM,
        choices,
        stage,
        overlay_enabled=True,
    )
    second = answer_scalar_science_mcq(
        STEM,
        replay_choices,
        stage,
        overlay_enabled=True,
    )
    assert choices.reads == 1
    assert replay_choices.reads == 1
    assert first["choice_key"] == "B"
    assert scalar_outcome_digest(first) == scalar_outcome_digest(second)
