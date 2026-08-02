from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .generator import ImaginationGenerator, select_archetype
from .models import Archetype, ImaginationFrame, ImaginationSeed, default_safety_flags
from .scene_choreography import SceneBeat, SceneChoreographyPlan, compile_scene_choreography


SceneCommand = Literal["spawn_object", "morph", "render_knowledge_hologram", "move", "focus_camera", "label", "despawn"]


@dataclass(frozen=True)
class SplatraCommandPlan:
    plan_id: str
    command: str
    scene_command: SceneCommand
    archetype: Archetype
    prompt: str
    scene_action: dict[str, Any]
    splatra_contract: dict[str, Any]
    safety_flags: dict[str, bool]
    external_splatra_called: bool = False
    raw_buffer_in_agent_context: bool = False
    proof_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplatraSceneCommandSequence:
    sequence_id: str
    source_plan_id: str
    scene_actions: list[dict[str, Any]]
    candidate_cartridge_requests: list[dict[str, Any]]
    splatra_contract: dict[str, Any]
    hot_swap_policy: dict[str, Any]
    particle_motion_policy: dict[str, Any]
    safety_flags: dict[str, bool]
    external_splatra_called: bool = False
    raw_buffer_in_agent_context: bool = False
    proof_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip())[:480]


def _select_command_archetype(command: str, explicit_archetype: Archetype | None = None) -> Archetype:
    if explicit_archetype:
        return explicit_archetype
    selected = select_archetype(f"splatra_command:{command}", curiosity=0.72)
    return "constellation" if selected == "orb" else selected


def _splatra_contract() -> dict[str, Any]:
    return {
        "compatible_source": "Cozystone/SPLATRA",
        "source_observed_url": "https://github.com/Cozystone/SPLATRA",
        "contract_basis": "side_channel_cartridge_handles_no_raw_buffers",
        "tool_schema": [
            "spawn_object",
            "morph",
            "move",
            "focus_camera",
            "label",
            "despawn",
            "render_knowledge_hologram",
        ],
        "compatible_endpoints": [
            "POST /v1/chat",
            "POST /v1/generate_3d_object",
            "POST /v1/render_knowledge_hologram",
            "GET /v1/cartridge",
            "WS /ws/viewer",
        ],
        "agent_context_payload": "sgf_summary_and_command_sequence_only",
        "side_channel": "viewer pulls cartridge; agent context gets summary only",
        "cartridge_side_channel_required": True,
        "raw_buffers_in_agent_context": False,
        "spl2_or_spl3_cartridge_ready": False,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
    }


def _particle_motion_policy() -> dict[str, Any]:
    return {
        "basis": "verified_scene_choreography",
        "field_model": "magnetic_swarm_noise_decay_reference",
        "inspiration": "codepen_magnetic_swarm_noise_decay_reference",
        "particle_marks_only": True,
        "flow_lines": "sparse_particle_marks_not_canvas_paths",
        "text_rendering": "dom_text_not_particles",
        "agent_control": "airbend_recompose_particles_inside_safe_region",
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
    }


def _beat_position(position: tuple[float, float, float]) -> list[float]:
    return [float(position[0]), float(position[1]), float(position[2])]


def _beat_scene_action(beat: SceneBeat, index: int, *, particle_budget: int) -> dict[str, Any]:
    action_id = _stable_id("splatra_action", f"{index}:{beat.op}:{beat.object_id}:{beat.prompt}:{beat.t_start}")
    args: dict[str, Any] = {
        "id": beat.object_id or _stable_id("obj", f"{index}:{beat.prompt}"),
        "track_id": beat.object_track_id,
        "track_basis": beat.object_track_basis,
        "prompt": beat.prompt,
        "archetype": beat.archetype,
        "semantic_role": beat.semantic_role,
        "visual_affordance": beat.visual_affordance,
        "spatial_relation": beat.spatial_relation,
        "position": _beat_position(beat.position),
        "particle_budget": max(64, min(int(particle_budget), 100_000)),
        "t_start": beat.t_start,
        "duration": beat.duration,
        "particle_behavior": beat.particle_behavior,
        "pose_hint": beat.pose_hint,
        "surface_features": list(beat.surface_features),
        "scene_group_id": beat.scene_group_id,
        "scene_group_role": beat.scene_group_role,
        "speech_cue": beat.speech_cue,
        "speech_cue_basis": beat.speech_cue_basis,
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
    }
    if beat.motion_path:
        args["motion_path"] = dict(beat.motion_path)
    if beat.physics_hint:
        args["physics_hint"] = dict(beat.physics_hint)
    if beat.camera:
        args["camera"] = dict(beat.camera)
    if beat.scene_directive:
        args["scene_directive"] = dict(beat.scene_directive)
    if beat.scene_evidence:
        args["scene_evidence"] = dict(beat.scene_evidence)
    if beat.narration:
        args["narration"] = beat.narration
        args["narration_source"] = "verified_beat_narration"
    if beat.source_fact:
        args["source_fact"] = beat.source_fact

    return {
        "id": action_id,
        "op": beat.op,
        "args": args,
        "version": 1,
        "execute_js": False,
        "mutation_performed": False,
        "raw_buffer_in_agent_context": False,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
    }


def _candidate_cartridge_request(action: dict[str, Any], index: int) -> dict[str, Any]:
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    request_id = _stable_id(
        "splatra_cart_req",
        f"{action.get('id')}:{action.get('op')}:{args.get('id')}:{args.get('prompt')}:{args.get('t_start')}",
    )
    evidence = args.get("scene_evidence") if isinstance(args.get("scene_evidence"), dict) else {}
    directive = args.get("scene_directive") if isinstance(args.get("scene_directive"), dict) else {}
    return {
        "request_id": request_id,
        "action_id": action.get("id"),
        "object_id": args.get("id"),
        "track_id": args.get("track_id"),
        "op": action.get("op"),
        "endpoint": "POST /v1/generate_3d_object" if action.get("op") in {"spawn_object", "morph", "move"} else "POST /v1/chat",
        "cartridge_format": "SPL3_candidate",
        "cartridge_role": "viewer_side_channel_candidate",
        "input_basis": "verified_scene_action",
        "prompt": args.get("prompt", ""),
        "archetype": args.get("archetype"),
        "semantic_role": args.get("semantic_role"),
        "visual_affordance": args.get("visual_affordance"),
        "particle_budget": args.get("particle_budget"),
        "position": args.get("position"),
        "motion_path": args.get("motion_path") if isinstance(args.get("motion_path"), dict) else {},
        "physics_hint": args.get("physics_hint") if isinstance(args.get("physics_hint"), dict) else {},
        "camera": args.get("camera") if isinstance(args.get("camera"), dict) else {},
        "timing": {
            "t_start": args.get("t_start"),
            "duration": args.get("duration"),
            "sequence_index": index,
        },
        "quality_gates": {
            "source_type": evidence.get("source_type", "verified_evidence_unit"),
            "source_fact_hash": evidence.get("source_fact_hash", ""),
            "directive_basis": directive.get("basis", "verified_scene_beat"),
            "particle_text": False,
            "text_rendering": "dom_text_not_particles",
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
            "raw_buffers_in_agent_context": False,
            "mutation_performed": False,
            "external_splatra_called": False,
        },
        "execution": {
            "status": "candidate_request_only",
            "execute_now": False,
            "viewer_fetch_after_swap_ready": True,
            "agent_context_receives": "request_summary_only",
            "raw_buffer_in_agent_context": False,
        },
    }


def compile_splatra_command(
    command: str,
    *,
    particle_budget: int = 1600,
    mode: str = "product",
    scene_command: SceneCommand = "spawn_object",
    archetype: Archetype | None = None,
) -> tuple[SplatraCommandPlan, ImaginationFrame]:
    """Compile an ATANOR visual command into a bounded SPLATRA scene action.

    This function intentionally does not infer topic-specific content such as
    "gravity means apple tree". Upstream ATANOR scene planning must author
    those beats. This adapter only validates and packages a command/action
    contract, keeping raw 3D buffers out of the agent context.
    """

    normalized = _normalize_command(command) or "abstract particle object"
    selected_archetype = _select_command_archetype(normalized, archetype)
    plan_id = _stable_id("splatra_cmd", f"{scene_command}:{selected_archetype}:{normalized}")
    object_id = _stable_id("obj", normalized)
    scene_action = {
        "op": scene_command,
        "args": {
            "id": object_id,
            "prompt": normalized,
            "archetype": selected_archetype,
            "position": [0.0, 0.0, 0.0],
            "quality": "procedural_proof",
            "particle_budget": max(64, min(int(particle_budget), 100_000)),
        },
        "version": 1,
        "execute_js": False,
        "mutation_performed": False,
    }
    splatra_contract = _splatra_contract()
    seed = ImaginationSeed(
        seed_id=plan_id,
        archetype=selected_archetype,
        randomness=0.61,
        valence=0.12,
        arousal=0.62 if mode == "product" else 0.7,
        curiosity=0.78,
        particle_budget=max(64, min(int(particle_budget), 100_000)),
        state="imagining",
        created_at="splatra_command_adapter",
    )
    frame = ImaginationGenerator(max_particle_budget=100_000).generate_frame(seed)
    item = frame.objects[0]
    item.metadata["splatra_command_plan"] = {
        "plan_id": plan_id,
        "scene_command": scene_command,
        "prompt": normalized,
        "scene_action": scene_action,
        "splatra_contract": splatra_contract,
    }
    return (
        SplatraCommandPlan(
            plan_id=plan_id,
            command=normalized,
            scene_command=scene_command,
            archetype=selected_archetype,
            prompt=normalized,
            scene_action=scene_action,
            splatra_contract=splatra_contract,
            safety_flags=default_safety_flags(),
        ),
        frame,
    )


def compile_scene_choreography_commands(
    choreography: SceneChoreographyPlan | dict[str, Any],
    *,
    particle_budget: int = 8_000,
) -> SplatraSceneCommandSequence:
    """Package verified scene choreography as SPLATRA viewer-side commands.

    The adapter does not decide that a topic should become a tree, apple, or
    any other object. It only preserves agent-authored, evidence-backed beats
    and gives the SPLATRA viewer a bounded sequence of particle operations.
    Raw Gaussian buffers stay on the cartridge side channel.
    """

    plan = compile_scene_choreography(choreography) if isinstance(choreography, dict) else choreography
    scene_actions = [
        _beat_scene_action(beat, index, particle_budget=particle_budget)
        for index, beat in enumerate(plan.beats)
    ]
    cartridge_requests = [
        _candidate_cartridge_request(action, index)
        for index, action in enumerate(scene_actions)
    ]
    sequence_id = _stable_id("splatra_seq", f"{plan.plan_id}:{len(scene_actions)}:{particle_budget}")
    return SplatraSceneCommandSequence(
        sequence_id=sequence_id,
        source_plan_id=plan.plan_id,
        scene_actions=scene_actions,
        candidate_cartridge_requests=cartridge_requests,
        splatra_contract=_splatra_contract(),
        hot_swap_policy={
            "mode": "candidate_only",
            "state_machine": "IDLE_TO_GENERATING_TO_SWAP_READY_TO_DISPLAYED",
            "viewer_side_channel": "GET /v1/cartridge",
            "websocket_signal": "WS /ws/viewer",
            "candidate_request_count": len(cartridge_requests),
            "commit_to_store": False,
            "mutation_performed": False,
            "raw_buffers_in_agent_context": False,
        },
        particle_motion_policy=_particle_motion_policy(),
        safety_flags=default_safety_flags(),
    )
