from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


AudioSourceType = Literal["wav_file", "microphone_disabled", "test_fixture", "mock"]
IntentType = Literal[
    "ask_question",
    "command",
    "correction",
    "wake_candidate",
    "consent_phrase",
    "ignore_noise",
    "morning_brief_request",
    "autonomy_status_request",
    "interruption",
    "stop_speaking",
]
SpeakingStyle = Literal["calm", "concise", "friendly", "technical", "morning_brief"]
TTSEngine = Literal["fish_2", "fish_1_5", "fallback", "mock"]
DeviceClass = Literal["high_end_gpu", "mid_gpu", "cpu_only", "low_power", "unknown"]


def _required(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _unit_interval(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class AudioSource:
    source_id: str
    source_type: AudioSourceType
    path: str | None = None
    sample_rate: int | None = None
    channels: int = 1
    consent_required: bool = True
    user_consented: bool = False

    def __post_init__(self) -> None:
        _required("source_id", self.source_id)
        if self.channels < 1:
            raise ValueError("channels must be positive")
        if self.sample_rate is not None and self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.source_type == "wav_file" and not self.path:
            raise ValueError("path is required for wav_file sources")
        if self.source_type == "microphone_disabled" and self.user_consented:
            raise ValueError("microphone is disabled in proof mode")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    source_id: str
    text: str
    language: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None
    final: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("segment_id", self.segment_id)
        _required("source_id", self.source_id)
        object.__setattr__(self, "confidence", _unit_interval("confidence", self.confidence))
        if self.start_ms is not None and self.start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        if self.end_ms is not None and self.end_ms < 0:
            raise ValueError("end_ms must be non-negative")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoiceIntent:
    intent_id: str
    transcript_id: str
    intent_type: IntentType
    confidence: float
    requires_user_review: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("intent_id", self.intent_id)
        _required("transcript_id", self.transcript_id)
        object.__setattr__(self, "confidence", _unit_interval("confidence", self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoiceResponsePlan:
    plan_id: str
    intent_id: str
    text: str
    language: str
    speaking_style: SpeakingStyle
    can_speak: bool
    requires_user_review: bool
    writes_local_brain: bool = False
    writes_cloud_brain: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("plan_id", self.plan_id)
        _required("intent_id", self.intent_id)
        _required("language", self.language)
        if self.writes_local_brain:
            raise ValueError("voice response plans must not write Local Brain")
        if self.writes_cloud_brain:
            raise ValueError("voice response plans must not write Cloud Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TTSRuntimeProfile:
    runtime_id: str
    engine: TTSEngine
    device_class: DeviceClass
    ttfa_ms: float | None = None
    rtf: float | None = None
    peak_ram_mb: float | None = None
    peak_vram_mb: float | None = None
    stable: bool = False
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _required("runtime_id", self.runtime_id)
        for name in ("ttfa_ms", "rtf", "peak_ram_mb", "peak_vram_mb"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoiceOutputEvent:
    event_id: str
    text: str
    language: str
    tts_engine: str
    audio_path: str | None = None
    streaming: bool = False
    ttfa_ms: float | None = None
    rtf: float | None = None
    generated_audio_persisted: bool = False
    requires_user_review: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("event_id", self.event_id)
        _required("language", self.language)
        if self.generated_audio_persisted:
            raise ValueError("proof mode must not persist generated audio")
        for name in ("ttfa_ms", "rtf"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoiceLoopConfig:
    asr_model_name: str = "nvidia/nemotron-3.5-asr-streaming-0.6b"
    preferred_tts_engines: list[str] = field(default_factory=lambda: ["fish_2", "fish_1_5", "fallback"])
    target_lang: str = "ko-KR"
    allow_microphone: bool = False
    allow_file_transcription: bool = True
    allow_tts_output: bool = True
    allow_voice_clone: bool = False
    write_local_brain: bool = False
    write_cloud_brain: bool = False
    require_user_review: bool = True
    max_turn_latency_ms: int = 1500
    max_tts_rtf: float = 1.0

    def __post_init__(self) -> None:
        _required("asr_model_name", self.asr_model_name)
        _required("target_lang", self.target_lang)
        if self.allow_microphone:
            raise ValueError("always-on microphone is disabled for proof mode")
        if self.allow_voice_clone:
            raise ValueError("voice cloning requires explicit future consent flow")
        if self.write_local_brain:
            raise ValueError("voice loop must not write Local Brain")
        if self.write_cloud_brain:
            raise ValueError("voice loop must not write Cloud Brain")
        if self.max_turn_latency_ms <= 0:
            raise ValueError("max_turn_latency_ms must be positive")
        if self.max_tts_rtf <= 0:
            raise ValueError("max_tts_rtf must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
