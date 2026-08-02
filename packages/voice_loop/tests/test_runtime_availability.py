from __future__ import annotations

import pytest

from packages.voice_loop.runtime_availability import RuntimeAvailability, check_fish_runtime, check_modules, check_voice_runtime_availability


def test_runtime_availability_does_not_disable_text_or_enable_microphone():
    result = check_modules("missing_fixture", ["definitely_missing_voice_runtime_fixture"])

    assert result.available is False
    assert result.optional_channel is True
    assert result.text_input_supported is True
    assert result.microphone_enabled is False
    assert result.always_listening_enabled is False
    assert result.raw_voice_saved is False
    assert result.local_brain_write is False
    assert result.cloud_brain_write is False
    assert result.status == "unavailable_missing_package"
    assert result.audio_output_available is False


def test_voice_runtime_availability_reports_all_optional_runtimes():
    result = check_voice_runtime_availability()

    assert set(result) == {"nemotron_asr", "fish_2", "fish_1_5"}
    assert all(item.optional_channel for item in result.values())
    assert all(item.text_input_supported for item in result.values())
    assert all(item.microphone_enabled is False for item in result.values())
    assert all(item.always_listening_enabled is False for item in result.values())
    assert all(item.raw_voice_saved is False for item in result.values())


def test_fish_runtime_missing_package_is_explicit(monkeypatch):
    def missing_spec(_module: str):
        return None

    monkeypatch.setattr("packages.voice_loop.runtime_availability.importlib.util.find_spec", missing_spec)
    result = check_fish_runtime("fish_2")

    assert result.available is False
    assert result.status == "unavailable_missing_package"
    assert result.audio_output_available is False
    assert result.text_input_supported is True
    assert result.microphone_enabled is False
    assert result.install_hint


def test_runtime_availability_rejects_memory_writes():
    with pytest.raises(ValueError):
        RuntimeAvailability("bad", True, [], [], local_brain_write=True)
    with pytest.raises(ValueError):
        RuntimeAvailability("bad", True, [], [], raw_voice_saved=True)
    with pytest.raises(ValueError):
        RuntimeAvailability("bad", True, [], [], always_listening_enabled=True)
