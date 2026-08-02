from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.cloud_broker_client import CloudBrokerClient, CloudBrokerConfig
from app.services.contribution_service import default_contribution_service
from cost_model import CostInputs, CostModel, brain_balance_for_plan, cloud_budget_for_plan
from neuro_efficiency import build_hardware_benchmark, build_neuro_efficiency_plan, build_sustained_run_plan


router = APIRouter(prefix="/api/neuro", tags=["neuro-efficiency"])


def _coarse_ip_location() -> dict[str, Any]:
    """Return coarse public-IP geolocation without storing or returning raw IP."""

    fallback = {
        "region_label": "Local Node",
        "country_code": "XX",
        "approximate_lat": 37.6,
        "approximate_lng": 127.0,
        "provider": "fallback",
        "source": "fallback_seoul",
    }
    try:
        request = Request(
            "https://ipapi.co/json/",
            headers={"User-Agent": "ATANOR-Atlas/0.1 privacy-safe-coarse-geo"},
        )
        with urlopen(request, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        lat = round(float(payload.get("latitude")), 1)
        lng = round(float(payload.get("longitude")), 1)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return fallback
        city = str(payload.get("city") or "Local Region")
        region = str(payload.get("region") or "")
        country = str(payload.get("country_code") or "XX")
        return {
            "region_label": f"{city}{', ' + region if region else ''}",
            "country_code": country[:3],
            "approximate_lat": lat,
            "approximate_lng": lng,
            "provider": "ipapi_co",
            "source": "coarse_public_ip",
        }
    except Exception:
        return fallback


class NeuroPlanRequest(BaseModel):
    text: str | None = None
    task_type: str | None = None
    target_device: str | None = None
    token_budget: int | None = Field(default=None, ge=64, le=8192)
    module_budget: int | None = Field(default=None, ge=2, le=7)


class SustainedRunPlanRequest(BaseModel):
    hardware_profile: dict[str, Any] | None = None
    target_nodes: int | None = Field(default=None, ge=1_000, le=500_000)
    target_edges: int | None = Field(default=None, ge=2_000, le=3_000_000)
    duration_hours: int | None = Field(default=None, ge=1, le=720)


class HardwareBenchmarkRequest(BaseModel):
    hardware_profile: dict[str, Any] | None = None
    run_probes: bool = True


class CloudBudgetRequest(BaseModel):
    plan: str = Field(default="free")
    contribution_active: bool = False
    contribution_score: float = Field(default=0.0, ge=0.0, le=1.0)
    local_strength: float = Field(default=0.2, ge=0.0, le=1.0)
    cloud_coverage: float = Field(default=0.5, ge=0.0, le=1.0)
    seed_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    working_memory_capacity: float = Field(default=0.5, ge=0.0, le=1.0)
    epistemic_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    provider_healthy: bool = True
    remaining_budget_ratio: float = Field(default=1.0, ge=0.0, le=1.0)


class CostEstimateRequest(BaseModel):
    provider: str = Field(default="cloudflare")
    api_requests: int = Field(default=0, ge=0)
    worker_invocations: int = Field(default=0, ge=0)
    db_reads: int = Field(default=0, ge=0)
    db_writes: int = Field(default=0, ge=0)
    object_storage_gb: float = Field(default=0.0, ge=0.0)
    object_gets: int = Field(default=0, ge=0)
    object_puts: int = Field(default=0, ge=0)
    egress_gb: float = Field(default=0.0, ge=0.0)
    logs_gb: float = Field(default=0.0, ge=0.0)
    queue_ops: int = Field(default=0, ge=0)


@router.get("/plan")
def neuro_plan() -> dict[str, Any]:
    return build_neuro_efficiency_plan()


@router.post("/plan")
def neuro_plan_for_workload(payload: NeuroPlanRequest) -> dict[str, Any]:
    return build_neuro_efficiency_plan(payload.model_dump(exclude_none=True))


@router.get("/stability")
def sustained_run_plan() -> dict[str, Any]:
    return build_sustained_run_plan()


@router.post("/stability")
def sustained_run_plan_for_profile(payload: SustainedRunPlanRequest) -> dict[str, Any]:
    return build_sustained_run_plan(payload.model_dump(exclude_none=True))


@router.get("/benchmark")
def hardware_benchmark() -> dict[str, Any]:
    return build_hardware_benchmark()


@router.post("/benchmark")
def hardware_benchmark_for_profile(payload: HardwareBenchmarkRequest) -> dict[str, Any]:
    return build_hardware_benchmark(payload.model_dump(exclude_none=True))


@router.post("/cloud-budget")
def cloud_budget(payload: CloudBudgetRequest) -> dict[str, Any]:
    plan = payload.plan if payload.plan in {"free", "plus", "pro", "on_premise", "director"} else "free"
    return brain_balance_for_plan(
        plan,  # type: ignore[arg-type]
        local_strength=payload.local_strength,
        cloud_coverage=payload.cloud_coverage,
        seed_stability=payload.seed_stability,
        working_memory_capacity=payload.working_memory_capacity,
        epistemic_confidence=payload.epistemic_confidence,
        provider_healthy=payload.provider_healthy,
        contribution_active=payload.contribution_active,
        contribution_score=payload.contribution_score,
        remaining_budget_ratio=payload.remaining_budget_ratio,
    )


@router.get("/cloud-budget/{plan}")
def cloud_budget_for_named_plan(plan: str) -> dict[str, Any]:
    plan_id = plan if plan in {"free", "plus", "pro", "on_premise", "director"} else "free"
    return cloud_budget_for_plan(plan_id)  # type: ignore[arg-type]


@router.post("/cost-estimate")
def cost_estimate(payload: CostEstimateRequest) -> dict[str, Any]:
    provider = payload.provider if payload.provider in {"cloudflare", "aws", "hybrid"} else "cloudflare"
    inputs = CostInputs(provider=provider, **payload.model_dump(exclude={"provider"}))  # type: ignore[arg-type]
    return CostModel().estimate_usage(inputs)


@router.get("/cost-scenarios")
def cost_scenarios() -> dict[str, Any]:
    model = CostModel()
    return {
        "scenarios": model.plan_scenarios(),
        "base_unit_economics": model.blended_unit_economics("base"),
        "note": "Infrastructure gross margin is separate from company net margin.",
    }


@router.get("/atlas")
def atlas_status() -> dict[str, Any]:
    """Privacy-safe global contributor visualization state.

    Atlas intentionally returns only coarse anonymous regional display points.
    Raw IPs, device names, node IDs, local paths, and private memory state are
    not returned to the UI.
    """

    config = CloudBrokerConfig.from_env()
    contribution = default_contribution_service.get_status()
    broker_state = str(contribution.get("broker_state") or "local_broker_mode")
    remote_status: dict[str, Any] = {}
    if config.remote_enabled:
        try:
            remote_status = CloudBrokerClient(config).status()
            broker_state = str(remote_status.get("broker_state") or broker_state)
        except Exception:
            remote_status = {"broker_state": "remote_error"}
            broker_state = "remote_error"
    provider = config.cloud_provider if broker_state == "remote_connected" else "local"
    mode = "remote" if broker_state == "remote_connected" else "local_broker"

    cpu_limit = contribution.get("resource_limits", {}).get("cpu_limit_percent", 20)
    ram_limit = contribution.get("resource_limits", {}).get("ram_limit_gb", 2.0)
    contributor_state = str(contribution.get("contributor_state") or "local_only")
    pending_credits = float(contribution.get("pending_credits") or 0)
    confirmed_credits = float(contribution.get("confirmed_credits") or 0)
    completed_tasks = int(contribution.get("total_tasks_completed") or 0)
    current_task = contribution.get("current_task")

    active_local = contributor_state not in {"local_only", "contributor_disabled", "paused", "disabled", "error"}
    public_tasks_per_min = int(remote_status.get("queued_tasks") or (1 if current_task else 0))
    verified_remote_nodes = 0
    active_remote_peers = int(remote_status.get("active_peers") or 0)
    network_state = str(remote_status.get("network_state") or ("remote_broker_connected" if broker_state == "remote_connected" else "local_preview"))
    my_location = _coarse_ip_location()

    nodes: list[dict[str, Any]] = [
        {
            "display_id": "anon-region-seoul-hub",
            "region_label": "Seoul",
            "country_code": "KR",
            "approximate_lat": 37.56,
            "approximate_lng": 126.97,
            "jitter_seed": "seoul-hub",
            "state": "active" if broker_state == "remote_connected" or active_local else "idle",
            "activity_level": 0.86 if broker_state == "remote_connected" else 0.48,
            "last_seen_bucket": "now" if broker_state == "remote_connected" else "today",
            "source": "local",
            "role": "seoul_hub",
        },
        {
            "display_id": "anon-region-my-node",
            "region_label": "My Node",
            "country_code": my_location["country_code"],
            "approximate_lat": my_location["approximate_lat"],
            "approximate_lng": my_location["approximate_lng"],
            "jitter_seed": "my-node-local-private",
            "state": "active" if active_local or broker_state == "remote_connected" else "idle",
            "activity_level": 0.74 if active_local or broker_state == "remote_connected" else 0.44,
            "last_seen_bucket": "now",
            "source": "local",
            "role": "my_node",
        }
    ]

    preview_nodes = [
        ("anon-region-europe-preview", "Europe Relay", "EU", 50.1, 8.6, "preview-eu"),
        ("anon-region-north-america-preview", "North America Relay", "NA", 37.7, -122.4, "preview-na"),
        ("anon-region-pacific-preview", "Pacific Relay", "PA", -33.8, 151.2, "preview-pa"),
    ]
    if broker_state == "remote_connected":
        for display_id, label, country, lat, lng, seed in preview_nodes:
            nodes.append(
                {
                    "display_id": display_id,
                    "region_label": label,
                    "country_code": country,
                    "approximate_lat": lat,
                    "approximate_lng": lng,
                    "jitter_seed": seed,
                    "state": "syncing",
                    "activity_level": 0.28,
                    "last_seen_bucket": "today",
                    "source": "preview",
                }
            )

    return {
        "schema": "atanor.atlas.v1",
        "mode": mode,
        "provider": provider,
        "broker_state": broker_state,
        "hub": {
            "label": "Seoul Hub",
            "lat": 37.5665,
            "lng": 126.9780,
            "role": "Current visual origin hub; not a claim that all traffic physically routes through Seoul.",
        },
        "nodes": nodes,
        "stats": {
            "active_contributor_nodes": active_remote_peers if broker_state == "remote_connected" else (1 if active_local else 0),
            "verified_remote_contributor_nodes": verified_remote_nodes,
            "public_tasks_per_min": public_tasks_per_min,
            "fragments_verified_today": int(remote_status.get("verified_fragments") or completed_tasks),
            "submitted_fragments": int(remote_status.get("submitted_fragments") or 0),
            "queued_tasks": int(remote_status.get("queued_tasks") or 0),
            "pending_remote_credits": float(remote_status.get("pending_credits") or 0),
            "source_noise_rejected_today": int(contribution.get("total_tasks_rejected") or 0),
            "pending_credits": pending_credits,
            "confirmed_credits": confirmed_credits,
        },
        "my_node": {
            "state": "Active" if active_local else "Idle",
            "mode": "Remote Contributor" if broker_state == "remote_connected" else "Contributor Preview",
            "cpu_limit_percent": cpu_limit,
            "ram_limit_gb": ram_limit,
            "network_mode": "broker_metadata_only",
            "today_credit": pending_credits,
            "private_data": "Not Shared",
            "location_source": my_location["source"],
            "location_provider": my_location["provider"],
            "display_precision": "coarse_region_rounded_0.1deg",
        },
        "relay": {
            "active_region": "East Asia",
            "sequence": ["East Asia", "Europe", "North America", "Pacific"],
            "status": network_state,
            "real_remote_nodes_verified": verified_remote_nodes > 0,
        },
        "network_state": network_state,
        "remote_runtime": {
            "fragment_store": remote_status.get("fragment_store"),
            "active_peers": active_remote_peers,
            "queued_tasks": int(remote_status.get("queued_tasks") or 0),
            "submitted_fragments": int(remote_status.get("submitted_fragments") or 0),
            "verified_fragments": int(remote_status.get("verified_fragments") or 0),
            "r2_available": bool(remote_status.get("r2_available")),
            "kv_available": bool(remote_status.get("kv_available")),
        },
        "privacy": {
            "raw_ip_stored": False,
            "raw_ip_returned": False,
            "exact_location_shown": False,
            "private_data_shared": False,
            "contributor_identifier_exposed": False,
            "device_identifier_exposed": False,
            "ip_geo_provider": "none",
            "coarse_ip_geo_provider": my_location["provider"],
            "display_precision": "coarse_region_jittered",
        },
        "disclaimer": (
            "ATANOR Atlas is not a surveillance map. It is an anonymous regional visualization "
            "of Cloud Brain contribution signals."
        ),
    }
