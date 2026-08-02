from __future__ import annotations

import json
from pathlib import Path

from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult
from packages.cloud_brain.continuous_learning import CloudSurfaceLearningLoop
from packages.cloud_brain.surface_projection import (
    project_decompositions_to_surface,
)
from packages.cloud_brain.verified_payload_feeder import (
    PayloadSourcePolicy,
    VerifiedPayloadFeeder,
)


EVIDENCE_REF = "server-bound-evidence-0123456789"


def _candidate_shaped_decomposition() -> DecompositionResult:
    return DecompositionResult(
        concepts=[
            {"concept_id": "concept-subject"},
            {"concept_id": "concept-object"},
        ],
        relations=[{"relation_id": "relation-forged-by-caller"}],
        evidence={"source_hash": EVIDENCE_REF},
        case_frames=[
            {
                "frame_id": "frame-caller-shaped",
                "language": "en",
                "predicate": "supports",
                "source_hash": EVIDENCE_REF,
                "case_roles": [
                    {"role": "SUBJ", "marker": "nsubj", "head": "Alpha"},
                    {"role": "OBJ", "marker": "obj", "head": "Beta"},
                ],
            }
        ],
    )


def test_candidate_fields_cannot_self_mint_surface_readiness() -> None:
    result = project_decompositions_to_surface(
        [_candidate_shaped_decomposition()]
    )

    assert result.accepted_surface_candidates == 0
    assert result.rejected_surface_candidates == 1
    assert result.unsupported_claims == 1
    assert result.candidates == []


def test_independently_bound_evidence_preserves_legitimate_projection() -> None:
    result = project_decompositions_to_surface(
        [_candidate_shaped_decomposition()],
        verified_evidence_refs={EVIDENCE_REF},
    )

    assert result.accepted_surface_candidates == 1
    assert result.rejected_surface_candidates == 0
    assert result.unsupported_claims == 0
    candidate = result.candidates[0]
    assert candidate.safe_for_cgsr is True
    assert candidate.safe_for_rhfc is True
    assert candidate.confidence == 0.8


def test_learning_loop_binds_verified_source_before_surface_readiness(
    tmp_path: Path,
) -> None:
    source = tmp_path / "public-payloads.jsonl"
    source.write_text(
        json.dumps(
            {
                "source_type": "manual_public_sentence",
                "source_id": "manual:surface-authority:1",
                "text": "A graph system supports traceable public evidence.",
                "language": "en",
                "license": "CC BY-SA 4.0",
                "source_url_or_path": "manual://public/surface-authority/1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    loop = CloudSurfaceLearningLoop(
        feeder=VerifiedPayloadFeeder(
            source_paths=[source],
            policy=PayloadSourcePolicy(),
        ),
        candidate_store_root=tmp_path / "candidate",
    )

    result = loop.run_once().to_dict()

    assert result["semantic"]["payloads_accepted"] == 1
    assert result["surface"]["accepted_surface_candidates"] >= 1
    assert result["surface"]["unsupported_claims"] == 0
    assert result["candidate_ready_for_review"] is True
