# -*- coding: utf-8 -*-
"""Autonomous surfing: politeness, block-as-observation, and media routing.

No network in these tests -- the browser body is exercised live via scripts; here we pin the
POLICY invariants that must never regress (robots parsing, block detection, back-off, and the
honest degradation of the media lane)."""
import json

import packages.atanor_browser.autonomous_surf as surf


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(surf, "_DIR", tmp_path)
    monkeypatch.setattr(surf, "_BLOCKS", tmp_path / "blocked_origins.json")
    monkeypatch.setattr(surf, "_JOURNAL", tmp_path / "surf_journal.jsonl")


def test_robots_bom_does_not_disallow_whole_site(monkeypatch):
    """A UTF-8 BOM on robots.txt used to make EVERY path report disallowed (measured on
    wikipedia). The parser must decode utf-8-sig."""
    body = "﻿# comment\nUser-agent: *\nDisallow: /w/\nDisallow: /wiki/Special:\n".encode()

    class _R:
        def read(self, *_): return body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(surf.urllib.request, "urlopen", lambda *a, **k: _R())
    surf._ROBOTS.clear()
    assert surf.robots_allows("https://example.org/wiki/Rocket") is True
    assert surf.robots_allows("https://example.org/wiki/Special:Random") is False


def test_human_check_makes_us_step_away_for_now_not_forever(tmp_path, monkeypatch):
    """A human-check is not a verdict: one encounter -> step away for now (short cooloff), no
    permanent label, no strike count. The origin is fair game again after the cooloff."""
    _fresh(tmp_path, monkeypatch)
    url = "https://walled.example/search?q=x"
    assert surf.origin_backed_off(url) is False
    surf.record_block(url, "bot-check page (captcha)")
    assert surf.origin_backed_off(url) is True               # go read elsewhere for now
    assert surf.origin_backed_off(url, cooloff_s=0) is False  # ...but come back soon, no grudge
    saved = json.loads((tmp_path / "blocked_origins.json").read_text(encoding="utf-8"))
    # only 'when we last stepped away' is stored -- no count, no reasons, no judgment about the site
    assert set(saved["https://walled.example"].keys()) == {"last_ts"}


def test_block_markers_cover_real_challenge_text():
    """The live duckduckgo html endpoint served this on 2026-07-20."""
    real = ("unfortunately, bots use duckduckgo too. please complete the following challenge to "
            "confirm this search was made by a human.")
    assert any(m in real for m in surf._BLOCK_MARKERS)


def test_page_perception_main_text_prefers_main_over_body():
    p = surf.PagePerception(url="u", regions={"main": "the article", "body": "everything else"})
    assert p.main_text() == "the article"


def test_perceive_media_degrades_honestly_without_organs(monkeypatch):
    """Video/audio are declared ports; an undecodable item yields a status, never a fabricated
    percept."""
    p = surf.PagePerception(url="u", reading_order=["rocket engine ignition sequence"],
                            media=[surf.MediaRef(kind="video", url="https://x/v.mp4")])
    out = surf.perceive_media(p)
    assert out == [] or out[0]["status"] in ("port_declared_not_decoded", "no_detector_entry")
