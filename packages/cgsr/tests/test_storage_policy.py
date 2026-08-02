from __future__ import annotations

from cgsr.family_analysis import FamilyAnalysisRow
from cgsr.storage_policy import estimate_rhfc_storage_bytes, score_family_for_storage, split_storage_policy


def _row(classification: str, fixed: int, diversity: float, members: int, canonical: str = "SIMPLIFY_MARKER SLOT:NOUN 이다") -> FamilyAnalysisRow:
    return FamilyAnalysisRow(
        family_id=f"f_{classification}_{fixed}_{members}",
        classification=classification,
        canonical_form=canonical,
        member_count=members,
        reduction_contribution=max(0, members - 1),
        fixed_token_count=fixed,
        surface_diversity=diversity,
        sample_surfaces=["쉽게 말하면 X는 Y입니다", "간단히 말해 X는 Y입니다"],
        sample_examples=["쉽게 말하면 쿠버네티스는 플랫폼입니다."],
    )


def test_paraphrase_like_is_rhfc_candidate() -> None:
    decision = score_family_for_storage(_row("paraphrase_like", fixed=4, diversity=0.5, members=5))

    assert decision.destination == "rhfc_candidate"


def test_common_structure_stays_out_by_default() -> None:
    decision = score_family_for_storage(_row("common_structure", fixed=0, diversity=1.0, members=100, canonical="SLOT:NOUN SLOT:NOUN"))

    assert decision.destination == "structural_pool"


def test_singleton_specific_family_requires_review() -> None:
    decision = score_family_for_storage(
        _row("singleton", fixed=5, diversity=1.0, members=1, canonical="근거 중심 설명 SLOT:NOUN 검증")
    )

    assert decision.destination == "manual_review"


def test_recurrent_specific_valency_frame_is_rhfc_candidate() -> None:
    decision = score_family_for_storage(
        _row(
            "valency_frame",
            fixed=3,
            diversity=0.4,
            members=12,
            canonical="ADVL:에서 OBJ PREDICATE:검증하다",
        )
    )

    assert decision.destination == "rhfc_candidate"


def test_broad_topic_object_valency_frame_needs_review() -> None:
    decision = score_family_for_storage(
        _row(
            "valency_frame",
            fixed=3,
            diversity=0.4,
            members=30,
            canonical="TOPIC OBJ PREDICATE:검증하다",
        )
    )

    assert decision.destination != "rhfc_candidate"


def test_generic_valency_frame_stays_out_of_rhfc() -> None:
    decision = score_family_for_storage(
        _row(
            "valency_frame",
            fixed=3,
            diversity=0.4,
            members=30,
            canonical="TOPIC OBJ PREDICATE:하다",
        )
    )

    assert decision.destination != "rhfc_candidate"


def test_noisy_examples_keep_valency_frame_out_of_rhfc() -> None:
    row = _row(
        "valency_frame",
        fixed=3,
        diversity=0.4,
        members=12,
        canonical="ADVL:에 SUBJ PREDICATE:성립하다",
    )
    noisy_row = type(row)(
        **{
            **row.to_dict(),
            "sample_examples": ["곱셈적 함수 f,g\\colon\\mathbb Z^+\\to\\mathbb C 에 대하여 성립한다."],
        }
    )
    decision = score_family_for_storage(noisy_row)

    assert decision.destination != "rhfc_candidate"


def test_split_policy_and_storage_estimate() -> None:
    rows = [
        _row("paraphrase_like", fixed=4, diversity=0.5, members=5),
        _row("common_structure", fixed=0, diversity=1.0, members=100, canonical="SLOT:NOUN SLOT:NOUN"),
    ]
    split = split_storage_policy(rows)
    estimate = estimate_rhfc_storage_bytes(len(split["rhfc_candidates"]))

    assert split["counts"]["rhfc_candidates"] == 1
    assert estimate["bytes"] == 512
