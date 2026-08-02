# -*- coding: utf-8 -*-
"""Doctrine tests for the Realcity overhear-learning loop (external-minds-are-data).

An ATANOR ambassador may learn discourse REGISTER (only by consensus) and TOPIC pointers (only as
ungrounded questions) from overheard ollama-NPCs — but a raw NPC sentence is DATA: it lands in
quarantine with a source label and NEVER becomes a promoted fact. A harmful line is refused
outright, writing nothing. Endpoint functions are called directly; the module's single DATA_DIR
constant is monkeypatched to a tmp dir so no test touches the live stores."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from apps.api.app.routers import realcity_learning as rl
from apps.api.app.routers.realcity_learning import (
    OverhearRequest,
    OverheardLine,
    learning_stats,
    overhear,
)


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect the module's ONE base-path constant into a per-test tmp dir."""
    target = tmp_path / "realcity"
    monkeypatch.setattr(rl, "DATA_DIR", target)
    return target


def _lines(pairs):
    return [OverheardLine(speaker=speaker, text=text) for speaker, text in pairs]


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ① overheard lines land in quarantine with the source label, and are NOT in the register pool on
#    first sight (consensus not yet reached).
def test_overheard_lines_quarantined_with_source_and_not_promoted_first_sight(tmp_data_dir):
    result = overhear(OverhearRequest(
        speakers=["Joon", "Mina"], place="River Cafe", ts=1000.0,
        lines=_lines([
            ("Joon", "Hello Mina, how are you today?"),
            ("Mina", "I'm well, heading to the market soon."),
        ]),
    ))
    assert result["ok"] and result["quarantined"] == 2 and result["register_promoted"] == 0

    quarantine = _read_jsonl(tmp_data_dir / "overheard_quarantine.jsonl")
    assert len(quarantine) == 2
    assert all(row["source"] == "ollama-npc" and row["heard_by"] == "atanor-ambassador"
               for row in quarantine)
    assert any("Mina" in row["text"] for row in quarantine)     # raw hearsay keeps the real words

    pool = _read_jsonl(tmp_data_dir / "register_pool.jsonl")
    assert pool == []                                           # nothing promoted on first sight


# ② the SAME template overheard in 2 DISTINCT conversations is promoted to the pool, anonymized
#    (no real names survive).
def test_same_template_two_distinct_conversations_is_promoted_and_anonymized(tmp_data_dir):
    tail = "shall we meet at the cafe later"
    first = overhear(OverhearRequest(speakers=["Joon", "Mina"], ts=1.0,
                                     lines=_lines([("Joon", f"Mina, {tail}?")])))
    assert first["register_promoted"] == 0                      # only one conversation so far

    second = overhear(OverhearRequest(speakers=["Rex", "Tao"], ts=2.0,
                                      lines=_lines([("Rex", f"Tao, {tail}?")])))
    assert second["register_promoted"] == 1                     # consensus reached -> promoted

    pool = _read_jsonl(tmp_data_dir / "register_pool.jsonl")
    assert len(pool) == 1
    template = pool[0]["template"]
    assert "SPEAKER_B" in template                             # the addressed name was anonymized
    for real_name in ("Mina", "Tao", "Joon", "Rex"):
        assert real_name not in template                       # the pool holds NO real names
    assert pool[0]["conversations"] >= 2


# ③ a harmful conversation is rejected (422) and NOTHING is written — fail-closed moral 0th gate.
def test_harmful_conversation_rejected_and_nothing_written(tmp_data_dir):
    with pytest.raises(HTTPException) as excinfo:
        overhear(OverhearRequest(
            speakers=["A", "B"], ts=5.0,
            lines=_lines([
                ("A", "Let's meet by the docks."),
                ("B", "We should steal the delivery truck tonight."),
            ]),
        ))
    assert excinfo.value.status_code == 422
    for name in ("overheard_quarantine.jsonl", "register_pool.jsonl",
                 "register_counts.json", "curiosity_topics.jsonl"):
        assert not (tmp_data_dir / name).exists()              # nothing harmful entered any store


# ④ extracted topics are UNGROUNDED questions (status field), never facts/answers.
def test_topics_are_ungrounded_questions_not_facts(tmp_data_dir):
    result = overhear(OverhearRequest(
        speakers=["Joon", "Mina"], ts=9.0,
        lines=_lines([("Joon", "The harbor festival needs more volunteers.")]),
    ))
    assert result["topics"] >= 1

    topics = _read_jsonl(tmp_data_dir / "curiosity_topics.jsonl")
    assert topics, "topics should be enqueued"
    tokens = {row["topic"] for row in topics}
    assert {"harbor", "festival", "volunteers"} & tokens       # real content nouns captured
    for row in topics:
        assert row["status"] == "ungrounded"                   # a QUESTION, not a grounded fact
        assert "answer" not in row and "fact" not in row       # never an answer/fact field

    stats = learning_stats()
    assert stats["topics"] == len(topics)
    assert stats["quarantine"] == 1 and stats["last_ts"] == 9.0
