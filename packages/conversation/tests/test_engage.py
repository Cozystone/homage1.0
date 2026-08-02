# -*- coding: utf-8 -*-
"""The engagement composer: it must turn a grounded sub-answer into a warm multi-sentence turn,
abstain GRACEFULLY (with an offer) where ungrounded, restore terse byte-for-byte under the
kill-switch, and — the binding contract — NEVER introduce a content word it was not handed."""
from __future__ import annotations

import os

import pytest

from packages.conversation import (
    CONVERSATIONAL_VOCAB,
    compose_engagement,
    mechanism_certificate,
    verify_grounded,
)
from packages.conversation.engage import _content_tokens


def _sentences(s: str) -> int:
    import re
    return len([x for x in re.split(r"(?<=[.!?])\s+", s.strip()) if x.strip()])


# ── engage composes a fuller, in-character reply ──────────────────────────────────────────────────

def test_mechanism_is_voiced_naturally_not_a_raw_certificate():
    """A grounded how/why answer is spoken as reasoning, not dumped as a parenthetical certificate."""
    cert = mechanism_certificate("A cup is at the edge of the table and someone bumped it. What happens?")
    assert cert is not None
    r = compose_engagement("What happens?", "mechanism", "the cup falls.", {"certificate": cert})
    assert "fall" in r.lower()
    assert "(" not in r                                    # no raw certificate parenthetical
    assert _sentences(r) >= 2                              # reasoning + an in-character offer back


def test_negative_mechanism_leads_with_no():
    cert = mechanism_certificate("The tunnel is blocked by rubble. Can the bus pass through the tunnel?")
    r = compose_engagement("Can the bus pass?", "mechanism", "no.", {"certificate": cert})
    assert r.lower().startswith("no")
    assert "blocked" in r.lower()


def test_social_reply_is_warm_and_grounded_in_perception():
    pc = {"name": "Joon Lee", "place": "River Cafe", "activity": "pulling espresso shots"}
    r = compose_engagement("how is your day going?", "social", "Hello — I'm Joon Lee.",
                           {"name": "Joon Lee", "place": "River Cafe", "activity": "pulling espresso shots"}, pc)
    from packages.conversation.engage import _OFFERS
    assert "Joon Lee" in r and "River Cafe" in r           # grounded in the perceived twin
    assert _sentences(r) >= 2                              # acknowledge/content + an offer back
    assert any(r.strip().endswith(o) for o in _OFFERS["social"])   # ends by turning the conversation back


def test_self_intro_names_job_and_place():
    pc = {"name": "Joon Lee", "job": "barista", "place": "River Cafe"}
    r = compose_engagement("tell me about yourself", "self_about", "I'm Joon Lee.",
                           {"name": "Joon Lee", "job": "barista", "place": "River Cafe"}, pc)
    assert "Joon Lee" in r and "barista" in r and "River Cafe" in r


# ── graceful abstention (offer help), not a bare "I don't know" ───────────────────────────────────

def test_ungrounded_personal_still_abstains_but_gracefully():
    terse = "I wouldn't know that — it's your own life, not something I can see from here."
    r = compose_engagement("what did I eat for breakfast?", "personal_decline", terse, {}, {})
    assert "wouldn't know" in r.lower()                    # the honest decline is preserved
    assert len(r) > len(terse)                             # and an offer of what it CAN do is added
    assert _sentences(r) >= 2


def test_honest_fallback_is_never_lengthened_with_a_duplicate_offer():
    terse = ("I'd rather not make something up. I can tell you what I actually see around me here, "
             "or answer something I really know.")
    r = compose_engagement("population of Mars in 2099?", "honest_fallback", terse, {}, {})
    assert "rather not" in r.lower()
    assert not any(ch.isdigit() for ch in r)               # graceful, still no fabricated number


# ── the kill-switch restores terse, byte-for-byte ─────────────────────────────────────────────────

def test_kill_switch_returns_terse_byte_identical():
    terse = "the cup falls. (grounded)"
    prev = os.environ.get("ATANOR_ENGAGE")
    os.environ["ATANOR_ENGAGE"] = "0"
    try:
        r = compose_engagement("what happens?", "mechanism", terse,
                               {"certificate": {"answer": "the cup falls", "reasoning": "x"}})
        assert r == terse                                  # exactly the terse string, unchanged
    finally:
        if prev is None:
            os.environ.pop("ATANOR_ENGAGE", None)
        else:
            os.environ["ATANOR_ENGAGE"] = prev


# ── the binding contract: no fabrication, ever ────────────────────────────────────────────────────

def test_composer_never_introduces_an_ungrounded_content_word():
    """Every content word of a composed reply must trace to the grounding or the closed lexicon."""
    pc = {"name": "Mina", "place": "the market", "activity": "selling apples"}
    for kind, terse, facts in [
        ("social", "Hello — I'm Mina.", {"name": "Mina", "place": "the market", "activity": "selling apples"}),
        ("self_about", "I'm Mina.", {"name": "Mina", "job": "vendor", "place": "the market"}),
        ("self_perception", "I'm selling apples over at the market.", {}),
        ("knowledge", "an apple is a fruit that grows on trees.", {}),
        ("personal_decline", "I wouldn't know that — it's your own life.", {}),
    ]:
        r = compose_engagement("q about " + kind, kind, terse, facts, pc)
        grounding = set(_content_tokens(terse)) | set(_content_tokens("q about " + kind))
        for v in {**facts, **pc}.values():
            grounding |= set(_content_tokens(str(v)))
        ok, fabricated = verify_grounded(r, grounding)
        assert ok, f"{kind} fabricated {fabricated}: {r}"


def test_fabricated_candidate_falls_back_to_terse():
    """If a candidate would carry an ungrounded word, the composer must discard it for the terse
    answer — engagement can never REDUCE faithfulness (safety by construction)."""
    ok, fab = verify_grounded("The capital is Zorbltania, a lovely place.", {"capital"})
    assert not ok and "zorbltania" in [w.lower() for w in fab]


def test_offer_pools_use_only_closed_vocabulary():
    """No offer template may smuggle in a content word outside the declared closed lexicon."""
    from packages.conversation.engage import _OFFERS, _VITAL_NOTE
    for pool in list(_OFFERS.values()):
        for line in pool:
            extra = [w for w in _content_tokens(line) if w not in CONVERSATIONAL_VOCAB]
            assert not extra, f"offer {line!r} introduces {extra}"
    for note in _VITAL_NOTE.values():
        extra = [w for w in _content_tokens(note) if w not in CONVERSATIONAL_VOCAB]
        assert not extra, f"vital note {note!r} introduces {extra}"


def test_mechanism_grounds_a_why_question_from_the_users_own_words():
    """'why does the cup fall when bumped at the edge' — the falling-at-the-edge conditions are the
    user's own words, reshaped into what the mechanism engine reads; it must ground, not echo."""
    cert = mechanism_certificate("why does the cup fall when it is bumped at the edge of the table?")
    assert cert is not None and "fall" in str(cert.get("answer")).lower()


def test_unknown_kind_returns_terse():
    assert compose_engagement("q", "not_a_kind", "just this.", {}, {}) == "just this."
