from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from packages.reasoning_vm.science_quantity_exam import (
    answer_scalar_science_mcq,
    scalar_outcome_digest,
)
from packages.reasoning_vm.science_quantity_staging import (
    load_science_quantity_stage,
)


FIXTURES = Path(__file__).parent / "fixtures"
HOLDOUT = FIXTURES / "science_scalar_neutralization_e4_v1.json"
STAGE = FIXTURES / "science_stage_scalar_quantity_v1"
FROZEN_HOLDOUT_SHA256 = (
    "725c1073eac795c63113a5c63c1a3facf40c9e5739d7f7a1d99de31f53def34f"
)


def _fixture() -> dict:
    payload = HOLDOUT.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == FROZEN_HOLDOUT_SHA256
    return json.loads(payload)


def test_scalar_neutralization_fixture_hash_and_denominator_are_frozen():
    fixture = _fixture()

    assert fixture["paired_protocol"]["fixed_denominator"] == 12
    assert fixture["paired_protocol"]["semantic_group_count"] == 6
    assert len(fixture["paired_items"]) == 12
    assert len(fixture["semantic_groups"]) == 6
    assert len(fixture["negative_controls"]) == 6
    assert fixture["authorship"] == {
        "independently_written": True,
        "public_benchmark_question_copied": False,
        "public_benchmark_choices_copied": False,
        "external_authenticity_established": False,
    }


def test_scalar_neutralization_paired_off_on_measures_accuracy():
    fixture = _fixture()
    stage = load_science_quantity_stage(STAGE)
    off_correct = on_correct = 0
    off_fired = on_fired = wrong_fires = 0

    for ordinal, item in enumerate(fixture["paired_items"]):
        def run(condition: str):
            return answer_scalar_science_mcq(
                item["question"],
                item["choices"],
                stage if condition == "on" else None,
                overlay_enabled=condition == "on",
            )

        primary_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        replay_order = list(reversed(primary_order))
        primary = {
            condition: run(condition) for condition in primary_order
        }
        replay = {
            condition: run(condition) for condition in replay_order
        }
        off = primary["off"]
        on = primary["on"]
        off_correct += int(off["choice_key"] == item["gold"])
        on_correct += int(on["choice_key"] == item["gold"])
        off_fired += int(off["engine"]["accepted_fire"])
        on_fired += int(on["engine"]["accepted_fire"])
        wrong_fires += int(
            on["engine"]["accepted_fire"]
            and on["choice_key"] != item["gold"]
        )

        assert off["compiler"]["compiled"] is True
        assert off["reason"] == "required_evidence_unavailable"
        assert off["integrity"]["stage_structurally_absent"] is True
        assert on["compiler"]["input_fingerprint"] == (
            off["compiler"]["input_fingerprint"]
        )
        assert on["compiler"]["goal_digest_sha256"] == (
            off["compiler"]["goal_digest_sha256"]
        )
        assert on["choice_key"] == item["gold"]
        assert on["engine"]["formula_fired"] is True
        assert on["engine"]["accepted_fire"] is True
        assert on["staging"]["grounded_leaf_count"] == 3
        assert on["staging"]["grounded_stage_leaf_count"] == 3
        assert len(on["staging"]["evidence_ids"]) == 3
        assert on["staging"]["external_authenticity_established"] is False

        assert scalar_outcome_digest(off) == scalar_outcome_digest(
            replay["off"]
        )
        assert scalar_outcome_digest(on) == scalar_outcome_digest(
            replay["on"]
        )

    assert off_fired == 0
    assert on_fired == 12
    assert off_correct == 0
    assert on_correct == 12
    assert wrong_fires == 0


def test_scalar_neutralization_six_metamorphic_relations_hold():
    fixture = _fixture()
    by_id = {row["id"]: row for row in fixture["paired_items"]}
    expected_relation = {
        "g1": lambda left, right: left == right,
        "g2": lambda left, right: right == 2 * left,
        "g3": lambda left, right: right * 2 == left,
        "g4": lambda left, right: left == right,
        "g5": lambda left, right: left == right,
        "g6": lambda left, right: right == 2 * left,
    }

    for group in fixture["semantic_groups"]:
        left_row, right_row = (
            by_id[item_id] for item_id in group["item_ids"]
        )
        left = Fraction(left_row["expected_answer_liters"])
        right = Fraction(right_row["expected_answer_liters"])
        assert expected_relation[group["group_id"]](left, right)


def test_scalar_neutralization_gold_positions_are_balanced():
    fixture = _fixture()
    assert Counter(
        row["gold"] for row in fixture["paired_items"]
    ) == Counter({"A": 3, "B": 3, "C": 3, "D": 3})


def test_scalar_neutralization_negative_controls_match_taxonomy():
    fixture = _fixture()
    stage = load_science_quantity_stage(STAGE)

    for row in fixture["negative_controls"]:
        off = answer_scalar_science_mcq(
            row["question"],
            row["choices"],
            None,
            overlay_enabled=False,
        )
        on = answer_scalar_science_mcq(
            row["question"],
            row["choices"],
            stage,
            overlay_enabled=True,
        )
        assert off["compiler"]["status"] == row["expected_status"]
        assert on["compiler"]["status"] == row["expected_status"]
        assert off["engine"]["accepted_fire"] is False
        assert on["engine"]["accepted_fire"] is False
        if row["expected_status"] == "compiled":
            assert off["reason"] == row["expected_reason_off"]
            assert on["reason"] == row["expected_reason_on"]
        else:
            assert off["reason"] == row["expected_reason"]
            assert on["reason"] == row["expected_reason"]
