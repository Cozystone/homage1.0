# -*- coding: utf-8 -*-
"""Flywheel: turn logging, failure mining signals (abstain / re-ask / correction)."""
from __future__ import annotations

import json

from packages.flywheel import logger


def test_mine_failures_signals(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "FLYWHEEL_DIR", tmp_path)
    monkeypatch.setattr(logger, "TURNS_PATH", tmp_path / "turns.jsonl")
    monkeypatch.setattr(logger, "FAILURES_PATH", tmp_path / "failures.jsonl")
    logger.log_turn("양자컴퓨터가 뭐야?", "지금 확인된 근거가 부족해서 단정하기 어렵습니다.",
                    answer_kind="", lane="")
    logger.log_turn("양자컴퓨터가 뭔데?", "…", answer_kind="definition")   # re-ask
    logger.log_turn("서울이란?", "서울은 도시입니다.", answer_kind="definition")
    logger.log_turn("아니 그게 아니라", "…", answer_kind="")               # correction
    c = logger.mine_failures()
    assert c["turns"] == 4
    assert c["abstain"] == 1
    assert c["re_ask"] >= 1
    assert c["correction"] == 1
    mined = [json.loads(l) for l in (tmp_path / "failures.jsonl").open(encoding="utf-8")]
    assert any(m["signal"] == "abstain" for m in mined)


def test_log_turn_never_raises(monkeypatch):
    monkeypatch.setattr(logger, "TURNS_PATH", None)  # force an internal error
    logger.log_turn("q", "a")  # must swallow
