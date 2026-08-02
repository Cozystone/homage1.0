from __future__ import annotations

from rhfc.fft_binding import bind, fft_magnitude_deviation, make_unitary_key, unbind
from rhfc.hypervector import cosine_similarity, random_bipolar


def test_bind_unbind_recovers_bipolar_source() -> None:
    a = random_bipolar(4096, seed=11)
    b = random_bipolar(4096, seed=12)
    recovered = unbind(bind(a, b), b)
    assert cosine_similarity(a, recovered) > 0.7


def test_unitary_key_has_unit_fft_magnitude_and_recovers_source() -> None:
    a = random_bipolar(4096, seed=31)
    key = make_unitary_key(4096, seed=32)
    assert fft_magnitude_deviation(key) < 1e-10
    recovered = unbind(bind(a, key), key)
    assert cosine_similarity(a, recovered) > 0.999


def test_bind_rejects_dimension_mismatch() -> None:
    a = random_bipolar(128, seed=1)
    b = random_bipolar(256, seed=2)
    try:
        bind(a, b)
    except ValueError as exc:
        assert "dimension mismatch" in str(exc)
    else:
        raise AssertionError("expected dimension mismatch")
