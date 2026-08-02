"""Route-first adapter for atomic, scalar, and diagnostic relation lanes.

Routing is deliberately stem-only.  The original choices mapping is touched
only after routing has selected a lane or returned the supported
``unsupported`` classification, and it is consumed through exactly one
``items()`` call into an immutable tuple.  Execution reclassifies the frozen
stem and requires exact decision equality before entering either lane.

There is no cross-lane fallback.  Only the selected lane receives a freshly
materialized choices dictionary.  Overlay authority is derived solely from
the presence of that lane's typed snapshot in ``ScienceStageBundle``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import islice
import os
from typing import Any, Literal

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm import science_exam as atomic_exam
from packages.reasoning_vm import science_quantity_exam as scalar_exam
from packages.reasoning_vm import science_relation_exam as relation_exam
from packages.reasoning_vm.science_route import (
    ScienceRouteDecision,
    classify_science_stem,
)
from packages.reasoning_vm.science_staging import ScienceStageSnapshot
from packages.reasoning_vm.science_quantity_staging import (
    ScienceQuantityStageSnapshot,
)
from packages.reasoning_vm.deliberator.science_relation_staging import (
    ScienceRelationStageSnapshot,
)


ROUTED_SCIENCE_OUTCOME_SCHEMA = "atanor.routed-science-candidate-outcome.v2"
MIN_CHOICES = 2
MAX_CHOICES = 10
SCIENCE_BUNDLE_CONDITIONS = frozenset(
    {
        "off",
        "atomic_only",
        "scalar_only",
        "relation_only",
        "both",
        "atomic_relation",
        "scalar_relation",
        "all",
    }
)
ScienceBundleCondition = Literal[
    "off",
    "atomic_only",
    "scalar_only",
    "relation_only",
    "both",
    "atomic_relation",
    "scalar_relation",
    "all",
]
ChoiceItems = tuple[tuple[str, str], ...]


class ScienceCandidateError(RuntimeError):
    """Base class for a rejected route-first candidate request."""


class ScienceCandidateInputError(ScienceCandidateError):
    """Raised when preparation cannot produce a safe immutable input."""

    def __init__(
        self,
        message: str,
        *,
        route: ScienceRouteDecision | None,
        choice_snapshot_attempted: bool,
    ) -> None:
        super().__init__(message)
        self.route = route
        self.choice_snapshot_attempted = choice_snapshot_attempted


class ScienceCandidateContractError(ScienceCandidateError):
    """Raised by frozen boundary objects with invalid exact field types."""


def _validate_choice_items(value: Any) -> ChoiceItems:
    if (
        type(value) is not tuple
        or not MIN_CHOICES <= len(value) <= MAX_CHOICES
    ):
        raise ScienceCandidateContractError(
            "prepared choice_items must contain exactly 2..10 pairs"
        )
    seen: set[str] = set()
    normalized: list[tuple[str, str]] = []
    for index, pair in enumerate(value):
        if type(pair) is not tuple or len(pair) != 2:
            raise ScienceCandidateContractError(
                f"prepared choice_items[{index}] must be an exact pair tuple"
            )
        key, choice = pair
        if type(key) is not str or type(choice) is not str:
            raise ScienceCandidateContractError(
                f"prepared choice_items[{index}] must contain exact strings"
            )
        if not key or key in seen:
            raise ScienceCandidateContractError(
                "prepared choice keys must be non-empty and unique"
            )
        seen.add(key)
        normalized.append((key, choice))
    return tuple(normalized)


def _choices_digest(choice_items: ChoiceItems) -> str:
    return canonical_digest(
        [[key, value] for key, value in choice_items]
    )


def _validate_route_for_prepared(value: Any) -> ScienceRouteDecision:
    if type(value) is not ScienceRouteDecision:
        raise ScienceCandidateContractError(
            "prepared route must be an exact ScienceRouteDecision"
        )
    if value.status == "selected":
        if value.lane not in {"atomic", "scalar", "relation"}:
            raise ScienceCandidateContractError(
                "selected prepared route has no exact lane"
            )
    elif value.status == "unsupported":
        if value.lane is not None:
            raise ScienceCandidateContractError(
                "unsupported prepared route cannot carry a lane"
            )
    else:
        raise ScienceCandidateContractError(
            "invalid or ambiguous routes cannot become prepared inputs"
        )
    return value


@dataclass(frozen=True, slots=True)
class PreparedScienceInput:
    """Immutable route, stem, and one-shot choice snapshot."""

    route: ScienceRouteDecision
    stem: str
    choice_items: ChoiceItems
    choices_digest_sha256: str
    original_mapping_read_count: int

    def __post_init__(self) -> None:
        _validate_route_for_prepared(self.route)
        if type(self.stem) is not str:
            raise ScienceCandidateContractError(
                "prepared stem must be an exact string"
            )
        normalized = _validate_choice_items(self.choice_items)
        if normalized != self.choice_items:
            raise ScienceCandidateContractError(
                "prepared choice_items are not canonical"
            )
        if (
            type(self.choices_digest_sha256) is not str
            or self.choices_digest_sha256 != _choices_digest(normalized)
        ):
            raise ScienceCandidateContractError(
                "prepared choices digest does not derive"
            )
        if (
            type(self.original_mapping_read_count) is not int
            or self.original_mapping_read_count != 1
        ):
            raise ScienceCandidateContractError(
                "prepared original mapping read count must be exactly one"
            )

    @property
    def choices(self) -> ChoiceItems:
        """Immutable compatibility view; never the hostile source mapping."""

        return self.choice_items

    @property
    def input_digest_sha256(self) -> str:
        """Digest the exact evaluator input without benchmark metadata."""

        return canonical_digest(
            {
                "stem": self.stem,
                "choices_digest_sha256": self.choices_digest_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class ScienceStageBundle:
    """Typed snapshots for all lanes; execution passes only the selected one."""

    atomic_stage: ScienceStageSnapshot | None = None
    scalar_stage: ScienceQuantityStageSnapshot | None = None
    relation_stage: ScienceRelationStageSnapshot | None = None

    def __post_init__(self) -> None:
        _validate_stage_bundle(self)

    @property
    def condition(self) -> ScienceBundleCondition:
        present = (
            self.atomic_stage is not None,
            self.scalar_stage is not None,
            self.relation_stage is not None,
        )
        if present == (True, True, True):
            return "all"
        if present == (True, True, False):
            return "both"
        if present == (True, False, True):
            return "atomic_relation"
        if present == (False, True, True):
            return "scalar_relation"
        if present == (True, False, False):
            return "atomic_only"
        if present == (False, True, False):
            return "scalar_only"
        if present == (False, False, True):
            return "relation_only"
        return "off"


def _validate_stage_bundle(value: Any) -> ScienceStageBundle:
    if type(value) is not ScienceStageBundle:
        raise ScienceCandidateContractError(
            "stages must be an exact ScienceStageBundle"
        )
    if value.atomic_stage is not None and type(value.atomic_stage) is not (
        ScienceStageSnapshot
    ):
        raise ScienceCandidateContractError(
            "atomic_stage has an invalid snapshot type"
        )
    if value.scalar_stage is not None and type(value.scalar_stage) is not (
        ScienceQuantityStageSnapshot
    ):
        raise ScienceCandidateContractError(
            "scalar_stage has an invalid snapshot type"
        )
    if value.relation_stage is not None and type(value.relation_stage) is not (
        ScienceRelationStageSnapshot
    ):
        raise ScienceCandidateContractError(
            "relation_stage has an invalid snapshot type"
        )
    return value


def _safe_bundle_condition(value: Any) -> str | None:
    try:
        return _validate_stage_bundle(value).condition
    except (AttributeError, ScienceCandidateContractError):
        return None


def _validate_prepared_input(value: Any) -> PreparedScienceInput:
    if type(value) is not PreparedScienceInput:
        raise ScienceCandidateContractError(
            "prepared input must be an exact PreparedScienceInput"
        )
    _validate_route_for_prepared(value.route)
    if type(value.stem) is not str:
        raise ScienceCandidateContractError(
            "prepared stem must be an exact string"
        )
    choice_items = _validate_choice_items(value.choice_items)
    if (
        type(value.choices_digest_sha256) is not str
        or value.choices_digest_sha256 != _choices_digest(choice_items)
    ):
        raise ScienceCandidateContractError(
            "prepared choices digest does not derive"
        )
    if (
        type(value.original_mapping_read_count) is not int
        or value.original_mapping_read_count != 1
    ):
        raise ScienceCandidateContractError(
            "prepared original mapping read count must be exactly one"
        )
    return value


def _snapshot_choices_once(
    choices: Any,
    *,
    route: ScienceRouteDecision,
) -> ChoiceItems:
    if not isinstance(choices, Mapping):
        raise ScienceCandidateInputError(
            "choices must implement Mapping",
            route=route,
            choice_snapshot_attempted=False,
        )
    try:
        # This is the only access to the original mapping in the full request.
        # In particular, keys(), values(), iteration, len(), and __getitem__()
        # are never used.
        source_items = choices.items()
        captured = tuple(islice(source_items, MAX_CHOICES + 1))
    except Exception as exc:
        raise ScienceCandidateInputError(
            f"choices.items() snapshot failed: {type(exc).__name__}",
            route=route,
            choice_snapshot_attempted=True,
        ) from exc
    if len(captured) > MAX_CHOICES:
        raise ScienceCandidateInputError(
            "choices.items() exceeded the 10-choice bound",
            route=route,
            choice_snapshot_attempted=True,
        )
    try:
        return _validate_choice_items(captured)
    except ScienceCandidateContractError as exc:
        raise ScienceCandidateInputError(
            str(exc),
            route=route,
            choice_snapshot_attempted=True,
        ) from exc


def _submit_generic_predicate_shadow_if_enabled(
    prepared: PreparedScienceInput,
) -> None:
    """Submit the frozen input to the default-off sibling observer."""

    if os.environ.get("ATANOR_GENERIC_PREDICATE_SHADOW") != "1":
        return
    try:
        from packages.reasoning_vm.deliberator.generic_predicate_shadow import (
            submit,
        )

        submit(prepared)
    except Exception:
        # Shadow diagnostics cannot change preparation or answer semantics.
        return


def prepare_science_input(stem: Any, choices: Any) -> PreparedScienceInput:
    """Classify first, then snapshot choices once for selected/unsupported."""

    try:
        route = classify_science_stem(stem)
    except Exception as exc:
        raise ScienceCandidateInputError(
            f"science route classification failed: {type(exc).__name__}",
            route=None,
            choice_snapshot_attempted=False,
        ) from exc
    if type(route) is not ScienceRouteDecision:
        raise ScienceCandidateInputError(
            "science route returned an invalid decision type",
            route=None,
            choice_snapshot_attempted=False,
        )
    if route.status in {"invalid", "ambiguous"}:
        raise ScienceCandidateInputError(
            route.reason,
            route=route,
            choice_snapshot_attempted=False,
        )
    if route.status not in {"selected", "unsupported"}:
        raise ScienceCandidateInputError(
            "science route returned an unknown status",
            route=route,
            choice_snapshot_attempted=False,
        )
    captured = _snapshot_choices_once(choices, route=route)
    prepared = PreparedScienceInput(
        route=route,
        stem=stem,
        choice_items=captured,
        choices_digest_sha256=_choices_digest(captured),
        original_mapping_read_count=1,
    )
    _submit_generic_predicate_shadow_if_enabled(prepared)
    return prepared


def _route_telemetry(
    route: ScienceRouteDecision | None,
    *,
    revalidated: bool,
) -> dict[str, Any]:
    return {
        "decision": None if route is None else route.to_dict(),
        "revalidated": revalidated,
    }


def _condition_telemetry(
    global_bundle_condition: str | None,
    *,
    selected_lane_overlay_enabled: bool,
) -> dict[str, Any]:
    valid = (
        type(global_bundle_condition) is str
        and global_bundle_condition in SCIENCE_BUNDLE_CONDITIONS
    )
    return {
        "global_bundle_condition": (
            global_bundle_condition if valid else None
        ),
        "valid": valid,
        "selected_lane_overlay_enabled": (
            valid and selected_lane_overlay_enabled
        ),
    }


def _lane_telemetry(
    selected: str | None,
    *,
    entered: bool,
    atomic_invoked: bool,
    scalar_invoked: bool,
    relation_invoked: bool,
    selected_stage_passed: bool,
    semantic_digest: str | None,
) -> dict[str, Any]:
    return {
        "selected": selected,
        "entered": entered,
        "atomic_invoked": atomic_invoked,
        "scalar_invoked": scalar_invoked,
        "relation_invoked": relation_invoked,
        "selected_stage_passed": selected_stage_passed,
        "unselected_stage_passed": False,
        "fallback_attempted": False,
        "semantic_outcome_digest_sha256": semantic_digest,
    }


def _fail_closed_outcome(
    *,
    route: ScienceRouteDecision | None,
    prepared: PreparedScienceInput | None,
    global_bundle_condition: str | None,
    reason: str,
    error_kind: str | None,
    route_revalidated: bool,
    selected_lane_overlay_enabled: bool = False,
    original_mapping_read_count: int = 0,
    lane_entered: bool = False,
    atomic_invoked: bool = False,
    scalar_invoked: bool = False,
    relation_invoked: bool = False,
    selected_stage_passed: bool = False,
) -> dict[str, Any]:
    selected = route.lane if route is not None else None
    return {
        "schema_version": ROUTED_SCIENCE_OUTCOME_SCHEMA,
        "input_digest_sha256": (
            None if prepared is None else prepared.input_digest_sha256
        ),
        "choices_digest_sha256": (
            None if prepared is None else prepared.choices_digest_sha256
        ),
        "original_mapping_read_count": (
            prepared.original_mapping_read_count
            if prepared is not None
            else original_mapping_read_count
        ),
        "choice_key": None,
        "mode": "abstain" if error_kind is None else "error",
        "reason": reason,
        "route": _route_telemetry(
            route,
            revalidated=route_revalidated,
        ),
        "condition": _condition_telemetry(
            global_bundle_condition,
            selected_lane_overlay_enabled=(
                selected_lane_overlay_enabled
            ),
        ),
        "lane": _lane_telemetry(
            selected,
            entered=lane_entered,
            atomic_invoked=atomic_invoked,
            scalar_invoked=scalar_invoked,
            relation_invoked=relation_invoked,
            selected_stage_passed=selected_stage_passed,
            semantic_digest=None,
        ),
        "lane_outcome": None,
        "integrity": {
            "prepared_input_exact_type": (
                prepared is not None
                and type(prepared) is PreparedScienceInput
            ),
            "choice_snapshot_immutable": (
                prepared is not None
                and type(prepared.choice_items) is tuple
            ),
            "route_revalidated": route_revalidated,
            "choices_digest_bound": prepared is not None,
            "original_mapping_read_count": (
                prepared.original_mapping_read_count
                if prepared is not None
                else original_mapping_read_count
            ),
            "gold_in_candidate_payload": False,
            "benchmark_metadata_in_candidate_payload": False,
            "selected_lane_only": True,
            "unselected_stage_passed": False,
            "fallback_attempted": False,
        },
        "error_kind": error_kind,
    }


def answer_prepared_science_candidate(
    prepared: Any,
    stages: Any,
    *,
    base_facts: Callable[[str], list[tuple[str, str, str]]] | None = None,
    base_state_digest: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Revalidate the route and invoke exactly one selected existing lane."""

    if type(prepared) is not PreparedScienceInput:
        return _fail_closed_outcome(
            route=None,
            prepared=None,
            global_bundle_condition=None,
            reason="prepared_input_rejected",
            error_kind="ScienceCandidateContractError",
            route_revalidated=False,
        )
    try:
        _validate_prepared_input(prepared)
    except (AttributeError, ScienceCandidateContractError):
        return _fail_closed_outcome(
            route=(
                getattr(prepared, "route", None)
                if type(getattr(prepared, "route", None))
                is ScienceRouteDecision
                else None
            ),
            prepared=None,
            global_bundle_condition=None,
            reason="prepared_input_rejected",
            error_kind="ScienceCandidateContractError",
            route_revalidated=False,
        )

    try:
        current_route = classify_science_stem(prepared.stem)
    except Exception as exc:
        return _fail_closed_outcome(
            route=prepared.route,
            prepared=prepared,
            global_bundle_condition=None,
            reason="route_revalidation_failed",
            error_kind=type(exc).__name__,
            route_revalidated=False,
        )
    route_revalidated = (
        type(current_route) is ScienceRouteDecision
        and current_route == prepared.route
    )
    if not route_revalidated:
        return _fail_closed_outcome(
            route=prepared.route,
            prepared=prepared,
            global_bundle_condition=None,
            reason="route_revalidation_failed",
            error_kind="ScienceRouteForgeryError",
            route_revalidated=False,
        )

    try:
        stage_bundle = _validate_stage_bundle(stages)
    except (AttributeError, ScienceCandidateContractError) as exc:
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=None,
            reason="invalid_science_stage_bundle",
            error_kind=type(exc).__name__,
            route_revalidated=True,
        )
    if base_state_digest is not None and not callable(base_state_digest):
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason="invalid_base_state_digest_callback",
            error_kind="ScienceCandidateContractError",
            route_revalidated=True,
        )

    if current_route.status == "unsupported":
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason=current_route.reason,
            error_kind=None,
            route_revalidated=True,
        )
    if current_route.status != "selected" or current_route.lane not in {
        "atomic",
        "scalar",
        "relation",
    }:
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason="nonselected_route_rejected",
            error_kind="ScienceCandidateContractError",
            route_revalidated=True,
        )

    selected_stage = {
        "atomic": stage_bundle.atomic_stage,
        "scalar": stage_bundle.scalar_stage,
        "relation": stage_bundle.relation_stage,
    }[current_route.lane]
    overlay_enabled = selected_stage is not None
    if current_route.lane == "atomic" and not callable(base_facts):
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason="atomic_base_facts_missing",
            error_kind="ScienceCandidateContractError",
            route_revalidated=True,
            selected_lane_overlay_enabled=overlay_enabled,
        )

    lane_choices = dict(prepared.choice_items)
    atomic_invoked = current_route.lane == "atomic"
    scalar_invoked = current_route.lane == "scalar"
    relation_invoked = current_route.lane == "relation"
    stage_argument = selected_stage
    try:
        if current_route.lane == "atomic":
            assert base_facts is not None
            lane_outcome = atomic_exam.answer_science_mcq(
                prepared.stem,
                lane_choices,
                base_facts,
                stage_argument,
                overlay_enabled=overlay_enabled,
                base_state_digest=base_state_digest,
            )
            semantic_digest = atomic_exam.outcome_digest(lane_outcome)
        elif current_route.lane == "scalar":
            lane_outcome = scalar_exam.answer_scalar_science_mcq(
                prepared.stem,
                lane_choices,
                stage_argument,
                overlay_enabled=overlay_enabled,
                base_state_digest=base_state_digest,
            )
            semantic_digest = scalar_exam.scalar_outcome_digest(lane_outcome)
        else:
            lane_outcome = relation_exam.answer_relation_science_mcq(
                prepared.stem,
                lane_choices,
                stage_argument,
                overlay_enabled=overlay_enabled,
                base_state_digest=base_state_digest,
            )
            semantic_digest = relation_exam.relation_outcome_digest(
                lane_outcome
            )
    except Exception as exc:
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason="selected_lane_exception_fail_closed",
            error_kind=type(exc).__name__,
            route_revalidated=True,
            selected_lane_overlay_enabled=overlay_enabled,
            lane_entered=True,
            atomic_invoked=atomic_invoked,
            scalar_invoked=scalar_invoked,
            relation_invoked=relation_invoked,
            selected_stage_passed=overlay_enabled,
        )
    if not isinstance(lane_outcome, Mapping):
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason="selected_lane_outcome_invalid",
            error_kind="ScienceCandidateLaneError",
            route_revalidated=True,
            selected_lane_overlay_enabled=overlay_enabled,
            lane_entered=True,
            atomic_invoked=atomic_invoked,
            scalar_invoked=scalar_invoked,
            relation_invoked=relation_invoked,
            selected_stage_passed=overlay_enabled,
        )
    lane_integrity = lane_outcome.get("integrity")
    choice_key = lane_outcome.get("choice_key")
    benchmark_metadata_safe = (
        isinstance(lane_integrity, Mapping)
        and (
            lane_integrity.get(
                "benchmark_metadata_in_candidate_payload"
            )
            is False
            or (
                current_route.lane == "atomic"
                and "benchmark_metadata_in_candidate_payload"
                not in lane_integrity
            )
        )
    )
    lane_boundary_valid = (
        isinstance(lane_integrity, Mapping)
        and lane_integrity.get("gold_in_candidate_payload") is False
        and benchmark_metadata_safe
        and (
            choice_key is None
            or (
                type(choice_key) is str
                and choice_key in lane_choices
            )
        )
    )
    if not lane_boundary_valid:
        return _fail_closed_outcome(
            route=current_route,
            prepared=prepared,
            global_bundle_condition=stage_bundle.condition,
            reason="selected_lane_boundary_invalid",
            error_kind="ScienceCandidateLaneError",
            route_revalidated=True,
            selected_lane_overlay_enabled=overlay_enabled,
            lane_entered=True,
            atomic_invoked=atomic_invoked,
            scalar_invoked=scalar_invoked,
            relation_invoked=relation_invoked,
            selected_stage_passed=overlay_enabled,
        )

    return {
        "schema_version": ROUTED_SCIENCE_OUTCOME_SCHEMA,
        "input_digest_sha256": prepared.input_digest_sha256,
        "choices_digest_sha256": prepared.choices_digest_sha256,
        "original_mapping_read_count": (
            prepared.original_mapping_read_count
        ),
        "choice_key": lane_outcome.get("choice_key"),
        "mode": lane_outcome.get("mode"),
        "reason": lane_outcome.get("reason"),
        "route": _route_telemetry(
            current_route,
            revalidated=True,
        ),
        "condition": _condition_telemetry(
            stage_bundle.condition,
            selected_lane_overlay_enabled=overlay_enabled,
        ),
        "lane": _lane_telemetry(
            current_route.lane,
            entered=True,
            atomic_invoked=atomic_invoked,
            scalar_invoked=scalar_invoked,
            relation_invoked=relation_invoked,
            selected_stage_passed=stage_argument is not None,
            semantic_digest=semantic_digest,
        ),
        "lane_outcome": dict(lane_outcome),
        "integrity": {
            "prepared_input_exact_type": True,
            "choice_snapshot_immutable": True,
            "route_revalidated": True,
            "choices_digest_bound": True,
            "original_mapping_read_count": (
                prepared.original_mapping_read_count
            ),
            "gold_in_candidate_payload": False,
            "benchmark_metadata_in_candidate_payload": False,
            "selected_lane_only": True,
            "unselected_stage_passed": False,
            "fallback_attempted": False,
        },
        "error_kind": lane_outcome.get("error_kind"),
    }


def answer_science_candidate(
    stem: Any,
    choices: Any,
    stages: Any,
    *,
    base_facts: Callable[[str], list[tuple[str, str, str]]] | None = None,
    base_state_digest: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Full request boundary: route first, snapshot once, then one lane."""

    try:
        prepared = prepare_science_input(stem, choices)
    except ScienceCandidateInputError as exc:
        return _fail_closed_outcome(
            route=exc.route,
            prepared=None,
            global_bundle_condition=_safe_bundle_condition(stages),
            reason=(
                exc.route.reason
                if exc.route is not None
                else "science_input_preparation_failed"
            ),
            error_kind=type(exc).__name__,
            route_revalidated=False,
            original_mapping_read_count=int(
                exc.choice_snapshot_attempted
            ),
        )
    return answer_prepared_science_candidate(
        prepared,
        stages,
        base_facts=base_facts,
        base_state_digest=base_state_digest,
    )


# Clear aliases for callers that prefer "run" terminology.
run_science_candidate = answer_science_candidate
run_prepared_science_candidate = answer_prepared_science_candidate


__all__ = [
    "ChoiceItems",
    "MAX_CHOICES",
    "MIN_CHOICES",
    "PreparedScienceInput",
    "ROUTED_SCIENCE_OUTCOME_SCHEMA",
    "SCIENCE_BUNDLE_CONDITIONS",
    "ScienceCandidateContractError",
    "ScienceCandidateError",
    "ScienceCandidateInputError",
    "ScienceBundleCondition",
    "ScienceStageBundle",
    "answer_prepared_science_candidate",
    "answer_science_candidate",
    "prepare_science_input",
    "run_prepared_science_candidate",
    "run_science_candidate",
]
