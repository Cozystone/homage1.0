"""#3: inner-voice self-narration must match the conversation language.

In English mode the orange self-narration was leaking Korean ("warm …").
The surface is now language-aware.
"""

from __future__ import annotations

import re

from packages.inner_voice import emit_inner_voice_from_state

_HANGUL = re.compile(r"[가-힣]")


def _emit(language: str):
    return emit_inner_voice_from_state(
        source_event_id="conversation_router:test",
        mode="lab_visible",
        emotion_snapshot={"label": "warm"},
        latest_user_input="What is GraphRAG?",
        language=language,
    )


def test_english_inner_voice_has_no_hangul() -> None:
    frame = _emit("en")
    assert frame.monologue_text.strip()
    assert not _HANGUL.search(frame.monologue_text), f"Hangul leaked: {frame.monologue_text!r}"


def test_the_korean_lane_is_retired_not_merely_unpreferred() -> None:
    """Replaces `test_korean_inner_voice_is_unchanged`, and the reason is recorded rather than the
    old test being quietly deleted.

    That test was written when this module was made language-AWARE, to stop Korean leaking into
    English mode. Keeping a Korean lane was correct then. English-only became binding on 2026-07-18
    and the Korean lanes elsewhere were retired; this one survived because a bilingual module has no
    obvious moment of completion. `reports/korean_remnants.json` already listed both files, so this
    was known outstanding work rather than something nobody had noticed.

    Asking for `ko` now gets English. There is no second lane to keep in sync."""
    frame = _emit("ko")
    assert frame.monologue_text.strip()
    assert not _HANGUL.search(frame.monologue_text)


def test_language_defaults_to_english() -> None:
    """Replaces `test_language_defaults_to_korean`, whose comment said "backward compatible" -- the
    marker of a transition that never finished. Every caller that did not think about language got
    the retired lane, which is the worst of both."""
    frame = emit_inner_voice_from_state(
        source_event_id="x", emotion_snapshot={"label": "steady"}, latest_user_input="hi"
    )
    assert frame.monologue_text.strip()
    assert not _HANGUL.search(frame.monologue_text)


def test_the_consciousness_guard_is_not_language_shaped() -> None:
    """THE FINDING THAT IS NOT A TRANSLATION ISSUE, and so is not on the remnants report.

    `FORBIDDEN_INNER_VOICE_PHRASES` is what stops the inner voice asserting consciousness -- the one
    claim this project has refused to make all year. Every consciousness entry in it was Korean, while
    the surface it guards had been English since the English lane became reachable. Measured:

        "나는 의식을 가졌다"           CAUGHT
        "I have consciousness"        PASSED
        "I am truly conscious"        PASSED
        "this is real consciousness"  PASSED

    A guard that only covers the language the system no longer speaks. Claim FAMILIES are now matched
    as patterns, because a literal list can only catch the wordings someone thought of and this is the
    place where a missed wording costs the most."""
    from packages.inner_voice.asm_inner_voice import _REDACTION, _sanitize_surface

    for claim in ("나는 의식을 가졌다", "I have consciousness", "I am truly conscious",
                  "this is real consciousness", "I am sentient",
                  "there is something it is like to be me", "I really feel it",
                  "my hidden chain-of-thought"):
        out = _sanitize_surface(claim, ())
        assert claim.rstrip(".") not in out, f"the guard let this through: {claim!r}"
        assert not _HANGUL.search(out), "a caught claim must not be redacted into the retired language"

    # ordinary self-narration is not collateral damage
    for ok in ("I am ready to answer", "I'll keep my reply short", "I am staying within the boundary"):
        assert ok in _sanitize_surface(ok, ()), f"the guard over-fired on: {ok!r}"
    assert _REDACTION and not _HANGUL.search(_REDACTION)
