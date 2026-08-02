from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HotColdSplitPlan:
    hot_vectors: int
    cold_vectors: int
    dimension: int
    hot_precision_bytes: int = 4
    cold_precision_bytes: int = 1
    production_store_mutated: bool = False

    def __post_init__(self) -> None:
        if self.production_store_mutated:
            raise ValueError("Turbovec sandbox cannot mutate production vector stores")
        if self.hot_vectors < 0 or self.cold_vectors < 0 or self.dimension < 1:
            raise ValueError("vector counts and dimension must be non-negative with positive dimension")

    @property
    def baseline_bytes(self) -> int:
        return (self.hot_vectors + self.cold_vectors) * self.dimension * 8

    @property
    def planned_bytes(self) -> int:
        hot = self.hot_vectors * self.dimension * self.hot_precision_bytes
        cold = self.cold_vectors * self.dimension * self.cold_precision_bytes
        return hot + cold

    @property
    def compression_ratio(self) -> float:
        return self.baseline_bytes / self.planned_bytes if self.planned_bytes else 0.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["baseline_bytes"] = self.baseline_bytes
        payload["planned_bytes"] = self.planned_bytes
        payload["compression_ratio"] = self.compression_ratio
        return payload
