from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from .command_adapter import SplatraSceneCommandSequence


SAFE_QUEUE_FLAGS = {
    "execute_now": False,
    "raw_buffer_in_agent_context": False,
    "topic_scene_templates": False,
    "renderer_may_infer_topic": False,
    "particle_text": False,
    "mutation_performed": False,
    "external_splatra_called": False,
}


@dataclass(frozen=True)
class SplatraCandidateCartridgeJob:
    job_id: str
    request_id: str
    action_id: str
    object_id: str
    op: str
    endpoint: str
    cartridge_format: str
    execution_mode: str
    prompt: str
    archetype: str | None
    semantic_role: str | None
    visual_affordance: str | None
    particle_budget: int | None
    position: list[Any]
    motion_path: dict[str, Any]
    physics_hint: dict[str, Any]
    camera: dict[str, Any]
    quality_gates: dict[str, Any]
    execution: dict[str, Any]
    status: str = "queued_candidate_only"
    external_splatra_called: bool = False
    raw_buffer_in_agent_context: bool = False
    mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplatraCandidateCartridgeQueue:
    queue_id: str
    source_sequence_id: str
    source_plan_id: str
    jobs: list[SplatraCandidateCartridgeJob]
    status: str
    execution_mode: str
    side_channel: str
    external_splatra_called: bool = False
    raw_buffer_in_agent_context: bool = False
    mutation_performed: bool = False
    topic_scene_templates: bool = False
    renderer_may_infer_topic: bool = False
    particle_text: bool = False
    proof_only: bool = True

    @property
    def job_count(self) -> int:
        return len(self.jobs)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["job_count"] = self.job_count
        payload["jobs"] = [job.to_dict() for job in self.jobs]
        return payload


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _sequence_payload(sequence: SplatraSceneCommandSequence | dict[str, Any]) -> dict[str, Any]:
    if isinstance(sequence, SplatraSceneCommandSequence):
        return sequence.to_dict()
    if isinstance(sequence, dict):
        return sequence
    raise TypeError("sequence must be SplatraSceneCommandSequence or dict")


def _require_safe_request(request: dict[str, Any]) -> None:
    if request.get("cartridge_format") != "SPL3_candidate":
        raise ValueError("candidate cartridge request must use SPL3_candidate")
    execution = request.get("execution") if isinstance(request.get("execution"), dict) else {}
    quality = request.get("quality_gates") if isinstance(request.get("quality_gates"), dict) else {}
    if execution.get("execute_now") is not False:
        raise ValueError("candidate cartridge request tried to execute immediately")
    if execution.get("raw_buffer_in_agent_context") is not False:
        raise ValueError("candidate cartridge request tried to expose raw buffers")
    for key in (
        "raw_buffers_in_agent_context",
        "topic_scene_templates",
        "renderer_may_infer_topic",
        "particle_text",
        "mutation_performed",
        "external_splatra_called",
    ):
        if quality.get(key) is True:
            raise ValueError(f"candidate cartridge request violated {key}")


def _job_from_request(request: dict[str, Any], index: int) -> SplatraCandidateCartridgeJob:
    _require_safe_request(request)
    request_id = str(request.get("request_id") or _stable_id("splatra_cart_req", f"{index}:{request}"))
    return SplatraCandidateCartridgeJob(
        job_id=_stable_id("splatra_cart_job", f"{index}:{request_id}:{request.get('action_id')}"),
        request_id=request_id,
        action_id=str(request.get("action_id") or ""),
        object_id=str(request.get("object_id") or ""),
        op=str(request.get("op") or "spawn_object"),
        endpoint=str(request.get("endpoint") or "POST /v1/generate_3d_object"),
        cartridge_format=str(request.get("cartridge_format") or "SPL3_candidate"),
        execution_mode="candidate_only_dry_run",
        prompt=str(request.get("prompt") or ""),
        archetype=request.get("archetype") if isinstance(request.get("archetype"), str) else None,
        semantic_role=request.get("semantic_role") if isinstance(request.get("semantic_role"), str) else None,
        visual_affordance=request.get("visual_affordance") if isinstance(request.get("visual_affordance"), str) else None,
        particle_budget=int(request["particle_budget"]) if isinstance(request.get("particle_budget"), int) else None,
        position=list(request.get("position") or []),
        motion_path=dict(request.get("motion_path") or {}),
        physics_hint=dict(request.get("physics_hint") or {}),
        camera=dict(request.get("camera") or {}),
        quality_gates=dict(request.get("quality_gates") or {}),
        execution=dict(request.get("execution") or {}),
    )


def build_candidate_cartridge_queue(
    sequence: SplatraSceneCommandSequence | dict[str, Any],
) -> SplatraCandidateCartridgeQueue:
    """Build an execution-safe SPLATRA sidecar queue without calling SPLATRA.

    The queue is a candidate-only dry run. It gives ATANOR an explicit set of
    particle cartridge jobs while preserving the SPLATRA boundary: no raw
    buffers enter agent context, no external renderer call is made, and no
    production mutation is performed.
    """

    payload = _sequence_payload(sequence)
    requests = payload.get("candidate_cartridge_requests") if isinstance(payload.get("candidate_cartridge_requests"), list) else []
    jobs = [
        _job_from_request(request, index)
        for index, request in enumerate(requests)
        if isinstance(request, dict)
    ]
    source_sequence_id = str(payload.get("sequence_id") or "unknown_sequence")
    source_plan_id = str(payload.get("source_plan_id") or "unknown_plan")
    return SplatraCandidateCartridgeQueue(
        queue_id=_stable_id("splatra_cart_queue", f"{source_sequence_id}:{len(jobs)}"),
        source_sequence_id=source_sequence_id,
        source_plan_id=source_plan_id,
        jobs=jobs,
        status="ready_for_sidecar" if jobs else "empty",
        execution_mode="candidate_only_dry_run",
        side_channel="GET /v1/cartridge",
    )
