from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path

from packages.reasoning_vm.science_exam import (
    answer_exam_with_science_stage,
    answer_science_mcq,
    outcome_digest,
)
from packages.reasoning_vm.science_staging import load_science_stage


FIXTURES = Path(__file__).parent / "fixtures"
HOLDOUT = FIXTURES / "science_staging_e4_holdout_v1.json"
STAGE = FIXTURES / "science_stage_atomic_number_v1"
FROZEN_HOLDOUT_SHA256 = (
    "b0ae7a07694a40551659becba33370b3140fe7927ac846a180e87d84eb80c1b1"
)


def _fixture() -> dict:
    payload = HOLDOUT.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == FROZEN_HOLDOUT_SHA256
    return json.loads(payload)


def test_frozen_paired_e4_measures_accuracy_not_only_firing():
    fixture = _fixture()
    stage = load_science_stage(STAGE)
    base: dict[str, list[tuple[str, str, str]]] = {}

    def base_facts(subject: str):
        return list(base.get(subject, ()))

    def base_digest():
        return hashlib.sha256(
            json.dumps(
                base,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    off_correct = 0
    on_correct = 0
    off_fired = 0
    on_fired = 0
    wrong_fires = 0
    for item in fixture["paired_items"]:
        item_without_gold = {
            "question": item["question"],
            "choices": item["choices"],
        }
        off = answer_science_mcq(
            item_without_gold["question"],
            item_without_gold["choices"],
            base_facts,
            None,
            overlay_enabled=False,
            base_state_digest=base_digest,
        )
        on = answer_science_mcq(
            item_without_gold["question"],
            item_without_gold["choices"],
            base_facts,
            stage,
            overlay_enabled=True,
            base_state_digest=base_digest,
        )
        off_fired += int(off["engine"]["accepted_fire"])
        on_fired += int(on["engine"]["accepted_fire"])
        off_correct += int(off["choice_key"] == item["gold"])
        on_correct += int(on["choice_key"] == item["gold"])
        wrong_fires += int(
            on["engine"]["accepted_fire"]
            and on["choice_key"] != item["gold"]
        )

        assert off["compiler"]["compiled"] is True
        assert off["choice_key"] is None
        assert off["reason"] == "required_evidence_unavailable"
        assert on["compiler"]["input_fingerprint"] == (
            off["compiler"]["input_fingerprint"]
        )
        assert on["compiler"]["goal_digest_sha256"] == (
            off["compiler"]["goal_digest_sha256"]
        )
        assert on["choice_key"] == item["gold"]
        assert on["engine"]["accepted_fire"] is True
        assert on["staging"]["grounded_stage_leaf_count"] == 1
        assert on["staging"]["evidence_ids"] == (
            item["expected_on"]["evidence_fact_ids"]
        )
        assert on["integrity"]["base_state_unchanged"] is True
        assert on["error_kind"] is None

        replay = answer_science_mcq(
            item_without_gold["question"],
            item_without_gold["choices"],
            base_facts,
            stage,
            overlay_enabled=True,
            base_state_digest=base_digest,
        )
        assert outcome_digest(on) == outcome_digest(replay)

    n = fixture["paired_protocol"]["strict_denominator"]
    assert len(fixture["paired_items"]) == n == 15
    assert off_fired == 0
    assert on_fired == n
    assert off_correct == 0
    assert on_correct == n
    assert wrong_fires == 0


def test_frozen_negative_controls_abstain_with_declared_taxonomy():
    fixture = _fixture()
    stage = load_science_stage(STAGE)
    controls = {
        row["control_type"]: row for row in fixture["negative_controls"]
    }
    for kind, row in controls.items():
        outcome = answer_science_mcq(
            row["question"],
            row["choices"],
            lambda _subject: [],
            stage,
            overlay_enabled=True,
        )
        assert outcome["choice_key"] is None
        assert outcome["engine"]["accepted_fire"] is False
        if kind == "unsupported_surface":
            assert outcome["compiler"]["input_valid"] is True
            assert outcome["compiler"]["compiled"] is False
            assert outcome["reason"] == "unsupported_goal_family"
        elif kind == "ambiguous_duplicate_choices":
            assert outcome["compiler"]["input_valid"] is False
            assert outcome["compiler"]["compiled"] is False
            assert outcome["reason"] == "duplicate_normalized_choices"
        elif kind == "unknown_entity":
            assert outcome["compiler"]["input_valid"] is True
            assert outcome["compiler"]["compiled"] is True
            assert outcome["reason"] == "entity_unresolved"
        else:  # pragma: no cover - fixture schema guard
            raise AssertionError(f"unexpected negative control: {kind}")


def test_candidate_fails_closed_on_base_mutation_or_unattributed_duplicate():
    stage = load_science_stage(STAGE)
    question = "What is the atomic number of oxygen?"
    choices = {"A": "6", "B": "8", "C": "10", "D": "12"}

    states = iter(("a" * 64, "b" * 64))
    mutated = answer_science_mcq(
        question,
        choices,
        lambda _subject: [],
        stage,
        overlay_enabled=True,
        base_state_digest=lambda: next(states),
    )
    assert mutated["choice_key"] is None
    assert mutated["engine"]["accepted_fire"] is False
    assert mutated["reason"] == "base_state_mutated_fail_closed"
    assert mutated["error_kind"] == "BaseStateMutationDetected"

    duplicate = answer_science_mcq(
        question,
        choices,
        lambda subject: (
            [(subject, "atomic_number", "8")]
            if subject == "oxygen"
            else []
        ),
        stage,
        overlay_enabled=True,
    )
    assert duplicate["engine"]["raw_fired"] is True
    assert duplicate["engine"]["accepted_fire"] is False
    assert duplicate["choice_key"] is None
    assert duplicate["reason"] == "required_stage_provenance_unavailable"
    assert duplicate["integrity"]["base_state_unchanged"] is None


def test_exam_wrapper_never_falls_back_after_state_integrity_failure():
    stage = load_science_stage(STAGE)
    states = iter(("a" * 64, "b" * 64))
    base_calls = 0

    def base_facts(_subject):
        nonlocal base_calls
        base_calls += 1
        return []

    outcome = answer_exam_with_science_stage(
        "What is the atomic number of oxygen?",
        {"A": "6", "B": "8", "C": "10", "D": "12"},
        base_facts,
        stage,
        overlay_enabled=True,
        base_state_digest=lambda: next(states),
    )
    assert outcome["choice_key"] is None
    assert outcome["mode"] == "error"
    assert outcome["candidate_trace"]["reason"] == (
        "base_state_mutated_fail_closed"
    )
    # The two calls are DELIBERATOR propose+verify.  A fallback cascade would
    # add many more graph reads and can no longer run after the integrity fault.
    assert base_calls == 2


def test_candidate_executes_the_same_single_choice_snapshot_it_fingerprints():
    stage = load_science_stage(STAGE)

    class ChangingChoices(Mapping):
        def __init__(self):
            self.reads = 0

        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 4

        def items(self):
            self.reads += 1
            if self.reads > 1:
                raise RuntimeError("second mapping read is forbidden")
            return [
                ("A", "6"),
                ("B", "8"),
                ("C", "10"),
                ("D", "12"),
            ]

    choices = ChangingChoices()
    outcome = answer_science_mcq(
        "What is the atomic number of oxygen?",
        choices,
        lambda _subject: [],
        stage,
        overlay_enabled=True,
    )
    assert choices.reads == 1
    assert outcome["choice_key"] == "B"
    assert outcome["engine"]["accepted_fire"] is True


def test_candidate_rejects_a_proof_with_any_unprovenance_bound_leaf(
    monkeypatch,
):
    stage = load_science_stage(STAGE)

    class MixedProof:
        def leaves(self):
            return (
                ("oxygen", "atomic_number", "8"),
                ("unbound premise", "supports", "8"),
            )

        def to_dict(self):
            return {"kind": "mixed-proof", "leaves": list(self.leaves())}

    class MixedProofDeliberator:
        def __init__(self, facts_about, **_kwargs):
            self.facts_about = facts_about

        def answer_mcq_derive(self, subject, _relation, _choices):
            self.facts_about(subject)
            return {
                "choice_key": "B",
                "mode": "grounded",
                "proof": MixedProof(),
                "hops": 2,
            }

    from packages.reasoning_vm.deliberator import reasoner

    monkeypatch.setattr(reasoner, "Deliberator", MixedProofDeliberator)
    outcome = answer_science_mcq(
        "What is the atomic number of oxygen?",
        {"A": "6", "B": "8", "C": "10", "D": "12"},
        lambda _subject: [],
        stage,
        overlay_enabled=True,
    )
    assert outcome["engine"]["raw_fired"] is True
    assert outcome["engine"]["accepted_fire"] is False
    assert outcome["choice_key"] is None
    assert outcome["reason"] == "required_stage_provenance_unavailable"
    assert outcome["staging"]["grounded_leaf_count"] == 2
    assert outcome["staging"]["grounded_stage_leaf_count"] == 1
