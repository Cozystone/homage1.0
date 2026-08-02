from __future__ import annotations

import pytest

from packages.splatra_imagination import build_candidate_cartridge_queue, compile_scene_choreography_commands


def _sequence():
    return compile_scene_choreography_commands({
        "stage_layout": "scene_focus",
        "layout_intent": "wide_particle_stage",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "verified_subject",
                "prompt": "verified subject from source span",
                "archetype": "creature",
                "position": [-0.4, 0.12, 0.0],
            },
            {
                "op": "move",
                "object_id": "verified_motion",
                "prompt": "verified motion from source span",
                "position": [0.1, 0.4, 0.0],
                "motion_path": {"from": [0.1, 0.4, 0.0], "to": [0.2, -0.5, 0.0], "basis": "verified_motion_phrase"},
                "physics_hint": {"basis": "verified_motion_phrase", "field": "downward_attraction", "gravity_bias": 0.7},
            },
            {
                "op": "focus_camera",
                "object_id": "verified_motion",
                "prompt": "focus verified motion",
                "camera": {"target": [0.2, -0.5, 0], "zoom": 1.3},
            },
        ],
    })


def test_candidate_cartridge_queue_is_candidate_only_and_side_channel_safe() -> None:
    sequence = _sequence()
    queue = build_candidate_cartridge_queue(sequence)

    assert queue.status == "ready_for_sidecar"
    assert queue.execution_mode == "candidate_only_dry_run"
    assert queue.side_channel == "GET /v1/cartridge"
    assert queue.job_count == len(sequence.candidate_cartridge_requests)
    assert queue.external_splatra_called is False
    assert queue.raw_buffer_in_agent_context is False
    assert queue.mutation_performed is False
    assert queue.topic_scene_templates is False
    assert queue.renderer_may_infer_topic is False
    assert queue.particle_text is False
    assert all(job.execution_mode == "candidate_only_dry_run" for job in queue.jobs)
    assert all(job.execution["execute_now"] is False for job in queue.jobs)
    assert all(job.execution["raw_buffer_in_agent_context"] is False for job in queue.jobs)
    assert all(job.quality_gates["topic_scene_templates"] is False for job in queue.jobs)
    assert all(job.quality_gates["renderer_may_infer_topic"] is False for job in queue.jobs)
    assert all(job.quality_gates["particle_text"] is False for job in queue.jobs)
    assert all(job.external_splatra_called is False for job in queue.jobs)


def test_candidate_cartridge_queue_preserves_motion_and_camera_hints() -> None:
    queue = build_candidate_cartridge_queue(_sequence())

    move_job = next(job for job in queue.jobs if job.op == "move")
    assert move_job.object_id == "verified_motion"
    assert move_job.motion_path["basis"] == "verified_motion_phrase"
    assert move_job.physics_hint["field"] == "downward_attraction"

    focus_job = next(job for job in queue.jobs if job.op == "focus_camera")
    assert focus_job.camera["zoom"] == 1.3


def test_candidate_cartridge_queue_can_build_from_dict_payload() -> None:
    sequence = _sequence().to_dict()
    queue = build_candidate_cartridge_queue(sequence)

    assert queue.source_sequence_id == sequence["sequence_id"]
    assert queue.source_plan_id == sequence["source_plan_id"]
    assert queue.job_count == len(sequence["candidate_cartridge_requests"])


def test_candidate_cartridge_queue_rejects_immediate_execution() -> None:
    sequence = _sequence().to_dict()
    sequence["candidate_cartridge_requests"][0]["execution"]["execute_now"] = True

    with pytest.raises(ValueError, match="execute immediately"):
        build_candidate_cartridge_queue(sequence)


def test_candidate_cartridge_queue_rejects_topic_template_request() -> None:
    sequence = _sequence().to_dict()
    sequence["candidate_cartridge_requests"][0]["quality_gates"]["topic_scene_templates"] = True

    with pytest.raises(ValueError, match="topic_scene_templates"):
        build_candidate_cartridge_queue(sequence)
