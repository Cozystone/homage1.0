from __future__ import annotations

from cgsr.self_growth import (
    SelfGrowthState,
    canonicalize_growth_frame,
    dedupe_candidate_bank,
    frame_is_complete,
    make_growth_candidate,
)


def test_growth_frame_requires_case_roles_head_and_predicate() -> None:
    canonical = canonicalize_growth_frame(
        (("TOPIC", "", "GraphRAG"), ("OBJ", "", "document")),
        "verify",
    )

    assert "TOPIC" in canonical
    assert "OBJ" in canonical
    assert "HEAD:document" in canonical
    assert "PREDICATE:verify" in canonical
    assert frame_is_complete(canonical) is True
    assert frame_is_complete("TOPIC PREDICATE:verify") is False


def test_self_growth_observe_batch_never_uses_eval_rows() -> None:
    state = SelfGrowthState(min_frequency=2)
    candidate = make_growth_candidate("TOPIC OBJ HEAD:document PREDICATE:verify", 3, ["sample"])
    state.frame_counts["TOPIC OBJ HEAD:document PREDICATE:verify"] = 2
    state.examples["TOPIC OBJ HEAD:document PREDICATE:verify"] = ["sample"]

    result = state.observe_batch([], max_new=10)

    assert result["eval_rows_used_for_learning"] is False
    assert result["eligible_new_count"] == 1
    assert result["eligible_new_candidates"][0]["used_evaluation_cases"] is False
    assert result["eligible_new_candidates"][0]["row"]["canonical_form"] == candidate["row"]["canonical_form"]


def test_self_growth_accept_prevents_duplicate_absorption() -> None:
    candidate = make_growth_candidate("TOPIC OBJ HEAD:document PREDICATE:verify", 3, ["sample"])
    state = SelfGrowthState(min_frequency=2)

    assert state.accept([candidate]) == 1
    assert state.accept([candidate]) == 0


def test_dedupe_candidate_bank_by_canonical_form() -> None:
    left = make_growth_candidate("TOPIC OBJ HEAD:document PREDICATE:verify", 3, ["a"])
    right = make_growth_candidate("TOPIC OBJ HEAD:document PREDICATE:verify", 9, ["b"])

    assert len(dedupe_candidate_bank([left, right])) == 1
