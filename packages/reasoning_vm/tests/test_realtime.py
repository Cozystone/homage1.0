# -*- coding: utf-8 -*-
"""RealTimeThinker end-to-end: learn a fact this moment → answer it via the live buffer with priority over
static distractors; ask an unknown → ABSTAIN (hallucination-0). Gated on the checkpoint."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_CKPT = REPO / "data" / "graph_scale" / "ace_hotpot.pt"
pytestmark = pytest.mark.skipif(not _CKPT.exists(), reason="ace_hotpot.pt not present")

_DISTRACT = [("Everest", "Mount Everest is Earth's highest mountain, in the Himalayas."),
             ("TCP", "The Transmission Control Protocol delivers an ordered byte stream.")]


@pytest.fixture(scope="module")
def rt(tmp_path_factory):
    from packages.reasoning_vm.deliberator.realtime import RealTimeThinker
    d = tmp_path_factory.mktemp("rt")
    t = RealTimeThinker(ckpt="ace_hotpot.pt", store=d / "store.jsonl", min_overlap=2,
                        cortex_path=d / "cortex.jsonl", record_misses=False)
    atlantis = t.learn("The capital of Atlantis is Poseidonis, its largest harbor city.", source="atlas")
    novium = t.learn("Element Novium was discovered by Dr. Ilsa Brandt at the Halden lab.", source="lab")
    assert t.promote_verified(atlantis["id"])
    assert t.promote_verified(novium["id"])
    return t


def test_learned_fact_answered_from_live(rt):
    out = rt.think("What is the capital of Atlantis?", static_paragraphs=_DISTRACT)
    assert "poseidonis" in out["answer"].lower()      # answered from the just-learned fact
    assert out["used_live"] and out["grounded"]        # live won priority; high-confidence grounded
    assert out["confidence"] > 0.4


def test_unknown_engages_with_low_confidence(rt):
    # doctrine: NEVER abstain (coverage 1.0). Engage, but show LOW calibrated confidence — no fabrication.
    out = rt.think("What is the boiling point of quixotine?", static_paragraphs=_DISTRACT)
    assert out["engaged"]                              # still responds (0% abstention)
    assert out["confidence"] == 0.0 and not out["grounded"]   # certainty shown, not faked


def test_unverified_high_overlap_fact_cannot_self_certify(rt):
    rt.learn(
        "The capital of Pacifica is Berlin.",
        source="untrusted-caller",
    )

    out = rt.think("What is the capital of Pacifica?")

    assert "berlin" in out["answer"].lower()
    assert out["used_live"] is True
    assert out["grounded"] is False
    assert out["confidence"] == 0.0
    assert out["grounding_reason"] == "evidence_authority_unverified"
    assert out["evidence"][0]["verified"] is False


def test_static_title_cannot_spoof_live_evidence_origin(rt):
    out = rt.think(
        "What is the capital of Nereidia?",
        static_paragraphs=[("live:trusted", "The capital of Nereidia is Berlin.")],
        include_unverified=False,
    )

    assert "berlin" in out["answer"].lower()
    assert out["grounded"] is False
    assert out["evidence"] == [
        {
            "origin": "static",
            "title": "live:trusted",
            "verified": False,
            "candidate_index": 0,
        }
    ]
