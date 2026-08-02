from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agentic_micro_os as agentic_micro_os
from app.routers.agentic_micro_os import router
from packages.splatra_imagination import SplatraSidecarDispatchResult, SplatraSidecarJobResult


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_imagination_status_is_proof_only() -> None:
    payload = _client().get("/api/agentic-os/splatra/imagination/status").json()

    assert payload["available"] is True
    assert payload["proof_only"] is True
    assert payload["is_verified_knowledge"] is False
    assert payload["external_llm"] is False
    assert payload["image_model_used"] is False
    assert "orb" in payload["archetypes"]
    assert payload["visible_object"] is True
    assert payload["product_visible"] is True
    assert payload["clear_radius"] == 0.34


def test_imagination_generate_returns_particles_and_safety_flags() -> None:
    payload = _client().post(
        "/api/agentic-os/splatra/imagination/generate",
        json={"seed_id": "api_test", "archetype": "machine_core", "particle_budget": 300},
    ).json()
    frame = payload["frame"]
    item = frame["objects"][0]

    assert payload["allowed"] is True
    assert item["particle_count"] <= 300
    assert item["is_verified_knowledge"] is False
    assert item["compressed_ref"]["compression_ratio"] > 1.0
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False
    assert payload["visible_object"] is True
    assert payload["product_visible"] is True
    assert payload["active_archetype"] == "machine_core"
    assert payload["particle_count"] == item["particle_count"]
    assert payload["clear_radius"] == 0.34


def test_imagination_rejects_unknown_archetype() -> None:
    payload = _client().post(
        "/api/agentic-os/splatra/imagination/generate",
        json={"seed_id": "api_test", "archetype": "forbidden_memory_fact", "particle_budget": 300},
    ).json()

    assert payload["allowed"] is False
    assert payload["production_store_mutated"] is False


def test_imagination_evaluate_runs_all_archetypes() -> None:
    payload = _client().post("/api/agentic-os/splatra/imagination/evaluate", json={"particle_budget": 180}).json()

    assert payload["passed"] is True
    assert len(payload["archetypes"]) == 9
    assert payload["safety_flags"]["generated_scene_committed"] is False


def test_imagination_command_exposes_agent_usable_scene_action() -> None:
    payload = _client().post(
        "/api/agentic-os/splatra/imagination/command",
        json={"command": "make a bounded visual object", "particle_budget": 240, "scene_command": "morph", "archetype": "tree"},
    ).json()

    assert payload["allowed"] is True
    assert payload["agent_can_use"] is True
    assert payload["splatra_command_adapter"] is True
    assert payload["external_splatra_called"] is False
    assert payload["raw_buffer_in_agent_context"] is False
    assert payload["command_plan"]["scene_action"]["execute_js"] is False
    assert payload["command_plan"]["scene_command"] == "morph"
    assert payload["command_plan"]["archetype"] == "tree"
    assert payload["command_plan"]["splatra_contract"]["compatible_source"] == "Cozystone/SPLATRA"
    assert payload["command_plan"]["splatra_contract"]["topic_scene_templates"] is False
    assert payload["frame"]["objects"][0]["particle_count"] <= 240
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_scene_choreography_endpoint_accepts_agent_authored_beats_only() -> None:
    payload = _client().post(
        "/api/agentic-os/splatra/imagination/choreography",
        json={
            "stage_layout": "scene_focus",
            "beats": [
                {
                    "op": "spawn_object",
                    "object_id": "concept_a",
                    "prompt": "concept figure",
                    "archetype": "creature",
                    "scene_directive": {
                        "directive_owner": "cgsr_visual_imagination_planner",
                        "basis": "verified_scene_beat",
                        "narrative_function": "present_verified_fact",
                        "stage_instruction": "assemble_verified_object",
                    },
                },
                {"op": "focus_camera", "object_id": "concept_a", "camera": {"zoom": 1.4}},
            ],
        },
    ).json()

    assert payload["allowed"] is True
    assert payload["agent_can_use"] is True
    assert payload["splatra_choreography_adapter"] is True
    assert payload["external_splatra_called"] is False
    assert payload["raw_buffer_in_agent_context"] is False
    assert payload["topic_scene_templates"] is False
    assert payload["scene_choreography"]["stage_layout"] == "scene_focus"
    assert payload["scene_choreography"]["orb_anchor"] == "lower_right"
    assert payload["scene_choreography"]["agent_scene_decisions"][0]["decision_id"] == "scene_space_allocation"
    assert payload["scene_choreography"]["agent_scene_decisions"][0]["generated_visual_elements"] == "particle_points_only"
    assert payload["scene_choreography"]["agent_scene_decisions"][0]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert len(payload["scene_choreography"]["particle_operation_intents"]) == len(payload["scene_choreography"]["beats"])
    assert payload["scene_choreography"]["particle_operation_intents"][0]["agent_control"] == "airbend_recompose_particles_inside_safe_region"
    assert payload["scene_choreography"]["particle_operation_intents"][0]["raw_buffer_in_agent_context"] is False
    assert payload["splatra_command_sequence"]["hot_swap_policy"]["mode"] == "candidate_only"
    assert payload["splatra_command_sequence"]["hot_swap_policy"]["viewer_side_channel"] == "GET /v1/cartridge"
    assert payload["splatra_command_sequence"]["splatra_contract"]["raw_buffers_in_agent_context"] is False
    assert payload["splatra_command_sequence"]["splatra_contract"]["topic_scene_templates"] is False
    assert payload["splatra_command_sequence"]["splatra_contract"]["renderer_may_infer_topic"] is False
    assert payload["splatra_command_sequence"]["particle_motion_policy"]["agent_control"] == "airbend_recompose_particles_inside_safe_region"
    assert len(payload["splatra_command_sequence"]["scene_actions"]) == len(payload["scene_choreography"]["beats"])
    assert payload["splatra_command_sequence"]["hot_swap_policy"]["candidate_request_count"] == len(payload["scene_choreography"]["beats"])
    assert len(payload["splatra_command_sequence"]["candidate_cartridge_requests"]) == len(payload["scene_choreography"]["beats"])
    assert payload["splatra_interactive_scene_analysis"]["interactive_scene"] is True
    assert payload["splatra_interactive_scene_analysis"]["analyzer_contract"]["raw_splat_inference"] is False
    assert payload["splatra_interactive_scene_analysis"]["analyzer_contract"]["persistent_3d_bounding_boxes"] is True
    assert payload["splatra_interactive_scene_analysis"]["safety_flags"]["raw_buffer_in_agent_context"] is False
    assert all("bounding_box" in item for item in payload["splatra_interactive_scene_analysis"]["objects"])
    assert payload["splatra_cartridge_queue"]["status"] == "ready_for_sidecar"
    assert payload["splatra_cartridge_queue"]["execution_mode"] == "candidate_only_dry_run"
    assert payload["splatra_cartridge_queue"]["side_channel"] == "GET /v1/cartridge"
    assert payload["splatra_cartridge_queue"]["job_count"] == len(payload["scene_choreography"]["beats"])
    assert payload["splatra_cartridge_queue"]["external_splatra_called"] is False
    assert payload["splatra_cartridge_queue"]["raw_buffer_in_agent_context"] is False
    assert payload["splatra_cartridge_queue"]["mutation_performed"] is False
    assert all(
        request["cartridge_format"] == "SPL3_candidate"
        for request in payload["splatra_command_sequence"]["candidate_cartridge_requests"]
    )
    assert all(
        request["execution"]["execute_now"] is False
        for request in payload["splatra_command_sequence"]["candidate_cartridge_requests"]
    )
    assert len(payload["scene_choreography"]["beats"]) == 2
    first_beat = payload["scene_choreography"]["beats"][0]
    assert first_beat["scene_directive"]["directive_owner"] == "cgsr_visual_imagination_planner"
    assert first_beat["scene_directive"]["stage_instruction"] == "assemble_verified_object"
    assert first_beat["scene_directive"]["text_rendering"] == "dom_text_not_particles"
    assert first_beat["scene_directive"]["particle_text"] is False
    assert first_beat["scene_directive"]["topic_scene_templates"] is False
    assert first_beat["scene_evidence"]["source_type"] == "verified_evidence_unit"
    assert first_beat["scene_evidence"]["prompt_span"] == "concept figure"
    assert first_beat["scene_evidence"]["text_rendering"] == "dom_text_not_particles"
    assert first_beat["scene_evidence"]["particle_text"] is False
    assert first_beat["scene_evidence"]["topic_scene_templates"] is False
    assert first_beat["scene_evidence"]["renderer_may_infer_topic"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_scene_cartridge_queue_endpoint_is_dry_run_only() -> None:
    payload = _client().post(
        "/api/agentic-os/splatra/imagination/cartridge-queue",
        json={
            "stage_layout": "scene_focus",
            "beats": [
                {
                    "op": "move",
                    "object_id": "verified_motion",
                    "prompt": "verified motion",
                    "motion_path": {"from": [0.0, 0.4, 0.0], "to": [0.0, -0.4, 0.0], "basis": "verified_motion_phrase"},
                },
            ],
        },
    ).json()

    assert payload["allowed"] is True
    assert payload["agent_can_use"] is True
    assert payload["splatra_cartridge_queue_adapter"] is True
    assert payload["external_splatra_called"] is False
    assert payload["raw_buffer_in_agent_context"] is False
    assert payload["mutation_performed"] is False
    assert payload["splatra_cartridge_queue"]["status"] == "ready_for_sidecar"
    assert payload["splatra_cartridge_queue"]["execution_mode"] == "candidate_only_dry_run"
    assert payload["splatra_cartridge_queue"]["job_count"] == 1
    assert payload["splatra_cartridge_queue"]["jobs"][0]["execution"]["execute_now"] is False
    assert payload["splatra_cartridge_queue"]["jobs"][0]["motion_path"]["basis"] == "verified_motion_phrase"


def test_scene_cartridge_queue_can_report_real_sidecar_dispatch_without_raw_buffers(monkeypatch) -> None:
    def fake_dispatch(queue, poll_ticks=2):
        return SplatraSidecarDispatchResult(
            status="swap_ready",
            configured=True,
            sidecar_url="http://127.0.0.1:8000",
            external_splatra_called=True,
            raw_buffer_in_agent_context=False,
            raw_cartridge_fetched=False,
            mutation_performed=False,
            jobs=[
                SplatraSidecarJobResult(
                    job_id="local_job",
                    request_id="local_request",
                    object_id="verified_motion",
                    prompt="verified motion",
                    endpoint="POST /v1/generate_3d_object",
                    status="swap_ready",
                    external_splatra_called=True,
                    raw_buffer_in_agent_context=False,
                    mutation_performed=False,
                    sidecar_job_id="sidecar_1",
                    viewer_cartridge_url="http://127.0.0.1:8000/v1/cartridge",
                    sgf_summary={"num_gaussians": 170000},
                )
            ],
        )

    monkeypatch.setattr(agentic_micro_os, "dispatch_candidate_queue_to_sidecar", fake_dispatch)

    payload = _client().post(
        "/api/agentic-os/splatra/imagination/cartridge-queue",
        json={
            "stage_layout": "scene_focus",
            "dispatch_sidecar": True,
            "beats": [
                {"op": "spawn_object", "object_id": "verified_motion", "prompt": "verified motion"},
            ],
        },
    ).json()

    assert payload["external_splatra_called"] is True
    assert payload["raw_buffer_in_agent_context"] is False
    assert payload["mutation_performed"] is False
    assert payload["splatra_sidecar_dispatch"]["status"] == "swap_ready"
    assert payload["splatra_sidecar_dispatch"]["raw_cartridge_fetched"] is False
    assert payload["splatra_cartridge_queue"]["sidecar_status"] == "swap_ready"
    assert payload["splatra_cartridge_queue"]["sidecar_configured"] is True
