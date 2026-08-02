from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import gwip_capability_gates as gates
from scripts.gwip_capability_episode_runner import (
    census_runtime_dependency_sources,
    materialized_runtime_dependencies,
)
from scripts.gwip_capability_harness import (
    REQUIRED_HARD_GATES,
    canonical_digest,
)


def _log(*, steps: int = 2) -> list[dict]:
    rows: list[dict] = [{"operation": "reset", "result": {"reset": True}}]
    for index in range(steps):
        rows.extend(
            [
                {
                    "operation": "observe",
                    "result": {"value": index % 7},
                },
                {
                    "operation": "valid_actions",
                    "result": [{"action_id": "a", "payload": {}}],
                },
                {
                    "operation": "step",
                    "step_index": index,
                    "action_id": "a",
                    "result": {
                        "observation": {"value": (index + 1) % 7},
                        "terminal": False,
                        "success": False,
                        "stop_reason": None,
                    },
                },
            ]
        )
    rows.extend(
        [
            {"operation": "observe", "result": {"value": steps % 7}},
            {
                "operation": "valid_actions",
                "result": [{"action_id": "a", "payload": {}}],
            },
            {
                "operation": "stop",
                "result": {
                    "stopped": True,
                    "reason": "fixture_stop",
                    "steps": steps,
                    "success": False,
                },
            },
        ]
    )
    return rows


def _direct_stop_log(
    *,
    steps: int = 1,
    terminal: bool,
    success: bool,
    stop_reason: str | None = None,
) -> list[dict]:
    rows = _log(steps=steps)
    rows = rows[:-3] + [rows[-1]]
    resolved_stop_reason = stop_reason or (
        "goal_reached"
        if success
        else "environment_terminal"
        if terminal
        else "environment_failure:RuntimeError"
    )
    rows[-2]["result"].update(
        {
            "terminal": terminal,
            "success": success,
            "stop_reason": resolved_stop_reason if terminal or success else None,
        }
    )
    rows[-1]["result"].update(
        {
            "reason": resolved_stop_reason,
            "success": success,
        }
    )
    return rows


def _stop_after_observe_log(*, reason: str) -> list[dict]:
    return [
        {"operation": "reset", "result": {"reset": True}},
        {"operation": "observe", "result": {"value": 0}},
        {
            "operation": "stop",
            "result": {
                "stopped": True,
                "reason": reason,
                "steps": 0,
                "success": False,
            },
        },
    ]


def _stop_after_reset_log(*, reason: str) -> list[dict]:
    return [
        {"operation": "reset", "result": {"reset": True}},
        {
            "operation": "stop",
            "result": {
                "stopped": True,
                "reason": reason,
                "steps": 0,
                "success": False,
            },
        },
    ]


def _stop_after_valid_actions_log(*, reason: str) -> list[dict]:
    rows = _log(steps=0)
    if reason == "no_valid_actions":
        rows[-2]["result"] = []
    rows[-1]["result"]["reason"] = reason
    return rows


def _dummy_inputs(tmp_path: Path) -> gates.CapabilityGateInputs:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    repository = tmp_path / "repository"
    repository.mkdir()
    return gates.CapabilityGateInputs(
        schedule={},
        episodes=[],
        parent_evidence={},
        candidate_root=candidate,
        candidate_archive_binding={},
        frozen_source_binding={},
        seed_manifest_audit={},
        budget_probe={},
        repository_root=repository,
        production=False,
    )


def test_parent_call_order_reconstructs_and_rejects_post_stop() -> None:
    accepted = gates.audit_environment_call_log(_log(), step_budget=11)
    assert accepted == {
        "passed": True,
        "findings": [],
        "executed_steps": 2,
        "stop_count": 1,
    }

    forged = _log()
    forged.append({"operation": "step", "step_index": 2, "action_id": "a"})
    rejected = gates.audit_environment_call_log(forged, step_budget=11)
    assert rejected["passed"] is False
    assert "row_10:call_after_stop" in rejected["findings"]


def test_parent_call_order_accepts_terminal_step_followed_by_stop() -> None:
    log = _direct_stop_log(terminal=True, success=True)
    assert gates.audit_environment_call_log(log, step_budget=24) == {
        "passed": True,
        "findings": [],
        "executed_steps": 1,
        "stop_count": 1,
    }


def test_parent_call_order_accepts_success_step_followed_by_stop() -> None:
    log = _direct_stop_log(terminal=False, success=True)
    assert gates.audit_environment_call_log(log, step_budget=24)["passed"] is True


def test_parent_call_order_accepts_environment_terminal_followed_by_stop() -> None:
    log = _direct_stop_log(terminal=True, success=False)
    assert gates.audit_environment_call_log(log, step_budget=24)["passed"] is True


def test_v3_bug_reproduction_accepts_budget_denial_after_observe_and_actions() -> None:
    """The sealed candidate checks the next proposal before denying step 25."""

    log = _log(steps=24)
    result = gates.audit_environment_call_log(log, step_budget=24)
    assert result == {
        "passed": True,
        "findings": [],
        "executed_steps": 24,
        "stop_count": 1,
    }


@pytest.mark.parametrize(
    "reason",
    [
        "policy_abstained",
        "no_valid_actions",
        "proposal_not_in_evaluator_valid_set",
        "run_lease_authorization_witness_invalid",
        "run_lease_authorization_binding_mismatch",
        "run_lease_denied",
    ],
)
def test_parent_call_order_accepts_normal_stop_after_valid_actions(
    reason: str,
) -> None:
    result = gates.audit_environment_call_log(
        _stop_after_valid_actions_log(reason=reason),
        step_budget=24,
    )
    assert result["passed"] is True


@pytest.mark.parametrize(
    "reason",
    ["operator_stop_requested", "post_observation_mismatch"],
)
def test_parent_call_order_accepts_normal_stop_after_observe(
    reason: str,
) -> None:
    result = gates.audit_environment_call_log(
        _stop_after_observe_log(reason=reason),
        step_budget=24,
    )
    assert result["passed"] is True


def test_parent_call_order_accepts_finally_stop_after_reset_failure() -> None:
    result = gates.audit_environment_call_log(
        _stop_after_reset_log(reason="environment_failure:RuntimeError"),
        step_budget=24,
    )
    assert result["passed"] is True


def test_parent_call_order_accepts_finally_stop_after_nonterminal_step() -> None:
    log = _direct_stop_log(
        terminal=False,
        success=False,
        stop_reason="environment_failure:RuntimeError",
    )
    result = gates.audit_environment_call_log(log, step_budget=24)
    assert result["passed"] is True


@pytest.mark.parametrize(
    "log",
    [
        _stop_after_reset_log(reason="environment_failure:RuntimeError"),
        _stop_after_observe_log(reason="environment_failure:RuntimeError"),
        _stop_after_valid_actions_log(
            reason="environment_failure:RuntimeError"
        ),
    ],
)
def test_parent_call_order_accepts_finally_stop_from_every_live_state(
    log: list[dict],
) -> None:
    assert gates.audit_environment_call_log(log, step_budget=24)["passed"] is True


def test_parent_call_order_rejects_activity_after_terminal_step() -> None:
    log = _direct_stop_log(terminal=True, success=True)
    log.insert(-1, {"operation": "observe", "result": {"value": 1}})
    result = gates.audit_environment_call_log(log, step_budget=24)
    assert result["passed"] is False
    assert (
        "row_4:terminal_step_not_followed_by_stop"
        in result["findings"]
    )


def test_parent_call_order_accepts_direct_stop_at_exact_budget() -> None:
    log = _direct_stop_log(
        steps=24,
        terminal=False,
        success=False,
        stop_reason="step_budget_exhausted",
    )
    result = gates.audit_environment_call_log(log, step_budget=24)
    assert result == {
        "passed": True,
        "findings": [],
        "executed_steps": 24,
        "stop_count": 1,
    }


def test_parent_call_order_enforces_budget_without_pass_flag() -> None:
    result = gates.audit_environment_call_log(_log(steps=12), step_budget=11)
    assert result["passed"] is False
    assert result["executed_steps"] == 12
    assert "step_budget_exceeded" in result["findings"]


def test_complete_lineage_reports_full_failure_count_with_bounded_ordinals() -> None:
    cycle = {
        ordinal: {"passed": ordinal >= 95}
        for ordinal in range(100)
    }
    shards = {
        ordinal: {"passed": True}
        for ordinal in range(100)
    }
    evaluator = SimpleNamespace(
        _ordinal_findings=lambda: [],
        _primary_cycle_reports=lambda: cycle,
        _shard_reports=lambda: shards,
        _failed_ordinals=gates._GateEvaluator._failed_ordinals,  # type: ignore[attr-defined]
        _failure_count=gates._GateEvaluator._failure_count,  # type: ignore[attr-defined]
        _episode_by_ordinal={},
        parent={},
        rows={},
        _memory_lineage_findings=lambda: [],
        inputs=SimpleNamespace(
            seed_manifest_audit={
                "nonoverlap_audit": {"passed": True},
                "candidate_domain_audit": {"passed": True},
                "candidate_restricted_diff": {"passed": True},
            },
            support_bindings=None,
            semantic_analysis=None,
            attempted_ordinals=[],
        ),
        _harness_source_receipts_valid=lambda: True,
        expected_count=100,
    )
    result = gates._GateEvaluator.complete_lineage(evaluator)  # type: ignore[arg-type,attr-defined]
    assert "lineage_cycle_failed:95" in result["evidence"]["findings"]
    assert len(evaluator._failed_ordinals(cycle)) == 64


def test_invalid_inputs_fail_all_twelve_gates_closed(tmp_path: Path) -> None:
    result = gates.evaluate_hard_gates(_dummy_inputs(tmp_path))
    assert tuple(result) == REQUIRED_HARD_GATES
    assert all(item["passed"] is False for item in result.values())
    assert all(
        item["evidence"]["input_validation_failed"] is True
        for item in result.values()
    )


def test_production_rejects_runtime_dependency_binding_not_sealed_by_seed(
    tmp_path: Path,
) -> None:
    host_binding = census_runtime_dependency_sources(
        repository_root=Path(__file__).resolve().parents[2]
    )
    forged_seed_binding = copy.deepcopy(host_binding)
    forged_seed_binding["files"][0]["sha256"] = "0" * 64
    forged_seed_binding["tree_sha256"] = canonical_digest(
        forged_seed_binding["files"]
    )
    with materialized_runtime_dependencies(
        host_binding,
        repository_root=Path(__file__).resolve().parents[2],
    ) as (dependency_root, materialized_binding):
        inputs = replace(
            _dummy_inputs(tmp_path),
            production=True,
            runtime_dependency_root=dependency_root,
            runtime_dependency_binding=materialized_binding,
            seed_manifest_audit={
                "runtime_dependency_binding": forged_seed_binding,
            },
        )
        with pytest.raises(
            gates.CapabilityGateError,
            match="runtime dependency binding differs from seed S",
        ):
            gates._GateEvaluator(inputs)  # type: ignore[attr-defined]


def test_registry_adapter_snapshots_provider_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        name: {
            "passed": True,
            "evidence": {
                "schema_version": gates.GATE_EVIDENCE_SCHEMA,
                "gate": name,
                "findings": [],
            },
        }
        for name in REQUIRED_HARD_GATES
    }
    calls: list[dict] = []

    def provider(context: dict) -> gates.CapabilityGateInputs:
        calls.append(context)
        return _dummy_inputs(tmp_path)

    monkeypatch.setattr(
        gates,
        "evaluate_hard_gates",
        lambda _inputs: expected,
    )
    verifiers = gates.make_gate_verifiers(provider)
    context = {
        "schedule_sha256": "a" * 64,
        "attempted_ordinals": [0],
        "episodes": [{"ordinal": 0}],
        "source_before": {"x": 1},
        "source_after": {"x": 1},
    }
    assert set(verifiers) == set(REQUIRED_HARD_GATES)
    assert verifiers[REQUIRED_HARD_GATES[0]](context)["passed"] is True
    assert verifiers[REQUIRED_HARD_GATES[-1]](context)["passed"] is True
    assert len(calls) == 1


def test_registry_adapter_rejects_context_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gates,
        "evaluate_hard_gates",
        lambda _inputs: {
            name: {"passed": True, "evidence": {"findings": []}}
            for name in REQUIRED_HARD_GATES
        },
    )
    verifiers = gates.make_gate_verifiers(
        lambda _context: _dummy_inputs(tmp_path)
    )
    base = {
        "schedule_sha256": "b" * 64,
        "attempted_ordinals": [0],
        "episodes": [{"ordinal": 0}],
        "source_before": {},
        "source_after": {},
    }
    assert verifiers[REQUIRED_HARD_GATES[0]](base)["passed"] is True
    changed = {**base, "attempted_ordinals": [0, 1]}
    rejected = verifiers[REQUIRED_HARD_GATES[1]](changed)
    assert rejected["passed"] is False
    assert rejected["evidence"]["adapter_fail_closed"] is True


def test_parent_evidence_numeric_alias_cannot_duplicate() -> None:
    with pytest.raises(gates.CapabilityGateError):
        gates._normalize_parent_evidence(  # type: ignore[attr-defined]
            {1: {"status": "complete"}, "01": {"status": "complete"}}
        )


def test_fixed_evaluator_source_census_includes_runner_gates_and_verifier() -> None:
    assert len(gates._EVALUATOR_SOURCE_PATHS) == 10  # type: ignore[attr-defined]
    assert {
        "scripts/gwip_capability_episode_runner.py",
        "scripts/gwip_capability_gates.py",
        "scripts/gwip_capability_verifier.py",
    } <= set(gates._EVALUATOR_SOURCE_PATHS)  # type: ignore[attr-defined]
