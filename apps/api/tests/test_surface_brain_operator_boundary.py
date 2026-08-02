from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agentic_micro_os as agentic_router
from app.routers.surface_brain import router
from packages.agentic_micro_os.operator_confirm import (
    FULL_HOST_CONFIRMATION_PHRASE,
)
from packages.agentic_micro_os.permission_gate import (
    PermissionScope,
    gate_for_test,
)
from packages.surface_brain.review_queue import get_repair_candidate
from packages.surface_brain.rule_registry import (
    REGISTRY_PATH,
    disable_rule,
    load_production_rules,
)


DELEGATION_HEADER = "X-Atanor-Operator-Delegation"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _create_candidate(client: TestClient, *, run_id: str, feedback_id: str) -> str:
    created = client.post(
        "/api/surface-brain/feedback-to-repair-candidates",
        json={
            "run_id": run_id,
            "feedback_items": [
                {
                    "feedback_id": feedback_id,
                    "type": "trace_leakage",
                    "suggestion": "Move internal route details to trace.",
                    "flags": ["trace_leakage"],
                }
            ],
        },
    )
    assert created.status_code == 200
    return str(created.json()["candidate_ids"][0])


def _bound_operator(
    monkeypatch,
    tmp_path,
    *,
    operator_id: str = "bound_surface_owner",
):
    gate = gate_for_test(tmp_path / "operator-boundary")
    enabled = gate.enable_full_host(
        enabled_by=operator_id,
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches={"cloud_production_write": True},
    )
    assert enabled["allowed"] is True
    delegation = gate.issue_signed_delegation(
        [
            PermissionScope.REVIEW_DRAFT_WRITE,
            PermissionScope.CLOUD_PRODUCTION_WRITE,
        ],
        max_runtime_sec=600,
    )
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate)
    return gate, str(delegation["token_id"])


def test_bound_operator_can_approve_and_enable_without_trusting_reviewer(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _gate, token = _bound_operator(monkeypatch, tmp_path)
    client = _client()
    candidate_id = _create_candidate(
        client,
        run_id="bound-operator-positive",
        feedback_id="bound-feedback",
    )
    headers = {DELEGATION_HEADER: token}

    approved = client.post(
        f"/api/surface-brain/repair-candidates/{candidate_id}/approve",
        headers=headers,
        json={
            "reviewer": "forged_caller_reviewer",
            "comment": "reviewed through the bound operator session",
        },
    )

    assert approved.status_code == 200
    production_rule = approved.json()["production_rule"]
    assert production_rule["approved_by"] == "bound_surface_owner"
    assert (
        get_repair_candidate(candidate_id)["review"]["reviewer"]
        == "bound_surface_owner"
    )

    disable_rule(production_rule["rule_id"], actor="trusted_test_setup")
    enabled = client.post(
        f"/api/surface-brain/production-rules/{production_rule['rule_id']}/enable",
        headers=headers,
    )

    assert enabled.status_code == 200
    assert enabled.json()["production_rule"]["enabled"] is True


def test_forged_reviewer_and_unauthenticated_mutations_fail_closed(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _gate, token = _bound_operator(monkeypatch, tmp_path)
    client = _client()

    seed_id = _create_candidate(
        client,
        run_id="bound-operator-seed",
        feedback_id="seed-feedback",
    )
    seeded = client.post(
        f"/api/surface-brain/repair-candidates/{seed_id}/approve",
        headers={DELEGATION_HEADER: token},
        json={"reviewer": "ignored", "comment": "seed production rule"},
    )
    assert seeded.status_code == 200
    rule_id = str(seeded.json()["production_rule"]["rule_id"])
    disable_rule(rule_id, actor="trusted_test_setup")

    attack_id = _create_candidate(
        client,
        run_id="unauthenticated-attacks",
        feedback_id="attack-feedback",
    )
    candidate_before = get_repair_candidate(attack_id)
    registry_before = REGISTRY_PATH.read_bytes()

    edited = client.post(
        f"/api/surface-brain/repair-candidates/{attack_id}/edit",
        json={
            "patch": {
                "proposed_rule": {
                    "rule_id": rule_id,
                    "replacement": "attacker-controlled rewrite",
                }
            }
        },
    )
    approved = client.post(
        f"/api/surface-brain/repair-candidates/{attack_id}/approve",
        json={"reviewer": "local_operator", "comment": "forged reviewer string"},
    )
    enabled = client.post(
        f"/api/surface-brain/production-rules/{rule_id}/enable",
        headers={DELEGATION_HEADER: "delegation_forged"},
    )

    assert edited.status_code == 403
    assert approved.status_code == 403
    assert enabled.status_code == 403
    assert get_repair_candidate(attack_id) == candidate_before
    assert REGISTRY_PATH.read_bytes() == registry_before
    assert next(
        row for row in load_production_rules() if row["rule_id"] == rule_id
    )["enabled"] is False


def test_review_only_delegation_cannot_promote_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    gate = gate_for_test(tmp_path / "operator-boundary")
    assert gate.enable_full_host(
        enabled_by="scoped_surface_reviewer",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches={"cloud_production_write": True},
    )["allowed"] is True
    review_only = gate.issue_signed_delegation(
        [PermissionScope.REVIEW_DRAFT_WRITE],
        max_runtime_sec=600,
    )
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate)
    headers = {DELEGATION_HEADER: str(review_only["token_id"])}
    client = _client()
    candidate_id = _create_candidate(
        client,
        run_id="review-scope-only",
        feedback_id="review-scope-feedback",
    )

    edited = client.post(
        f"/api/surface-brain/repair-candidates/{candidate_id}/edit",
        headers=headers,
        json={"patch": {"reason": "reviewed but not promoted"}},
    )
    approved = client.post(
        f"/api/surface-brain/repair-candidates/{candidate_id}/approve",
        headers=headers,
        json={"reviewer": "scoped_surface_reviewer"},
    )

    assert edited.status_code == 200
    assert approved.status_code == 403
    assert get_repair_candidate(candidate_id)["status"] == "needs_edit"
    assert load_production_rules() == []
