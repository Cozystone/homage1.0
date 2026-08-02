from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class HardwareProfile:
    ram_gb: float
    vram_gb: float
    gpu_name: str
    source: str
    ram_available_gb: float | None = None
    ram_os_overhead_gb: float | None = None
    vram_available_gb: float | None = None
    vram_used_gb: float | None = None
    cpu_ops_per_ms: float | None = None
    viewport_10k_frame_ms: float | None = None


@dataclass(frozen=True)
class ElasticRuntimeConfig:
    tier: str
    tier_label: str
    max_graph_nodes: int
    max_chunk_nodes: int
    inference_mode: str
    pruning_aggressiveness: str
    lazy_subgraph_nodes: int
    lazy_subgraph_edges: int
    lazy_subgraph_depth: int
    utterance_max_tokens: int
    continuous_threading_enabled: bool
    heavy_edge_mesh_enabled: bool
    profile: HardwareProfile

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["profile"] = asdict(self.profile)
        return payload


def _env_float(name: str) -> float | None:
    value = os.getenv(name)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _round_capacity(value: float) -> float:
    """Normalize marketed RAM/VRAM capacity after OS/driver reservation.

    Windows often reports a 32 GB kit as ~31.1 GB and a 16 GB GPU as ~15.9 GB.
    The tier matrix should not punish that reservation, while the benchmark
    still exposes true currently available memory as a separate pressure value.
    """

    if 15.5 <= value < 16:
        return 16.0
    if 31.0 <= value < 32:
        return 32.0
    if 63.0 <= value < 64:
        return 64.0
    return round(value, 2)


def _detect_ram() -> tuple[float, float | None, float | None, str]:
    override = _env_float("HOMAGE_RAM_GB")
    available_override = _env_float("HOMAGE_RAM_AVAILABLE_GB")
    if override is not None:
        overhead = max(0.0, override - available_override) if available_override is not None else None
        return _round_capacity(override), available_override, overhead, "env"
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        total = round(memory.total / (1024**3), 2)
        available = round(memory.available / (1024**3), 2)
        return _round_capacity(total), available, round(max(0.0, total - available), 2), "psutil"
    except Exception:
        return 8.0, None, None, "fallback"


def _detect_torch_vram() -> tuple[float, float | None, float | None, str] | None:
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return 0.0, 0.0, 0.0, "torch-cuda-unavailable"
        device_index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device_index)
        total = round(float(props.total_memory) / (1024**3), 2)
        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(device_index)
            available = round(float(free_bytes) / (1024**3), 2)
            used = round(max(0.0, float(total_bytes - free_bytes)) / (1024**3), 2)
        except Exception:
            available = None
            used = None
        return _round_capacity(total), available, used, str(props.name)
    except Exception:
        return None


def _detect_nvidia_smi_vram() -> tuple[float, float | None, float | None, str] | None:
    command = shutil.which("nvidia-smi")
    if not command:
        return None
    try:
        output = subprocess.check_output(
            [
                command,
                "--query-gpu=name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        ).strip().splitlines()[0]
        name, memory_total, memory_used, memory_free = [part.strip() for part in output.split(",", 3)]
        total = _round_capacity(round(float(memory_total) / 1024, 2))
        used = round(float(memory_used) / 1024, 2)
        free = round(float(memory_free) / 1024, 2)
        return total, free, used, name
    except Exception:
        return None


def _detect_vram() -> tuple[float, float | None, float | None, str]:
    override = _env_float("HOMAGE_VRAM_GB")
    available_override = _env_float("HOMAGE_VRAM_AVAILABLE_GB")
    if override is not None:
        used = max(0.0, override - available_override) if available_override is not None else None
        return _round_capacity(override), available_override, used, "env"
    torch_result = _detect_torch_vram()
    if torch_result is not None:
        return torch_result
    smi_result = _detect_nvidia_smi_vram()
    if smi_result is not None:
        return smi_result
    return 0.0, None, None, "unavailable"


def detect_hardware_profile() -> HardwareProfile:
    ram_gb, ram_available_gb, ram_os_overhead_gb, ram_source = _detect_ram()
    vram_gb, vram_available_gb, vram_used_gb, gpu_name = _detect_vram()
    return HardwareProfile(
        ram_gb=ram_gb,
        vram_gb=vram_gb,
        gpu_name=gpu_name,
        source=f"ram:{ram_source};vram:{gpu_name}",
        ram_available_gb=ram_available_gb,
        ram_os_overhead_gb=ram_os_overhead_gb,
        vram_available_gb=vram_available_gb,
        vram_used_gb=vram_used_gb,
    )


def _profile_from_mapping(profile: dict[str, Any]) -> HardwareProfile:
    ram_gb = _round_capacity(float(profile.get("ram_gb") or 0.0))
    vram_gb = _round_capacity(float(profile.get("vram_gb") or 0.0))
    ram_available = profile.get("ram_available_gb")
    vram_available = profile.get("vram_available_gb")
    return HardwareProfile(
        ram_gb=ram_gb,
        vram_gb=vram_gb,
        gpu_name=str(profile.get("gpu_name") or profile.get("gpu") or "override"),
        source=str(profile.get("source") or "override"),
        ram_available_gb=float(ram_available) if ram_available is not None else None,
        ram_os_overhead_gb=float(profile.get("ram_os_overhead_gb")) if profile.get("ram_os_overhead_gb") is not None else None,
        vram_available_gb=float(vram_available) if vram_available is not None else None,
        vram_used_gb=float(profile.get("vram_used_gb")) if profile.get("vram_used_gb") is not None else None,
        cpu_ops_per_ms=float(profile.get("cpu_ops_per_ms")) if profile.get("cpu_ops_per_ms") is not None else None,
        viewport_10k_frame_ms=float(profile.get("viewport_10k_frame_ms")) if profile.get("viewport_10k_frame_ms") is not None else None,
    )


def build_runtime_config(profile: HardwareProfile | dict[str, Any] | None = None) -> ElasticRuntimeConfig:
    if profile is None:
        detected = detect_hardware_profile()
    elif isinstance(profile, HardwareProfile):
        detected = profile
    else:
        detected = _profile_from_mapping(profile)

    ram_gb = detected.ram_gb
    vram_gb = detected.vram_gb

    if ram_gb >= 60 and vram_gb >= 24:
        return ElasticRuntimeConfig(
            tier="tier_s",
            tier_label="Tier S / Overlord",
            max_graph_nodes=2_000_000,
            max_chunk_nodes=20_000,
            inference_mode="gpu_native",
            pruning_aggressiveness="very_low",
            lazy_subgraph_nodes=20_000,
            lazy_subgraph_edges=80_000,
            lazy_subgraph_depth=3,
            utterance_max_tokens=192,
            continuous_threading_enabled=True,
            heavy_edge_mesh_enabled=True,
            profile=detected,
        )
    if ram_gb >= 30 and vram_gb >= 16:
        return ElasticRuntimeConfig(
            tier="tier_1_m",
            tier_label="Tier 1-M / Director",
            max_graph_nodes=500_000,
            max_chunk_nodes=5_000,
            inference_mode="gpu_native",
            pruning_aggressiveness="low",
            lazy_subgraph_nodes=5_000,
            lazy_subgraph_edges=20_000,
            lazy_subgraph_depth=3,
            utterance_max_tokens=128,
            continuous_threading_enabled=True,
            heavy_edge_mesh_enabled=True,
            profile=detected,
        )
    if ram_gb >= 30 and vram_gb >= 11:
        return ElasticRuntimeConfig(
            tier="tier_1_s",
            tier_label="Tier 1-S / Creator",
            max_graph_nodes=300_000,
            max_chunk_nodes=3_000,
            inference_mode="gpu_assisted",
            pruning_aggressiveness="medium",
            lazy_subgraph_nodes=3_000,
            lazy_subgraph_edges=12_000,
            lazy_subgraph_depth=3,
            utterance_max_tokens=112,
            continuous_threading_enabled=True,
            heavy_edge_mesh_enabled=True,
            profile=detected,
        )
    if ram_gb >= 14 and vram_gb >= 8:
        return ElasticRuntimeConfig(
            tier="tier_2_a",
            tier_label="Tier 2-A / Developer",
            max_graph_nodes=100_000,
            max_chunk_nodes=1_500,
            inference_mode="gpu_assisted_low_vram",
            pruning_aggressiveness="aggressive",
            lazy_subgraph_nodes=1_500,
            lazy_subgraph_edges=6_000,
            lazy_subgraph_depth=2,
            utterance_max_tokens=80,
            continuous_threading_enabled=False,
            heavy_edge_mesh_enabled=True,
            profile=detected,
        )
    if ram_gb >= 14:
        return ElasticRuntimeConfig(
            tier="tier_2_e",
            tier_label="Tier 2-E / Mainstream",
            max_graph_nodes=50_000,
            max_chunk_nodes=800,
            inference_mode="cpu_gguf",
            pruning_aggressiveness="high",
            lazy_subgraph_nodes=800,
            lazy_subgraph_edges=3_200,
            lazy_subgraph_depth=2,
            utterance_max_tokens=64,
            continuous_threading_enabled=False,
            heavy_edge_mesh_enabled=False,
            profile=detected,
        )
    return ElasticRuntimeConfig(
        tier="tier_3",
        tier_label="Tier 3 / Edge",
        max_graph_nodes=10_000,
        max_chunk_nodes=300,
        inference_mode="text_fallback",
        pruning_aggressiveness="critical",
        lazy_subgraph_nodes=300,
        lazy_subgraph_edges=1_000,
        lazy_subgraph_depth=1,
        utterance_max_tokens=40,
        continuous_threading_enabled=False,
        heavy_edge_mesh_enabled=False,
        profile=detected,
    )


@lru_cache(maxsize=1)
def get_runtime_config() -> ElasticRuntimeConfig:
    return build_runtime_config(_EMPIRICAL_PROFILE)


def runtime_config_dict() -> dict[str, Any]:
    return get_runtime_config().as_dict()


def prime_runtime_config(profile: HardwareProfile | dict[str, Any]) -> ElasticRuntimeConfig:
    """Install the latest empirical startup benchmark as the runtime source."""

    global _EMPIRICAL_PROFILE
    _EMPIRICAL_PROFILE = profile if isinstance(profile, HardwareProfile) else _profile_from_mapping(profile)
    get_runtime_config.cache_clear()
    return get_runtime_config()
_EMPIRICAL_PROFILE: HardwareProfile | None = None
