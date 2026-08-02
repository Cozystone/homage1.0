from __future__ import annotations

import json
from pathlib import Path

from packages.cgsr.cgsr.conversation_grounding import gather_grounded_context
from packages.cgsr.cgsr.conversation_router import route_conversation_request
from packages.cgsr.cgsr.visual_imagination_planner import plan_visual_imagination


TEXT_ANCHORS = {"upper_left", "lower_left", "upper_right", "lower_center"}


def _plan(question: str, store_path: Path | None = None, layout_feedback: dict[str, object] | None = None):
    route = route_conversation_request(question)
    runtime = {"verified_store_path": str(store_path)} if store_path else None
    context = gather_grounded_context(question, route, runtime=runtime)
    return plan_visual_imagination(
        question,
        route=route,
        grounded_context=context,
        diagnostics={
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_used": False,
        },
        answer_available=True,
        client_layout_feedback=layout_feedback,
    )


def test_visual_planner_abstains_without_grounded_general_knowledge() -> None:
    plan = _plan("Explain gravity with a visual scene")

    assert plan.enabled is False
    assert plan.scene_choreography is None
    assert plan.diagnostics["topic_scene_templates"] is False


def test_visual_planner_uses_grounded_phrases_without_topic_templates() -> None:
    question = "Use SPLATRA to visualize gravity as moving particles"
    plan = _plan(question)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    assert plan.scene_choreography["stage_layout"] == "scene_focus"
    assert plan.scene_choreography["orb_anchor"] == "lower_right"
    assert plan.scene_choreography["text_anchor"] in TEXT_ANCHORS
    assert plan.scene_choreography["layout_intent"] in {"balanced_scene", "wide_particle_stage"}
    assert plan.scene_choreography["scene_extent"]["beat_count"] == len(plan.scene_choreography["beats"])
    assert plan.diagnostics["topic_scene_templates"] is False
    assert plan.scene_choreography["topic_scene_templates"] is False
    assert plan.scene_choreography["beats"]
    assert plan.scene_choreography["beats"][0]["prompt"] == question
    assert len(plan.scene_choreography["beats"]) == 1
    assert plan.scene_choreography["beats"][0]["semantic_role"] == "user_visual_intent"
    assert all("Newton" not in beat["prompt"] for beat in plan.scene_choreography["beats"])
    assert all("apple" not in beat["prompt"].casefold() for beat in plan.scene_choreography["beats"])


def test_visual_planner_uses_client_layout_feedback_only_for_dom_collision() -> None:
    question = "Use SPLATRA to visualize gravity as moving particles"
    plan = _plan(
        question,
        layout_feedback={
            "feedback_basis": "client_dom_scene_collision_telemetry",
            "collision_state": "orb_overlap_risk",
            "overlap_px": 120,
            "offscreen_px": 0,
            "orb_overlap_px": 260,
            "orb_offscreen_px": 24,
            "speech_anchor": "lower_left",
            "self_narration_anchor": "upper_right",
            "text_rendering": "dom_text_not_particles",
            "particle_text": False,
        },
    )

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    decision = plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]
    feedback = decision["client_layout_feedback"]
    assert feedback["feedback_basis"] == "client_dom_scene_collision_telemetry"
    assert feedback["layout_feedback_used"] is True
    assert feedback["content_used_for_scene_generation"] is False
    assert feedback["text_rendering"] == "dom_text_not_particles"
    assert feedback["particle_text"] is False
    assert decision["orb_movement"] == "lower_right_micro_stage_guard"
    assert "client_dom_collision_feedback" in decision["selection_reason"]
    assert plan.diagnostics["client_layout_feedback_used"] is True
    assert all(beat["prompt"] == question for beat in plan.scene_choreography["beats"] if beat["semantic_role"] == "user_visual_intent")


def test_visual_planner_keeps_direct_splatra_generation_as_single_user_intent() -> None:
    question = "SPLATRA 파티클로 사실적인 빨간 사과 3D 모델을 직접 생성해서 보여줘"
    plan = _plan(question)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    assert len(beats) == 1
    assert beats[0]["prompt"] == "red apple"
    assert beats[0]["narration"] == question
    assert beats[0]["semantic_role"] == "user_visual_intent"
    assert tuple(beats[0]["position"][:2]) == (0.0, 0.0)
    assert beats[0]["scene_directive"]["particle_text"] is False
    assert beats[0]["scene_directive"]["text_rendering"] == "dom_text_not_particles"
    assert plan.scene_choreography["layout_intent"] == "wide_particle_stage"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["agent_action"] == "yield_center_to_particle_scene"
    assert plan.scene_choreography["dashboard_layout"]["stage_safe_region"]["footprint"]["block_text"] is True
    assert plan.scene_choreography["dashboard_layout"]["stage_safe_region"]["footprint"]["min_x"] <= -0.72
    assert plan.scene_choreography["dashboard_layout"]["stage_safe_region"]["footprint"]["max_x"] >= 0.72
    assert plan.diagnostics["scene_content_source"] == "user_visual_intent_only"
    assert plan.diagnostics["particle_text"] is False
    assert plan.diagnostics["text_rendering"] == "dom_text_not_particles"


def test_visual_planner_accepts_clean_korean_direct_generation_without_splatra_word() -> None:
    question = "사실적인 유리 구슬을 직접 생성해서 보여줘"
    plan = _plan(question)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    assert plan.diagnostics["scene_authoring_basis"] == "user_direct_splatra_generation_request"
    assert plan.scene_choreography["beats"][0]["prompt"] == "translucent glass marble sphere with visible rim"
    assert plan.scene_choreography["beats"][0]["narration"] == question
    assert plan.scene_choreography["beats"][0]["semantic_role"] == "user_visual_intent"
    assert plan.scene_choreography["layout_intent"] == "wide_particle_stage"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["agent_action"] == "yield_center_to_particle_scene"
    assert plan.diagnostics["particle_text"] is False
    assert plan.diagnostics["text_rendering"] == "dom_text_not_particles"


def test_visual_planner_uses_verified_store_facts_for_general_knowledge(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "Gravity"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("What is the law of gravity?", tmp_path)

    assert plan.enabled is False
    assert plan.reason == "insufficient_concrete_visual_evidence"
    assert plan.scene_choreography is None
    assert plan.diagnostics["scene_authoring_basis"] == "abstained_abstract_or_nonvisual_evidence"
    assert plan.diagnostics["scene_content_source"] == "none"
    assert plan.diagnostics["renderer_may_infer_topic"] is False
    assert plan.diagnostics["particle_text"] is False
    assert plan.diagnostics["text_rendering"] == "dom_text_not_particles"
    assert plan.diagnostics["visual_affordance_basis"] == "source_phrase_affordance_extraction_no_topic_template"


def test_visual_planner_ignores_prompted_newton_apple_scene_without_verified_evidence(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "Gravity"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("Explain gravity with Newton, an apple tree, and a falling apple.", tmp_path)

    if not plan.enabled:
        assert plan.scene_choreography is None
        assert plan.diagnostics["scene_content_source"] == "none"
        assert plan.diagnostics["renderer_may_infer_topic"] is False
        assert plan.diagnostics["particle_text"] is False
        return

    prompts = [beat["prompt"].casefold() for beat in plan.scene_choreography["beats"]]
    narrations = [beat["narration"].casefold() for beat in plan.scene_choreography["beats"]]
    assert any("isaac newton" in prompt for prompt in prompts)
    assert all("apple" not in prompt for prompt in prompts)
    assert all("tree" not in prompt for prompt in prompts)
    assert all("apple" not in narration for narration in narrations)
    assert all("tree" not in narration for narration in narrations)
    assert plan.scene_choreography["topic_scene_templates"] is False
    assert plan.diagnostics["scene_content_source"] == "verified_store_facts"
    assert plan.diagnostics["renderer_may_infer_topic"] is False
    assert plan.diagnostics["particle_text"] is False


def test_visual_planner_does_not_scene_from_function_word_overlap(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "The Second Law of Thermodynamics explains entropy in closed systems.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "Thermodynamics"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("What is the law of gravity?", tmp_path)

    assert plan.enabled is False
    assert plan.scene_choreography is None
    assert plan.diagnostics["topic_scene_templates"] is False


def test_visual_planner_abstains_for_abstract_korean_physics_fact(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "뉴턴의 중력 법칙은 질량을 가진 물체 사이의 끌림을 설명하며, 힘의 크기는 거리의 제곱에 반비례한다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "중력"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("중력의 법칙에 대해 설명해줘", tmp_path)

    assert plan.enabled is False
    assert plan.reason == "insufficient_concrete_visual_evidence"
    assert plan.scene_choreography is None
    assert plan.diagnostics["scene_authoring_basis"] == "abstained_abstract_or_nonvisual_evidence"
    assert plan.diagnostics["particle_text"] is False
    assert plan.diagnostics["text_rendering"] == "dom_text_not_particles"


def test_visual_planner_only_adds_motion_when_verified_fact_contains_motion(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "아이작 뉴턴은 중력 법칙과 관련해 사과가 나무에서 떨어지는 장면을 관찰했다. 그 사건은 물체가 지구 쪽으로 끌리는 현상을 설명하는 단서가 되었다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "뉴턴"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("중력의 법칙에 대해 설명해줘", tmp_path)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    assert any(beat["op"] == "move" for beat in beats)
    assert any("사과" in beat["narration"] for beat in beats)
    assert any("떨어" in beat["narration"] for beat in beats)
    assert all(beat["source_fact"] for beat in beats)


def test_visual_planner_extracts_korean_figure_tree_apple_motion_without_topic_script(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": (
                    "아이작 뉴턴은 중력 법칙과 관련해 사과가 나무에서 떨어지는 장면을 관찰했다. "
                    "그는 사과나무 밑에 앉아 있었고 사과가 뉴턴의 머리 위로 떨어졌다."
                ),
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "뉴턴 사과나무"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("중력의 법칙에 대해 설명해줘", tmp_path)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    assert any("뉴턴" in beat["prompt"] and beat["visual_affordance"] == "entity_figure" for beat in beats)
    assert any("나무" in beat["prompt"] and beat["visual_affordance"] == "organic_structure" for beat in beats)
    assert any(beat["prompt"] == "사과" and beat["visual_affordance"] == "small_moving_object" for beat in beats)
    assert any(beat["prompt"] == "사과" and beat["speech_cue"] is True and beat["semantic_role"] == "verified_motion_event" for beat in beats)
    assert any(beat["prompt"] == "사과나무" and beat["speech_cue"] is False and beat["semantic_role"] == "verified_motion_source" for beat in beats)
    assert any("뉴턴" in beat["prompt"] and beat["speech_cue"] is False and beat["semantic_role"] == "verified_motion_target" for beat in beats)
    assert any("뉴턴" in beat["prompt"] and beat["spatial_relation"] == "under_target" for beat in beats)
    apple_motion = next(beat for beat in beats if beat["prompt"] == "사과" and beat.get("motion_path"))
    assert "나무" in apple_motion["motion_path"]["source_prompt"]
    assert "뉴턴" in apple_motion["motion_path"]["target_prompt"]
    assert apple_motion["motion_path"]["from"][1] > apple_motion["motion_path"]["to"][1]
    assert plan.scene_choreography["topic_scene_templates"] is False
    assert plan.diagnostics["scene_authoring_basis"] == "verified_fact_entity_action_extraction"


def test_visual_planner_handles_korean_motion_with_short_particles_without_topic_script(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": (
                    "중력 법칙 설명에서 아이작 뉴턴은 사과나무 밑에 앉아 있었다. "
                    "사과 떨어짐은 뉴턴의 머리 쪽으로 내려가는 물체 이동으로 관찰되었다."
                ),
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "뉴턴 사과 이동"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("중력의 법칙에 대해 설명해줘", tmp_path)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    motion_beats = [beat for beat in beats if beat["op"] == "move" and beat.get("motion_path")]
    assert motion_beats
    assert any(beat["prompt"] == "사과" for beat in motion_beats)
    apple_motion = next(beat for beat in motion_beats if beat["prompt"] == "사과")
    assert apple_motion["motion_path"]["basis"] == "verified_motion_phrase"
    assert "나무" in apple_motion["motion_path"]["source_prompt"]
    assert "뉴턴" in apple_motion["motion_path"]["target_prompt"]
    assert apple_motion["particle_behavior"] == "gravity_arc"
    assert apple_motion["scene_directive"]["topic_scene_templates"] is False
    assert apple_motion["scene_evidence"]["particle_text"] is False
    assert plan.scene_choreography["topic_scene_templates"] is False


def test_visual_planner_extracts_utf8_korean_motion_without_moving_scene_anchors(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": (
                    "아이작 뉴턴은 중력 법칙과 관련해 사과가 사과나무에서 떨어지는 장면을 관찰했다. "
                    "그는 사과나무 밑에 앉아 있었고 사과가 뉴턴의 머리 위로 떨어졌다."
                ),
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "뉴턴 사과나무"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("중력의 법칙에 대해 설명해줘", tmp_path)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    apple_moves = [beat for beat in beats if beat["prompt"] == "사과" and beat["op"] == "move" and beat.get("motion_path")]
    assert apple_moves
    apple_motion = apple_moves[0]
    assert "사과나무" in apple_motion["motion_path"]["source_prompt"]
    assert "뉴턴" in apple_motion["motion_path"]["target_prompt"]
    assert apple_motion["particle_behavior"] == "gravity_arc"
    assert apple_motion["scene_directive"]["topic_scene_templates"] is False
    assert apple_motion["scene_evidence"]["renderer_may_infer_topic"] is False
    anchor_beats = [
        beat
        for beat in beats
        if beat["semantic_role"] in {
            "verified_motion_source",
            "verified_motion_target",
            "verified_motion_anchor",
            "verified_motion_context",
            "verified_entity_anchor",
        }
    ]
    assert any(beat["prompt"] == "사과나무" and beat["visual_affordance"] == "organic_structure" for beat in anchor_beats)
    assert any("뉴턴" in beat["prompt"] and beat["visual_affordance"] == "entity_figure" for beat in anchor_beats)
    assert all(beat["op"] != "move" for beat in anchor_beats)
    assert all(not beat.get("motion_path") for beat in anchor_beats)
    assert all(beat["speech_cue"] is False for beat in anchor_beats)
    assert plan.scene_choreography["topic_scene_templates"] is False
    assert plan.diagnostics["scene_authoring_basis"] == "verified_fact_entity_action_extraction"


def test_visual_planner_text_anchor_is_scene_position_dependent(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "A river moves through a lower valley. The falling water shifts from the left channel to the center basin.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "River"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("Explain how the water moves", tmp_path)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    assert plan.scene_choreography["text_anchor"] in TEXT_ANCHORS
    assert plan.scene_choreography["text_anchor"] != "auto"


def test_visual_planner_decomposes_verified_motion_scene_without_topic_script(tmp_path: Path) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": (
                    "Gravity is associated with Isaac Newton. "
                    "Isaac Newton sat under an apple tree. "
                    "An apple fell from the tree toward Newton, and the event helped explain gravitational attraction."
                ),
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "Newton apple tree"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan = _plan("What is gravity?", tmp_path)

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    prompts = [beat["prompt"] for beat in beats]
    starts = [beat["t_start"] for beat in beats]
    assert starts == sorted(starts)
    assert all(beat["duration"] >= 1.05 for beat in beats)
    assert len({beat["duration"] for beat in beats}) >= 2
    assert any(prompt == "Isaac Newton" for prompt in prompts)
    assert any(prompt == "apple" for prompt in prompts)
    assert any(prompt == "tree" for prompt in prompts)
    assert any("apple fell" in prompt for prompt in prompts)
    assert any(beat["visual_affordance"] == "entity_figure" and beat["archetype"] == "creature" for beat in beats if "Isaac Newton" in beat["prompt"])
    assert any(beat["visual_affordance"] == "organic_structure" and beat["archetype"] == "tree" for beat in beats if beat["prompt"] == "tree")
    assert any(beat["visual_affordance"] == "small_moving_object" and beat["archetype"] == "machine_core" for beat in beats if beat["prompt"] == "apple")
    assert any(beat["semantic_role"] == "verified_motion_subject" and beat["prompt"] == "apple" for beat in beats)
    assert any(beat["semantic_role"] == "verified_motion_source" and beat["prompt"] == "tree" for beat in beats)
    assert any(beat["semantic_role"] == "verified_motion_target" and beat["prompt"] == "Isaac Newton" and beat["visual_affordance"] == "entity_figure" for beat in beats)
    apple_tracks = {beat["object_track_id"] for beat in beats if beat["prompt"] == "apple"}
    tree_tracks = {beat["object_track_id"] for beat in beats if beat["prompt"] == "tree"}
    newton_tracks = {beat["object_track_id"] for beat in beats if beat["prompt"] == "Isaac Newton" and beat["visual_affordance"] == "entity_figure"}
    assert len(apple_tracks) == 1
    assert len(tree_tracks) == 1
    assert len(newton_tracks) == 1
    assert all(beat["object_track_basis"] == "verified_source_anchor" for beat in beats)
    assert all(beat["archetype"] == "abstract_memory_cloud" for beat in beats if beat["visual_affordance"] == "concept_cloud")
    seated_newton = next(beat for beat in beats if beat["prompt"] == "Isaac Newton" and beat["spatial_relation"] == "under_target")
    tree_anchor = next(beat for beat in beats if beat["prompt"] == "tree" and beat["spatial_relation"] in {"over_anchor", "motion_source"})
    assert seated_newton["pose_hint"] == "seated"
    assert seated_newton["physics_hint"]["pose_hint"] == "seated"
    assert "fruit_cluster" in tree_anchor["surface_features"]
    assert "fruit_cluster" in tree_anchor["physics_hint"]["surface_features"]
    assert seated_newton["position"][1] < tree_anchor["position"][1]
    assert any(beat["op"] == "move" and beat["prompt"] == "apple" for beat in beats)
    assert all("speech_cue" in beat for beat in beats)
    assert all("speech_cue_basis" in beat for beat in beats)
    assert all("scene_group_id" in beat for beat in beats)
    assert all("scene_group_role" in beat for beat in beats)
    assert all(beat["speech_cue"] is True for beat in beats if beat["semantic_role"] in {"verified_entity_relation", "verified_motion_event"})
    assert all(beat["speech_cue"] is False for beat in beats if beat["semantic_role"] in {"verified_entity_anchor", "verified_motion_anchor", "verified_motion_context", "verified_motion_subject", "verified_motion_source", "verified_motion_target"})
    assert any(beat["speech_cue_basis"] == "visual_anchor_only" and beat["prompt"] == "tree" for beat in beats)
    assert any(beat["speech_cue_basis"] == "verified_evidence_unit" and beat["prompt"] == "apple" for beat in beats)
    speech_groups = {beat["scene_group_id"] for beat in beats if beat["scene_group_role"] == "speech_unit"}
    visual_anchor_groups = {beat["scene_group_id"] for beat in beats if beat["scene_group_role"] == "visual_anchor"}
    assert speech_groups
    assert visual_anchor_groups <= speech_groups
    tree_group = next(beat["scene_group_id"] for beat in beats if beat["prompt"] == "tree")
    assert any(beat["scene_group_id"] == tree_group and beat["scene_group_role"] == "speech_unit" for beat in beats)
    motion_beats = [beat for beat in beats if beat["op"] == "move" and beat.get("motion_path")]
    assert motion_beats
    assert all(beat["motion_path"]["basis"] == "verified_motion_phrase" for beat in motion_beats)
    assert any(beat["motion_path"].get("source_prompt") for beat in motion_beats)
    assert any(beat["motion_path"].get("target_prompt") for beat in motion_beats)
    apple_motion = next(beat for beat in motion_beats if beat["prompt"] == "apple")
    assert apple_motion["particle_behavior"] == "gravity_arc"
    assert apple_motion["scene_directive"]["directive_owner"] == "cgsr_visual_imagination_planner"
    assert apple_motion["scene_directive"]["narrative_function"] == "demonstrate_verified_motion"
    assert apple_motion["scene_directive"]["stage_instruction"] == "animate_verified_motion_path"
    assert apple_motion["scene_directive"]["text_rendering"] == "dom_text_not_particles"
    assert apple_motion["scene_directive"]["particle_text"] is False
    assert apple_motion["scene_directive"]["topic_scene_templates"] is False
    assert apple_motion["scene_evidence"]["source_type"] == "verified_evidence_unit"
    assert apple_motion["scene_evidence"]["prompt_span"] == "apple"
    assert apple_motion["scene_evidence"]["motion_basis"] == "verified_motion_phrase"
    assert apple_motion["scene_evidence"]["motion_source_prompt"] == "tree"
    assert apple_motion["scene_evidence"]["motion_target_prompt"] == "Isaac Newton"
    assert apple_motion["scene_evidence"]["particle_behavior"] == "gravity_arc"
    assert apple_motion["scene_evidence"]["text_rendering"] == "dom_text_not_particles"
    assert apple_motion["scene_evidence"]["particle_text"] is False
    assert apple_motion["scene_evidence"]["topic_scene_templates"] is False
    assert apple_motion["scene_evidence"]["renderer_may_infer_topic"] is False
    assert apple_motion["physics_hint"]["basis"] == "verified_motion_phrase"
    assert apple_motion["physics_hint"]["field"] == "downward_attraction"
    assert apple_motion["physics_hint"]["gravity_bias"] > 0
    assert apple_motion["motion_path"]["from"][1] > apple_motion["motion_path"]["to"][1]
    assert tuple(apple_motion["camera"]["target"]) == tuple(apple_motion["position"])
    assert apple_motion["camera"]["zoom"] > 1.0
    focus_beats = [beat for beat in beats if beat["op"] == "focus_camera"]
    assert focus_beats
    assert all(
        beat["scene_directive"]["stage_instruction"] == "close_up_verified_object"
        for beat in focus_beats
        if beat["speech_cue"] is True
    )
    assert all(tuple(beat["camera"]["target"]) == tuple(beat["position"]) for beat in focus_beats)
    anchor_beats = [beat for beat in beats if beat["speech_cue"] is False and not beat.get("motion_path") and beat["op"] != "move"]
    assert anchor_beats
    assert all(beat["scene_directive"]["stage_instruction"] == "assemble_silent_anchor" for beat in anchor_beats)
    assert plan.scene_choreography["layout_intent"] == "wide_particle_stage"
    assert plan.scene_choreography["scene_extent"]["motion_count"] >= 1
    assert plan.scene_choreography["dashboard_layout"]["planning_basis"] == "scene_geometry_extent"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["decision_owner"] == "cgsr_scene_choreography_agent"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["decision_basis"] == "verified_scene_geometry_and_self_body_clearance_state"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["decision_model"] == "self_body_scene_pressure_scorer_no_topic_templates"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["scene_self_state"]["self_body_identity"] == "atanor_orb_self_body"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["scene_self_state"]["particle_field_pressure"] >= 0.72
    decision_candidates = plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["decision_candidates"]
    assert decision_candidates
    assert decision_candidates[0]["action"] == plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["agent_action"]
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["selected_action_score"] == decision_candidates[0]["score"]
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["selection_reason"] == decision_candidates[0]["reason"]
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["agent_action"] == "yield_center_to_particle_scene"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["text_rendering"] == "dom_text_not_particles"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["content_source"] == "verified_beats_only"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["topic_scene_templates"] is False
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["renderer_may_infer_topic"] is False
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["particle_space"] == "uncovered_dashboard_field_minus_sidebar_composer_and_text"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["generated_visual_elements"] == "particle_points_only"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["flow_motion_reference"] == "codepen_magnetic_swarm_noise_decay_reference"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["text_exception"] == "dom_text_measured_layout_only"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["orb_self_body_yield"] == "orb_moves_and_scales_to_clear_verified_particle_scene"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["orb_movement"] == "lower_right_micro_stage_guard"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["orb_yield_strength"] >= 0.82
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["particle_recomposition_mode"] == "agent_airbend_recompose_verified_beats"
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["scene_geometry_inputs"]["motion_count"] >= 1
    avoidance_map = plan.scene_choreography["dashboard_layout"]["avoidance_map"]
    assert avoidance_map["basis"] == "verified_scene_extent_motion_and_dom_clearance"
    assert avoidance_map["dom_text_only"] is True
    assert avoidance_map["particle_text"] is False
    assert "lower_right" == avoidance_map["orb_reserved_lane"]
    assert "upper_right" in avoidance_map["text_safe_lanes"]
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["avoidance_map"]["basis"] == avoidance_map["basis"]
    assert plan.scene_choreography["dashboard_layout"]["agent_layout_decision"]["text_safe_lanes"] == avoidance_map["text_safe_lanes"]
    assert plan.scene_choreography["dashboard_layout"]["orb"]["anchor"] == "lower_right"
    assert plan.scene_choreography["dashboard_layout"]["orb"]["size_vmin"] < 24
    assert plan.scene_choreography["dashboard_layout"]["speech"]["max_vw"] < 50
    assert plan.scene_choreography["dashboard_layout"]["speech"]["upper_left_top_vh"] < 23
    assert plan.scene_choreography["dashboard_layout"]["speech"]["lower_left_bottom_vh"] < 16
    assert plan.scene_choreography["dashboard_layout"]["speech"]["lower_center_bottom_vh"] < 17
    assert plan.scene_choreography["dashboard_layout"]["self_narration"]["anchor"] == "upper_right"
    assert plan.scene_choreography["dashboard_layout"]["stage_safe_region"]["primary"] == "center_particle_stage"
    assert plan.scene_choreography["dashboard_layout"]["stage_safe_region"]["scale_strategy"] == "fit_verified_particle_stage_inside_uncovered_dashboard"
    assert plan.scene_choreography["dashboard_layout"]["scene"]["generated_visual_elements"] == "particle_points_only"
    assert plan.scene_choreography["dashboard_layout"]["scene"]["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert plan.scene_choreography["dashboard_layout"]["scene"]["text_exception"] == "dom_text_not_particle_geometry"
    decisions = plan.scene_choreography["agent_scene_decisions"]
    assert decisions[0]["decision_id"] == "scene_space_allocation"
    assert decisions[0]["selected_action"] == "yield_center_to_particle_scene"
    assert decisions[0]["decision_model"] == "self_body_scene_pressure_scorer_no_topic_templates"
    assert decisions[0]["scene_self_state"]["self_body_pressure"] > 0
    assert decisions[0]["decision_candidates"][0]["action"] == "yield_center_to_particle_scene"
    assert decisions[0]["selection_reason"] == "verified_motion_or_wide_scene_needs_uncovered_center_particle_stage"
    assert decisions[0]["orb_movement"] == "lower_right_micro_stage_guard"
    assert decisions[0]["orb_yield_strength"] >= 0.82
    assert decisions[0]["topic_scene_templates"] is False
    assert decisions[0]["renderer_may_infer_topic"] is False
    assert decisions[0]["particle_text"] is False
    assert decisions[0]["text_rendering"] == "dom_text_not_particles"
    assert any(item["decision_id"].startswith("speech_beat_layout_") for item in decisions)
    intents = plan.scene_choreography["particle_operation_intents"]
    assert len(intents) == len(beats)
    apple_intent = next(item for item in intents if item["prompt_span"] == "apple" and item["operation"] == "animate_particle_motion_path")
    assert apple_intent["source_fact_hash"] == apple_motion["scene_evidence"]["source_fact_hash"]
    assert apple_intent["agent_control"] == "airbend_recompose_particles_inside_safe_region"
    assert apple_intent["generated_visual_elements"] == "particle_points_only"
    assert apple_intent["line_rendering"] == "particle_segments_not_canvas_strokes"
    assert apple_intent["flow_motion_reference"] == "codepen_magnetic_swarm_noise_decay_reference"
    assert apple_intent["particle_text"] is False
    assert apple_intent["topic_scene_templates"] is False
    assert apple_intent["renderer_may_infer_topic"] is False
    assert all("apple" in beat["source_fact"].casefold() for beat in beats if "apple" in beat["prompt"].casefold())
    assert plan.scene_choreography["topic_scene_templates"] is False
    assert plan.diagnostics["scene_authoring_basis"] == "verified_fact_entity_action_extraction"
