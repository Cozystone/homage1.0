"""EAD-1 preregistered, model-free live wiring controls.

These tests bind the answer producer to the exact evidence row that the
independent discriminator receives.  Human-readable/caller-controlled titles
are presentation metadata, never row identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate
from packages.reasoning_vm.deliberator.realtime import RealTimeThinker


class _Memory:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def recall(self, _query, *, k, include_unverified):
        return list(self.rows[:k])


class _IndexedReader:
    def __init__(
        self,
        answer: str,
        *,
        support_titles: list[str],
        support_indices: list[int] | None,
        answer_index: int | None,
        answer_type: str = "span",
    ):
        self.answer_text = answer
        self.support_titles = support_titles
        self.support_indices = support_indices
        self.answer_index = answer_index
        self.answer_type = answer_type

    def answer(self, _question, _paragraphs, *, k, chain, rank):
        value = {
            "answer": self.answer_text,
            "support": list(self.support_titles),
            "type": self.answer_type,
        }
        if self.support_indices is not None:
            value["support_indices"] = list(self.support_indices)
        if self.answer_index is not None:
            value["answer_index"] = self.answer_index
        return value


@dataclass
class _Gate:
    accepted: bool = True
    confidence: float = 0.97
    calls: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)

    def judge_answer(self, question: str, answer: str, evidence: list[str]):
        self.calls.append((question, answer, tuple(evidence)))
        return {
            "accepted": self.accepted,
            "confidence": self.confidence,
            "reason": (
                "evidence_answer_supported"
                if self.accepted
                else "evidence_answer_not_supported"
            ),
            "signals": {"evidence_index": 0, "evidence_count": len(evidence)},
        }


def _manual_thinker(rows, reader, gate) -> RealTimeThinker:
    thinker = RealTimeThinker.__new__(RealTimeThinker)
    thinker.mem = _Memory(rows)
    thinker.cortex = _Memory([])
    thinker.misslog = None
    thinker.record_misses = False
    thinker.reader = reader
    thinker.gate = gate
    thinker.k = 3
    thinker.min_overlap = 2
    return thinker


def test_constructor_wires_distinct_readers_and_fixed_thresholds(
    tmp_path, monkeypatch
):
    from packages.reasoning_vm.deliberator import doubt_gate, planner

    constructed: list[str] = []

    class FakeReader:
        def __init__(self, ckpt):
            self.ckpt = ckpt
            constructed.append(ckpt)

    class FakeGate:
        def __init__(
            self,
            reader,
            *,
            threshold,
            support_reader,
            answerability_threshold,
            support_net_threshold,
        ):
            self.reader = reader
            self.support_reader = support_reader
            self.threshold = threshold
            self.answerability_threshold = answerability_threshold
            self.support_net_threshold = support_net_threshold

    monkeypatch.setattr(planner, "MultiHopReader", FakeReader)
    monkeypatch.setattr(doubt_gate, "DoubtGate", FakeGate)
    thinker = RealTimeThinker(
        store=tmp_path / "memory.jsonl",
        cortex_path=tmp_path / "cortex.jsonl",
        misslog=object(),
        record_misses=False,
    )

    assert constructed == ["ace_hotpot.pt", "ace_support.pt"]
    assert thinker.reader is not thinker.gate.support_reader
    assert thinker.gate.reader is thinker.reader
    assert thinker.gate.answerability_threshold == 0.90
    assert thinker.gate.support_net_threshold == 0.90


def test_constructor_does_not_reuse_answerability_reader_when_support_missing(
    tmp_path, monkeypatch
):
    from packages.reasoning_vm.deliberator import doubt_gate, planner, realtime

    class FakeReader:
        def __init__(self, ckpt):
            self.ckpt = ckpt

    observed = {}

    class FakeGate:
        def __init__(self, reader, **kwargs):
            observed["reader"] = reader
            observed.update(kwargs)

    monkeypatch.setattr(planner, "MultiHopReader", FakeReader)
    monkeypatch.setattr(doubt_gate, "DoubtGate", FakeGate)
    monkeypatch.setattr(realtime, "REPO", tmp_path)
    thinker = RealTimeThinker(
        store=tmp_path / "memory.jsonl",
        cortex_path=tmp_path / "cortex.jsonl",
        misslog=object(),
        record_misses=False,
    )

    assert thinker.reader.ckpt == "ace_hotpot.pt"
    assert observed["support_reader"] is None
    assert observed["reader"] is thinker.reader


def test_judge_uses_exact_claim_rows_and_inclusive_threshold_boundary():
    class Answerability:
        def __init__(self):
            self.calls = []

        def _relevance(self, question, evidence):
            self.calls.append((question, tuple(evidence)))
            return [0.90, 0.899]

    class Support:
        def __init__(self):
            self.calls = []

        def _support(self, claim, evidence):
            self.calls.append((claim, tuple(evidence)))
            return [[0.90, 0.10, 0.0], [0.90, 0.10, 0.0]]

    answerability, support = Answerability(), Support()
    gate = DoubtGate(answerability, support_reader=support)
    result = gate.judge_answer("Where is Selene?", "Lumen", ["row-a", "row-b"])

    assert result["accepted"] is True
    assert result["signals"]["evidence_index"] == 0
    assert answerability.calls == [("Where is Selene?", ("row-a", "row-b"))]
    assert support.calls == [("Where is Selene? Lumen", ("row-a", "row-b"))]


def test_production_reader_returns_answer_producer_index(monkeypatch):
    from packages.reasoning_vm.deliberator.planner import MultiHopReader

    reader = object.__new__(MultiHopReader)
    monkeypatch.setattr(
        reader,
        "_relevance",
        lambda _question, _texts: np.asarray([0.2, 0.9], dtype=np.float64),
    )
    monkeypatch.setattr(reader, "_is_polar", lambda _question: False)
    monkeypatch.setattr(
        reader,
        "_span",
        lambda _question, evidence: (
            ("Poseidonis", 3.0)
            if "Poseidonis" in evidence
            else ("Berlin", 1.0)
        ),
    )

    result = reader.answer(
        "What is the capital of Atlantis?",
        [
            ("duplicate", "The capital of Atlantis is Berlin."),
            ("duplicate", "The capital of Atlantis is Poseidonis."),
        ],
        k=2,
        chain=False,
        rank="ans",
    )

    assert result["support_indices"] == [1, 0]
    assert result["answer_index"] == 1
    assert result["support"] == ["duplicate", "duplicate"]


@pytest.mark.parametrize(
    ("support_indices", "answer_index"),
    [
        (None, None),
        ([4], 4),
        ([0], 1),
    ],
)
def test_unbound_or_invalid_reader_identity_fails_closed(
    support_indices, answer_index
):
    gate = _Gate()
    thinker = _manual_thinker(
        [
            {
                "text": "The capital of Atlantis is Poseidonis.",
                "source": "atlas",
                "verified": True,
            }
        ],
        _IndexedReader(
            "Poseidonis",
            support_titles=["atlas"],
            support_indices=support_indices,
            answer_index=answer_index,
        ),
        gate,
    )

    result = thinker.think("What is the capital of Atlantis?")

    assert result["grounded"] is False
    assert result["confidence"] == 0.0
    assert result["grounding_reason"] == "evidence_selection_unbound"
    assert gate.calls == []


def test_duplicate_titles_cannot_expand_the_answer_producer_row():
    gate = _Gate()
    thinker = _manual_thinker(
        [
            {
                "text": "The capital of Atlantis is Poseidonis.",
                "source": "duplicate",
                "verified": True,
            },
            {
                "text": "The capital of Atlantis is Berlin.",
                "source": "duplicate",
                "verified": True,
            },
        ],
        _IndexedReader(
            "Poseidonis",
            support_titles=["live:duplicate"],
            support_indices=[0],
            answer_index=0,
        ),
        gate,
    )

    result = thinker.think("What is the capital of Atlantis?")

    assert result["grounded"] is True
    assert gate.calls == [
        (
            "What is the capital of Atlantis?",
            "Poseidonis",
            ("The capital of Atlantis is Poseidonis.",),
        )
    ]
    assert result["evidence"] == [
        {
            "origin": "live",
            "title": "live:duplicate",
            "verified": True,
            "candidate_index": 0,
        }
    ]


def test_api_think_reaches_the_same_evidence_answer_boundary(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "apps" / "api"))
    from app.main import app
    from app.routers import realtime_think as realtime_router

    gate = _Gate(accepted=False, confidence=0.41)
    thinker = _manual_thinker(
        [
            {
                "text": "The capital of Atlantis is Poseidonis.",
                "source": "atlas",
                "verified": True,
            }
        ],
        _IndexedReader(
            "Poseidonis",
            support_titles=["live:atlas"],
            support_indices=[0],
            answer_index=0,
        ),
        gate,
    )
    monkeypatch.setattr(realtime_router, "_thinker", thinker)
    monkeypatch.setattr(realtime_router, "_load_error", None)

    response = TestClient(app).post(
        "/api/realtime/think",
        json={"question": "What is the capital of Atlantis?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["grounding_reason"] == "evidence_answer_not_supported"
    assert body["confidence"] == 0.41
    assert gate.calls == [
        (
            "What is the capital of Atlantis?",
            "Poseidonis",
            ("The capital of Atlantis is Poseidonis.",),
        )
    ]
