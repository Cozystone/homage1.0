from __future__ import annotations

from packages.voice_loop.models import TTSRuntimeProfile
from packages.voice_loop.selector import select_tts_engine


def test_selector_picks_fish2_when_fast_and_stable() -> None:
    selection = select_tts_engine(
        [
            TTSRuntimeProfile("f2", "fish_2", "high_end_gpu", ttfa_ms=350, rtf=0.5, stable=True),
            TTSRuntimeProfile("f15", "fish_1_5", "mid_gpu", ttfa_ms=500, rtf=0.7, stable=True),
        ]
    )
    assert selection.selected_engine == "fish_2"


def test_selector_falls_back_to_fish15_when_fish2_slow() -> None:
    selection = select_tts_engine(
        [
            TTSRuntimeProfile("f2", "fish_2", "high_end_gpu", ttfa_ms=900, rtf=0.9, stable=True),
            TTSRuntimeProfile("f15", "fish_1_5", "mid_gpu", ttfa_ms=500, rtf=0.7, stable=True),
        ]
    )
    assert selection.selected_engine == "fish_1_5"


def test_selector_falls_back_to_mock_when_no_runtime_passes() -> None:
    selection = select_tts_engine([TTSRuntimeProfile("f2", "fish_2", "unknown", stable=False)])
    assert selection.selected_engine == "mock"
