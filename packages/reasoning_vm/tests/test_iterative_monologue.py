# -*- coding: utf-8 -*-
"""answer_iterative produces an inspectable sub-query trail (the internal monologue) and an answer. This is
correct architecture for OPEN-corpus multi-hop; on closed HotpotQA-distractor it measured below parallel
top-2 (0.360 vs 0.400) — kept non-default, validated here for shape only. Gated on the checkpoint."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_CKPT = REPO / "data" / "graph_scale" / "ace_hotpot.pt"
pytestmark = pytest.mark.skipif(not _CKPT.exists(), reason="ace_hotpot.pt not present")


def test_monologue_trail_and_answer():
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    rd = MultiHopReader(ckpt="ace_hotpot.pt")
    paras = [("Inception", "Inception is a 2010 film directed by Christopher Nolan."),
             ("Christopher Nolan", "Christopher Nolan is a British-American film director."),
             ("Penguins", "Penguins are aquatic flightless birds of the Southern Hemisphere.")]
    out = rd.answer_iterative("Who directed Inception?", paras, max_hops=2)
    assert out["monologue"] and out["monologue"][0]["hop"] == 1        # a reasoning trail exists
    assert "subquery" in out["monologue"][0]                           # each hop records its forged query
    assert "answer" in out                                             # and it produces an answer
