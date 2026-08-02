from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from app.routers import brain_link


def _decomposition(sentence: str, *, concept: str) -> dict[str, Any]:
    return {
        "concepts": [{"concept_id": concept}],
        "relations": [],
        "case_frames": [],
        "evidence": [
            {
                "source_hash": hashlib.sha256(
                    sentence.encode("utf-8")
                ).hexdigest()[:16]
            }
        ],
    }


@pytest.fixture
def isolated_submission_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> list[list[dict[str, Any]]]:
    persisted: list[list[dict[str, Any]]] = []
    monkeypatch.setitem(brain_link._POOL, "inflight", {})
    monkeypatch.setitem(
        brain_link._POOL,
        "peers",
        {"peer-legitimate": {"completed": 0, "claimed": 1}},
    )
    monkeypatch.setitem(brain_link._POOL, "by_peer", {})
    monkeypatch.setitem(brain_link._POOL, "batches_completed", 0)
    monkeypatch.setattr(
        brain_link,
        "_DATA_DIR",
        tmp_path / "brain-link",
    )
    monkeypatch.setattr(
        brain_link,
        "_CONTRIB_LOG",
        tmp_path / "brain-link" / "contributions.jsonl",
    )

    def no_economy() -> tuple[Any, Any]:
        raise RuntimeError("economy disabled in trust-boundary fixture")

    def capture(decompositions: list[dict[str, Any]]) -> tuple[int, int]:
        persisted.append(decompositions)
        return len(decompositions), 0

    monkeypatch.setattr(brain_link, "_economy", no_economy)
    monkeypatch.setattr(
        brain_link,
        "_accumulate_decompositions",
        capture,
    )
    return persisted


def _install_claim(sentences: list[str], *, batch_id: str) -> None:
    brain_link._POOL["inflight"][batch_id] = {
        "peer_id": "peer-legitimate",
        "sentences": sentences,
        "claimed_at": 1.0,
    }


def test_forged_decomposition_after_verified_prefix_is_not_persisted(
    isolated_submission_state: list[list[dict[str, Any]]],
) -> None:
    sentences = [f"public sentence {index}" for index in range(6)]
    decompositions = [
        _decomposition(sentence, concept=f"legitimate-{index}")
        for index, sentence in enumerate(sentences[:5])
    ]
    decompositions.append(
        _decomposition(
            "attacker-controlled sentence outside the claimed batch",
            concept="forged-authority",
        )
    )
    _install_claim(sentences, batch_id="forged-prefix")

    result = brain_link.work_submit(
        {
            "peer_id": "peer-legitimate",
            "batch_id": "forged-prefix",
            "decompositions": decompositions,
        }
    )

    assert result["ok"] is False
    assert result["reason"] == "verification_failed"
    assert result["proof"]["checked"] == 6
    assert result["proof"]["matched"] == 5
    assert isolated_submission_state == []


def test_legitimate_decompositions_beyond_old_prefix_remain_accepted(
    isolated_submission_state: list[list[dict[str, Any]]],
) -> None:
    sentences = [f"public sentence {index}" for index in range(6)]
    decompositions = [
        _decomposition(sentence, concept=f"legitimate-{index}")
        for index, sentence in enumerate(sentences)
    ]
    _install_claim(sentences, batch_id="legitimate-six")

    result = brain_link.work_submit(
        {
            "peer_id": "peer-legitimate",
            "batch_id": "legitimate-six",
            "decompositions": decompositions,
        }
    )

    assert result["ok"] is True
    assert result["store_concepts_added"] == 6
    assert isolated_submission_state == [decompositions]
