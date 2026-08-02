from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import agentic_micro_os
from packages.agentic_micro_os.operator_confirm import (
    FULL_HOST_CONFIRMATION_PHRASE,
)
from packages.agentic_micro_os.permission_gate import (
    PermissionScope,
    gate_for_test,
)


def _client(tmp_path, monkeypatch) -> TestClient:
    agentic_micro_os.REVIEW_QUEUE.items.clear()
    agentic_micro_os.REVIEW_QUEUE.decisions.clear()
    monkeypatch.setattr(
        agentic_micro_os,
        "REVIEW_QUEUE_PATH",
        tmp_path / "review_queue.json",
    )
    app = FastAPI()
    app.include_router(agentic_micro_os.router)
    return TestClient(app)


def _seed_review_item(client: TestClient) -> str:
    response = client.post(
        "/api/agentic-os/review/import-web-run",
        json={
            "run_payload": {
                "run_id": "authority-boundary-run",
                "candidate_drafts": [
                    {
                        "draft_id": "authority-boundary-draft",
                        "title": "Bounded public candidate",
                        "summary": "A queue-only candidate for review.",
                        "source_url": "https://example.invalid/evidence",
                        "content_hash": "authority-boundary-content",
                        "confidence": 0.8,
                    }
                ],
                "skill_drafts": [],
                "sources": [],
                "trajectory": {},
            }
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["imported"] == 1
    return payload["items"][0]["item_id"]


def _bind_operator(
    tmp_path,
    monkeypatch,
    *,
    operator_id: str = "bound_review_owner",
) -> str:
    """Install a test-internal session; no live API issues this delegation."""

    gate = gate_for_test(tmp_path / "operator-boundary")
    enabled = gate.enable_full_host(
        enabled_by=operator_id,
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
    )
    assert enabled["allowed"] is True
    delegation = gate.issue_signed_delegation(
        [PermissionScope.REVIEW_DRAFT_WRITE],
        max_runtime_sec=600,
    )
    monkeypatch.setattr(agentic_micro_os, "PERMISSION_GATE", gate)
    return str(delegation["token_id"])


def test_forged_operator_claim_cannot_mint_review_approval(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    item_id = _seed_review_item(client)
    _bind_operator(tmp_path, monkeypatch)

    response = client.post(
        "/api/agentic-os/review/decide",
        json={
            "item_id": item_id,
            "decision": "approved",
            "reviewer": "root_operator",
            "reason": "caller says this is approved",
            "approved_for": "promotion_request",
        },
        headers={
            "X-Atanor-Operator-Delegation": "caller-forged-delegation",
        },
    )

    assert response.status_code == 403
    payload = response.json()["detail"]
    assert payload["required_boundary"] == "agentic_micro_os_permission_gate"
    assert payload["required_scope"] == "review_draft_write"
    assert "delegation is missing or invalid" in payload["reason"]
    assert agentic_micro_os.REVIEW_QUEUE.get(item_id).status == "pending"
    assert agentic_micro_os.REVIEW_QUEUE.decisions == []

    persisted = json.loads(
        (tmp_path / "review_queue.json").read_text(encoding="utf-8")
    )
    assert persisted["decisions"] == []
    assert "root_operator" not in json.dumps(persisted)
    assert "promotion_request" not in json.dumps(persisted)


def test_internal_bound_operator_primitive_overrides_caller_metadata_claims(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    item_id = _seed_review_item(client)
    token = _bind_operator(tmp_path, monkeypatch)

    response = client.post(
        "/api/agentic-os/review/decide",
        json={
            "item_id": item_id,
            "decision": "approved",
            "reviewer": "forged_root_operator",
            "reason": "reviewed within the bound session",
            "approved_for": "promotion_request",
        },
        headers={"X-Atanor-Operator-Delegation": token},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["review_authority_verified"] is True
    assert payload["review_authority_boundary"] == "agentic_micro_os_permission_gate"
    assert payload["decision"]["decision"] == "approved"
    assert payload["decision"]["reviewer"] == "bound_review_owner"
    assert payload["decision"]["approved_for"] == "draft_only"
    assert payload["item"]["status"] == "approved"
    assert payload["caller_reviewer_claim_authoritative"] is False
    assert payload["caller_approved_for_claim_authoritative"] is False
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False

    persisted = json.loads(
        (tmp_path / "review_queue.json").read_text(encoding="utf-8")
    )
    assert persisted["decisions"][0]["reviewer"] == "bound_review_owner"
    assert persisted["decisions"][0]["approved_for"] == "draft_only"
    assert "forged_root_operator" not in json.dumps(persisted)
    assert "promotion_request" not in json.dumps(persisted)


def test_live_full_host_route_cannot_issue_review_authority(
    tmp_path,
    monkeypatch,
) -> None:
    """The production HTTP surface is fail-closed, not a live accept proof."""

    gate = gate_for_test(tmp_path / "unbound-operator-boundary")
    monkeypatch.setattr(agentic_micro_os, "PERMISSION_GATE", gate)
    client = _client(tmp_path, monkeypatch)
    item_id = _seed_review_item(client)

    enable = client.post(
        "/api/agentic-os/permission/full-host/enable",
        json={
            "enabled_by": "live_operator",
            "typed_phrase": FULL_HOST_CONFIRMATION_PHRASE,
            "duration_sec": 600,
            "sub_switches": {"review_draft_write": True},
        },
    )

    assert enable.status_code == 200
    assert enable.json()["allowed"] is False
    assert enable.json()["reason"] == "signed_operator_run_lease_required"
    assert gate.session is None
    assert gate.signed_delegations == {}

    decide = client.post(
        "/api/agentic-os/review/decide",
        json={
            "item_id": item_id,
            "decision": "approved",
            "reviewer": "live_operator",
            "reason": "no live issuance path exists",
            "approved_for": "draft_only",
        },
        headers={"X-Atanor-Operator-Delegation": "unissued-token"},
    )

    assert decide.status_code == 403
    assert agentic_micro_os.REVIEW_QUEUE.get(item_id).status == "pending"
    assert agentic_micro_os.REVIEW_QUEUE.decisions == []
