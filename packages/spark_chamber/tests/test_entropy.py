from __future__ import annotations

from packages.spark_chamber.entropy import collect_environmental_entropy, make_deterministic_entropy, normalize_entropy


def test_deterministic_entropy_reproducible() -> None:
    first = make_deterministic_entropy(7).random()
    second = make_deterministic_entropy(7).random()
    assert first == second


def test_environmental_entropy_disabled_by_default() -> None:
    result = collect_environmental_entropy()
    assert result["enabled"] is False


def test_normalize_entropy_bounded() -> None:
    assert 0.0 <= normalize_entropy(123456) <= 1.0
