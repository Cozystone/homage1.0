from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from .models import default_safety_flags
from .scene_choreography import SceneBeat, SceneChoreographyPlan, compile_scene_choreography


Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class BoundingBox3D:
    min: Point3
    max: Point3
    center: Point3
    extent: Point3
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InteractiveSceneObject:
    object_id: str
    object_track_id: str
    label: str
    semantic_role: str
    visual_affordance: str
    bounding_box: BoundingBox3D
    interactions: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    source_beat_indices: list[int] = field(default_factory=list)
    analyzer_basis: str = "scene_choreography_object_tracks"
    raw_splat_inference: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bounding_box"] = self.bounding_box.to_dict()
        return payload


@dataclass(frozen=True)
class InteractiveSceneAnalysis:
    analysis_id: str
    source_plan_id: str
    interactive_scene: bool
    object_count: int
    objects: list[InteractiveSceneObject]
    spatial_index: list[dict[str, Any]]
    analyzer_contract: dict[str, Any]
    safety_flags: dict[str, bool]
    proof_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "objects": [item.to_dict() for item in self.objects],
        }


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _point(value: Any) -> Point3:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (_as_float(value[0]), _as_float(value[1]), _as_float(value[2]))
    return (0.0, 0.0, 0.0)


def _visual_extent(beat: SceneBeat) -> Point3:
    affordance = (beat.visual_affordance or "").lower()
    role = (beat.semantic_role or "").lower()
    op = (beat.op or "").lower()
    if "field" in affordance or "relation" in role:
        return (0.46, 0.30, 0.20)
    if "anchor" in role or "structure" in affordance or beat.archetype in {"tree", "tower", "city_block"}:
        return (0.34, 0.56, 0.24)
    if "figure" in affordance or "entity" in role or beat.archetype == "creature":
        return (0.24, 0.42, 0.18)
    if "small" in affordance or op == "move":
        return (0.14, 0.14, 0.14)
    return (0.24, 0.24, 0.18)


def _bbox_for_points(points: list[Point3], padding: Point3, *, basis: str) -> BoundingBox3D:
    if not points:
        points = [(0.0, 0.0, 0.0)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    min_point = (min(xs) - padding[0], min(ys) - padding[1], min(zs) - padding[2])
    max_point = (max(xs) + padding[0], max(ys) + padding[1], max(zs) + padding[2])
    center = (
        (min_point[0] + max_point[0]) / 2.0,
        (min_point[1] + max_point[1]) / 2.0,
        (min_point[2] + max_point[2]) / 2.0,
    )
    extent = (
        max_point[0] - min_point[0],
        max_point[1] - min_point[1],
        max_point[2] - min_point[2],
    )
    return BoundingBox3D(min=min_point, max=max_point, center=center, extent=extent, basis=basis)


def _beat_points(beat: SceneBeat) -> list[Point3]:
    points = [beat.position]
    path = beat.motion_path if isinstance(beat.motion_path, dict) else {}
    if "from" in path:
        points.append(_point(path.get("from")))
    if "to" in path:
        points.append(_point(path.get("to")))
    target = beat.camera.get("target") if isinstance(beat.camera, dict) else None
    if target is not None:
        points.append(_point(target))
    return points


def _interaction_handles(beat: SceneBeat, object_id: str) -> list[dict[str, Any]]:
    base = [
        {
            "type": "select",
            "target": object_id,
            "mutation_performed": False,
            "basis": "interactive_scene_metadata",
        },
        {
            "type": "highlight",
            "target": object_id,
            "mutation_performed": False,
            "basis": "verified_scene_track",
        },
        {
            "type": "focus_camera",
            "target": object_id,
            "mutation_performed": False,
            "basis": "viewer_camera_only",
        },
        {
            "type": "show_evidence",
            "target": object_id,
            "mutation_performed": False,
            "basis": "source_fact_ref",
        },
    ]
    if beat.op == "move" or beat.motion_path:
        base.append({
            "type": "animate_path",
            "target": object_id,
            "motion_path": dict(beat.motion_path),
            "mutation_performed": False,
            "basis": "verified_motion_path",
        })
    return base


def _evidence_ref(beat: SceneBeat) -> dict[str, Any]:
    evidence = dict(beat.scene_evidence) if isinstance(beat.scene_evidence, dict) else {}
    return {
        "source_type": evidence.get("source_type", "verified_evidence_unit"),
        "source_fact_hash": evidence.get("source_fact_hash", ""),
        "prompt_span": evidence.get("prompt_span") or beat.prompt,
        "narration_span": evidence.get("narration_span") or beat.narration,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
        "particle_text": False,
        "text_rendering": "dom_text_not_particles",
    }


def _merge_unique(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def analyze_scene_choreography(choreography: SceneChoreographyPlan | dict[str, Any]) -> InteractiveSceneAnalysis:
    """Build Splat-Analyzer-inspired interactive metadata from ATANOR scene tracks.

    This is deliberately not a claim of zero-shot object detection over raw
    Gaussian buffers. It structures the agent-authored, evidence-backed scene
    beats into persistent object tracks, bounding boxes, and safe viewer
    interactions so a later raw SPL2/SPL3/SPZ analyzer can plug into the same
    contract without exposing raw buffers to the agent context.
    """

    plan = compile_scene_choreography(choreography) if isinstance(choreography, dict) else choreography
    grouped: dict[str, dict[str, Any]] = {}
    for index, beat in enumerate(plan.beats):
        object_id = beat.object_id or _stable_id("scene_obj", f"{index}:{beat.prompt}:{beat.op}")
        track_id = beat.object_track_id or object_id
        entry = grouped.setdefault(track_id, {
            "object_id": object_id,
            "track_id": track_id,
            "label": beat.prompt or object_id,
            "semantic_role": beat.semantic_role,
            "visual_affordance": beat.visual_affordance,
            "points": [],
            "padding": [],
            "interactions": [],
            "evidence_refs": [],
            "operations": [],
            "source_beat_indices": [],
        })
        if not entry["semantic_role"] and beat.semantic_role:
            entry["semantic_role"] = beat.semantic_role
        if not entry["visual_affordance"] and beat.visual_affordance:
            entry["visual_affordance"] = beat.visual_affordance
        entry["points"].extend(_beat_points(beat))
        entry["padding"].append(_visual_extent(beat))
        entry["interactions"].extend(_interaction_handles(beat, object_id))
        entry["evidence_refs"].append(_evidence_ref(beat))
        entry["operations"].append(beat.op)
        entry["source_beat_indices"].append(index)

    objects: list[InteractiveSceneObject] = []
    for entry in grouped.values():
        padding = max(entry["padding"], key=lambda value: value[0] * value[1] * value[2]) if entry["padding"] else (0.24, 0.24, 0.18)
        bbox = _bbox_for_points(
            entry["points"],
            padding,
            basis="scene_track_positions_motion_paths_and_visual_affordance_extent",
        )
        objects.append(InteractiveSceneObject(
            object_id=str(entry["object_id"]),
            object_track_id=str(entry["track_id"]),
            label=str(entry["label"]),
            semantic_role=str(entry["semantic_role"] or ""),
            visual_affordance=str(entry["visual_affordance"] or ""),
            bounding_box=bbox,
            interactions=_merge_unique(entry["interactions"]),
            evidence_refs=_merge_unique(entry["evidence_refs"]),
            operations=_merge_unique(entry["operations"]),
            source_beat_indices=list(entry["source_beat_indices"]),
        ))

    objects.sort(key=lambda item: (item.object_track_id, item.object_id))
    spatial_index = [
        {
            "object_track_id": item.object_track_id,
            "object_id": item.object_id,
            "center": item.bounding_box.center,
            "extent": item.bounding_box.extent,
            "interaction_count": len(item.interactions),
        }
        for item in objects
    ]
    safety_flags = {
        **default_safety_flags(),
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "raw_buffer_in_agent_context": False,
        "mock_growth": False,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
        "particle_text": False,
    }
    contract = {
        "inspiration": "splat_analyzer_structured_interactive_scene",
        "analyzer_basis": "scene_choreography_object_tracks",
        "zero_setup_object_detection": "scene_track_structuring_only",
        "object_detection_claim": "planned_from_agent_scene_tracks_not_raw_splat_inference",
        "raw_splat_inference": False,
        "raw_buffers_in_agent_context": False,
        "persistent_3d_bounding_boxes": True,
        "interactive_scene_metadata": True,
        "viewer_can_select_move_focus": True,
        "mutation_performed": False,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
        "particle_text": False,
        "text_rendering": "dom_text_not_particles",
        "future_upgrade_path": "replace_scene_track_basis_with_raw_spl2_spl3_spz_detector_after_quality_gate",
    }
    return InteractiveSceneAnalysis(
        analysis_id=_stable_id("splatra_scene_analysis", f"{plan.plan_id}:{len(objects)}"),
        source_plan_id=plan.plan_id,
        interactive_scene=bool(objects),
        object_count=len(objects),
        objects=objects,
        spatial_index=spatial_index,
        analyzer_contract=contract,
        safety_flags=safety_flags,
    )
