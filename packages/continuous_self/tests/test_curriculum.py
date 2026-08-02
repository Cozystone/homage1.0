# -*- coding: utf-8 -*-
"""Endogenous curriculum — value-stack ranking from real signals only."""

from __future__ import annotations

import json

import packages.continuous_self.curriculum as cur


def test_no_failures_means_no_curriculum(monkeypatch):
    monkeypatch.setattr(cur, "_failure_terms", lambda limit=300: {})
    assert cur.build_curriculum() == []  # never invents topics


def test_value_stack_orders_user_relevant_gap_first(monkeypatch):
    monkeypatch.setattr(cur, "_failure_terms",
                        lambda limit=300: {"물병": 3, "양자역학": 3, "커피": 1})
    monkeypatch.setattr(cur, "_user_terms", lambda: {"물병", "커피"})
    monkeypatch.setattr(cur, "_self_question_terms", lambda: {"양자역학"})
    monkeypatch.setattr(cur, "_kg_has", lambda t: t == "커피")

    ranked = cur.build_curriculum()
    order = [r["term"] for r in ranked]



    assert order == ["물병", "양자역학", "커피"]
    top = ranked[0]
    assert top["evidence"]["failed_turns"] == 3
    assert top["evidence"]["user_model_hit"] is True


def test_enqueue_writes_ledger_and_queue(monkeypatch, tmp_path):
    monkeypatch.setattr(cur, "_failure_terms", lambda limit=300: {"위상공간": 2})
    monkeypatch.setattr(cur, "_user_terms", lambda: set())
    monkeypatch.setattr(cur, "_self_question_terms", lambda: set())
    monkeypatch.setattr(cur, "_kg_has", lambda t: False)
    monkeypatch.setattr(cur, "CURRICULUM_PATH", tmp_path / "curriculum.jsonl")

    pushed_terms: list[str] = []

    class _FakeQueue:
        @staticmethod
        def record_abstain(q):
            pushed_terms.append(q)
            return [q]

    import packages.graph_scale as gs
    monkeypatch.setattr(gs, "abstain_queue", _FakeQueue, raising=False)

    out = cur.enqueue_top(limit=2)
    assert out["ranked"] == 1
    assert pushed_terms == ["위상공간"]
    ledger = (tmp_path / "curriculum.jsonl").read_text(encoding="utf-8").strip()
    row = json.loads(ledger)
    assert row["ranked"][0]["term"] == "위상공간"
    assert row["pushed"] == ["위상공간"]
