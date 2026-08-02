# -*- coding: utf-8 -*-
"""Developmental milestones: announced only when a REAL measured gate is crossed, once each, in
order — the honest 'newborn -> infant -> ...' the owner asked for, never faked."""
import json

from packages.live_selfhood_cycle.development_stage import (
    LADDER, check_and_announce, current_stage)


def test_ladder_is_ordered_and_gated():
    keys = [s.key for s in LADDER]
    assert keys == ["newborn", "infant", "toddler", "child", "adolescent", "adult"]


def test_current_stage_needs_contiguous_gates_no_skipping():
    # infant gate met but newborn gate NOT -> cannot be infant (no skipped stages)
    s = {"self_in_world_pass": 0.0, "outward_curiosity_frac": 0.9}
    assert current_stage(s).key == "newborn"
    # newborn + infant met, toddler not -> infant
    s = {"self_in_world_pass": 1.0, "outward_curiosity_frac": 0.5, "s2_faithfulness": 0.1}
    assert current_stage(s).key == "infant"


def _isolate_metrics(monkeypatch, tmp_path):
    """Point the non-stream gate metrics at empty tmp files so a test exercises ONLY the
    stream-driven signal (outward curiosity) — real metrics on disk must not leak in."""
    import packages.live_selfhood_cycle.development_stage as ds
    for name in ("S2_METRIC", "SITU_METRIC", "HARD_EXAM_METRIC"):
        monkeypatch.setattr(ds, name, tmp_path / f"{name}.json")


def test_announces_advance_once_then_stays_quiet(tmp_path, monkeypatch):
    _isolate_metrics(monkeypatch, tmp_path)
    state = tmp_path / "stage.json"
    stream = tmp_path / "life.jsonl"
    # a stream where curiosity has turned outward: 4 world-facing, 1 self -> 0.8 >= 0.30
    rows = [{"meta": {"source": "curious_search"}, "content": "I looked up global tortoise ranges"},
            {"meta": {"source": "perception"}, "content": "the world says: new telescope image"},
            {"meta": {"source": "curiosity"}, "content": "what makes basalt columns hexagonal"},
            {"meta": {"source": "curiosity"}, "content": "how do glaciers carve fjords"},
            {"meta": {"source": "curiosity"}, "content": "my speech weak is still with me"}]
    stream.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    seen = []
    m1 = check_and_announce(record_fn=seen.append, stream=stream, state_path=state)
    # newborn gate is live (self-causal reasoner passes) + infant gate met -> lands at infant
    assert m1 and m1["stage"] == "infant" and "infant" in m1["announcement"]
    assert len(seen) == 1
    # second check, same state -> no re-announcement
    m2 = check_and_announce(record_fn=seen.append, stream=stream, state_path=state)
    assert m2 is None and len(seen) == 1


def test_regression_never_un_childs(tmp_path, monkeypatch):
    _isolate_metrics(monkeypatch, tmp_path)
    state = tmp_path / "stage.json"
    stream = tmp_path / "life.jsonl"
    outward = [{"meta": {"source": "curious_search"}, "content": f"looked up thing {i}"}
               for i in range(5)]
    stream.write_text("\n".join(json.dumps(r) for r in outward), encoding="utf-8")
    check_and_announce(record_fn=lambda t: None, stream=stream, state_path=state)
    # now a bad day: all inward again
    inward = [{"meta": {"source": "curiosity"}, "content": "my own wiring worries me"}
              for _ in range(5)]
    stream.write_text("\n".join(json.dumps(r) for r in inward), encoding="utf-8")
    # high-water mark only rises: no announcement, and the stored stage does not drop
    m = check_and_announce(record_fn=lambda t: None, stream=stream, state_path=state)
    assert m is None
    assert json.loads(state.read_text(encoding="utf-8"))["stage"] == "infant"
