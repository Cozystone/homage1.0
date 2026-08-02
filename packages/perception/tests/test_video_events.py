# -*- coding: utf-8 -*-
"""Video → events → memory → reasoning stitch. The milk/fridge and keys/desk scenarios from the
Copilot proposal, run over per-frame scene graphs (the shape perception.scene_graph.build emits)."""
from packages.perception.video_events import (events_from_frames, understand_video, to_memory,
                                              diff_frames)


def _g(nodes, edges):
    return {"nodes": [{"label": n, "count": 1} for n in nodes],
            "edges": [{"subject": s, "relation": r, "object": o} for s, r, o in edges]}


def test_take_event_from_possession_change():
    # frame 1: fridge contains milk; frame 2: person contains (holds) milk -> TAKE
    f1 = _g(["person", "fridge", "milk"], [("fridge", "contains", "milk")])
    f2 = _g(["person", "fridge", "milk"], [("person", "contains", "milk")])
    evs = diff_frames(f1, f2, 1)
    kinds = {(e.kind, e.subject, e.obj) for e in evs}
    assert ("take", "person", "milk") in kinds


def test_milk_scenario_narrative_and_hypothesis():
    frames = [
        _g(["person", "fridge"], []),                                   # walks in
        _g(["person", "fridge"], [("person", "near", "fridge")]),       # approaches fridge
        _g(["person", "fridge", "milk"], [("fridge", "contains", "milk")]),
        _g(["person", "fridge", "milk"], [("person", "contains", "milk")]),  # takes milk
    ]
    out = understand_video(frames)
    texts = " ".join(n["text"] for n in out["narrative"]).lower()
    assert "approached the fridge" in texts
    assert "took the milk" in texts
    # intent is a FLAGGED hypothesis, never asserted as fact
    assert out["intent_hypotheses"], "should offer an intent hypothesis"
    h = out["intent_hypotheses"][0]
    assert h["is_hypothesis"] is True and "milk" in h["hypothesis"]
    assert h["grounded_in"]                                             # auditable, not invented


def test_keys_on_desk_recall_from_memory():
    # keys placed near desk at t1, person leaves; later "where are the keys?" -> recall, not re-watch
    frames = [
        _g(["person", "keys", "desk"], [("person", "contains", "keys")]),   # holding keys
        _g(["person", "keys", "desk"], [("keys", "near", "desk")]),         # keys -> desk (released)
    ]
    out = understand_video(frames)
    mem = out["memory"]
    # released keys: held_by cleared (gap). The desk relation persists as recallable memory.
    rel = mem.current("keys", "near", viewer="public")
    assert rel is not None and rel[0] == "desk"


def test_events_trace_to_frame_diffs_only():
    # an empty->empty transition invents nothing
    assert events_from_frames([_g([], []), _g([], [])]) == []


def test_object_permanence_prediction():
    """Ball thrown behind wall: it vanishes from frame, world model PREDICTS it still exists."""
    from packages.perception.video_events import predict_next
    frames = [_g(["ball", "wall"], [("ball", "near", "wall")]),
              _g(["wall"], [])]                                    # ball occluded by wall
    pred = predict_next(frames)
    assert any(p["label"] == "ball" and p["is_prediction"] for p in pred["persist"])


def test_surprise_drives_think_harder():
    from packages.perception.video_events import predict_next, surprise, events_from_frames
    frames = [_g(["person", "cup"], [("person", "contains", "cup")]),  # took cup
              _g(["person", "cup"], [])]                                # nothing follows
    pred = predict_next(frames)
    s = surprise(pred, frames[-1], events_from_frames(frames[-2:]))
    assert 0.0 <= s["surprise"] <= 1.0 and isinstance(s["think_harder"], bool)
