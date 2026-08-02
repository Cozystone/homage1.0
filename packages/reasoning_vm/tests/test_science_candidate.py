from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from packages.reasoning_vm import science_candidate as candidate
from packages.reasoning_vm import science_route
from packages.reasoning_vm.science_quantity_staging import (
    load_science_quantity_stage,
)
from packages.reasoning_vm.deliberator.science_relation_staging import (
    ScienceRelationStageSnapshot,
    load_science_relation_stage,
)
from packages.reasoning_vm.science_staging import load_science_stage


ATOMIC_STEM = "What is the atomic number of oxygen?"
SCALAR_STEM = (
    "What volume of 0.200 M NaOH is required to completely neutralize "
    "25.0 mL of 0.100 M HCl?"
)
UNSUPPORTED_STEM = "What is the boiling point of iron?"
RELATION_STEM = "Which country is Athens located in?"
ATOMIC_CHOICES = {"A": "6", "B": "8", "C": "10", "D": "12"}
SCALAR_CHOICES = {
    "A": "6.25 mL",
    "B": "12.5 mL",
    "C": "25 mL",
    "D": "50 mL",
}
RELATION_CHOICES = {
    "A": "France",
    "B": "Greece",
    "C": "Italy",
}
REPO = Path(__file__).resolve().parents[3]


class HostileChoices(Mapping[str, str]):
    """Only items() is safe; every competing mapping access is observable."""

    def __init__(self, rows: tuple[tuple[str, str], ...]) -> None:
        self.rows = rows
        self.calls = {
            "items": 0,
            "keys": 0,
            "values": 0,
            "iter": 0,
            "getitem": 0,
            "len": 0,
        }

    def items(self):
        self.calls["items"] += 1
        return self.rows

    def keys(self):
        self.calls["keys"] += 1
        raise AssertionError("keys() must not be used")

    def values(self):
        self.calls["values"] += 1
        raise AssertionError("values() must not be used")

    def __iter__(self) -> Iterator[str]:
        self.calls["iter"] += 1
        raise AssertionError("mapping iteration must not be used")

    def __getitem__(self, key: str) -> str:
        self.calls["getitem"] += 1
        raise AssertionError("__getitem__ must not be used")

    def __len__(self) -> int:
        self.calls["len"] += 1
        raise AssertionError("len(mapping) must not be used")


class InfiniteHostileChoices(HostileChoices):
    def __init__(self) -> None:
        super().__init__((("A", "seed"),))
        self.yielded = 0

    def items(self):
        self.calls["items"] += 1

        def generate():
            index = 0
            while True:
                self.yielded += 1
                yield (f"K{index}", f"choice-{index}")
                index += 1

        return generate()


def _hostile(rows: Mapping[str, str]) -> HostileChoices:
    return HostileChoices(tuple(rows.items()))


def _assert_items_only_once(value: HostileChoices) -> None:
    assert value.calls == {
        "items": 1,
        "keys": 0,
        "values": 0,
        "iter": 0,
        "getitem": 0,
        "len": 0,
    }


def _assert_choices_untouched(value: HostileChoices) -> None:
    assert value.calls == {
        "items": 0,
        "keys": 0,
        "values": 0,
        "iter": 0,
        "getitem": 0,
        "len": 0,
    }


def _synthetic_atomic_outcome() -> dict[str, Any]:
    return {
        "schema_version": "atanor.instrumented-science-outcome.v1",
        "choice_key": "B",
        "mode": "grounded",
        "reason": "synthetic_atomic",
        "compiler": {"compiled": True},
        "staging": {},
        "engine": {"accepted_fire": True},
        "integrity": {"gold_in_candidate_payload": False},
        "error_kind": None,
    }


def _synthetic_scalar_outcome() -> dict[str, Any]:
    return {
        "schema_version": "atanor.instrumented-scalar-science-outcome.v1",
        "choice_key": "B",
        "mode": "grounded",
        "reason": "synthetic_scalar",
        "compiler": {"compiled": True},
        "staging": {},
        "engine": {"accepted_fire": True},
        "integrity": {
            "gold_in_candidate_payload": False,
            "benchmark_metadata_in_candidate_payload": False,
        },
        "error_kind": None,
    }


@pytest.fixture(scope="module")
def stage_bundle() -> candidate.ScienceStageBundle:
    atomic = load_science_stage(
        REPO
        / "packages/reasoning_vm/tests/fixtures/"
        "science_stage_atomic_number_v1"
    )
    scalar = load_science_quantity_stage(
        REPO
        / "packages/reasoning_vm/tests/fixtures/"
        "science_stage_scalar_quantity_v1"
    )
    return candidate.ScienceStageBundle(
        atomic_stage=atomic,
        scalar_stage=scalar,
    )


@pytest.fixture(scope="module")
def relation_stage() -> ScienceRelationStageSnapshot:
    return load_science_relation_stage(
        REPO
        / "packages/reasoning_vm/tests/fixtures/"
        "science_stage_typed_relation_v1"
    )


def test_boundary_objects_are_frozen_slotted_and_exact() -> None:
    prepared = candidate.prepare_science_input(ATOMIC_STEM, ATOMIC_CHOICES)
    stages = candidate.ScienceStageBundle()

    assert type(prepared) is candidate.PreparedScienceInput
    assert type(prepared.choice_items) is tuple
    assert all(type(pair) is tuple for pair in prepared.choice_items)
    assert prepared.choices is prepared.choice_items
    assert prepared.choices_digest_sha256 == candidate._choices_digest(
        prepared.choice_items
    )
    assert prepared.original_mapping_read_count == 1
    assert not hasattr(prepared, "__dict__")
    assert not hasattr(stages, "__dict__")
    with pytest.raises(FrozenInstanceError):
        prepared.stem = SCALAR_STEM  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        stages.atomic_stage = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        candidate.PreparedScienceInput(
            route=prepared.route,
            stem=prepared.stem,
            choice_items=prepared.choice_items,
            choices_digest_sha256=prepared.choices_digest_sha256,
            original_mapping_read_count=1,
            gold="B",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("stem", "choices", "status", "lane"),
    (
        (ATOMIC_STEM, ATOMIC_CHOICES, "selected", "atomic"),
        (SCALAR_STEM, SCALAR_CHOICES, "selected", "scalar"),
        (RELATION_STEM, RELATION_CHOICES, "selected", "relation"),
        (UNSUPPORTED_STEM, ATOMIC_CHOICES, "unsupported", None),
    ),
)
def test_prepare_routes_first_then_snapshots_items_exactly_once(
    stem: str,
    choices: Mapping[str, str],
    status: str,
    lane: str | None,
) -> None:
    hostile = _hostile(choices)
    prepared = candidate.prepare_science_input(stem, hostile)

    assert prepared.route.status == status
    assert prepared.route.lane == lane
    assert prepared.stem == stem
    assert prepared.choice_items == tuple(choices.items())
    assert prepared.choices_digest_sha256 == candidate._choices_digest(
        prepared.choice_items
    )
    assert prepared.original_mapping_read_count == 1
    assert len(prepared.input_digest_sha256) == 64
    _assert_items_only_once(hostile)

    hostile.rows = (("A", "mutated after snapshot"),)
    assert prepared.choice_items == tuple(choices.items())


def test_choice_snapshot_is_bounded_to_exactly_two_through_ten() -> None:
    one = HostileChoices((("A", "only"),))
    with pytest.raises(
        candidate.ScienceCandidateInputError,
        match="exactly 2..10",
    ):
        candidate.prepare_science_input(ATOMIC_STEM, one)
    _assert_items_only_once(one)

    ten = HostileChoices(
        tuple((f"K{index}", f"choice-{index}") for index in range(10))
    )
    prepared = candidate.prepare_science_input(ATOMIC_STEM, ten)
    assert len(prepared.choice_items) == 10
    _assert_items_only_once(ten)

    infinite = InfiniteHostileChoices()
    with pytest.raises(
        candidate.ScienceCandidateInputError,
        match="exceeded the 10-choice bound",
    ) as raised:
        candidate.prepare_science_input(ATOMIC_STEM, infinite)
    assert raised.value.choice_snapshot_attempted is True
    assert infinite.yielded == 11
    _assert_items_only_once(infinite)


def test_invalid_route_never_touches_choices() -> None:
    hostile = _hostile(ATOMIC_CHOICES)
    with pytest.raises(
        candidate.ScienceCandidateInputError,
        match="stem_not_string",
    ) as raised:
        candidate.prepare_science_input(None, hostile)
    assert raised.value.route is not None
    assert raised.value.route.status == "invalid"
    assert raised.value.choice_snapshot_attempted is False
    _assert_choices_untouched(hostile)

    outcome = candidate.answer_science_candidate(
        None,
        hostile,
        candidate.ScienceStageBundle(),
    )
    assert outcome["mode"] == "error"
    assert outcome["lane"]["entered"] is False
    assert outcome["input_digest_sha256"] is None
    assert outcome["choices_digest_sha256"] is None
    assert outcome["original_mapping_read_count"] == 0
    _assert_choices_untouched(hostile)


def test_ambiguous_route_never_touches_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambiguous = science_route._reduce_profile_matches(
        ATOMIC_STEM,
        ("atomic", "scalar"),
    )
    assert ambiguous.status == "ambiguous"
    monkeypatch.setattr(
        candidate,
        "classify_science_stem",
        lambda stem: ambiguous,
    )
    hostile = _hostile(ATOMIC_CHOICES)

    with pytest.raises(
        candidate.ScienceCandidateInputError,
        match="ambiguous_science_profile",
    ):
        candidate.prepare_science_input(ATOMIC_STEM, hostile)
    _assert_choices_untouched(hostile)

    outcome = candidate.answer_science_candidate(
        ATOMIC_STEM,
        hostile,
        candidate.ScienceStageBundle(),
    )
    assert outcome["route"]["decision"]["status"] == "ambiguous"
    assert outcome["lane"]["entered"] is False
    _assert_choices_untouched(hostile)


def test_full_selected_request_classifies_twice_but_snapshots_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = science_route.classify_science_stem
    stems: list[Any] = []

    def observed(stem: Any):
        stems.append(stem)
        return original(stem)

    monkeypatch.setattr(candidate, "classify_science_stem", observed)
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: _synthetic_atomic_outcome(),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("unselected scalar lane entered"),
    )
    hostile = _hostile(ATOMIC_CHOICES)

    outcome = candidate.answer_science_candidate(
        ATOMIC_STEM,
        hostile,
        candidate.ScienceStageBundle(),
        base_facts=lambda subject: [],
    )
    assert stems == [ATOMIC_STEM, ATOMIC_STEM]
    _assert_items_only_once(hostile)
    assert outcome["route"]["revalidated"] is True
    assert outcome["lane"]["selected"] == "atomic"
    assert outcome["lane"]["atomic_invoked"] is True
    assert outcome["lane"]["scalar_invoked"] is False


def test_unsupported_snapshots_for_digest_without_entering_a_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: pytest.fail("atomic lane entered"),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("scalar lane entered"),
    )
    hostile = _hostile(ATOMIC_CHOICES)
    outcome = candidate.answer_science_candidate(
        UNSUPPORTED_STEM,
        hostile,
        candidate.ScienceStageBundle(),
    )

    _assert_items_only_once(hostile)
    assert outcome["input_digest_sha256"] is not None
    assert outcome["choices_digest_sha256"] is not None
    assert outcome["original_mapping_read_count"] == 1
    assert outcome["mode"] == "abstain"
    assert outcome["reason"] == "unsupported_science_profile"
    assert outcome["route"]["revalidated"] is True
    assert outcome["lane"] == {
        "selected": None,
        "entered": False,
            "atomic_invoked": False,
            "scalar_invoked": False,
            "relation_invoked": False,
        "selected_stage_passed": False,
        "unselected_stage_passed": False,
        "fallback_attempted": False,
        "semantic_outcome_digest_sha256": None,
    }


def test_forged_route_is_rejected_before_either_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    atomic_prepared = candidate.prepare_science_input(
        ATOMIC_STEM,
        ATOMIC_CHOICES,
    )
    scalar_route = science_route.classify_science_stem(SCALAR_STEM)
    forged = candidate.PreparedScienceInput(
        route=scalar_route,
        stem=atomic_prepared.stem,
        choice_items=atomic_prepared.choice_items,
        choices_digest_sha256=atomic_prepared.choices_digest_sha256,
        original_mapping_read_count=1,
    )
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: pytest.fail("atomic lane entered"),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("scalar lane entered"),
    )

    outcome = candidate.answer_prepared_science_candidate(
        forged,
        candidate.ScienceStageBundle(),
    )
    assert outcome["reason"] == "route_revalidation_failed"
    assert outcome["error_kind"] == "ScienceRouteForgeryError"
    assert outcome["route"]["revalidated"] is False
    assert outcome["lane"]["entered"] is False


@pytest.mark.parametrize(
    ("field", "forged_value"),
    (
        ("choices_digest_sha256", "0" * 64),
        ("original_mapping_read_count", 2),
    ),
)
def test_forged_prepared_receipt_fields_are_rejected_before_lane(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    forged_value: Any,
) -> None:
    prepared = candidate.prepare_science_input(
        ATOMIC_STEM,
        ATOMIC_CHOICES,
    )
    object.__setattr__(prepared, field, forged_value)
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: pytest.fail("atomic lane entered"),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("scalar lane entered"),
    )

    outcome = candidate.answer_prepared_science_candidate(
        prepared,
        candidate.ScienceStageBundle(),
        base_facts=lambda subject: [],
    )
    assert outcome["reason"] == "prepared_input_rejected"
    assert outcome["lane"]["entered"] is False
    assert outcome["error_kind"] == "ScienceCandidateContractError"


def test_atomic_on_passes_only_atomic_stage_and_preserves_digest(
    monkeypatch: pytest.MonkeyPatch,
    stage_bundle: candidate.ScienceStageBundle,
) -> None:
    captured: dict[str, Any] = {}
    lane_outcome = _synthetic_atomic_outcome()

    def atomic_lane(stem, choices, base_facts, stage, **kwargs):
        captured.update(
            stem=stem,
            choices=choices,
            base_facts=base_facts,
            stage=stage,
            kwargs=kwargs,
        )
        return lane_outcome

    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        atomic_lane,
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("unselected scalar lane entered"),
    )
    base_facts = lambda subject: []
    prepared = candidate.prepare_science_input(ATOMIC_STEM, ATOMIC_CHOICES)
    outcome = candidate.answer_prepared_science_candidate(
        prepared,
        stage_bundle,
        base_facts=base_facts,
    )

    assert captured["stem"] == ATOMIC_STEM
    assert captured["choices"] == ATOMIC_CHOICES
    assert captured["base_facts"] is base_facts
    assert captured["stage"] is stage_bundle.atomic_stage
    assert captured["kwargs"]["overlay_enabled"] is True
    assert outcome["lane_outcome"] == lane_outcome
    assert outcome["lane"]["selected"] == "atomic"
    assert outcome["lane"]["atomic_invoked"] is True
    assert outcome["lane"]["scalar_invoked"] is False
    assert outcome["lane"]["selected_stage_passed"] is True
    assert outcome["lane"]["unselected_stage_passed"] is False
    assert outcome["lane"]["semantic_outcome_digest_sha256"] == (
        candidate.atomic_exam.outcome_digest(lane_outcome)
    )
    assert outcome["choices_digest_sha256"] == (
        prepared.choices_digest_sha256
    )
    assert outcome["original_mapping_read_count"] == 1
    assert outcome["condition"] == {
        "global_bundle_condition": "both",
        "valid": True,
        "selected_lane_overlay_enabled": True,
    }


def test_scalar_on_passes_only_scalar_stage_and_preserves_digest(
    monkeypatch: pytest.MonkeyPatch,
    stage_bundle: candidate.ScienceStageBundle,
) -> None:
    captured: dict[str, Any] = {}
    lane_outcome = _synthetic_scalar_outcome()

    def scalar_lane(stem, choices, stage, **kwargs):
        captured.update(
            stem=stem,
            choices=choices,
            stage=stage,
            kwargs=kwargs,
        )
        return lane_outcome

    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: pytest.fail("unselected atomic lane entered"),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        scalar_lane,
    )
    prepared = candidate.prepare_science_input(SCALAR_STEM, SCALAR_CHOICES)
    outcome = candidate.answer_prepared_science_candidate(
        prepared,
        stage_bundle,
        base_facts=lambda subject: pytest.fail(
            "base_facts must not enter scalar lane"
        ),
    )

    assert captured["stem"] == SCALAR_STEM
    assert captured["choices"] == SCALAR_CHOICES
    assert captured["stage"] is stage_bundle.scalar_stage
    assert captured["kwargs"]["overlay_enabled"] is True
    assert outcome["lane_outcome"] == lane_outcome
    assert outcome["lane"]["selected"] == "scalar"
    assert outcome["lane"]["atomic_invoked"] is False
    assert outcome["lane"]["scalar_invoked"] is True
    assert outcome["lane"]["selected_stage_passed"] is True
    assert outcome["lane"]["unselected_stage_passed"] is False
    assert outcome["lane"]["semantic_outcome_digest_sha256"] == (
        candidate.scalar_exam.scalar_outcome_digest(lane_outcome)
    )
    assert outcome["choices_digest_sha256"] == (
        prepared.choices_digest_sha256
    )
    assert outcome["original_mapping_read_count"] == 1
    assert outcome["condition"] == {
        "global_bundle_condition": "both",
        "valid": True,
        "selected_lane_overlay_enabled": True,
    }


@pytest.mark.parametrize(
    ("stem", "choices", "lane", "global_condition"),
    (
        (
            ATOMIC_STEM,
            ATOMIC_CHOICES,
            "atomic",
            "scalar_only",
        ),
        (
            SCALAR_STEM,
            SCALAR_CHOICES,
            "scalar",
            "atomic_only",
        ),
    ),
)
def test_unselected_only_bundle_keeps_selected_lane_effectively_off(
    monkeypatch: pytest.MonkeyPatch,
    stage_bundle: candidate.ScienceStageBundle,
    stem: str,
    choices: Mapping[str, str],
    lane: str,
    global_condition: str,
) -> None:
    captured: dict[str, Any] = {}

    def atomic_lane(stem, choices, base_facts, stage, **kwargs):
        captured.update(stage=stage, kwargs=kwargs)
        return _synthetic_atomic_outcome()

    def scalar_lane(stem, choices, stage, **kwargs):
        captured.update(stage=stage, kwargs=kwargs)
        return _synthetic_scalar_outcome()

    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        atomic_lane,
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        scalar_lane,
    )
    effective_bundle = (
        candidate.ScienceStageBundle(
            scalar_stage=stage_bundle.scalar_stage
        )
        if lane == "atomic"
        else candidate.ScienceStageBundle(
            atomic_stage=stage_bundle.atomic_stage
        )
    )
    outcome = candidate.answer_science_candidate(
        stem,
        choices,
        effective_bundle,
        base_facts=lambda subject: [],
    )

    assert outcome["lane"]["selected"] == lane
    assert captured["stage"] is None
    assert captured["kwargs"]["overlay_enabled"] is False
    assert outcome["lane"]["selected_stage_passed"] is False
    assert outcome["condition"] == {
        "global_bundle_condition": global_condition,
        "valid": True,
        "selected_lane_overlay_enabled": False,
    }


def test_invalid_stage_and_atomic_base_fail_before_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"atomic": 0, "scalar": 0}

    def atomic_lane(*args, **kwargs):
        calls["atomic"] += 1
        return _synthetic_atomic_outcome()

    def scalar_lane(*args, **kwargs):
        calls["scalar"] += 1
        return _synthetic_scalar_outcome()

    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        atomic_lane,
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        scalar_lane,
    )

    atomic = candidate.prepare_science_input(ATOMIC_STEM, ATOMIC_CHOICES)
    missing_base = candidate.answer_prepared_science_candidate(
        atomic,
        candidate.ScienceStageBundle(),
    )
    assert missing_base["reason"] == "atomic_base_facts_missing"
    assert missing_base["lane"]["entered"] is False

    forged_bundle = object.__new__(candidate.ScienceStageBundle)
    object.__setattr__(forged_bundle, "atomic_stage", object())
    object.__setattr__(forged_bundle, "scalar_stage", None)
    invalid_stage = candidate.answer_prepared_science_candidate(
        atomic,
        forged_bundle,
        base_facts=lambda subject: [],
    )
    assert invalid_stage["reason"] == "invalid_science_stage_bundle"
    assert invalid_stage["lane"]["entered"] is False
    assert calls == {"atomic": 0, "scalar": 0}

    with pytest.raises(
        candidate.ScienceCandidateContractError,
        match="invalid snapshot type",
    ):
        candidate.ScienceStageBundle(atomic_stage=object())  # type: ignore[arg-type]


def test_bundle_presence_is_the_only_condition_authority(
    stage_bundle: candidate.ScienceStageBundle,
) -> None:
    assert candidate.ScienceStageBundle().condition == "off"
    assert candidate.ScienceStageBundle(
        atomic_stage=stage_bundle.atomic_stage
    ).condition == "atomic_only"
    assert candidate.ScienceStageBundle(
        scalar_stage=stage_bundle.scalar_stage
    ).condition == "scalar_only"
    assert stage_bundle.condition == "both"

    with pytest.raises(TypeError):
        candidate.answer_science_candidate(
            ATOMIC_STEM,
            ATOMIC_CHOICES,
            candidate.ScienceStageBundle(),
            condition="off",  # type: ignore[call-arg]
            base_facts=lambda subject: [],
        )


def test_selected_lane_exception_fails_closed_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"atomic": 0, "scalar": 0}

    def atomic_lane(*args, **kwargs):
        calls["atomic"] += 1
        raise RuntimeError("synthetic failure")

    def scalar_lane(*args, **kwargs):
        calls["scalar"] += 1
        return _synthetic_scalar_outcome()

    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        atomic_lane,
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        scalar_lane,
    )
    outcome = candidate.answer_science_candidate(
        ATOMIC_STEM,
        ATOMIC_CHOICES,
        candidate.ScienceStageBundle(),
        base_facts=lambda subject: [],
    )

    assert calls == {"atomic": 1, "scalar": 0}
    assert outcome["mode"] == "error"
    assert outcome["reason"] == "selected_lane_exception_fail_closed"
    assert outcome["error_kind"] == "RuntimeError"
    assert outcome["lane"]["entered"] is True
    assert outcome["lane"]["fallback_attempted"] is False
    assert outcome["integrity"]["fallback_attempted"] is False


def test_selected_lane_cannot_report_gold_in_candidate_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane_outcome = _synthetic_atomic_outcome()
    lane_outcome["integrity"]["gold_in_candidate_payload"] = True
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: lane_outcome,
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("fallback lane entered"),
    )
    outcome = candidate.answer_science_candidate(
        ATOMIC_STEM,
        ATOMIC_CHOICES,
        candidate.ScienceStageBundle(),
        base_facts=lambda subject: [],
    )
    assert outcome["reason"] == "selected_lane_boundary_invalid"
    assert outcome["error_kind"] == "ScienceCandidateLaneError"
    assert outcome["lane"]["entered"] is True
    assert outcome["lane"]["fallback_attempted"] is False
    assert outcome["lane_outcome"] is None


def test_atomic_lane_cannot_report_benchmark_metadata_in_candidate_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane_outcome = _synthetic_atomic_outcome()
    lane_outcome["integrity"][
        "benchmark_metadata_in_candidate_payload"
    ] = True
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: lane_outcome,
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("fallback lane entered"),
    )

    outcome = candidate.answer_science_candidate(
        ATOMIC_STEM,
        ATOMIC_CHOICES,
        candidate.ScienceStageBundle(),
        base_facts=lambda subject: [],
    )

    assert outcome["reason"] == "selected_lane_boundary_invalid"
    assert outcome["error_kind"] == "ScienceCandidateLaneError"
    assert outcome["lane"]["entered"] is True
    assert outcome["lane"]["fallback_attempted"] is False
    assert outcome["lane_outcome"] is None


def test_prepared_or_candidate_gold_and_extra_fields_are_rejected() -> None:
    prepared = candidate.prepare_science_input(ATOMIC_STEM, ATOMIC_CHOICES)
    forged_mapping = {
        "route": prepared.route,
        "stem": prepared.stem,
        "choice_items": prepared.choice_items,
        "gold": "B",
    }
    outcome = candidate.answer_prepared_science_candidate(
        forged_mapping,
        candidate.ScienceStageBundle(),
        base_facts=lambda subject: [],
    )
    assert outcome["reason"] == "prepared_input_rejected"
    assert outcome["lane"]["entered"] is False
    assert outcome["integrity"]["gold_in_candidate_payload"] is False

    with pytest.raises(TypeError):
        candidate.answer_science_candidate(
            ATOMIC_STEM,
            ATOMIC_CHOICES,
            candidate.ScienceStageBundle(),
            base_facts=lambda subject: [],
            gold="B",  # type: ignore[call-arg]
        )


def test_relation_lane_receives_only_relation_stage_and_exact_p17_proof(
    monkeypatch: pytest.MonkeyPatch,
    relation_stage: ScienceRelationStageSnapshot,
) -> None:
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: pytest.fail("atomic lane entered"),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("scalar lane entered"),
    )
    hostile = _hostile(RELATION_CHOICES)
    outcome = candidate.answer_science_candidate(
        RELATION_STEM,
        hostile,
        candidate.ScienceStageBundle(relation_stage=relation_stage),
        base_state_digest=lambda: "sentinel",
    )

    _assert_items_only_once(hostile)
    assert outcome["choice_key"] == "B"
    assert outcome["mode"] == "grounded"
    assert outcome["route"]["revalidated"] is True
    assert outcome["condition"] == {
        "global_bundle_condition": "relation_only",
        "valid": True,
        "selected_lane_overlay_enabled": True,
    }
    assert outcome["lane"]["selected"] == "relation"
    assert outcome["lane"]["atomic_invoked"] is False
    assert outcome["lane"]["scalar_invoked"] is False
    assert outcome["lane"]["relation_invoked"] is True
    assert outcome["lane"]["selected_stage_passed"] is True
    assert outcome["lane_outcome"]["staging"]["source_property_id"] == "P17"
    assert outcome["lane_outcome"]["integrity"]["choice_ranking_used"] is False
    assert outcome["lane"]["semantic_outcome_digest_sha256"] == (
        candidate.relation_exam.relation_outcome_digest(
            outcome["lane_outcome"]
        )
    )


def test_relation_lane_off_abstains_without_cross_lane_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        candidate.atomic_exam,
        "answer_science_mcq",
        lambda *args, **kwargs: pytest.fail("atomic lane entered"),
    )
    monkeypatch.setattr(
        candidate.scalar_exam,
        "answer_scalar_science_mcq",
        lambda *args, **kwargs: pytest.fail("scalar lane entered"),
    )
    outcome = candidate.answer_science_candidate(
        RELATION_STEM,
        RELATION_CHOICES,
        candidate.ScienceStageBundle(),
    )

    assert outcome["choice_key"] is None
    assert outcome["mode"] == "abstain"
    assert outcome["reason"] == "required_relation_stage_unavailable"
    assert outcome["lane"]["selected"] == "relation"
    assert outcome["lane"]["relation_invoked"] is True
    assert outcome["lane"]["selected_stage_passed"] is False
    assert outcome["lane"]["fallback_attempted"] is False
    assert outcome["condition"]["global_bundle_condition"] == "off"


def test_real_atomic_and_scalar_lanes_keep_native_semantic_digests(
    stage_bundle: candidate.ScienceStageBundle,
) -> None:
    atomic = candidate.answer_science_candidate(
        ATOMIC_STEM,
        ATOMIC_CHOICES,
        stage_bundle,
        base_facts=lambda subject: [],
        base_state_digest=lambda: "sentinel",
    )
    scalar = candidate.answer_science_candidate(
        SCALAR_STEM,
        SCALAR_CHOICES,
        stage_bundle,
        base_state_digest=lambda: "sentinel",
    )

    assert atomic["lane"]["selected"] == "atomic"
    assert atomic["lane"]["semantic_outcome_digest_sha256"] == (
        candidate.atomic_exam.outcome_digest(atomic["lane_outcome"])
    )
    assert scalar["lane"]["selected"] == "scalar"
    assert scalar["lane"]["semantic_outcome_digest_sha256"] == (
        candidate.scalar_exam.scalar_outcome_digest(scalar["lane_outcome"])
    )
    for outcome in (atomic, scalar):
        assert outcome["route"]["revalidated"] is True
        assert outcome["condition"]["global_bundle_condition"] == "both"
        assert (
            outcome["condition"]["selected_lane_overlay_enabled"] is True
        )
        assert outcome["lane"]["entered"] is True
        assert outcome["lane"]["fallback_attempted"] is False
        assert outcome["integrity"]["selected_lane_only"] is True
        assert outcome["integrity"]["unselected_stage_passed"] is False
