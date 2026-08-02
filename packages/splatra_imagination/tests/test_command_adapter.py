from __future__ import annotations

from packages.splatra_imagination.command_adapter import compile_scene_choreography_commands, compile_splatra_command
from packages.splatra_imagination.scene_choreography import compile_scene_choreography


def test_command_adapter_compiles_prompt_to_scene_action_without_raw_buffers() -> None:
    plan, frame = compile_splatra_command("show a bounded particle object", particle_budget=320)

    assert plan.scene_command == "spawn_object"
    assert plan.scene_action["op"] == "spawn_object"
    assert plan.scene_action["args"]["particle_budget"] == 320
    assert plan.raw_buffer_in_agent_context is False
    assert plan.external_splatra_called is False
    assert plan.splatra_contract["raw_buffers_in_agent_context"] is False
    assert plan.splatra_contract["topic_scene_templates"] is False
    assert frame.objects[0].metadata["splatra_command_plan"]["scene_action"]["execute_js"] is False
    assert frame.objects[0].particle_count <= 320


def test_command_adapter_respects_agent_authored_action_without_keyword_templates() -> None:
    plan, _frame = compile_splatra_command(
        "agent-authored visual beat",
        particle_budget=128,
        scene_command="morph",
        archetype="tree",
    )

    assert plan.scene_command == "morph"
    assert plan.archetype == "tree"
    assert plan.scene_action["op"] == "morph"
    assert plan.splatra_contract["topic_scene_templates"] is False


def test_scene_choreography_validates_agent_authored_beats_without_inventing_content() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "beats": [
            {"op": "spawn_object", "object_id": "figure", "prompt": "historical figure", "archetype": "creature"},
            {"op": "move", "object_id": "falling_object", "position": [0.2, -0.8, 0.0]},
        ],
    })

    assert plan.stage_layout == "scene_focus"
    assert plan.orb_anchor == "lower_right"
    assert plan.text_anchor == "lower_left"
    assert plan.primary_surface == "splatra_stage"
    assert len(plan.beats) == 2
    assert plan.topic_scene_templates is False
    assert plan.external_splatra_called is False
    assert plan.raw_buffer_in_agent_context is False
    assert plan.safety_flags["local_brain_write"] is False
    assert plan.safety_flags["production_store_mutated"] is False


def test_scene_choreography_preserves_timing_position_and_camera_hints() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "text_anchor": "upper_right",
        "beats": [
            {
                "op": "focus_camera",
                "object_id": "focus_subject",
                "object_track_id": "verified_track_focus_subject",
                "object_track_basis": "verified_source_anchor",
                "prompt": "agent-authored subject",
                "narration": "agent-authored visible narration",
                "t_start": 2.5,
                "duration": 4.0,
                "position": [1.5, -1.0, 0.25],
                "pose_hint": "reaching",
                "surface_features": ["fruit_cluster"],
                "particle_behavior": "gravity_arc",
                "scene_directive": {
                    "directive_owner": "cgsr_visual_imagination_planner",
                    "basis": "verified_scene_beat",
                    "narrative_function": "demonstrate_verified_motion",
                    "stage_instruction": "animate_verified_motion_path",
                    "particle_text": False,
                },
                "physics_hint": {"basis": "verified_motion_phrase", "field": "downward_attraction", "gravity_bias": 0.7},
                "motion_path": {"from": [-0.5, 0.25, 0], "to": [0.5, -0.25, 0], "basis": "verified_motion_phrase"},
                "camera": {"target": [0.5, -0.25, 0], "zoom": 1.2},
            },
        ],
    })

    beat = plan.beats[0]
    assert plan.text_anchor == "upper_right"
    assert beat.op == "focus_camera"
    assert beat.object_track_id == "verified_track_focus_subject"
    assert beat.object_track_basis == "verified_source_anchor"
    assert beat.narration == "agent-authored visible narration"
    assert beat.t_start == 2.5
    assert beat.duration == 4.0
    assert beat.position == (1.5, -1.0, 0.25)
    assert beat.pose_hint == "reaching"
    assert beat.surface_features == ("fruit_cluster",)
    assert beat.particle_behavior == "gravity_arc"
    assert beat.scene_directive["directive_owner"] == "cgsr_visual_imagination_planner"
    assert beat.scene_directive["stage_instruction"] == "animate_verified_motion_path"
    assert beat.scene_directive["particle_text"] is False
    assert beat.scene_evidence["source_type"] == "verified_evidence_unit"
    assert beat.scene_evidence["prompt_span"] == "agent-authored subject"
    assert beat.scene_evidence["text_rendering"] == "dom_text_not_particles"
    assert beat.scene_evidence["particle_text"] is False
    assert beat.scene_evidence["topic_scene_templates"] is False
    assert beat.scene_evidence["renderer_may_infer_topic"] is False
    assert beat.physics_hint == {"basis": "verified_motion_phrase", "field": "downward_attraction", "gravity_bias": 0.7}
    assert beat.motion_path == {"from": (-0.5, 0.25, 0.0), "to": (0.5, -0.25, 0.0), "basis": "verified_motion_phrase"}
    assert beat.camera == {"target": [0.5, -0.25, 0], "zoom": 1.2}
    assert plan.topic_scene_templates is False


def test_scene_choreography_exports_verified_speech_timeline() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "tree_anchor",
                "prompt": "tree",
                "narration": "A tree is the visible anchor.",
                "speech_cue": False,
                "speech_cue_basis": "visual_anchor_only",
                "t_start": 0.0,
            },
            {
                "op": "move",
                "object_id": "apple_motion",
                "prompt": "apple",
                "narration": "The apple moves downward in the verified account.",
                "speech_cue": True,
                "speech_cue_basis": "verified_evidence_unit",
                "scene_group_id": "gravity_example",
                "scene_group_role": "motion_event",
                "t_start": 1.4,
                "duration": 2.2,
                "particle_behavior": "gravity_arc",
                "physics_hint": {"basis": "verified_motion_phrase", "field": "downward_attraction", "gravity_bias": 0.7},
                "motion_path": {"from": [0.0, 0.5, 0.0], "to": [0.0, -0.6, 0.0], "basis": "verified_motion_phrase"},
            },
        ],
    })

    assert len(plan.speech_timeline) == 1
    item = plan.speech_timeline[0]
    assert item["beat_index"] == 1
    assert item["text"] == "The apple moves downward in the verified account."
    assert item["text_source"] == "verified_beat_narration"
    assert item["speech_cue_basis"] == "verified_evidence_unit"
    assert item["scene_group_id"] == "gravity_example"
    assert "object_track_id" in item
    assert item["particle_behavior"] == "gravity_arc"
    assert item["scene_directive"]["stage_instruction"] == "animate_verified_motion_path"
    assert item["scene_directive"]["particle_text"] is False
    assert item["scene_evidence"]["source_type"] == "verified_evidence_unit"
    assert item["scene_evidence"]["prompt_span"] == "apple"
    assert item["scene_evidence"]["motion_basis"] == "verified_motion_phrase"
    assert item["scene_evidence"]["particle_text"] is False
    assert item["scene_evidence"]["topic_scene_templates"] is False
    assert item["scene_evidence"]["renderer_may_infer_topic"] is False
    assert item["physics_hint"]["field"] == "downward_attraction"
    assert item["motion_path"]["basis"] == "verified_motion_phrase"
    assert plan.dashboard_layout["agent_layout_decision"]["text_rendering"] == "dom_text_not_particles"
    assert plan.dashboard_layout["agent_layout_decision"]["decision_owner"] == "cgsr_scene_choreography_agent"
    assert plan.dashboard_layout["agent_layout_decision"]["content_source"] == "verified_beats_only"
    assert plan.dashboard_layout["agent_layout_decision"]["particle_space"] == "uncovered_dashboard_field_minus_sidebar_composer_and_text"
    assert plan.dashboard_layout["agent_layout_decision"]["generated_visual_elements"] == "particle_points_only"
    assert plan.dashboard_layout["agent_layout_decision"]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert plan.dashboard_layout["agent_layout_decision"]["flow_motion_reference"] == "codepen_magnetic_swarm_noise_decay_reference"
    assert plan.dashboard_layout["agent_layout_decision"]["text_exception"] == "dom_text_measured_layout_only"
    assert plan.dashboard_layout["agent_layout_decision"]["orb_self_body_yield"] == "orb_moves_and_scales_to_clear_verified_particle_scene"
    assert plan.dashboard_layout["agent_layout_decision"]["orb_yield_strength"] >= 0.72
    assert plan.dashboard_layout["agent_layout_decision"]["particle_recomposition_mode"] == "agent_airbend_recompose_verified_beats"
    assert plan.dashboard_layout["agent_layout_decision"]["topic_scene_templates"] is False
    assert plan.dashboard_layout["agent_layout_decision"]["renderer_may_infer_topic"] is False
    assert plan.dashboard_layout["agent_layout_decision"]["scene_geometry_inputs"]["motion_count"] == 1
    assert plan.dashboard_layout["scene"]["generated_visual_elements"] == "particle_points_only"
    assert plan.dashboard_layout["scene"]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert plan.dashboard_layout["scene"]["text_exception"] == "dom_text_not_particle_geometry"
    assert plan.dashboard_layout["stage_safe_region"]["footprint"]["basis"] == "verified_scene_geometry_extent"
    assert plan.dashboard_layout["stage_safe_region"]["footprint"]["block_text"] is True
    assert plan.layout_timeline[0]["action"] in {"share_center_with_particle_scene", "yield_center_to_particle_scene"}
    assert plan.layout_timeline[0]["decision_basis"] == "verified_scene_geometry_and_self_body_clearance_state"
    assert plan.layout_timeline[0]["decision_owner"] == "cgsr_scene_choreography_agent"
    assert plan.layout_timeline[0]["text_rendering"] == "dom_text_not_particles"
    assert plan.layout_timeline[0]["particle_space"] == "uncovered_dashboard_field_minus_sidebar_composer_and_text"
    assert plan.layout_timeline[0]["generated_visual_elements"] == "particle_points_only"
    assert plan.layout_timeline[0]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert plan.layout_timeline[0]["text_exception"] == "dom_text_measured_layout_only"
    assert plan.layout_timeline[0]["particle_recomposition_mode"] == "agent_airbend_recompose_verified_beats"
    active_layout = next(item for item in plan.layout_timeline if item["action"] == "sync_orb_text_with_particle_beat" and item["beat_index"] == 1)
    assert active_layout["text_rendering"] == "dom_text_not_particles"
    assert active_layout["decision_owner"] == "cgsr_scene_choreography_agent"
    assert active_layout["scene_directive"]["stage_instruction"] == "animate_verified_motion_path"
    assert active_layout["scene_evidence"]["source_type"] == "verified_evidence_unit"
    assert active_layout["scene_evidence"]["motion_basis"] == "verified_motion_phrase"
    assert active_layout["scene_evidence"]["renderer_may_infer_topic"] is False
    assert "object_track_id" in active_layout
    assert active_layout["orb_movement"] == "lower_right_lifted_micro"
    assert active_layout["active_layout_pressure"] >= 0.78
    assert active_layout["active_bbox"]["basis"] == "active_verified_beat_position_and_motion_path"
    assert active_layout["orb_scale_hint"] == "micro_self_body_yield"
    assert active_layout["text_safe_region"] == active_layout["text_anchor"]
    assert active_layout["text_anchor"] == "lower_left"
    assert active_layout["text_anchor_basis"] == "verified_vertical_motion_path_conversational_clearance"
    assert active_layout["text_anchor_points"] == 3
    assert active_layout["self_narration_anchor"] in {"upper_left", "upper_right"}
    assert plan.agent_scene_decisions[0]["decision_id"] == "scene_space_allocation"
    assert plan.agent_scene_decisions[0]["selected_action"] in {"share_center_with_particle_scene", "yield_center_to_particle_scene"}
    assert plan.agent_scene_decisions[0]["decision_model"] == "self_body_scene_pressure_scorer_no_topic_templates"
    assert plan.agent_scene_decisions[0]["decision_candidates"]
    assert plan.agent_scene_decisions[0]["scene_self_state"]["self_body_identity"] == "atanor_orb_self_body"
    assert plan.agent_scene_decisions[0]["scene_self_state"]["topic_scene_templates"] is False
    assert plan.agent_scene_decisions[0]["decision_candidates"][0]["action"] == plan.agent_scene_decisions[0]["selected_action"]
    assert plan.agent_scene_decisions[0]["selected_action_score"] == plan.agent_scene_decisions[0]["decision_candidates"][0]["score"]
    assert plan.agent_scene_decisions[0]["selection_reason"]
    assert plan.agent_scene_decisions[0]["topic_scene_templates"] is False
    assert plan.agent_scene_decisions[0]["renderer_may_infer_topic"] is False
    assert plan.agent_scene_decisions[0]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert plan.agent_scene_decisions[0]["orb_yield_strength"] >= 0.72
    speech_decision = next(item for item in plan.agent_scene_decisions if item["decision_id"] == "speech_beat_layout_1")
    assert speech_decision["object_id"] == "apple_motion"
    assert speech_decision["text_rendering"] == "dom_text_not_particles"
    assert speech_decision["particle_text"] is False
    assert len(plan.particle_operation_intents) == len(plan.beats)
    move_intent = next(item for item in plan.particle_operation_intents if item["object_id"] == "apple_motion")
    assert move_intent["operation"] == "animate_particle_motion_path"
    assert move_intent["agent_control"] == "airbend_recompose_particles_inside_safe_region"
    assert move_intent["generated_visual_elements"] == "particle_points_only"
    assert move_intent["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert move_intent["flow_motion_reference"] == "codepen_magnetic_swarm_noise_decay_reference"
    assert move_intent["text_rendering"] == "dom_text_not_particles"
    assert move_intent["particle_text"] is False
    assert move_intent["topic_scene_templates"] is False
    assert move_intent["renderer_may_infer_topic"] is False
    assert move_intent["external_splatra_called"] is False
    assert move_intent["raw_buffer_in_agent_context"] is False
    assert move_intent["mutation_performed"] is False
    assert plan.topic_scene_templates is False


def test_layout_timeline_places_speech_away_from_active_scene_focus() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "spawn_object",
                "prompt": "verified right-side particle focus",
                "narration": "The verified focus is on the right side.",
                "position": [0.72, 0.24, 0.0],
                "speech_cue": True,
                "t_start": 0.0,
                "duration": 1.4,
            },
            {
                "op": "spawn_object",
                "prompt": "verified left-side particle focus",
                "narration": "The verified focus shifts to the left side.",
                "position": [-0.72, 0.24, 0.0],
                "speech_cue": True,
                "t_start": 1.4,
                "duration": 1.4,
            },
        ],
    })

    first = next(item for item in plan.layout_timeline if item.get("beat_index") == 0)
    second = next(item for item in plan.layout_timeline if item.get("beat_index") == 1)
    assert first["text_anchor"] == "upper_left"
    assert second["text_anchor"] == "upper_right"
    assert first["text_rendering"] == second["text_rendering"] == "dom_text_not_particles"
    footprint = plan.dashboard_layout["stage_safe_region"]["footprint"]
    assert footprint["basis"] == "verified_scene_geometry_extent"
    assert footprint["min_x"] < 0 < footprint["max_x"]


def test_wide_particle_stage_reserves_dom_text_lanes_outside_central_footprint() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "layout_intent": "wide_particle_stage",
        "beats": [
            {
                "op": "spawn_object",
                "prompt": "verified left particle anchor",
                "narration": "The verified anchor starts on the left.",
                "position": [-0.88, -0.48, 0.0],
                "speech_cue": True,
            },
            {
                "op": "move",
                "prompt": "verified right particle motion",
                "narration": "The verified object moves through the field.",
                "position": [0.88, 0.48, 0.0],
                "motion_path": {"from": [-0.72, 0.45, 0.0], "to": [0.72, -0.45, 0.0], "basis": "verified_motion_phrase"},
                "speech_cue": True,
            },
        ],
    })

    footprint = plan.dashboard_layout["stage_safe_region"]["footprint"]
    assert footprint["block_text"] is True
    assert footprint["basis"] == "verified_scene_geometry_extent"
    assert footprint["min_x"] >= -0.88
    assert footprint["max_x"] <= 0.88
    assert footprint["min_y"] >= -0.5
    assert footprint["max_y"] <= 0.46
    assert plan.dashboard_layout["scene"]["generated_visual_elements"] == "particle_points_only"
    assert plan.dashboard_layout["scene"]["text_exception"] == "dom_text_not_particle_geometry"
    assert plan.dashboard_layout["agent_layout_decision"]["particle_space"] == "uncovered_dashboard_field_minus_sidebar_composer_and_text"


def test_layout_timeline_nudges_orb_from_active_lower_right_focus() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "move",
                "prompt": "verified lower-right moving object",
                "narration": "The verified object moves through the lower right.",
                "position": [0.58, -0.36, 0.0],
                "motion_path": {"from": [0.45, 0.22, 0.0], "to": [0.62, -0.46, 0.0], "basis": "verified_motion_phrase"},
                "speech_cue": True,
                "t_start": 0.0,
                "duration": 1.6,
            },
        ],
    })

    active = next(item for item in plan.layout_timeline if item.get("beat_index") == 0)
    assert active["decision_basis"] == "verified_speech_cue_beat"
    assert active["orb_movement"] == "lower_right_micro_stage_guard"
    assert active["active_layout_pressure"] >= 0.64
    assert active["active_bbox"]["basis"] == "active_verified_beat_position_and_motion_path"
    assert "right_stage" in active["active_regions"]
    assert active["orb_scale_hint"] in {"compact_self_body_yield", "micro_self_body_yield"}
    assert active["text_rendering"] == "dom_text_not_particles"


def test_layout_timeline_places_speech_away_from_motion_path_even_when_position_is_centered() -> None:
    plan = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "move",
                "prompt": "verified right-side falling object",
                "narration": "The verified object moves down on the right side.",
                "position": [0.0, 0.0, 0.0],
                "motion_path": {"from": [0.66, 0.48, 0.0], "to": [0.72, -0.42, 0.0], "basis": "verified_motion_phrase"},
                "speech_cue": True,
                "t_start": 0.0,
                "duration": 1.6,
            },
        ],
    })

    active = next(item for item in plan.layout_timeline if item.get("beat_index") == 0)
    assert active["decision_basis"] == "verified_speech_cue_beat"
    assert active["text_anchor"] == "upper_left"
    assert active["text_anchor_basis"] == "verified_motion_path_horizontal_clearance"
    assert active["text_anchor_points"] == 3
    assert active["text_rendering"] == "dom_text_not_particles"


def test_command_adapter_keeps_safety_flags_closed() -> None:
    plan, frame = compile_splatra_command("visual scene request", particle_budget=128)

    assert plan.safety_flags["external_llm"] is False
    assert plan.safety_flags["external_sllm"] is False
    assert plan.safety_flags["image_model_used"] is False
    assert plan.safety_flags["local_brain_write"] is False
    assert plan.safety_flags["production_store_mutated"] is False
    assert plan.safety_flags["generated_scene_committed"] is False
    assert frame.objects[0].is_verified_knowledge is False


def test_scene_choreography_commands_compile_airbend_particle_sequence_without_raw_buffers() -> None:
    choreography = compile_scene_choreography({
        "stage_layout": "scene_focus",
        "layout_intent": "wide_particle_stage",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "verified_tree_anchor",
                "object_track_id": "track_tree_anchor",
                "object_track_basis": "verified_source_anchor",
                "prompt": "tree from verified source span",
                "narration": "The tree is the verified visual anchor.",
                "archetype": "tree",
                "position": [-0.44, 0.0, 0.0],
                "scene_evidence": {
                    "source_type": "verified_evidence_unit",
                    "source_fact_hash": "fact_tree_hash",
                    "prompt_span": "tree from verified source span",
                    "topic_scene_templates": False,
                },
            },
            {
                "op": "move",
                "object_id": "verified_falling_object",
                "object_track_id": "track_falling_object",
                "prompt": "falling object from verified source span",
                "narration": "The verified object moves downward.",
                "particle_behavior": "gravity_arc",
                "position": [0.12, 0.35, 0.0],
                "motion_path": {"from": [0.12, 0.35, 0.0], "to": [0.18, -0.52, 0.0], "basis": "verified_motion_phrase"},
                "physics_hint": {"basis": "verified_motion_phrase", "field": "downward_attraction", "gravity_bias": 0.7},
                "scene_evidence": {
                    "source_type": "verified_evidence_unit",
                    "source_fact_hash": "fact_motion_hash",
                    "motion_basis": "verified_motion_phrase",
                    "topic_scene_templates": False,
                },
            },
            {
                "op": "focus_camera",
                "object_id": "verified_falling_object",
                "prompt": "focus verified falling object",
                "camera": {"target": [0.18, -0.52, 0.0], "zoom": 1.35},
            },
        ],
    })

    sequence = compile_scene_choreography_commands(choreography, particle_budget=12_000)

    assert sequence.external_splatra_called is False
    assert sequence.raw_buffer_in_agent_context is False
    assert sequence.hot_swap_policy["mode"] == "candidate_only"
    assert sequence.hot_swap_policy["mutation_performed"] is False
    assert sequence.hot_swap_policy["viewer_side_channel"] == "GET /v1/cartridge"
    assert sequence.hot_swap_policy["candidate_request_count"] == 3
    assert sequence.splatra_contract["compatible_source"] == "Cozystone/SPLATRA"
    assert sequence.splatra_contract["raw_buffers_in_agent_context"] is False
    assert sequence.splatra_contract["agent_context_payload"] == "sgf_summary_and_command_sequence_only"
    assert sequence.splatra_contract["topic_scene_templates"] is False
    assert sequence.splatra_contract["renderer_may_infer_topic"] is False
    assert sequence.particle_motion_policy["field_model"] == "magnetic_swarm_noise_decay_reference"
    assert sequence.particle_motion_policy["flow_lines"] == "sparse_particle_marks_not_canvas_paths"
    assert sequence.particle_motion_policy["agent_control"] == "airbend_recompose_particles_inside_safe_region"

    assert [action["op"] for action in sequence.scene_actions] == ["spawn_object", "move", "focus_camera"]
    assert len(sequence.candidate_cartridge_requests) == len(sequence.scene_actions)
    for action in sequence.scene_actions:
        assert action["execute_js"] is False
        assert action["mutation_performed"] is False
        assert action["raw_buffer_in_agent_context"] is False
        assert action["topic_scene_templates"] is False
        assert action["renderer_may_infer_topic"] is False
        assert action["args"]["particle_text"] is False
        assert action["args"]["text_rendering"] == "dom_text_not_particles"

    for request in sequence.candidate_cartridge_requests:
        assert request["cartridge_format"] == "SPL3_candidate"
        assert request["cartridge_role"] == "viewer_side_channel_candidate"
        assert request["input_basis"] == "verified_scene_action"
        assert request["execution"]["status"] == "candidate_request_only"
        assert request["execution"]["execute_now"] is False
        assert request["execution"]["agent_context_receives"] == "request_summary_only"
        assert request["execution"]["raw_buffer_in_agent_context"] is False
        assert request["quality_gates"]["particle_text"] is False
        assert request["quality_gates"]["topic_scene_templates"] is False
        assert request["quality_gates"]["renderer_may_infer_topic"] is False
        assert request["quality_gates"]["mutation_performed"] is False

    move = sequence.scene_actions[1]
    assert move["args"]["track_id"] == "track_falling_object"
    assert move["args"]["particle_behavior"] == "gravity_arc"
    assert move["args"]["motion_path"]["basis"] == "verified_motion_phrase"
    assert move["args"]["physics_hint"]["field"] == "downward_attraction"
    assert move["args"]["scene_evidence"]["source_fact_hash"] == "fact_motion_hash"
    motion_request = sequence.candidate_cartridge_requests[1]
    assert motion_request["object_id"] == "verified_falling_object"
    assert motion_request["motion_path"]["basis"] == "verified_motion_phrase"
    assert motion_request["physics_hint"]["field"] == "downward_attraction"
    assert motion_request["quality_gates"]["source_fact_hash"] == "fact_motion_hash"

    focus = sequence.scene_actions[2]
    assert focus["args"]["camera"]["zoom"] == 1.35
    assert sequence.safety_flags["external_llm"] is False
    assert sequence.safety_flags["local_brain_write"] is False
    assert sequence.safety_flags["production_store_mutated"] is False


def test_scene_choreography_command_sequence_does_not_invent_topic_objects() -> None:
    sequence = compile_scene_choreography_commands({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "move",
                "object_id": "verified_motion_only",
                "prompt": "verified motion marker",
                "motion_path": {"from": [-0.1, 0.2, 0.0], "to": [0.1, -0.2, 0.0], "basis": "verified_motion_phrase"},
            },
        ],
    })

    payload = str(sequence.to_dict()).casefold()
    assert "apple" not in payload
    assert "newton" not in payload
    assert "tree" not in payload
    assert sequence.splatra_contract["topic_scene_templates"] is False
