from __future__ import annotations

from packages.cloud_brain.surface_projection import SurfaceProjectionCandidate
from cgsr.cloud_surface_adapter import candidate_to_english_frame, surface_candidates_to_frames


def _candidate() -> SurfaceProjectionCandidate:
    return SurfaceProjectionCandidate(
        projection_id="spc_test",
        source_concept_ids=["c1"],
        source_relation_ids=["r1"],
        evidence_refs=["ev1"],
        language="ko",
        canonical_language="en",
        construction_family="evidence_based_claim",
        slots={"SUBJ": "GraphRAG", "OBJ": "근거 문서", "predicate": "검증하다", "evidence_ref": "ev1"},
        required_slots=["SUBJ", "OBJ", "predicate", "evidence_ref"],
        case_role_signature=["SUBJ:는:GraphRAG", "OBJ:를:근거 문서"],
        discourse_role="grounded_claim",
        semantic_constraints={"grounded_claims_only": True, "requires_evidence": True},
        confidence=0.8,
        quality_flags=[],
        safe_for_cgsr=True,
        safe_for_rhfc=True,
    )


def test_surface_candidate_becomes_english_construction_frame() -> None:
    frame = candidate_to_english_frame(_candidate())
    assert frame.frame_id == "cloud_surface_spc_test"
    assert frame.evidence_required is True
    assert "SUBJ" in frame.required_slots
    assert "evidence_ref" in frame.required_slots


def test_surface_candidates_feed_rhfc_candidate_memory() -> None:
    result = surface_candidates_to_frames([_candidate()])
    payload = result.to_dict()
    assert payload["frames_added"] == 1
    assert payload["rhfc_candidates_added"] == 1
    assert payload["false_confident"] == 0
    assert payload["forgetting_count"] == 0
    assert payload["recall_accuracy"] == 1.0
