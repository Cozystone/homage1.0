from __future__ import annotations

from dataclasses import asdict, dataclass

from packages.voice_loop.models import TTSRuntimeProfile


@dataclass(frozen=True)
class TTSSelection:
    selected_engine: str
    reason: str
    benchmark_profile: TTSRuntimeProfile
    fallback_chain: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _within_memory_budget(profile: TTSRuntimeProfile, max_ram_mb: float | None = None) -> bool:
    if max_ram_mb is not None and profile.peak_ram_mb is not None and profile.peak_ram_mb > max_ram_mb:
        return False
    return True


def select_tts_engine(
    profiles: list[TTSRuntimeProfile],
    max_ttfa_ms: float = 700.0,
    max_rtf: float = 1.0,
    max_ram_mb: float | None = None,
) -> TTSSelection:
    """Select Fish 2, Fish 1.5, or fallback using conservative proof policy."""

    by_engine = {profile.engine: profile for profile in profiles}
    fish2 = by_engine.get("fish_2")
    if (
        fish2
        and fish2.stable
        and fish2.ttfa_ms is not None
        and fish2.ttfa_ms <= max_ttfa_ms
        and fish2.rtf is not None
        and fish2.rtf <= max_rtf
        and _within_memory_budget(fish2, max_ram_mb)
    ):
        return TTSSelection("fish_2", "Fish 2 passed TTFA, RTF, stability, and memory policy", fish2, ["fish_2"])
    fish15 = by_engine.get("fish_1_5")
    if fish15 and fish15.stable and fish15.rtf is not None and fish15.rtf <= max_rtf and _within_memory_budget(fish15, max_ram_mb):
        return TTSSelection("fish_1_5", "Fish 2 unavailable or too slow; Fish 1.5 passed fallback policy", fish15, ["fish_2", "fish_1_5"])
    fallback = by_engine.get("fallback") or by_engine.get("mock")
    if fallback is None:
        fallback = TTSRuntimeProfile("mock_benchmark", "mock", "unknown", ttfa_ms=0.0, rtf=0.0, stable=True, notes=["implicit mock fallback"])
    return TTSSelection("mock" if fallback.engine == "mock" else "fallback", "No Fish runtime passed policy; using proof fallback", fallback, ["fish_2", "fish_1_5", fallback.engine])
