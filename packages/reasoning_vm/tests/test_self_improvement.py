# -*- coding: utf-8 -*-
"""The Self-Improvement Orchestrator cycle: autonomously acquires a queued skill (bounded, verified),
classifies each module's wall into within-envelope vs ENVELOPE wall, and persists the capability ledger.
Proves the honest edge — it does the bounded fix, and flags (never fakes) the wall it can't cross."""
from __future__ import annotations

from packages.reasoning_vm import self_improvement as SI
from packages.reasoning_vm.deliberator import kernel_forge as KF


def test_cycle_acquires_skill_and_separates_envelope_from_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(SI, "DIR", tmp_path)
    monkeypatch.setattr(SI, "SKILL_QUEUE", tmp_path / "skills.jsonl")
    monkeypatch.setattr(SI, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "kreg.json")
    monkeypatch.setattr(SI, "diagnose_modules", lambda: [
        {"module": "gate", "verdict": "representation_wall", "current_acc": 0.66, "oracle_acc": 0.56,
         "goal_acc": 0.80, "note": "features overlap"},
        {"module": "ranker", "verdict": "training_wall", "current_acc": 0.50, "oracle_acc": 0.90,
         "goal_acc": 0.90, "note": "separable but under-realized"},
    ])
    # the reasoning circuit demands a computation it lacks
    ex = [[{"a": a, "b": b}, a - b] for a in range(1, 8) for b in range(5)]
    SI.request_skill("sub_ab", ex, ["a", "b"])

    rep = SI.run_once()

    # bounded fix ran autonomously: the skill was verified-acquired
    assert any(s["name"] == "sub_ab" and s["accepted"] for s in rep["skills_acquired"])
    assert "sub_ab" in rep["skill_library"]
    # the queue was drained
    assert SI._read_queue() == []
    # honest classification: representation wall = ENVELOPE (operator+architecture), training wall = bounded
    assert any(w["module"] == "gate" for w in rep["envelope_walls"])
    assert any(w["module"] == "ranker" for w in rep["within_envelope"])
    assert (tmp_path / "ledger.json").exists()
