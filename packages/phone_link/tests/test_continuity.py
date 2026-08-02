# -*- coding: utf-8 -*-
"""Device continuity v0 — snapshot/adopt contract, handoff remembered."""

from __future__ import annotations

import importlib


def _mod(monkeypatch, tmp_path):
    cont = importlib.import_module("packages.phone_link.continuity")
    monkeypatch.setattr(cont, "SNAPSHOT_PATH", tmp_path / "snap.json")
    tl = importlib.import_module("packages.episodic_memory.timeline")
    monkeypatch.setattr(tl, "EVENTS_PATH", tmp_path / "events.jsonl")
    return cont, tl


def test_snapshot_then_adopt_records_handoff(monkeypatch, tmp_path):
    cont, tl = _mod(monkeypatch, tmp_path)
    snap = cont.make_snapshot("desktop")
    assert snap["token"] and snap["adopted_by"] is None

    out = cont.adopt_snapshot(snap["token"], "phone")
    assert out["adopted"] is True
    assert out["snapshot"]["adopted_by"] == "phone"
    # the handoff is itself an episodic event — continuity is remembered
    rows = tl.timeline("desktop→phone")
    assert rows and rows[0]["predicate"] == "세션이동"


def test_adopt_rejects_wrong_token_and_double_adopt(monkeypatch, tmp_path):
    cont, _ = _mod(monkeypatch, tmp_path)
    snap = cont.make_snapshot("desktop")
    assert cont.adopt_snapshot("bogus", "phone")["adopted"] is False
    assert cont.adopt_snapshot(snap["token"], "phone")["adopted"] is True
    again = cont.adopt_snapshot(snap["token"], "tablet")
    assert again["adopted"] is False and "already adopted" in again["reason"]


def test_read_without_snapshot_is_honest(monkeypatch, tmp_path):
    cont, _ = _mod(monkeypatch, tmp_path)
    assert cont.read_snapshot() is None
