"""M2-mechanism tests for the default-off relational-object shadow lane.

These tests establish compiler precision, bounded telemetry, and isolation only.
They are not an E5 capability or benchmark-lift result.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from packages.reasoning_vm.deliberator.relational_object_compiler import (
    COMPILER_RULE,
    EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
    MAX_CHOICE_TEXT_CHARS,
    compile_explicit_relational_object_mcq,
)
from packages.reasoning_vm.deliberator.relational_object_shadow import (
    MAX_RECEIPT_BYTES,
    RelationalObjectShadowObserver,
    SHADOW_RECEIPT_SCHEMA,
)


def test_explicit_location_question_compiles_to_choice_as_object_goal():
    choices = {
        "A": "Italy",
        "B": "Greece",
        "C": "Egypt",
        "D": "Spain",
    }

    receipt = compile_explicit_relational_object_mcq(
        "Which country is Athens located in?",
        choices,
    )

    assert receipt.compiled is True
    assert receipt.schema_version == EXPLICIT_RELATIONAL_OBJECT_SCHEMA
    assert receipt.surface_family == "explicit_relational_object_mcq"
    assert receipt.goal is not None
    assert receipt.goal.subject == "Athens"
    assert receipt.goal.relation == "located_in"
    assert receipt.goal.object_source == "choice_text"
    assert receipt.goal.answer_type == "country"
    assert receipt.goal.compiler_rule == COMPILER_RULE
    assert receipt.input_fingerprint
    assert receipt.to_dict()["provenance"] == {
        "source_parser": (
            "packages.base_brain.relational_lookup:parse_relational_shape"
        ),
        "relation_semantics": (
            "packages.base_brain.relational_lookup:REL_SYNONYMS[located in]"
        ),
    }


def test_plural_named_subject_and_situated_surface_remain_narrowly_supported():
    receipt = compile_explicit_relational_object_mcq(
        "Which continent are the Alps situated in?",
        {"A": "Europe", "B": "Asia", "C": "Africa", "D": "Oceania"},
    )

    assert receipt.compiled is True
    assert receipt.goal is not None
    assert receipt.goal.subject == "Alps"
    assert receipt.goal.answer_type == "continent"
    assert receipt.goal.relation == "located_in"


@pytest.mark.parametrize(
    "stem",
    [
        "Which of the following causes rainfall?",
        "Which country is larger than France?",
        "Which country is France associated with?",
        "Which country is not France located in?",
        "Which of the following is a mammal?",
        "Why is Athens located in Greece?",
        "Which country is Athens located in, and why?",
        "Which country contains Athens?",
        "Which country is a reaction located in?",
    ],
)
def test_broad_which_causal_comparative_category_and_ambiguous_stems_abstain(stem):
    receipt = compile_explicit_relational_object_mcq(
        stem,
        {"A": "one", "B": "two", "C": "three", "D": "four"},
    )

    assert receipt.compiled is False
    assert receipt.status == "abstain"
    assert receipt.goal is None


@pytest.mark.parametrize(
    ("choices", "reason"),
    [
        ({"A": "Greece"}, "choice_count_out_of_bounds"),
        (
            {"A": "Greece", "B": "  greece  ", "C": "Italy"},
            "duplicate_choice_text",
        ),
        (
            {"A": "x" * (MAX_CHOICE_TEXT_CHARS + 1), "B": "Italy"},
            "invalid_choice_text",
        ),
        ({"A": "", "B": "Italy"}, "invalid_choice_text"),
    ],
)
def test_choice_objects_must_be_bounded_nonempty_and_unique(choices, reason):
    receipt = compile_explicit_relational_object_mcq(
        "Which country is Athens located in?",
        choices,
    )

    assert receipt.compiled is False
    assert receipt.reason == reason
    assert receipt.input_fingerprint is None


class Poison:
    def __getattribute__(self, name):
        raise AssertionError("disabled shadow lane accessed its input")


def test_shadow_is_default_off_and_cannot_change_or_even_read_live_inputs():
    observer = RelationalObjectShadowObserver()
    assert observer.enabled is False

    result = observer.observe(Poison(), Poison(), Poison())

    assert result is None
    assert observer.receipts == ()
    assert observer.coverage_telemetry["attempted"] == 0
    assert observer.firing_telemetry["engine_calls"] == 0


def test_truthy_string_cannot_enable_shadow_lane():
    with pytest.raises(TypeError, match="literal boolean"):
        RelationalObjectShadowObserver(enabled="false")


def test_shadow_reuses_choice_as_object_proof_without_mutating_inputs():
    facts = {
        "Athens": [("Athens", "located_in", "Greece")],
    }
    choices = {
        "A": "Italy",
        "B": "Greece",
        "C": "Egypt",
        "D": "Spain",
    }
    original = deepcopy(choices)
    observer = RelationalObjectShadowObserver(enabled=True)

    receipt = observer.observe(
        "Which country is Athens located in?",
        choices,
        lambda subject: facts.get(subject, []),
    )

    assert choices == original
    assert receipt is not None
    assert receipt["mode"] == "shadow"
    assert receipt["status"] == "shadow_grounded"
    assert receipt["authoritative"] is False
    assert receipt["choice_influenced"] is False
    assert receipt["action_executed"] is False
    assert receipt["firing_event"]["choice_key"] == "B"
    assert receipt["firing_event"]["grounded"] is True
    assert receipt["firing_event"]["hops"] >= 1
    assert receipt["firing_event"]["proof_digest"]
    assert "trail" not in receipt["firing_event"]

    assert observer.coverage_telemetry == {
        "schema_version": EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
        "attempted": 1,
        "compiled": 1,
        "abstained": 0,
        "compiler_errors": 0,
        "coverage_rate": 1.0,
    }
    assert observer.firing_telemetry["schema_version"] == SHADOW_RECEIPT_SCHEMA
    assert observer.firing_telemetry["engine_calls"] == 1
    assert observer.firing_telemetry["grounded_firings"] == 1
    assert observer.firing_telemetry["firing_rate"] == 1.0
    assert "accuracy" not in observer.firing_telemetry


def test_compiler_abstention_records_coverage_but_never_calls_engine():
    def should_not_run(_facts):
        raise AssertionError("unsupported surface reached the proof engine")

    observer = RelationalObjectShadowObserver(
        enabled=True,
        reasoner_factory=should_not_run,
    )

    receipt = observer.observe(
        "Which of the following causes rainfall?",
        {"A": "one", "B": "two", "C": "three", "D": "four"},
        lambda _subject: [],
    )

    assert receipt is not None
    assert receipt["status"] == "compiler_abstained"
    assert receipt["firing_event"]["engine_called"] is False
    assert observer.coverage_telemetry["attempted"] == 1
    assert observer.coverage_telemetry["compiled"] == 0
    assert observer.coverage_telemetry["abstained"] == 1
    assert observer.firing_telemetry["engine_calls"] == 0


def test_engine_exception_is_contained_and_does_not_escape_shadow_lane():
    def failing_factory(_facts):
        raise OSError("sensitive failure detail must not enter the receipt")

    observer = RelationalObjectShadowObserver(
        enabled=True,
        reasoner_factory=failing_factory,
    )

    receipt = observer.observe(
        "Which country is Athens located in?",
        {"A": "Italy", "B": "Greece", "C": "Egypt", "D": "Spain"},
        lambda _subject: [],
    )

    assert receipt is not None
    assert receipt["status"] == "engine_error"
    assert receipt["error_kind"] == "OSError"
    assert "sensitive failure detail" not in json.dumps(receipt)
    assert receipt["authoritative"] is False
    assert observer.firing_telemetry["engine_calls"] == 1
    assert observer.firing_telemetry["engine_errors"] == 1
    assert observer.firing_telemetry["grounded_firings"] == 0


def test_receipts_are_bounded_detached_and_exclude_raw_proof_trails():
    class LongTrailReasoner:
        def answer_mcq_object(self, subject, relation, choices):
            return {
                "choice_key": "B",
                "mode": "grounded",
                "hops": 2,
                "trail": "private proof material " * 10_000,
            }

    observer = RelationalObjectShadowObserver(
        enabled=True,
        reasoner_factory=lambda _facts: LongTrailReasoner(),
    )
    receipt = observer.observe(
        "Which country is Athens located in?",
        {"A": "Italy", "B": "Greece", "C": "Egypt", "D": "Spain"},
        lambda _subject: [],
    )

    assert receipt is not None
    assert len(
        json.dumps(receipt, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ) <= MAX_RECEIPT_BYTES
    assert "private proof material" not in json.dumps(receipt)

    detached = observer.receipts[0]
    detached["status"] = "tampered"
    assert observer.receipts[0]["status"] != "tampered"
