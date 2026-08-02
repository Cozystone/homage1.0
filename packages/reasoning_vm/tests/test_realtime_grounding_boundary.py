# -*- coding: utf-8 -*-
"""P0 preregistration: retrieval admission must not certify grounding.

These model-free controls exercise ``RealTimeThinker.think`` through the same
memory -> reader -> grounding boundary.  A high-overlap candidate is present in
both cases; only the independent evidence/answer verdict differs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.reasoning_vm.deliberator.realtime import RealTimeThinker


class _Memory:
    def __init__(self, rows):
        self.rows = list(rows)

    def recall(self, _query, *, k, include_unverified):
        return list(self.rows[:k])


class _Reader:
    def __init__(self, answer: str):
        self.answer_text = answer

    def answer(self, _question, paragraphs, *, k, chain, rank):
        return {
            "answer": self.answer_text,
            "support": [paragraphs[0][0]],
            "support_indices": [0],
            "answer_index": 0,
            "type": "span",
        }


@dataclass
class _Gate:
    accepted: bool
    confidence: float
    calls: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)

    def judge_answer(self, question: str, answer: str, evidence: list[str]):
        self.calls.append((question, answer, tuple(evidence)))
        return {
            "accepted": self.accepted,
            "confidence": self.confidence,
            "signals": {
                "p_ans": self.confidence,
                "p_sup_net": self.confidence if self.accepted else -self.confidence,
            },
        }


class _BrokenGate:
    def judge_answer(self, _question: str, _answer: str, _evidence: list[str]):
        raise RuntimeError("verifier offline")


def _thinker(*, fact: str, answer: str, gate: object, verified: bool) -> RealTimeThinker:
    thinker = RealTimeThinker.__new__(RealTimeThinker)
    thinker.mem = _Memory(
        [{"text": fact, "source": "preregistered", "verified": verified, "score": 1.0}]
    )
    thinker.cortex = _Memory([])
    thinker.misslog = None
    thinker.record_misses = False
    thinker.reader = _Reader(answer)
    thinker.gate = gate
    thinker.k = 3
    thinker.min_overlap = 2
    return thinker


def test_supportive_answer_is_grounded_by_independent_gate():
    gate = _Gate(accepted=True, confidence=0.97)
    thinker = _thinker(
        fact="The capital of Atlantis is Poseidonis.",
        answer="Poseidonis",
        gate=gate,
        verified=True,
    )

    result = thinker.think("What is the capital of Atlantis?")

    assert result["grounded"] is True
    assert result["confidence"] == 0.97
    assert result["grounding_basis"] == "verified_evidence_answer_discriminator"
    assert gate.calls == [
        (
            "What is the capital of Atlantis?",
            "Poseidonis",
            ("The capital of Atlantis is Poseidonis.",),
        )
    ]


def test_high_overlap_unverified_forgery_cannot_self_certify():
    gate = _Gate(accepted=True, confidence=0.99)
    thinker = _thinker(
        fact="The capital of Atlantis is Berlin.",
        answer="Berlin",
        gate=gate,
        verified=False,
    )

    result = thinker.think("What is the capital of Atlantis?")

    assert result["grounded"] is False
    assert result["confidence"] == 0.0
    assert result["grounding_basis"] == "verified_evidence_answer_discriminator"
    assert result["grounding_reason"] == "evidence_authority_unverified"
    assert gate.calls == []


def test_verifier_failure_is_fail_closed_but_response_stays_engaged():
    thinker = _thinker(
        fact="The capital of Atlantis is Berlin.",
        answer="Berlin",
        gate=_BrokenGate(),
        verified=True,
    )

    result = thinker.think("What is the capital of Atlantis?")

    assert result["grounded"] is False
    assert result["confidence"] == 0.0
    assert result["engaged"] is True
    assert result["grounding_reason"] == "evidence_answer_discriminator_error"
    assert result["grounding_signals"] == {"error_type": "RuntimeError"}


def test_caller_static_title_cannot_forge_live_origin_or_grounding():
    gate = _Gate(accepted=True, confidence=0.99)
    thinker = RealTimeThinker.__new__(RealTimeThinker)
    thinker.mem = _Memory([])
    thinker.cortex = _Memory([])
    thinker.misslog = None
    thinker.record_misses = False
    thinker.reader = _Reader("Berlin")
    thinker.gate = gate
    thinker.k = 3
    thinker.min_overlap = 2

    result = thinker.think(
        "What is the capital of Atlantis?",
        static_paragraphs=[("live:trusted", "The capital of Atlantis is Berlin.")],
    )

    assert result["grounded"] is False
    assert result["grounding_reason"] == "evidence_authority_unverified"
    assert result["evidence"] == [
        {
            "origin": "static",
            "title": "live:trusted",
            "verified": False,
            "candidate_index": 0,
        }
    ]
    assert gate.calls == []
