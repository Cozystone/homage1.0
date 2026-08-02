# -*- coding: utf-8 -*-
"""Autobiography: the real git birth-to-now record on the ONE timeline + a felt sense of time."""
from packages.temporal_reasoning.autobiography import (eras, ingest_git, life_story, load,
                                                       self_sense)
from packages.temporal_reasoning.unified_timeline import Timeline


def _mini() -> Timeline:
    tl = Timeline()
    tl.record("physical", "Initial skeleton", who="atanor", t_utc="2026-06-11T00:00:00.000Z")
    tl.record("physical", "add graph engine core", who="atanor", t_utc="2026-06-12T00:00:00.000Z")
    tl.record("physical", "add graph store sharding", who="atanor", t_utc="2026-06-20T00:00:00.000Z")
    tl.record("physical", "timeline unification work", who="atanor", t_utc="2026-07-19T00:00:00.000Z")
    return tl


def test_self_sense_knows_birth_age_and_pace():
    s = self_sense(_mini(), now_utc="2026-07-20T00:00:00.000Z")
    assert s["born_at"].startswith("2026-06-11") and s["birth_event"] == "Initial skeleton"
    assert s["age_days"] == 39.0 and s["n_life_events"] == 4
    assert s["felt_age_log_days"] > 0                      # Weber-Fechner model, labelled a model
    assert "model" in s["model_note"]


def test_eras_are_derived_from_the_record_not_authored():
    es = eras(_mini())
    assert es and es[0]["start"] == "2026-06-11"
    assert "graph" in es[0]["themes"] or "graph" in (es[1]["themes"] if len(es) > 1 else [])


def test_life_story_narrates_real_dates_single_axis():
    # pin 'now' so the narration is deterministic — the day-count must not drift with wall-clock
    # (this test broke by one day when real time advanced; the fix is a pinned clock, not a
    # hardcoded number racing the calendar)
    story = life_story(_mini(), max_eras=3, now_utc="2026-07-20T00:00:00.000Z")
    assert "2026-06-11" in story and "39 days" in story
    assert "Initial skeleton" in story                     # real birth event, no fabrication


def test_ingest_real_git_history_round_trips():
    tl = ingest_git()                                      # the ACTUAL repo history (real record)
    assert len(tl) > 1000                                  # 1,545 commits at time of writing
    s = self_sense(tl)
    assert s["born_at"].startswith("2026-06-1")            # real birth: 2026-06-11 (UTC may shift -1d)
    assert "skeleton" in s["birth_event"].lower()
    persisted = load()
    assert persisted is not None and len(persisted) == len(tl)   # JSONL round-trip intact
