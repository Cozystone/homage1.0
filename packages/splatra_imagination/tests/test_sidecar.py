from __future__ import annotations

from typing import Any

from packages.splatra_imagination import (
    build_candidate_cartridge_queue,
    compile_scene_choreography_commands,
    dispatch_candidate_queue_to_sidecar,
)
from packages.splatra_imagination.sidecar import _sidecar_quality_profile, _sidecar_visual_prompt


def _queue():
    sequence = compile_scene_choreography_commands({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "verified_apple",
                "prompt": "a red apple generated from verified scene evidence",
                "archetype": "small_object",
                "position": [0.0, 0.2, 0.0],
            },
            {
                "op": "focus_camera",
                "object_id": "verified_apple",
                "prompt": "focus verified apple",
                "camera": {"zoom": 1.2},
            },
        ],
    })
    return build_candidate_cartridge_queue(sequence)


def _multi_object_queue():
    sequence = compile_scene_choreography_commands({
        "stage_layout": "scene_focus",
        "beats": [
            {
                "op": "spawn_object",
                "object_id": "verified_figure",
                "prompt": "a verified historical figure",
                "archetype": "creature",
                "position": [-0.24, -0.18, 0.0],
            },
            {
                "op": "spawn_object",
                "object_id": "verified_tree",
                "prompt": "a verified tree",
                "archetype": "tree",
                "position": [0.22, 0.24, 0.0],
            },
        ],
    })
    return build_candidate_cartridge_queue(sequence)


def test_sidecar_dispatch_is_safe_noop_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv("SPLATRA_SIDECAR_URL", raising=False)
    monkeypatch.delenv("ATANOR_SPLATRA_SIDECAR_URL", raising=False)

    result = dispatch_candidate_queue_to_sidecar(_queue())

    assert result.status == "sidecar_not_configured"
    assert result.configured is False
    assert result.external_splatra_called is False
    assert result.raw_buffer_in_agent_context is False
    assert result.raw_cartridge_fetched is False
    assert result.mutation_performed is False


def test_sidecar_quality_profile_defaults_to_gpu_for_dense_local_generation(monkeypatch) -> None:
    monkeypatch.delenv("ATANOR_SPLATRA_QUALITY", raising=False)
    monkeypatch.delenv("SPLATRA_ATANOR_QUALITY", raising=False)

    assert _sidecar_quality_profile() == "gpu"


def test_sidecar_quality_profile_allows_operator_override(monkeypatch) -> None:
    monkeypatch.setenv("ATANOR_SPLATRA_QUALITY", "realistic")

    assert _sidecar_quality_profile() == "realistic"


def test_sidecar_dispatch_calls_generate_and_poll_without_fetching_raw_cartridge(monkeypatch) -> None:
    monkeypatch.delenv("ATANOR_SPLATRA_QUALITY", raising=False)
    monkeypatch.delenv("SPLATRA_ATANOR_QUALITY", raising=False)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_transport(method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append((method, url, payload))
        assert "/v1/cartridge" not in url
        if method == "POST":
            assert url.endswith("/v1/generate_3d_object")
            assert payload
            assert payload["prompt"].startswith("a red apple")
            assert payload["quality"] == "gpu"
            assert "shape" not in payload
            return {"status": "generating", "job_id": "job-real-1", "poll": "/v1/job/job-real-1"}
        assert method == "GET"
        assert url.endswith("/v1/job/job-real-1")
        return {
            "job_id": "job-real-1",
            "state": "displayed",
            "done": True,
            "events": [{"state": "SWAP_READY", "info": "verified cartridge pinned"}],
            "sgf": {"num_gaussians": 170000, "raw_bytes": 9520000, "bbox": [[-1, -1, -1], [1, 1, 1]]},
            "shape": "triposr_text_to_3d",
            "cache": "real_generator",
            "hot_swap": True,
        }

    result = dispatch_candidate_queue_to_sidecar(
        _queue(),
        sidecar_url="http://127.0.0.1:8000",
        transport=fake_transport,
        poll_ticks=2,
    )

    assert result.status == "swap_ready"
    assert result.configured is True
    assert result.external_splatra_called is True
    assert result.raw_buffer_in_agent_context is False
    assert result.raw_cartridge_fetched is False
    assert result.mutation_performed is False
    assert len(calls) == 2
    assert calls[0][0] == "POST"
    assert calls[1][0] == "GET"
    assert result.jobs[0].status == "swap_ready"
    assert result.jobs[0].sidecar_job_id == "job-real-1"
    assert result.jobs[0].viewer_cartridge_url == "http://127.0.0.1:8000/v1/cartridge"
    assert result.jobs[0].sgf_summary
    assert result.jobs[0].generation_engine == "triposr_text_to_3d"
    assert result.jobs[0].real_generator_used is True
    assert result.jobs[0].raw_buffer_in_agent_context is False
    assert result.jobs[1].status == "skipped"
    assert result.jobs[1].error_reason == "non_generation_action"


def test_sidecar_dispatch_uses_env_configuration(monkeypatch) -> None:
    monkeypatch.setenv("SPLATRA_SIDECAR_URL", "http://splatra.local")
    calls: list[str] = []

    def fake_transport(method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append(url)
        if method == "POST":
            return {"status": "displayed", "job_id": "hit-1", "poll": "/v1/job/hit-1"}
        return {"job_id": "hit-1", "state": "displayed", "done": True, "sgf": {"num_gaussians": 42}}

    result = dispatch_candidate_queue_to_sidecar(_queue(), transport=fake_transport, poll_ticks=1)

    assert result.configured is True
    assert result.external_splatra_called is True
    assert calls[0] == "http://splatra.local/v1/generate_3d_object"


def test_sidecar_normalizes_korean_visual_prompt_for_clip_generator() -> None:
    prompt = _sidecar_visual_prompt("사실적인 유리 사과를 SPLATRA 파티클 모델로 직접 생성해줘", "fallback")

    assert prompt.startswith("realistic transparent glass red apple")
    assert "translucent glass material" in prompt
    assert "single centered object" in prompt
    assert "plain white background" in prompt
    assert "SPLATRA" not in prompt
    assert "파티클" not in prompt


def test_sidecar_dispatch_sends_normalized_korean_prompt_without_raw_buffer() -> None:
    sequence = compile_scene_choreography_commands({
        "stage_layout": "scene_focus",
        "beats": [{
            "op": "spawn_object",
            "object_id": "verified_glass_apple",
            "prompt": "사실적인 유리 사과를 SPLATRA 파티클 모델로 직접 생성해줘",
            "archetype": "small_object",
        }],
    })
    queue = build_candidate_cartridge_queue(sequence)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_transport(method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append((method, url, payload))
        assert "/v1/cartridge" not in url
        if method == "POST":
            assert payload
            assert payload["prompt"].startswith("realistic transparent glass red apple")
            assert "translucent glass material" in payload["prompt"]
            return {"status": "displayed", "job_id": "korean-visual-1", "poll": "/v1/job/korean-visual-1"}
        return {
            "job_id": "korean-visual-1",
            "state": "displayed",
            "done": True,
            "sgf": {"num_gaussians": 90000},
            "shape": "triposr_text_to_3d",
            "cache": "real_generator",
        }

    result = dispatch_candidate_queue_to_sidecar(
        queue,
        sidecar_url="http://127.0.0.1:8000",
        transport=fake_transport,
        poll_ticks=1,
    )

    assert result.status == "swap_ready"
    assert result.raw_cartridge_fetched is False
    assert calls[0][2]["prompt"].startswith("realistic transparent glass red apple")
    assert "single centered object" in calls[0][2]["prompt"]


def test_sidecar_dispatch_waits_for_async_real_generator_job(monkeypatch) -> None:
    monkeypatch.delenv("ATANOR_SPLATRA_QUALITY", raising=False)
    monkeypatch.delenv("SPLATRA_ATANOR_QUALITY", raising=False)
    monkeypatch.setattr("packages.splatra_imagination.sidecar.time.sleep", lambda _seconds: None)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    polls = {"count": 0}

    def fake_transport(method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append((method, url, payload))
        assert "/v1/cartridge" not in url
        if method == "POST":
            assert payload
            assert payload["quality"] == "gpu"
            return {
                "status": "generating",
                "job_id": "async-real-1",
                "poll": "/v1/job/async-real-1",
                "shape": "real_generator:realistic",
                "cache": "real_generator_pending",
            }
        polls["count"] += 1
        if polls["count"] < 3:
            return {"job_id": "async-real-1", "state": "generating", "done": False, "shape": "real_generator:realistic"}
        return {
            "job_id": "async-real-1",
            "state": "displayed",
            "done": True,
            "shape": "triposr_text_to_3d:realistic",
            "cache": "real_generator",
            "sgf": {"num_gaussians": 87465, "raw_bytes": 4898040},
            "hot_swap": True,
        }

    result = dispatch_candidate_queue_to_sidecar(
        _queue(),
        sidecar_url="http://127.0.0.1:8000",
        transport=fake_transport,
        poll_ticks=5,
    )

    assert polls["count"] == 3
    assert result.status == "swap_ready"
    assert result.jobs[0].status == "swap_ready"
    assert result.jobs[0].generation_engine == "triposr_text_to_3d:realistic"
    assert result.jobs[0].real_generator_used is True
    assert result.jobs[0].sgf_summary == {"num_gaussians": 87465, "raw_bytes": 4898040}
    assert result.raw_cartridge_fetched is False


def test_sidecar_dispatch_assembles_multi_object_scene_without_fetching_raw_cartridge(monkeypatch) -> None:
    monkeypatch.delenv("ATANOR_SPLATRA_QUALITY", raising=False)
    monkeypatch.delenv("SPLATRA_ATANOR_QUALITY", raising=False)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_transport(method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append((method, url, payload))
        assert "/v1/cartridge" not in url
        if url.endswith("/v1/scene/clear"):
            assert method == "POST"
            return {"ok": True}
        assert url.endswith("/v1/scene/spawn")
        assert method == "POST"
        assert payload
        assert payload["id"] in {"verified_figure", "verified_tree"}
        assert payload["quality"] == "gpu"
        assert isinstance(payload["position"], list)
        return {
            "ok": True,
            "id": payload["id"],
            "engine": "triposr_text_to_3d",
            "sgf": {"num_gaussians": 240000, "raw_bytes": 13440000},
        }

    result = dispatch_candidate_queue_to_sidecar(
        _multi_object_queue(),
        sidecar_url="http://127.0.0.1:8000",
        transport=fake_transport,
        poll_ticks=2,
    )

    assert result.status == "swap_ready"
    assert result.external_splatra_called is True
    assert result.raw_buffer_in_agent_context is False
    assert result.raw_cartridge_fetched is False
    assert result.mutation_performed is False
    assert [call[1].split("/")[-1] for call in calls] == ["clear", "spawn", "spawn"]
    assert all(job.endpoint == "POST /v1/scene/spawn" for job in result.jobs)
    assert all(job.status == "swap_ready" for job in result.jobs)
    assert all(job.real_generator_used is True for job in result.jobs)
    assert all(job.viewer_cartridge_url == "http://127.0.0.1:8000/v1/cartridge" for job in result.jobs)
