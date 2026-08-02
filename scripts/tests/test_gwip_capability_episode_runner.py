from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

import pytest

from scripts import gwip_capability_episode_runner as runner_module
from scripts.gwip_capability_episode_runner import (
    CandidateEpisodeRunner,
    census_runtime_dependency_sources,
    EpisodeRunnerError,
    materialized_runtime_dependencies,
    ThreadSafeEvidenceSink,
    WORKER_RPC_SCHEMA,
    _ParentProtocol,
    _strict_json_line,
)
from scripts.gwip_capability_harness import (
    BoundEpisodeAuthority,
    SOURCE_BINDING_SCHEMA,
    WORKER_REQUEST_SCHEMA,
    canonical_digest,
    episode_input_digest,
)


REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "scripts" / "gwip_capability_worker.py"


@pytest.fixture(scope="module")
def runtime_dependencies() -> tuple[Path, dict]:
    binding = census_runtime_dependency_sources(repository_root=REPO)
    with materialized_runtime_dependencies(
        binding,
        repository_root=REPO,
    ) as materialized:
        yield materialized


def test_runtime_dependency_binding_reads_each_payload_once() -> None:
    class _Source:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.read_count = 0

        def read_bytes(self) -> bytes:
            self.read_count += 1
            return self.payload

    cffi = _Source(b"cffi-bytes")
    cryptography = _Source(b"cryptography-bytes")
    binding = runner_module._runtime_dependency_binding_from_sources(  # type: ignore[attr-defined]
        [
            ("_cffi_backend", "_cffi_backend.pyd", cffi),
            (
                "cryptography",
                "cryptography/__init__.py",
                cryptography,
            ),
        ]
    )
    assert cffi.read_count == 1
    assert cryptography.read_count == 1
    assert binding["files"] == [
        {
            "dependency": "_cffi_backend",
            "path": "_cffi_backend.pyd",
            "size_bytes": len(cffi.payload),
            "sha256": hashlib.sha256(cffi.payload).hexdigest(),
        },
        {
            "dependency": "cryptography",
            "path": "cryptography/__init__.py",
            "size_bytes": len(cryptography.payload),
            "sha256": hashlib.sha256(cryptography.payload).hexdigest(),
        },
    ]


def _write_candidate(
    root: Path,
    *,
    stderr_anomaly: bool = False,
    exit_code: int | None = None,
    protocol_noise: bool = False,
) -> None:
    packages = root / "packages"
    cognitive = packages / "cognitive_core"
    fusion = packages / "fusion_loop"
    cognitive.mkdir(parents=True)
    fusion.mkdir(parents=True)
    (packages / "__init__.py").write_text("", encoding="utf-8")
    (fusion / "__init__.py").write_text("", encoding="utf-8")
    (cognitive / "__init__.py").write_text(
        """
from __future__ import annotations
import copy
from enum import Enum

class GoalOrigin(str, Enum):
    EXPLICIT_USER = "explicit_user"

class GoalIR:
    def __init__(
        self,
        *,
        statement,
        origin,
        metadata,
        priority=50,
        parent_goal_ids=(),
        constraints=(),
    ):
        self.statement = statement
        self.origin = GoalOrigin(origin)
        self.metadata = copy.deepcopy(metadata)
        self.priority = priority
        self.parent_goal_ids = tuple(parent_goal_ids)
        self.constraints = tuple(constraints)

    def to_dict(self):
        return {
            "statement": self.statement,
            "origin": self.origin.value,
            "metadata": copy.deepcopy(self.metadata),
            "priority": self.priority,
            "parent_goal_ids": list(self.parent_goal_ids),
            "constraints": list(self.constraints),
        }
""".lstrip(),
        encoding="utf-8",
    )
    (fusion / "interactive_organs.py").write_text(
        """
from __future__ import annotations
import copy

class AtanorInteractivePolicy:
    def __init__(self, memory):
        self.memory = copy.deepcopy(memory)

    @classmethod
    def from_memory(cls, memory):
        return cls(memory)

    def export_memory(self):
        return copy.deepcopy(self.memory)
""".lstrip(),
        encoding="utf-8",
    )
    anomaly_line = (
        'sys.stderr.write("fixture stderr anomaly\\\\n")'
        if stderr_anomaly
        else "pass"
    )
    exit_line = f"os._exit({exit_code})" if exit_code is not None else "pass"
    protocol_line = (
        "os.write(1, b'{\"type\":\"x\",\"type\":\"y\"}\\\\n')"
        if protocol_noise
        else "pass"
    )
    (fusion / "interactive.py").write_text(
        f"""
from __future__ import annotations
import copy
import hashlib
import json
import os
import sys

{anomaly_line}
{exit_line}
{protocol_line}

def _digest(value):
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class AuthorizationWitness:
    def __init__(
        self,
        *,
        action_id,
        step_index,
        granted,
        reason,
        authority_kind,
        operational_evidence,
    ):
        self.action_id = action_id
        self.step_index = step_index
        self.granted = granted
        self.reason = reason
        self.authority_kind = authority_kind
        self.operational_evidence = copy.deepcopy(operational_evidence)
        payload = {{
            "action_id": action_id,
            "authority_kind": authority_kind,
            "granted": granted,
            "operational_evidence": self.operational_evidence,
            "reason": reason,
            "step_index": step_index,
        }}
        self.witness_id = "authorization_witness_" + _digest(payload)[:32]

    def semantic_dict(self):
        return {{
            "action_id": self.action_id,
            "authority_kind": self.authority_kind,
            "granted": self.granted,
            "reason": self.reason,
            "step_index": self.step_index,
        }}

    def to_dict(self):
        return {{
            **self.semantic_dict(),
            "bearer_capability": False,
            "operational_evidence": copy.deepcopy(
                self.operational_evidence
            ),
            "witness_id": self.witness_id,
        }}

class _Memory:
    def __init__(self, value):
        self.value = copy.deepcopy(value)

    def to_dict(self):
        return copy.deepcopy(self.value)

    def __eq__(self, other):
        return isinstance(other, _Memory) and self.value == other.value

class _Step:
    def __init__(self, authorization):
        self.authorization = authorization

class _Trace:
    def __init__(
        self,
        *,
        goal,
        authorization,
        authority_finish,
        memory_before,
        memory_after,
        environment_seed,
        policy_seed,
        step_budget,
        retain_policy_updates,
    ):
        self.steps = [_Step(authorization)]
        self.memory_before = _Memory(memory_before)
        self.memory_after = _Memory(memory_after)
        self.authority_finish = copy.deepcopy(authority_finish)
        self.semantic_trace = {{
            "goal": goal.to_dict(),
            "environment_seed": environment_seed,
            "policy_seed": policy_seed,
            "step_budget": step_budget,
            "retain_policy_updates": retain_policy_updates,
            "memory_before": copy.deepcopy(memory_before),
            "memory_after": copy.deepcopy(memory_after),
            "steps": [
                {{"authorization": authorization.semantic_dict()}}
            ],
            "stop_reason": "goal_reached",
        }}
        self.semantic_trace_digest = _digest(self.semantic_trace)

    def to_dict(self):
        return {{
            "schema_version": "atanor.gwip-interactive-trace.fixture.v1",
            "semantic_trace": copy.deepcopy(self.semantic_trace),
            "semantic_trace_digest": self.semantic_trace_digest,
            "lineage_steps": [
                {{"authorization": self.steps[0].authorization.to_dict()}}
            ],
            "authority_finish": copy.deepcopy(self.authority_finish),
        }}

class GenericWorldInteractionLoop:
    def __init__(self, *, authority, policy, require_run_lease):
        self.authority = authority
        self.policy = policy

    def run(
        self,
        environment,
        goal,
        *,
        environment_seed,
        policy_seed,
        step_budget,
        retain_policy_updates,
        session_id,
    ):
        memory_before = self.policy.export_memory()
        environment.reset(environment_seed)
        environment.observe()
        actions = environment.valid_actions()
        action_id = actions[0]["action_id"]
        authorization = self.authority.authorize(action_id, 0)
        result = environment.step(action_id)
        environment.stop(result["stop_reason"])
        finish = self.authority.finish(result["stop_reason"])
        if retain_policy_updates:
            self.policy.memory["visits"] += 1
        return _Trace(
            goal=goal,
            authorization=authorization,
            authority_finish=finish,
            memory_before=memory_before,
            memory_after=self.policy.export_memory(),
            environment_seed=environment_seed,
            policy_seed=policy_seed,
            step_budget=step_budget,
            retain_policy_updates=retain_policy_updates,
        )

class _Verification:
    def to_dict(self):
        return {{
            "structural_replay_ok": True,
            "receipt_cross_check_ok": True,
            "environment_reexecution_ok": True,
            "authority_independently_verified": False,
            "fixture_authority_check_ok": True,
        }}

def reexecute_interactive_trace(
    environment_factory,
    trace,
    *,
    fixture_authority_verifier,
    expected_goal,
    expected_memory_before,
):
    environment = environment_factory()
    environment.reset(101)
    environment.observe()
    actions = environment.valid_actions()
    environment.step(actions[0]["action_id"])
    environment.stop("goal_reached")
    return _Verification()
""".lstrip(),
        encoding="utf-8",
    )


def _make_read_only(root: Path) -> None:
    paths = sorted(
        root.rglob("*"),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for path in paths:
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def _make_writable(root: Path) -> None:
    if not root.exists():
        return
    root.chmod(0o777)
    for path in root.rglob("*"):
        path.chmod(0o777 if path.is_dir() else 0o666)


def _source_binding() -> dict:
    return {
        "schema_version": SOURCE_BINDING_SCHEMA,
        "candidate_commit": "1" * 40,
        "candidate_source_sha256": "2" * 64,
        "evaluator_commit": "3" * 40,
        "evaluator_source_sha256": "4" * 64,
        "seed_manifest_sha256": "5" * 64,
    }


def _request(*, target: bool, modulus: int) -> dict:
    goal = {
        "statement": "Satisfy the structured fixture target.",
        "origin": "explicit_user",
        "metadata": {
            "target_constraints": [
                {
                    "path": "/typed/registers/0",
                    "op": "eq",
                    "value": 1,
                }
            ]
        },
    }
    environment_spec = {
        "fixture_nonproduction": True,
        "shape": f"p{modulus}",
    }
    memory = {
        "schema_version": "atanor.gwip-policy-memory.fixture.v1",
        "visits": 0,
    }
    binding = _source_binding()
    return {
        "schema_version": WORKER_REQUEST_SCHEMA,
        "ordinal": 8 if target else 4,
        "schedule_row_sha256": "6" * 64,
        "phase": "target" if target else "support",
        "pair_index": 0,
        "episode_index": None if target else 0,
        "arm": "matched_warm" if target else None,
        "environment_seed": 101,
        "policy_seed": 3,
        "step_budget": 24,
        "retain_policy_updates": not target,
        "session_id": (
            "gwip-capability:target:0008"
            if target
            else "gwip-capability:support:0004"
        ),
        "goal_ir": goal,
        "environment_spec": environment_spec,
        "policy_memory": memory,
        "policy_memory_sha256": canonical_digest(memory),
        "episode_input_sha256": episode_input_digest(
            goal_ir=goal,
            environment_spec=environment_spec,
        ),
        "source_binding_sha256": canonical_digest(binding),
    }


@dataclass
class _Activation:
    allowed: bool = True
    reason: str = "run_lease_activated"
    lease_id: str = "fixture-lease"

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "lease_id": self.lease_id,
        }


@dataclass
class _Authorization:
    allowed: bool
    reason: str
    counters: dict


@dataclass
class _Finish:
    finished: bool = True
    reason: str = "run_lease_finished"
    lease_id: str = "fixture-lease"

    def to_dict(self) -> dict:
        return {
            "finished": self.finished,
            "reason": self.reason,
            "lease_id": self.lease_id,
            "runner_id": "general_world_interaction",
        }


class _Store:
    def __init__(self) -> None:
        self.count = 0

    def activate(self, *, document: dict, live_context: dict) -> _Activation:
        return _Activation(lease_id=document["lease_id"])

    def authorize(
        self,
        *,
        lease_id: str,
        runner_id: str,
        action_class: str,
        costs: dict,
    ) -> _Authorization:
        self.count += 1
        counters = copy.deepcopy(costs)
        counters["cycles"] = self.count
        counters["actions"] = self.count
        return _Authorization(
            allowed=True,
            reason="run_lease_authorized",
            counters=counters,
        )

    def finish(
        self,
        *,
        lease_id: str,
        runner_id: str,
        reason: str,
    ) -> _Finish:
        return _Finish(lease_id=lease_id)


def _authority(request: dict) -> BoundEpisodeAuthority:
    value = BoundEpisodeAuthority(
        ordinal=request["ordinal"],
        schedule_row_sha256=request["schedule_row_sha256"],
        document={
            "lease_id": "fixture-lease",
            "nonce": "fixture-nonce-00000001",
            "signature": {"fixture": True},
        },
        live_context={
            "fixture_nonproduction": True,
            "input_manifest_sha256": request["episode_input_sha256"],
        },
        store=_Store(),
        issued_monotonic=time.monotonic(),
    )
    value.activate()
    return value


class _Environment:
    def __init__(self, modulus: int) -> None:
        self.modulus = modulus
        self.state = 0

    def reset(self, seed: int) -> dict:
        self.state = 0
        return {"reset": True, "seed": seed}

    def observe(self) -> dict:
        return {
            "schema_version": "fixture-observation.v1",
            "state_ref": f"state-{self.state}",
            "typed": {
                "registers": [self.state],
                "context": {"modulus": self.modulus},
            },
            "terminal": self.state == 1,
        }

    def valid_actions(self) -> list[dict]:
        return [
            {
                "action_id": "fixture-action",
                "payload": {"semantic_cue": "fixture-cue"},
            }
        ]

    def step(self, action_id: str) -> dict:
        assert action_id == "fixture-action"
        self.state = 1
        return {
            "observation": self.observe(),
            "terminal": True,
            "success": True,
            "stop_reason": "goal_reached",
        }

    def stop(self, reason: str) -> dict:
        return {"stopped": True, "reason": reason}


def _runner(
    candidate_root: Path,
    sink: ThreadSafeEvidenceSink,
    *,
    modulus: int,
    runtime_dependencies: tuple[Path, dict],
    timeout_seconds: int = 20,
) -> CandidateEpisodeRunner:
    binding = _source_binding()
    dependency_root, dependency_binding = runtime_dependencies
    return CandidateEpisodeRunner(
        candidate_root=candidate_root,
        worker_script=WORKER,
        evidence_sink=sink,
        environment_factory=lambda _request, _session: _Environment(
            modulus
        ),
        source_probe=lambda: copy.deepcopy(binding),
        repository_root=REPO,
        runtime_dependency_root=dependency_root,
        runtime_dependency_binding=dependency_binding,
        timeout_seconds=timeout_seconds,
    )


@pytest.mark.parametrize(
    ("target", "modulus"),
    ((False, 7), (True, 11)),
)
def test_parent_runner_seals_primary_and_records_independent_evidence(
    tmp_path: Path,
    target: bool,
    modulus: int,
    runtime_dependencies: tuple[Path, dict],
) -> None:
    candidate = tmp_path / "candidate"
    _write_candidate(candidate)
    _make_read_only(candidate)
    try:
        request = _request(target=target, modulus=modulus)
        authority = _authority(request)
        sink = ThreadSafeEvidenceSink()
        result = _runner(
            candidate,
            sink,
            modulus=modulus,
            runtime_dependencies=runtime_dependencies,
        )(
            request,
            authority,
        )
        evidence = sink.get(request["ordinal"])
    finally:
        _make_writable(candidate)

    assert result["schema_version"].endswith("worker-result.v1")
    assert evidence["status"] == "complete"
    assert evidence["worker_claims_accepted_as_authority"] is False
    assert evidence["environment_object_count"] == 5
    assert set(evidence["environment_sessions"]) == {
        "primary",
        "structural_reexecution",
        "determinism_a",
        "determinism_b",
        "fresh_reexecution",
    }
    primary_seal = evidence["primary_seal"]
    structural_index = next(
        item["index"]
        for item in evidence["protocol_order"]
        if item["session"] == "structural_reexecution"
    )
    assert primary_seal["order_index"] < structural_index
    assert primary_seal["sealed_before_auxiliary_sessions"] is True
    assert evidence["authority"]["parent_authorizations"] == result[
        "operational_authority"
    ]
    assert evidence["authority"]["finish_receipt"] == result["trace"][
        "authority_finish"
    ]
    assert evidence["process"]["stderr_bytes"] == 0
    assert evidence["process"]["runtime_entries"] == []
    assert evidence["candidate_archive_before"] == evidence[
        "candidate_archive_after"
    ]
    assert evidence["runtime_dependency_before"] == evidence[
        "runtime_dependency_after"
    ]
    assert evidence["runtime_dependency_before"] == runtime_dependencies[1]
    assert evidence["runtime_dependency_binding_sha256"] == canonical_digest(
        runtime_dependencies[1]
    )
    if target:
        assert result["memory_after"] == result["memory_before"]
    else:
        assert result["memory_after"]["visits"] == 1


def test_protocol_rejects_duplicate_call_id_and_auth_action_mismatch() -> None:
    request = _request(target=False, modulus=7)
    protocol = _ParentProtocol(
        request=request,
        authority=_authority(request),
        environment_factory=lambda _request, _session: _Environment(7),
    )
    malformed_call = {
        "schema_version": WORKER_RPC_SCHEMA,
        "type": "environment_request",
        "session": "primary",
        "call_id": 1,
        "operation": "reset",
        "payload": {"seed": 101},
    }
    with pytest.raises(EpisodeRunnerError, match="call ID"):
        protocol.handle(malformed_call)

    protocol = _ParentProtocol(
        request=request,
        authority=_authority(request),
        environment_factory=lambda _request, _session: _Environment(7),
    )
    for call_id, operation, payload in (
        (0, "reset", {"seed": 101}),
        (1, "observe", {}),
        (2, "valid_actions", {}),
    ):
        protocol.handle(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "environment_request",
                "session": "primary",
                "call_id": call_id,
                "operation": operation,
                "payload": payload,
            }
        )
    with pytest.raises(EpisodeRunnerError, match="action/step binding"):
        protocol.handle(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "authority_request",
                "session": "authority:primary",
                "call_id": 0,
                "operation": "authorize",
                "payload": {
                    "action_id": "forged-action",
                    "step_index": 0,
                },
            }
        )


def test_protocol_rejects_late_primary_and_authoritative_worker_claims() -> None:
    request = _request(target=False, modulus=7)
    protocol = _ParentProtocol(
        request=request,
        authority=_authority(request),
        environment_factory=lambda _request, _session: _Environment(7),
    )
    protocol.phase = "structural_reexecution"
    with pytest.raises(EpisodeRunnerError, match="after auxiliary"):
        protocol.handle(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "primary_result",
                "session": "primary_result",
                "call_id": 0,
                "result": {},
            }
        )

    with pytest.raises(EpisodeRunnerError, match="claims as authority"):
        protocol._reject_authoritative_worker_claims(
            {
                "worker_claims": {
                    "non_authoritative": False,
                    "all_hard_gates_passed": True,
                }
            }
        )


def test_malformed_json_and_stderr_anomaly_fail_closed(
    tmp_path: Path,
    runtime_dependencies: tuple[Path, dict],
) -> None:
    with pytest.raises(EpisodeRunnerError, match="duplicate JSON key"):
        _strict_json_line(
            b'{"type":"x","type":"y"}\n',
            label="fixture",
        )

    candidate = tmp_path / "stderr-candidate"
    _write_candidate(candidate, stderr_anomaly=True)
    _make_read_only(candidate)
    request = _request(target=False, modulus=7)
    sink = ThreadSafeEvidenceSink()
    try:
        with pytest.raises(EpisodeRunnerError, match="stderr anomaly"):
            _runner(
                candidate,
                sink,
                modulus=7,
                runtime_dependencies=runtime_dependencies,
            )(request, _authority(request))
        evidence = sink.get(request["ordinal"])
    finally:
        _make_writable(candidate)
    assert evidence["status"] == "failed"
    assert evidence["stderr_bytes"] > 0

    protocol_candidate = tmp_path / "protocol-candidate"
    _write_candidate(protocol_candidate, protocol_noise=True)
    _make_read_only(protocol_candidate)
    protocol_sink = ThreadSafeEvidenceSink()
    try:
        with pytest.raises(EpisodeRunnerError, match="duplicate JSON key"):
            _runner(
                protocol_candidate,
                protocol_sink,
                modulus=7,
                runtime_dependencies=runtime_dependencies,
            )(
                request,
                _authority(request),
            )
        protocol_evidence = protocol_sink.get(request["ordinal"])
    finally:
        _make_writable(protocol_candidate)
    assert protocol_evidence["status"] == "failed"


def test_nonzero_worker_exit_is_rejected(
    tmp_path: Path,
    runtime_dependencies: tuple[Path, dict],
) -> None:
    candidate = tmp_path / "exit-candidate"
    _write_candidate(candidate, exit_code=9)
    _make_read_only(candidate)
    request = _request(target=False, modulus=7)
    sink = ThreadSafeEvidenceSink()
    try:
        with pytest.raises(EpisodeRunnerError, match="code 9"):
            _runner(
                candidate,
                sink,
                modulus=7,
                runtime_dependencies=runtime_dependencies,
            )(
                request,
                _authority(request),
            )
        evidence = sink.get(request["ordinal"])
    finally:
        _make_writable(candidate)
    assert evidence["status"] == "failed"


def test_candidate_archive_must_be_external_and_read_only(
    tmp_path: Path,
    runtime_dependencies: tuple[Path, dict],
) -> None:
    candidate = tmp_path / "writable-candidate"
    _write_candidate(candidate)
    with pytest.raises(EpisodeRunnerError, match="read-only"):
        _runner(
            candidate,
            ThreadSafeEvidenceSink(),
            modulus=7,
            runtime_dependencies=runtime_dependencies,
        )
