from __future__ import annotations

import pytest

from rhfc.compression import CompressionSpec, compress_hypervector, decompress_hypervector
from rhfc.hypervector import cosine_similarity, random_bipolar


def test_storage_estimate_binary_is_64x_smaller_than_fp64() -> None:
    fp64 = CompressionSpec(dim=1024, precision="fp64")
    binary = CompressionSpec(dim=1024, precision="binary")

    assert fp64.bytes_per_vector() / binary.bytes_per_vector() == 64.0


@pytest.mark.parametrize("precision", ["fp64", "fp32", "int8", "binary"])
def test_compress_decompress_preserves_bipolar_pattern(precision: str) -> None:
    spec = CompressionSpec(dim=256, precision=precision)  # type: ignore[arg-type]
    vector = random_bipolar(dim=256, seed=7)

    restored = decompress_hypervector(compress_hypervector(vector, spec), spec)

    assert cosine_similarity(vector.normalized(), restored) > 0.99


def test_storage_budget_projection_for_cloud_scale() -> None:
    concepts = 22_530_240
    binary_512 = CompressionSpec(dim=512, precision="binary")
    int8_512 = CompressionSpec(dim=512, precision="int8")

    assert binary_512.gib_for_vectors(concepts) < 2.0
    assert int8_512.gib_for_vectors(concepts) < 16.0
