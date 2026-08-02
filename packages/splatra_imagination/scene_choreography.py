from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .models import ARCHETYPES, Archetype, default_safety_flags


SceneBeatOp = Literal["spawn_object", "morph", "move", "focus_camera", "label", "despawn"]
StageLayout = Literal["conversation", "scene_focus"]
OrbAnchor = Literal["center", "lower_right"]
TextAnchor = Literal["auto", "upper_left", "lower_left", "upper_right", "lower_center"]
LayoutIntent = Literal["conversation", "balanced_scene", "wide_particle_stage"]


@dataclass(frozen=True)
class SceneBeat:
    op: SceneBeatOp
    prompt: str = ""
    narration: str = ""
    object_id: str = ""
    object_track_id: str = ""
    object_track_basis: str = ""
    semantic_role: str = ""
    visual_affordance: str = ""
    spatial_relation: str = ""
    pose_hint: str = ""
    surface_features: tuple[str, ...] = field(default_factory=tuple)
    particle_behavior: str = ""
    physics_hint: dict[str, Any] = field(default_factory=dict)
    scene_directive: dict[str, Any] = field(default_factory=dict)
    scene_evidence: dict[str, Any] = field(default_factory=dict)
    source_fact: str = ""
    speech_cue: bool = True
    speech_cue_basis: str = "verified_evidence_unit"
    scene_group_id: str = ""
    scene_group_role: str = ""
    archetype: Archetype | None = None
    t_start: float = 0.0
    duration: float = 1.0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    motion_path: dict[str, Any] = field(default_factory=dict)
    camera: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SceneChoreographyPlan:
    plan_id: str
    stage_layout: StageLayout
    orb_anchor: OrbAnchor
    text_anchor: TextAnchor
    layout_intent: LayoutIntent
    scene_extent: dict[str, Any]
    dashboard_layout: dict[str, Any]
    primary_surface: str
    beats: list[SceneBeat]
    safety_flags: dict[str, bool]
    speech_timeline: list[dict[str, Any]] = field(default_factory=list)
    layout_timeline: list[dict[str, Any]] = field(default_factory=list)
    agent_scene_decisions: list[dict[str, Any]] = field(default_factory=list)
    particle_operation_intents: list[dict[str, Any]] = field(default_factory=list)
    external_splatra_called: bool = False
    raw_buffer_in_agent_context: bool = False
    topic_scene_templates: bool = False
    renderer_may_infer_topic: bool = False
    particle_text: bool = False
    text_rendering: str = "dom_text_not_particles"
    proof_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["beats"] = [beat.to_dict() for beat in self.beats]
        return payload


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _clean_text(value: Any, *, limit: int = 360) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _coerce_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
      number = float(value)
    except (TypeError, ValueError):
      return default
    return max(minimum, min(maximum, number))


def _coerce_position(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return (0.0, 0.0, 0.0)
    return (
        _coerce_float(value[0], 0.0, minimum=-4.0, maximum=4.0),
        _coerce_float(value[1], 0.0, minimum=-4.0, maximum=4.0),
        _coerce_float(value[2], 0.0, minimum=-4.0, maximum=4.0),
    )


def _coerce_motion_path(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    path: dict[str, Any] = {}
    if "from" in value:
        path["from"] = _coerce_position(value.get("from"))
    if "to" in value:
        path["to"] = _coerce_position(value.get("to"))
    if "basis" in value:
        path["basis"] = _clean_text(value.get("basis"), limit=80)
    if "source_prompt" in value:
        path["source_prompt"] = _clean_text(value.get("source_prompt"), limit=96)
    if "target_prompt" in value:
        path["target_prompt"] = _clean_text(value.get("target_prompt"), limit=96)
    return path


def _default_scene_directive(raw: dict[str, Any], op: str, speech_cue: bool, motion_path: dict[str, Any]) -> dict[str, str | bool]:
    semantic_role = _clean_text(raw.get("semantic_role") or raw.get("role") or "", limit=80)
    if op == "move" or motion_path:
        narrative_function = "demonstrate_verified_motion"
        stage_instruction = "animate_verified_motion_path"
    elif not speech_cue or semantic_role.endswith("_anchor"):
        narrative_function = "establish_visual_anchor"
        stage_instruction = "assemble_silent_anchor"
    elif op == "focus_camera":
        narrative_function = "focus_verified_detail"
        stage_instruction = "close_up_verified_object"
    elif "relation" in semantic_role:
        narrative_function = "introduce_verified_relation"
        stage_instruction = "bind_relation_field"
    else:
        narrative_function = "present_verified_beat"
        stage_instruction = "render_verified_particle_beat"
    return {
        "directive_owner": "cgsr_visual_imagination_planner",
        "basis": "verified_scene_beat",
        "narrative_function": narrative_function,
        "stage_instruction": stage_instruction,
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
        "topic_scene_templates": False,
    }


def _coerce_beat(raw: dict[str, Any], index: int) -> SceneBeat:
    op = str(raw.get("op") or "spawn_object")
    if op not in {"spawn_object", "morph", "move", "focus_camera", "label", "despawn"}:
        op = "spawn_object"
    archetype = raw.get("archetype")
    if archetype not in ARCHETYPES:
        archetype = None
    prompt = _clean_text(raw.get("prompt") or raw.get("label") or raw.get("description"))
    narration = _clean_text(raw.get("narration") or raw.get("speech") or "", limit=240)
    object_id = _clean_text(raw.get("object_id") or raw.get("id") or _stable_id("scene_obj", f"{index}:{prompt}"), limit=96)
    object_track_id = _clean_text(raw.get("object_track_id") or raw.get("track_id") or "", limit=96)
    object_track_basis = _clean_text(raw.get("object_track_basis") or "", limit=80)
    semantic_role = _clean_text(raw.get("semantic_role") or raw.get("role") or "", limit=80)
    visual_affordance = _clean_text(raw.get("visual_affordance") or "", limit=80)
    spatial_relation = _clean_text(raw.get("spatial_relation") or "", limit=80)
    raw_physics_hint = raw.get("physics_hint") if isinstance(raw.get("physics_hint"), dict) else {}
    pose_hint = _clean_text(raw.get("pose_hint") or raw_physics_hint.get("pose_hint") or "", limit=40)
    raw_features = raw.get("surface_features") or raw_physics_hint.get("surface_features") or ()
    if isinstance(raw_features, str):
        raw_features = (raw_features,)
    if not isinstance(raw_features, (list, tuple)):
        raw_features = ()
    surface_features = tuple(
        feature for feature in (_clean_text(item, limit=64) for item in raw_features)
        if feature
    )[:12]
    particle_behavior = _clean_text(raw.get("particle_behavior") or "", limit=80)
    physics_hint = raw_physics_hint
    source_fact = _clean_text(raw.get("source_fact") or "", limit=360)
    speech_cue = bool(raw.get("speech_cue", True))
    speech_cue_basis = _clean_text(raw.get("speech_cue_basis") or "verified_evidence_unit", limit=80)
    scene_group_id = _clean_text(raw.get("scene_group_id") or "", limit=96)
    scene_group_role = _clean_text(raw.get("scene_group_role") or "", limit=80)
    motion_path = _coerce_motion_path(raw.get("motion_path"))
    raw_directive = raw.get("scene_directive") if isinstance(raw.get("scene_directive"), dict) else {}
    directive_default = _default_scene_directive(raw, op, speech_cue, motion_path)
    scene_directive = {
        "directive_owner": _clean_text(raw_directive.get("directive_owner") or directive_default["directive_owner"], limit=80),
        "basis": _clean_text(raw_directive.get("basis") or directive_default["basis"], limit=80),
        "narrative_function": _clean_text(raw_directive.get("narrative_function") or directive_default["narrative_function"], limit=80),
        "stage_instruction": _clean_text(raw_directive.get("stage_instruction") or directive_default["stage_instruction"], limit=80),
        "visual_affordance": _clean_text(raw_directive.get("visual_affordance") or visual_affordance, limit=80),
        "speech_sync": _clean_text(raw_directive.get("speech_sync") or ("speech_timeline" if speech_cue else "visual_anchor_only"), limit=80),
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
        "topic_scene_templates": False,
    }
    raw_evidence = raw.get("scene_evidence") if isinstance(raw.get("scene_evidence"), dict) else {}
    raw_evidence_features = raw_evidence.get("surface_features")
    if not isinstance(raw_evidence_features, list):
        raw_evidence_features = list(surface_features)
    scene_evidence = {
        "evidence_owner": _clean_text(raw_evidence.get("evidence_owner") or scene_directive["directive_owner"], limit=80),
        "source_type": _clean_text(raw_evidence.get("source_type") or "verified_evidence_unit", limit=80),
        "source_fact_hash": _clean_text(raw_evidence.get("source_fact_hash") or "", limit=80),
        "prompt_span": _clean_text(raw_evidence.get("prompt_span") or prompt, limit=120),
        "narration_span": _clean_text(raw_evidence.get("narration_span") or narration, limit=240),
        "semantic_role": _clean_text(raw_evidence.get("semantic_role") or semantic_role, limit=80),
        "visual_affordance": _clean_text(raw_evidence.get("visual_affordance") or visual_affordance, limit=80),
        "spatial_relation": _clean_text(raw_evidence.get("spatial_relation") or spatial_relation, limit=80),
        "surface_features": [
            feature for feature in raw_evidence_features
            if isinstance(feature, str)
        ][:12],
        "motion_basis": _clean_text(raw_evidence.get("motion_basis") or motion_path.get("basis") or "", limit=80),
        "motion_source_prompt": _clean_text(raw_evidence.get("motion_source_prompt") or motion_path.get("source_prompt") or "", limit=96),
        "motion_target_prompt": _clean_text(raw_evidence.get("motion_target_prompt") or motion_path.get("target_prompt") or "", limit=96),
        "particle_behavior": _clean_text(raw_evidence.get("particle_behavior") or particle_behavior, limit=80),
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
    }
    return SceneBeat(
        op=op,  # type: ignore[arg-type]
        prompt=prompt,
        narration=narration,
        object_id=object_id,
        object_track_id=object_track_id,
        object_track_basis=object_track_basis,
        semantic_role=semantic_role,
        visual_affordance=visual_affordance,
        spatial_relation=spatial_relation,
        pose_hint=pose_hint,
        surface_features=surface_features,
        particle_behavior=particle_behavior,
        physics_hint=physics_hint,
        scene_directive=scene_directive,
        scene_evidence=scene_evidence,
        source_fact=source_fact,
        speech_cue=speech_cue,
        speech_cue_basis=speech_cue_basis,
        scene_group_id=scene_group_id,
        scene_group_role=scene_group_role,
        archetype=archetype,  # type: ignore[arg-type]
        t_start=_coerce_float(raw.get("t_start"), index * 1.25, minimum=0.0, maximum=600.0),
        duration=_coerce_float(raw.get("duration"), 1.0, minimum=0.1, maximum=60.0),
        position=_coerce_position(raw.get("position")),
        motion_path=motion_path,
        camera=raw.get("camera") if isinstance(raw.get("camera"), dict) else {},
    )


def _coerce_text_anchor(value: Any, stage_layout: StageLayout) -> TextAnchor:
    text_anchor = str(value or "auto")
    if text_anchor not in {"auto", "upper_left", "lower_left", "upper_right", "lower_center"}:
        text_anchor = "auto"
    if text_anchor == "auto" and stage_layout == "scene_focus":
        return "lower_left"
    return text_anchor  # type: ignore[return-value]


def _coerce_layout_intent(value: Any, stage_layout: StageLayout, beats: list[SceneBeat]) -> LayoutIntent:
    if stage_layout == "conversation":
        return "conversation"
    layout_intent = str(value or "")
    if layout_intent in {"balanced_scene", "wide_particle_stage"}:
        return layout_intent  # type: ignore[return-value]
    motion_count = sum(1 for beat in beats if beat.op == "move" or beat.motion_path)
    if len(beats) >= 4 or motion_count:
        return "wide_particle_stage"
    return "balanced_scene"


def _scene_extent(beats: list[SceneBeat]) -> dict[str, Any]:
    points: list[tuple[float, float]] = []
    motion_count = 0
    for beat in beats:
        points.append((beat.position[0], beat.position[1]))
        if beat.motion_path:
            motion_count += 1
            raw_from = beat.motion_path.get("from")
            raw_to = beat.motion_path.get("to")
            if isinstance(raw_from, tuple) and len(raw_from) >= 2:
                points.append((float(raw_from[0]), float(raw_from[1])))
            if isinstance(raw_to, tuple) and len(raw_to) >= 2:
                points.append((float(raw_to[0]), float(raw_to[1])))
    if not points:
        return {"beat_count": 0, "motion_count": 0, "spread_x": 0.0, "spread_y": 0.0}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "beat_count": len(beats),
        "motion_count": motion_count,
        "spread_x": round(max(xs) - min(xs), 3),
        "spread_y": round(max(ys) - min(ys), 3),
        "min_x": round(min(xs), 3),
        "max_x": round(max(xs), 3),
        "min_y": round(min(ys), 3),
        "max_y": round(max(ys), 3),
    }


def _scene_self_pressure_state(load: float, layout_intent: LayoutIntent, scene_extent: dict[str, Any]) -> dict[str, Any]:
    """Summarize the agent's layout state from scene evidence and self-body constraints."""

    motion_count = float(scene_extent.get("motion_count") or 0.0)
    beat_count = float(scene_extent.get("beat_count") or 0.0)
    spread_x = float(scene_extent.get("spread_x") or 0.0)
    spread_y = float(scene_extent.get("spread_y") or 0.0)
    particle_field_pressure = min(1.0, max(0.0, load + motion_count * 0.08 + max(spread_x, spread_y) * 0.08))
    self_body_pressure = min(1.0, max(0.0, 0.28 + load * 0.48 + motion_count * 0.08))
    text_clearance_pressure = min(1.0, max(0.0, 0.22 + load * 0.38 + beat_count * 0.025))
    composer_clearance_pressure = min(1.0, max(0.0, 0.18 + (0.22 if layout_intent == "wide_particle_stage" else 0.0) + spread_y * 0.08))
    return {
        "state_owner": "cgsr_scene_choreography_agent",
        "state_basis": "verified_scene_geometry_plus_self_body_constraints",
        "self_body_identity": "atanor_orb_self_body",
        "particle_field_pressure": round(particle_field_pressure, 3),
        "self_body_pressure": round(self_body_pressure, 3),
        "text_clearance_pressure": round(text_clearance_pressure, 3),
        "composer_clearance_pressure": round(composer_clearance_pressure, 3),
        "scene_complexity": {
            "beat_count": int(beat_count),
            "motion_count": int(motion_count),
            "spread_x": round(spread_x, 3),
            "spread_y": round(spread_y, 3),
            "layout_intent": layout_intent,
        },
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
    }


def _layout_decision_candidates(load: float, layout_intent: LayoutIntent, scene_extent: dict[str, Any], self_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Score orb/stage placement alternatives from scene/self pressure, not topic words."""

    motion_count = float(scene_extent.get("motion_count") or 0.0)
    beat_count = float(scene_extent.get("beat_count") or 0.0)
    spread_x = float(scene_extent.get("spread_x") or 0.0)
    spread_y = float(scene_extent.get("spread_y") or 0.0)
    wide_bonus = 0.18 if layout_intent == "wide_particle_stage" else 0.0
    self_body_pressure = float(self_state.get("self_body_pressure") or 0.0)
    particle_field_pressure = float(self_state.get("particle_field_pressure") or 0.0)
    text_clearance_pressure = float(self_state.get("text_clearance_pressure") or 0.0)
    composer_clearance_pressure = float(self_state.get("composer_clearance_pressure") or 0.0)
    candidates = [
        {
            "action": "keep_orb_primary",
            "score": round(max(0.0, 1.0 - particle_field_pressure - self_body_pressure * 0.22 - wide_bonus), 3),
            "orb_movement": "center",
            "reason": "conversation_space_has_priority_when_verified_particle_load_is_low",
            "score_components": {
                "particle_field_pressure": particle_field_pressure,
                "self_body_pressure": self_body_pressure,
                "text_clearance_pressure": text_clearance_pressure,
            },
        },
        {
            "action": "share_center_with_particle_scene",
            "score": round(max(0.0, 0.38 + beat_count * 0.032 + spread_x * 0.06 + spread_y * 0.05 - max(0.0, particle_field_pressure - 0.7) * 0.42), 3),
            "orb_movement": "lower_right_scaled_down",
            "reason": "moderate_verified_scene_load_can_share_center_with_orb",
            "score_components": {
                "particle_field_pressure": particle_field_pressure,
                "self_body_pressure": self_body_pressure,
                "text_clearance_pressure": text_clearance_pressure,
                "composer_clearance_pressure": composer_clearance_pressure,
            },
        },
        {
            "action": "yield_center_to_particle_scene",
            "score": round(max(0.0, 0.2 + particle_field_pressure * 0.62 + self_body_pressure * 0.18 + motion_count * 0.12 + wide_bonus), 3),
            "orb_movement": "lower_right_micro_stage_guard" if load >= 0.82 else "lower_right_scaled_down",
            "reason": "verified_motion_or_wide_scene_needs_uncovered_center_particle_stage",
            "score_components": {
                "particle_field_pressure": particle_field_pressure,
                "self_body_pressure": self_body_pressure,
                "text_clearance_pressure": text_clearance_pressure,
                "composer_clearance_pressure": composer_clearance_pressure,
            },
        },
    ]
    return sorted(candidates, key=lambda item: float(item["score"]), reverse=True)


def _client_layout_feedback_state(value: Any) -> dict[str, Any]:
    """Read client DOM collision telemetry without using it as scene content."""

    if not isinstance(value, dict):
        return {
            "feedback_basis": "none",
            "layout_feedback_used": False,
            "collision_state": "none",
            "pressure": 0.0,
            "overlap_px": 0.0,
            "offscreen_px": 0.0,
            "orb_overlap_px": 0.0,
            "orb_offscreen_px": 0.0,
            "text_rendering": "dom_text_not_particles",
            "particle_text": False,
        }
    overlap_px = _coerce_float(value.get("overlap_px"), 0.0, minimum=0.0, maximum=2000.0)
    offscreen_px = _coerce_float(value.get("offscreen_px"), 0.0, minimum=0.0, maximum=2000.0)
    orb_overlap_px = _coerce_float(value.get("orb_overlap_px"), 0.0, minimum=0.0, maximum=2000.0)
    orb_offscreen_px = _coerce_float(value.get("orb_offscreen_px"), 0.0, minimum=0.0, maximum=2000.0)
    pressure = min(1.0, overlap_px / 260.0 + offscreen_px / 340.0 + orb_overlap_px / 220.0 + orb_offscreen_px / 320.0)
    collision_state = _clean_text(value.get("collision_state") or "none", limit=48)
    feedback_basis = _clean_text(value.get("feedback_basis") or "client_dom_scene_collision_telemetry", limit=96)
    return {
        "feedback_basis": feedback_basis,
        "layout_feedback_used": feedback_basis != "none",
        "collision_state": collision_state,
        "pressure": round(pressure, 3),
        "overlap_px": round(overlap_px, 2),
        "offscreen_px": round(offscreen_px, 2),
        "orb_overlap_px": round(orb_overlap_px, 2),
        "orb_offscreen_px": round(orb_offscreen_px, 2),
        "speech_anchor": _clean_text(value.get("speech_anchor") or "", limit=32),
        "self_narration_anchor": _clean_text(value.get("self_narration_anchor") or "", limit=32),
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
        "content_used_for_scene_generation": False,
    }


def _dashboard_layout(
    stage_layout: StageLayout,
    orb_anchor: OrbAnchor,
    text_anchor: TextAnchor,
    layout_intent: LayoutIntent,
    scene_extent: dict[str, Any],
    client_layout_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive dashboard placement from scene geometry, not subject templates."""

    client_feedback = _client_layout_feedback_state(client_layout_feedback)
    if stage_layout != "scene_focus":
        return {
            "planning_basis": "conversation_default",
            "stage": stage_layout,
            "layout_intent": layout_intent,
            "orb": {"anchor": "center"},
            "speech": {"anchor": text_anchor},
            "scene": {"field_opacity": 0.72},
            "agent_layout_decision": {
                "decision_owner": "cgsr_scene_choreography_agent",
                "decision_basis": "conversation_default",
                "scene_geometry_inputs": dict(scene_extent),
                "topic_scene_templates": False,
                "agent_action": "keep_orb_primary",
                "text_rendering": "dom_text_not_particles",
                "content_source": "conversation_without_visual_scene",
                "client_layout_feedback": client_feedback,
            },
        }

    beat_count = float(scene_extent.get("beat_count") or 0.0)
    motion_count = float(scene_extent.get("motion_count") or 0.0)
    spread_x = float(scene_extent.get("spread_x") or 0.0)
    spread_y = float(scene_extent.get("spread_y") or 0.0)
    load = min(1.0, max(0.0, 0.18 + beat_count * 0.08 + motion_count * 0.2 + spread_x * 0.22 + spread_y * 0.18))
    if layout_intent == "wide_particle_stage":
        load = max(load, 0.72)
    load = min(1.0, load + float(client_feedback.get("pressure") or 0.0) * 0.18)
    orb_movement = "lower_right_micro_stage_guard" if load >= 0.82 else "lower_right_scaled_down"
    self_state = _scene_self_pressure_state(load, layout_intent, scene_extent)
    decision_candidates = _layout_decision_candidates(load, layout_intent, scene_extent, self_state)
    selected_candidate = decision_candidates[0] if decision_candidates else {
        "action": "share_center_with_particle_scene",
        "score": 0.0,
        "orb_movement": orb_movement,
        "reason": "fallback_geometry_decision",
    }
    selected_action = str(selected_candidate.get("action") or ("yield_center_to_particle_scene" if load >= 0.72 else "share_center_with_particle_scene"))
    if float(client_feedback.get("pressure") or 0.0) >= 0.35:
        selected_candidate = {
            **selected_candidate,
            "orb_movement": "lower_right_micro_stage_guard",
            "reason": f"{selected_candidate.get('reason', 'verified_scene_geometry')};client_dom_collision_feedback",
        }
        if selected_action == "keep_orb_primary":
            selected_action = "share_center_with_particle_scene"

    orb_size_vmin = round(25.0 - load * 7.5, 2)
    orb_min_px = round(170.0 - load * 38.0)
    orb_max_px = round(262.0 - load * 44.0)
    orb_right_vw = round(12.0 - load * 3.4, 2)
    orb_bottom_vh = round(18.2 - load * 4.1, 2)
    speech_max_vw = round(50.0 - load * 14.0, 2)
    speech_right_vw = round(29.0 - load * 5.0, 2)
    speech_bottom_vh = round(18.0 - load * 2.0, 2)
    upper_left_top_vh = round(23.0 - load * 4.2, 2)
    upper_right_top_vh = round(17.0 + load * 3.8, 2)
    lower_left_bottom_vh = round((15.2 - load * 3.7) if layout_intent == "wide_particle_stage" else (16.0 + load * 3.2), 2)
    lower_center_bottom_vh = round((16.0 - load * 3.0) if layout_intent == "wide_particle_stage" else (17.0 + load * 3.4), 2)
    self_narration_top_vh = round(16.0 - load * 2.2, 2)
    self_narration_right_vw = round(8.0 - load * 1.4, 2)
    self_narration_max_vw = round(28.0 - load * 4.0, 2)
    footprint_padding = round(0.14 + load * 0.16, 3)
    stage_min_x = max(-1.0, float(scene_extent.get("min_x") or -0.34) - footprint_padding)
    stage_max_x = min(1.0, float(scene_extent.get("max_x") or 0.34) + footprint_padding)
    stage_min_y = max(-0.86, float(scene_extent.get("min_y") or -0.28) - footprint_padding)
    stage_max_y = min(0.86, float(scene_extent.get("max_y") or 0.28) + footprint_padding)
    if layout_intent == "wide_particle_stage":
        # Keep the visual particle field wide, but reserve a smaller DOM-text
        # blocking footprint. The renderer may still use the surrounding dark
        # dashboard space for particles; speech, self narration, and the
        # composer need stable lanes that are not treated as occupied.
        stage_min_x = max(-0.88, min(stage_min_x, -0.72))
        stage_max_x = min(0.88, max(stage_max_x, 0.72))
        stage_min_y = max(-0.5, min(stage_min_y, -0.44))
        stage_max_y = min(0.46, max(stage_max_y, 0.4))
    text_safe_lanes = [
        "upper_left",
        "upper_right",
        "lower_left",
        "lower_center",
    ]
    if layout_intent == "wide_particle_stage":
        # The center is owned by the verified particle scene; keep DOM text in
        # perimeter lanes and let the client choose the least crowded lane from
        # measured geometry.
        text_safe_lanes = ["upper_left", "upper_right", "lower_left"]
    avoidance_map = {
        "map_owner": "cgsr_scene_choreography_agent",
        "basis": "verified_scene_extent_motion_and_dom_clearance",
        "scene_footprint": {
            "min_x": round(stage_min_x, 3),
            "max_x": round(stage_max_x, 3),
            "min_y": round(stage_min_y, 3),
            "max_y": round(stage_max_y, 3),
        },
        "orb_reserved_lane": "lower_right",
        "composer_reserved_lane": "bottom_center",
        "text_safe_lanes": text_safe_lanes,
        "self_narration_preferred_lane": "upper_right" if load >= 0.72 else "upper_left",
        "dom_text_only": True,
        "particle_text": False,
        "topic_scene_templates": False,
    }

    return {
        "planning_basis": "scene_geometry_extent",
        "stage": stage_layout,
        "layout_intent": layout_intent,
        "stage_pressure": round(load, 3),
        "scene_self_state": self_state,
        "orb": {
            "anchor": orb_anchor,
            "size_vmin": orb_size_vmin,
            "min_px": orb_min_px,
            "max_px": orb_max_px,
            "right_vw": orb_right_vw,
            "bottom_vh": orb_bottom_vh,
        },
        "speech": {
            "anchor": text_anchor,
            "max_vw": speech_max_vw,
            "right_vw": speech_right_vw,
            "bottom_vh": speech_bottom_vh,
            "upper_left_top_vh": upper_left_top_vh,
            "upper_right_top_vh": upper_right_top_vh,
            "lower_left_bottom_vh": lower_left_bottom_vh,
            "lower_center_bottom_vh": lower_center_bottom_vh,
        },
        "self_narration": {
            "anchor": "upper_right" if load >= 0.72 else "upper_left",
            "top_vh": self_narration_top_vh,
            "right_vw": self_narration_right_vw,
            "max_vw": self_narration_max_vw,
        },
        "stage_safe_region": {
            "primary": "center_particle_stage",
            "orb_exclusion": "lower_right",
            "text_exclusion": text_anchor,
            "composer_exclusion": "bottom_center",
            "scale_strategy": "fit_verified_particle_stage_inside_uncovered_dashboard",
            "footprint": {
                "basis": "verified_scene_geometry_extent",
                "min_x": round(stage_min_x, 3),
                "max_x": round(stage_max_x, 3),
                "min_y": round(stage_min_y, 3),
                "max_y": round(stage_max_y, 3),
                "block_text": True,
            },
        },
        "avoidance_map": avoidance_map,
        "scene": {
            "field_opacity": round(0.9 + load * 0.07, 3),
            "central_scale": round(1.0 + load * 0.14, 3),
            "generated_visual_elements": "particle_points_only",
            "line_rendering": "particle_segments_not_canvas_strokes",
            "text_exception": "dom_text_not_particle_geometry",
        },
        "agent_layout_decision": {
            "decision_owner": "cgsr_scene_choreography_agent",
            "decision_basis": "verified_scene_geometry_and_self_body_clearance_state",
            "decision_model": "self_body_scene_pressure_scorer_no_topic_templates",
            "decision_candidates": decision_candidates,
            "client_layout_feedback": client_feedback,
            "selected_action_score": selected_candidate.get("score", 0.0),
            "selection_reason": selected_candidate.get("reason", "verified_scene_geometry"),
            "scene_geometry_inputs": dict(scene_extent),
            "scene_self_state": self_state,
            "topic_scene_templates": False,
            "agent_action": selected_action,
            "orb_movement": selected_candidate.get("orb_movement") or orb_movement,
            "orb_identity": "atanor_self_body_not_scene_object",
            "layout_autonomy": "agent_authored_from_verified_scene_geometry_and_client_feedback",
            "text_strategy": "dom_text_collision_avoidance",
            "text_rendering": "dom_text_not_particles",
            "scene_region": "dashboard_center",
            "particle_stage_strategy": "airbend_recompose_particles_inside_safe_region",
            "particle_space": "uncovered_dashboard_field_minus_sidebar_composer_and_text",
            "generated_visual_elements": "particle_points_only",
            "line_rendering": "particle_segments_not_canvas_strokes",
            "flow_motion_reference": "codepen_magnetic_swarm_noise_decay_reference",
            "text_exception": "dom_text_measured_layout_only",
            "orb_self_body_yield": "orb_moves_and_scales_to_clear_verified_particle_scene",
            "orb_yield_strength": round(load, 3),
            "particle_recomposition_mode": "agent_airbend_recompose_verified_beats",
            "avoid_regions": ["orb", "composer", "self_narration", "scene_motion_paths"],
            "avoidance_map": avoidance_map,
            "text_safe_lanes": text_safe_lanes,
            "content_source": "verified_beats_only",
            "renderer_may_infer_topic": False,
        },
    }


def _speech_timeline(beats: list[SceneBeat]) -> list[dict[str, Any]]:
    """Expose verified speech beats as a renderer timeline without inventing text."""

    timeline: list[dict[str, Any]] = []
    previous_text = ""
    for index, beat in enumerate(beats):
        if beat.speech_cue is False:
            continue
        text = _clean_text(beat.narration or beat.prompt, limit=240)
        if not text or text == previous_text:
            continue
        previous_text = text
        timeline.append({
            "beat_index": index,
            "object_id": beat.object_id,
            "object_track_id": beat.object_track_id,
            "object_track_basis": beat.object_track_basis,
            "scene_group_id": beat.scene_group_id,
            "scene_group_role": beat.scene_group_role,
            "text": text,
            "text_source": "verified_beat_narration",
            "speech_cue_basis": beat.speech_cue_basis,
            "t_start": beat.t_start,
            "duration": beat.duration,
            "particle_behavior": beat.particle_behavior,
            "physics_hint": dict(beat.physics_hint),
            "scene_directive": dict(beat.scene_directive),
            "scene_evidence": dict(beat.scene_evidence),
            "motion_path": dict(beat.motion_path),
            "semantic_role": beat.semantic_role,
            "visual_affordance": beat.visual_affordance,
        })
    return timeline


def _layout_timeline(stage_layout: StageLayout, dashboard_layout: dict[str, Any], beats: list[SceneBeat]) -> list[dict[str, Any]]:
    """Expose orb/text/stage placement decisions as geometry-derived actions."""

    decision = dashboard_layout.get("agent_layout_decision") if isinstance(dashboard_layout.get("agent_layout_decision"), dict) else {}
    default_text_anchor = dashboard_layout.get("speech", {}).get("anchor", "lower_left")
    default_self_anchor = dashboard_layout.get("self_narration", {}).get("anchor", "upper_right")
    if stage_layout != "scene_focus":
        return [{
            "t_start": 0.0,
            "duration": 999.0,
            "action": "keep_orb_primary",
            "decision_owner": "cgsr_scene_choreography_agent",
            "decision_basis": "conversation_default",
            "orb_anchor": "center",
            "text_anchor": "lower_center",
            "self_narration_anchor": "upper_right",
            "text_rendering": "dom_text_not_particles",
            "stage_region": "conversation_center",
        }]

    timeline = [{
        "t_start": 0.0,
        "duration": 999.0,
        "action": decision.get("agent_action") or "share_center_with_particle_scene",
        "decision_owner": decision.get("decision_owner") or "cgsr_scene_choreography_agent",
        "decision_basis": decision.get("decision_basis") or "verified_scene_geometry_and_self_body_clearance_state",
        "decision_model": decision.get("decision_model") or "self_body_scene_pressure_scorer_no_topic_templates",
        "selected_action_score": decision.get("selected_action_score", 0.0),
        "selection_reason": decision.get("selection_reason") or "verified_scene_geometry",
        "orb_anchor": dashboard_layout.get("orb", {}).get("anchor", "lower_right"),
        "orb_movement": decision.get("orb_movement") or "lower_right_scaled_down",
        "orb_identity": decision.get("orb_identity") or "atanor_self_body_not_scene_object",
        "text_anchor": default_text_anchor,
        "self_narration_anchor": default_self_anchor,
        "text_rendering": decision.get("text_rendering") or "dom_text_not_particles",
        "text_strategy": decision.get("text_strategy") or "dom_text_collision_avoidance",
        "stage_region": decision.get("scene_region") or "dashboard_center",
        "particle_stage_strategy": decision.get("particle_stage_strategy") or "airbend_recompose_particles_inside_safe_region",
        "particle_space": decision.get("particle_space") or "uncovered_dashboard_field_minus_sidebar_composer_and_text",
        "generated_visual_elements": decision.get("generated_visual_elements") or "particle_points_only",
        "line_rendering": decision.get("line_rendering") or "particle_segments_not_canvas_strokes",
        "flow_motion_reference": decision.get("flow_motion_reference") or "codepen_magnetic_swarm_noise_decay_reference",
        "text_exception": decision.get("text_exception") or "dom_text_measured_layout_only",
        "orb_self_body_yield": decision.get("orb_self_body_yield") or "orb_moves_and_scales_to_clear_verified_particle_scene",
        "particle_recomposition_mode": decision.get("particle_recomposition_mode") or "agent_airbend_recompose_verified_beats",
        "layout_autonomy": decision.get("layout_autonomy") or "agent_authored_from_verified_scene_geometry_and_client_feedback",
        "scene_self_state": dict(decision.get("scene_self_state") or dashboard_layout.get("scene_self_state") or {}),
    }]
    for index, beat in enumerate(beats):
        if beat.speech_cue is False:
            continue
        active_layout_points = _active_beat_layout_points(beat)
        active_layout_state = _active_beat_layout_state(beat)
        timeline.append({
            "t_start": beat.t_start,
            "duration": beat.duration,
            "action": "sync_orb_text_with_particle_beat",
            "decision_owner": decision.get("decision_owner") or "cgsr_scene_choreography_agent",
            "decision_basis": "verified_speech_cue_beat",
            "decision_model": decision.get("decision_model") or "self_body_scene_pressure_scorer_no_topic_templates",
            "beat_index": index,
            "scene_group_id": beat.scene_group_id,
            "object_id": beat.object_id,
            "object_track_id": beat.object_track_id,
            "object_track_basis": beat.object_track_basis,
            "orb_anchor": dashboard_layout.get("orb", {}).get("anchor", "lower_right"),
            "orb_movement": _orb_movement_for_active_beat(beat, decision.get("orb_movement") or "lower_right_scaled_down"),
            "orb_identity": decision.get("orb_identity") or "atanor_self_body_not_scene_object",
            "text_anchor": _text_anchor_for_active_beat(beat, default_text_anchor),
            "text_anchor_basis": _text_anchor_basis_for_active_beat(beat, default_text_anchor),
            "text_anchor_points": len(active_layout_points),
            "active_layout_pressure": active_layout_state["active_layout_pressure"],
            "active_bbox": dict(active_layout_state["active_bbox"]),
            "active_regions": list(active_layout_state["active_regions"]),
            "orb_scale_hint": active_layout_state["orb_scale_hint"],
            "text_safe_region": active_layout_state["text_safe_region"],
            "self_narration_anchor": default_self_anchor,
            "text_rendering": "dom_text_not_particles",
            "stage_region": "dashboard_center",
            "particle_stage_strategy": decision.get("particle_stage_strategy") or "airbend_recompose_particles_inside_safe_region",
            "particle_space": decision.get("particle_space") or "uncovered_dashboard_field_minus_sidebar_composer_and_text",
            "generated_visual_elements": decision.get("generated_visual_elements") or "particle_points_only",
            "line_rendering": decision.get("line_rendering") or "particle_segments_not_canvas_strokes",
            "flow_motion_reference": decision.get("flow_motion_reference") or "codepen_magnetic_swarm_noise_decay_reference",
            "text_exception": decision.get("text_exception") or "dom_text_measured_layout_only",
            "orb_self_body_yield": decision.get("orb_self_body_yield") or "orb_moves_and_scales_to_clear_verified_particle_scene",
            "particle_recomposition_mode": decision.get("particle_recomposition_mode") or "agent_airbend_recompose_verified_beats",
            "layout_autonomy": decision.get("layout_autonomy") or "agent_authored_from_verified_scene_geometry_and_client_feedback",
            "scene_self_state": dict(decision.get("scene_self_state") or dashboard_layout.get("scene_self_state") or {}),
            "particle_behavior": beat.particle_behavior,
            "scene_directive": dict(beat.scene_directive),
            "scene_evidence": dict(beat.scene_evidence),
        })
    return timeline


def _agent_scene_decisions(
    stage_layout: StageLayout,
    layout_intent: LayoutIntent,
    dashboard_layout: dict[str, Any],
    scene_extent: dict[str, Any],
    beats: list[SceneBeat],
) -> list[dict[str, Any]]:
    """Expose why the agent gave dashboard space to particles.

    The renderer should be able to audit an agent-authored scene without
    smuggling in topic templates. These decisions only cite geometry,
    evidence spans, and renderer safety constraints.
    """

    decision = dashboard_layout.get("agent_layout_decision") if isinstance(dashboard_layout.get("agent_layout_decision"), dict) else {}
    safe_region = dashboard_layout.get("stage_safe_region") if isinstance(dashboard_layout.get("stage_safe_region"), dict) else {}
    footprint = safe_region.get("footprint") if isinstance(safe_region.get("footprint"), dict) else {}
    decisions: list[dict[str, Any]] = [
        {
            "decision_id": "scene_space_allocation",
            "decision_owner": decision.get("decision_owner") or "cgsr_scene_choreography_agent",
            "decision_basis": decision.get("decision_basis") or ("verified_scene_geometry" if stage_layout == "scene_focus" else "conversation_default"),
            "stage_layout": stage_layout,
            "layout_intent": layout_intent,
            "selected_action": decision.get("agent_action") or ("share_center_with_particle_scene" if stage_layout == "scene_focus" else "keep_orb_primary"),
            "scene_geometry_inputs": dict(scene_extent),
            "scene_self_state": dict(decision.get("scene_self_state") or dashboard_layout.get("scene_self_state") or {}),
            "decision_model": decision.get("decision_model") or "self_body_scene_pressure_scorer_no_topic_templates",
            "decision_candidates": list(decision.get("decision_candidates") or []),
            "selected_action_score": decision.get("selected_action_score", 0.0),
            "selection_reason": decision.get("selection_reason") or "verified_scene_geometry",
            "particle_space": decision.get("particle_space") or ("uncovered_dashboard_field_minus_sidebar_composer_and_text" if stage_layout == "scene_focus" else "orb_local_field"),
            "orb_self_body_yield": decision.get("orb_self_body_yield") or ("orb_moves_and_scales_to_clear_verified_particle_scene" if stage_layout == "scene_focus" else "none"),
            "orb_movement": decision.get("orb_movement") or ("lower_right_scaled_down" if stage_layout == "scene_focus" else "center"),
            "orb_yield_strength": decision.get("orb_yield_strength") or dashboard_layout.get("stage_pressure") or 0,
            "text_policy": decision.get("text_exception") or "dom_text_measured_layout_only",
            "generated_visual_elements": decision.get("generated_visual_elements") or "particle_points_only",
            "line_rendering": decision.get("line_rendering") or "particle_segments_not_canvas_strokes",
            "flow_motion_reference": decision.get("flow_motion_reference") or "codepen_magnetic_swarm_noise_decay_reference",
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
            "particle_text": False,
            "text_rendering": "dom_text_not_particles",
        },
        {
            "decision_id": "safe_region_fit",
            "decision_owner": decision.get("decision_owner") or "cgsr_scene_choreography_agent",
            "decision_basis": "dashboard_uncovered_region_fit",
            "stage_layout": stage_layout,
            "footprint": dict(footprint),
            "scale_strategy": safe_region.get("scale_strategy") or "fit_verified_particle_stage_inside_uncovered_dashboard",
            "avoid_regions": list(decision.get("avoid_regions") or ["orb", "composer", "self_narration"]),
            "particle_recomposition_mode": decision.get("particle_recomposition_mode") or "agent_airbend_recompose_verified_beats",
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
        },
    ]
    default_text_anchor = dashboard_layout.get("speech", {}).get("anchor", "lower_left")
    for index, beat in enumerate(beats):
        if beat.speech_cue is False:
            continue
        active_layout_state = _active_beat_layout_state(beat)
        decisions.append(
            {
                "decision_id": f"speech_beat_layout_{index}",
                "decision_owner": decision.get("decision_owner") or "cgsr_scene_choreography_agent",
                "decision_basis": "verified_speech_cue_beat",
                "scene_self_state": dict(decision.get("scene_self_state") or dashboard_layout.get("scene_self_state") or {}),
                "beat_index": index,
                "object_id": beat.object_id,
                "object_track_id": beat.object_track_id,
                "object_track_basis": beat.object_track_basis,
                "scene_group_id": beat.scene_group_id,
                "semantic_role": beat.semantic_role,
                "text_anchor": _text_anchor_for_active_beat(beat, default_text_anchor),
                "text_anchor_basis": _text_anchor_basis_for_active_beat(beat, default_text_anchor),
                "orb_movement": _orb_movement_for_active_beat(beat, decision.get("orb_movement") or "lower_right_scaled_down"),
                "active_layout_pressure": active_layout_state["active_layout_pressure"],
                "active_bbox": dict(active_layout_state["active_bbox"]),
                "active_regions": list(active_layout_state["active_regions"]),
                "orb_scale_hint": active_layout_state["orb_scale_hint"],
                "text_safe_region": active_layout_state["text_safe_region"],
                "particle_behavior": beat.particle_behavior,
                "scene_directive": dict(beat.scene_directive),
                "scene_evidence": dict(beat.scene_evidence),
                "particle_space": decision.get("particle_space") or "uncovered_dashboard_field_minus_sidebar_composer_and_text",
                "line_rendering": decision.get("line_rendering") or "particle_segments_not_canvas_strokes",
                "text_rendering": "dom_text_not_particles",
                "particle_text": False,
                "topic_scene_templates": False,
                "renderer_may_infer_topic": False,
            }
        )
    return decisions


def _particle_operation_for_beat(beat: SceneBeat) -> str:
    if beat.op == "move" or beat.motion_path:
        return "animate_particle_motion_path"
    if beat.op == "focus_camera":
        return "focus_particle_cluster"
    if beat.op == "morph":
        return "recompose_particle_cluster"
    if beat.op == "despawn":
        return "disperse_particle_cluster"
    return "assemble_particle_cluster"


def _particle_operation_intents(beats: list[SceneBeat]) -> list[dict[str, Any]]:
    """Return SPLATRA-facing particle operations without raw particle buffers."""

    intents: list[dict[str, Any]] = []
    for index, beat in enumerate(beats):
        operation = _particle_operation_for_beat(beat)
        evidence = dict(beat.scene_evidence)
        intents.append(
            {
                "intent_id": _stable_id("particle_intent", f"{index}:{beat.object_id}:{operation}:{beat.prompt}"),
                "beat_index": index,
                "object_id": beat.object_id,
                "object_track_id": beat.object_track_id,
                "object_track_basis": beat.object_track_basis,
                "operation": operation,
                "op": beat.op,
                "prompt_span": evidence.get("prompt_span") or beat.prompt,
                "narration_span": evidence.get("narration_span") or beat.narration,
                "source_fact_hash": evidence.get("source_fact_hash") or "",
                "semantic_role": beat.semantic_role,
                "visual_affordance": beat.visual_affordance,
                "particle_behavior": beat.particle_behavior,
                "physics_hint": dict(beat.physics_hint),
                "motion_path": dict(beat.motion_path),
                "scene_directive": dict(beat.scene_directive),
                "scene_evidence": evidence,
                "agent_control": "airbend_recompose_particles_inside_safe_region",
                "generated_visual_elements": "particle_points_only",
                "line_rendering": "particle_segments_not_canvas_strokes",
                "flow_motion_reference": "codepen_magnetic_swarm_noise_decay_reference",
                "text_rendering": "dom_text_not_particles",
                "particle_text": False,
                "topic_scene_templates": False,
                "renderer_may_infer_topic": False,
                "external_splatra_called": False,
                "raw_buffer_in_agent_context": False,
                "mutation_performed": False,
            }
        )
    return intents


def _orb_movement_for_active_beat(beat: SceneBeat, fallback: Any) -> str:
    """Nudge the orb away from the active verified particle focus."""

    fallback_movement = str(fallback or "lower_right_scaled_down")
    layout_state = _active_beat_layout_state(beat)
    points = list(layout_state["points"])
    if not points:
        return fallback_movement
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    pressure = float(layout_state["active_layout_pressure"])
    if pressure >= 0.78:
        return "lower_right_lifted_micro" if min_y <= -0.18 else "lower_right_micro_stage_guard"
    if pressure >= 0.64 and (max_x >= 0.18 or min_y <= -0.24):
        return "lower_right_micro_stage_guard"
    if max_x >= 0.32 and min_y <= -0.12:
        return "lower_right_lifted_compact"
    if max_x >= 0.32:
        return "lower_right_tucked_compact"
    if min_y <= -0.34:
        return "lower_right_lifted"
    if max_y >= 0.42:
        return "lower_right_low_compact"
    return fallback_movement


def _active_beat_layout_points(beat: SceneBeat) -> list[tuple[float, float]]:
    """Collect verified scene coordinates that can collide with DOM text."""

    points: list[tuple[float, float]] = []
    if beat.position and len(beat.position) >= 2:
        points.append((float(beat.position[0]), float(beat.position[1])))
    if beat.motion_path:
        for key in ("from", "to"):
            raw_point = beat.motion_path.get(key)
            if isinstance(raw_point, tuple) and len(raw_point) >= 2:
                points.append((float(raw_point[0]), float(raw_point[1])))
    return points


def _active_beat_layout_state(beat: SceneBeat) -> dict[str, Any]:
    """Summarize active beat occupancy for text/orb layout.

    The state is derived only from authored scene geometry and verified motion
    endpoints. It does not inspect the topic and it does not make text into
    particles; it only gives the dashboard a local clearance map.
    """

    points = _active_beat_layout_points(beat)
    if not points:
        return {
            "points": [],
            "active_layout_pressure": 0.0,
            "active_bbox": {
                "basis": "no_active_verified_geometry",
                "min_x": 0.0,
                "max_x": 0.0,
                "min_y": 0.0,
                "max_y": 0.0,
            },
            "active_regions": [],
            "orb_scale_hint": "fallback",
            "text_safe_region": "fallback_anchor",
            "particle_text": False,
        }
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    spread_x = max_x - min_x
    spread_y = max_y - min_y
    center_crossing = min_x <= 0.16 and max_x >= -0.16 and min_y <= 0.16 and max_y >= -0.16
    behavior = str(beat.particle_behavior or "")
    visual_affordance = str(beat.visual_affordance or "")
    motion_bonus = 0.24 if beat.motion_path or beat.op == "move" else 0.0
    behavior_bonus = 0.18 if behavior in {"gravity_arc", "kinetic_flow"} else 0.1 if behavior else 0.0
    affordance_bonus = 0.12 if visual_affordance in {"entity_figure", "organic_structure"} else 0.08 if visual_affordance else 0.0
    pressure = min(1.0, max(0.0, 0.18 + spread_x * 0.42 + spread_y * 0.42 + motion_bonus + behavior_bonus + affordance_bonus + (0.1 if center_crossing else 0.0)))
    regions: list[str] = []
    if center_crossing:
        regions.append("center_stage")
    if max_x >= 0.26:
        regions.append("right_stage")
    if min_x <= -0.26:
        regions.append("left_stage")
    if max_y >= 0.26:
        regions.append("upper_stage")
    if min_y <= -0.26:
        regions.append("lower_stage")
    if not regions:
        regions.append("local_cluster")
    if pressure >= 0.72:
        orb_scale_hint = "micro_self_body_yield"
    elif pressure >= 0.54:
        orb_scale_hint = "compact_self_body_yield"
    else:
        orb_scale_hint = "normal_self_body_clearance"
    text_safe_region = _text_anchor_for_active_beat(beat, "lower_left")
    padding = 0.12 + pressure * 0.08
    return {
        "points": points,
        "active_layout_pressure": round(pressure, 3),
        "active_bbox": {
            "basis": "active_verified_beat_position_and_motion_path",
            "min_x": round(max(-1.0, min_x - padding), 3),
            "max_x": round(min(1.0, max_x + padding), 3),
            "min_y": round(max(-0.92, min_y - padding), 3),
            "max_y": round(min(0.92, max_y + padding), 3),
        },
        "active_regions": regions,
        "orb_scale_hint": orb_scale_hint,
        "text_safe_region": text_safe_region,
        "particle_text": False,
    }


def _text_anchor_clearance_score(anchor: TextAnchor, points: list[tuple[float, float]], fallback: str) -> float:
    """Score text anchors by clearance from active verified geometry.

    This is not topic scripting: only scene coordinates and motion endpoints
    influence the placement.
    """

    anchor_points = {
        "upper_left": (-0.72, 0.58),
        "lower_left": (-0.72, -0.72),
        "upper_right": (0.72, 0.58),
        "lower_center": (0.0, -0.78),
    }
    target_x, target_y = anchor_points.get(anchor, anchor_points["lower_left"])
    crowding = 0.0
    high_motion = False
    low_motion = False
    for x, y in points:
        distance = max(0.12, ((x - target_x) ** 2 + (y - target_y) ** 2) ** 0.5)
        crowding += 1.0 / distance
        high_motion = high_motion or y >= 0.12
        low_motion = low_motion or y <= -0.32
    vertical_penalty = 0.0
    if high_motion and anchor.startswith("lower"):
        vertical_penalty += 0.42
    if low_motion and anchor.startswith("upper") and not high_motion:
        vertical_penalty += 0.18
    composer_penalty = 0.58 if anchor == "lower_center" else 0.08 if anchor == "lower_left" else 0.0
    fallback_bonus = -0.16 if anchor == fallback else 0.0
    return crowding + vertical_penalty + composer_penalty + fallback_bonus


def _text_anchor_for_active_beat(beat: SceneBeat, fallback: Any) -> TextAnchor:
    """Place current speech away from the active verified particle focus."""

    fallback_anchor = str(fallback or "lower_left")
    if fallback_anchor not in {"upper_left", "lower_left", "upper_right", "lower_center"}:
        fallback_anchor = "lower_left"
    points = _active_beat_layout_points(beat)
    if not points:
        return fallback_anchor  # type: ignore[return-value]
    avg_x = sum(point[0] for point in points) / len(points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    if avg_x <= -0.18:
        return "upper_right"
    if avg_x >= 0.18:
        return "upper_left"
    if min_y <= -0.32 and max_y >= 0.12:
        return "lower_left"
    candidates: list[TextAnchor] = ["lower_left", "upper_left", "upper_right", "lower_center"]
    return min(candidates, key=lambda anchor: _text_anchor_clearance_score(anchor, points, fallback_anchor))


def _text_anchor_basis_for_active_beat(beat: SceneBeat, fallback: Any) -> str:
    fallback_anchor = str(fallback or "lower_left")
    points = _active_beat_layout_points(beat)
    if not points:
        return f"fallback_anchor:{fallback_anchor}"
    avg_x = sum(point[0] for point in points) / len(points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    has_motion = bool(beat.motion_path)
    if avg_x <= -0.18 or avg_x >= 0.18:
        return "verified_motion_path_horizontal_clearance" if has_motion else "verified_position_horizontal_clearance"
    if min_y <= -0.32 and max_y >= 0.12:
        return "verified_vertical_motion_path_conversational_clearance"
    return "verified_geometry_clearance_score"


def compile_scene_choreography(plan: dict[str, Any]) -> SceneChoreographyPlan:
    """Validate an agent-authored SPLATRA scene plan without inventing content.

    This is the boundary needed for non-template visual explanation: the
    conversation/scene agent may author beats, while this module only clamps,
    validates, and marks the dashboard layout that should host them.
    """

    raw_beats = plan.get("beats") if isinstance(plan.get("beats"), list) else []
    beats = [_coerce_beat(item, index) for index, item in enumerate(raw_beats[:32]) if isinstance(item, dict)]
    stage_layout: StageLayout = "scene_focus" if plan.get("stage_layout") == "scene_focus" or beats else "conversation"
    orb_anchor: OrbAnchor = "lower_right" if stage_layout == "scene_focus" or plan.get("orb_anchor") == "lower_right" else "center"
    text_anchor = _coerce_text_anchor(plan.get("text_anchor"), stage_layout)
    layout_intent = _coerce_layout_intent(plan.get("layout_intent"), stage_layout, beats)
    scene_extent = _scene_extent(beats)
    client_layout_feedback = plan.get("client_layout_feedback") if isinstance(plan.get("client_layout_feedback"), dict) else {}
    dashboard_layout = _dashboard_layout(
        stage_layout,
        orb_anchor,
        text_anchor,
        layout_intent,
        scene_extent,
        client_layout_feedback,
    )
    speech_timeline = _speech_timeline(beats)
    layout_timeline = _layout_timeline(stage_layout, dashboard_layout, beats)
    agent_scene_decisions = _agent_scene_decisions(stage_layout, layout_intent, dashboard_layout, scene_extent, beats)
    particle_operation_intents = _particle_operation_intents(beats)
    seed = f"{stage_layout}:{orb_anchor}:{text_anchor}:{layout_intent}:{[(beat.op, beat.prompt, beat.object_id) for beat in beats]}"
    return SceneChoreographyPlan(
        plan_id=_stable_id("scene_choreo", seed),
        stage_layout=stage_layout,
        orb_anchor=orb_anchor,
        text_anchor=text_anchor,
        layout_intent=layout_intent,
        scene_extent=scene_extent,
        dashboard_layout=dashboard_layout,
        primary_surface="splatra_stage" if stage_layout == "scene_focus" else "conversation",
        beats=beats,
        speech_timeline=speech_timeline,
        layout_timeline=layout_timeline,
        agent_scene_decisions=agent_scene_decisions,
        particle_operation_intents=particle_operation_intents,
        safety_flags=default_safety_flags(),
    )
