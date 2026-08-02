from packages.splatra_turbovec.quantization import (
    dequantize_log_radius,
    dequantize_unorm,
    quantize_log_radius,
    quantize_snorm,
    quantize_unorm,
)


def test_quantized_values_bounded():
    assert quantize_unorm(-10, 8) == 0
    assert quantize_unorm(10, 8) == 255
    assert 0.49 < dequantize_unorm(quantize_unorm(0.5, 12), 12) < 0.51
    assert -32767 <= quantize_snorm(-2.0, 16, 1.0) <= 32767


def test_radius_log_round_trip():
    value = 0.037
    q = quantize_log_radius(value, 16, 0.001, 0.1)
    restored = dequantize_log_radius(q, 16, 0.001, 0.1)
    assert abs(value - restored) < 0.00001
