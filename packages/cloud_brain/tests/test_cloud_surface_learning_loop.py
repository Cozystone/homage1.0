from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.continuous_learning import CloudSurfaceLearningLoop
from packages.cloud_brain.verified_payload_feeder import PayloadSourcePolicy, VerifiedPayloadFeeder


def _payload_file(path: Path) -> Path:

    # a relation enters the candidate store only after independent re-confirmation.
    rows = [
        {
            "source_type": "manual_public_sentence",
            "source_id": "manual:cloud-surface:1",
            "text": "GraphRAG는 근거 문서를 검증합니다.",
            "language": "ko",
            "license": "CC BY-SA 4.0",
            "source_url_or_path": "manual://public/cloud-surface/1",
        },
        {
            "source_type": "manual_public_sentence",
            "source_id": "manual:cloud-surface:2",
            "text": "GraphRAG는 답변의 근거 문서를 검증합니다.",
            "language": "ko",
            "license": "CC BY-SA 4.0",
            "source_url_or_path": "manual://public/cloud-surface/2",
        },
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def test_waiting_state_does_not_claim_learning(tmp_path: Path) -> None:
    loop = CloudSurfaceLearningLoop(
        feeder=VerifiedPayloadFeeder(source_dir=tmp_path / "none"),
        candidate_store_root=tmp_path / "candidate",
    )
    result = loop.run_once()
    payload = result.to_dict()
    assert payload["active_learning_state"] == "waiting_for_payloads"
    assert payload["cumulative_learning_seconds"] == 0
    assert payload["idle_waiting_seconds"] >= 1
    assert payload["semantic"]["payloads_accepted"] == 0
    assert payload["production_store_mutated"] is False
    assert payload["invariants"]["mock_growth"] is False


def test_verified_payload_grows_candidate_surface_and_rhfc_without_production_mutation(tmp_path: Path) -> None:
    source = _payload_file(tmp_path / "payloads.jsonl")
    loop = CloudSurfaceLearningLoop(
        feeder=VerifiedPayloadFeeder(source_paths=[source], policy=PayloadSourcePolicy()),
        candidate_store_root=tmp_path / "candidate",
    )
    result = loop.run_once()
    payload = result.to_dict()
    assert payload["active_learning_state"] == "learning"
    assert payload["semantic"]["payloads_accepted"] == 2
    assert payload["semantic"]["concepts_added"] > 0
    assert payload["semantic"]["relations_added"] > 0  # promoted via 2-source consensus
    assert payload["semantic"]["evidence_added"] == 2
    assert payload["consensus"] is not None and payload["consensus"]["promoted"] >= 1
    assert payload["semantic"]["case_frames_added"] > 0
    assert payload["surface"]["accepted_surface_candidates"] > 0
    assert payload["cgsr_rhfc"]["frames_added"] > 0
    assert payload["cgsr_rhfc"]["rhfc_candidates_added"] > 0
    assert payload["false_confident"] == 0
    assert payload["forgetting_count"] == 0
    assert payload["production_store_mutated"] is False
    assert payload["invariants"]["local_brain_write"] is False
    assert payload["invariants"]["eval_rows_used_for_learning"] is False
    assert payload["pair_edges_sent"] == 0
