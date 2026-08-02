# -*- coding: utf-8 -*-
"""The failure-receipt engine must turn accumulated rejections into a search steer — steering AWAY
from junk-heavy domains and jumping harder when failure concentrates — and stay inert when empty."""
from pathlib import Path

import packages.flywheel.failure_receipts as fr


def _isolate(tmp_path: Path):
    fr._ARCHIVE = tmp_path / "receipts.jsonl"


def test_empty_ledger_is_inert(tmp_path):
    _isolate(tmp_path)
    b = fr.search_bias()
    assert b["avoid_topics"] == [] and b["sampled"] == 0
    assert b["jump_probability"] == 0.15                       # a neutral default, not invented
    assert fr.should_avoid("anything") is False


def test_concentrated_failure_raises_jump_and_flags_topic(tmp_path):
    _isolate(tmp_path)
    for _ in range(20):
        fr.record_receipt(topic="라리가일정", causes=["foreign", "run_on"], source="critic")
    for _ in range(2):
        fr.record_receipt(topic="철학", causes=["dangling"], source="critic")
    b = fr.search_bias()
    assert b["sampled"] == 22

    assert any(a["topic"] == "라리가일정" for a in b["avoid_topics"])
    assert not any(a["topic"] == "철학" for a in b["avoid_topics"])   # a rare topic is spared
    assert b["jump_probability"] >= 0.7
    assert fr.should_avoid("라리가일정") is True
    assert fr.should_avoid("철학") is False


def test_gap_receipts_steer_toward_not_away(tmp_path):
    _isolate(tmp_path)

    for _ in range(12):
        fr.record_receipt(topic="상대성이론", causes=["abstain"], source="flywheel", kind="gap")
    for _ in range(12):
        fr.record_receipt(topic="라리가일정", causes=["foreign"], source="critic", kind="junk")
    b = fr.search_bias()
    assert any(s["topic"] == "상대성이론" for s in b["seek_topics"])       # a gap → seek
    assert not any(a["topic"] == "상대성이론" for a in b["avoid_topics"])   # never avoided
    assert any(a["topic"] == "라리가일정" for a in b["avoid_topics"])       # junk → avoid
    assert not any(s["topic"] == "라리가일정" for s in b["seek_topics"])
    assert fr.should_avoid("상대성이론") is False                          # a gap is not avoided


def test_diffuse_failure_keeps_jump_low(tmp_path):
    _isolate(tmp_path)
    for i in range(30):
        fr.record_receipt(topic=f"topic_{i}", causes=["run_on"], source="critic")
    b = fr.search_bias()
    assert b["jump_probability"] <= 0.2                        # no single domain dominates
    assert b["avoid_topics"] == []                            # nothing is junk-heavy


def test_dominant_causes_surface(tmp_path):
    _isolate(tmp_path)
    for _ in range(10):
        fr.record_receipt(topic="x", causes=["foreign"], source="critic")
    for _ in range(3):
        fr.record_receipt(topic="y", causes=["repetition"], source="critic")
    causes = fr.search_bias()["dominant_causes"]
    assert causes.get("foreign", 0) > causes.get("repetition", 0)


def test_ring_buffer_bounds(tmp_path):
    _isolate(tmp_path)
    fr._MAX_RECEIPTS = 50
    for i in range(80):
        fr.record_receipt(topic="t", causes=["run_on"], source="s")
    assert len(fr._load()) == 50
    fr._MAX_RECEIPTS = 5000
