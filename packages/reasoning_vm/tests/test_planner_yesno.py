# -*- coding: utf-8 -*-
"""Polar (yes/no) routing in the multi-hop reader: wh-questions go to the span head, polar questions to
the support judge. The detector is a pure function (fast); the end-to-end yes/no answer needs the model
(skipped if the checkpoint is absent)."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_CKPT = REPO / "data" / "graph_scale" / "ace_support.pt"


def _detector():
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    return object.__new__(MultiHopReader)          # no __init__ → no model load


def test_polar_detection():
    rd = _detector()
    assert rd._is_polar("Are both films directed by the same person?")
    assert rd._is_polar("Is Poseidonis a harbor city?")
    assert rd._is_polar("Was the treaty signed before 1900?")
    assert rd._is_polar("Does the engine use muon plasma?")
    # wh-questions are span, not polar
    assert not rd._is_polar("Who directed the film?")
    assert not rd._is_polar("What year was it founded?")
    assert not rd._is_polar("Where is the lab located?")
    assert not rd._is_polar("Which city is the capital?")   # 'which' excluded (usually a span pick)


@pytest.mark.skipif(not _CKPT.exists(), reason="ace_support.pt not present")
def test_yesno_answer_shape():
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    rd = MultiHopReader(ckpt="ace_support.pt")
    paras = [("Eiffel", "The Eiffel Tower is a wrought-iron tower in Paris, France."),
             ("Paris", "Paris is the capital and most populous city of France.")]
    out = rd.answer("Is the Eiffel Tower located in Paris?", paras, k=2, chain=False, rank="ans")
    assert out.get("type") == "yesno"
    assert out["answer"] in ("yes", "no")               # judged, not a span echo
    assert out["support"]                                # provenance still flows
