# -*- coding: utf-8 -*-
"""Mineness (B3-deep): every moment given as MINE — one continuous owner, agency role, real
continuity. The functional structure of for-me-ness; no qualia claimed."""
from packages.live_selfhood_cycle.mineness import continuity_report, own
from packages.temporal_reasoning.unified_timeline import Timeline


def test_a_produced_thought_is_mine_as_author():
    o = own("I decide to work on my speech", "self_development", birth=("Initial skeleton", 39.0))
    assert o.mine and o.role == "author"
    assert "mine" in o.report.lower() and "39 days ago" in o.report


def test_an_arriving_perception_is_mine_as_undergoer():
    o = own("I looked it up: fjords", "curious_search", birth=("Initial skeleton", 39.0))
    assert o.mine and o.role == "undergoer" and "happening to me" in o.report


def test_an_interoceptive_notice_is_mine_as_witness():
    o = own("my speech is still weak", "interoception", birth=("Initial skeleton", 39.0))
    assert o.role == "witness" and "find in myself" in o.report


def test_stream_is_single_owner_and_unbroken(tmp_path):
    tl = Timeline(path=tmp_path / "tl.jsonl")
    for i in range(4):
        tl.record("thought", f"moment {i}", who="atanor")
    rep = continuity_report(tl)
    assert rep["single_owner"] and rep["unbroken"] and rep["moments"] == 4


def test_the_beat_stamps_every_moment_as_mine(tmp_path):
    from packages.live_selfhood_cycle.life import Life
    import json
    life = Life(stream_path=tmp_path / "life.jsonl"); life._browser_ok = False
    for _ in range(5):
        life.step()
    metas = [json.loads(ln).get("meta", {}) for ln in
             (tmp_path / "life.jsonl").read_text(encoding="utf-8").splitlines()]
    thoughts = [m for m in metas if m.get("inner_voice")]
    assert thoughts and all(m.get("mine") for m in thoughts)          # not one anonymous moment
    assert all(m.get("mine_role") in ("author", "undergoer", "witness") for m in thoughts)
