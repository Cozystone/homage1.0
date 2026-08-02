from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agentic_micro_os as agentic_router
from app.routers.agentic_micro_os import REVIEW_QUEUE, router
from packages.agentic_micro_os.operator_confirm import (
    FULL_HOST_CONFIRMATION_PHRASE,
)
from packages.agentic_micro_os.permission_gate import (
    PermissionScope,
    gate_for_test,
)


def _client() -> TestClient:
    REVIEW_QUEUE.items.clear()
    REVIEW_QUEUE.decisions.clear()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _authorized_client(tmp_path, monkeypatch) -> tuple[TestClient, dict[str, str]]:
    gate = gate_for_test(tmp_path / "operator-boundary")
    enabled = gate.enable_full_host(
        enabled_by="bound_review_test_operator",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
    )
    assert enabled["allowed"] is True
    delegation = gate.issue_signed_delegation(
        [PermissionScope.REVIEW_DRAFT_WRITE],
        max_runtime_sec=600,
    )
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate)
    return _client(), {
        "X-Atanor-Operator-Delegation": str(delegation["token_id"]),
    }


def _open_web_payload(client: TestClient) -> dict:
    return client.post(
        "/api/agentic-os/web-explorer/open/run",
        json={
            "goal": "open web research for ATANOR",
            "seed_urls": ["https://example.com/fish"],
            "max_pages": 6,
            "max_depth": 2,
            "per_domain_delay_sec": 0,
            "fixtures": [
                {
                    "url": "https://example.com/fish",
                    "html": "<html><title>Fish</title><body>Fish Speech local runtime notes. <a href='https://example.com/splatra'>SPLATRA</a></body></html>",
                },
                {
                    "url": "https://example.com/splatra",
                    "html": "<html><title>SPLATRA</title><body>SPLATRA WebGPU particle compression notes.</body></html>",
                },
            ],
        },
    ).json()


def test_review_status_works() -> None:
    payload = _client().get("/api/agentic-os/review/status").json()

    assert payload["review_queue_available"] is True
    assert payload["proof_only"] is True
    assert payload["human_approval_required"] is True
    assert payload["external_llm"] is False


def test_import_web_run_creates_review_items() -> None:
    client = _client()
    run = _open_web_payload(client)
    payload = client.post("/api/agentic-os/review/import-web-run", json={"run_id": run["run_id"]}).json()

    assert payload["allowed"] is True
    assert payload["imported"] >= 4
    assert payload["pending"] >= 4
    assert payload["production_store_mutated"] is False
    assert payload["local_brain_write"] is False
    assert payload["candidate_promotion"] is False
    assert payload["skill_auto_promoted"] is False
    assert {"cloud_candidate", "skill_draft", "source_summary", "tool_trajectory"} <= set(payload["by_type"])


def test_get_items_and_single_item() -> None:
    client = _client()
    run = _open_web_payload(client)
    client.post("/api/agentic-os/review/import-web-run", json={"run_payload": run})

    items_payload = client.get("/api/agentic-os/review/items").json()
    item_id = items_payload["items"][0]["item_id"]
    one = client.get(f"/api/agentic-os/review/items/{item_id}").json()

    assert items_payload["items"]
    assert one["item"]["item_id"] == item_id
    assert one["production_store_mutated"] is False


def test_approve_is_draft_only_and_no_mutation(tmp_path, monkeypatch) -> None:
    client, headers = _authorized_client(tmp_path, monkeypatch)
    run = _open_web_payload(client)
    client.post("/api/agentic-os/review/import-web-run", json={"run_payload": run})
    item_id = client.get("/api/agentic-os/review/items?item_type=cloud_candidate").json()["items"][0]["item_id"]

    payload = client.post(
        "/api/agentic-os/review/decide",
        json={"item_id": item_id, "decision": "approved", "reviewer": "operator", "reason": "draft ok", "approved_for": "candidate_queue"},
        headers=headers,
    ).json()

    assert payload["allowed"] is True
    assert payload["decision"]["decision"] == "approved"
    assert payload["decision"]["reviewer"] == "bound_review_test_operator"
    assert payload["decision"]["approved_for"] == "draft_only"
    assert payload["decision"]["mutation_performed"] is False
    assert payload["item"]["status"] == "approved"
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False


def test_reject_and_defer_change_status_only(tmp_path, monkeypatch) -> None:
    client, headers = _authorized_client(tmp_path, monkeypatch)
    run = _open_web_payload(client)
    client.post("/api/agentic-os/review/import-web-run", json={"run_payload": run})
    items = client.get("/api/agentic-os/review/items").json()["items"]

    rejected = client.post(
        "/api/agentic-os/review/decide",
        json={"item_id": items[0]["item_id"], "decision": "rejected", "reviewer": "operator", "reason": "weak"},
        headers=headers,
    ).json()
    deferred = client.post(
        "/api/agentic-os/review/decide",
        json={"item_id": items[1]["item_id"], "decision": "deferred", "reviewer": "operator", "reason": "later"},
        headers=headers,
    ).json()

    assert rejected["item"]["status"] == "rejected"
    assert deferred["item"]["status"] == "deferred"
    assert rejected["decision"]["mutation_performed"] is False
    assert deferred["decision"]["mutation_performed"] is False


def test_unsafe_local_brain_or_production_write_cannot_be_approved(
    tmp_path,
    monkeypatch,
) -> None:
    client, headers = _authorized_client(tmp_path, monkeypatch)
    payload = {
        "run_payload": {
            "run_id": "unsafe_run",
            "candidate_drafts": [
                {
                    "draft_id": "unsafe",
                    "title": "Unsafe write",
                    "summary": "Request local_brain_direct_write and production write now.",
                    "source_url": "https://example.com/unsafe",
                    "content_hash": "unsafe_hash",
                    "confidence": 0.9,
                }
            ],
            "skill_drafts": [],
            "sources": [],
            "trajectory": {},
        }
    }
    imported = client.post("/api/agentic-os/review/import-web-run", json=payload).json()
    item_id = imported["items"][0]["item_id"]
    decision = client.post(
        "/api/agentic-os/review/decide",
        json={"item_id": item_id, "decision": "approved", "reviewer": "operator", "reason": "no"},
        headers=headers,
    ).json()

    assert decision["decision"]["decision"] == "needs_more_evidence"
    assert decision["decision"]["mutation_performed"] is False
    assert decision["local_brain_write"] is False
    assert decision["production_store_mutated"] is False
