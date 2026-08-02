"""Independent hard-gate evaluation for the GWIP capability pilot.

The capability worker and the execution harness intentionally emit many
useful *claims*.  None of those claims is authority here.  This module
re-opens evaluator-owned environment logs, authority ledgers, source trees,
and write-once shards and reconstructs all twelve preregistered hard gates.

The production entry point is :func:`evaluate_hard_gates`.  The small
``make_*`` adapters exist only because :class:`IndependentGateRegistry`
expects one callback per gate while most expensive evidence (notably cycle
verification and durable RunLease reopening) should be computed once.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import threading
from typing import Any, Callable, Mapping, Sequence

from scripts import gwip_mechanism_eval as mechanism
from scripts.gwip_capability_cycle_verify import (
    reseal_worker_owned_semantic_digest,
    verify_capability_trace,
)
from scripts.gwip_capability_harness import (
    EXACT_WORKER_COUNT,
    FINAL_PAIR_COUNT,
    FINISH_TO_SEAL_MAX_SECONDS,
    FORGERY_HOOK_PATHS,
    ISSUE_TO_ACTIVATION_MAX_SECONDS,
    REQUIRED_HARD_GATES,
    STEP_BUDGET,
    TOTAL_LEASE_PATH_MAX_SECONDS,
    WORKER_TIMEOUT_SECONDS,
    IndependentGateRegistry,
    _lease_input_manifest_digest,
    apply_forgery_hook,
    canonical_digest,
    validate_semantic_schedule,
    validate_source_binding,
    validate_worker_request,
    validate_worker_result,
)
from scripts.gwip_capability_episode_runner import (
    APPROVED_RUNTIME_DEPENDENCIES,
    bind_runtime_dependency_root,
    validate_runtime_dependency_binding,
)


# ``RunLeaseBoundaryConfig`` is deliberately imported from the production
# authority package, not accepted from a harness object.
from packages.autonomy_envelope.run_lease import (  # noqa: E402
    GENERAL_INTERACTION_RUNNER_ID,
    RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION,
    RUN_LEASE_ACTIVE_RELATIVE_PATH,
    RUN_LEASE_CLAIMS_RELATIVE_PATH,
    RUN_LEASE_NONCE_CLAIM_SCHEMA_VERSION,
    RUN_LEASE_PURPOSE,
    RUN_LEASE_SCHEMA_VERSION,
    RunLeaseBoundaryConfig,
    RunLeaseStore,
    verify_run_lease,
)
from packages.autonomy_envelope.operator_trust import SIGNATURE_FIELD  # noqa: E402


GATE_EVIDENCE_SCHEMA = "atanor.gwip-capability-independent-gates.v1"
EXPECTED_CANDIDATE_EPISODES = 1_024
EXPECTED_ENVIRONMENT_SESSIONS = (
    "primary",
    "structural_reexecution",
    "determinism_a",
    "determinism_b",
    "fresh_reexecution",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIRECT_CANDIDATE_PATHS = (
    "packages/fusion_loop/interactive.py",
    "packages/fusion_loop/interactive_organs.py",
)
_EVALUATOR_SOURCE_PATHS = (
    "scripts/gwip_capability_design.py",
    "scripts/gwip_capability_semantics.py",
    "scripts/gwip_capability_harness.py",
    "scripts/gwip_capability_cycle_verify.py",
    "scripts/gwip_capability_episode_runner.py",
    "scripts/gwip_capability_gates.py",
    "scripts/gwip_capability_verifier.py",
    "scripts/gwip_capability_worker.py",
    "scripts/gwip_capability_eval.py",
    "scripts/gwip_mechanism_eval.py",
)
_APPLICATION_PROBES = frozenset(
    {
        "child_process_blocked",
        "native_child_process_blocked",
        "native_library_loading_blocked",
        "native_file_access_blocked",
        "nonledger_write_blocked",
        "evaluator_source_read_blocked",
        "seed_manifest_read_blocked",
        "evaluator_workspace_enumeration_blocked",
        "system_site_source_read_blocked",
        "system_site_extension_load_blocked",
        "evaluator_main_hidden",
        "runtime_cwd_isolated",
        "sensitive_environment_scrubbed",
    }
)
_NETWORK_PROBES = frozenset(
    {
        "external_network_blocked",
        "udp_sendto_blocked",
        "dns_resolution_blocked",
    }
)
_AUX_AUTHORITY_EVIDENCE = {
    "production_authority": False,
    "worker_claim_only": True,
}
_MAX_FINDINGS = 64


class CapabilityGateError(ValueError):
    """An evaluator-owned gate input is malformed or incomplete."""


@dataclass(frozen=True)
class CapabilityGateInputs:
    """All non-worker evidence needed to recompute the twelve hard gates.

    ``attempted_ordinals`` and the two harness source receipts are required in
    production; they are optional only for bounded fixture tests.
    ``semantic_analysis`` and ``support_bindings`` are optional because the
    harness evaluates gates immediately after execution, before the final
    capability scorer has necessarily materialized its semantic report.  If
    supplied, they are checked and bound into ``complete_lineage``.

    ``production=False`` is a focused-test seam.  It cannot pass through a
    production semantic schedule because the schedule's fixture marker and
    this flag must agree.
    """

    schedule: Mapping[str, Any]
    episodes: Sequence[Mapping[str, Any]]
    parent_evidence: Mapping[int | str, Mapping[str, Any]]
    candidate_root: Path
    candidate_archive_binding: Mapping[str, Any]
    frozen_source_binding: Mapping[str, Any]
    seed_manifest_audit: Mapping[str, Any]
    budget_probe: Mapping[str, Any]
    repository_root: Path
    attempted_ordinals: Sequence[int] | None = None
    harness_source_before: Mapping[str, Any] | None = None
    harness_source_after: Mapping[str, Any] | None = None
    semantic_analysis: Mapping[str, Any] | None = None
    support_bindings: Mapping[int, Mapping[str, Any]] | None = None
    runtime_dependency_root: Path | None = None
    runtime_dependency_binding: Mapping[str, Any] | None = None
    production: bool = True


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _bounded_findings(findings: Sequence[str]) -> list[str]:
    return sorted(set(str(item) for item in findings))[:_MAX_FINDINGS]


def _surface(
    *,
    passed: bool,
    findings: Sequence[str] = (),
    **evidence: Any,
) -> dict[str, Any]:
    bounded = _bounded_findings(findings)
    body = {
        "schema_version": GATE_EVIDENCE_SCHEMA,
        "findings": bounded,
        **copy.deepcopy(evidence),
    }
    return {"passed": bool(passed) and not bounded, "evidence": body}


def _safe_surface(
    name: str,
    callback: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        raw = callback()
        if (
            type(raw) is not dict
            or raw.get("passed") not in {True, False}
            or type(raw.get("evidence")) is not dict
        ):
            raise CapabilityGateError(
                f"{name} verifier returned a malformed surface"
            )
        return copy.deepcopy(dict(raw))
    except Exception as exc:
        return _surface(
            passed=False,
            findings=[
                f"independent_verifier_exception:{type(exc).__name__}:{exc}"
            ],
            gate=name,
            exception_fail_closed=True,
        )


def _normalize_parent_evidence(
    value: Mapping[int | str, Mapping[str, Any]],
) -> dict[int, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise CapabilityGateError("parent evidence must be a mapping")
    output: dict[int, dict[str, Any]] = {}
    for raw_key, raw_value in value.items():
        if type(raw_key) is int:
            key = raw_key
        elif type(raw_key) is str and raw_key.isdigit():
            key = int(raw_key)
        else:
            raise CapabilityGateError("parent evidence ordinal is invalid")
        if key in output or type(raw_value) is not dict:
            raise CapabilityGateError(
                "parent evidence ordinal repeats or has a non-object value"
            )
        output[key] = copy.deepcopy(dict(raw_value))
    return output


def _strict_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()

    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in rows:
            if key in output:
                raise CapabilityGateError(
                    f"duplicate key in {path.name}: {key}"
                )
            output[key] = value
        return output

    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            CapabilityGateError(f"non-finite JSON token: {token}")
        ),
    )
    if type(value) is not dict:
        raise CapabilityGateError(f"{path.name} is not an object")
    return value, raw


def _utc_second(value: Any) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    return parsed


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _candidate_manifest(
    candidate_root: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    root = Path(candidate_root).resolve(strict=True)
    repository = Path(repository_root).resolve(strict=True)
    if (
        _path_within(root, repository)
        or root.is_symlink()
        or not (root / "packages").is_dir()
    ):
        raise CapabilityGateError(
            "candidate archive is not an external package tree"
        )
    records: list[dict[str, Any]] = []
    paths = [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]
    for path in paths:
        if path.is_symlink():
            raise CapabilityGateError("candidate archive contains a symlink")
        metadata = path.stat()
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise CapabilityGateError(
                "candidate archive is not recursively read-only"
            )
        if path.is_dir():
            kind = "directory"
            size: int | None = None
            digest: str | None = None
        elif path.is_file():
            kind = "file"
            size = metadata.st_size
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise CapabilityGateError(
                "candidate archive contains a non-file entry"
            )
        records.append(
            {
                "path": (
                    "."
                    if path == root
                    else path.relative_to(root).as_posix()
                ),
                "kind": kind,
                "mode": mode,
                "size_bytes": size,
                "sha256": digest,
            }
        )
    files = [
        {
            "path": row["path"],
            "size_bytes": row["size_bytes"],
            "sha256": row["sha256"],
        }
        for row in records
        if row["kind"] == "file"
    ]
    return {
        "root_path_sha256": hashlib.sha256(
            str(root).encode("utf-8")
        ).hexdigest(),
        "entry_count": len(records),
        "file_count": len(files),
        "metadata_manifest_sha256": canonical_digest(records),
        "content_manifest_sha256": canonical_digest(files),
        "recursively_read_only": True,
        "external_to_repository": True,
    }


def _candidate_file_records(candidate_root: Path) -> list[dict[str, Any]]:
    root = Path(candidate_root).resolve(strict=True)
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    ]


def audit_environment_call_log(
    call_log: Sequence[Mapping[str, Any]],
    *,
    step_budget: int = STEP_BUDGET,
) -> dict[str, Any]:
    """Reconstruct reset/observe/actions/step/stop order from parent rows."""

    findings: list[str] = []
    if (
        isinstance(call_log, (str, bytes))
        or not isinstance(call_log, Sequence)
    ):
        return {
            "passed": False,
            "findings": ["call_log_not_an_array"],
            "executed_steps": 0,
            "stop_count": 0,
        }
    phase = "reset"
    step_index = 0
    stop_count = 0
    for index, raw in enumerate(call_log):
        if type(raw) is not dict:
            findings.append(f"row_{index}:not_an_object")
            continue
        operation = raw.get("operation")
        if phase == "reset":
            if operation != "reset":
                findings.append("first_call_not_reset")
            else:
                phase = "need_observe"
        elif phase == "need_observe":
            if operation == "observe":
                phase = "need_valid_actions"
            elif operation == "stop":
                stop_count += 1
                phase = "done"
            else:
                findings.append(f"row_{index}:observe_order_mismatch")
        elif phase == "need_valid_actions":
            if operation == "valid_actions":
                phase = "after_valid_actions"
            elif operation == "stop":
                stop_count += 1
                phase = "done"
            else:
                findings.append(
                    f"row_{index}:valid_actions_order_mismatch"
                )
        elif phase == "after_valid_actions":
            if operation == "step":
                if raw.get("step_index") != step_index:
                    findings.append(f"row_{index}:step_index_mismatch")
                if type(raw.get("action_id")) is not str or not raw[
                    "action_id"
                ]:
                    findings.append(f"row_{index}:step_action_missing")
                if step_index >= step_budget:
                    findings.append("step_budget_exceeded")
                step_index += 1
                result = raw.get("result")
                terminal = (
                    type(result) is dict
                    and (
                        result.get("terminal") is True
                        or result.get("success") is True
                    )
                )
                phase = "must_stop" if terminal else "need_observe"
            elif operation == "stop":
                stop_count += 1
                phase = "done"
            else:
                findings.append(f"row_{index}:step_or_stop_order_mismatch")
        elif phase == "must_stop":
            if operation == "stop":
                stop_count += 1
                phase = "done"
            else:
                findings.append(
                    f"row_{index}:terminal_step_not_followed_by_stop"
                )
        else:
            findings.append(f"row_{index}:call_after_stop")
        if "result" in raw and raw.get("result_sha256") not in {
            None,
            canonical_digest(raw["result"]),
        }:
            findings.append(f"row_{index}:parent_result_digest_mismatch")
    if phase != "done" or stop_count != 1:
        findings.append("terminal_stop_census_mismatch")
    return {
        "passed": not findings,
        "findings": _bounded_findings(findings),
        "executed_steps": step_index,
        "stop_count": stop_count,
    }


def _normalize_log_for_comparison(
    value: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in value:
        if type(raw) is not dict:
            raise CapabilityGateError("environment log row is not an object")
        output.append(
            {
                key: copy.deepcopy(item)
                for key, item in raw.items()
                if key != "order_index"
            }
        )
    return output


def _auxiliary_authorizations(
    trace: Mapping[str, Any],
) -> list[dict[str, Any]]:
    semantic = trace.get("semantic_trace")
    steps = semantic.get("steps") if type(semantic) is dict else None
    if type(steps) is not list:
        raise CapabilityGateError("auxiliary trace steps are absent")
    output: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if type(step) is not dict or type(step.get("selected_action")) is not str:
            raise CapabilityGateError("auxiliary selected action is absent")
        output.append(
            {
                "action_id": step["selected_action"],
                "step_index": index,
                "granted": True,
                "reason": "auxiliary_reexecution_fixture_granted",
                "authority_kind": "non_authoritative_auxiliary_fixture",
                "operational_evidence": copy.deepcopy(
                    _AUX_AUTHORITY_EVIDENCE
                ),
            }
        )
    return output


def _auxiliary_finish(trace: Mapping[str, Any]) -> dict[str, Any]:
    semantic = trace.get("semantic_trace")
    if type(semantic) is not dict or type(semantic.get("stop_reason")) is not str:
        raise CapabilityGateError("auxiliary stop reason is absent")
    return {
        "finished": True,
        "reason": semantic["stop_reason"],
        "production_authority": False,
    }


class _GateEvaluator:
    def __init__(self, inputs: CapabilityGateInputs) -> None:
        if type(inputs.production) is not bool:
            raise CapabilityGateError("production marker must be boolean")
        self.inputs = inputs
        self.repository_root = Path(inputs.repository_root).resolve(
            strict=True
        )
        self.candidate_root = Path(inputs.candidate_root).resolve(strict=True)
        if (
            inputs.runtime_dependency_root is None
            or inputs.runtime_dependency_binding is None
        ):
            if inputs.production:
                raise CapabilityGateError(
                    "production runtime dependency evidence is absent"
                )
            self.runtime_dependency_root = None
            self.runtime_dependency_binding = None
        else:
            self.runtime_dependency_root = Path(
                inputs.runtime_dependency_root
            ).resolve(strict=True)
            self.runtime_dependency_binding = (
                validate_runtime_dependency_binding(
                    inputs.runtime_dependency_binding
                )
            )
            if (
                _path_within(
                    self.runtime_dependency_root,
                    self.repository_root,
                )
                or _path_within(
                    self.runtime_dependency_root,
                    self.candidate_root,
                )
                or bind_runtime_dependency_root(
                    self.runtime_dependency_root
                )
                != self.runtime_dependency_binding
            ):
                raise CapabilityGateError(
                    "runtime dependency root/binding mismatch"
                )
            for path in [
                self.runtime_dependency_root,
                *self.runtime_dependency_root.rglob("*"),
            ]:
                if path.is_symlink():
                    raise CapabilityGateError(
                        "runtime dependency root contains a symlink"
                    )
                mode = stat.S_IMODE(path.stat().st_mode)
                if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                    raise CapabilityGateError(
                        "runtime dependency root is not recursively read-only"
                    )
            seed_dependency_binding = inputs.seed_manifest_audit.get(
                "runtime_dependency_binding"
            )
            if inputs.production:
                if (
                    type(seed_dependency_binding) is not dict
                    or validate_runtime_dependency_binding(
                        seed_dependency_binding
                    )
                    != self.runtime_dependency_binding
                ):
                    raise CapabilityGateError(
                        "runtime dependency binding differs from seed S"
                    )
            elif (
                seed_dependency_binding is not None
                and seed_dependency_binding
                != self.runtime_dependency_binding
            ):
                raise CapabilityGateError(
                    "fixture runtime dependency binding differs from seed audit"
                )
        self.schedule = validate_semantic_schedule(
            inputs.schedule,
            production=inputs.production,
            repository_root=self.repository_root,
        )
        if bool(self.schedule["fixture_nonproduction"]) == inputs.production:
            raise CapabilityGateError(
                "schedule fixture marker conflicts with production marker"
            )
        self.source_binding = validate_source_binding(
            inputs.frozen_source_binding
        )
        if self.source_binding != self.schedule["source_binding"]:
            raise CapabilityGateError(
                "frozen source binding differs from schedule"
            )
        self.episodes = [copy.deepcopy(dict(item)) for item in inputs.episodes]
        self.parent = _normalize_parent_evidence(inputs.parent_evidence)
        self.rows = {
            int(row["ordinal"]): copy.deepcopy(row)
            for row in self.schedule["rows"]
        }
        self.expected_count = (
            EXPECTED_CANDIDATE_EPISODES
            if inputs.production
            else int(self.schedule["candidate_episode_count"])
        )
        self._episode_by_ordinal: dict[int, dict[str, Any]] = {}
        for episode in self.episodes:
            ordinal = episode.get("ordinal")
            if type(ordinal) is int and ordinal not in self._episode_by_ordinal:
                self._episode_by_ordinal[ordinal] = episode
        self._primary_cycle: dict[int, dict[str, Any]] | None = None
        self._shards: dict[int, dict[str, Any]] | None = None
        self._lease: dict[int, dict[str, Any]] | None = None

    def _ordinal_findings(self) -> list[str]:
        expected = set(range(self.expected_count))
        findings: list[str] = []
        if self.expected_count != self.schedule["candidate_episode_count"]:
            findings.append("production_candidate_episode_count_not_1024")
        for label, actual in (
            ("schedule", set(self.rows)),
            ("episodes", set(self._episode_by_ordinal)),
            ("parent_evidence", set(self.parent)),
        ):
            missing = expected - actual
            extra = actual - expected
            if missing:
                findings.append(
                    f"{label}_missing_ordinals:{len(missing)}"
                )
            if extra:
                findings.append(f"{label}_extra_ordinals:{len(extra)}")
        if len(self.episodes) != len(self._episode_by_ordinal):
            findings.append("episode_ordinal_duplicate_or_invalid")
        attempted = self.inputs.attempted_ordinals
        if attempted is None:
            if self.inputs.production:
                findings.append("attempted_ordinal_census_absent")
        elif (
            isinstance(attempted, (str, bytes))
            or not isinstance(attempted, Sequence)
            or list(attempted) != list(range(self.expected_count))
        ):
            findings.append("attempted_ordinal_census_mismatch")
        return findings

    def _harness_source_receipts_valid(self) -> bool:
        expected = {
            "kind": "full_candidate_evaluator_seed_binding",
            "binding": copy.deepcopy(self.source_binding),
            "binding_sha256": canonical_digest(self.source_binding),
            "fixture_nonproduction": not self.inputs.production,
        }
        before = self.inputs.harness_source_before
        after = self.inputs.harness_source_after
        if before is None or after is None:
            return not self.inputs.production
        return before == expected and after == expected

    def _episode(self, ordinal: int) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._episode_by_ordinal[ordinal], self.parent[ordinal]

    def _primary_cycle_reports(self) -> dict[int, dict[str, Any]]:
        if self._primary_cycle is not None:
            return self._primary_cycle
        reports: dict[int, dict[str, Any]] = {}
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            result = episode.get("worker_result")
            authority = parent.get("authority")
            sessions = parent.get("environment_sessions")
            try:
                if (
                    type(result) is not dict
                    or type(authority) is not dict
                    or type(sessions) is not dict
                    or type(sessions.get("primary")) is not dict
                ):
                    raise CapabilityGateError(
                        "primary independent witnesses are absent"
                    )
                reports[ordinal] = verify_capability_trace(
                    result["trace"],
                    request=episode["request"],
                    environment_log=sessions["primary"]["call_log"],
                    parent_authorizations=authority[
                        "parent_authorizations"
                    ],
                    parent_finish=authority["finish_receipt"],
                )
            except Exception as exc:
                reports[ordinal] = {
                    "passed": False,
                    "findings": [
                        f"cycle_exception:{type(exc).__name__}:{exc}"
                    ],
                    "surfaces": {},
                }
        self._primary_cycle = reports
        return reports

    def _shard_reports(self) -> dict[int, dict[str, Any]]:
        if self._shards is not None:
            return self._shards
        output: dict[int, dict[str, Any]] = {}
        for ordinal, episode in sorted(self._episode_by_ordinal.items()):
            findings: list[str] = []
            shard = episode.get("shard")
            try:
                if type(shard) is not dict:
                    raise CapabilityGateError("shard receipt is absent")
                path = Path(str(shard.get("path"))).resolve(strict=True)
                if _path_within(path, self.repository_root):
                    findings.append("shard_path_inside_repository")
                envelope, raw = _strict_json_object(path)
                body = {
                    key: copy.deepcopy(item)
                    for key, item in envelope.items()
                    if key in {
                        "schema_version",
                        "ordinal",
                        "status",
                        "schedule_sha256",
                        "attempt_sha256",
                        "payload",
                    }
                }
                if (
                    hashlib.sha256(raw).hexdigest()
                    != shard.get("raw_sha256")
                ):
                    findings.append("shard_raw_digest_mismatch")
                if envelope.get("ordinal") != ordinal:
                    findings.append("shard_ordinal_mismatch")
                if envelope.get("status") != "complete":
                    findings.append("shard_not_complete")
                if envelope.get("payload_sha256") != canonical_digest(
                    envelope.get("payload")
                ):
                    findings.append("shard_payload_digest_mismatch")
                if envelope.get(
                    "shard_checksum_sha256"
                ) != canonical_digest(body):
                    findings.append("shard_checksum_mismatch")
                payload = envelope.get("payload")
                if (
                    type(payload) is not dict
                    or payload.get("request") != episode.get("request")
                    or payload.get("worker_result")
                    != episode.get("worker_result")
                    or payload.get(
                        "worker_claims_are_non_authoritative"
                    )
                    is not True
                ):
                    findings.append("shard_payload_episode_mismatch")
                if (
                    shard.get("shard_checksum_sha256")
                    != envelope.get("shard_checksum_sha256")
                ):
                    findings.append("shard_receipt_checksum_mismatch")
            except Exception as exc:
                findings.append(
                    f"shard_exception:{type(exc).__name__}:{exc}"
                )
            output[ordinal] = {
                "passed": not findings,
                "findings": _bounded_findings(findings),
            }
        self._shards = output
        return output

    def _lease_reports(self) -> dict[int, dict[str, Any]]:
        if self._lease is not None:
            return self._lease
        output: dict[int, dict[str, Any]] = {}
        lease_ids: set[str] = set()
        nonces: set[str] = set()
        boundaries: set[str] = set()
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            row = self.rows.get(ordinal)
            findings: list[str] = []
            replay_reason: str | None = None
            try:
                if type(row) is not dict:
                    raise CapabilityGateError("schedule row is absent")
                authority = parent.get("authority")
                if type(authority) is not dict:
                    raise CapabilityGateError("parent authority is absent")
                document = authority.get("document")
                live_context = authority.get("live_context")
                boundary_path = Path(row["boundary_config_path"]).resolve(
                    strict=True
                )
                boundary = RunLeaseBoundaryConfig.from_external_file(
                    boundary_path,
                    repository_root=self.repository_root,
                )
                verified = verify_run_lease(
                    document,
                    trust_root=boundary.trust_root,
                    live_context=live_context,
                )
                signed = boundary.trust_root.verify_document(
                    document,
                    required_purpose=RUN_LEASE_PURPOSE,
                )
                expected_document_fields = {
                    "schema_version",
                    "purpose",
                    "lease_id",
                    "issued_at",
                    "expires_at",
                    "nonce",
                    SIGNATURE_FIELD,
                    *row["live_context"],
                }
                if (
                    signed.ok is not True
                    or signed.reason != "operator_signature_valid"
                    or type(document) is not dict
                    or set(document) != expected_document_fields
                    or document.get("schema_version")
                    != RUN_LEASE_SCHEMA_VERSION
                    or document.get("purpose") != RUN_LEASE_PURPOSE
                    or signed.key_id != boundary.expected_key_id
                ):
                    findings.append(
                        "run_lease_signature_or_schema:"
                        f"{signed.reason}"
                    )
                if (
                    live_context != row["live_context"]
                    or document.get("lease_id") != row["lease_id"]
                    or document.get("nonce") != row["nonce"]
                    or canonical_digest(row)
                    != episode.get("request", {}).get(
                        "schedule_row_sha256"
                    )
                    or row["episode_input_sha256"]
                    != episode.get("request", {}).get(
                        "episode_input_sha256"
                    )
                    or row["live_context"].get("input_manifest_sha256")
                    != _lease_input_manifest_digest(
                        row,
                        seed_manifest_sha256=self.source_binding[
                            "seed_manifest_sha256"
                        ],
                    )
                ):
                    findings.append("run_lease_schedule_binding_mismatch")
                lease_id = str(document.get("lease_id"))
                nonce = str(document.get("nonce"))
                boundary_text = str(boundary_path)
                if lease_id in lease_ids:
                    findings.append("lease_id_reused")
                if nonce in nonces:
                    findings.append("lease_nonce_reused")
                if boundary_text in boundaries:
                    findings.append("lease_boundary_reused")
                lease_ids.add(lease_id)
                nonces.add(nonce)
                boundaries.add(boundary_text)

                activation = authority.get("activation_receipt")
                finish = authority.get("finish_receipt")
                auth_responses = authority.get(
                    "parent_authorization_responses"
                )
                auth_witnesses = authority.get("parent_authorizations")
                sessions = parent.get("environment_sessions")
                primary_log = (
                    sessions.get("primary", {}).get("call_log")
                    if type(sessions) is dict
                    else None
                )
                call_audit = audit_environment_call_log(
                    primary_log if isinstance(primary_log, Sequence) else []
                )
                step_count = call_audit["executed_steps"]
                if (
                    type(activation) is not dict
                    or activation.get("allowed") is not True
                    or activation.get("reason")
                    != "run_lease_activated"
                    or type(finish) is not dict
                    or finish.get("finished") is not True
                    or finish.get("reason") != "run_lease_finished"
                    or type(auth_responses) is not list
                    or type(auth_witnesses) is not list
                    or len(auth_responses) != step_count
                    or len(auth_witnesses) != step_count
                ):
                    findings.append(
                        "run_lease_activation_finish_or_census_mismatch"
                    )
                for index, response in enumerate(auth_responses or []):
                    counters = (
                        response.get("operational_evidence", {}).get(
                            "counters"
                        )
                        if type(response) is dict
                        else None
                    )
                    if (
                        type(response) is not dict
                        or response.get("step_index") != index
                        or response.get("granted") is not True
                        or response.get("authority_kind")
                        != "externally_signed_run_lease"
                        or response.get(
                            "operational_evidence", {}
                        ).get("lease_id_sha256")
                        != canonical_digest(row["lease_id"])
                        or type(counters) is not dict
                        or counters.get("actions") != index + 1
                        or counters.get("cycles") != index + 1
                        or any(
                            counters.get(name) != 0
                            for name in (
                                "external_requests",
                                "external_response_bytes",
                                "scratch_write_bytes",
                                "child_tasks",
                                "concurrent_child_tasks",
                            )
                        )
                    ):
                        findings.append(
                            f"authorization_{index}:direct_authority_mismatch"
                        )
                        break

                store = RunLeaseStore(boundary)
                active_name = (
                    hashlib.sha256(
                        GENERAL_INTERACTION_RUNNER_ID.encode("utf-8")
                    ).hexdigest()
                    + ".json"
                )
                active_path = (
                    boundary.replay_root
                    / RUN_LEASE_ACTIVE_RELATIVE_PATH
                    / active_name
                )
                active_state, _active_raw = _strict_json_object(active_path)
                signature = document[SIGNATURE_FIELD]
                claim_name = (
                    hashlib.sha256(
                        (
                            f"{signature['key_id']}|{document['nonce']}|"
                            f"{boundary.deployment_id}"
                        ).encode("utf-8")
                    ).hexdigest()
                    + ".json"
                )
                claim_path = (
                    boundary.replay_root
                    / RUN_LEASE_CLAIMS_RELATIVE_PATH
                    / claim_name
                )
                claim, _claim_raw = _strict_json_object(claim_path)
                issued_at = _utc_second(document.get("issued_at"))
                expires_at = _utc_second(document.get("expires_at"))
                activated_at = _utc_second(active_state.get("activated_at"))
                finished_at = _utc_second(active_state.get("finished_at"))
                historical_window_valid = (
                    issued_at is not None
                    and expires_at is not None
                    and activated_at is not None
                    and finished_at is not None
                    and issued_at <= activated_at <= finished_at < expires_at
                )
                durable_counters = active_state.get("counters")
                historical_state_valid = (
                    set(active_state)
                    == {
                        "schema_version",
                        "status",
                        "lease_id",
                        "runner_id",
                        "key_id",
                        "payload_sha256",
                        "nonce",
                        "activated_at",
                        "finished_at",
                        "finish_reason",
                        "lease_document",
                        "live_context",
                        "counters",
                        "authorization_count",
                        "last_authorized_at",
                    }
                    and active_state.get("schema_version")
                    == RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION
                    and active_state.get("status") == "finished"
                    and active_state.get("lease_id") == row["lease_id"]
                    and active_state.get("runner_id")
                    == GENERAL_INTERACTION_RUNNER_ID
                    and active_state.get("lease_document") == document
                    and active_state.get("live_context") == live_context
                    and active_state.get("key_id")
                    == signature["key_id"]
                    and active_state.get("payload_sha256")
                    == signature["payload_sha256"]
                    and active_state.get("nonce") == document["nonce"]
                    and active_state.get("finish_reason")
                    == parent["environment_sessions"]["primary"][
                        "stop_reason"
                    ]
                    and active_state.get("authorization_count") == step_count
                    and type(durable_counters) is dict
                    and durable_counters.get("actions") == step_count
                    and durable_counters.get("cycles") == step_count
                    and any(
                        active_state.get(name)
                        for name in ("activated_at", "finished_at")
                    )
                    and (
                        (
                            step_count == 0
                            and active_state.get("last_authorized_at") == ""
                        )
                        or (
                            step_count > 0
                            and _utc_second(
                                active_state.get("last_authorized_at")
                            )
                            is not None
                        )
                    )
                    and historical_window_valid
                )
                durable_claim_valid = (
                    set(claim)
                    == {
                        "schema_version",
                        "key_id",
                        "nonce",
                        "deployment_id",
                        "lease_id",
                        "runner_id",
                        "payload_sha256",
                        "claimed_at",
                    }
                    and claim.get("schema_version")
                    == RUN_LEASE_NONCE_CLAIM_SCHEMA_VERSION
                    and claim.get("key_id") == signature["key_id"]
                    and claim.get("nonce") == document["nonce"]
                    and claim.get("deployment_id")
                    == boundary.deployment_id
                    and claim.get("lease_id") == row["lease_id"]
                    and claim.get("runner_id")
                    == GENERAL_INTERACTION_RUNNER_ID
                    and claim.get("payload_sha256")
                    == signature["payload_sha256"]
                    and claim.get("claimed_at")
                    == active_state.get("activated_at")
                )
                if (
                    not historical_state_valid
                    or not durable_claim_valid
                    or any(
                        durable_counters.get(name) != 0
                        for name in (
                            "external_requests",
                            "external_response_bytes",
                            "scratch_write_bytes",
                            "child_tasks",
                            "concurrent_child_tasks",
                        )
                    )
                ):
                    findings.append("durable_run_lease_ledger_mismatch")
                if verified.ok is True:
                    replay = store.activate(
                        document=document,
                        live_context=live_context,
                    )
                    replay_reason = replay.reason
                    if (
                        replay.allowed is not False
                        or replay.reason != "run_lease_replay"
                    ):
                        findings.append(
                            "durable_run_lease_replay_not_rejected"
                        )
                elif (
                    verified.reason == "run_lease_expired"
                    and historical_state_valid
                    and durable_claim_valid
                ):
                    # The nonce claim remains the independent replay witness
                    # after the short lease window closes.  Requiring the
                    # current-time verifier to return replay here would
                    # incorrectly turn a completed >1h run RED merely because
                    # expiry is checked before the nonce ledger.
                    replay_reason = "run_lease_replay_durable_claim"
                else:
                    findings.append(
                        f"run_lease_context_validation:{verified.reason}"
                    )

                sealed = episode.get("run_lease")
                shard = episode.get("shard")
                if (
                    type(sealed) is not dict
                    or type(shard) is not dict
                    or sealed.get("passed") is not True
                    or sealed.get("ordinal") != ordinal
                    or sealed.get("schedule_row_sha256")
                    != canonical_digest(row)
                    or sealed.get("lease_id_sha256")
                    != canonical_digest(row["lease_id"])
                    or sealed.get("nonce_sha256")
                    != canonical_digest(row["nonce"])
                    or sealed.get("authorization_count") != step_count
                    or sealed.get("shard_sha256")
                    != shard.get("raw_sha256")
                    or sealed.get("activation_reason")
                    != "run_lease_activated"
                    or sealed.get("finish_reason")
                    != "run_lease_finished"
                    or sealed.get("single_use_replay_reason")
                    != "run_lease_replay"
                ):
                    findings.append("harness_run_lease_seal_mismatch")
                for field, maximum in (
                    (
                        "issue_to_activation_seconds",
                        ISSUE_TO_ACTIVATION_MAX_SECONDS,
                    ),
                    ("worker_seconds", WORKER_TIMEOUT_SECONDS),
                    (
                        "finish_to_seal_seconds",
                        FINISH_TO_SEAL_MAX_SECONDS,
                    ),
                    ("total_seconds", TOTAL_LEASE_PATH_MAX_SECONDS),
                ):
                    value = sealed.get(field) if type(sealed) is dict else None
                    if (
                        type(value) not in {int, float}
                        or isinstance(value, bool)
                        or not 0 <= float(value) <= maximum
                    ):
                        findings.append(f"harness_timing_invalid:{field}")
            except Exception as exc:
                findings.append(
                    f"run_lease_exception:{type(exc).__name__}:{exc}"
                )
            output[ordinal] = {
                "passed": not findings,
                "findings": _bounded_findings(findings),
                "replay_reason": replay_reason,
            }
        self._lease = output
        return output

    @staticmethod
    def _failed_ordinals(
        reports: Mapping[int, Mapping[str, Any]],
    ) -> list[int]:
        return [
            ordinal
            for ordinal, report in sorted(reports.items())
            if report.get("passed") is not True
        ][:_MAX_FINDINGS]

    @staticmethod
    def _failure_count(
        reports: Mapping[int, Mapping[str, Any]],
    ) -> int:
        return sum(
            report.get("passed") is not True
            for report in reports.values()
        )

    def call_order_and_stop(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        failed: list[int] = []
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            sessions = parent.get("environment_sessions")
            protocol = parent.get("protocol_order")
            primary_seal = parent.get("primary_seal")
            if (
                type(sessions) is not dict
                or set(sessions) != set(EXPECTED_ENVIRONMENT_SESSIONS)
                or type(protocol) is not list
                or type(primary_seal) is not dict
            ):
                failed.append(ordinal)
                continue
            session_failed = False
            for session_name in EXPECTED_ENVIRONMENT_SESSIONS:
                session = sessions[session_name]
                if type(session) is not dict:
                    session_failed = True
                    break
                audit = audit_environment_call_log(
                    session.get("call_log", []),
                    step_budget=episode.get("request", {}).get(
                        "step_budget", -1
                    ),
                )
                if (
                    audit["passed"] is not True
                    or session.get("stopped") is not True
                    or session.get("step_count")
                    != audit["executed_steps"]
                    or session.get("stop_reason")
                    != session.get("call_log", [])[-1].get("payload", {}).get(
                        "reason"
                    )
                    or session.get("call_log_sha256")
                    != canonical_digest(session.get("call_log"))
                ):
                    session_failed = True
                    break
            primary_index = primary_seal.get("order_index")
            aux_indexes = [
                row.get("index")
                for row in protocol
                if row.get("session")
                in {
                    "structural_reexecution",
                    "determinism_a",
                    "determinism_b",
                    "fresh_reexecution",
                }
            ]
            first_environment_index: dict[str, int] = {}
            primary_result_rows = []
            worker_result_rows = []
            unexpected_authority_sessions = []
            for protocol_row in protocol:
                if type(protocol_row) is not dict:
                    session_failed = True
                    continue
                if protocol_row.get("type") == "environment_request":
                    session_name = protocol_row.get("session")
                    if (
                        session_name in EXPECTED_ENVIRONMENT_SESSIONS
                        and session_name not in first_environment_index
                        and type(protocol_row.get("index")) is int
                    ):
                        first_environment_index[session_name] = protocol_row[
                            "index"
                        ]
                elif protocol_row.get("type") == "primary_result":
                    primary_result_rows.append(protocol_row)
                elif protocol_row.get("type") == "worker_result":
                    worker_result_rows.append(protocol_row)
                elif (
                    protocol_row.get("type") == "authority_request"
                    and protocol_row.get("session") != "authority:primary"
                ):
                    unexpected_authority_sessions.append(
                        protocol_row.get("session")
                    )
            ordered_environment_phases = (
                set(first_environment_index)
                == set(EXPECTED_ENVIRONMENT_SESSIONS)
                and [
                    first_environment_index[name]
                    for name in EXPECTED_ENVIRONMENT_SESSIONS
                ]
                == sorted(first_environment_index.values())
            )
            if (
                session_failed
                or primary_seal.get(
                    "sealed_before_auxiliary_sessions"
                )
                is not True
                or type(primary_index) is not int
                or (aux_indexes and min(aux_indexes) <= primary_index)
                or parent.get("protocol_order_sha256")
                != canonical_digest(protocol)
                or not ordered_environment_phases
                or len(primary_result_rows) != 1
                or primary_result_rows[0].get("index") != primary_index
                or len(worker_result_rows) != 1
                or worker_result_rows[0].get("index") != len(protocol) - 1
                or bool(unexpected_authority_sessions)
                or parent.get("worker_claims_accepted_as_authority")
                is not False
            ):
                failed.append(ordinal)
        if failed:
            findings.append(f"call_order_failed_ordinals:{len(failed)}")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="call_order_and_stop",
            episode_count=len(self._episode_by_ordinal),
            failed_ordinals=failed[:_MAX_FINDINGS],
            all_five_sessions_reconstructed=True,
        )

    def step_budget_and_pre_mutation_denial(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        failed: list[int] = []
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            request = episode.get("request")
            sessions = parent.get("environment_sessions")
            if (
                type(request) is not dict
                or request.get("step_budget") != STEP_BUDGET
                or type(sessions) is not dict
            ):
                failed.append(ordinal)
                continue
            for session in sessions.values():
                audit = audit_environment_call_log(
                    session.get("call_log", [])
                    if type(session) is dict
                    else [],
                    step_budget=STEP_BUDGET,
                )
                if audit["passed"] is not True:
                    failed.append(ordinal)
                    break
        probe = self.inputs.budget_probe
        rows = probe.get("rows") if type(probe) is dict else None
        expected_pairs = FINAL_PAIR_COUNT if self.inputs.production else (
            self.schedule["pair_count"]
        )
        probe_ok = (
            type(rows) is list
            and len(rows) == expected_pairs
            and {
                row.get("pair_index")
                for row in rows
                if type(row) is dict
            }
            == set(range(expected_pairs))
            and all(
                type(row) is dict
                and row.get("rejected") is True
                and row.get("state_unchanged") is True
                and row.get("log_unchanged") is True
                and row.get("executed_step_count") == STEP_BUDGET
                for row in rows
            )
        )
        if failed:
            findings.append(f"step_budget_failed_ordinals:{len(failed)}")
        if not probe_ok:
            findings.append("pre_mutation_budget_probe_failed")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="step_budget_and_pre_mutation_denial",
            failed_ordinals=failed[:_MAX_FINDINGS],
            budget_probe_pair_count=len(rows) if type(rows) is list else 0,
            parent_owned_pre_mutation_probe=True,
        )

    def run_lease_direct_authority(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        reports = self._lease_reports()
        failed = self._failed_ordinals(reports)
        if failed:
            findings.append(f"direct_run_lease_failed_ordinals:{len(failed)}")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="run_lease_direct_authority",
            verified_count=sum(
                report["passed"] is True for report in reports.values()
            ),
            failed_ordinals=failed,
            signature_and_live_context_reopened=True,
            durable_ledger_reopened=True,
        )

    def run_lease_single_use_and_replay_rejection(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        reports = self._lease_reports()
        failed = [
            ordinal
            for ordinal, report in sorted(reports.items())
            if report.get("passed") is not True
            or report.get("replay_reason")
            not in {
                "run_lease_replay",
                "run_lease_replay_durable_claim",
            }
        ]
        if failed:
            findings.append(f"replay_rejection_failed_ordinals:{len(failed)}")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="run_lease_single_use_and_replay_rejection",
            replay_rejected_count=len(reports) - len(failed),
            failed_ordinals=failed[:_MAX_FINDINGS],
            fresh_store_replay_attempted=True,
        )

    def structural_cycle_replay(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        primary = self._primary_cycle_reports()
        failed: list[int] = []
        for ordinal, report in sorted(primary.items()):
            if report.get("passed") is not True:
                failed.append(ordinal)
                continue
            episode, parent = self._episode(ordinal)
            sessions = parent["environment_sessions"]
            authority = parent["authority"]
            structural = verify_capability_trace(
                episode["worker_result"]["trace"],
                request=episode["request"],
                environment_log=sessions["structural_reexecution"][
                    "call_log"
                ],
                parent_authorizations=authority[
                    "parent_authorizations"
                ],
                parent_finish=authority["finish_receipt"],
            )
            if structural.get("passed") is not True:
                failed.append(ordinal)
        if failed:
            findings.append(f"structural_cycle_failed_ordinals:{len(failed)}")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="structural_cycle_replay",
            verified_count=len(primary) - len(failed),
            failed_ordinals=failed[:_MAX_FINDINGS],
            candidate_structural_pass_flags_used=False,
        )

    def semantic_reexecution_determinism(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        failed: list[int] = []
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            try:
                sessions = parent["environment_sessions"]
                claims = episode["worker_result"]["worker_claims"]
                trace_a = claims["candidate_determinism_trace_a"]
                trace_b = claims["candidate_determinism_trace_b"]
                request = copy.deepcopy(episode["request"])
                request["session_id"] = (
                    str(request["session_id"]) + ":determinism"
                )
                report_a = verify_capability_trace(
                    trace_a,
                    request=request,
                    environment_log=sessions["determinism_a"]["call_log"],
                    parent_authorizations=_auxiliary_authorizations(trace_a),
                    parent_finish=_auxiliary_finish(trace_a),
                )
                report_b = verify_capability_trace(
                    trace_b,
                    request=request,
                    environment_log=sessions["determinism_b"]["call_log"],
                    parent_authorizations=_auxiliary_authorizations(trace_b),
                    parent_finish=_auxiliary_finish(trace_b),
                )
                logs_equal = _normalize_log_for_comparison(
                    sessions["determinism_a"]["call_log"]
                ) == _normalize_log_for_comparison(
                    sessions["determinism_b"]["call_log"]
                )
                if (
                    report_a.get("passed") is not True
                    or report_b.get("passed") is not True
                    or not logs_equal
                    or trace_a != trace_b
                ):
                    failed.append(ordinal)
            except Exception:
                failed.append(ordinal)
        if failed:
            findings.append(f"semantic_determinism_failed_ordinals:{len(failed)}")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="semantic_reexecution_determinism",
            verified_trace_pair_count=self.expected_count - len(failed),
            failed_ordinals=failed[:_MAX_FINDINGS],
            full_a_b_traces_independently_verified=True,
            worker_determinism_pass_flag_used=False,
        )

    def fresh_environment_reexecution(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        failed: list[int] = []
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            try:
                sessions = parent["environment_sessions"]
                authority = parent["authority"]
                result = verify_capability_trace(
                    episode["worker_result"]["trace"],
                    request=episode["request"],
                    environment_log=sessions["fresh_reexecution"]["call_log"],
                    parent_authorizations=authority[
                        "parent_authorizations"
                    ],
                    parent_finish=authority["finish_receipt"],
                )
                if (
                    result.get("passed") is not True
                    or _normalize_log_for_comparison(
                        sessions["primary"]["call_log"]
                    )
                    != _normalize_log_for_comparison(
                        sessions["fresh_reexecution"]["call_log"]
                    )
                    or parent.get("environment_object_count")
                    != len(EXPECTED_ENVIRONMENT_SESSIONS)
                ):
                    failed.append(ordinal)
            except Exception:
                failed.append(ordinal)
        if failed:
            findings.append(f"fresh_reexecution_failed_ordinals:{len(failed)}")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="fresh_environment_reexecution",
            verified_count=self.expected_count - len(failed),
            failed_ordinals=failed[:_MAX_FINDINGS],
            fresh_parent_environment_objects_required=True,
            worker_fresh_pass_flag_used=False,
        )

    def _memory_lineage_findings(self) -> list[str]:
        findings: list[str] = []
        support_final: dict[int, dict[str, Any]] = {}
        empty_memories: list[dict[str, Any]] = []
        support_rows: dict[int, list[dict[str, Any]]] = {}
        target_rows: list[dict[str, Any]] = []
        for ordinal, row in sorted(self.rows.items()):
            episode = self._episode_by_ordinal.get(ordinal)
            if episode is None:
                continue
            if row["phase"] == "support":
                support_rows.setdefault(row["pair_index"], []).append(
                    episode
                )
            else:
                target_rows.append(episode)
        for pair_index, episodes in sorted(support_rows.items()):
            prior: dict[str, Any] | None = None
            for index, episode in enumerate(episodes):
                request = episode["request"]
                result = episode["worker_result"]
                before = request["policy_memory"]
                if index == 0:
                    empty_memories.append(copy.deepcopy(before))
                elif before != prior:
                    findings.append(
                        f"support_pair_{pair_index}:memory_chain_mismatch"
                    )
                if result["memory_before"] != before:
                    findings.append(
                        f"support_pair_{pair_index}:result_before_mismatch"
                    )
                prior = copy.deepcopy(result["memory_after"])
            if prior is not None:
                support_final[pair_index] = prior
        if empty_memories and any(
            item != empty_memories[0] for item in empty_memories[1:]
        ):
            findings.append("canonical_empty_memory_not_unique")
        empty = empty_memories[0] if empty_memories else None
        for episode in target_rows:
            ordinal = episode["ordinal"]
            row = self.rows[ordinal]
            actual = episode["request"]["policy_memory"]
            source_pair = row["memory_source_pair_index"]
            expected = empty if source_pair is None else support_final.get(
                source_pair
            )
            if expected is None or actual != expected:
                findings.append(f"target_{ordinal}:memory_source_mismatch")
            if (
                episode["worker_result"]["memory_before"] != actual
                or episode["worker_result"]["memory_after"] != actual
            ):
                findings.append(f"target_{ordinal}:detached_memory_mutated")

        bindings = self.inputs.support_bindings
        if bindings is not None:
            try:
                from scripts.gwip_capability_semantics import (
                    verify_target_memory_binding,
                )

                if set(bindings) != set(range(self.schedule["pair_count"])):
                    findings.append("support_binding_pair_census_mismatch")
                for episode in target_rows:
                    row = self.rows[episode["ordinal"]]
                    report = verify_target_memory_binding(
                        actual_memory_before=episode["request"][
                            "policy_memory"
                        ],
                        arm=row["arm"],
                        pair_index=row["pair_index"],
                        support_bindings=bindings,
                        pair_count=self.schedule["pair_count"],
                    )
                    if report.get("passed") is not True:
                        findings.append(
                            f"target_{episode['ordinal']}:semantic_binding_failed"
                        )
            except Exception as exc:
                findings.append(
                    f"support_binding_exception:{type(exc).__name__}:{exc}"
                )
        semantic = self.inputs.semantic_analysis
        if semantic is not None:
            if (
                type(semantic) is not dict
                or semantic.get("passed") is not True
                or semantic.get("candidate_episode_count")
                not in {None, self.expected_count}
            ):
                findings.append("optional_semantic_analysis_failed")
        return findings

    def complete_lineage(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        cycle = self._primary_cycle_reports()
        shards = self._shard_reports()
        failed_cycle = self._failed_ordinals(cycle)
        failed_shards = self._failed_ordinals(shards)
        failed_cycle_count = self._failure_count(cycle)
        failed_shard_count = self._failure_count(shards)
        if failed_cycle:
            findings.append(f"lineage_cycle_failed:{failed_cycle_count}")
        if failed_shards:
            findings.append(f"lineage_shard_failed:{failed_shard_count}")
        for ordinal in sorted(set(self._episode_by_ordinal) & set(self.parent)):
            episode, parent = self._episode(ordinal)
            row = self.rows[ordinal]
            try:
                request = validate_worker_request(episode["request"])
                result = validate_worker_result(
                    episode["worker_result"], request=request
                )
                authority = parent.get("authority")
                primary_seal = parent.get("primary_seal")
                primary_result = {
                    key: copy.deepcopy(result[key])
                    for key in (
                        "trace",
                        "operational_authority",
                        "memory_before",
                        "memory_before_sha256",
                        "memory_after",
                        "memory_after_sha256",
                    )
                }
                transcript = {
                    "authorizations": (
                        authority.get("parent_authorizations")
                        if type(authority) is dict
                        else None
                    ),
                    "finish": (
                        authority.get("finish_receipt")
                        if type(authority) is dict
                        else None
                    ),
                }
                if (
                    request["ordinal"] != ordinal
                    or request["schedule_row_sha256"]
                    != canonical_digest(row)
                    or request["source_binding_sha256"]
                    != canonical_digest(self.source_binding)
                    or parent.get("status") != "complete"
                    or parent.get("ordinal") != ordinal
                    or parent.get("request_sha256")
                    != canonical_digest(request)
                    or parent.get("worker_result_sha256")
                    != canonical_digest(result)
                    or parent.get("source_binding")
                    != self.source_binding
                    or parent.get("source_binding_sha256")
                    != canonical_digest(self.source_binding)
                    or parent.get(
                        "worker_claims_accepted_as_authority"
                    )
                    is not False
                    or type(authority) is not dict
                    or authority.get("authority_transcript_sha256")
                    != canonical_digest(transcript)
                    or type(primary_seal) is not dict
                    or primary_seal.get("primary_result_sha256")
                    != canonical_digest(primary_result)
                    or primary_seal.get("authority_transcript_sha256")
                    != canonical_digest(transcript)
                ):
                    findings.append(f"ordinal_{ordinal}:binding_mismatch")
            except Exception as exc:
                findings.append(
                    f"ordinal_{ordinal}:lineage_exception:{type(exc).__name__}"
                )
        findings.extend(self._memory_lineage_findings())
        audit = self.inputs.seed_manifest_audit
        if type(audit) is not dict:
            findings.append("seed_manifest_audit_absent")
        else:
            for name in (
                "nonoverlap_audit",
                "candidate_domain_audit",
                "candidate_restricted_diff",
            ):
                value = audit.get(name)
                if type(value) is not dict or value.get("passed") is not True:
                    findings.append(f"seed_manifest_{name}_failed")
        if not self._harness_source_receipts_valid():
            findings.append("harness_source_before_after_binding_mismatch")
        return _surface(
            passed=not findings,
            findings=findings,
            gate="complete_lineage",
            expected_episode_count=self.expected_count,
            schedule_episode_count=len(self.rows),
            harness_episode_count=len(self._episode_by_ordinal),
            parent_evidence_count=len(self.parent),
            cycle_verified_count=sum(
                item.get("passed") is True for item in cycle.values()
            ),
            shard_verified_count=sum(
                item.get("passed") is True for item in shards.values()
            ),
            support_bindings_checked=self.inputs.support_bindings is not None,
            semantic_analysis_checked=self.inputs.semantic_analysis is not None,
            attempted_ordinal_count=(
                len(self.inputs.attempted_ordinals)
                if self.inputs.attempted_ordinals is not None
                else 0
            ),
        )

    def _forgery_baseline(
        self,
        *,
        ordinal: int,
        result: Mapping[str, Any],
        cached_primary_cycle: bool = False,
    ) -> tuple[bool, list[str]]:
        findings: list[str] = []
        episode, parent = self._episode(ordinal)
        row = self.rows[ordinal]
        try:
            validate_worker_result(result, request=episode["request"])
        except Exception as exc:
            findings.append(f"worker_binding:{type(exc).__name__}:{exc}")
        if result.get("ordinal") != ordinal:
            findings.append("ordinal_ground_truth_mismatch")
        if result.get("schedule_row_sha256") != canonical_digest(row):
            findings.append("schedule_row_ground_truth_mismatch")
        if result.get("source_binding_sha256") != canonical_digest(
            self.source_binding
        ):
            findings.append("source_ground_truth_mismatch")
        if parent.get("worker_result_sha256") != canonical_digest(result):
            findings.append("parent_result_seal_mismatch")
        try:
            cycle = (
                self._primary_cycle_reports()[ordinal]
                if cached_primary_cycle
                else verify_capability_trace(
                    result["trace"],
                    request=episode["request"],
                    environment_log=parent["environment_sessions"][
                        "primary"
                    ]["call_log"],
                    parent_authorizations=parent["authority"][
                        "parent_authorizations"
                    ],
                    parent_finish=parent["authority"]["finish_receipt"],
                )
            )
            findings.extend(
                f"cycle:{item}" for item in cycle.get("findings", [])
            )
        except Exception as exc:
            findings.append(f"cycle_exception:{type(exc).__name__}:{exc}")
        return not findings, _bounded_findings(findings)

    def adversarial_self_attestation_rejection(self) -> dict[str, Any]:
        findings = self._ordinal_findings()
        hook_rows: dict[str, Any] = {}
        ordinals = sorted(set(self._episode_by_ordinal) & set(self.parent))
        for hook in FORGERY_HOOK_PATHS:
            selected: int | None = None
            baseline_findings: list[str] = []
            forged_findings: list[str] = []
            for ordinal in ordinals:
                result = self._episode_by_ordinal[ordinal]["worker_result"]
                baseline_ok, baseline_findings = self._forgery_baseline(
                    ordinal=ordinal,
                    result=result,
                    cached_primary_cycle=True,
                )
                if not baseline_ok:
                    continue
                try:
                    forged = apply_forgery_hook(result, hook)
                    # The generic helper reseals a mutated memory object.  For
                    # the digest leaf itself that would restore the original
                    # value and turn the probe into a no-op, so mutate that
                    # leaf after the generic reseal.
                    if hook == "memory_before_digest":
                        forged["memory_before_sha256"] = (
                            str(forged["memory_before_sha256"]) + ":forged"
                        )
                    trace = forged.get("trace")
                    if (
                        type(trace) is dict
                        and type(trace.get("semantic_trace")) is dict
                        and hook
                        in {
                            "decision_receipt",
                            "world_snapshot",
                            "authority_witness",
                            "target_constraint",
                            "rule_ir",
                            "action_payload",
                            "support_citations",
                        }
                    ):
                        forged["trace"] = (
                            reseal_worker_owned_semantic_digest(trace)
                        )
                    forged_ok, forged_findings = self._forgery_baseline(
                        ordinal=ordinal,
                        result=forged,
                    )
                except Exception:
                    continue
                if not forged_ok:
                    selected = ordinal
                    break
            passed = (
                selected is not None
                and not baseline_findings
                and bool(forged_findings)
                and any(
                    not item.startswith("parent_result_seal_mismatch")
                    for item in forged_findings
                )
            )
            if not passed:
                findings.append(f"forgery_hook_not_proven:{hook}")
            hook_rows[hook] = {
                "passed": passed,
                "applicable_ordinal": selected,
                "baseline_passed": not baseline_findings,
                "forged_findings": forged_findings[:12],
                "worker_owned_digest_resealed_where_applicable": True,
                "parent_result_digest_not_sole_rejection_reason": passed,
            }
        return _surface(
            passed=not findings,
            findings=findings,
            gate="adversarial_self_attestation_rejection",
            hook_count=len(hook_rows),
            hooks=hook_rows,
            missing_applicability_allowed=False,
        )

    def candidate_domain_neutrality(self) -> dict[str, Any]:
        findings: list[str] = []
        direct = [
            self.candidate_root / item for item in _DIRECT_CANDIDATE_PATHS
        ]
        try:
            audit = mechanism.audit_candidate_sources(
                direct,
                repository_root=self.candidate_root,
            )
            if audit.get("passed") is not True:
                findings.extend(
                    f"static_domain:{item}"
                    for item in audit.get("findings", [])
                )
            seed_audit = self.inputs.seed_manifest_audit.get(
                "candidate_domain_audit"
            )
            if (
                type(seed_audit) is not dict
                or seed_audit.get("passed") is not True
            ):
                findings.append("sealed_candidate_domain_audit_failed")
        except Exception as exc:
            audit = {"passed": False, "findings": [str(exc)]}
            findings.append(
                f"candidate_domain_exception:{type(exc).__name__}:{exc}"
            )
        return _surface(
            passed=not findings,
            findings=findings,
            gate="candidate_domain_neutrality",
            direct_paths=list(_DIRECT_CANDIDATE_PATHS),
            closure_path_count=len(audit.get("local_closure_paths", [])),
            static_audit_sha256=canonical_digest(audit),
            candidate_pass_flags_used=False,
        )

    def candidate_runtime_import_closure(self) -> dict[str, Any]:
        findings: list[str] = []
        module_sets: list[str] = []
        if (
            self.runtime_dependency_root is None
            or self.runtime_dependency_binding is None
        ):
            findings.append("runtime_dependency_evidence_absent")
        else:
            try:
                if (
                    bind_runtime_dependency_root(
                        self.runtime_dependency_root
                    )
                    != self.runtime_dependency_binding
                ):
                    findings.append(
                        "runtime_dependency_root_rebind_mismatch"
                    )
            except Exception as exc:
                findings.append(
                    "runtime_dependency_root_rebind:"
                    f"{type(exc).__name__}:{exc}"
                )
        for ordinal, episode in sorted(self._episode_by_ordinal.items()):
            closure = episode.get("worker_result", {}).get(
                "repo_import_closure"
            )
            try:
                if (
                    type(closure) is not dict
                    or closure.get("schema_version")
                    != "atanor.gwip-capability-import-closure.v1"
                    or type(closure.get("candidate_modules")) is not list
                    or type(closure.get("dependency_modules")) is not list
                    or closure.get("approved_dependency_modules")
                    != list(APPROVED_RUNTIME_DEPENDENCIES)
                    or closure.get("outside_candidate_root_modules") != []
                    or closure.get("outside_allowed_root_modules") != []
                    or closure.get("unresolved_file_modules") != []
                    or closure.get("missing_public_modules") != []
                    or closure.get("working_tree_modules") != []
                    or type(closure.get("stdlib_module_count")) is not int
                    or closure.get("stdlib_module_count") < 0
                ):
                    raise CapabilityGateError("import closure shape invalid")
                candidate_rows: list[dict[str, str]] = []
                names: set[str] = set()
                for raw in closure["candidate_modules"]:
                    if (
                        type(raw) is not dict
                        or set(raw) != {"module", "path", "sha256"}
                        or type(raw["module"]) is not str
                        or type(raw["path"]) is not str
                        or _SHA256_RE.fullmatch(str(raw["sha256"])) is None
                    ):
                        raise CapabilityGateError(
                            "import closure module row invalid"
                        )
                    path = (self.candidate_root / raw["path"]).resolve(
                        strict=True
                    )
                    if (
                        not _path_within(path, self.candidate_root)
                        or hashlib.sha256(path.read_bytes()).hexdigest()
                        != raw["sha256"]
                    ):
                        raise CapabilityGateError(
                            "import closure module bytes mismatch"
                        )
                    candidate_rows.append(copy.deepcopy(raw))
                    names.add(raw["module"])
                dependency_rows: list[dict[str, str]] = []
                if self.runtime_dependency_root is None:
                    raise CapabilityGateError(
                        "runtime dependency root is absent"
                    )
                for raw in closure["dependency_modules"]:
                    if (
                        type(raw) is not dict
                        or set(raw) != {"module", "path", "sha256"}
                        or type(raw["module"]) is not str
                        or not (
                            raw["module"] == "_cffi_backend"
                            or raw["module"] == "cryptography"
                            or raw["module"].startswith("cryptography.")
                        )
                        or type(raw["path"]) is not str
                        or _SHA256_RE.fullmatch(str(raw["sha256"])) is None
                    ):
                        raise CapabilityGateError(
                            "dependency import closure module row invalid"
                        )
                    path = (
                        self.runtime_dependency_root / raw["path"]
                    ).resolve(strict=True)
                    if (
                        not _path_within(
                            path,
                            self.runtime_dependency_root,
                        )
                        or hashlib.sha256(path.read_bytes()).hexdigest()
                        != raw["sha256"]
                    ):
                        raise CapabilityGateError(
                            "dependency import closure bytes mismatch"
                        )
                    dependency_rows.append(copy.deepcopy(raw))
                required = set(closure.get("required_public_modules", []))
                if (
                    required
                    != {
                        "packages.cognitive_core",
                        "packages.fusion_loop.interactive",
                        "packages.fusion_loop.interactive_organs",
                    }
                    or not required <= names
                    or closure.get("candidate_modules_sha256")
                    != canonical_digest(candidate_rows)
                    or closure.get("dependency_modules_sha256")
                    != canonical_digest(dependency_rows)
                ):
                    raise CapabilityGateError(
                        "import closure required set/digest mismatch"
                    )
                module_sets.append(
                    canonical_digest(
                        {
                            "candidate": candidate_rows,
                            "dependencies": dependency_rows,
                        }
                    )
                )
            except Exception as exc:
                findings.append(
                    f"ordinal_{ordinal}:import_closure:{type(exc).__name__}:{exc}"
                )
        return _surface(
            passed=not findings and len(module_sets) == self.expected_count,
            findings=findings,
            gate="candidate_runtime_import_closure",
            verified_episode_count=len(module_sets),
            distinct_module_closure_count=len(set(module_sets)),
            every_module_rehashed_from_candidate_archive=True,
            every_dependency_module_rehashed_from_dependency_root=True,
            runtime_dependency_root_rebound=True,
            outside_allowed_file_backed_module_count=0,
            worker_pass_boolean_used=False,
        )

    def candidate_fixed_source_guard_controls(self) -> dict[str, Any]:
        findings: list[str] = []
        actual_dependency_binding: dict[str, Any] = {}
        if not self._harness_source_receipts_valid():
            findings.append("harness_source_before_after_binding_mismatch")
        if (
            self.runtime_dependency_root is None
            or self.runtime_dependency_binding is None
        ):
            findings.append("runtime_dependency_evidence_absent")
        else:
            try:
                actual_dependency_binding = bind_runtime_dependency_root(
                    self.runtime_dependency_root
                )
                if (
                    actual_dependency_binding
                    != self.runtime_dependency_binding
                ):
                    findings.append(
                        "runtime_dependency_root_rebind_mismatch"
                    )
            except Exception as exc:
                findings.append(
                    "runtime_dependency_root_rebind:"
                    f"{type(exc).__name__}:{exc}"
                )
        try:
            actual_archive = _candidate_manifest(
                self.candidate_root,
                repository_root=self.repository_root,
            )
            expected_archive = copy.deepcopy(
                dict(self.inputs.candidate_archive_binding)
            )
            actual_files = _candidate_file_records(self.candidate_root)
            source_tree_binding_valid = (
                set(expected_archive) == {"file_count", "files", "tree_sha256"}
                and expected_archive.get("file_count") == len(actual_files)
                and expected_archive.get("files") == actual_files
                and expected_archive.get("tree_sha256")
                == canonical_digest(actual_files)
            )
            runner_manifest_binding_valid = (
                expected_archive == actual_archive
            )
            if not (
                source_tree_binding_valid or runner_manifest_binding_valid
            ):
                findings.append("candidate_archive_binding_mismatch")
            candidate_git = mechanism.bind_git_candidate_tree(
                self.source_binding["candidate_commit"],
                repository_root=self.repository_root,
            )
            if (
                candidate_git.get("source_digest")
                != self.source_binding["candidate_source_sha256"]
                or candidate_git.get("files") != actual_files
            ):
                findings.append("candidate_archive_differs_from_sealed_C")
            evaluator_git = mechanism.bind_git_paths(
                self.source_binding["evaluator_commit"],
                _EVALUATOR_SOURCE_PATHS,
                repository_root=self.repository_root,
            )
            if (
                evaluator_git.get("source_digest")
                != self.source_binding["evaluator_source_sha256"]
            ):
                findings.append("evaluator_sources_differ_from_sealed_E")
        except Exception as exc:
            actual_archive = {}
            findings.append(
                f"candidate_archive_exception:{type(exc).__name__}:{exc}"
            )
        worker_path = self.repository_root / "scripts/gwip_capability_worker.py"
        worker_sha = (
            hashlib.sha256(worker_path.read_bytes()).hexdigest()
            if worker_path.is_file()
            else None
        )
        for ordinal, episode in sorted(self._episode_by_ordinal.items()):
            parent = self.parent.get(ordinal)
            result = episode.get("worker_result")
            if type(parent) is not dict or type(result) is not dict:
                findings.append(f"ordinal_{ordinal}:source_evidence_absent")
                continue
            process = parent.get("process")
            application = result.get("application_isolation")
            network = result.get("network_guard")
            try:
                if (
                    parent.get("candidate_archive_before") != actual_archive
                    or parent.get("candidate_archive_after") != actual_archive
                    or parent.get("source_binding")
                    != self.source_binding
                    or parent.get("source_binding_sha256")
                    != canonical_digest(self.source_binding)
                    or parent.get("runtime_dependency_before")
                    != self.runtime_dependency_binding
                    or parent.get("runtime_dependency_after")
                    != self.runtime_dependency_binding
                    or parent.get(
                        "runtime_dependency_binding_sha256"
                    )
                    != canonical_digest(self.runtime_dependency_binding)
                    or type(process) is not dict
                    or process.get("return_code") != 0
                    or process.get("stderr_bytes") != 0
                    or process.get("stderr_overflow") is not False
                    or process.get("trailing_stdout_lines") != 0
                    or process.get("runtime_entries") != []
                    or process.get(
                        "environment_secret_keys_forwarded"
                    )
                    is not False
                    or process.get("candidate_subprocess_isolated")
                    is not True
                    or process.get("worker_source_sha256") != worker_sha
                ):
                    raise CapabilityGateError(
                        "parent source/process guard mismatch"
                    )
                if (
                    type(application) is not dict
                    or application.get("schema_version")
                    != "atanor.gwip-capability-application-isolation.v1"
                    or application.get("kind")
                    != "python_audit_guard_not_os_sandbox"
                    or set(application.get("probes", {}))
                    != _APPLICATION_PROBES
                    or not all(
                        value is True
                        for value in application["probes"].values()
                    )
                    or type(application.get("blocked_event_counts"))
                    is not dict
                    or set(application["blocked_event_counts"])
                    != {"child_or_native", "write", "workspace_read"}
                    or not all(
                        type(value) is int and value >= 0
                        for value in application[
                            "blocked_event_counts"
                        ].values()
                    )
                ):
                    raise CapabilityGateError(
                        "application guard probes do not reconstruct"
                    )
                if (
                    type(network) is not dict
                    or network.get("schema_version")
                    != "atanor.gwip-capability-network-guard.v1"
                    or network.get("kind")
                    != "python_audit_and_socket_guard_not_network_namespace"
                    or set(network.get("probes", {})) != _NETWORK_PROBES
                    or not all(
                        value is True
                        for value in network["probes"].values()
                    )
                    or type(network.get("blocked_event_count")) is not int
                    or network["blocked_event_count"] < len(_NETWORK_PROBES)
                ):
                    raise CapabilityGateError(
                        "network guard probes do not reconstruct"
                    )
            except Exception as exc:
                findings.append(
                    f"ordinal_{ordinal}:fixed_source_guard:{type(exc).__name__}:{exc}"
                )
        return _surface(
            passed=not findings
            and len(self._episode_by_ordinal) == self.expected_count,
            findings=findings,
            gate="candidate_fixed_source_guard_controls",
            candidate_archive_sha256=canonical_digest(actual_archive),
            frozen_source_binding_sha256=canonical_digest(
                self.source_binding
            ),
            worker_source_sha256=worker_sha,
            runtime_dependency_binding_sha256=canonical_digest(
                actual_dependency_binding
            ),
            runtime_dependency_parent_receipts_recomputed=True,
            verified_episode_count=len(self._episode_by_ordinal),
            candidate_archive_binding_kind=(
                "sealed_source_tree"
                if "files" in self.inputs.candidate_archive_binding
                else "runner_read_only_manifest"
            ),
            worker_guard_pass_booleans_used=False,
        )

    def all(self) -> dict[str, dict[str, Any]]:
        callbacks: dict[str, Callable[[], Mapping[str, Any]]] = {
            "call_order_and_stop": self.call_order_and_stop,
            "step_budget_and_pre_mutation_denial": (
                self.step_budget_and_pre_mutation_denial
            ),
            "run_lease_direct_authority": self.run_lease_direct_authority,
            "run_lease_single_use_and_replay_rejection": (
                self.run_lease_single_use_and_replay_rejection
            ),
            "adversarial_self_attestation_rejection": (
                self.adversarial_self_attestation_rejection
            ),
            "complete_lineage": self.complete_lineage,
            "structural_cycle_replay": self.structural_cycle_replay,
            "semantic_reexecution_determinism": (
                self.semantic_reexecution_determinism
            ),
            "fresh_environment_reexecution": (
                self.fresh_environment_reexecution
            ),
            "candidate_domain_neutrality": (
                self.candidate_domain_neutrality
            ),
            "candidate_runtime_import_closure": (
                self.candidate_runtime_import_closure
            ),
            "candidate_fixed_source_guard_controls": (
                self.candidate_fixed_source_guard_controls
            ),
        }
        if set(callbacks) != set(REQUIRED_HARD_GATES):
            raise AssertionError("hard-gate callback set drifted")
        return {
            name: _safe_surface(name, callbacks[name])
            for name in REQUIRED_HARD_GATES
        }


def evaluate_hard_gates(
    inputs: CapabilityGateInputs,
) -> dict[str, dict[str, Any]]:
    """Recompute all twelve gates and fail every gate closed on bad inputs."""

    try:
        evaluator = _GateEvaluator(inputs)
    except Exception as exc:
        return {
            name: _surface(
                passed=False,
                findings=[
                    f"input_validation_exception:{type(exc).__name__}:{exc}"
                ],
                gate=name,
                input_validation_failed=True,
            )
            for name in REQUIRED_HARD_GATES
        }
    return evaluator.all()


GateInputsProvider = Callable[
    [Mapping[str, Any]],
    CapabilityGateInputs,
]


def make_gate_verifiers(
    inputs_provider: GateInputsProvider,
) -> dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]:
    """Adapt one complete evaluator to the harness's twelve callbacks.

    The harness invokes callbacks sequentially with the same immutable
    context.  The first callback snapshots runner evidence through
    ``inputs_provider`` and computes all gates.  A later context substitution
    is rejected instead of silently recomputing against different evidence.
    """

    if not callable(inputs_provider):
        raise CapabilityGateError("gate inputs provider must be callable")
    lock = threading.Lock()
    cache: dict[str, Any] = {}

    def complete(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        token = canonical_digest(
            {
                "schedule_sha256": context.get("schedule_sha256"),
                "attempted_ordinals": context.get("attempted_ordinals"),
                "episode_ordinals": [
                    item.get("ordinal")
                    for item in context.get("episodes", [])
                    if type(item) is dict
                ],
                "source_before": context.get("source_before"),
                "source_after": context.get("source_after"),
            }
        )
        with lock:
            if not cache:
                inputs = inputs_provider(copy.deepcopy(dict(context)))
                if not isinstance(inputs, CapabilityGateInputs):
                    raise CapabilityGateError(
                        "inputs provider did not return CapabilityGateInputs"
                    )
                cache["token"] = token
                cache["surfaces"] = evaluate_hard_gates(inputs)
            elif cache["token"] != token:
                raise CapabilityGateError(
                    "hard-gate callback context changed during evaluation"
                )
            return copy.deepcopy(cache["surfaces"])

    def one(name: str) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
        def verify(context: Mapping[str, Any]) -> Mapping[str, Any]:
            try:
                return complete(context)[name]
            except Exception as exc:
                return _surface(
                    passed=False,
                    findings=[
                        f"adapter_exception:{type(exc).__name__}:{exc}"
                    ],
                    gate=name,
                    adapter_fail_closed=True,
                )

        return verify

    return {name: one(name) for name in REQUIRED_HARD_GATES}


def make_independent_gate_registry(
    inputs_provider: GateInputsProvider,
    *,
    fixture_nonproduction: bool = False,
) -> IndependentGateRegistry:
    """Return the exact registry type required by ``CapabilityHarness``."""

    return IndependentGateRegistry(
        verifiers=make_gate_verifiers(inputs_provider),
        fixture_nonproduction=fixture_nonproduction,
    )


__all__ = [
    "CapabilityGateError",
    "CapabilityGateInputs",
    "GATE_EVIDENCE_SCHEMA",
    "audit_environment_call_log",
    "evaluate_hard_gates",
    "make_gate_verifiers",
    "make_independent_gate_registry",
]
