from __future__ import annotations

import math


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def quantize_unorm(value: float, bits: int, low: float = 0.0, high: float = 1.0) -> int:
    if bits < 1 or bits > 16:
        raise ValueError("bits must be in 1..16")
    if high <= low:
        raise ValueError("high must be greater than low")
    normalized = clamp((value - low) / (high - low), 0.0, 1.0)
    return int(round(normalized * ((1 << bits) - 1)))


def dequantize_unorm(value: int, bits: int, low: float = 0.0, high: float = 1.0) -> float:
    if bits < 1 or bits > 16:
        raise ValueError("bits must be in 1..16")
    max_value = (1 << bits) - 1
    return low + (clamp(float(value), 0.0, float(max_value)) / max_value) * (high - low)


def quantize_snorm(value: float, bits: int, max_abs: float) -> int:
    if bits < 2 or bits > 16:
        raise ValueError("bits must be in 2..16")
    if max_abs <= 0:
        return 0
    limit = (1 << (bits - 1)) - 1
    return int(round(clamp(value / max_abs, -1.0, 1.0) * limit))


def dequantize_snorm(value: int, bits: int, max_abs: float) -> float:
    if max_abs <= 0:
        return 0.0
    limit = (1 << (bits - 1)) - 1
    return clamp(float(value), -float(limit), float(limit)) / limit * max_abs


def quantize_log_radius(radius: float, bits: int, min_radius: float, max_radius: float) -> int:
    if radius <= 0 or min_radius <= 0 or max_radius <= 0:
        raise ValueError("radii must be positive")
    log_min = math.log(min_radius)
    log_max = math.log(max_radius)
    return quantize_unorm(math.log(radius), bits, log_min, log_max)


def dequantize_log_radius(value: int, bits: int, min_radius: float, max_radius: float) -> float:
    log_min = math.log(min_radius)
    log_max = math.log(max_radius)
    return math.exp(dequantize_unorm(value, bits, log_min, log_max))
