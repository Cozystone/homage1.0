# -*- coding: utf-8 -*-
"""Dialogue coach + Chinese-room coach — deterministic tests (mentor mocked, zero cost):
the coach observes REAL transcript text, seeds only TOPIC NAMES; the room coach's demonstrations
are assembled from real organs/ledgers; nothing the mentor says is written into any brain."""
from __future__ import annotations

import json
from collections import namedtuple

import packages.advisor_loop.chinese_room_coach as crc
import packages.advisor_loop.dialogue_coach as dc

_Ex = namedtuple("Ex", "reply injection_findings")
_Cand = namedtuple("Cand", "status paths reason")

_CRITIQUE = ("1. In the quoted turns the answer ignores the running topic.\n"
             "2. Yes — a context failure; carrying recent topics into search would show it overcome.\n"
             "3. Practice: state, border.\n"
             "4. Physical: friction.\n"
             "TOPICS: state, border, friction")


def _mock(monkeypatch, mod):
    monkeypatch.setattr(mod, "ask_cli",
                        lambda advisor, prompt, timeout_s=240: _Ex(reply=_CRITIQUE, injection_findings=0))
    monkeypatch.setattr(mod, "intake",
                        lambda advisor, reply, summary="": _Cand("advice_only", [], ""))


# ---------- dialogue coach ----------

def test_coach_parses_topics_and_seeds_file(monkeypatch, tmp_path):
    _mock(monkeypatch, dc)
    monkeypatch.setattr(dc, "TRANSCRIPT", tmp_path / "t.log")
    monkeypatch.setattr(dc, "TOPICS", tmp_path / "topics.json")
    monkeypatch.setattr(dc, "LOG", tmp_path / "coach.jsonl")
    (tmp_path / "t.log").write_text("01:00  atanor-pc > what is state?\n"
                                    "01:00  atanor-edge > Topics referred to by the same term\n",
                                    encoding="utf-8")
    rec = dc.coach_round(advisor="mock", now_utc=5.0)
    assert rec["topics_seeded"] == ["state", "border", "friction"]
    seeded = json.loads((tmp_path / "topics.json").read_text(encoding="utf-8"))
    assert seeded["topics"] == ["state", "border", "friction"] and seeded["ts"] == 5.0
    # journaled with the critique, constitution-scanned
    assert (tmp_path / "coach.jsonl").exists()


def test_coach_skips_when_no_transcript(monkeypatch, tmp_path):
    _mock(monkeypatch, dc)
    monkeypatch.setattr(dc, "TRANSCRIPT", tmp_path / "missing.log")
    rec = dc.coach_round(advisor="mock", now_utc=1.0)
    assert "skipped" in rec                       # observe nothing -> say nothing (no fabricated film)


def test_topic_parse_rejects_junk():
    assert dc._parse_topics("no topics line here") == []
    assert dc._parse_topics("TOPICS: ok topic, bad;one, x" ) == ["ok topic", "x"]


# ---------- chinese-room coach ----------

def test_context_demo_is_a_real_run():
    d = crc._demo_context_sensitivity()
    assert "kitchen" in d and "garden" in d            # live situation-organ outputs, not claims
    assert "did not change their rules" in d


def test_self_mechanism_demo_reads_real_docstrings():
    d = crc._demo_self_mechanism()
    assert "speech organ" in d and "situation organ" in d and "web organ" in d
    assert "silent by construction" in d               # the honesty floor is stated


def test_session_journals_and_never_writes_knowledge(monkeypatch, tmp_path):
    _mock(monkeypatch, crc)
    monkeypatch.setattr(crc, "LOG", tmp_path / "room.jsonl")
    rec = crc.run_session(rounds=2, advisor="mock", now_utc=9.0)
    assert rec["rounds"] == 2 and len(rec["exchanges"]) == 2
    # ATANOR's side rotates demonstrations + sincere questions; both present each round
    for e in rec["exchanges"]:
        assert e["atanor"]["demonstration"] and e["atanor"]["question"]
        assert e["coach"] == _CRITIQUE and e["intake_status"] == "advice_only"
    # nothing else was created: only the journal file (no graph/corpus writes from coaching)
    assert [p.name for p in tmp_path.iterdir()] == ["room.jsonl"]
