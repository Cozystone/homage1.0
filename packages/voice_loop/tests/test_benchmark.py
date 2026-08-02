from __future__ import annotations

from packages.voice_loop.benchmark import benchmark_tts_runtime, detect_device_profile
from packages.voice_loop.mock_tts import MockTTSAdapter


def test_benchmark_profile_is_bounded() -> None:
    profile = detect_device_profile()
    assert profile.cpu_count >= 1
    assert profile.device_class in {"high_end_gpu", "mid_gpu", "cpu_only", "low_power", "unknown"}


def test_runtime_benchmark_handles_mock() -> None:
    profile = benchmark_tts_runtime(MockTTSAdapter(), "mock")
    assert profile.stable is True
    assert profile.engine == "mock"
    assert profile.rtf is not None
