from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import AutonomyLevelName


@dataclass(frozen=True)
class LiveSelfhoodSchedulerConfig:
    """Opt-in, proof-only scheduler bounds for Live Selfhood Cycle sessions."""

    enabled: bool = False
    autonomy_level: AutonomyLevelName = "LEVEL_3_SANDBOX_PLANNER"
    max_ticks_per_session: int = 10
    max_runtime_seconds: int = 60
    min_delay_seconds: float = 5.0
    max_delay_seconds: float = 3600.0
    allow_user_attention_events: bool = True
    allow_voice_events: bool = False
    allow_memory_write: bool = False
    allow_candidate_promotion: bool = False
    allow_real_p2p: bool = False
    allow_generated_code_execution: bool = False
    require_user_approval: bool = True
    stop_marker_path: str | None = None
    deterministic_seed: str | None = "atanor-live-selfhood-proof"

    def __post_init__(self) -> None:
        if self.max_ticks_per_session < 0 or self.max_ticks_per_session > 100:
            raise ValueError("max_ticks_per_session must be between 0 and 100")
        if self.max_runtime_seconds < 0 or self.max_runtime_seconds > 86_400:
            raise ValueError("max_runtime_seconds must be between 0 and 86400")
        if self.min_delay_seconds < 0:
            raise ValueError("min_delay_seconds must be non-negative")
        if self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError("max_delay_seconds must be greater than or equal to min_delay_seconds")
        if self.max_delay_seconds > 86_400:
            raise ValueError("max_delay_seconds must be no more than 86400")
        if self.require_user_approval is not True:
            raise ValueError("require_user_approval must remain true")
        blocked = {
            "allow_voice_events": self.allow_voice_events,
            "allow_memory_write": self.allow_memory_write,
            "allow_candidate_promotion": self.allow_candidate_promotion,
            "allow_real_p2p": self.allow_real_p2p,
            "allow_generated_code_execution": self.allow_generated_code_execution,
        }
        unsafe = {key: value for key, value in blocked.items() if value}
        if unsafe:
            raise ValueError(f"Live Selfhood scheduler cannot enable unsafe capabilities: {unsafe}")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
