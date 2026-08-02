from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .cartridge_queue import SplatraCandidateCartridgeJob, SplatraCandidateCartridgeQueue


Transport = Callable[[str, str, dict[str, Any] | None, float], dict[str, Any]]
SPLATRA_QUALITY_PROFILES = {"fast", "realistic", "high", "learned", "gpu"}


VISUAL_PROMPT_KO_EN = {
    "사실적인": "realistic",
    "실사": "photorealistic",
    "고품질": "high quality",
    "투명한": "transparent",
    "반투명": "translucent",
    "유리": "transparent glass",
    "금속": "metal",
    "나무 재질": "wooden",
    "물체": "object",
    "물": "water",
    "모래": "sand",
    "사과": "red apple",
    "바나나": "banana",
    "딸기": "strawberry",
    "오렌지": "orange fruit",
    "피카츄": "pikachu, yellow pokemon",
    "포켓몬": "pokemon",
    "강아지": "puppy dog",
    "고양이": "cat",
    "토끼": "rabbit",
    "곰": "teddy bear",
    "공룡": "dinosaur",
    "자동차": "car",
    "비행기": "airplane",
    "로켓": "rocket",
    "배": "ship",
    "집": "house",
    "나무": "tree",
    "꽃": "flower",
    "별": "star",
    "하트": "red heart",
    "컵": "coffee cup",
    "책": "book",
    "시계": "clock",
    "축구공": "soccer ball",
    "버섯": "mushroom",
    "케이크": "cake",
    "도넛": "donut",
    "햄버거": "hamburger",
    "우산": "umbrella",
    "달": "moon",
    "지구": "planet earth",
    "왕관": "golden crown",
}

VISUAL_PROMPT_STOPWORDS = (
    "SPLATRA",
    "splatra",
    "파티클",
    "입자",
    "모델",
    "홀로그램",
    "카트리지",
    "직접",
    "생성해줘",
    "생성",
    "만들어줘",
    "만들어",
    "보여줘",
    "렌더링해줘",
    "렌더링",
    "3D",
    "삼차원",
    "으로",
    "로",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
)


@dataclass(frozen=True)
class SplatraSidecarJobResult:
    job_id: str
    request_id: str
    object_id: str
    prompt: str
    endpoint: str
    status: str
    external_splatra_called: bool
    raw_buffer_in_agent_context: bool
    mutation_performed: bool
    sidecar_job_id: str | None = None
    sidecar_state: str | None = None
    poll_url: str | None = None
    viewer_side_channel: str = "GET /v1/cartridge"
    viewer_cartridge_url: str | None = None
    sgf_summary: dict[str, Any] | None = None
    generation_engine: str | None = None
    real_generator_used: bool = False
    events: list[dict[str, Any]] | None = None
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplatraSidecarDispatchResult:
    status: str
    configured: bool
    sidecar_url: str | None
    jobs: list[SplatraSidecarJobResult]
    external_splatra_called: bool = False
    raw_buffer_in_agent_context: bool = False
    mutation_performed: bool = False
    cartridge_side_channel: str = "GET /v1/cartridge"
    raw_cartridge_fetched: bool = False
    proof_only: bool = True

    @property
    def job_count(self) -> int:
        return len(self.jobs)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["job_count"] = self.job_count
        payload["jobs"] = [job.to_dict() for job in self.jobs]
        return payload


def configured_sidecar_url() -> str | None:
    """Return the optional SPLATRA sidecar URL.

    Absence is the safe default. ATANOR can package cartridge requests without
    calling SPLATRA; a real sidecar call only happens when the operator provides
    SPLATRA_SIDECAR_URL or ATANOR_SPLATRA_SIDECAR_URL.
    """

    raw = os.environ.get("SPLATRA_SIDECAR_URL") or os.environ.get("ATANOR_SPLATRA_SIDECAR_URL")
    if not raw:
        return None
    return raw.rstrip("/")


def _http_json(method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        body = response.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _safe_shape(job: SplatraCandidateCartridgeJob) -> str | None:
    if job.archetype in {"orb", "tree", "creature", "machine_core", "small_object"}:
        return job.archetype
    if job.visual_affordance in {"entity_figure", "physical_object", "organic_structure"}:
        return str(job.visual_affordance)
    return None


def _sidecar_visual_prompt(prompt: str, fallback: str) -> str:
    """Normalize visual-generation prompts for SPLATRA's English CLIP path.

    This is not an answer template and does not author scene content. It only
    preserves material/object words already present in the user's visual request
    so the sidecar generator receives a usable text-to-image prompt.
    """

    out = prompt or fallback
    for ko, en in sorted(VISUAL_PROMPT_KO_EN.items(), key=lambda item: len(item[0]), reverse=True):
        out = out.replace(ko, en)
    for token in VISUAL_PROMPT_STOPWORDS:
        out = out.replace(token, " ")
    out = re.sub(r"[가-힣]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip(" ,.-")
    out = out or fallback or "bounded particle object"
    return _realistic_generation_prompt(out)


def _realistic_generation_prompt(prompt: str) -> str:
    """Add generator-facing visual constraints without authoring new content.

    This is a rendering prompt adapter, not a dialogue/answer template. It only
    sharpens the material/object words already present so SPLATRA's learned
    text-to-image and TripoSR stages produce a full isolated object instead of a
    vague colored blob.
    """

    lowered = prompt.lower()
    hints: list[str] = []
    if "realistic" not in lowered and "photorealistic" not in lowered:
        hints.append("photorealistic")
    if "glass" in lowered or "transparent" in lowered or "translucent" in lowered:
        hints.extend([
            "translucent glass material",
            "clear rim silhouette",
            "glossy refraction",
            "bright caustic highlights",
        ])
    if "metal" in lowered:
        hints.extend(["brushed metal material", "crisp specular highlights"])
    if "water" in lowered:
        hints.extend(["clear water material", "fluid translucent surface"])
    hints.extend([
        "single centered object",
        "entire object visible",
        "not cropped",
        "plain white background",
        "clean studio product lighting",
        "no text",
        "no watermark",
    ])
    parts: list[str] = []
    for part in [prompt, *hints]:
        cleaned = part.strip(" ,.")
        if cleaned and cleaned.lower() not in {seen.lower() for seen in parts}:
            parts.append(cleaned)
    return ", ".join(parts)


def _sidecar_quality_profile() -> str:
    """Select the SPLATRA rendering profile without changing scene content.

    ATANOR answers and scene semantics are generated elsewhere. This profile is
    only a renderer-side quality request. `gpu` asks a capable SPLATRA sidecar
    to use its densest TripoSR profile; operators on smaller machines can set
    ATANOR_SPLATRA_QUALITY=realistic/high/learned/fast.
    """

    raw = (
        os.environ.get("ATANOR_SPLATRA_QUALITY")
        or os.environ.get("SPLATRA_ATANOR_QUALITY")
        or "gpu"
    )
    profile = raw.strip().lower()
    return profile if profile in SPLATRA_QUALITY_PROFILES else "gpu"


def _sidecar_generate_payload(job: SplatraCandidateCartridgeJob) -> dict[str, Any]:
    # Do not pass ATANOR archetypes as SPLATRA `shape` hints by default.
    # In SPLATRA, a non-empty shape is an explicit primitive request and it
    # bypasses the learned text-to-3D path. ATANOR archetypes are semantic
    # planning hints, not user requests for primitive geometry.
    return {
        "prompt": _sidecar_visual_prompt(job.prompt, job.object_id or "bounded particle object"),
        "quality": _sidecar_quality_profile(),
    }


def _sidecar_scene_spawn_payload(job: SplatraCandidateCartridgeJob) -> dict[str, Any]:
    position = job.position if isinstance(job.position, list) and len(job.position) >= 3 else [0.0, 0.0, 0.0]
    safe_position: list[float] = []
    for value in position[:3]:
        try:
            safe_position.append(max(-2.5, min(2.5, float(value))))
        except (TypeError, ValueError):
            safe_position.append(0.0)
    return {
        "prompt": _sidecar_visual_prompt(job.prompt, job.object_id or "bounded particle object"),
        "id": job.object_id or job.request_id,
        "position": safe_position,
        "scale": 1.0,
        "label": job.object_id or job.prompt or "",
        "quality": _sidecar_quality_profile(),
    }


def _poll_url(base_url: str, poll_path: str | None, sidecar_job_id: str | None) -> str | None:
    if poll_path:
        return urllib.parse.urljoin(f"{base_url}/", poll_path.lstrip("/"))
    if sidecar_job_id:
        return urllib.parse.urljoin(f"{base_url}/", f"v1/job/{sidecar_job_id}")
    return None


def _skipped_job(job: SplatraCandidateCartridgeJob, reason: str) -> SplatraSidecarJobResult:
    return SplatraSidecarJobResult(
        job_id=job.job_id,
        request_id=job.request_id,
        object_id=job.object_id,
        prompt=job.prompt,
        endpoint=job.endpoint,
        status="skipped",
        external_splatra_called=False,
        raw_buffer_in_agent_context=False,
        mutation_performed=False,
        error_reason=reason,
    )


def dispatch_candidate_queue_to_sidecar(
    queue: SplatraCandidateCartridgeQueue | dict[str, Any],
    *,
    sidecar_url: str | None = None,
    transport: Transport | None = None,
    poll_ticks: int = 12,
    poll_interval_sec: float = 2.0,
    timeout_sec: float = 8.0,
) -> SplatraSidecarDispatchResult:
    """Dispatch safe candidate jobs to a running SPLATRA sidecar.

    The dispatcher never downloads /v1/cartridge. Raw Gaussian buffers stay on
    the viewer side-channel; ATANOR receives only job metadata and SGF summaries.
    """

    if isinstance(queue, dict):
        jobs = queue.get("jobs") if isinstance(queue.get("jobs"), list) else []
        queue_obj = SplatraCandidateCartridgeQueue(
            queue_id=str(queue.get("queue_id") or "dict_queue"),
            source_sequence_id=str(queue.get("source_sequence_id") or "unknown_sequence"),
            source_plan_id=str(queue.get("source_plan_id") or "unknown_plan"),
            jobs=[
                SplatraCandidateCartridgeJob(**job)
                for job in jobs
                if isinstance(job, dict)
            ],
            status=str(queue.get("status") or "ready_for_sidecar"),
            execution_mode=str(queue.get("execution_mode") or "candidate_only_dry_run"),
            side_channel=str(queue.get("side_channel") or "GET /v1/cartridge"),
        )
    else:
        queue_obj = queue

    base_url = (sidecar_url or configured_sidecar_url() or "").rstrip("/")
    if not base_url:
        return SplatraSidecarDispatchResult(
            status="sidecar_not_configured",
            configured=False,
            sidecar_url=None,
            jobs=[],
        )

    call = transport or _http_json
    results: list[SplatraSidecarJobResult] = []
    external_called = False
    cartridge_url = urllib.parse.urljoin(f"{base_url}/", "v1/cartridge")
    safe_generation_jobs = [
        job
        for job in queue_obj.jobs
        if job.endpoint == "POST /v1/generate_3d_object"
        and job.execution.get("execute_now") is False
        and job.execution.get("raw_buffer_in_agent_context") is False
    ]

    if len(safe_generation_jobs) >= 2:
        try:
            clear_url = urllib.parse.urljoin(f"{base_url}/", "v1/scene/clear")
            call("POST", clear_url, {}, timeout_sec)
            external_called = True
            for job in queue_obj.jobs:
                if job not in safe_generation_jobs:
                    results.append(_skipped_job(job, "non_generation_action"))
                    continue
                spawn_url = urllib.parse.urljoin(f"{base_url}/", "v1/scene/spawn")
                spawned = call("POST", spawn_url, _sidecar_scene_spawn_payload(job), timeout_sec)
                sgf_summary = spawned.get("sgf") if isinstance(spawned.get("sgf"), dict) else None
                generation_engine = str(spawned.get("engine") or "")
                results.append(
                    SplatraSidecarJobResult(
                        job_id=job.job_id,
                        request_id=job.request_id,
                        object_id=job.object_id,
                        prompt=job.prompt,
                        endpoint="POST /v1/scene/spawn",
                        status="swap_ready" if spawned.get("ok") is True else str(spawned.get("status") or "submitted"),
                        external_splatra_called=True,
                        raw_buffer_in_agent_context=False,
                        mutation_performed=False,
                        sidecar_state="scene_displayed" if spawned.get("ok") is True else None,
                        viewer_side_channel="GET /v1/cartridge",
                        viewer_cartridge_url=cartridge_url,
                        sgf_summary=sgf_summary,
                        generation_engine=generation_engine or None,
                        real_generator_used=any(
                            token in generation_engine.lower()
                            for token in ("triposr", "multiview", "tiny-sd", "real_generator")
                        ),
                        events=[{
                            "state": "SCENE_OBJECT_SPAWNED",
                            "object_id": job.object_id,
                            "endpoint": "POST /v1/scene/spawn",
                        }],
                    )
                )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            results = [
                SplatraSidecarJobResult(
                    job_id=job.job_id,
                    request_id=job.request_id,
                    object_id=job.object_id,
                    prompt=job.prompt,
                    endpoint="POST /v1/scene/spawn",
                    status="sidecar_error",
                    external_splatra_called=external_called,
                    raw_buffer_in_agent_context=False,
                    mutation_performed=False,
                    viewer_cartridge_url=cartridge_url,
                    error_reason=type(exc).__name__,
                )
                for job in queue_obj.jobs
            ]
        status = "swap_ready" if any(job.status == "swap_ready" for job in results) else "submitted" if external_called else "sidecar_error"
        return SplatraSidecarDispatchResult(
            status=status,
            configured=True,
            sidecar_url=base_url,
            jobs=results,
            external_splatra_called=any(job.external_splatra_called for job in results),
            raw_buffer_in_agent_context=False,
            mutation_performed=False,
            raw_cartridge_fetched=False,
        )

    for job in queue_obj.jobs:
        if job.endpoint != "POST /v1/generate_3d_object":
            results.append(_skipped_job(job, "non_generation_action"))
            continue
        if job.execution.get("execute_now") is not False or job.execution.get("raw_buffer_in_agent_context") is not False:
            results.append(_skipped_job(job, "unsafe_candidate_request"))
            continue

        try:
            generate_url = urllib.parse.urljoin(f"{base_url}/", "v1/generate_3d_object")
            generated = call("POST", generate_url, _sidecar_generate_payload(job), timeout_sec)
            external_called = True
            sidecar_job_id = str(generated.get("job_id") or "") or None
            status = str(generated.get("status") or "submitted")
            poll = _poll_url(base_url, generated.get("poll") if isinstance(generated.get("poll"), str) else None, sidecar_job_id)
            events: list[dict[str, Any]] = []
            sgf_summary: dict[str, Any] | None = generated.get("sgf") if isinstance(generated.get("sgf"), dict) else None
            sidecar_state: str | None = str(generated.get("state")) if generated.get("state") is not None else None
            generation_engine = str(generated.get("shape") or generated.get("engine") or "")
            real_generator_used = generated.get("cache") == "real_generator" or any(
                token in generation_engine.lower()
                for token in ("triposr", "multiview", "tiny-sd", "real_generator")
            )
            if poll:
                max_ticks = max(0, min(int(poll_ticks), 30))
                interval = max(0.0, min(float(poll_interval_sec), 5.0))
                for tick_index in range(max_ticks):
                    if tick_index > 0 and interval > 0:
                        time.sleep(interval)
                    tick = call("GET", poll, None, timeout_sec)
                    sidecar_state = str(tick.get("state")) if tick.get("state") is not None else sidecar_state
                    if isinstance(tick.get("events"), list):
                        events.extend(event for event in tick["events"] if isinstance(event, dict))
                    if isinstance(tick.get("sgf"), dict):
                        sgf_summary = tick["sgf"]
                    tick_engine = str(tick.get("shape") or tick.get("engine") or "")
                    if tick_engine:
                        generation_engine = tick_engine
                    if tick.get("cache") == "real_generator" or any(
                        token in generation_engine.lower()
                        for token in ("triposr", "multiview", "tiny-sd", "real_generator")
                    ):
                        real_generator_used = True
                    if tick.get("done") is True:
                        status = "swap_ready"
                        break
                    status = "generating"

            results.append(
                SplatraSidecarJobResult(
                    job_id=job.job_id,
                    request_id=job.request_id,
                    object_id=job.object_id,
                    prompt=job.prompt,
                    endpoint=job.endpoint,
                    status=status,
                    external_splatra_called=True,
                    raw_buffer_in_agent_context=False,
                    mutation_performed=False,
                    sidecar_job_id=sidecar_job_id,
                    sidecar_state=sidecar_state,
                    poll_url=poll,
                    viewer_cartridge_url=cartridge_url,
                    sgf_summary=sgf_summary,
                    generation_engine=generation_engine or None,
                    real_generator_used=bool(real_generator_used),
                    events=events,
                )
            )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            results.append(
                SplatraSidecarJobResult(
                    job_id=job.job_id,
                    request_id=job.request_id,
                    object_id=job.object_id,
                    prompt=job.prompt,
                    endpoint=job.endpoint,
                    status="sidecar_error",
                    external_splatra_called=external_called,
                    raw_buffer_in_agent_context=False,
                    mutation_performed=False,
                    viewer_cartridge_url=cartridge_url,
                    error_reason=type(exc).__name__,
                )
            )

    if any(job.status == "swap_ready" for job in results):
        status = "swap_ready"
    elif any(job.external_splatra_called for job in results):
        status = "submitted"
    elif results:
        status = "no_generation_jobs"
    else:
        status = "empty"
    return SplatraSidecarDispatchResult(
        status=status,
        configured=True,
        sidecar_url=base_url,
        jobs=results,
        external_splatra_called=any(job.external_splatra_called for job in results),
        raw_buffer_in_agent_context=False,
        mutation_performed=False,
        raw_cartridge_fetched=False,
    )
