from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
import os
import shutil
from typing import Literal


FishRuntimeStatus = Literal[
    "unavailable_missing_package",
    "unavailable_missing_model",
    "unavailable_no_device",
    "available_not_loaded",
    "available_loaded",
    "synthesis_failed",
    "synthesis_ok",
    "fallback_mock",
]


@dataclass(frozen=True)
class RuntimeAvailability:
    runtime_id: str
    available: bool
    checked_modules: list[str]
    missing_modules: list[str]
    status: str = "available_not_loaded"
    reason: str | None = None
    install_hint: str | None = None
    audio_output_available: bool = False
    optional_channel: bool = True
    text_input_supported: bool = True
    microphone_enabled: bool = False
    always_listening_enabled: bool = False
    raw_voice_saved: bool = False
    generated_audio_persisted: bool = False
    local_brain_write: bool = False
    cloud_brain_write: bool = False

    def __post_init__(self) -> None:
        if not self.optional_channel or not self.text_input_supported:
            raise ValueError("voice runtime must remain optional and text input must remain supported")
        if self.microphone_enabled:
            raise ValueError("availability checks must not enable the microphone")
        if self.always_listening_enabled:
            raise ValueError("availability checks must not enable always-on listening")
        if self.raw_voice_saved or self.generated_audio_persisted or self.local_brain_write or self.cloud_brain_write:
            raise ValueError("availability checks must not persist audio or write memory")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def check_modules(runtime_id: str, modules: list[str]) -> RuntimeAvailability:
    """Check optional runtime imports without loading models or calling services."""

    missing: list[str] = []
    for module in modules:
        try:
            found = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            found = False
        if not found:
            missing.append(module)
    return RuntimeAvailability(
        runtime_id=runtime_id,
        available=not missing,
        checked_modules=modules,
        missing_modules=missing,
        status="available_not_loaded" if not missing else "unavailable_missing_package",
        reason=None if not missing else f"missing modules: {','.join(missing)}",
        install_hint=None if not missing else f"Install optional runtime package(s): {', '.join(missing)}",
        audio_output_available=False,
    )


def _module_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def check_fish_runtime(runtime_id: str = "fish_2") -> RuntimeAvailability:
    """Check Fish runtime readiness without importing models or downloading weights."""

    if runtime_id not in {"fish_2", "fish_1_5"}:
        raise ValueError("runtime_id must be fish_2 or fish_1_5")
    checked = ["fish_speech"] if runtime_id == "fish_1_5" else ["fish_speech", "fish_audio_sdk"]
    present = [module for module in checked if _module_present(module)]
    missing = [module for module in checked if module not in present]
    if not present:
        return RuntimeAvailability(
            runtime_id=runtime_id,
            available=False,
            checked_modules=checked,
            missing_modules=missing,
            status="unavailable_missing_package",
            reason=f"{runtime_id} package is not installed",
            install_hint="Install Fish Speech/Fish Audio runtime and configure a local model path before enabling audio.",
            audio_output_available=False,
        )

    model_env = "ATANOR_FISH2_MODEL_DIR" if runtime_id == "fish_2" else "ATANOR_FISH15_MODEL_DIR"
    model_dir = os.environ.get(model_env) or os.environ.get("FISH_SPEECH_MODEL_DIR")
    if not model_dir or not os.path.exists(model_dir):
        return RuntimeAvailability(
            runtime_id=runtime_id,
            available=False,
            checked_modules=checked,
            missing_modules=missing,
            status="unavailable_missing_model",
            reason=f"{model_env} or FISH_SPEECH_MODEL_DIR is not configured",
            install_hint="Set a local Fish model directory after downloading weights outside the repository.",
            audio_output_available=False,
        )

    if shutil.which("ffmpeg") is None:
        return RuntimeAvailability(
            runtime_id=runtime_id,
            available=False,
            checked_modules=checked,
            missing_modules=missing,
            status="unavailable_no_device",
            reason="ffmpeg is not available for browser-playable audio packaging",
            install_hint="Install ffmpeg and keep generated audio in an ignored runtime directory.",
            audio_output_available=False,
        )

    return RuntimeAvailability(
        runtime_id=runtime_id,
        available=True,
        checked_modules=checked,
        missing_modules=missing,
        status="available_not_loaded",
        reason="Fish package and model path are configured; synthesis has not been run",
        install_hint=None,
        audio_output_available=False,
    )


def check_voice_runtime_availability() -> dict[str, RuntimeAvailability]:
    """Return safe availability checks for optional ASR/TTS runtimes."""

    return {
        "nemotron_asr": check_modules("nemotron_asr", ["nemo.collections.asr"]),
        "fish_2": check_fish_runtime("fish_2"),
        "fish_1_5": check_fish_runtime("fish_1_5"),
    }
