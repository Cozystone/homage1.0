from __future__ import annotations

from packages.digital_life_kernel.needs import signals_from_observation


def test_candidate_run_creates_promotion_signal():
    signals = signals_from_observation({"candidate_run": {"accepted": 10}, "source": "test"})

    assert [signal.signal_type for signal in signals] == ["promotion_candidate"]


def test_resource_pressure_creates_signal():
    signals = signals_from_observation({"resource_state": {"disk_free_gib": 20.0, "ram_free_gib": 10.0}})

    assert any(signal.signal_type == "resource_pressure" for signal in signals)
