from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
from types import ModuleType

import pytest

from scripts import gwip_capability_worker as worker
from scripts.gwip_capability_episode_runner import (
    census_runtime_dependency_sources,
    materialized_runtime_dependencies,
)
from scripts.gwip_capability_harness import validate_worker_result


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


def test_system_site_is_never_classified_as_stdlib() -> None:
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    source = purelib / "requests" / "__init__.py"
    assert source.is_file()
    assert worker._within_stdlib(  # type: ignore[attr-defined]
        source,
        stdlib_roots=worker._stdlib_import_roots(),  # type: ignore[attr-defined]
        third_party_roots=worker._third_party_import_roots(),  # type: ignore[attr-defined]
    ) is False


def test_unbound_system_site_module_is_outside_allowed_closure(
    tmp_path: Path,
    runtime_dependencies: tuple[Path, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.find_spec("requests")
    assert spec is not None and spec.origin is not None
    injected = ModuleType("_atanor_injected_system_site_module")
    injected.__file__ = spec.origin
    monkeypatch.setitem(
        sys.modules,
        "_atanor_injected_system_site_module",
        injected,
    )
    candidate_root = tmp_path / "candidate"
    (candidate_root / "packages").mkdir(parents=True)
    closure = worker._module_closure(  # type: ignore[attr-defined]
        candidate_root,
        runtime_dependencies[0],
        REPO,
    )
    assert {
        "module": "_atanor_injected_system_site_module",
        "path": str(Path(spec.origin).resolve(strict=True)),
    } in closure["outside_allowed_root_modules"]
    assert closure["passed"] is False


def _goal(modulus: int) -> dict:
    return {
        "statement": "Satisfy the structured fixture target.",
        "origin": "explicit_user",
        "metadata": {
            "target_constraints": [
                {
                    "path": "/typed/registers/0",
                    "op": "eq",
                    "value": 2,
                }
            ],
            "fixture_modulus": modulus,
        },
    }


def _request(*, target: bool, modulus: int) -> dict:
    goal = _goal(modulus)
    environment_spec = {
        "fixture_nonproduction": True,
        "shape": f"p{modulus}",
        "public_action_count": 1,
    }
    memory = {
        "schema_version": "atanor.gwip-policy-memory.fixture.v1",
        "visits": 0,
    }
    value = {
        "schema_version": worker.WORKER_REQUEST_SCHEMA,
        "ordinal": 5 if target else 2,
        "schedule_row_sha256": "a" * 64,
        "phase": "target" if target else "support",
        "pair_index": 0,
        "episode_index": None if target else 2,
        "arm": "matched_warm" if target else None,
        "environment_seed": 101,
        "policy_seed": 3,
        "step_budget": 24,
        "retain_policy_updates": not target,
        "session_id": (
            "gwip-capability:target:0005"
            if target
            else "gwip-capability:support:0002"
        ),
        "goal_ir": goal,
        "environment_spec": environment_spec,
        "policy_memory": memory,
        "policy_memory_sha256": worker.canonical_digest(memory),
        "episode_input_sha256": worker.episode_input_digest(
            goal_ir=goal,
            environment_spec=environment_spec,
        ),
        "source_binding_sha256": "b" * 64,
    }
    return value


def _write_mock_candidate(root: Path) -> None:
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
    (fusion / "interactive.py").write_text(
        f"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import __main__

try:
    Path({str(WORKER)!r}).read_bytes()
except PermissionError:
    FORBIDDEN_EVALUATOR_READ_BLOCKED = True
else:
    FORBIDDEN_EVALUATOR_READ_BLOCKED = False
SEED_ENV_ABSENT = "ATANOR_PRIVATE_SEED_TOKEN" not in os.environ
EVALUATOR_MAIN_HIDDEN = not hasattr(__main__, "validate_worker_request")

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

    def to_dict(self):
        return {{
            "action_id": self.action_id,
            "step_index": self.step_index,
            "granted": self.granted,
            "reason": self.reason,
            "authority_kind": self.authority_kind,
            "operational_evidence": copy.deepcopy(self.operational_evidence),
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
        action_id,
        authorization,
        memory_before,
        memory_after,
        authority_finish,
        retain_policy_updates,
        session_id,
    ):
        self.goal = goal
        self.action_id = action_id
        self.steps = [_Step(authorization)]
        self.memory_before = _Memory(memory_before)
        self.memory_after = _Memory(memory_after)
        self.authority_finish = copy.deepcopy(authority_finish)
        self.retain_policy_updates = retain_policy_updates
        self.session_id = session_id
        self.semantic_trace_digest = _digest(self.semantic_dict())

    def semantic_dict(self):
        return {{
            "goal": self.goal.to_dict(),
            "action_id": self.action_id,
            "memory_before": self.memory_before.to_dict(),
            "memory_after": self.memory_after.to_dict(),
            "retain_policy_updates": self.retain_policy_updates,
            "session_id": self.session_id,
        }}

    def to_dict(self):
        return {{
            "schema_version": "atanor.gwip-interactive-trace.fixture.v1",
            "semantic_trace": self.semantic_dict(),
            "semantic_trace_digest": self.semantic_trace_digest,
            "lineage_steps": [
                {{"authorization": self.steps[0].authorization.to_dict()}}
            ],
            "authority_finish": copy.deepcopy(self.authority_finish),
            "memory_before": self.memory_before.to_dict(),
            "memory_after": self.memory_after.to_dict(),
            "candidate_probes": {{
                "forbidden_evaluator_read_blocked":
                    FORBIDDEN_EVALUATOR_READ_BLOCKED,
                "seed_environment_absent": SEED_ENV_ABSENT,
                "evaluator_main_hidden": EVALUATOR_MAIN_HIDDEN,
            }},
        }}

class GenericWorldInteractionLoop:
    def __init__(self, *, authority, policy, require_run_lease):
        self.authority = authority
        self.policy = policy
        self.require_run_lease = require_run_lease

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
            action_id=action_id,
            authorization=authorization,
            memory_before=memory_before,
            memory_after=self.policy.export_memory(),
            authority_finish=finish,
            retain_policy_updates=retain_policy_updates,
            session_id=session_id,
        )

class _Verification:
    def __init__(self):
        self.payload = {{
            "structural_replay_ok": True,
            "receipt_cross_check_ok": True,
            "environment_reexecution_ok": True,
            "authority_independently_verified": False,
            "fixture_authority_check_ok": True,
        }}

    def to_dict(self):
        return copy.deepcopy(self.payload)

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


def _write_response(
    process: subprocess.Popen[str],
    *,
    message_type: str,
    session: str,
    call_id: int,
    result: object,
) -> None:
    assert process.stdin is not None
    process.stdin.write(
        json.dumps(
            {
                "schema_version": worker.WORKER_RPC_SCHEMA,
                "type": message_type,
                "session": session,
                "call_id": call_id,
                "ok": True,
                "result": result,
                "error": None,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    process.stdin.flush()


def _exercise_worker(
    tmp_path: Path,
    *,
    target: bool,
    modulus: int,
    runtime_dependencies: tuple[Path, dict],
) -> tuple[dict, list[str], str]:
    candidate_root = tmp_path / "candidate"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True)
    _write_mock_candidate(candidate_root)
    request = _request(target=target, modulus=modulus)
    environment = os.environ.copy()
    dependency_root, _dependency_binding = runtime_dependencies
    environment.update(
        {
            "ATANOR_GWIP_CAPABILITY_CANDIDATE_ROOT": str(
                candidate_root
            ),
            "ATANOR_GWIP_CAPABILITY_DEPENDENCY_ROOT": str(
                dependency_root
            ),
            "ATANOR_GWIP_CAPABILITY_RUNTIME_ROOT": str(runtime_root),
            "ATANOR_PRIVATE_SEED_TOKEN": "must-not-reach-candidate",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-S", str(WORKER), "candidate-worker"],
        cwd=REPO,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(
        json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n"
    )
    process.stdin.flush()
    session_state: dict[str, int] = {}
    order: list[str] = []
    result: dict | None = None
    for _ in range(100):
        line = process.stdout.readline()
        assert line, "worker exited before returning a protocol result"
        message = json.loads(line)
        message_type = message["type"]
        if message_type == "environment_request":
            session = message["session"]
            operation = message["operation"]
            order.append(f"{session}:{operation}")
            if operation == "reset":
                session_state[session] = 0
                response: object = {
                    "reset": True,
                    "fixture": f"p{modulus}",
                }
            elif operation == "observe":
                response = {
                    "schema_version": "fixture-observation.v1",
                    "state_ref": f"state-{session_state[session]}",
                    "typed": {
                        "registers": [session_state[session]],
                        "context": {"modulus": modulus},
                    },
                    "terminal": session_state[session] == 1,
                }
            elif operation == "valid_actions":
                response = [
                    {
                        "action_id": "fixture-action",
                        "payload": {"semantic_cue": "fixture-cue"},
                    }
                ]
            elif operation == "step":
                assert message["payload"] == {
                    "action_id": "fixture-action"
                }
                session_state[session] = 1
                response = {
                    "observation": {
                        "schema_version": "fixture-observation.v1",
                        "state_ref": "state-1",
                        "typed": {
                            "registers": [1],
                            "context": {"modulus": modulus},
                        },
                        "terminal": True,
                    },
                    "terminal": True,
                    "success": True,
                    "stop_reason": "goal_reached",
                }
            elif operation == "stop":
                response = {
                    "stopped": True,
                    "reason": message["payload"]["reason"],
                }
            else:  # pragma: no cover - protocol drift
                raise AssertionError(operation)
            _write_response(
                process,
                message_type="environment_response",
                session=session,
                call_id=message["call_id"],
                result=response,
            )
        elif message_type == "authority_request":
            order.append(f"authority:{message['operation']}")
            if message["operation"] == "authorize":
                response = {
                    "action_id": message["payload"]["action_id"],
                    "step_index": message["payload"]["step_index"],
                    "granted": True,
                    "reason": "fixture_run_lease_granted",
                    "authority_kind": "externally_signed_run_lease",
                    "operational_evidence": {
                        "fixture_nonproduction": True
                    },
                }
            else:
                response = {
                    "finished": True,
                    "reason": message["payload"]["reason"],
                }
            _write_response(
                process,
                message_type="authority_response",
                session=message["session"],
                call_id=message["call_id"],
                result=response,
            )
        elif message_type == "primary_result":
            order.append("primary_result:sealed")
            assert not any(
                item.startswith("structural_reexecution:")
                for item in order[:-1]
            )
            _write_response(
                process,
                message_type="primary_result_ack",
                session="primary_result",
                call_id=0,
                result={"sealed": True},
            )
        elif message_type == "worker_result":
            result = message["result"]
            break
        elif message_type == "worker_failure":  # pragma: no cover - diagnostic
            raise AssertionError(message)
        else:  # pragma: no cover - protocol drift
            raise AssertionError(message)
    process.stdin.close()
    return_code = process.wait(timeout=20)
    assert process.stderr is not None
    stderr = process.stderr.read()
    assert return_code == 0, stderr
    assert result is not None
    return result, order, stderr


def test_request_validation_is_exact_and_binds_complete_episode_input() -> None:
    request = _request(target=False, modulus=7)
    assert worker.validate_worker_request(request) == request

    forged = copy.deepcopy(request)
    forged["environment_spec"]["public_action_count"] = 2
    with pytest.raises(worker.CapabilityWorkerError, match="value invalid"):
        worker.validate_worker_request(forged)

    extra = copy.deepcopy(request)
    extra["caller_says_valid"] = True
    with pytest.raises(worker.CapabilityWorkerError, match="fields mismatch"):
        worker.validate_worker_request(extra)

    target = _request(target=True, modulus=11)
    target["retain_policy_updates"] = True
    with pytest.raises(worker.CapabilityWorkerError, match="value invalid"):
        worker.validate_worker_request(target)


def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers() -> None:
    with pytest.raises(worker.CapabilityWorkerError, match="duplicate JSON key"):
        worker._strict_json_line(b'{"x":1,"x":2}\n', label="fixture")
    with pytest.raises(worker.CapabilityWorkerError, match="non-finite"):
        worker._strict_json_line(b'{"x":NaN}\n', label="fixture")


@pytest.mark.parametrize(
    ("target", "modulus"),
    ((False, 7), (True, 11)),
)
def test_subprocess_seals_primary_before_auxiliary_and_isolates_candidate(
    tmp_path: Path,
    target: bool,
    modulus: int,
    runtime_dependencies: tuple[Path, dict],
) -> None:
    result, order, _stderr = _exercise_worker(
        tmp_path,
        target=target,
        modulus=modulus,
        runtime_dependencies=runtime_dependencies,
    )
    request = _request(target=target, modulus=modulus)
    assert validate_worker_result(result, request=request) == result
    assert result["trace"]["candidate_probes"] == {
        "forbidden_evaluator_read_blocked": True,
        "seed_environment_absent": True,
        "evaluator_main_hidden": True,
    }
    assert result["application_isolation"]["passed"] is True
    assert result["repo_import_closure"]["passed"] is True
    assert result["network_guard"]["passed"] is True
    assert result["worker_claims"]["non_authoritative"] is True
    assert (
        result["worker_claims"][
            "primary_result_sealed_before_auxiliary_sessions"
        ]
        is True
    )
    assert (
        result["worker_claims"]["candidate_determinism_trace_a"]
        ["semantic_trace_digest"]
        == result["worker_claims"]["candidate_determinism_trace_b"]
        ["semantic_trace_digest"]
    )
    seal_index = order.index("primary_result:sealed")
    for session in (
        "structural_reexecution",
        "determinism_a",
        "determinism_b",
        "fresh_reexecution",
    ):
        first = next(
            index
            for index, item in enumerate(order)
            if item.startswith(f"{session}:")
        )
        assert first > seal_index
    if target:
        assert result["memory_after"] == result["memory_before"]
    else:
        assert result["memory_after"]["visits"] == 1


def test_cli_rejects_every_non_worker_mode() -> None:
    with pytest.raises(SystemExit, match="usage"):
        worker.main([])
