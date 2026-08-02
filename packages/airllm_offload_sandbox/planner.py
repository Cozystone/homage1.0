from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


PlanStatus = Literal["advisory_ok", "blocked"]


@dataclass(frozen=True)
class HardwareProfile:
    ram_gib: float
    vram_gib: float
    disk_free_gib: float

    def __post_init__(self) -> None:
        if self.ram_gib < 0 or self.vram_gib < 0 or self.disk_free_gib < 0:
            raise ValueError("hardware resources cannot be negative")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class ModelProfile:
    name: str
    parameter_billion: float
    quantization_bits: int = 4
    layer_count: int = 32

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("model name is required")
        if self.parameter_billion <= 0 or self.quantization_bits <= 0 or self.layer_count <= 0:
            raise ValueError("model parameters, quantization, and layers must be positive")

    @property
    def estimated_weight_gib(self) -> float:
        return (self.parameter_billion * 1_000_000_000 * self.quantization_bits / 8) / (1024**3)

    def to_dict(self) -> dict[str, float | int | str]:
        payload = asdict(self)
        payload["estimated_weight_gib"] = self.estimated_weight_gib
        return payload


@dataclass(frozen=True)
class OffloadPlan:
    status: PlanStatus
    reason: str
    gpu_layers: int
    cpu_layers: int
    disk_cache_gib: float
    advisory_only: bool = True
    model_downloaded: bool = False
    production_answer_path_integrated: bool = False

    def __post_init__(self) -> None:
        if not self.advisory_only or self.model_downloaded or self.production_answer_path_integrated:
            raise ValueError("AirLLM sandbox must remain advisory-only with no downloads or production integration")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def plan_offload(model: ModelProfile, hardware: HardwareProfile) -> OffloadPlan:
    """Create an advisory layer offload plan without downloading or running models."""

    required_disk = model.estimated_weight_gib * 1.25
    if required_disk > hardware.disk_free_gib:
        return OffloadPlan("blocked", "insufficient_disk_budget", 0, model.layer_count, required_disk)
    if model.estimated_weight_gib > hardware.ram_gib * 0.8:
        return OffloadPlan("blocked", "insufficient_ram_budget", 0, model.layer_count, required_disk)
    gpu_fraction = min(1.0, hardware.vram_gib / max(model.estimated_weight_gib, 0.001))
    gpu_layers = int(model.layer_count * gpu_fraction)
    cpu_layers = model.layer_count - gpu_layers
    return OffloadPlan("advisory_ok", "fits_advisory_budget", gpu_layers, cpu_layers, required_disk)
