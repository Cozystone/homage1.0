"""FFT-accelerated HRR binding operations."""

from __future__ import annotations

import numpy as np

from .hypervector import HyperVector


def make_unitary_key(dim: int, seed: int | None = None) -> HyperVector:
    """Create a complex key whose FFT spectrum has unit magnitude.

    Random bipolar keys are only approximately invertible under circular
    correlation. A unitary HRR key keeps every Fourier bin on the unit circle,
    so unbinding multiplies by the exact complex conjugate phase instead of
    amplifying or suppressing frequency bands.
    """

    if dim <= 0:
        raise ValueError("dim must be positive")
    rng = np.random.default_rng(seed)
    phases = rng.uniform(0.0, 2.0 * np.pi, size=int(dim))
    spectrum = np.exp(1j * phases)
    values = np.fft.ifft(spectrum)
    return HyperVector(values, "complex")


def fft_magnitude_deviation(key: HyperVector) -> float:
    """Return max abs(|FFT(key)| - 1), useful for unitary validation."""

    spectrum = np.fft.fft(key.values)
    return float(np.max(np.abs(np.abs(spectrum) - 1.0)))


def bind(a: HyperVector, b: HyperVector) -> HyperVector:
    """Bind two hypervectors with circular convolution via FFT.

    Complexity is O(n log n) because the convolution is implemented as
    inverse_fft(fft(a) * fft(b)).
    """

    if a.dim != b.dim:
        raise ValueError("dimension mismatch")
    kind = "complex" if a.kind == "complex" or b.kind == "complex" else "bipolar"
    values = np.fft.ifft(np.fft.fft(a.values) * np.fft.fft(b.values))
    if kind == "bipolar":
        values = np.real(values)
    return HyperVector(values, kind).normalized()


def unbind(c: HyperVector, b: HyperVector) -> HyperVector:
    """Approximately recover ``a`` from ``bind(a, b)`` using correlation.

    For random high-dimensional bipolar vectors, correlation with the binding
    key suppresses cross-talk and recovers a vector close to the original.
    """

    if c.dim != b.dim:
        raise ValueError("dimension mismatch")
    kind = "complex" if c.kind == "complex" or b.kind == "complex" else "bipolar"
    values = np.fft.ifft(np.fft.fft(c.values) * np.conj(np.fft.fft(b.values)))
    if kind == "bipolar":
        values = np.real(values)
    return HyperVector(values, kind).normalized()
