from __future__ import annotations

import os
import platform
import shutil
import time
from dataclasses import asdict, dataclass

from packages.voice_loop.models import DeviceClass, TTSRuntimeProfile
from packages.voice_loop.tts_adapter import TTSAdapter


@dataclass(frozen=True)
class DeviceBenchmarkProfile:
    os_name: str
    cpu_count: int
    total_ram_mb: float | None
    available_ram_mb: float | None
    cuda_available: bool
    gpu_name: str | None
    vram_mb: float | None
    battery_powered: bool | None
    thermal_pressure: bool | None
    disk_free_gb: float | None
    device_class: DeviceClass
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_device_profile() -> DeviceBenchmarkProfile:
    """Collect bounded local device metadata without starting heavy runtimes."""

    total_ram_mb: float | None = None
    available_ram_mb: float | None = None
    cuda_available = False
    gpu_name: str | None = None
    vram_mb: float | None = None
    notes: list[str] = []
    try:
        import psutil  # type: ignore[import-not-found]

        memory = psutil.virtual_memory()
        total_ram_mb = memory.total / (1024 * 1024)
        available_ram_mb = memory.available / (1024 * 1024)
    except Exception as exc:
        notes.append(f"psutil unavailable: {exc}")
    try:
        import torch  # type: ignore[import-not-found]

        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            gpu_name = str(torch.cuda.get_device_name(0))
            props = torch.cuda.get_device_properties(0)
            vram_mb = props.total_memory / (1024 * 1024)
    except Exception as exc:
        notes.append(f"torch cuda probe unavailable: {exc}")
    disk_free_gb: float | None = None
    try:
        disk_free_gb = shutil.disk_usage(os.getcwd()).free / (1024**3)
    except Exception as exc:
        notes.append(f"disk probe unavailable: {exc}")
    if cuda_available and vram_mb and vram_mb >= 16000:
        device_class: DeviceClass = "high_end_gpu"
    elif cuda_available:
        device_class = "mid_gpu"
    elif total_ram_mb and total_ram_mb < 8192:
        device_class = "low_power"
    else:
        device_class = "cpu_only"
    return DeviceBenchmarkProfile(
        os_name=platform.platform(),
        cpu_count=os.cpu_count() or 1,
        total_ram_mb=total_ram_mb,
        available_ram_mb=available_ram_mb,
        cuda_available=cuda_available,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        battery_powered=None,
        thermal_pressure=None,
        disk_free_gb=disk_free_gb,
        device_class=device_class,
        notes=notes,
    )


def benchmark_tts_runtime(
    adapter: TTSAdapter,
    engine: str,
    device_class: DeviceClass = "unknown",
    text: str = "안녕하세요. 저는 ATANOR입니다.",
) -> TTSRuntimeProfile:
    """Run a tiny local TTS probe if a runtime is already available."""

    start = time.perf_counter()
    try:
        adapter.load()
        event = adapter.synthesize(text, "ko-KR", "calm")
    except Exception as exc:
        return TTSRuntimeProfile(
            runtime_id=f"{engine}_benchmark",
            engine=engine if engine in {"fish_2", "fish_1_5", "fallback", "mock"} else "fallback",
            device_class=device_class,
            stable=False,
            notes=[f"runtime unavailable: {exc}"],
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    rtf = event.rtf if event.rtf is not None else min(1.0, elapsed_ms / 1000.0)
    return TTSRuntimeProfile(
        runtime_id=f"{engine}_benchmark",
        engine=engine if engine in {"fish_2", "fish_1_5", "fallback", "mock"} else "fallback",
        device_class=device_class,
        ttfa_ms=event.ttfa_ms if event.ttfa_ms is not None else elapsed_ms,
        rtf=rtf,
        stable=True,
        notes=["bounded local benchmark completed"],
    )
