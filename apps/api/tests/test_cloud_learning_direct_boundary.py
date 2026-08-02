from __future__ import annotations

"""Preregistered contract for direct Cloud Learning ingress.

The public ``learning/tick`` and ``learning/run-once`` routes are candidate-only
ingress.  A caller may propose evidence, but cannot select the destination or
grant production-promotion authority.  Every direct payload must cross the same
``PayloadSourcePolicy`` used by file-backed ingestion before any store opens.

Accordingly these tests freeze four properties before the production patch:

1. a normal caller may trigger server-owned approved-source ingestion but may
   not turn policy-shaped request data into an approved source observation;
2. caller-supplied safety/source metadata cannot bypass source policy;
3. ``candidate_store_root`` and ``promote_to_verified`` are rejected before any
   caller-selected or verified-like store is mutated; and
4. the underlying learning service itself rejects production-promotion mode.

All stores in this suite are ``tmp_path`` fixtures.  It must never write shipped
graph data or live candidate/verified stores.
"""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from packages.cloud_brain.continuous_learning import (
    DEFAULT_VERIFIED_STORE,
    CloudSurfaceLearningLoop,
    ensure_candidate_store_initialized,
)
from packages.cloud_brain.verified_payload_feeder import PayloadSourcePolicy, VerifiedPayloadFeeder


client = TestClient(app)


def _valid_payload(*, source_id: str = "manual:direct-boundary:valid") -> dict[str, object]:
    text = "Kubernetes manages containerized applications across distributed clusters."
    return {
        "source_type": "manual_public_sentence",
        "source_id": source_id,
        "text": text,
        "language": "en",
        "provenance_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_url_or_path": "manual://public/direct-boundary/valid",
        "license_hint": "CC BY-SA 4.0",
        "target_store": "verified_store_v0_candidate",
    }


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_direct_api_rejects_policy_shaped_caller_payload_before_store_write(tmp_path, monkeypatch) -> None:
    canonical = tmp_path / "canonical_candidate"
    canonical.mkdir()
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(canonical))

    response = client.post(
        "/api/cloud-brain/learning/run-once",
        json={"payloads": [_valid_payload()]},
    )

    assert response.status_code == 400
    assert "independently bound source observation" in response.json()["detail"]
    assert _snapshot(canonical) == {}


def test_direct_api_can_trigger_server_owned_feeder_without_caller_payload(tmp_path, monkeypatch) -> None:
    canonical = tmp_path / "canonical_candidate"
    canonical.mkdir()
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(canonical))

    response = client.post(
        "/api/cloud-brain/learning/run-once",
        json={"dry_run": True},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["production_store_mutated"] is False
    assert _snapshot(canonical) == {}


def test_direct_api_reapplies_source_policy_to_caller_metadata(tmp_path, monkeypatch) -> None:
    canonical = tmp_path / "canonical_candidate"
    canonical.mkdir()
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(canonical))

    private = {**_valid_payload(source_id="manual:direct-boundary:private"), "is_private": True}
    generated = {**_valid_payload(source_id="manual:direct-boundary:generated"), "is_generated": True}
    eval_row = {**_valid_payload(source_id="manual:direct-boundary:eval"), "is_eval_row": True}
    mock = {**_valid_payload(source_id="manual:direct-boundary:mock"), "is_mock": True}
    quality_rejected = {
        **_valid_payload(source_id="manual:direct-boundary:quality"),
        "quality_flags": ["quality_rejected"],
    }
    production_target = {
        **_valid_payload(source_id="manual:direct-boundary:production"),
        "target_store": "verified_store_v0",
    }
    unsupported_source = {
        **_valid_payload(source_id="caller:direct-boundary:forged-source"),
        "source_type": "caller_asserted_verified",
    }

    response = client.post(
        "/api/cloud-brain/learning/run-once",
        json={
            "payloads": [
                private,
                generated,
                eval_row,
                mock,
                quality_rejected,
                production_target,
                unsupported_source,
            ]
        },
    )

    assert response.status_code == 400
    assert "independently bound source observation" in response.json()["detail"]
    assert _snapshot(canonical) == {}


def test_direct_api_rejects_caller_selected_store_before_write(tmp_path, monkeypatch) -> None:
    canonical = tmp_path / "canonical_candidate"
    canonical.mkdir()
    attacker_root = tmp_path / "caller_selected_store"
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(canonical))

    response = client.post(
        "/api/cloud-brain/learning/run-once",
        json={
            "candidate_store_root": str(attacker_root),
            "payloads": [_valid_payload()],
        },
    )

    assert response.status_code == 400
    assert not attacker_root.exists()
    assert _snapshot(canonical) == {}


def test_direct_api_rejects_promotion_before_verified_like_store_write(tmp_path, monkeypatch) -> None:
    verified_like = tmp_path / "verified_like_store"
    ensure_candidate_store_initialized(verified_like)
    before = _snapshot(verified_like)

    response = client.post(
        "/api/cloud-brain/learning/run-once",
        json={
            "promote_to_verified": True,
            "candidate_store_root": str(verified_like),
            "payloads": [_valid_payload()],
        },
    )

    assert response.status_code == 400
    assert _snapshot(verified_like) == before


def test_learning_service_rejects_production_promotion_configuration(tmp_path) -> None:
    with pytest.raises(ValueError, match="candidate-only"):
        CloudSurfaceLearningLoop(
            candidate_store_root=tmp_path / "verified_like_store",
            promote_to_verified=True,
        )


def test_learning_service_rejects_production_target_policy(tmp_path) -> None:
    production_policy = PayloadSourcePolicy(target_store="verified_store_v0")
    with pytest.raises(ValueError, match="candidate-only source policy"):
        CloudSurfaceLearningLoop(
            feeder=VerifiedPayloadFeeder(policy=production_policy),
            candidate_store_root=tmp_path / "verified_like_store",
        )


def test_learning_service_rejects_shipped_verified_store_destination() -> None:
    with pytest.raises(ValueError, match="verified production store"):
        CloudSurfaceLearningLoop(candidate_store_root=DEFAULT_VERIFIED_STORE)


def test_capped_api_rejects_caller_destination_before_write(tmp_path, monkeypatch) -> None:
    canonical = tmp_path / "canonical_candidate"
    canonical.mkdir()
    attacker_root = tmp_path / "caller_selected_store"
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(canonical))

    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": True,
            "dry_run": False,
            "target_candidate_store": str(attacker_root),
        },
    )

    assert response.status_code == 400
    assert not attacker_root.exists()
    assert _snapshot(canonical) == {}


def test_capped_api_rejects_policy_shaped_caller_payload_before_write(tmp_path, monkeypatch) -> None:
    canonical = tmp_path / "canonical_candidate"
    canonical.mkdir()
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(canonical))

    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": True,
            "dry_run": False,
            "payloads": [_valid_payload()],
        },
    )

    assert response.status_code == 400
    assert "independently bound source observation" in response.json()["detail"]
    assert _snapshot(canonical) == {}
