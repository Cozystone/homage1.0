# -*- coding: utf-8 -*-
"""Realcity adapter x learned intent router — retirement wiring tests.

The greeting / personal-life / self-situation routing DECISION is now made by the learned intent
router (packages/base_brain/intent_router.py), with the regexes demoted to feature extractors. These
tests pin the two contract guarantees:
  1. with the router ON (default), the routing outcomes are unchanged on the golden probe set;
  2. the kill-switch (ATANOR_INTENT_ROUTER=0) restores the OLD hand-regex behaviour BYTE-IDENTICALLY.
"""
from __future__ import annotations

import pytest

from apps.api.app.routers.realcity_agent import _answer, _perceive, _route


@pytest.fixture(autouse=True)
def _isolate_routing_layer(monkeypatch):
    """These tests pin the intent-ROUTING layer, whose goldens are the terse routing outputs. The
    engagement composer (ATANOR_ENGAGE, packages/conversation) is a separate SURFACE layer stacked
    above routing and is covered by its own tests; pin it off here so the router-layer guarantees are
    measured in isolation — byte-identical routing, unchanged by whether engagement is on."""
    monkeypatch.setenv("ATANOR_ENGAGE", "0")

_GREETING = """You are an autonomous person living in RealCity.
Name: Joon Lee
Job: barista
Current activity: pulling espresso shots
Current place: River Cafe
Reflection: Joon Lee is pulling espresso shots near River Cafe; strongest pressure is checking in with someone; 3 known contacts
City state: mid-morning, light foot traffic on Depot-gil
A player walks up and asks what is happening here."""
_PHONE = """You are a named autonomous RealCity NPC replying through RealPhone.
Name: Yujin Choi
Job: nurse
Current place/activity: Hanbit Hospital / on shift
Player message: where are you right now?"""

_PG = _perceive(_GREETING, None)
_PP = _perceive(_PHONE, None)

# probes that exercise the routed (deterministic) branches, with the OLD behaviour captured verbatim
# from the pre-retirement adapter (the golden reference for the byte-identical kill-switch guarantee).
_PROBES = [
    ("hello how are you", None, "Sora", None),
    ("what did I eat for breakfast yesterday?", None, "Roo", None),
    ("where are you right now?", None, "Yujin Choi", _PP),
    ("what is happening here", None, "Joon Lee", _PG),
    ("who are you?", None, "Mina", {"name": "Mina", "job": "barista", "place": "River Cafe"}),
    ("what are you doing?", None, "Mina", {"name": "Mina", "activity": "pulling shots", "place": "River Cafe"}),
]
_GOLDEN = [
    "Hello — I'm Sora. I'm out in the city. What would you like to know?",
    "I wouldn't know that — it's your own life, not something I can see from here.",
    "I'm at Hanbit Hospital right now, on shift.",
    ("I'm pulling espresso shots over at River Cafe; what's pulling at me is checking in with someone; "
     "around me: mid-morning, light foot traffic on Depot-gil. That's honestly what I can see from here."),
    "I'm Mina, a barista. I'm around River Cafe just now.",
    "I'm pulling shots at River Cafe.",
]


def test_router_on_preserves_golden_outputs():
    """Router ON (default): the learned decision reproduces the old branch on the probe set."""
    for (q, w, a, pc), want in zip(_PROBES, _GOLDEN):
        assert _answer(q, w, a, pc) == want, q


def test_killswitch_restores_old_behaviour_byte_identical(monkeypatch):
    """ATANOR_INTENT_ROUTER=0 -> the exact original regex ladder, byte-for-byte."""
    monkeypatch.setenv("ATANOR_INTENT_ROUTER", "0")
    for (q, w, a, pc), want in zip(_PROBES, _GOLDEN):
        assert _answer(q, w, a, pc) == want, q


def test_route_labels_match_between_on_and_off(monkeypatch):
    """The routing LABEL is the same whether the learned router or the fallback ladder decides it,
    for the probe set (this is why the outputs are byte-identical)."""
    labels_on = [_route(q) for q, *_ in _PROBES]
    monkeypatch.setenv("ATANOR_INTENT_ROUTER", "0")
    labels_off = [_route(q) for q, *_ in _PROBES]
    assert labels_on == labels_off
    assert labels_on == ["social", "personal", "self_situation", "self_situation",
                         "self_situation", "self_situation"]


def test_killswitch_falls_back_when_artifacts_absent(monkeypatch):
    """If the router artifact is missing, the adapter gracefully uses the old ladder (no crash, no
    self-heal at request time)."""
    import packages.base_brain.intent_router as ir
    monkeypatch.setattr(ir, "_WEIGHTS_PATH", ir._DATA_DIR / "does_not_exist.json")
    # _intent_router() must return None -> fallback ladder -> still the golden greeting
    r = _answer("hello how are you", None, "Sora", None)
    assert r == "Hello — I'm Sora. I'm out in the city. What would you like to know?"


def test_knowledge_route_still_abstains_on_ungrounded():
    """A relational fact the store cannot ground still abstains (unchanged), not fabricates. Uses a
    fictional entity the graph holds no capital edge for — 'capital of France' now resolves to Paris
    once the knowledge_harvest edges are ingested, so it is no longer an 'ungroundable' fixture."""
    r = _answer("what is the capital of Wakanda?", None, "Joon Lee", {"name": "Joon Lee"})
    assert "washington" not in r.lower()
    assert "rather not" in r.lower() or "really know" in r.lower()
