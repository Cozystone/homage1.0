from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


Provider = Literal["cloudflare", "aws", "hybrid"]
Plan = Literal["free", "plus", "pro", "on_premise", "director"]

REVENUE_BY_PLAN: dict[Plan, float] = {
    "free": 0.0,
    "plus": 0.0,
    "pro": 49.0,
    "on_premise": 99.0,
    "director": 199.0,
}


@dataclass(frozen=True)
class PlanPolicy:
    plan: Plan
    price_usd: float
    cloud_fragment_requests_per_day: int
    max_cloud_nodes_per_query: int
    max_cloud_edges_per_query: int
    max_cloud_bytes_per_query: int
    deep_cloud_search_per_day: int
    freshness_tier: str
    cloud_pack_access_level: str
    background_farming_enabled: bool
    contributor_required: bool
    contributor_multiplier: float
    cache_size_limit_mb: int
    snapshot_limit: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PLAN_POLICIES: dict[Plan, PlanPolicy] = {
    "free": PlanPolicy("free", 0.0, 24, 32, 96, 128 * 1024, 0, "standard_low", "hot_fragments_low_res", False, False, 1.0, 16, 0),
    "plus": PlanPolicy("plus", 0.0, 96, 128, 384, 512 * 1024, 4, "standard", "compute_backed_hot_fragments", False, True, 2.5, 64, 1),
    "pro": PlanPolicy("pro", 49.0, 480, 512, 1536, 2 * 1024 * 1024, 32, "high", "background_farming", True, False, 1.5, 512, 14),
    "on_premise": PlanPolicy("on_premise", 99.0, 240, 1024, 4096, 4 * 1024 * 1024, 24, "high_local_cache", "local_hot_shard_snapshot", False, False, 1.0, 4096, 30),
    "director": PlanPolicy("director", 199.0, 2000, 2048, 8192, 8 * 1024 * 1024, 128, "highest", "dedicated_namespace", True, False, 1.0, 8192, 90),
}


@dataclass(frozen=True)
class CostInputs:
    provider: Provider = "cloudflare"
    api_requests: int = 0
    worker_invocations: int = 0
    db_reads: int = 0
    db_writes: int = 0
    object_storage_gb: float = 0.0
    object_gets: int = 0
    object_puts: int = 0
    egress_gb: float = 0.0
    logs_gb: float = 0.0
    queue_ops: int = 0
    contributor_tasks: int = 0
    hot_fragment_hits: int = 0
    cold_fragment_fetches: int = 0


def load_pricing_defaults(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else Path(__file__).resolve().parents[1] / "pricing_defaults.json"
    return json.loads(target.read_text(encoding="utf-8"))


class CostModel:
    """Configurable infrastructure cost estimator.

    The constants are not treated as guaranteed provider pricing. They are
    editable assumptions that must be checked against current provider bills.
    """

    def __init__(self, pricing: dict[str, Any] | None = None) -> None:
        self.pricing = pricing or load_pricing_defaults()

    def estimate_usage(self, inputs: CostInputs) -> dict[str, Any]:
        key = inputs.provider
        if key == "hybrid":
            cf = self._estimate_provider("cloudflare", inputs)
            aws = self._estimate_provider("aws", inputs)
            total = cf["estimated_cost_usd"] * 0.75 + aws["estimated_cost_usd"] * 0.25
            return {"provider": "hybrid", "estimated_cost_usd": round(total, 4), "components": {"cloudflare": cf, "aws": aws}}
        return self._estimate_provider(key, inputs)

    def _estimate_provider(self, provider: str, inputs: CostInputs) -> dict[str, Any]:
        prices = self.pricing[provider]
        components = {
            "api_requests": inputs.api_requests * prices.get("api_request_per_million", 0.0) / 1_000_000,
            "worker_invocations": inputs.worker_invocations * prices.get("worker_invocation_per_million", 0.0) / 1_000_000,
            "db_reads": inputs.db_reads * prices.get("db_read_per_million", 0.0) / 1_000_000,
            "db_writes": inputs.db_writes * prices.get("db_write_per_million", 0.0) / 1_000_000,
            "object_storage": inputs.object_storage_gb * prices.get("object_storage_gb_month", 0.0),
            "object_gets": inputs.object_gets * prices.get("object_get_per_million", 0.0) / 1_000_000,
            "object_puts": inputs.object_puts * prices.get("object_put_per_million", 0.0) / 1_000_000,
            "egress": inputs.egress_gb * prices.get("egress_gb", 0.0),
            "logs": inputs.logs_gb * prices.get("logs_gb", 0.0),
            "queue_ops": inputs.queue_ops * prices.get("queue_op_per_million", 0.0) / 1_000_000,
        }
        total = sum(components.values())
        return {"provider": provider, "estimated_cost_usd": round(total, 4), "components": {key: round(value, 4) for key, value in components.items()}}

    def plan_scenarios(self) -> dict[str, dict[str, float]]:
        return dict(self.pricing["plan_scenarios"])

    def blended_unit_economics(
        self,
        scenario: Literal["optimistic", "base", "risk"] = "base",
        distribution: dict[Plan, float] | None = None,
    ) -> dict[str, Any]:
        distribution = distribution or {"free": 0.40, "plus": 0.45, "pro": 0.10, "on_premise": 0.04, "director": 0.01}
        scenario_costs = self.plan_scenarios()[scenario]
        blended_arpu = sum(REVENUE_BY_PLAN[plan] * distribution.get(plan, 0.0) for plan in REVENUE_BY_PLAN)
        blended_infra_cost = sum(float(scenario_costs[plan]) * distribution.get(plan, 0.0) for plan in REVENUE_BY_PLAN)
        infra_gross_margin = 0.0 if blended_arpu <= 0 else (blended_arpu - blended_infra_cost) / blended_arpu
        return {
            "scenario": scenario,
            "distribution": distribution,
            "revenue_by_plan": REVENUE_BY_PLAN,
            "infra_cost_by_plan": scenario_costs,
            "blended_arpu": round(blended_arpu, 4),
            "blended_infra_cost": round(blended_infra_cost, 4),
            "infra_gross_margin": round(infra_gross_margin, 4),
            "company_net_margin": None,
            "margin_note": "Infrastructure gross margin is not company net margin.",
        }


def cloud_budget_for_plan(plan: Plan, *, contribution_active: bool = False, contribution_score: float = 0.0) -> dict[str, Any]:
    policy = PLAN_POLICIES[plan]
    multiplier = 1.0
    if plan == "plus":
        multiplier = policy.contributor_multiplier if contribution_active else 0.35
        multiplier += max(0.0, min(1.0, contribution_score)) * 0.5 if contribution_active else 0.0
    return {
        **policy.to_dict(),
        "effective_fragment_requests_per_day": int(policy.cloud_fragment_requests_per_day * multiplier),
        "effective_max_cloud_nodes_per_query": int(policy.max_cloud_nodes_per_query * min(multiplier, 2.0)),
        "contribution_active": contribution_active,
        "contribution_score": round(max(0.0, min(1.0, contribution_score)), 3),
    }


def brain_balance_for_plan(
    plan: Plan,
    *,
    local_strength: float,
    cloud_coverage: float,
    seed_stability: float,
    working_memory_capacity: float,
    epistemic_confidence: float,
    provider_healthy: bool,
    contribution_active: bool = False,
    contribution_score: float = 0.0,
    remaining_budget_ratio: float = 1.0,
) -> dict[str, Any]:
    budget = cloud_budget_for_plan(plan, contribution_active=contribution_active, contribution_score=contribution_score)
    local_strength = max(0.0, min(1.0, local_strength))
    cloud_coverage = max(0.0, min(1.0, cloud_coverage))
    remaining_budget_ratio = max(0.0, min(1.0, remaining_budget_ratio))
    if not provider_healthy or remaining_budget_ratio <= 0:
        planned_cloud = 0.0
    else:
        planned_cloud = (1.0 - local_strength) * 0.55 + cloud_coverage * 0.25 + (1.0 - seed_stability) * 0.10
        if plan == "free":
            planned_cloud = min(planned_cloud, 0.35)
        elif plan == "plus" and not contribution_active:
            planned_cloud = min(planned_cloud, 0.22)
        elif plan == "director":
            planned_cloud = min(max(planned_cloud, 0.20), 0.85)
        planned_cloud *= remaining_budget_ratio
    planned_cloud = round(max(0.0, min(0.9, planned_cloud)), 3)
    planned_local = round(1.0 - planned_cloud, 3)
    confidence_cloud = round(planned_cloud * max(0.0, min(1.0, epistemic_confidence)), 3)
    return {
        "plan": plan,
        "provider_healthy": provider_healthy,
        "cloud_budget": budget,
        "planned_balance": {"local": planned_local, "cloud": planned_cloud},
        "actual_context_balance": {
            "local": planned_local,
            "cloud": planned_cloud,
            "seed": round(max(0.0, min(1.0, 1.0 - seed_stability)) * 0.15, 3),
            "working_memory": round(max(0.0, min(1.0, working_memory_capacity)), 3),
        },
        "confidence_contribution_balance": {
            "local": round(planned_local * max(0.0, min(1.0, epistemic_confidence)), 3),
            "cloud": confidence_cloud,
        },
    }
