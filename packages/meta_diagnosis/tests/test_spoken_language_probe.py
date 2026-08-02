# -*- coding: utf-8 -*-
"""English-only, checked by making the system SPEAK rather than by grepping for Hangul."""
from __future__ import annotations

from packages.meta_diagnosis.spoken_language_probe import HANGUL, STATES, probe


def test_the_speaking_organs_speak_english_in_every_state():
    """The standing gate.

    Grepping `packages/` finds 592 files and 6120 lines containing Hangul, and almost all of it is
    comments, Korean test fixtures, and input-side handling the system must still be able to READ.
    English-only is a rule about what this system SAYS, and a line count cannot tell those apart.

    So this drives each speaking organ across several internal states and looks at what comes OUT.
    Several states, because a surface that is English in the calm branch and Korean in the alarmed one
    is exactly what a single call misses -- and the alarmed branch is the one a person is most likely
    to see."""
    r = probe()
    assert not r["errors"], f"an organ could not be driven: {r['errors']}"
    assert r["fields_that_spoke_korean"] == 0, r["rows"]


def test_an_organ_that_cannot_be_driven_is_not_reported_as_clean():
    """The instrument's own guard. The first version put the "could not drive" marker into the same
    list it counted as findings, so a driver bug reported itself as three Korean fields. The opposite
    failure -- a broken driver reading as a pass -- is the one that would matter, so `clean` requires
    no errors as well as no Korean."""
    r = probe()
    assert r["clean"] is (r["fields_that_spoke_korean"] == 0 and not r["errors"])


def test_the_self_modification_path_cannot_reintroduce_the_retired_language():
    """Found by translating the voice and watching two SAFETY tests go red.

    `code_self_modification` proposes new phrasings that are INSERTED into `voice.py` -- they become
    things this system says. Its variant pool was Korean, so every time the mind noticed it was
    repeating itself it would have written the retired language back into the spoken lane. A
    translation that undoes itself."""
    from packages.continuous_self.code_self_modification import _WHITELIST, _compose_fresh_phrasing

    class _S:
        ticks = 0

    for i in range(4):
        _S.ticks = i
        assert not HANGUL.search(_compose_fresh_phrasing(_S, "seed"))
    for anchor in _WHITELIST["voice.py"]["lists"].values():
        assert not HANGUL.search(anchor)


def test_the_probe_drives_more_than_one_state():
    """A single call only ever exercises one branch, and the untested branch is where a retired lane
    survives. This pins that the probe keeps sweeping."""
    assert len(STATES) >= 3
    assert len({s["label"] for s in STATES}) == len(STATES)
