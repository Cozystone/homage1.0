from __future__ import annotations

from packages.selfhood_control.bridges import from_voice_loop, to_atlas_route, to_tabularis_review, to_voice_response


def test_voice_bridge_creates_status_input() -> None:
    event = from_voice_loop("ATANOR, current state", "en-US")
    assert event.source == "voice_transcript"
    assert event.metadata["voice_intent"]["intent_type"] == "autonomy_status_request"


def test_tabularis_bridge_removes_raw_private_export() -> None:
    report = to_tabularis_review({"name": "Ada Lovelace", "email": "ada@example.test", "age": 34})
    assert report["raw_private_data_exported"] is False
    assert report["report"]["safe_for_cloud_brain"] is False
    assert report["sanitized"]["raw_private_data_removed"] is True


def test_atlas_bridge_never_writes_local_brain() -> None:
    route = to_atlas_route()
    assert route["safe_to_write_local_brain"] is False
    assert route["real_p2p_used"] is False
    assert route["real_cloud_upload"] is False


def test_voice_response_bridge_is_mock_and_safe() -> None:
    input_event = from_voice_loop("ATANOR, current state", "en-US")
    response = to_voice_response(input_event, "safe status")
    assert response["writes_local_brain"] is False
    assert response["writes_cloud_brain"] is False
    assert response["candidate_ingestion"] is False
