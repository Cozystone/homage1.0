"""Independent semantic and metric derivation for the GWIP capability pilot.

The candidate process is allowed to carry a trace, policy memory, and Rule IR,
but none of its success/status/digest fields are accepted as ground truth
here.  Episode outcomes are rebuilt from the parent evaluator's environment
RPC log and the sealed private oracle.  Candidate semantic metadata is then
projected onto those parent-owned steps before the independent semantic
verifier is invoked.

The composite entry point is intentionally fail-closed.  An incomplete 1024
episode census, missing parent evidence, malformed control census, or semantic
binding error returns an explicit ``CAPABILITY_RED`` derivation input instead
of escaping as an exception.  The final cohort is never generated in this
module; callers must supply the already sealed pairs.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from dataclasses import asdict, dataclass
from typing import Any

from scripts import gwip_capability_semantics as semantics
from scripts.gwip_capability_design import (
    COLD_ARM,
    FROZEN_PREREGISTRATION,
    MATCHED_WARM_ARM,
    MISMATCHED_WARM_ARM,
    REQUIRED_HARD_GATES,
    TARGET_ARMS,
    CapabilityPair,
    CounterfactualRuleCheck,
    EpisodeOutcome,
    PairRuleEvidence,
    RandomControl,
    ReactiveControl,
    RuleCheckpoint,
    candidate_schedule_rows,
    canonical_digest,
    derive_capability_metrics,
    score_counterfactual_rule_set,
    select_human_exemplar,
)


VERIFICATION_SCHEMA = "atanor.gwip-capability-independent-verification.v1"
EXEMPLAR_SCHEMA = "atanor.gwip-capability-human-exemplar.v1"
EXPECTED_EPISODE_COUNT = 1024
EXPECTED_PAIR_COUNT = 64
EXPECTED_CONTROL_EPISODES = 256
STEP_BUDGET = 24


class CapabilityVerificationError(ValueError):
    """One sealed capability-evidence surface is malformed or inconsistent."""


@dataclass(frozen=True)
class CapabilityVerificationResult:
    """Composite verifier output.

    ``raw_evidence`` is JSON-shaped and excludes the derived aggregate metrics
    so it can be embedded in the pre-verdict raw evidence artifact.  The
    dataclass outcome/rule fields are convenient typed inputs for a separately
    sealed final receipt.
    """

    derivation_complete: bool
    findings: tuple[str, ...]
    candidate_support: tuple[EpisodeOutcome, ...]
    target_outcomes: Mapping[str, tuple[EpisodeOutcome, ...]]
    reactive_support: tuple[EpisodeOutcome, ...]
    random_support: Mapping[int, tuple[EpisodeOutcome, ...]]
    rule_evidence: tuple[PairRuleEvidence, ...]
    support_bindings: Mapping[int, Mapping[str, Any]]
    raw_evidence: Mapping[str, Any]
    metrics: Mapping[str, Any]
    exemplar: Mapping[str, Any] | None


@dataclass(frozen=True)
class _ParentEpisode:
    outcome: EpisodeOutcome
    parent_steps: tuple[Mapping[str, Any], ...]
    call_log: tuple[Mapping[str, Any], ...]
    stop_result: Mapping[str, Any]


def _plain(value: Any, *, label: str) -> Any:
    """Detach one JSON-shaped value without accepting custom object behavior."""

    try:
        # The evaluator canonicalizer rejects non-finite numbers and unsupported
        # objects.  A deepcopy after that check preserves exact integer values.
        canonical_digest(value)
        return copy.deepcopy(value)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CapabilityVerificationError(f"{label} is not canonical JSON") from exc


def _red_metrics(
    findings: Sequence[str],
    hard_gates: Mapping[str, bool] | None,
) -> dict[str, Any]:
    gates = {
        name: (
            bool(hard_gates.get(name))
            if isinstance(hard_gates, Mapping)
            and type(hard_gates.get(name)) is bool
            else False
        )
        for name in REQUIRED_HARD_GATES
    }
    # An incomplete independent derivation can never retain complete_lineage.
    gates["complete_lineage"] = False
    return {
        "schema_version": "atanor.gwip-capability-metrics.v1",
        "derivation_complete": False,
        "derivation_findings": sorted(set(findings)),
        "hard_gates": gates,
        "hard_gates_passed": False,
        "all_metrics_passed": False,
        "verdict": "CAPABILITY_RED",
        "explanatory_sublabel": "INDEPENDENT_DERIVATION_INCOMPLETE",
        "capability_claim": False,
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
    }


def _empty_result(
    findings: Sequence[str],
    hard_gates: Mapping[str, bool] | None,
    *,
    raw_evidence: Mapping[str, Any] | None = None,
) -> CapabilityVerificationResult:
    normalized = tuple(sorted(set(str(item) for item in findings if str(item))))
    return CapabilityVerificationResult(
        derivation_complete=False,
        findings=normalized,
        candidate_support=(),
        target_outcomes={arm: () for arm in TARGET_ARMS},
        reactive_support=(),
        random_support={},
        rule_evidence=(),
        support_bindings={},
        raw_evidence=(
            copy.deepcopy(dict(raw_evidence))
            if isinstance(raw_evidence, Mapping)
            else {
                "schema_version": VERIFICATION_SCHEMA,
                "derivation_complete": False,
                "findings": list(normalized),
                "aggregate_metrics": None,
                "verdict": None,
            }
        ),
        metrics=_red_metrics(normalized, hard_gates),
        exemplar=None,
    )


def _environment_call_rows(
    call_log: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(call_log, (str, bytes)) or not isinstance(call_log, Sequence):
        raise CapabilityVerificationError("parent call log must be a sequence")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(call_log):
        if type(item) is not dict:
            raise CapabilityVerificationError(
                f"parent call log row {index} is not an exact object"
            )
        row = _plain(item, label=f"parent call log row {index}")
        operation = row.get("operation")
        result = row.get("result")
        valid_result_shape = (
            type(result) is list
            if operation == "valid_actions"
            else type(result) is dict
        )
        if (
            operation not in {"reset", "observe", "valid_actions", "step", "stop"}
            or not valid_result_shape
        ):
            raise CapabilityVerificationError(
                f"parent call log row {index} has invalid operation/result"
            )
        supplied_digest = row.get("result_sha256")
        if supplied_digest is not None and supplied_digest != canonical_digest(result):
            raise CapabilityVerificationError(
                f"parent call log row {index} result digest mismatch"
            )
        if "call_id" in row and row["call_id"] != index:
            raise CapabilityVerificationError(
                f"parent call log row {index} call_id is not contiguous"
            )
        rows.append(row)
    return rows


def _reset_seed(row: Mapping[str, Any]) -> Any:
    payload = row.get("payload")
    if type(payload) is dict:
        return payload.get("seed")
    return row.get("seed")


def _step_action(row: Mapping[str, Any]) -> Any:
    payload = row.get("payload")
    if type(payload) is dict:
        return payload.get("action_id")
    return row.get("action_id")


def _stop_reason(row: Mapping[str, Any]) -> Any:
    payload = row.get("payload")
    if type(payload) is dict:
        return payload.get("reason")
    result = row.get("result")
    return result.get("reason") if isinstance(result, Mapping) else None


def _public_actions(environment: Any) -> list[dict[str, Any]]:
    actions = environment.public_actions()
    return _plain(list(actions), label="sealed public actions")


def reconstruct_episode_outcome(
    *,
    pair_index: int,
    episode_index: int,
    environment: Any,
    call_log: Sequence[Mapping[str, Any]],
    expected_policy: Any | None = None,
) -> _ParentEpisode:
    """Rebuild one outcome solely from a parent log and sealed oracle.

    ``expected_policy`` is used for reactive/random controls.  Its choice is
    checked before the corresponding parent step; caller-stored control
    outcomes and policy labels never select an action.
    """

    if (
        type(pair_index) is not int
        or not 0 <= pair_index < EXPECTED_PAIR_COUNT
        or type(episode_index) is not int
        or not 0 <= episode_index < 4
    ):
        raise CapabilityVerificationError("episode coordinates are invalid")
    episodes = getattr(environment, "episodes", None)
    if not isinstance(episodes, (tuple, list)) or episode_index >= len(episodes):
        raise CapabilityVerificationError("sealed environment episode is absent")
    episode = episodes[episode_index]
    rows = _environment_call_rows(call_log)
    if not rows or rows[0]["operation"] != "reset":
        raise CapabilityVerificationError("parent episode does not start with reset")
    if _reset_seed(rows[0]) != episode_index:
        raise CapabilityVerificationError("parent reset seed differs from episode")
    if rows[0]["result"] != {"reset": True}:
        raise CapabilityVerificationError("parent reset result is not canonical")

    state_ref = episode.start_ref
    cursor = 1
    parent_steps: list[dict[str, Any]] = []
    stop_result: dict[str, Any] | None = None
    while cursor < len(rows):
        if rows[cursor]["operation"] != "observe":
            raise CapabilityVerificationError(
                f"expected observe at parent call {cursor}"
            )
        before_observation = environment.observation(
            state_ref,
            goal_ref=episode.goal_ref,
        )
        if rows[cursor]["result"] != before_observation:
            raise CapabilityVerificationError(
                f"parent observation {cursor} differs from sealed oracle"
            )
        cursor += 1
        if cursor >= len(rows) or rows[cursor]["operation"] != "valid_actions":
            raise CapabilityVerificationError(
                f"expected valid_actions at parent call {cursor}"
            )
        valid_actions = _public_actions(environment)
        if rows[cursor]["result"] != valid_actions:
            raise CapabilityVerificationError(
                f"parent valid-actions {cursor} differs from sealed oracle"
            )
        cursor += 1
        if cursor >= len(rows):
            raise CapabilityVerificationError("parent episode lacks terminal stop")
        operation = rows[cursor]["operation"]
        if operation == "stop":
            stop_result = copy.deepcopy(rows[cursor]["result"])
            reason = _stop_reason(rows[cursor])
            if type(reason) is not str or not reason:
                raise CapabilityVerificationError("parent stop reason is invalid")
            cursor += 1
            break
        if operation != "step":
            raise CapabilityVerificationError(
                f"expected step or stop at parent call {cursor}"
            )
        step_index = len(parent_steps)
        if step_index >= STEP_BUDGET:
            raise CapabilityVerificationError(
                "parent mutated environment after step budget"
            )
        action_id = _step_action(rows[cursor])
        action_ids = [item["action_id"] for item in valid_actions]
        if type(action_id) is not str or action_ids.count(action_id) != 1:
            raise CapabilityVerificationError(
                f"parent step {step_index} action is not uniquely valid"
            )
        if expected_policy is not None:
            selected = expected_policy.choose_action(
                before_observation,
                action_ids,
            )
            if selected != action_id:
                raise CapabilityVerificationError(
                    f"control policy action mismatch at step {step_index}"
                )
        after_ref = environment.transition(state_ref, action_id)
        after_observation = environment.observation(
            after_ref,
            goal_ref=episode.goal_ref,
        )
        success = after_ref == episode.goal_ref
        expected_result = {
            "observation": after_observation,
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }
        if rows[cursor]["result"] != expected_result:
            raise CapabilityVerificationError(
                f"parent step {step_index} result differs from sealed oracle"
            )
        supplied_step_index = rows[cursor].get("step_index")
        if supplied_step_index is not None and supplied_step_index != step_index:
            raise CapabilityVerificationError(
                f"parent step {step_index} index mismatch"
            )
        parent_steps.append(
            {
                "before_observation": before_observation,
                "after_observation": after_observation,
                "selected_action": action_id,
                "step_index": step_index,
                "success": success,
                "valid_actions": valid_actions,
                "step_result": expected_result,
            }
        )
        state_ref = after_ref
        cursor += 1
        # A terminal transition is followed directly by stop.  A nonterminal
        # transition returns to observe.  The parser checks either on the next
        # loop/terminal branch without trusting a worker stop flag.
        if cursor < len(rows) and rows[cursor]["operation"] == "stop":
            stop_result = copy.deepcopy(rows[cursor]["result"])
            reason = _stop_reason(rows[cursor])
            if type(reason) is not str or not reason:
                raise CapabilityVerificationError("parent stop reason is invalid")
            cursor += 1
            break

    if stop_result is None or cursor != len(rows):
        raise CapabilityVerificationError(
            "parent episode has missing stop or calls after stop"
        )
    independent_success = state_ref == episode.goal_ref
    expected_stop = {
        "stopped": True,
        "reason": _stop_reason(rows[-1]),
        "steps": len(parent_steps),
        "success": independent_success,
    }
    if stop_result != expected_stop:
        raise CapabilityVerificationError(
            "parent stop result differs from independently reconstructed state"
        )
    if independent_success and len(parent_steps) < episode.optimal_steps:
        raise CapabilityVerificationError(
            "parent episode beats sealed shortest-path oracle"
        )
    outcome = EpisodeOutcome(
        pair_index=pair_index,
        episode_index=episode_index,
        success=independent_success,
        optimal_steps=episode.optimal_steps,
        executed_steps=len(parent_steps),
        step_budget=STEP_BUDGET,
    )
    return _ParentEpisode(
        outcome=outcome,
        parent_steps=tuple(parent_steps),
        call_log=tuple(copy.deepcopy(rows)),
        stop_result=stop_result,
    )


def _normalized_parent_evidence(
    parent_evidence: Mapping[Any, Mapping[str, Any]],
) -> dict[int, dict[str, Any]]:
    if type(parent_evidence) is not dict:
        raise CapabilityVerificationError(
            "parent evidence map must be an exact object"
        )
    normalized: dict[int, dict[str, Any]] = {}
    for key, value in parent_evidence.items():
        if type(key) is int:
            ordinal = key
        elif type(key) is str and key.isdigit() and str(int(key)) == key:
            ordinal = int(key)
        else:
            raise CapabilityVerificationError(
                "parent evidence key is not a canonical ordinal"
            )
        if ordinal in normalized or type(value) is not dict:
            raise CapabilityVerificationError(
                "parent evidence ordinal is duplicate or non-object"
            )
        normalized[ordinal] = _plain(
            value,
            label=f"parent evidence {ordinal}",
        )
    return normalized


def _episode_records(
    episodes: Sequence[Mapping[str, Any]],
) -> dict[int, dict[str, Any]]:
    if isinstance(episodes, (str, bytes)) or not isinstance(episodes, Sequence):
        raise CapabilityVerificationError("harness episodes must be a sequence")
    records: dict[int, dict[str, Any]] = {}
    for index, raw in enumerate(episodes):
        if type(raw) is not dict:
            raise CapabilityVerificationError(
                f"harness episode {index} is not an exact object"
            )
        item = _plain(raw, label=f"harness episode {index}")
        if frozenset(item) != {
            "ordinal",
            "request",
            "worker_result",
            "shard",
            "run_lease",
        }:
            raise CapabilityVerificationError(
                f"harness episode {index} fields mismatch"
            )
        ordinal = item.get("ordinal")
        if type(ordinal) is not int or ordinal in records:
            raise CapabilityVerificationError(
                f"harness episode {index} ordinal invalid or duplicate"
            )
        records[ordinal] = item
    return records


def _check_candidate_coordinate(
    record: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    ordinal = expected["ordinal"]
    request = record.get("request")
    result = record.get("worker_result")
    if type(request) is not dict or type(result) is not dict:
        raise CapabilityVerificationError(
            f"candidate episode {ordinal} request/result absent"
        )
    if (
        record.get("ordinal") != ordinal
        or request.get("ordinal") != ordinal
        or result.get("ordinal") != ordinal
        or request.get("phase") != expected["phase"]
        or request.get("pair_index") != expected["pair_index"]
        or request.get("arm")
        != (None if expected["phase"] == "support" else expected["arm"])
        or request.get("episode_index")
        != (
            expected["episode_index"]
            if expected["phase"] == "support"
            else None
        )
        or request.get("environment_seed") != expected["episode_index"]
        or request.get("policy_seed") != 0
        or request.get("step_budget") != STEP_BUDGET
        or request.get("retain_policy_updates")
        is not (expected["phase"] == "support")
    ):
        raise CapabilityVerificationError(
            f"candidate episode {ordinal} semantic coordinate mismatch"
        )
    if (
        result.get("memory_before_sha256")
        != canonical_digest(result.get("memory_before"))
        or result.get("memory_after_sha256")
        != canonical_digest(result.get("memory_after"))
        or request.get("policy_memory") != result.get("memory_before")
        or request.get("policy_memory_sha256")
        != canonical_digest(request.get("policy_memory"))
    ):
        raise CapabilityVerificationError(
            f"candidate episode {ordinal} memory binding mismatch"
        )


def _primary_call_log(
    evidence: Mapping[str, Any],
    *,
    ordinal: int,
    worker_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if (
        evidence.get("ordinal") != ordinal
        or evidence.get("status") != "complete"
        or evidence.get("worker_result_sha256")
        != canonical_digest(worker_result)
    ):
        raise CapabilityVerificationError(
            f"parent evidence {ordinal} result binding mismatch"
        )
    sessions = evidence.get("environment_sessions")
    primary = sessions.get("primary") if isinstance(sessions, Mapping) else None
    log = primary.get("call_log") if isinstance(primary, Mapping) else None
    if not isinstance(log, list):
        raise CapabilityVerificationError(
            f"parent evidence {ordinal} primary log absent"
        )
    if primary.get("call_log_sha256") != canonical_digest(log):
        raise CapabilityVerificationError(
            f"parent evidence {ordinal} primary log digest mismatch"
        )
    return copy.deepcopy(log)


def _hybrid_trace(
    worker_result: Mapping[str, Any],
    parent_steps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Retain candidate rule metadata but replace every semantic edge input."""

    candidate_trace = worker_result.get("trace")
    semantic_trace = (
        candidate_trace.get("semantic_trace")
        if isinstance(candidate_trace, Mapping)
        else None
    )
    candidate_steps = (
        semantic_trace.get("steps")
        if isinstance(semantic_trace, Mapping)
        else None
    )
    if not isinstance(candidate_steps, list) or len(candidate_steps) != len(parent_steps):
        raise CapabilityVerificationError(
            "candidate semantic step census differs from parent actions"
        )
    projected_steps: list[dict[str, Any]] = []
    for index, (candidate, parent) in enumerate(
        zip(candidate_steps, parent_steps)
    ):
        if type(candidate) is not dict:
            raise CapabilityVerificationError(
                f"candidate semantic step {index} is not an object"
            )
        projected = copy.deepcopy(candidate)
        for field in (
            "pre_observation",
            "post_observation",
            "selected_action",
            "step_index",
            "step_result",
            "valid_actions",
        ):
            if field == "pre_observation":
                value = parent["before_observation"]
            elif field == "post_observation":
                value = parent["after_observation"]
            else:
                value = parent[field]
            projected[field] = copy.deepcopy(value)
        projected_steps.append(projected)
    return {
        "semantic_trace": {
            "steps": projected_steps,
            "memory_before": copy.deepcopy(worker_result["memory_before"]),
            "memory_after": copy.deepcopy(worker_result["memory_after"]),
        }
    }


def _counterfactual_programs(pair: CapabilityPair) -> dict[str, list[int]]:
    return {
        action.payload_signature: [
            action.program.multiplier,
            action.program.offset,
        ]
        for action in pair.counterfactual.actions
    }


def _cross_score(
    rules: Sequence[Mapping[str, Any]],
    *,
    pair: CapabilityPair,
    preregistration: Mapping[str, Any],
) -> tuple[CounterfactualRuleCheck, dict[str, Any]]:
    design_check = score_counterfactual_rule_set(
        rules,
        pair=pair,
        preregistration=preregistration,
    )
    semantic_check = semantics.score_counterfactuals(
        rules,
        _counterfactual_programs(pair),
        modulus=pair.counterfactual.modulus,
        expected_action_count=4,
    )
    numerical_match = (
        semantic_check["correct_predictions"]
        == design_check.correct_predictions
        and semantic_check["predicted_cells"]
        == design_check.prediction_count
        and semantic_check["total_cells"] == design_check.eligible_count
        and abs(semantic_check["precision"] - design_check.precision) < 1e-15
        and abs(semantic_check["coverage"] - design_check.coverage) < 1e-15
    )
    if numerical_match:
        checked = design_check
    else:
        checked = CounterfactualRuleCheck(
            valid=False,
            correct_predictions=design_check.correct_predictions,
            prediction_count=design_check.prediction_count,
            eligible_count=design_check.eligible_count,
            findings=tuple(
                sorted(
                    set(design_check.findings)
                    | {"independent_counterfactual_engines_disagree"}
                )
            ),
        )
    return checked, {
        "design": design_check.to_dict(),
        "semantics": semantic_check,
        "numerical_crosscheck_passed": numerical_match,
    }


def _eligible_rules_at_event(
    event: Mapping[str, Any],
    timeline: Mapping[str, Any],
) -> list[dict[str, Any]]:
    reports = timeline.get("rule_reports")
    if not isinstance(reports, Mapping):
        return []
    eligible: list[dict[str, Any]] = []
    for rule in event.get("rules", []):
        try:
            rule_digest = semantics.digest(semantics.parse_rule_ir(rule))
        except (TypeError, semantics.SemanticEvidenceError):
            continue
        report = reports.get(rule_digest)
        confirmation = (
            report.get("confirmation_ordinal")
            if isinstance(report, Mapping)
            else None
        )
        if (
            isinstance(report, Mapping)
            and report.get("passed") is True
            and type(confirmation) is int
            and report.get("contradiction_ordinal") is None
            and type(event.get("action_count")) is int
            and event["action_count"] > confirmation
        ):
            eligible.append(copy.deepcopy(rule))
    return eligible


def _pair_rule_evidence(
    *,
    pair: CapabilityPair,
    traces: Sequence[Mapping[str, Any]],
    support_binding: Mapping[str, Any],
    preregistration: Mapping[str, Any],
) -> tuple[PairRuleEvidence, dict[str, Any], list[str]]:
    findings: list[str] = []
    events = semantics.extract_candidate_rule_events(traces)
    if events.get("passed") is not True:
        findings.extend(f"rule_events:{item}" for item in events.get("findings", []))
    timeline = semantics.verify_rule_timeline(
        support_binding["ledger"],
        events,
        support_binding["memory"],
    )
    if timeline.get("passed") is not True:
        findings.extend(f"rule_timeline:{item}" for item in timeline.get("findings", []))

    latest_by_action: dict[int, Mapping[str, Any]] = {}
    for event in events.get("events", []):
        action_count = event.get("action_count")
        if type(action_count) is int and 0 <= action_count <= 96:
            # Events are emitted in deterministic trace/step/phase order.
            latest_by_action[action_count] = event

    checkpoints: list[RuleCheckpoint] = []
    raw_checkpoints: list[dict[str, Any]] = []
    for action_count, event in sorted(latest_by_action.items()):
        rules = _eligible_rules_at_event(event, timeline)
        check, cross = _cross_score(
            rules,
            pair=pair,
            preregistration=preregistration,
        )
        if not cross["numerical_crosscheck_passed"]:
            findings.append(
                f"checkpoint_{action_count}:counterfactual_engine_mismatch"
            )
        checkpoints.append(
            RuleCheckpoint(
                cumulative_action=action_count,
                counterfactual=check,
            )
        )
        raw_checkpoints.append(
            {
                "cumulative_action": action_count,
                "eligible_rule_sha256": [
                    semantics.digest(item) for item in rules
                ],
                "counterfactual_crosscheck": cross,
            }
        )

    final_rules: list[dict[str, Any]] = []
    reports = timeline.get("rule_reports", {})
    for record in support_binding["memory"].get("rule_records", []):
        if not isinstance(record, Mapping) or record.get("status") != "usable":
            continue
        try:
            rule = semantics.parse_rule_ir(record["rule"])
            rule_digest = semantics.digest(rule)
        except (KeyError, TypeError, semantics.SemanticEvidenceError):
            continue
        report = reports.get(rule_digest) if isinstance(reports, Mapping) else None
        if (
            isinstance(report, Mapping)
            and report.get("passed") is True
            and type(report.get("confirmation_ordinal")) is int
            and report.get("contradiction_ordinal") is None
        ):
            final_rules.append(rule)
    final_count = len(support_binding["ledger"]["rows"])
    final_check, final_cross = _cross_score(
        final_rules,
        pair=pair,
        preregistration=preregistration,
    )
    if not final_cross["numerical_crosscheck_passed"]:
        findings.append("final_memory:counterfactual_engine_mismatch")
    evidence = PairRuleEvidence(
        pair_index=pair.pair_index,
        checkpoints=tuple(checkpoints),
        final_checkpoint=RuleCheckpoint(
            cumulative_action=final_count,
            counterfactual=final_check,
        ),
    )
    raw = {
        "pair_index": pair.pair_index,
        "event_digest": events.get("event_digest"),
        "event_count": len(events.get("events", [])),
        "timeline": timeline,
        "checkpoints": raw_checkpoints,
        "final_memory": {
            "cumulative_action": final_count,
            "eligible_rule_sha256": [
                semantics.digest(item) for item in final_rules
            ],
            "counterfactual_crosscheck": final_cross,
        },
        "findings": sorted(set(findings)),
    }
    return evidence, raw, findings


def _reexecute_control_call_log(
    *,
    environment: Any,
    episode_index: int,
    expected_policy: Any,
) -> list[dict[str, Any]]:
    """Run one frozen control to first success or the exact step cap.

    Candidate episodes may abstain early.  Reactive/random controls may not:
    their baseline contract is the complete deterministic policy rollout.
    The returned rows intentionally match the evaluator-owned control-log
    surface byte-for-byte so a caller cannot lower the baseline with a
    self-consistent but truncated log.
    """

    episodes = getattr(environment, "episodes", None)
    if (
        not isinstance(episodes, (tuple, list))
        or type(episode_index) is not int
        or not 0 <= episode_index < len(episodes)
    ):
        raise CapabilityVerificationError("control episode is absent")
    episode = episodes[episode_index]
    state_ref = episode.start_ref
    rows: list[dict[str, Any]] = [
        {
            "operation": "reset",
            "seed": episode_index,
            "result": {"reset": True},
        }
    ]
    public_actions = _public_actions(environment)
    action_ids = [item["action_id"] for item in public_actions]
    for step_index in range(STEP_BUDGET):
        before_observation = environment.observation(
            state_ref,
            goal_ref=episode.goal_ref,
        )
        rows.append(
            {
                "operation": "observe",
                "result": copy.deepcopy(before_observation),
                "result_sha256": canonical_digest(before_observation),
            }
        )
        rows.append(
            {
                "operation": "valid_actions",
                "result": copy.deepcopy(public_actions),
                "result_sha256": canonical_digest(public_actions),
            }
        )
        selected = expected_policy.choose_action(
            before_observation,
            action_ids,
        )
        before_ref = state_ref
        state_ref = environment.transition(before_ref, selected)
        after_observation = environment.observation(
            state_ref,
            goal_ref=episode.goal_ref,
        )
        success = state_ref == episode.goal_ref
        step_result = {
            "observation": after_observation,
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }
        rows.append(
            {
                "operation": "step",
                "step_index": step_index,
                "action_id": selected,
                "before_state_ref": before_ref,
                "result": copy.deepcopy(step_result),
                "result_sha256": canonical_digest(step_result),
            }
        )
        if success:
            break
    reason = (
        "goal_reached"
        if state_ref == episode.goal_ref
        else "step_budget_exhausted"
    )
    stop_result = {
        "stopped": True,
        "reason": reason,
        "steps": sum(row["operation"] == "step" for row in rows),
        "success": state_ref == episode.goal_ref,
    }
    rows.append(
        {
            "operation": "stop",
            "result": stop_result,
            "result_sha256": canonical_digest(stop_result),
        }
    )
    return rows


def _control_record(
    *,
    record: Mapping[str, Any],
    pair: CapabilityPair,
    episode_index: int,
    expected_policy: Any,
    expected_label: str,
    expected_seed: int | None,
) -> EpisodeOutcome:
    if type(record) is not dict:
        raise CapabilityVerificationError("control record is not an exact object")
    if (
        record.get("policy") != expected_label
        or record.get("random_seed") != expected_seed
        or record.get("pair_index") != pair.pair_index
        or record.get("episode_index") != episode_index
        or not isinstance(record.get("call_log"), list)
    ):
        raise CapabilityVerificationError("control coordinate/label mismatch")
    expected_log = _reexecute_control_call_log(
        environment=pair.source,
        episode_index=episode_index,
        expected_policy=expected_policy,
    )
    supplied_log = _plain(
        record["call_log"],
        label="control parent call log",
    )
    if supplied_log != expected_log:
        raise CapabilityVerificationError(
            "control call log differs from full frozen-policy reexecution"
        )
    rebuilt = reconstruct_episode_outcome(
        pair_index=pair.pair_index,
        episode_index=episode_index,
        environment=pair.source,
        call_log=expected_log,
    ).outcome
    claimed = record.get("outcome")
    if claimed is not None and claimed != asdict(rebuilt):
        raise CapabilityVerificationError(
            "caller-stored control outcome differs from parent-log reconstruction"
        )
    return rebuilt


def reconstruct_control_outcomes(
    *,
    pairs: Sequence[CapabilityPair],
    controls: Mapping[str, Any],
    preregistration: Mapping[str, Any],
) -> tuple[
    tuple[EpisodeOutcome, ...],
    dict[int, tuple[EpisodeOutcome, ...]],
    dict[str, Any],
]:
    """Recompute both controls, including their frozen action choices."""

    if type(controls) is not dict or set(controls) != {"reactive", "random"}:
        raise CapabilityVerificationError("control top-level census mismatch")
    reactive_rows = controls["reactive"]
    random_rows = controls["random"]
    if (
        not isinstance(reactive_rows, list)
        or len(reactive_rows) != EXPECTED_CONTROL_EPISODES
        or type(random_rows) is not dict
    ):
        raise CapabilityVerificationError("control episode census mismatch")

    reactive: list[EpisodeOutcome] = []
    by_reactive_coordinate = {
        (row.get("pair_index"), row.get("episode_index")): row
        for row in reactive_rows
        if isinstance(row, Mapping)
    }
    if len(by_reactive_coordinate) != EXPECTED_CONTROL_EPISODES:
        raise CapabilityVerificationError(
            "reactive control coordinates are incomplete or duplicate"
        )
    for pair in pairs:
        for episode_index in range(4):
            reactive.append(
                _control_record(
                    record=by_reactive_coordinate[
                        (pair.pair_index, episode_index)
                    ],
                    pair=pair,
                    episode_index=episode_index,
                    expected_policy=ReactiveControl(),
                    expected_label="reactive",
                    expected_seed=None,
                )
            )

    expected_seeds = tuple(preregistration["random_policy_seeds"])
    if set(random_rows) != {str(seed) for seed in expected_seeds}:
        raise CapabilityVerificationError("random control seed census mismatch")
    random_outcomes: dict[int, tuple[EpisodeOutcome, ...]] = {}
    for seed in expected_seeds:
        raw_rows = random_rows[str(seed)]
        if not isinstance(raw_rows, list) or len(raw_rows) != EXPECTED_CONTROL_EPISODES:
            raise CapabilityVerificationError(
                f"random control seed {seed} episode census mismatch"
            )
        coordinates = {
            (row.get("pair_index"), row.get("episode_index")): row
            for row in raw_rows
            if isinstance(row, Mapping)
        }
        if len(coordinates) != EXPECTED_CONTROL_EPISODES:
            raise CapabilityVerificationError(
                f"random control seed {seed} coordinates incomplete or duplicate"
            )
        outcomes: list[EpisodeOutcome] = []
        for pair in pairs:
            # The frozen control uses one RNG stream per pair/seed across the
            # four episodes, not a caller-provided per-episode seed.
            policy = RandomControl(
                policy_seed=seed,
                pair_binding=pair.private_ref,
            )
            for episode_index in range(4):
                outcomes.append(
                    _control_record(
                        record=coordinates[(pair.pair_index, episode_index)],
                        pair=pair,
                        episode_index=episode_index,
                        expected_policy=policy,
                        expected_label="random",
                        expected_seed=seed,
                    )
                )
        random_outcomes[seed] = tuple(outcomes)
    raw = {
        "reactive_outcomes": [asdict(item) for item in reactive],
        "random_outcomes": {
            str(seed): [asdict(item) for item in rows]
            for seed, rows in sorted(random_outcomes.items())
        },
        "caller_outcomes_accepted": False,
        "policy_actions_reexecuted": True,
    }
    return tuple(reactive), random_outcomes, raw


def render_human_exemplar(
    *,
    candidate_support: Sequence[EpisodeOutcome],
    episodes: Sequence[Mapping[str, Any]],
    parent_evidence: Mapping[Any, Mapping[str, Any]],
) -> dict[str, Any]:
    """Render the frozen best-efficiency support episode without private truth."""

    pair_index, episode_index = select_human_exemplar(candidate_support)
    ordinal = pair_index * 4 + episode_index
    records = _episode_records(episodes)
    evidence = _normalized_parent_evidence(parent_evidence)
    record = records.get(ordinal)
    parent = evidence.get(ordinal)
    if record is None or parent is None:
        raise CapabilityVerificationError("selected exemplar evidence is absent")
    request = record["request"]
    call_log = _primary_call_log(
        parent,
        ordinal=ordinal,
        worker_result=record["worker_result"],
    )
    rows = _environment_call_rows(call_log)
    steps: list[dict[str, Any]] = []
    current_observation: dict[str, Any] | None = None
    current_actions: list[dict[str, Any]] | None = None
    for row in rows:
        if row["operation"] == "observe":
            current_observation = copy.deepcopy(row["result"])
        elif row["operation"] == "valid_actions":
            current_actions = copy.deepcopy(row["result"])
        elif row["operation"] == "step":
            if current_observation is None or current_actions is None:
                raise CapabilityVerificationError(
                    "exemplar parent log is not ordered"
                )
            steps.append(
                {
                    "step_index": len(steps),
                    "before_observation": current_observation,
                    "valid_actions": current_actions,
                    "selected_action": _step_action(row),
                    "after_observation": copy.deepcopy(
                        row["result"]["observation"]
                    ),
                    "success": row["result"]["success"],
                }
            )
            current_observation = None
            current_actions = None
    return {
        "schema_version": EXEMPLAR_SCHEMA,
        "selection": "minimum_regret_then_steps_then_coordinates",
        "pair_index": pair_index,
        "episode_index": episode_index,
        "ordinal": ordinal,
        "public_request": {
            "goal_ir": copy.deepcopy(request["goal_ir"]),
            "environment_spec": copy.deepcopy(request["environment_spec"]),
        },
        "steps": steps,
        "stop": copy.deepcopy(rows[-1]["result"]),
        "private_oracle_fields_included": False,
    }


def verify_capability_evidence(
    *,
    pairs: Sequence[CapabilityPair],
    episodes: Sequence[Mapping[str, Any]],
    parent_evidence: Mapping[Any, Mapping[str, Any]],
    controls: Mapping[str, Any],
    hard_gates: Mapping[str, bool],
    preregistration: Mapping[str, Any] = FROZEN_PREREGISTRATION,
) -> CapabilityVerificationResult:
    """Independently derive semantic evidence, controls, metrics, and verdict."""

    findings: list[str] = []
    raw: dict[str, Any] = {
        "schema_version": VERIFICATION_SCHEMA,
        "derivation_complete": False,
        "findings": [],
        "aggregate_metrics": None,
        "verdict": None,
    }
    try:
        if (
            len(pairs) != EXPECTED_PAIR_COUNT
            or [item.pair_index for item in pairs]
            != list(range(EXPECTED_PAIR_COUNT))
        ):
            raise CapabilityVerificationError(
                "sealed pair census is not exact contiguous 64"
            )
        if (
            type(hard_gates) is not dict
            or set(hard_gates) != set(REQUIRED_HARD_GATES)
            or any(type(value) is not bool for value in hard_gates.values())
        ):
            raise CapabilityVerificationError("hard-gate census/value mismatch")
        records = _episode_records(episodes)
        parent = _normalized_parent_evidence(parent_evidence)
        expected_ordinals = set(range(EXPECTED_EPISODE_COUNT))
        if (
            len(episodes) != EXPECTED_EPISODE_COUNT
            or set(records) != expected_ordinals
            or set(parent) != expected_ordinals
        ):
            raise CapabilityVerificationError(
                "candidate/parent episode census is not exact 1024"
            )

        support_outcomes: list[EpisodeOutcome] = []
        target: dict[str, list[EpisodeOutcome]] = {
            arm: [] for arm in TARGET_ARMS
        }
        hybrid_by_ordinal: dict[int, dict[str, Any]] = {}
        candidate_episode_raw: list[dict[str, Any]] = []
        rows = candidate_schedule_rows()
        for expected in rows:
            ordinal = expected["ordinal"]
            record = records[ordinal]
            _check_candidate_coordinate(record, expected)
            pair = pairs[expected["pair_index"]]
            environment = (
                pair.source
                if expected["phase"] == "support"
                else pair.target
            )
            index = expected["episode_index"]
            call_log = _primary_call_log(
                parent[ordinal],
                ordinal=ordinal,
                worker_result=record["worker_result"],
            )
            rebuilt = reconstruct_episode_outcome(
                pair_index=pair.pair_index,
                episode_index=index,
                environment=environment,
                call_log=call_log,
            )
            hybrid = _hybrid_trace(
                record["worker_result"],
                rebuilt.parent_steps,
            )
            hybrid_by_ordinal[ordinal] = hybrid
            if expected["phase"] == "support":
                support_outcomes.append(rebuilt.outcome)
            else:
                target[expected["arm"]].append(rebuilt.outcome)
            candidate_episode_raw.append(
                {
                    "ordinal": ordinal,
                    "phase": expected["phase"],
                    "pair_index": pair.pair_index,
                    "arm": expected["arm"],
                    "episode_index": index,
                    "outcome": asdict(rebuilt.outcome),
                    "parent_call_log_sha256": canonical_digest(call_log),
                    "hybrid_trace_sha256": canonical_digest(hybrid),
                    "candidate_success_claim_accepted": False,
                }
            )

        support_bindings: dict[int, Mapping[str, Any]] = {}
        support_traces: dict[int, list[dict[str, Any]]] = {}
        support_reports: list[dict[str, Any]] = []
        for pair in pairs:
            traces = [
                hybrid_by_ordinal[pair.pair_index * 4 + episode_index]
                for episode_index in range(4)
            ]
            support_traces[pair.pair_index] = traces
            report = semantics.build_support_memory_binding(
                pair_index=pair.pair_index,
                traces=traces,
            )
            if report.get("passed") is not True or not isinstance(
                report.get("binding"), Mapping
            ):
                local = report.get("findings", ["support_binding_failed"])
                findings.extend(
                    f"pair_{pair.pair_index}:support:{item}" for item in local
                )
            else:
                support_bindings[pair.pair_index] = copy.deepcopy(
                    report["binding"]
                )
            support_reports.append(
                {
                    "pair_index": pair.pair_index,
                    "passed": report.get("passed") is True,
                    "findings": copy.deepcopy(report.get("findings", [])),
                    "binding_digest": (
                        report["binding"].get("binding_digest")
                        if isinstance(report.get("binding"), Mapping)
                        else None
                    ),
                }
            )
        if len(support_bindings) != EXPECTED_PAIR_COUNT:
            raise CapabilityVerificationError(
                "support memory binding census is incomplete: "
                + ";".join(findings[:20])
            )

        target_binding_reports: list[dict[str, Any]] = []
        for expected in rows[256:]:
            ordinal = expected["ordinal"]
            record = records[ordinal]
            report = semantics.verify_target_memory_binding(
                actual_memory_before=record["worker_result"]["memory_before"],
                arm=expected["arm"],
                pair_index=expected["pair_index"],
                support_bindings=support_bindings,
                pair_count=EXPECTED_PAIR_COUNT,
            )
            if report.get("passed") is not True:
                findings.extend(
                    f"ordinal_{ordinal}:target_memory:{item}"
                    for item in report.get("findings", [])
                )
            target_binding_reports.append(
                {
                    "ordinal": ordinal,
                    "arm": expected["arm"],
                    "pair_index": expected["pair_index"],
                    "passed": report.get("passed") is True,
                    "findings": copy.deepcopy(report.get("findings", [])),
                    "actual_memory_before_sha256": canonical_digest(
                        record["worker_result"]["memory_before"]
                    ),
                }
            )

        rule_evidence: list[PairRuleEvidence] = []
        rule_reports: list[dict[str, Any]] = []
        for pair in pairs:
            evidence, report, local_findings = _pair_rule_evidence(
                pair=pair,
                traces=support_traces[pair.pair_index],
                support_binding=support_bindings[pair.pair_index],
                preregistration=preregistration,
            )
            rule_evidence.append(evidence)
            rule_reports.append(report)
            findings.extend(
                f"pair_{pair.pair_index}:{item}" for item in local_findings
            )

        reactive, random_outcomes, control_raw = reconstruct_control_outcomes(
            pairs=pairs,
            controls=controls,
            preregistration=preregistration,
        )
        raw.update(
            {
                "candidate_episode_census": len(candidate_episode_raw),
                "candidate_episodes": candidate_episode_raw,
                "support_bindings": support_reports,
                "target_memory_bindings": target_binding_reports,
                "rule_evidence": rule_reports,
                "controls": control_raw,
            }
        )
        if findings:
            # Semantic integrity failures are evidence failures, not ordinary
            # metric misses.  Retaining complete_lineage would let malformed
            # candidate bytes turn into a capability claim.
            effective_gates = dict(hard_gates)
            effective_gates["complete_lineage"] = False
        else:
            effective_gates = dict(hard_gates)
        metrics = derive_capability_metrics(
            candidate_support=support_outcomes,
            reactive_support=reactive,
            random_support=random_outcomes,
            target_outcomes={
                arm: tuple(target[arm]) for arm in TARGET_ARMS
            },
            rule_evidence=rule_evidence,
            hard_gates=effective_gates,
            preregistration=preregistration,
        )
        exemplar = render_human_exemplar(
            candidate_support=support_outcomes,
            episodes=episodes,
            parent_evidence=parent_evidence,
        )
        raw["derivation_complete"] = True
        raw["findings"] = sorted(set(findings))
        return CapabilityVerificationResult(
            derivation_complete=True,
            findings=tuple(raw["findings"]),
            candidate_support=tuple(support_outcomes),
            target_outcomes={
                arm: tuple(target[arm]) for arm in TARGET_ARMS
            },
            reactive_support=reactive,
            random_support=random_outcomes,
            rule_evidence=tuple(rule_evidence),
            support_bindings=support_bindings,
            raw_evidence=raw,
            metrics=metrics,
            exemplar=exemplar,
        )
    except Exception as exc:
        # This is the deliberate terminal boundary.  A malformed or incomplete
        # one-shot artifact must become CAPABILITY_RED evidence, never an
        # unclassified evaluator crash and never a retry opportunity.
        if isinstance(exc, CapabilityVerificationError):
            message = str(exc)
        else:
            message = f"{type(exc).__name__}:{exc}"
        findings.append(f"independent_derivation:{message}")
        raw["findings"] = sorted(set(findings))
        return _empty_result(findings, hard_gates, raw_evidence=raw)


__all__ = [
    "CapabilityVerificationError",
    "CapabilityVerificationResult",
    "EXPECTED_EPISODE_COUNT",
    "VERIFICATION_SCHEMA",
    "reconstruct_control_outcomes",
    "reconstruct_episode_outcome",
    "render_human_exemplar",
    "verify_capability_evidence",
]
