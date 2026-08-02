from __future__ import annotations

from packages.cloud_brain.surface_projection import project_decompositions_to_surface
from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult


def test_surface_projection_preserves_evidence_and_case_roles() -> None:
    decomposition = DecompositionResult(
        concepts=[{"concept_id": "c1"}, {"concept_id": "c2"}],
        relations=[{"relation_id": "r1"}],
        evidence={"source_hash": "evidence_hash_1234567890"},
        case_frames=[
            {
                "frame_id": "f1",
                "language": "ko",
                "predicate": "관리하다",
                "source_hash": "evidence_hash_1234567890",
                "case_roles": [
                    {"role": "SUBJ", "marker": "는", "head": "쿠버네티스"},
                    {"role": "OBJ", "marker": "를", "head": "컨테이너"},
                ],
            }
        ],
    )
    result = project_decompositions_to_surface(
        [decomposition],
        verified_evidence_refs={"evidence_hash_1234567890"},
    )
    assert result.semantic_payloads_used == 1
    assert result.accepted_surface_candidates == 1
    assert result.rejected_surface_candidates == 0
    assert result.evidence_preservation is True
    assert result.false_confident == 0
    candidate = result.candidates[0]
    assert candidate.safe_for_cgsr is True
    assert candidate.safe_for_rhfc is True
    assert candidate.evidence_refs
    assert "SUBJ:는:쿠버네티스" in candidate.case_role_signature
