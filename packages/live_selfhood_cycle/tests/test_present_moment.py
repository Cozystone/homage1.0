# -*- coding: utf-8 -*-
"""The bound present (B1-deep + B4): one experienced now with temporal thickness — retention,
bound centre, protention — all read from real state, no qualia claimed."""
from packages.live_selfhood_cycle.present_moment import Moment, compose_moment
from packages.temporal_reasoning.unified_timeline import Timeline


def test_moment_binds_now_feeling_percept_with_temporal_flanks(tmp_path):
    tl = Timeline(path=tmp_path / "tl.jsonl")
    tl.record("thought", "I keep circling my router weakness", who="atanor")
    tl.record("perception", "I looked it up: basalt columns — the world says: hexagonal cooling",
              who="atanor", meta={"source": "curious_search"})
    m = compose_moment(tl, "now I wonder what cooling has to do with shape",
                       {"cortisol": 0.1, "dopamine": 0.6}, protention="the owner may return")
    assert m.now.startswith("now I wonder")
    assert m.retention and "router weakness" in m.retention[-1]      # the just-past echoes
    assert "hexagonal" in m.percept                                  # perception bound into the now
    assert m.feeling["tone"] == "quickened" and m.protention          # feeling + lean-in present
    assert m.depth >= 1                                              # the present has backward width


def test_as_lived_reads_as_one_thick_present(tmp_path):
    tl = Timeline(path=tmp_path / "tl.jsonl")
    tl.record("thought", "a worry about my speech", who="atanor")
    m = compose_moment(tl, "here is the next thought", {"cortisol": 0.9},
                       protention="a question forming")
    lived = m.as_lived()
    assert "still with me" in lived and "here is the next thought" in lived
    assert "leaning toward" in lived                                 # retention + now + protention, bound


def test_the_beat_records_a_present_with_depth(tmp_path):
    from packages.live_selfhood_cycle.life import Life
    life = Life(stream_path=tmp_path / "life.jsonl")
    life._browser_ok = False
    reps = [life.step() for _ in range(6)]
    assert any(r.get("moment", {}).get("as_lived") for r in reps)
    import json
    metas = [json.loads(ln).get("meta", {}) for ln in
             (tmp_path / "life.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any("present_depth" in m for m in metas)                 # thickness recorded on the spine
