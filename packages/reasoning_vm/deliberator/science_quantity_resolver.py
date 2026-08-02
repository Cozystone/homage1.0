"""Exact, provenance-aware resolver for the neutralization-volume goal.

The resolver is a sibling of the existing DELIBERATOR path.  It keeps the same
propose/prove/verify discipline without registering a mutable kernel: a
stage-bound rational-v1 AST is interpreted under exact ``Fraction`` inputs,
the conservation equality is recomputed, and a frozen proof is independently
replayed before an MCQ choice can be proposed.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from packages.cognitive_core.canonical import canonical_digest
from packages.evolution.rational_evolver import (
    canonical as canonical_rational,
    evaluate as evaluate_rational,
)
from packages.reasoning_vm.deliberator.science_quantity_goal import (
    FORMULA_ID,
    NeutralizationCompilation,
    verify_compilation_source_spans,
)
from packages.reasoning_vm.science_quantity_staging import (
    QuantityStageOverlay,
    StagedFormula,
    StagedSpecies,
)


SCALAR_PROOF_SCHEMA = "atanor.scalar-neutralization-proof.v1"
MAX_RESULT_LITERS = Fraction(1000)


@dataclass(frozen=True)
class PromptQuantityProof:
    """One prompt-owned value already bound by the compiler goal digest."""

    slot: str
    exact_value: Fraction
    unit: str
    source_start: int
    source_end: int
    source_text_sha256: str
    binding_digest_sha256: str

    def __post_init__(self) -> None:
        if self.slot not in {
            "known_concentration",
            "known_volume_l",
            "target_concentration",
        }:
            raise ValueError("unknown prompt quantity proof slot")
        if type(self.exact_value) is not Fraction or self.exact_value <= 0:
            raise ValueError("prompt quantity proof must be positive and exact")
        expected_unit = (
            "L" if self.slot == "known_volume_l" else "mol/L"
        )
        if self.unit != expected_unit:
            raise ValueError("prompt quantity proof unit mismatch")
        if (
            type(self.source_start) is not int
            or type(self.source_end) is not int
            or not 0 <= self.source_start < self.source_end
            or type(self.source_text_sha256) is not str
            or len(self.source_text_sha256) != 64
            or type(self.binding_digest_sha256) is not str
            or len(self.binding_digest_sha256) != 64
        ):
            raise ValueError("prompt quantity proof digest invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "exact_value": canonical_rational(self.exact_value),
            "unit": self.unit,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "source_text_sha256": self.source_text_sha256,
            "binding_digest_sha256": self.binding_digest_sha256,
        }


@dataclass(frozen=True)
class ScalarDerivationProof:
    """Frozen proof whose leaves are exactly the three staged authorities."""

    schema_version: str
    goal_digest_sha256: str
    formula_id: str
    formula_ast_digest_sha256: str
    prompt_bindings: tuple[PromptQuantityProof, ...]
    stage_facts: tuple[tuple[str, str, str], ...]
    answer_liters: Fraction
    choice_key: str
    conservation_left: Fraction
    conservation_right: Fraction

    def __post_init__(self) -> None:
        if self.schema_version != SCALAR_PROOF_SCHEMA:
            raise ValueError("unsupported scalar proof schema")
        if (
            type(self.goal_digest_sha256) is not str
            or len(self.goal_digest_sha256) != 64
            or self.formula_id != FORMULA_ID
            or type(self.formula_ast_digest_sha256) is not str
            or len(self.formula_ast_digest_sha256) != 64
        ):
            raise ValueError("scalar proof identity invalid")
        if (
            len(self.prompt_bindings) != 3
            or {row.slot for row in self.prompt_bindings}
            != {
                "known_concentration",
                "known_volume_l",
                "target_concentration",
            }
            or len(self.stage_facts) != 3
            or len(set(self.stage_facts)) != 3
            or any(
                not isinstance(row, tuple)
                or len(row) != 3
                or any(type(value) is not str for value in row)
                for row in self.stage_facts
            )
        ):
            raise ValueError("scalar proof bindings are incomplete")
        if (
            type(self.answer_liters) is not Fraction
            or self.answer_liters <= 0
            or self.answer_liters > MAX_RESULT_LITERS
            or type(self.choice_key) is not str
            or not self.choice_key
            or type(self.conservation_left) is not Fraction
            or type(self.conservation_right) is not Fraction
            or self.conservation_left <= 0
            or self.conservation_left != self.conservation_right
        ):
            raise ValueError("scalar proof result or conservation is invalid")

    def leaves(self) -> list[tuple[str, str, str]]:
        return list(self.stage_facts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "goal_digest_sha256": self.goal_digest_sha256,
            "formula_id": self.formula_id,
            "formula_ast_digest_sha256": self.formula_ast_digest_sha256,
            "prompt_bindings": [
                row.to_dict() for row in self.prompt_bindings
            ],
            "stage_facts": [list(row) for row in self.stage_facts],
            "answer_liters": canonical_rational(self.answer_liters),
            "choice_key": self.choice_key,
            "conservation_left": canonical_rational(
                self.conservation_left
            ),
            "conservation_right": canonical_rational(
                self.conservation_right
            ),
        }


@dataclass(frozen=True)
class ScalarResolution:
    choice_key: str | None
    answer_liters: Fraction | None
    raw_fired: bool
    formula_fired: bool
    grounded: bool
    proof: ScalarDerivationProof | None
    reason: str

    def __post_init__(self) -> None:
        if self.raw_fired and (
            self.choice_key is None
            or self.answer_liters is None
            or self.proof is None
        ):
            raise ValueError("raw scalar fire requires a proposed proof")
        if self.grounded and not self.raw_fired:
            raise ValueError("grounded scalar result must have fired")
        if self.proof is not None and not self.raw_fired:
            raise ValueError("abstention cannot retain a scalar proof")

    def to_engine_dict(self) -> dict[str, Any]:
        return {
            "choice_key": self.choice_key,
            "answer_liters": (
                canonical_rational(self.answer_liters)
                if self.answer_liters is not None
                else None
            ),
            "mode": "grounded" if self.grounded else "abstain",
            "raw_fired": self.raw_fired,
            "formula_fired": self.formula_fired,
            "grounded": self.grounded,
            "hops": 6 if self.grounded else 0,
            "proof": self.proof,
            "reason": self.reason,
            "engine": "scalar_rational_stage_resolver",
        }


def _prompt_bindings(
    compilation: NeutralizationCompilation,
) -> tuple[PromptQuantityProof, ...]:
    goal = compilation.goal
    if goal is None or compilation.goal_digest_sha256 is None:
        raise ValueError("compiled scalar goal is required")
    rows = (
        (
            "known_concentration",
            goal.known_concentration_mol_per_liter,
            "mol/L",
            "known_concentration",
        ),
        ("known_volume_l", goal.known_volume_liters, "L", "known_volume"),
        (
            "target_concentration",
            goal.target_concentration_mol_per_liter,
            "mol/L",
            "target_concentration",
        ),
    )
    spans = {row.slot: row for row in goal.source_spans}
    return tuple(
        PromptQuantityProof(
            slot=slot,
            exact_value=value,
            unit=unit,
            source_start=spans[span_slot].start,
            source_end=spans[span_slot].end,
            source_text_sha256=spans[span_slot].text_sha256,
            binding_digest_sha256=canonical_digest(
                {
                    "goal_digest_sha256": compilation.goal_digest_sha256,
                    "slot": slot,
                    "exact_value": canonical_rational(value),
                    "unit": unit,
                    "source_span": spans[span_slot].to_dict(),
                }
            ),
        )
        for slot, value, unit, span_slot in rows
    )


def _environment(
    compilation: NeutralizationCompilation,
    known: StagedSpecies,
    target: StagedSpecies,
) -> dict[str, Any]:
    goal = compilation.goal
    if goal is None:
        raise ValueError("scalar environment requires a compiled goal")
    return {
        "known_concentration": goal.known_concentration_mol_per_liter,
        "known_volume_l": goal.known_volume_liters,
        "known_equivalents": known.equivalents_per_mole,
        "target_concentration": goal.target_concentration_mol_per_liter,
        "target_equivalents": target.equivalents_per_mole,
    }


def _evaluate(
    compilation: NeutralizationCompilation,
    known: StagedSpecies,
    target: StagedSpecies,
    formula: StagedFormula,
) -> tuple[Fraction, Fraction, Fraction] | None:
    goal = compilation.goal
    if (
        goal is None
        or known.role != goal.known_role_required
        or target.role != goal.target_role_required
    ):
        return None
    env = _environment(compilation, known, target)
    result = evaluate_rational(
        formula.expression,
        env,
        max_nodes=15,
        max_steps=128,
        max_bits=4096,
        max_exp10=300,
    )
    if (
        result is None
        or result <= 0
        or result > MAX_RESULT_LITERS
    ):
        return None
    left = (
        env["known_concentration"]
        * env["known_volume_l"]
        * env["known_equivalents"]
    )
    right = (
        env["target_concentration"]
        * result
        * env["target_equivalents"]
    )
    if (
        type(left) is not Fraction
        or type(right) is not Fraction
        or left <= 0
        or left != right
    ):
        return None
    return result, left, right


def _resolve_stage_rows(
    compilation: NeutralizationCompilation,
    overlay: QuantityStageOverlay,
) -> tuple[StagedSpecies, StagedSpecies, StagedFormula] | None:
    goal = compilation.goal
    if goal is None:
        return None
    known = overlay.resolve_species(goal.known_species)
    target = overlay.resolve_species(goal.target_species)
    formula = overlay.formula(goal.formula_id)
    if known is None or target is None or formula is None:
        return None
    return known, target, formula


def verify_scalar_proof(
    proof: ScalarDerivationProof,
    compilation: NeutralizationCompilation,
    overlay: QuantityStageOverlay,
    *,
    stem: Any,
) -> bool:
    """Replay every prompt binding, staged leaf, formula, and choice match."""

    if (
        type(proof) is not ScalarDerivationProof
        or type(compilation) is not NeutralizationCompilation
        or not compilation.compiled
        or not verify_compilation_source_spans(compilation, stem)
        or compilation.goal_digest_sha256 is None
        or proof.goal_digest_sha256 != compilation.goal_digest_sha256
        or proof.formula_id != FORMULA_ID
        or proof.prompt_bindings != _prompt_bindings(compilation)
    ):
        return False
    rows = _resolve_stage_rows(compilation, overlay)
    if rows is None:
        return False
    known, target, formula = rows
    if proof.formula_ast_digest_sha256 != formula.expression_digest_sha256:
        return False
    expected_stage_facts = (
        known.proof_fact,
        target.proof_fact,
        formula.proof_fact,
    )
    if proof.stage_facts != expected_stage_facts:
        return False
    evaluated = _evaluate(compilation, known, target, formula)
    if evaluated is None:
        return False
    answer, left, right = evaluated
    matches = [
        row.key
        for row in compilation.choice_items
        if row.value_liters == answer
    ]
    return (
        len(matches) == 1
        and proof.choice_key == matches[0]
        and proof.answer_liters == answer
        and proof.conservation_left == left
        and proof.conservation_right == right
    )


class ScalarQuantityResolver:
    """Resolve one compiled goal or abstain with a stable reason taxonomy."""

    def resolve(
        self,
        compilation: NeutralizationCompilation,
        overlay: QuantityStageOverlay,
        *,
        stem: Any,
    ) -> ScalarResolution:
        if (
            type(compilation) is not NeutralizationCompilation
            or not compilation.compiled
        ):
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=False,
                grounded=False,
                proof=None,
                reason="typed_goal_unavailable",
            )
        if not verify_compilation_source_spans(compilation, stem):
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=False,
                grounded=False,
                proof=None,
                reason="prompt_source_binding_invalid",
            )
        rows = _resolve_stage_rows(compilation, overlay)
        if rows is None:
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=False,
                grounded=False,
                proof=None,
                reason=(
                    "entity_or_formula_unresolved"
                    if overlay.enabled
                    else "required_evidence_unavailable"
                ),
            )
        known, target, formula = rows
        goal = compilation.goal
        if (
            goal is None
            or known.role != goal.known_role_required
            or target.role != goal.target_role_required
        ):
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=False,
                grounded=False,
                proof=None,
                reason="species_roles_invalid",
            )
        evaluated = _evaluate(compilation, known, target, formula)
        if evaluated is None:
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=True,
                grounded=False,
                proof=None,
                reason="formula_or_conservation_invalid",
            )
        answer, left, right = evaluated
        matches = [
            row.key
            for row in compilation.choice_items
            if row.value_liters == answer
        ]
        if len(matches) != 1:
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=True,
                grounded=False,
                proof=None,
                reason=(
                    "multiple_exact_choice_matches"
                    if len(matches) > 1
                    else "no_exact_choice_match"
                ),
            )
        proof = ScalarDerivationProof(
            schema_version=SCALAR_PROOF_SCHEMA,
            goal_digest_sha256=compilation.goal_digest_sha256 or "",
            formula_id=formula.rule_id,
            formula_ast_digest_sha256=formula.expression_digest_sha256,
            prompt_bindings=_prompt_bindings(compilation),
            stage_facts=(
                known.proof_fact,
                target.proof_fact,
                formula.proof_fact,
            ),
            answer_liters=answer,
            choice_key=matches[0],
            conservation_left=left,
            conservation_right=right,
        )
        verified = verify_scalar_proof(
            proof,
            compilation,
            overlay,
            stem=stem,
        )
        if not verified:
            return ScalarResolution(
                choice_key=None,
                answer_liters=None,
                raw_fired=False,
                formula_fired=True,
                grounded=False,
                proof=None,
                reason="proof_replay_failed",
            )
        return ScalarResolution(
            choice_key=matches[0],
            answer_liters=answer,
            raw_fired=True,
            formula_fired=True,
            grounded=True,
            proof=proof,
            reason="verified_exact_neutralization_derivation",
        )
