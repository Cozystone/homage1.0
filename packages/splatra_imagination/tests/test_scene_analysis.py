from packages.splatra_imagination import analyze_scene_choreography, compile_scene_choreography


def test_scene_analysis_builds_interactive_bounding_boxes_from_verified_tracks() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "layout_intent": "wide_particle_stage",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "verified_anchor",
                "object_track_id": "track_anchor",
                "prompt": "verified source anchor",
                "semantic_role": "visual_anchor",
                "visual_affordance": "organic_structure",
                "archetype": "tree",
                "position": [-0.44, 0.0, 0.0],
                "scene_evidence": {
                    "source_type": "verified_evidence_unit",
                    "source_fact_hash": "fact_anchor",
                    "prompt_span": "verified source anchor",
                },
            },
            {
                "op": "move",
                "object_id": "verified_falling_object",
                "object_track_id": "track_falling_object",
                "prompt": "verified falling object",
                "semantic_role": "moving_evidence_object",
                "visual_affordance": "small_moving_object",
                "position": [0.12, 0.35, 0.0],
                "motion_path": {
                    "from": [0.12, 0.35, 0.0],
                    "to": [0.18, -0.52, 0.0],
                    "basis": "verified_motion_phrase",
                },
                "scene_evidence": {
                    "source_type": "verified_evidence_unit",
                    "source_fact_hash": "fact_motion",
                    "prompt_span": "verified falling object",
                },
            },
        ],
    })

    analysis = analyze_scene_choreography(plan)
    payload = analysis.to_dict()

    assert payload["interactive_scene"] is True
    assert payload["object_count"] == 2
    assert payload["analyzer_contract"]["raw_splat_inference"] is False
    assert payload["analyzer_contract"]["object_detection_claim"] == "planned_from_agent_scene_tracks_not_raw_splat_inference"
    assert payload["analyzer_contract"]["persistent_3d_bounding_boxes"] is True
    assert payload["analyzer_contract"]["interactive_scene_metadata"] is True
    assert payload["safety_flags"]["external_llm_used"] is False
    assert payload["safety_flags"]["local_brain_write"] is False
    assert payload["safety_flags"]["production_store_mutated"] is False
    assert payload["safety_flags"]["raw_buffer_in_agent_context"] is False
    assert payload["safety_flags"]["topic_scene_templates"] is False
    assert payload["safety_flags"]["renderer_may_infer_topic"] is False
    assert payload["safety_flags"]["particle_text"] is False

    moving = next(item for item in payload["objects"] if item["object_track_id"] == "track_falling_object")
    bbox = moving["bounding_box"]
    assert bbox["min"][1] < -0.52
    assert bbox["max"][1] > 0.35
    assert bbox["basis"] == "scene_track_positions_motion_paths_and_visual_affordance_extent"
    assert "move" in moving["operations"]
    interaction_types = {interaction["type"] for interaction in moving["interactions"]}
    assert {"select", "highlight", "focus_camera", "show_evidence", "animate_path"} <= interaction_types
    assert moving["evidence_refs"][0]["source_fact_hash"] == "fact_motion"
    assert moving["evidence_refs"][0]["particle_text"] is False

    index_row = next(row for row in payload["spatial_index"] if row["object_track_id"] == "track_falling_object")
    assert index_row["interaction_count"] >= 5


def test_scene_analysis_merges_multiple_beats_into_persistent_object_track() -> None:
    analysis = analyze_scene_choreography({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "verified_particle_object",
                "object_track_id": "track_verified_particle_object",
                "prompt": "verified object",
                "position": [0.0, 0.0, 0.0],
            },
            {
                "op": "focus_camera",
                "object_id": "verified_particle_object",
                "object_track_id": "track_verified_particle_object",
                "prompt": "focus verified object",
                "camera": {"target": [0.3, 0.2, 0.1], "zoom": 1.2},
            },
        ],
    })

    payload = analysis.to_dict()
    assert payload["object_count"] == 1
    item = payload["objects"][0]
    assert item["object_id"] == "verified_particle_object"
    assert item["operations"] == ["spawn_object", "focus_camera"]
    assert item["source_beat_indices"] == [0, 1]
    assert item["bounding_box"]["max"][0] > 0.3
