from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cloud_broker_client import CloudBrokerConfig
from app.services.cloud_brain_providers import AwsBrokerProvider, CloudflareBrokerProvider, LocalBrokerProvider, provider_from_config
from app.services.contribution_service import ContributionValidationError, validate_contribution_task
from cost_model import CostInputs, CostModel, brain_balance_for_plan, cloud_budget_for_plan


client = TestClient(app)


def test_provider_config_parses_local_aws_and_cloudflare(monkeypatch) -> None:
    monkeypatch.setenv("ATANOR_CLOUD_PROVIDER", "cloudflare")
    monkeypatch.setenv("ATANOR_CLOUD_MODE", "remote")
    monkeypatch.setenv("ATANOR_CLOUD_ENDPOINT", "https://atanor.example.workers.dev")

    cf_config = CloudBrokerConfig.from_env()
    assert cf_config.cloud_provider == "cloudflare"
    assert isinstance(provider_from_config(cf_config), CloudflareBrokerProvider)

    monkeypatch.setenv("ATANOR_CLOUD_PROVIDER", "aws")
    monkeypatch.setenv("ATANOR_CLOUD_ENDPOINT", "https://example.execute-api.ap-northeast-2.amazonaws.com/dev")
    aws_config = CloudBrokerConfig.from_env()
    assert aws_config.cloud_provider == "aws"
    assert isinstance(provider_from_config(aws_config), AwsBrokerProvider)

    monkeypatch.setenv("ATANOR_CLOUD_MODE", "local_broker")
    local_config = CloudBrokerConfig.from_env()
    assert local_config.cloud_provider == "local"
    assert isinstance(provider_from_config(local_config), LocalBrokerProvider)


def test_plus_cloud_budget_depends_on_contribution() -> None:
    offline = cloud_budget_for_plan("plus", contribution_active=False)
    active = cloud_budget_for_plan("plus", contribution_active=True, contribution_score=0.8)

    assert offline["price_usd"] == 0.0
    assert active["price_usd"] == 0.0
    assert active["effective_fragment_requests_per_day"] > offline["effective_fragment_requests_per_day"]
    assert active["contributor_required"] is True


def test_brain_balance_respects_plan_and_provider_health() -> None:
    free = brain_balance_for_plan(
        "free",
        local_strength=0.0,
        cloud_coverage=1.0,
        seed_stability=0.2,
        working_memory_capacity=0.8,
        epistemic_confidence=0.8,
        provider_healthy=True,
    )
    down = brain_balance_for_plan(
        "director",
        local_strength=0.0,
        cloud_coverage=1.0,
        seed_stability=0.1,
        working_memory_capacity=1.0,
        epistemic_confidence=1.0,
        provider_healthy=False,
    )

    assert free["planned_balance"]["cloud"] <= 0.35
    assert free["cloud_budget"]["max_cloud_nodes_per_query"] == 32
    assert down["planned_balance"]["cloud"] == 0.0


def test_cost_model_computes_plus_zero_revenue_and_infra_margin_note() -> None:
    model = CostModel()
    economics = model.blended_unit_economics("base")

    assert economics["revenue_by_plan"]["plus"] == 0.0
    assert economics["blended_arpu"] > 0
    assert economics["blended_infra_cost"] > 0
    assert economics["company_net_margin"] is None
    assert "Infrastructure gross margin" in economics["margin_note"]


def test_cost_model_provider_estimate_runs() -> None:
    estimate = CostModel().estimate_usage(
        CostInputs(
            provider="cloudflare",
            api_requests=100_000,
            worker_invocations=100_000,
            db_reads=500_000,
            db_writes=50_000,
            object_storage_gb=1.0,
            object_gets=100_000,
            object_puts=10_000,
            queue_ops=20_000,
        )
    )

    assert estimate["provider"] == "cloudflare"
    assert estimate["estimated_cost_usd"] >= 0


def test_public_source_fetch_is_whitelisted_but_private_payloads_are_rejected() -> None:
    task = validate_contribution_task(
        {
            "task_id": "source-fetch-001",
            "task_type": "public_source_fetch",
            "schema_version": "atanor.contribution-task.v1",
            "payload": {"source_url": "https://example.com/public"},
            "max_runtime_ms": 1000,
            "max_memory_mb": 64,
            "max_output_bytes": 4096,
            "created_at": "2026-06-15T00:00:00Z",
            "expires_at": "2026-06-15T00:10:00Z",
            "trust_requirement": 0.0,
            "credit_estimate": 1.0,
            "privacy_classification": "public_only",
        }
    )
    assert task.task_type == "public_source_fetch"

    with pytest.raises(ContributionValidationError):
        validate_contribution_task(
            {
                "task_id": "bad-schema",
                "task_type": "public_source_fetch",
                "schema_version": "atanor.bad-task.v1",
                "payload": {"source_url": "https://example.com/public"},
                "max_runtime_ms": 1000,
                "max_memory_mb": 64,
                "max_output_bytes": 4096,
                "created_at": "2026-06-15T00:00:00Z",
                "expires_at": "2026-06-15T00:10:00Z",
                "trust_requirement": 0.0,
                "credit_estimate": 1.0,
                "privacy_classification": "public_only",
            }
        )


def test_neuro_cost_and_budget_endpoints() -> None:
    budget = client.get("/api/neuro/cloud-budget/plus")
    assert budget.status_code == 200
    assert budget.json()["price_usd"] == 0.0

    estimate = client.post("/api/neuro/cost-estimate", json={"provider": "cloudflare", "api_requests": 1000})
    assert estimate.status_code == 200
    assert estimate.json()["provider"] == "cloudflare"

    scenarios = client.get("/api/neuro/cost-scenarios")
    assert scenarios.status_code == 200
    assert scenarios.json()["base_unit_economics"]["company_net_margin"] is None


def test_atlas_endpoint_is_privacy_safe() -> None:
    response = client.get("/api/neuro/atlas")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "atanor.atlas.v1"
    assert payload["hub"]["label"] == "Seoul Hub"
    assert payload["privacy"]["raw_ip_stored"] is False
    assert payload["privacy"]["raw_ip_returned"] is False
    assert payload["privacy"]["exact_location_shown"] is False
    assert payload["privacy"]["private_data_shared"] is False
    assert payload["privacy"]["contributor_identifier_exposed"] is False
    assert payload["privacy"]["device_identifier_exposed"] is False

    encoded = str(payload).lower()
    assert "raw_ip" in encoded
    assert "node_id" not in encoded
    assert "device_name" not in encoded
    assert "device_label" not in encoded
    assert "payload_vault_shared" not in encoded
