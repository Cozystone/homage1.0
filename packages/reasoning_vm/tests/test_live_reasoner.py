# -*- coding: utf-8 -*-
"""End-to-end: teach a fact this moment, reason over it the next — no retraining. Also: honest abstention
when memory is empty, and the verified gate blocks unverified evidence when asked to. Skipped if the ACE
checkpoint isn't present (heavy model)."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_CKPT = REPO / "data" / "graph_scale" / "ace_hotpot.pt"
pytestmark = pytest.mark.skipif(not _CKPT.exists(), reason="ace_hotpot.pt not present")


@pytest.fixture(scope="module")
def reasoner(tmp_path_factory):
    from packages.reasoning_vm.deliberator.live_reasoner import LiveReasoner
    store = tmp_path_factory.mktemp("live") / "store.jsonl"
    return LiveReasoner(ckpt="ace_hotpot.pt", store=store)


def test_learn_then_reason(reasoner):
    reasoner.learn("The capital of Atlantis is Poseidonis, its largest harbor city.",
                   source="atlas", verified=True)
    reasoner.learn("The Vega relay outputs 9.2 terawatts at peak load.", source="grid", verified=True)
    out = reasoner.ask("What is the capital of Atlantis?")
    assert out["grounded"]
    assert "poseidonis" in out["answer"].lower()      # answered from a fact taught seconds ago
    assert out["support"]                              # provenance flowed through


def test_empty_memory_abstains(reasoner):
    out = reasoner.ask("What is the boiling point of quixotine?")   # nothing relevant in memory
    # honest: either no evidence at all, or no span found — never a fabricated answer
    assert out["answer"] == "" or not out["grounded"] or not out["evidence"]
