from __future__ import annotations

from dataclasses import replace
from typing import Any

from .action_queue import enqueue_actions
from .autonomy_level import permits_action
from .brief import generate_brief
from .deliberation import deliberate_actions
from .event_stream import build_events
from .freedom_budget import FreedomBudget, can_generate_spark, register_action
from .impulse import rank_impulses
from .models import LifeCycleConfig, LifeCycleResult, LifeCycleTick, RhythmPolicy, ScheduledAction, Spark, default_safety
from .needs import append_operator_confirmation_need, needs_from_observations
from .rhythm import choose_next_rhythm, derive_rhythm_state
from .scheduler import LifeCycleScheduler
from .sensors import observe_all


def run_life_cycle_tick(
    config: LifeCycleConfig,
    tick: LifeCycleTick,
    context: dict[str, Any] | None = None,
) -> LifeCycleResult:
    """Run one proof-only lifecycle tick."""

    ctx = dict(context or {})
    observations = observe_all(ctx)
    needs = needs_from_observations(observations, tick)
    needs = append_operator_confirmation_need(needs, bool(ctx.get("approved_write_plan_waiting", False)))
    impulses = rank_impulses(needs)
    policy = ctx.get("rhythm_policy")
    if not isinstance(policy, RhythmPolicy):
        policy = RhythmPolicy(entropy_seed=str(ctx.get("entropy_seed", "atanor-proof-seed")))
    rhythm_state = derive_rhythm_state(
        observations,
        policy,
        last_tick_at=str(ctx.get("last_tick_at")) if ctx.get("last_tick_at") else None,
        user_presence=float(ctx.get("user_presence", 0.0) or 0.0),
        no_op_cycles=int(ctx.get("no_op_cycles", 0) or 0),
    )
    rhythm_decision = choose_next_rhythm(rhythm_state, observations, needs, policy)
    budget = ctx.get("freedom_budget")
    if not isinstance(budget, FreedomBudget):
        budget = FreedomBudget(current_counts=dict(ctx.get("freedom_counts", {}) or {}), reset_at=str(ctx.get("budget_reset_at", "")))
    spark = Spark.from_dict(rhythm_decision.spark) if hasattr(Spark, "from_dict") and rhythm_decision.spark else None
    if rhythm_decision.spark and not spark:
        spark = Spark(**rhythm_decision.spark)
    if spark and not can_generate_spark(budget):
        spark = None
        rhythm_decision = replace(rhythm_decision, spark_generated=False, spark=None, explanation=f"{rhythm_decision.explanation} Spark budget exhausted; waiting.")
    scheduler = LifeCycleScheduler()
    scheduled = scheduler.schedule(tick, config, impulses, list(ctx.get("recent_events", [])))
    if (
        spark
        and spark.proposed_action_type != "do_nothing"
        and permits_action(config.autonomy_level, spark.proposed_action_type)
        and not any(action.action_type == spark.proposed_action_type for action in scheduled)
    ):
        scheduled.append(
            ScheduledAction(
                action_id=f"action-{tick.tick_id}-spark-{spark.spark_type}",
                action_type=spark.proposed_action_type,
                title=f"Spark: {spark.spark_type.replace('_', ' ')}",
                summary=spark.trigger_reason,
                requires_user_approval=True,
                irreversible=False,
                can_apply_now=False,
                safety_flags=default_safety(),
            )
        )
        scheduled = scheduled[: config.max_actions_per_tick]
    for action in scheduled:
        budget = register_action(budget, "internal_action")
        if action.action_type in {"run_mirofish_deliberation"}:
            budget = register_action(budget, "deliberation")
        if action.action_type in {"prepare_morning_brief", "prepare_evening_brief"}:
            budget = register_action(budget, "brief")
        if action.action_type in {"ask_user_attention", "prepare_operator_confirmation_request"}:
            budget = register_action(budget, "user_attention")
    if spark:
        budget = register_action(budget, "spark")
    queued = enqueue_actions(scheduled)
    deliberations = deliberate_actions(impulses, observations, scheduled)
    brief = generate_brief(tick, observations, needs, impulses, scheduled, queued)
    payload = {
        "tick": tick.to_dict(),
        "observations": [item.to_dict() for item in observations],
        "needs": [item.to_dict() for item in needs],
        "impulses": [item.to_dict() for item in impulses],
        "scheduled_actions": [item.to_dict() for item in scheduled],
        "queued_actions": [item.to_dict() for item in queued],
        "deliberations": [item.to_dict() for item in deliberations],
        "brief": brief.to_dict() if brief else None,
    }
    events = build_events(payload)
    actual_mutations = {
        "real_local_brain_write": False,
        "real_local_brain_mutated": False,
        "production_store_mutated": False,
        "candidate_store_mutated": False,
        "candidate_promotion": False,
        "actual_promotion_performed": False,
        "external_llm_used": False,
        "real_p2p_used": False,
        "real_cloud_upload": False,
        "generated_code_executed": False,
        "real_hot_swap_performed": False,
        "always_listening_enabled": False,
        "raw_voice_saved": False,
        "memory_apply_enabled": False,
    }
    return LifeCycleResult(
        tick=tick,
        observations=observations,
        needs=needs,
        impulses=impulses,
        scheduled_actions=scheduled,
        queued_actions=queued,
        deliberations=deliberations,
        brief=brief,
        events=events,
        safety=default_safety(),
        actual_mutations=actual_mutations,
        rhythm_state=rhythm_state,
        rhythm_decision=rhythm_decision,
        spark=spark,
        next_tick_delay_seconds=rhythm_decision.next_tick_delay_seconds,
        freedom_budget_snapshot=budget.to_dict(),
    )
