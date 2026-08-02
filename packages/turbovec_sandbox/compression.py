from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from typing import Iterable


Vector = list[float]


@dataclass(frozen=True)
class CompressionResult:
    original_bytes: int
    compressed_bytes: int
    scale: float
    quantized: list[int]
    reconstructed: Vector

    @property
    def compression_ratio(self) -> float:
        return self.original_bytes / self.compressed_bytes if self.compressed_bytes else 0.0

    @property
    def max_abs_error(self) -> float:
        return max((abs(a - b) for a, b in zip(self.reconstructed, dequantize_int8(self.quantized, self.scale))), default=0.0)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["compression_ratio"] = self.compression_ratio
        payload["max_abs_error"] = self.max_abs_error
        return payload


def quantize_int8(vector: Vector) -> CompressionResult:
    """Quantize a float vector to int8 with deterministic symmetric scaling."""

    if not vector:
        raise ValueError("vector is required")
    max_abs = max(abs(value) for value in vector)
    scale = max_abs / 127.0 if max_abs else 1.0
    quantized = [max(-127, min(127, int(round(value / scale)))) for value in vector]
    reconstructed = dequantize_int8(quantized, scale)
    return CompressionResult(
        original_bytes=len(vector) * 8,
        compressed_bytes=len(quantized),
        scale=scale,
        quantized=quantized,
        reconstructed=reconstructed,
    )


def dequantize_int8(quantized: Iterable[int], scale: float) -> Vector:
    return [int(value) * scale for value in quantized]


def cosine(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError("vectors must have the same dimension")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def recall_at_k(query: Vector, corpus: list[Vector], expected_index: int, k: int) -> float:
    """Return 1.0 when expected_index is within top-k cosine matches, else 0.0."""

    if k < 1:
        raise ValueError("k must be >= 1")
    if expected_index < 0 or expected_index >= len(corpus):
        raise ValueError("expected_index is out of range")
    scores = sorted(((cosine(query, vector), index) for index, vector in enumerate(corpus)), reverse=True)
    top_indices = {index for _, index in scores[:k]}
    return 1.0 if expected_index in top_indices else 0.0
