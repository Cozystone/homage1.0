from __future__ import annotations

from packages.turbovec_sandbox.compression import cosine, quantize_int8, recall_at_k


def test_quantization_is_deterministic():
    vector = [0.2, -0.5, 1.0, 0.0]

    assert quantize_int8(vector).quantized == quantize_int8(vector).quantized


def test_quantization_has_bounded_distortion():
    vector = [0.2, -0.5, 1.0, 0.0]
    result = quantize_int8(vector)

    assert cosine(vector, result.reconstructed) > 0.999
    assert result.compression_ratio == 8.0


def test_recall_at_k_computed():
    corpus = [[1.0, 0.0], [0.0, 1.0]]

    assert recall_at_k([0.9, 0.1], corpus, expected_index=0, k=1) == 1.0
