from __future__ import annotations

"""Preregistered contract for the real-time verification authority boundary.

The public ``/api/realtime/learn`` ingress may add immediately recallable
episodic evidence, but it never owns the ``verified`` bit.  Verification is a
separate, server-owned promotion step.  Consequently:

1. ordinary public learning remains immediate and unverified;
2. caller-supplied verification metadata is rejected before storage and cannot
   cross sleep consolidation into the durable cortex;
3. the in-process promotion operation remains able to verify a stored item,
   after which the existing consolidation path may persist it.

These tests were added before the production fix and use only ``tmp_path``
stores; they must never touch the shipped graph or live memory files.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import realtime_think as realtime_router
from packages.reasoning_vm import consolidation
from packages.reasoning_vm.consolidation import MissLog
from packages.reasoning_vm.deliberator.realtime import RealTimeThinker
from packages.reasoning_vm.live_memory import LiveMemory


@pytest.fixture
def realtime_rig(tmp_path, monkeypatch):
    thinker = RealTimeThinker.__new__(RealTimeThinker)
    thinker.mem = LiveMemory(path=tmp_path / "hippocampus.jsonl")
    thinker.cortex = LiveMemory(path=tmp_path / "cortex.jsonl")
    thinker.misslog = MissLog(path=tmp_path / "misses.jsonl")
    monkeypatch.setattr(realtime_router, "_thinker", thinker)
    monkeypatch.setattr(realtime_router, "_load_error", None)
    monkeypatch.setattr(consolidation, "_BASE", tmp_path / "sleep")
    return TestClient(app), thinker


def test_public_learn_remains_immediate_and_unverified(realtime_rig) -> None:
    client, thinker = realtime_rig

    response = client.post(
        "/api/realtime/learn",
        json={"text": "The Orpheus relay uses a sapphire clock.", "source": "conversation"},
    )

    assert response.status_code == 200
    assert response.json()["verified"] is False
    hits = thinker.mem.recall("Orpheus sapphire clock", include_unverified=True)
    assert hits and hits[0]["verified"] is False


@pytest.mark.parametrize("forged_value", [True, "true", 1])
def test_forged_public_verified_flag_is_rejected_and_never_consolidates(
    realtime_rig, forged_value
) -> None:
    client, thinker = realtime_rig

    forged = client.post(
        "/api/realtime/learn",
        json={
            "text": "The Orpheus relay outputs 900 exawatts.",
            "source": "caller-assertion",
            "verified": forged_value,
        },
    )

    assert forged.status_code == 422
    assert thinker.mem.items == []
    slept = client.post("/api/realtime/sleep")
    assert slept.status_code == 200
    assert slept.json()["consolidated"]["promoted"] == 0
    assert thinker.cortex.items == []


def test_service_learn_has_no_verified_metadata_bypass(realtime_rig) -> None:
    _client, thinker = realtime_rig

    with pytest.raises(TypeError):
        thinker.learn(
            "The Orpheus relay outputs 900 exawatts.",
            source="direct-service-caller",
            verified=True,
        )
    with pytest.raises(TypeError):
        thinker.learn(
            "The Orpheus relay outputs 900 exawatts.",
            "direct-service-caller",
            True,
        )

    assert thinker.mem.items == []


def test_query_parameter_cannot_reintroduce_verification_authority(realtime_rig) -> None:
    client, thinker = realtime_rig

    response = client.post(
        "/api/realtime/learn?verified=true",
        json={"text": "The Orpheus relay uses a sapphire clock.", "source": "conversation"},
    )

    assert response.status_code == 200
    assert response.json()["verified"] is False
    slept = client.post("/api/realtime/sleep")
    assert slept.json()["consolidated"]["promoted"] == 0
    assert thinker.cortex.items == []


def test_server_owned_promotion_still_allows_verified_consolidation(realtime_rig) -> None:
    client, thinker = realtime_rig
    learned = client.post(
        "/api/realtime/learn",
        json={"text": "The Orpheus relay uses a sapphire clock.", "source": "conversation"},
    )
    item_id = learned.json()["id"]

    assert thinker.promote_verified(item_id) is True
    slept = client.post("/api/realtime/sleep")

    assert slept.status_code == 200
    assert slept.json()["consolidated"]["promoted"] == 1
    hits = thinker.cortex.recall("Orpheus sapphire clock", include_unverified=False)
    assert hits and hits[0]["verified"] is True
