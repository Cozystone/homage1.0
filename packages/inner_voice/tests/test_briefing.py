from __future__ import annotations

from packages.inner_voice.briefing import build_inner_voice_brief
from packages.inner_voice.generator import InnerVoiceInput, generate_inner_voice_frame
from packages.inner_voice.models import InnerVoiceLog


def test_lab_brief_contains_frames_product_hides_raw() -> None:
    log = InnerVoiceLog()
    log.append(generate_inner_voice_frame(InnerVoiceInput(latest_user_input="안녕")))

    lab = build_inner_voice_brief(log)
    product = build_inner_voice_brief(log, product=True)

    assert lab["frames"]
    # was two Korean substrings, standing in for "the brief carried the monologue through". The
    # Korean lane is retired, so the property is asserted directly instead of through its language.
    assert log.frames[0].monologue_text[:30] in lab["brief"]
    assert product["raw_inner_voice_hidden"] is True
    assert "frames" not in product
