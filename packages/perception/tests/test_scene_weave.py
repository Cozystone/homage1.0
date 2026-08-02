# -*- coding: utf-8 -*-
"""Scene weave — a living context narrative that speaks on CHANGE, like a person, not a classifier log."""
from __future__ import annotations

from packages.perception.scene_weave import new_state, observe


def test_first_sight_narrates_the_full_scene():
    st = new_state()
    out = observe(st, ["사람", "책장"], "가운데에 사람, 왼쪽에 책장이 보이는 공간이에요.", now=100.0)
    assert out["changed"] and out["narrative"].startswith("가운데에 사람")


def test_unchanged_room_stays_silent():
    st = new_state()
    observe(st, ["사람", "책장"], "S1", now=100.0)
    out = observe(st, ["사람", "책장"], "S1", now=103.0)
    assert out["narrative"] is None and out["changed"] is False    # nothing new → say nothing
    assert out["last_sentence"] == "S1"                            # the last remark stands


def test_new_object_narrates_appearance_with_correct_josa():
    st = new_state()
    observe(st, ["사람"], "S1", now=100.0)
    out = observe(st, ["사람", "컵"], "S2", now=104.0)
    assert out["changed"] and "컵이 새로 보였어요" in out["narrative"]
    out2 = observe(st, ["사람", "컵", "의자"], "S3", now=108.0)
    assert "의자가 새로 보였어요" in out2["narrative"]


def test_disappearance_after_grace_window_not_on_flicker():
    st = new_state()
    observe(st, ["사람", "컵"], "S1", now=100.0)
    observe(st, ["사람", "컵"], "S1", now=104.0)          # cup seen twice → an ESTABLISHED thread
    # a missed frame (flicker) inside the 12s grace window → no death
    out = observe(st, ["사람"], "S1", now=108.0)
    assert not any(e["kind"] == "gone" for e in out["events"])
    # still gone well past the window → an honest, narrated disappearance
    out2 = observe(st, ["사람"], "S1", now=118.0)
    assert any(e["kind"] == "gone" and e["label"] == "컵" for e in out2["events"])
    assert "컵이 시야에서 사라졌네요" in out2["narrative"]


def test_a_one_frame_blip_expires_silently_no_phantom_disappearance():

    st = new_state()
    observe(st, ["사람"], "S1", now=100.0)
    observe(st, ["사람", "그림자물체"], "S1", now=104.0)   # a single flicker detection
    out = observe(st, ["사람"], "S1", now=140.0)           # long gone
    assert not any(e["kind"] == "gone" for e in out["events"])
    assert st["threads"]["그림자물체"]["alive"] is False          # it did quietly end, just unspoken


def test_return_after_long_absence_is_a_reunion():
    st = new_state()
    observe(st, ["사람"], "S1", now=100.0)
    observe(st, ["사람"], "S1", now=104.0)               # seen twice → established
    observe(st, [], "S1", now=120.0)                    # person leaves (past the 12s grace)
    out = observe(st, ["사람"], "S1", now=200.0)         # comes back 80s later
    assert "사람이 다시 보여요" in out["narrative"]
    assert st["threads"]["사람"]["times"] == 2            # the thread remembers it met them twice
