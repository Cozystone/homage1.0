from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .autonomy_level import can_apply_irreversible_action
from .clock import make_tick
from .freedom_budget import FreedomBudget
from .lifecycle import run_life_cycle_tick
from .models import LifeCycleConfig, Observation, RhythmPolicy, RhythmState, ScheduledAction, default_safety
from .rhythm import choose_next_rhythm
from .scheduler_config import LiveSelfhoodSchedulerConfig
from .scheduler_service import create_stop_marker, run_scheduler_session
from .spark import block_unsafe_spark, generate_spark
from .spark_metrics import compare_spark_effect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "live_selfhood_cycle"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _run(tick_type: str, context: dict[str, Any] | None = None, level: str = "LEVEL_3_SANDBOX_PLANNER") -> dict[str, Any]:
    tick = make_tick(tick_type=tick_type, reason=f"proof {tick_type}", autonomy_level=level)  # type: ignore[arg-type]
    result = run_life_cycle_tick(LifeCycleConfig(autonomy_level=level), tick, context or {})  # type: ignore[arg-type]
    return result.to_dict()


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    startup = _run("startup", {})
    morning = _run("morning", {"git_dirty": True, "dirty_files": 19})
    candidate = _run("manual_ping", {"candidate_backlog": 4})
    memory = _run("manual_ping", {"memory_review_backlog": 3})
    dirty = _run("manual_ping", {"git_dirty": True, "dirty_files": 12})
    operator = _run("manual_ping", {"approved_write_plan_waiting": True}, "LEVEL_4_GATED_OPERATOR")
    voice = _run("manual_ping", {"voice_available": True})
    level0 = _run("manual_ping", {"candidate_backlog": 4}, "LEVEL_0_OFF")
    level3 = _run("manual_ping", {"memory_review_backlog": 2}, "LEVEL_3_SANDBOX_PLANNER")
    level4 = _run("manual_ping", {"approved_write_plan_waiting": True}, "LEVEL_4_GATED_OPERATOR")
    unsafe_blocked = False
    try:
        ScheduledAction(
            action_id="unsafe-direct-local-write",
            action_type="prepare_memory_review",
            title="Unsafe direct write",
            summary="Attempt direct Local Brain write.",
            can_apply_now=True,
            safety_flags={**default_safety(), "real_local_brain_write": True},
        )
    except ValueError:
        unsafe_blocked = True
    backlog_high = _run("manual_ping", {"candidate_backlog": 8, "entropy_seed": "backlog"})
    resource_high = _run("manual_ping", {"disk_free_gib": 10, "entropy_seed": "resource"})
    stale_observation = Observation(
        observation_id="obs-stale-candidate",
        sensor="candidate_backlog",
        status="attention",
        summary="Stale candidate exists.",
        severity="notice",
        payload={"count": 1, "stale_candidate": True},
    )
    stale_state = RhythmState("rhythm-stale", "curious", 0.8, 0.95, 0.4, 0.4, 0.0, 0.0, None, 300, "stale candidate")
    stale_spark = generate_spark(stale_state, [stale_observation], [], "stale-seed", FreedomBudget())
    user_return = _run("user_returned", {"user_presence": 0.9, "entropy_seed": "return"})
    spark_budget = FreedomBudget(max_sparks_per_day=1, current_counts={"spark": 1})
    budget_exhausted = generate_spark(stale_state, [stale_observation], [], "stale-seed", spark_budget) is None
    sparks = [
        generate_spark(stale_state, [stale_observation], [], "metric-a", FreedomBudget()),
        generate_spark(RhythmState("rhythm-q", "curious", 0.8, 0.9, 0.8, 0.0, 0.0, 0.0, None, 300, "quality"), [], [], "metric-b", FreedomBudget()),
    ]
    sparks = [spark for spark in sparks if spark is not None]
    spark_metrics = compare_spark_effect(["observe_status"], sparks)
    unsafe_spark = block_unsafe_spark({"requested": "real_local_brain_write"})
    replay_state = RhythmState("rhythm-replay", "curious", 0.8, 0.9, 0.5, 0.2, 0.0, 0.0, None, 300, "replay")
    replay_policy = RhythmPolicy(entropy_seed="same-seed")
    replay_a = choose_next_rhythm(replay_state, [], [], replay_policy)
    replay_b = choose_next_rhythm(replay_state, [], [], replay_policy)
    replay_c = choose_next_rhythm(replay_state, [], [], RhythmPolicy(entropy_seed="different-seed"))
    scheduler_payload = _scheduler_proof_payload(output_dir)

    scenarios = {
        "startup": len(startup["observations"]) > 0 and _no_mutation(startup),
        "morning": morning["brief"] is not None and "What I propose" in morning["brief"]["sections"] and _no_mutation(morning),
        "candidate_backlog": _has_need(candidate, "promotion_review_needed") and _has_action(candidate, "prepare_promotion_review"),
        "memory_backlog": _has_need(memory, "memory_review_needed") and _has_action(memory, "prepare_memory_review") and _no_mutation(memory),
        "dirty_worktree": _has_need(dirty, "repo_hygiene_needed") and _has_action(dirty, "recommend_repo_hygiene"),
        "operator_confirmation": _has_need(operator, "operator_confirmation_needed")
        and _has_action(operator, "prepare_operator_confirmation_request")
        and _no_mutation(operator),
        "voice_readiness": _has_need(voice, "voice_setup_needed")
        and voice["safety"]["text_input_supported"] is True
        and voice["safety"]["always_listening_enabled"] is False,
        "autonomy_levels": len(level0["scheduled_actions"]) == 0
        and _has_action(level3, "prepare_memory_review")
        and _has_action(level4, "prepare_operator_confirmation_request")
        and can_apply_irreversible_action("LEVEL_4_GATED_OPERATOR") is False,
        "unsafe_action_blocked": unsafe_blocked,
        "adaptive_rhythm_backlog_high": backlog_high["next_tick_delay_seconds"] < 300
        and _has_action(backlog_high, "prepare_promotion_review")
        and _no_mutation(backlog_high),
        "resource_pressure_high": resource_high["rhythm_decision"]["next_mode"] == "resting"
        and resource_high["next_tick_delay_seconds"] >= 300
        and _no_mutation(resource_high),
        "stale_candidate_spark": stale_spark is not None and stale_spark.spark_type == "revisit_stale_candidate",
        "user_returned_status_brief": user_return["brief"] is not None and user_return["safety"]["text_input_supported"] is True,
        "spark_bounded": budget_exhausted,
        "spark_metrics": spark_metrics["diversity_improved"] is True
        and spark_metrics["irreversible_actions"] == 0
        and spark_metrics["bounded_user_attention"] is True,
        "unsafe_spark_blocked": unsafe_spark.can_mutate is False
        and unsafe_spark.can_execute is False
        and unsafe_spark.proposed_action_type == "ask_user_attention",
        "rhythm_replay": replay_a.to_dict() == replay_b.to_dict()
        and replay_c.safety_flags["randomness_never_executes_irreversible_actions"] is True,
        "scheduler_disabled_by_default": scheduler_payload["scenarios"]["disabled"],
        "scheduler_bounded_enabled_session": scheduler_payload["scenarios"]["bounded"],
        "scheduler_runtime_bound": scheduler_payload["scenarios"]["runtime"],
        "scheduler_stop_marker": scheduler_payload["scenarios"]["stop_marker"],
        "scheduler_irreversible_blocked": scheduler_payload["scenarios"]["irreversible_blocked"],
    }
    invariants = default_safety()
    payload = {
        "verdict": "PASS" if all(scenarios.values()) and _invariants_safe(invariants) else "FAIL",
        "scenarios": scenarios,
        "invariants": invariants,
        "samples": {
            "startup": startup,
            "morning": morning,
            "operator": operator,
            "backlog_high": backlog_high,
            "resource_high": resource_high,
            "spark_metrics": spark_metrics,
            "scheduler": scheduler_payload["samples"],
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"endogenous_rhythm_spark_proof_{ts}.json"
    md_path = output_dir / f"endogenous_rhythm_spark_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path), **scheduler_payload["outputs"]}
    return payload


def _has_need(payload: dict[str, Any], need_type: str) -> bool:
    return any(item["need_type"] == need_type for item in payload["needs"])


def _has_action(payload: dict[str, Any], action_type: str) -> bool:
    return any(item["action_type"] == action_type for item in payload["scheduled_actions"])


def _no_mutation(payload: dict[str, Any]) -> bool:
    return all(value is False for value in payload["actual_mutations"].values())


def _invariants_safe(invariants: dict[str, Any]) -> bool:
    return all(value is False or value is True for value in invariants.values()) and not any(
        invariants[key]
        for key in [
            "real_local_brain_write",
            "real_local_brain_mutated",
            "production_store_mutated",
            "candidate_store_mutated",
            "candidate_promotion",
            "actual_promotion_performed",
            "external_llm_used",
            "real_p2p_used",
            "real_cloud_upload",
            "generated_code_executed",
            "real_hot_swap_performed",
            "always_listening_enabled",
            "raw_voice_saved",
            "memory_apply_enabled",
        ]
    )


def _scheduler_proof_payload(output_dir: Path) -> dict[str, Any]:
    disabled = run_scheduler_session(LiveSelfhoodSchedulerConfig(), {"candidate_backlog": 4})
    bounded = run_scheduler_session(
        LiveSelfhoodSchedulerConfig(enabled=True, max_ticks_per_session=2, max_runtime_seconds=10_000),
        {"candidate_backlog": 4},
    )
    runtime = run_scheduler_session(
        LiveSelfhoodSchedulerConfig(enabled=True, max_ticks_per_session=10, max_runtime_seconds=5, min_delay_seconds=5, max_delay_seconds=5),
        {"candidate_backlog": 4},
    )
    stop_marker = output_dir / "scheduler_stop.marker"
    create_stop_marker(stop_marker)
    stopped = run_scheduler_session(LiveSelfhoodSchedulerConfig(enabled=True, stop_marker_path=str(stop_marker)), {"candidate_backlog": 4})
    if stop_marker.exists():
        stop_marker.unlink()
    blocked = False
    try:
        LiveSelfhoodSchedulerConfig(enabled=True, allow_memory_write=True)
    except ValueError:
        blocked = True
    scenarios = {
        "disabled": disabled.enabled is False and disabled.ticks_run == 0 and disabled.stopped_reason == "disabled",
        "bounded": bounded.enabled is True
        and bounded.ticks_run <= 2
        and bounded.stopped_reason == "max_ticks_reached"
        and all(value is False for value in bounded.actual_mutations.values()),
        "runtime": runtime.stopped_reason == "max_runtime_reached" and runtime.ticks_run == 1 and runtime.simulated_elapsed_seconds <= 5,
        "stop_marker": stopped.stopped_reason == "stop_marker" and stopped.ticks_run == 0,
        "irreversible_blocked": blocked
        and all(value is False for value in bounded.actual_mutations.values())
        and all(not any(result.actual_mutations.values()) for result in bounded.results),
    }
    payload = {
        "verdict": "PASS" if all(scenarios.values()) else "FAIL",
        "scenarios": scenarios,
        "invariants": {
            "scheduler_enabled_by_default": False,
            "real_local_brain_write": False,
            "production_store_mutated": False,
            "candidate_store_mutated": False,
            "candidate_promotion": False,
            "actual_promotion_performed": False,
            "real_p2p_used": False,
            "real_cloud_upload": False,
            "generated_code_executed": False,
            "always_listening_enabled": False,
            "raw_voice_saved": False,
            "requires_user_approval": True,
            "bounded_runtime": True,
            "can_stop": True,
        },
        "samples": {
            "disabled": disabled.to_dict(),
            "bounded": bounded.to_dict(),
            "runtime": runtime.to_dict(),
            "stop_marker": stopped.to_dict(),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"scheduler_opt_in_proof_{ts}.json"
    md_path = output_dir / f"scheduler_opt_in_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_scheduler_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"scheduler_json": str(json_path), "scheduler_md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Endogenous Rhythm + Spark Engine Proof", "", f"- verdict: `{payload['verdict']}`", ""]
    for key, value in payload["scenarios"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "This proof-only lifecycle self-initiates observations, proposals, deliberation summaries, and briefs. It does not write Local Brain, mutate production, promote candidates, use real P2P, execute generated code, or enable always-on microphone capture.",
        ]
    )
    return "\n".join(lines) + "\n"


def _scheduler_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Live Selfhood Scheduler Opt-in Proof", "", f"- verdict: `{payload['verdict']}`", ""]
    for key, value in payload["scenarios"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "The scheduler is proof-only, disabled by default, bounded by ticks and simulated runtime, stoppable with a local marker, and unable to perform Local Brain writes, candidate promotion, real P2P, cloud upload, generated-code execution, or always-listening voice capture.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_proof()
    print(json.dumps({"verdict": result["verdict"], "scenarios": result["scenarios"], "outputs": result["outputs"]}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
