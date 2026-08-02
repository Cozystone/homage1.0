# -*- coding: utf-8 -*-
"""DoubtGate: the learned combiner separates a linearly-separable toy (fast, no model); and end-to-end the
gate produces a bounded confidence and answers a clearly-answerable case (gated on the checkpoint)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_CKPT = REPO / "data" / "graph_scale" / "ace_squad.pt"


def test_logistic_combiner_learns():
    from packages.reasoning_vm.deliberator.doubt_gate import _Logistic
    rng = np.random.default_rng(0)
    pos = rng.normal(1.0, 0.3, (200, 3))
    neg = rng.normal(-1.0, 0.3, (200, 3))
    X = np.vstack([pos, neg]); y = np.array([1] * 200 + [0] * 200)
    lr = _Logistic().fit(X, y)
    assert lr.prob(pos).mean() > 0.7 > lr.prob(neg).mean()      # separates the two clouds


def test_features_order_stable():
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate
    f = DoubtGate.features({"p_ans": 0.9, "peak": 0.01, "p_sup_net": 0.4})
    assert len(f) == 3 and f[0] == 0.9                          # p_ans first, always


class _AnswerabilityReader:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.float64)

    def _relevance(self, _question, evidence):
        assert len(evidence) == len(self.values)
        return self.values


class _SupportReader:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.float64)

    def _support(self, _claim, evidence):
        assert len(evidence) == len(self.values)
        return self.values


def test_answer_judge_requires_both_signals_on_same_evidence():
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate

    gate = DoubtGate(
        _AnswerabilityReader([0.99, 0.10]),
        support_reader=_SupportReader(
            [
                [0.20, 0.75, 0.05],  # answerable row, but not supporting
                [0.99, 0.005, 0.005],  # support-like row, but not answerable
            ]
        ),
    )

    result = gate.judge_answer("Where is Atlantis?", "Berlin", ["row one", "row two"])

    assert result["accepted"] is False
    assert result["reason"] == "evidence_answer_not_supported"


def test_answer_judge_accepts_joint_answerability_and_support():
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate

    gate = DoubtGate(
        _AnswerabilityReader([0.98]),
        support_reader=_SupportReader([[0.97, 0.02, 0.01]]),
    )

    result = gate.judge_answer(
        "What is the capital of Atlantis?",
        "Poseidonis",
        ["The capital of Atlantis is Poseidonis."],
    )

    assert result["accepted"] is True
    assert result["confidence"] >= 0.90


def test_answer_judge_fails_closed_without_independent_support_reader():
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate

    gate = DoubtGate(_AnswerabilityReader([0.99]))

    result = gate.judge_answer(
        "What is the capital of Atlantis?",
        "Berlin",
        ["The capital of Atlantis is Berlin."],
    )

    assert result["accepted"] is False
    assert result["confidence"] == 0.0
    assert result["reason"] == "support_reader_unavailable"


def test_answer_judge_rejects_non_probability_signals():
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate

    gate = DoubtGate(
        _AnswerabilityReader([1.2]),
        support_reader=_SupportReader([[0.97, 0.02, 0.01]]),
    )

    with pytest.raises(ValueError, match="invalid evidence-answer"):
        gate.judge_answer(
            "What is the capital of Atlantis?",
            "Berlin",
            ["The capital of Atlantis is Berlin."],
        )


@pytest.mark.skipif(not _CKPT.exists(), reason="ace_squad.pt not present")
def test_gate_confidence_and_answer():
    from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    gate = DoubtGate(MultiHopReader(ckpt="ace_squad.pt"), threshold=0.3)
    ev = "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France."
    out = gate.decide("Where is the Eiffel Tower?", ev)
    assert 0.0 <= out["confidence"] <= 1.0
    assert not out["abstain"] and out["answer"]                 # clearly answerable → not abstained


_CKPT2 = REPO / "data" / "graph_scale" / "ace2_squad.pt"


@pytest.mark.skipif(not _CKPT2.exists(), reason="ace2_squad.pt not present (Phase C not run/won yet)")
def test_multihop_reader_ace2_lane_constructs():
    """E9 Phase D readiness: an ace2_* ckpt routes through the BPE/model2 branch and answers the
    same reader API. Activates automatically once Phase C produces the checkpoint."""
    rd = MultiHopReader(ckpt="ace2_squad.pt")
    span, score = rd._span("What is water made of?", "Water is made of hydrogen and oxygen.")
    assert isinstance(span, str) and isinstance(score, float)
