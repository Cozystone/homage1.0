"""Evaluator-owned subprocess/RPC runner for one GWIP capability episode.

The candidate subprocess can propose actions and emit traces, but it never
owns the environment, RunLease, source seal, protocol order, or evidence
verdict.  This module keeps each of those surfaces in the parent process and
returns only an exact harness worker result after independently binding the
candidate's primary trace to the parent authority transcript.

Worker-side structural, replay, isolation, and capability statements are
retained as non-authoritative observations.  They are never accepted as hard
gate or capability evidence by this runner.
"""
from __future__ import annotations

import contextlib
import copy
from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import queue
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from typing import Any, Callable, Iterator, Mapping, Protocol, runtime_checkable

from scripts.gwip_capability_harness import (
    BoundEpisodeAuthority,
    WORKER_RESULT_SCHEMA,
    canonical_digest,
    validate_source_binding,
    validate_worker_request,
    validate_worker_result,
)


WORKER_RPC_SCHEMA = "atanor.gwip-capability-worker-rpc.v1"
RUNNER_EVIDENCE_SCHEMA = "atanor.gwip-capability-parent-episode-evidence.v1"
RUNTIME_DEPENDENCY_BINDING_SCHEMA = (
    "atanor.gwip-capability-runtime-dependency-binding.v1"
)
APPROVED_RUNTIME_DEPENDENCIES = ("_cffi_backend", "cryptography")

_MAX_LINE_BYTES = 32 * 1024 * 1024
_MAX_STDERR_BYTES = 1 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_DEPENDENCY_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "approved_dependencies",
        "python_runtime",
        "files",
        "tree_sha256",
    }
)
_RUNTIME_DEPENDENCY_FILE_FIELDS = frozenset(
    {"dependency", "path", "size_bytes", "sha256"}
)
_AUXILIARY_SESSIONS = (
    "structural_reexecution",
    "determinism_a",
    "determinism_b",
    "fresh_reexecution",
)
_ALL_ENVIRONMENT_SESSIONS = ("primary", *_AUXILIARY_SESSIONS)
_NEXT_AUXILIARY_PHASE = {
    "structural_reexecution": "determinism_a",
    "determinism_a": "determinism_b",
    "determinism_b": "fresh_reexecution",
    "fresh_reexecution": "complete",
}
_ENVIRONMENT_MESSAGE_FIELDS = frozenset(
    {
        "schema_version",
        "type",
        "session",
        "call_id",
        "operation",
        "payload",
    }
)
_AUTHORITY_MESSAGE_FIELDS = _ENVIRONMENT_MESSAGE_FIELDS
_PRIMARY_MESSAGE_FIELDS = frozenset(
    {"schema_version", "type", "session", "call_id", "result"}
)
_FINAL_MESSAGE_FIELDS = frozenset(
    {"schema_version", "type", "result"}
)
_FAILURE_MESSAGE_FIELDS = frozenset(
    {"schema_version", "type", "error_type", "error"}
)
_RPC_RESPONSE_FIELDS = frozenset(
    {
        "schema_version",
        "type",
        "session",
        "call_id",
        "ok",
        "result",
        "error",
    }
)
_PRIMARY_RESULT_FIELDS = frozenset(
    {
        "trace",
        "operational_authority",
        "memory_before",
        "memory_before_sha256",
        "memory_after",
        "memory_after_sha256",
    }
)
_WORKER_CLAIM_FIELDS = frozenset(
    {
        "schema_version",
        "non_authoritative",
        "parent_evaluator_must_reconstruct",
        "primary_result_sealed_before_auxiliary_sessions",
        "auxiliary_sessions",
        "auxiliary_used_production_authority",
        "candidate_structural_verification",
        "candidate_semantic_determinism",
        "candidate_determinism_trace_a",
        "candidate_determinism_trace_b",
        "candidate_fresh_environment_reexecution",
        "capability_verdict",
        "hard_gate_verdict",
    }
)


class EpisodeRunnerError(ValueError):
    """The candidate process or evaluator-owned episode boundary is invalid."""


@runtime_checkable
class EvidenceSink(Protocol):
    def record(self, ordinal: int, evidence: Mapping[str, Any]) -> None: ...


class ThreadSafeEvidenceSink:
    """Write-once in-memory evidence sink keyed by semantic ordinal."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._evidence: dict[int, dict[str, Any]] = {}

    def record(self, ordinal: int, evidence: Mapping[str, Any]) -> None:
        if type(ordinal) is not int or ordinal < 0 or type(evidence) is not dict:
            raise EpisodeRunnerError("evidence sink input is invalid")
        with self._lock:
            if ordinal in self._evidence:
                raise EpisodeRunnerError(
                    f"parent evidence already exists for ordinal {ordinal}"
                )
            self._evidence[ordinal] = copy.deepcopy(dict(evidence))

    def get(self, ordinal: int) -> dict[str, Any]:
        with self._lock:
            if ordinal not in self._evidence:
                raise KeyError(ordinal)
            return copy.deepcopy(self._evidence[ordinal])

    def snapshot(self) -> dict[int, dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._evidence)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_copy(value: Any, *, label: str) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise EpisodeRunnerError(f"{label} is not exact JSON") from exc


def _strict_json_line(raw: bytes, *, label: str) -> dict[str, Any]:
    if (
        not raw
        or len(raw) > _MAX_LINE_BYTES
        or not raw.endswith(b"\n")
    ):
        raise EpisodeRunnerError(f"{label} line is missing or too large")

    def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise EpisodeRunnerError(
                    f"{label} contains duplicate JSON key: {key}"
                )
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EpisodeRunnerError(
                    f"{label} contains non-finite number: {token}"
                )
            ),
        )
    except EpisodeRunnerError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EpisodeRunnerError(f"{label} is not strict JSON") from exc
    if type(value) is not dict:
        raise EpisodeRunnerError(f"{label} root must be an exact object")
    return value


def _write_message(stream: Any, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    stream.write(payload)
    stream.flush()


def _response(
    *,
    message_type: str,
    session: str,
    call_id: int,
    result: Any,
) -> dict[str, Any]:
    value = {
        "schema_version": WORKER_RPC_SCHEMA,
        "type": message_type,
        "session": session,
        "call_id": call_id,
        "ok": True,
        "result": _json_copy(result, label="RPC result"),
        "error": None,
    }
    if frozenset(value) != _RPC_RESPONSE_FIELDS:
        raise AssertionError("RPC response fields drifted")
    return value


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _python_runtime_binding() -> dict[str, Any]:
    return {
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag,
        "version": platform.python_version(),
        "platform": sys.platform,
        "machine": platform.machine(),
    }


def _runtime_dependency_sources(
    *,
    repository_root: Path,
) -> list[tuple[str, str, Path]]:
    repository = Path(repository_root).resolve(strict=True)
    rows: list[tuple[str, str, Path]] = []
    cryptography_spec = importlib.util.find_spec("cryptography")
    if (
        cryptography_spec is None
        or cryptography_spec.origin is None
        or cryptography_spec.submodule_search_locations is None
        or len(cryptography_spec.submodule_search_locations) != 1
    ):
        raise EpisodeRunnerError(
            "approved cryptography runtime dependency is unavailable"
        )
    cryptography_root = Path(
        next(iter(cryptography_spec.submodule_search_locations))
    ).resolve(strict=True)
    if (
        cryptography_root.name != "cryptography"
        or cryptography_root.is_symlink()
        or _path_within(cryptography_root, repository)
    ):
        raise EpisodeRunnerError(
            "cryptography runtime dependency source is unsafe"
        )
    for path in sorted(
        cryptography_root.rglob("*"),
        key=lambda item: item.as_posix(),
    ):
        if path.is_symlink():
            raise EpisodeRunnerError(
                "runtime dependency source contains a symlink"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise EpisodeRunnerError(
                "runtime dependency source contains a non-file entry"
            )
        relative = path.relative_to(cryptography_root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        rows.append(
            (
                "cryptography",
                (Path("cryptography") / relative).as_posix(),
                path,
            )
        )

    cffi_spec = importlib.util.find_spec("_cffi_backend")
    if cffi_spec is None or cffi_spec.origin is None:
        raise EpisodeRunnerError(
            "approved _cffi_backend runtime dependency is unavailable"
        )
    cffi_path = Path(cffi_spec.origin).resolve(strict=True)
    if (
        not cffi_path.is_file()
        or cffi_path.is_symlink()
        or _path_within(cffi_path, repository)
        or not cffi_path.name.startswith("_cffi_backend.")
    ):
        raise EpisodeRunnerError(
            "_cffi_backend runtime dependency source is unsafe"
        )
    rows.append(("_cffi_backend", cffi_path.name, cffi_path))
    if not rows:
        raise EpisodeRunnerError("runtime dependency source census is empty")
    return sorted(rows, key=lambda item: item[1])


def _runtime_dependency_binding_from_sources(
    sources: list[tuple[str, str, Path]],
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for dependency, logical_path, source in sources:
        payload = source.read_bytes()
        files.append(
            {
                "dependency": dependency,
                "path": logical_path,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    binding = {
        "schema_version": RUNTIME_DEPENDENCY_BINDING_SCHEMA,
        "approved_dependencies": list(APPROVED_RUNTIME_DEPENDENCIES),
        "python_runtime": _python_runtime_binding(),
        "files": files,
        "tree_sha256": canonical_digest(files),
    }
    return validate_runtime_dependency_binding(binding)


def validate_runtime_dependency_binding(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        type(value) is not dict
        or frozenset(value) != _RUNTIME_DEPENDENCY_BINDING_FIELDS
        or value.get("schema_version")
        != RUNTIME_DEPENDENCY_BINDING_SCHEMA
        or value.get("approved_dependencies")
        != list(APPROVED_RUNTIME_DEPENDENCIES)
    ):
        raise EpisodeRunnerError("runtime dependency binding fields mismatch")
    runtime = value.get("python_runtime")
    if (
        type(runtime) is not dict
        or set(runtime)
        != {"implementation", "cache_tag", "version", "platform", "machine"}
        or any(type(item) is not str or not item for item in runtime.values())
    ):
        raise EpisodeRunnerError("runtime dependency Python binding invalid")
    files = value.get("files")
    if type(files) is not list or not files:
        raise EpisodeRunnerError("runtime dependency file census invalid")
    normalized: list[dict[str, Any]] = []
    paths: set[str] = set()
    dependencies: set[str] = set()
    for raw in files:
        if (
            type(raw) is not dict
            or frozenset(raw) != _RUNTIME_DEPENDENCY_FILE_FIELDS
            or raw.get("dependency") not in APPROVED_RUNTIME_DEPENDENCIES
            or type(raw.get("path")) is not str
            or not raw["path"]
            or "\\" in raw["path"]
            or type(raw.get("size_bytes")) is not int
            or raw["size_bytes"] < 0
            or _SHA256_RE.fullmatch(str(raw.get("sha256"))) is None
        ):
            raise EpisodeRunnerError("runtime dependency file row invalid")
        logical = Path(raw["path"])
        if (
            logical.is_absolute()
            or ".." in logical.parts
            or "." in logical.parts
            or raw["path"] in paths
        ):
            raise EpisodeRunnerError("runtime dependency path is unsafe")
        if raw["dependency"] == "cryptography":
            if logical.parts[0] != "cryptography":
                raise EpisodeRunnerError(
                    "cryptography dependency path is outside its namespace"
                )
        elif (
            len(logical.parts) != 1
            or not logical.name.startswith("_cffi_backend.")
        ):
            raise EpisodeRunnerError(
                "_cffi_backend dependency path is outside its namespace"
            )
        paths.add(raw["path"])
        dependencies.add(raw["dependency"])
        normalized.append(copy.deepcopy(raw))
    if (
        normalized != sorted(normalized, key=lambda item: item["path"])
        or dependencies != set(APPROVED_RUNTIME_DEPENDENCIES)
        or value.get("tree_sha256") != canonical_digest(normalized)
    ):
        raise EpisodeRunnerError(
            "runtime dependency census order/digest mismatch"
        )
    return copy.deepcopy(dict(value))


def census_runtime_dependency_sources(
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Bind the exact approved host dependency bytes before seed S exists."""

    return _runtime_dependency_binding_from_sources(
        _runtime_dependency_sources(repository_root=repository_root)
    )


def bind_runtime_dependency_root(root: Path) -> dict[str, Any]:
    """Re-hash an already materialized dependency root without trusting it."""

    base = Path(root).resolve(strict=True)
    if not base.is_dir() or base.is_symlink():
        raise EpisodeRunnerError("runtime dependency root is unsafe")
    sources: list[tuple[str, str, Path]] = []
    for path in sorted(base.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise EpisodeRunnerError(
                "runtime dependency root contains a symlink"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise EpisodeRunnerError(
                "runtime dependency root contains a non-file entry"
            )
        relative = path.relative_to(base)
        logical = relative.as_posix()
        if relative.parts[0] == "cryptography":
            dependency = "cryptography"
        elif (
            len(relative.parts) == 1
            and relative.name.startswith("_cffi_backend.")
        ):
            dependency = "_cffi_backend"
        else:
            raise EpisodeRunnerError(
                "runtime dependency root contains an unapproved file"
            )
        sources.append((dependency, logical, path))
    return _runtime_dependency_binding_from_sources(sources)


def _set_runtime_dependency_tree_read_only(
    root: Path,
    *,
    read_only: bool,
) -> None:
    paths = [Path(root), *Path(root).rglob("*")]
    paths.sort(
        key=lambda item: len(item.parts),
        reverse=not read_only,
    )
    for path in paths:
        if path.is_dir():
            mode = stat.S_IREAD | stat.S_IEXEC
        else:
            mode = stat.S_IREAD
        if not read_only:
            mode |= stat.S_IWRITE
        path.chmod(mode)


def _assert_runtime_dependency_tree_read_only(root: Path) -> None:
    base = Path(root).resolve(strict=True)
    for path in [base, *base.rglob("*")]:
        if path.is_symlink():
            raise EpisodeRunnerError(
                "runtime dependency root contains a symlink"
            )
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise EpisodeRunnerError(
                "runtime dependency root is not recursively read-only"
            )


@contextlib.contextmanager
def materialized_runtime_dependencies(
    expected_binding: Mapping[str, Any],
    *,
    repository_root: Path,
) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Materialize only approved, hash-bound dependencies for one sealed run."""

    expected = validate_runtime_dependency_binding(expected_binding)
    if expected["python_runtime"] != _python_runtime_binding():
        raise EpisodeRunnerError(
            "runtime dependency Python ABI differs from the sealed binding"
        )
    sources = _runtime_dependency_sources(repository_root=repository_root)
    actual = _runtime_dependency_binding_from_sources(sources)
    if actual != expected:
        raise EpisodeRunnerError(
            "host runtime dependency bytes differ from the sealed binding"
        )
    with tempfile.TemporaryDirectory(
        prefix="atanor-gwip-runtime-dependencies-"
    ) as raw:
        root = Path(raw).resolve(strict=True)
        for _dependency, logical_path, source in sources:
            destination = root / Path(logical_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        materialized = bind_runtime_dependency_root(root)
        if materialized != expected:
            raise EpisodeRunnerError(
                "materialized runtime dependency binding mismatch"
            )
        _set_runtime_dependency_tree_read_only(root, read_only=True)
        _assert_runtime_dependency_tree_read_only(root)
        try:
            yield root, copy.deepcopy(materialized)
        finally:
            _set_runtime_dependency_tree_read_only(root, read_only=False)


def _candidate_read_only_manifest(
    candidate_root: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    root = Path(candidate_root).resolve(strict=True)
    repository = Path(repository_root).resolve(strict=True)
    if (
        _path_within(root, repository)
        or not (root / "packages").is_dir()
        or root.is_symlink()
    ):
        raise EpisodeRunnerError(
            "candidate archive must be an external package tree"
        )
    records: list[dict[str, Any]] = []
    paths = [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]
    for path in paths:
        if path.is_symlink():
            raise EpisodeRunnerError("candidate archive contains a symlink")
        metadata = path.stat()
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise EpisodeRunnerError(
                "candidate archive is not recursively read-only"
            )
        if path.is_dir():
            kind = "directory"
            size = None
            file_sha256 = None
        elif path.is_file():
            kind = "file"
            size = metadata.st_size
            file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise EpisodeRunnerError(
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
                "sha256": file_sha256,
            }
        )
    file_count = sum(item["kind"] == "file" for item in records)
    if file_count == 0:
        raise EpisodeRunnerError("candidate archive has no files")
    return {
        "root_path_sha256": hashlib.sha256(
            str(root).encode("utf-8")
        ).hexdigest(),
        "entry_count": len(records),
        "file_count": file_count,
        "metadata_manifest_sha256": canonical_digest(records),
        "content_manifest_sha256": canonical_digest(
            [
                {
                    "path": item["path"],
                    "size_bytes": item["size_bytes"],
                    "sha256": item["sha256"],
                }
                for item in records
                if item["kind"] == "file"
            ]
        ),
        "recursively_read_only": True,
        "external_to_repository": True,
    }


def candidate_archive_manifest(
    candidate_root: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Return the evaluator-owned immutable archive census.

    This public wrapper lets the top-level one-shot evaluator bind the exact
    same archive surface that the episode runner checks before and after every
    subprocess.  Independent hard gates still reconstruct the census in their
    own module.
    """

    return _candidate_read_only_manifest(
        candidate_root,
        repository_root=repository_root,
    )


def _action_ids(value: Any) -> tuple[str, ...]:
    if type(value) is not list:
        raise EpisodeRunnerError("valid_actions result must be an array")
    result: list[str] = []
    for item in value:
        if type(item) is str:
            action_id = item
        elif type(item) is dict and type(item.get("action_id")) is str:
            action_id = item["action_id"]
        else:
            raise EpisodeRunnerError("valid_actions item is invalid")
        if not action_id:
            raise EpisodeRunnerError("valid action ID is empty")
        result.append(action_id)
    if len(result) != len(set(result)):
        raise EpisodeRunnerError("valid action IDs are duplicated")
    return tuple(result)


def _authorization_witness(
    response: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "action_id",
        "step_index",
        "granted",
        "reason",
        "authority_kind",
        "operational_evidence",
    }
    if type(response) is not dict or frozenset(response) != fields:
        raise EpisodeRunnerError(
            "parent authority response fields mismatch"
        )
    payload = copy.deepcopy(dict(response))
    digest = canonical_digest(
        {
            "action_id": payload["action_id"],
            "authority_kind": payload["authority_kind"],
            "granted": payload["granted"],
            "operational_evidence": payload["operational_evidence"],
            "reason": payload["reason"],
            "step_index": payload["step_index"],
        }
    )
    return {
        "action_id": payload["action_id"],
        "authority_kind": payload["authority_kind"],
        "bearer_capability": False,
        "granted": payload["granted"],
        "operational_evidence": payload["operational_evidence"],
        "reason": payload["reason"],
        "step_index": payload["step_index"],
        "witness_id": f"authorization_witness_{digest[:32]}",
    }


@dataclass
class _EnvironmentSession:
    name: str
    environment: Any
    next_call_id: int = 0
    state: str = "new"
    step_count: int = 0
    valid_action_ids: tuple[str, ...] = ()
    stop_reason: str | None = None
    call_log: list[dict[str, Any]] = field(default_factory=list)


class _ParentProtocol:
    """Strict state machine for one candidate process."""

    def __init__(
        self,
        *,
        request: Mapping[str, Any],
        authority: BoundEpisodeAuthority,
        environment_factory: Callable[[Mapping[str, Any], str], Any],
    ) -> None:
        self.request = copy.deepcopy(dict(request))
        self.authority = authority
        self.environment_factory = environment_factory
        self.phase = "primary"
        self.sessions: dict[str, _EnvironmentSession] = {}
        self.environment_object_ids: set[int] = set()
        self.authority_call_id = 0
        self.pending_authorization: tuple[str, int] | None = None
        self.parent_authorizations: list[dict[str, Any]] = []
        self.parent_authorization_responses: list[dict[str, Any]] = []
        self.parent_finish: dict[str, Any] | None = None
        self.primary_result: dict[str, Any] | None = None
        self.primary_seal: dict[str, Any] | None = None
        self.worker_result: dict[str, Any] | None = None
        self.protocol_order: list[dict[str, Any]] = []

    def _record_order(
        self,
        *,
        message_type: str,
        session: Any = None,
        operation: Any = None,
        call_id: Any = None,
    ) -> int:
        index = len(self.protocol_order)
        self.protocol_order.append(
            {
                "index": index,
                "type": message_type,
                "session": session,
                "operation": operation,
                "call_id": call_id,
            }
        )
        return index

    def _session(self, name: str) -> _EnvironmentSession:
        current = self.sessions.get(name)
        if current is not None:
            return current
        environment = self.environment_factory(
            copy.deepcopy(self.request),
            name,
        )
        identity = id(environment)
        if identity in self.environment_object_ids:
            raise EpisodeRunnerError(
                "environment factory reused an object across sessions"
            )
        for method in ("reset", "observe", "valid_actions", "step", "stop"):
            if not callable(getattr(environment, method, None)):
                raise EpisodeRunnerError(
                    f"environment session {name} lacks {method}"
                )
        self.environment_object_ids.add(identity)
        current = _EnvironmentSession(name=name, environment=environment)
        self.sessions[name] = current
        return current

    def _environment_request(
        self,
        message: Mapping[str, Any],
        *,
        order_index: int,
    ) -> dict[str, Any]:
        if frozenset(message) != _ENVIRONMENT_MESSAGE_FIELDS:
            raise EpisodeRunnerError("environment RPC fields mismatch")
        session_name = message.get("session")
        if (
            session_name not in _ALL_ENVIRONMENT_SESSIONS
            or session_name != self.phase
            or type(message.get("payload")) is not dict
        ):
            raise EpisodeRunnerError("environment RPC phase/binding mismatch")
        session = self._session(session_name)
        call_id = message.get("call_id")
        if type(call_id) is not int or call_id != session.next_call_id:
            raise EpisodeRunnerError(
                "environment RPC call ID is duplicate or out of order"
            )
        session.next_call_id += 1
        operation = message.get("operation")
        payload = copy.deepcopy(message["payload"])

        if (
            operation == "reset"
            and frozenset(payload) == {"seed"}
            and session.state == "new"
        ):
            if payload["seed"] != self.request["environment_seed"]:
                raise EpisodeRunnerError("environment reset seed mismatch")
            result = session.environment.reset(payload["seed"])
            session.state = "need_observe"
        elif (
            operation == "observe"
            and not payload
            and session.state == "need_observe"
        ):
            result = session.environment.observe()
            session.state = "need_valid_actions"
        elif (
            operation == "valid_actions"
            and not payload
            and session.state == "need_valid_actions"
        ):
            result = list(session.environment.valid_actions())
            session.valid_action_ids = _action_ids(
                _json_copy(result, label="valid_actions result")
            )
            session.state = "after_valid_actions"
        elif (
            operation == "step"
            and frozenset(payload) == {"action_id"}
            and session.state == "after_valid_actions"
        ):
            action_id = payload["action_id"]
            if (
                type(action_id) is not str
                or action_id not in session.valid_action_ids
                or session.step_count >= self.request["step_budget"]
            ):
                raise EpisodeRunnerError(
                    "environment step is invalid or exceeds budget"
                )
            if session_name == "primary":
                if self.pending_authorization != (
                    action_id,
                    session.step_count,
                ):
                    raise EpisodeRunnerError(
                        "primary step lacks matching parent authorization"
                    )
                self.pending_authorization = None
            result = session.environment.step(action_id)
            session.step_count += 1
            session.state = "need_observe"
        elif (
            operation == "stop"
            and frozenset(payload) == {"reason"}
            and session.state
            in {"need_observe", "need_valid_actions", "after_valid_actions"}
        ):
            reason = payload["reason"]
            if type(reason) is not str or not reason:
                raise EpisodeRunnerError("environment stop reason is invalid")
            if session_name == "primary" and self.pending_authorization is not None:
                raise EpisodeRunnerError(
                    "primary environment stopped with unused authorization"
                )
            result = session.environment.stop(reason)
            session.stop_reason = reason
            session.state = "stopped"
            if session_name == "primary":
                self.phase = "await_primary_finish"
            else:
                self.phase = _NEXT_AUXILIARY_PHASE[session_name]
        else:
            raise EpisodeRunnerError(
                "environment RPC operation is out of order"
            )
        json_result = _json_copy(result, label=f"{session_name} {operation}")
        log = {
            "order_index": order_index,
            "call_id": call_id,
            "operation": operation,
            "payload": payload,
            "result": json_result,
            "result_sha256": canonical_digest(json_result),
        }
        # Flatten the evaluator-owned operation arguments used by the
        # independent cycle verifier.  The original payload remains present,
        # so these are cross-checkable conveniences rather than caller claims.
        if operation == "reset":
            log["seed"] = payload["seed"]
        elif operation == "step":
            log["action_id"] = payload["action_id"]
            log["step_index"] = session.step_count - 1
        elif operation == "stop":
            log["reason"] = payload["reason"]
        session.call_log.append(log)
        return _response(
            message_type="environment_response",
            session=session_name,
            call_id=call_id,
            result=json_result,
        )

    def _authority_request(
        self,
        message: Mapping[str, Any],
    ) -> dict[str, Any]:
        if frozenset(message) != _AUTHORITY_MESSAGE_FIELDS:
            raise EpisodeRunnerError("authority RPC fields mismatch")
        if (
            message.get("session") != "authority:primary"
            or type(message.get("call_id")) is not int
            or message["call_id"] != self.authority_call_id
            or type(message.get("payload")) is not dict
        ):
            raise EpisodeRunnerError(
                "authority RPC call ID or session is invalid"
            )
        call_id = self.authority_call_id
        self.authority_call_id += 1
        operation = message.get("operation")
        payload = copy.deepcopy(message["payload"])
        primary = self.sessions.get("primary")

        if (
            operation == "authorize"
            and frozenset(payload) == {"action_id", "step_index"}
        ):
            if (
                self.phase != "primary"
                or primary is None
                or primary.state != "after_valid_actions"
                or self.pending_authorization is not None
                or self.parent_finish is not None
            ):
                raise EpisodeRunnerError(
                    "parent authorization is out of order"
                )
            action_id = payload["action_id"]
            step_index = payload["step_index"]
            if (
                type(action_id) is not str
                or action_id not in primary.valid_action_ids
                or type(step_index) is not int
                or step_index != primary.step_count
            ):
                raise EpisodeRunnerError(
                    "parent authorization action/step binding mismatch"
                )
            result = self.authority.authorize(
                action_id=action_id,
                step_index=step_index,
            )
            expected = {
                "action_id",
                "step_index",
                "granted",
                "reason",
                "authority_kind",
                "operational_evidence",
            }
            if (
                type(result) is not dict
                or frozenset(result) != expected
                or result.get("action_id") != action_id
                or result.get("step_index") != step_index
                or result.get("granted") is not True
            ):
                raise EpisodeRunnerError(
                    "BoundEpisodeAuthority returned an invalid witness"
                )
            result = _json_copy(result, label="parent authorization")
            self.pending_authorization = (action_id, step_index)
            self.parent_authorization_responses.append(copy.deepcopy(result))
            self.parent_authorizations.append(
                _authorization_witness(result)
            )
        elif operation == "finish" and frozenset(payload) == {"reason"}:
            if (
                self.phase != "await_primary_finish"
                or primary is None
                or primary.state != "stopped"
                or self.pending_authorization is not None
                or self.parent_finish is not None
                or payload["reason"] != primary.stop_reason
            ):
                raise EpisodeRunnerError("parent authority finish is out of order")
            result = self.authority.finish(payload["reason"])
            if type(result) is not dict:
                raise EpisodeRunnerError(
                    "BoundEpisodeAuthority finish receipt is invalid"
                )
            result = _json_copy(result, label="parent finish receipt")
            self.parent_finish = copy.deepcopy(result)
            self.phase = "await_primary_result"
        else:
            raise EpisodeRunnerError("authority RPC operation is invalid")
        return _response(
            message_type="authority_response",
            session="authority:primary",
            call_id=call_id,
            result=result,
        )

    def _verify_authority_lineage(
        self,
        primary: Mapping[str, Any],
    ) -> None:
        if primary.get("operational_authority") != self.parent_authorizations:
            raise EpisodeRunnerError(
                "worker operational authority differs from parent transcript"
            )
        trace = primary.get("trace")
        if type(trace) is not dict:
            raise EpisodeRunnerError("primary trace is not an object")
        lineage = trace.get("lineage_steps")
        if (
            type(lineage) is not list
            or any(type(item) is not dict for item in lineage)
            or [item.get("authorization") for item in lineage]
            != self.parent_authorizations
            or trace.get("authority_finish") != self.parent_finish
        ):
            raise EpisodeRunnerError(
                "trace authority lineage differs from parent transcript"
            )
        semantic = trace.get("semantic_trace")
        if type(semantic) is not dict:
            raise EpisodeRunnerError("trace semantic projection is missing")
        expected_semantic = [
            {
                "action_id": item["action_id"],
                "authority_kind": item["authority_kind"],
                "granted": item["granted"],
                "reason": item["reason"],
                "step_index": item["step_index"],
            }
            for item in self.parent_authorizations
        ]
        semantic_steps = semantic.get("steps")
        if (
            type(semantic_steps) is not list
            or any(type(item) is not dict for item in semantic_steps)
            or [item.get("authorization") for item in semantic_steps]
            != expected_semantic
        ):
            raise EpisodeRunnerError(
                "semantic authorization lineage differs from parent transcript"
            )

    def _verify_primary_result(
        self,
        value: Any,
        *,
        order_index: int,
    ) -> dict[str, Any]:
        if (
            type(value) is not dict
            or frozenset(value) != _PRIMARY_RESULT_FIELDS
            or type(value.get("trace")) is not dict
            or type(value.get("operational_authority")) is not list
            or type(value.get("memory_before")) is not dict
            or type(value.get("memory_after")) is not dict
            or value.get("memory_before") != self.request["policy_memory"]
            or value.get("memory_before_sha256")
            != self.request["policy_memory_sha256"]
            or value.get("memory_after_sha256")
            != canonical_digest(value["memory_after"])
            or (
                self.request["retain_policy_updates"] is False
                and value["memory_after"] != value["memory_before"]
            )
        ):
            raise EpisodeRunnerError("primary result shape/binding is invalid")
        checked = copy.deepcopy(dict(value))
        self._verify_authority_lineage(checked)
        semantic = checked["trace"]["semantic_trace"]
        if (
            semantic.get("environment_seed")
            != self.request["environment_seed"]
            or semantic.get("policy_seed") != self.request["policy_seed"]
            or semantic.get("step_budget") != self.request["step_budget"]
            or semantic.get("retain_policy_updates")
            != self.request["retain_policy_updates"]
            or semantic.get("memory_before") != checked["memory_before"]
            or semantic.get("memory_after") != checked["memory_after"]
            or checked["trace"].get("semantic_trace_digest")
            != canonical_digest(semantic)
        ):
            raise EpisodeRunnerError(
                "primary semantic trace is not independently bound"
            )
        self.primary_result = checked
        self.primary_seal = {
            "order_index": order_index,
            "primary_result_sha256": canonical_digest(checked),
            "authority_transcript_sha256": canonical_digest(
                {
                    "authorizations": self.parent_authorizations,
                    "finish": self.parent_finish,
                }
            ),
            "sealed_before_auxiliary_sessions": True,
        }
        return checked

    def _primary_message(
        self,
        message: Mapping[str, Any],
        *,
        order_index: int,
    ) -> dict[str, Any]:
        if (
            frozenset(message) != _PRIMARY_MESSAGE_FIELDS
            or message.get("session") != "primary_result"
            or message.get("call_id") != 0
            or self.phase != "await_primary_result"
            or self.primary_result is not None
        ):
            raise EpisodeRunnerError(
                "primary result arrived after auxiliary work or out of order"
            )
        self._verify_primary_result(
            message.get("result"),
            order_index=order_index,
        )
        self.phase = "structural_reexecution"
        return _response(
            message_type="primary_result_ack",
            session="primary_result",
            call_id=0,
            result={"sealed": True},
        )

    @staticmethod
    def _reject_authoritative_worker_claims(
        result: Mapping[str, Any],
    ) -> None:
        claims = result.get("worker_claims")
        if (
            type(claims) is not dict
            or frozenset(claims) != _WORKER_CLAIM_FIELDS
            or claims.get("schema_version")
            != "atanor.gwip-capability-worker-claims.v1"
            or claims.get("non_authoritative") is not True
            or claims.get("parent_evaluator_must_reconstruct") is not True
            or claims.get(
                "primary_result_sealed_before_auxiliary_sessions"
            )
            is not True
            or claims.get("auxiliary_sessions")
            != list(_AUXILIARY_SESSIONS)
            or claims.get("auxiliary_used_production_authority") is not False
            or claims.get("capability_verdict") is not None
            or claims.get("hard_gate_verdict") is not None
        ):
            raise EpisodeRunnerError(
                "worker attempted to present claims as authority"
            )

    def _final_message(self, message: Mapping[str, Any]) -> None:
        if (
            frozenset(message) != _FINAL_MESSAGE_FIELDS
            or self.phase != "complete"
            or self.primary_result is None
            or self.worker_result is not None
        ):
            raise EpisodeRunnerError("worker result is out of order")
        result = validate_worker_result(
            message.get("result"),
            request=self.request,
        )
        if any(
            result[field] != self.primary_result[field]
            for field in _PRIMARY_RESULT_FIELDS
        ):
            raise EpisodeRunnerError(
                "primary result changed after auxiliary sessions"
            )
        self._reject_authoritative_worker_claims(result)
        self._verify_authority_lineage(result)
        self.worker_result = result

    def handle(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        if (
            type(message) is not dict
            or message.get("schema_version") != WORKER_RPC_SCHEMA
        ):
            raise EpisodeRunnerError("worker protocol schema is invalid")
        message_type = message.get("type")
        order_index = self._record_order(
            message_type=str(message_type),
            session=message.get("session"),
            operation=message.get("operation"),
            call_id=message.get("call_id"),
        )
        if message_type == "environment_request":
            return self._environment_request(
                message,
                order_index=order_index,
            )
        if message_type == "authority_request":
            return self._authority_request(message)
        if message_type == "primary_result":
            return self._primary_message(
                message,
                order_index=order_index,
            )
        if message_type == "worker_result":
            self._final_message(message)
            return None
        if message_type == "worker_failure":
            if frozenset(message) != _FAILURE_MESSAGE_FIELDS:
                raise EpisodeRunnerError(
                    "worker failure message fields mismatch"
                )
            error_type = str(message.get("error_type"))[:80]
            error = str(message.get("error"))[:240]
            raise EpisodeRunnerError(
                f"candidate worker failure: {error_type}:{error}"
            )
        raise EpisodeRunnerError("worker protocol message type is invalid")

    def evidence_surfaces(self) -> dict[str, Any]:
        return {
            "environment_sessions": {
                name: {
                    "call_log": copy.deepcopy(session.call_log),
                    "call_log_sha256": canonical_digest(session.call_log),
                    "step_count": session.step_count,
                    "stop_reason": session.stop_reason,
                    "stopped": session.state == "stopped",
                }
                for name, session in sorted(self.sessions.items())
            },
            "environment_object_count": len(self.environment_object_ids),
            "authority": {
                "document": copy.deepcopy(self.authority.document),
                "live_context": copy.deepcopy(self.authority.live_context),
                "activation_receipt": copy.deepcopy(
                    self.authority.activation_receipt
                ),
                "parent_authorization_responses": copy.deepcopy(
                    self.parent_authorization_responses
                ),
                "parent_authorizations": copy.deepcopy(
                    self.parent_authorizations
                ),
                "finish_receipt": copy.deepcopy(self.parent_finish),
                "authority_transcript_sha256": canonical_digest(
                    {
                        "authorizations": self.parent_authorizations,
                        "finish": self.parent_finish,
                    }
                ),
            },
            "primary_seal": copy.deepcopy(self.primary_seal),
            "protocol_order": copy.deepcopy(self.protocol_order),
            "protocol_order_sha256": canonical_digest(self.protocol_order),
            "worker_claims_accepted_as_authority": False,
        }


class CandidateEpisodeRunner:
    """Callable harness episode runner with an evaluator-owned RPC boundary."""

    def __init__(
        self,
        *,
        candidate_root: Path,
        worker_script: Path,
        evidence_sink: EvidenceSink,
        environment_factory: Callable[[Mapping[str, Any], str], Any],
        source_probe: Callable[[], Mapping[str, Any]],
        repository_root: Path,
        runtime_dependency_root: Path,
        runtime_dependency_binding: Mapping[str, Any],
        timeout_seconds: int = 1_200,
    ) -> None:
        self.repository_root = Path(repository_root).resolve(strict=True)
        self.candidate_root = Path(candidate_root).resolve(strict=True)
        self.worker_script = Path(worker_script).resolve(strict=True)
        self.runtime_dependency_root = Path(
            runtime_dependency_root
        ).resolve(strict=True)
        self.runtime_dependency_binding = validate_runtime_dependency_binding(
            runtime_dependency_binding
        )
        if (
            not self.worker_script.is_file()
            or not _path_within(self.worker_script, self.repository_root)
            or _path_within(self.worker_script, self.candidate_root)
        ):
            raise EpisodeRunnerError(
                "worker script must be evaluator-owned repository source"
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
            or _path_within(
                self.candidate_root,
                self.runtime_dependency_root,
            )
            or bind_runtime_dependency_root(self.runtime_dependency_root)
            != self.runtime_dependency_binding
        ):
            raise EpisodeRunnerError(
                "runtime dependency root/binding is invalid"
            )
        _assert_runtime_dependency_tree_read_only(
            self.runtime_dependency_root
        )
        if (
            not isinstance(evidence_sink, EvidenceSink)
            or not callable(environment_factory)
            or not callable(source_probe)
            or type(timeout_seconds) is not int
            or timeout_seconds <= 0
        ):
            raise EpisodeRunnerError("episode runner dependencies are invalid")
        self.evidence_sink = evidence_sink
        self.environment_factory = environment_factory
        self.source_probe = source_probe
        self.timeout_seconds = timeout_seconds
        self.worker_source_sha256 = hashlib.sha256(
            self.worker_script.read_bytes()
        ).hexdigest()
        self._source_probe_lock = threading.Lock()
        _candidate_read_only_manifest(
            self.candidate_root,
            repository_root=self.repository_root,
        )

    def _probe_source(self) -> dict[str, Any]:
        with self._source_probe_lock:
            raw = self.source_probe()
        if type(raw) is not dict:
            raise EpisodeRunnerError(
                "episode runner requires a full source binding probe"
            )
        return validate_source_binding(raw)

    @staticmethod
    def _sanitized_environment(runtime_root: Path) -> dict[str, str]:
        retained: dict[str, str] = {}
        for key in (
            "COMSPEC",
            "PATHEXT",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "WINDIR",
        ):
            value = os.environ.get(key)
            if value:
                retained[key] = value
        retained.update(
            {
                "ATANOR_GWIP_CAPABILITY_CANDIDATE_ROOT": "",
                "ATANOR_GWIP_CAPABILITY_DEPENDENCY_ROOT": "",
                "ATANOR_GWIP_CAPABILITY_RUNTIME_ROOT": "",
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONNOUSERSITE": "1",
                "PYTHONUTF8": "1",
                "TEMP": str(runtime_root),
                "TMP": str(runtime_root),
            }
        )
        return retained

    def __call__(
        self,
        request: Mapping[str, Any],
        authority: BoundEpisodeAuthority,
    ) -> dict[str, Any]:
        checked_request = validate_worker_request(request)
        ordinal = checked_request["ordinal"]
        evidence: dict[str, Any] = {
            "schema_version": RUNNER_EVIDENCE_SCHEMA,
            "ordinal": ordinal,
            "status": "running",
            "request_sha256": canonical_digest(checked_request),
            "worker_claims_accepted_as_authority": False,
        }
        protocol: _ParentProtocol | None = None
        process: subprocess.Popen[bytes] | None = None
        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None
        stdout_queue: queue.Queue[bytes | None] = queue.Queue()
        stderr_chunks: list[bytes] = []
        stderr_count = [0]
        stderr_overflow = [False]
        try:
            if type(authority) is not BoundEpisodeAuthority:
                raise EpisodeRunnerError(
                    "episode runner requires exact BoundEpisodeAuthority"
                )
            if (
                authority.ordinal != ordinal
                or authority.schedule_row_sha256
                != checked_request["schedule_row_sha256"]
                or authority.activated_monotonic is None
                or authority.activation_receipt is None
                or authority.finished_monotonic is not None
            ):
                raise EpisodeRunnerError(
                    "active authority does not bind the worker request"
                )
            archive_before = _candidate_read_only_manifest(
                self.candidate_root,
                repository_root=self.repository_root,
            )
            dependency_before = bind_runtime_dependency_root(
                self.runtime_dependency_root
            )
            _assert_runtime_dependency_tree_read_only(
                self.runtime_dependency_root
            )
            if dependency_before != self.runtime_dependency_binding:
                raise EpisodeRunnerError(
                    "runtime dependency bytes changed before episode"
                )
            source_before = self._probe_source()
            if canonical_digest(source_before) != checked_request[
                "source_binding_sha256"
            ]:
                raise EpisodeRunnerError(
                    "request/source probe binding mismatch"
                )
            worker_before = hashlib.sha256(
                self.worker_script.read_bytes()
            ).hexdigest()
            if worker_before != self.worker_source_sha256:
                raise EpisodeRunnerError(
                    "worker source changed before episode"
                )
            protocol = _ParentProtocol(
                request=checked_request,
                authority=authority,
                environment_factory=self.environment_factory,
            )
            with tempfile.TemporaryDirectory(
                prefix="atanor-gwip-capability-runtime-"
            ) as raw_runtime:
                runtime_root = Path(raw_runtime).resolve(strict=True)
                try:
                    runtime_root.relative_to(self.repository_root)
                except ValueError:
                    pass
                else:
                    raise EpisodeRunnerError(
                        "worker runtime is inside repository"
                    )
                environment = self._sanitized_environment(runtime_root)
                environment[
                    "ATANOR_GWIP_CAPABILITY_CANDIDATE_ROOT"
                ] = str(self.candidate_root)
                environment[
                    "ATANOR_GWIP_CAPABILITY_RUNTIME_ROOT"
                ] = str(runtime_root)
                environment[
                    "ATANOR_GWIP_CAPABILITY_DEPENDENCY_ROOT"
                ] = str(self.runtime_dependency_root)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-S",
                        str(self.worker_script),
                        "candidate-worker",
                    ],
                    cwd=runtime_root,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                assert process.stdin is not None
                assert process.stdout is not None
                assert process.stderr is not None

                def read_stdout() -> None:
                    assert process is not None
                    assert process.stdout is not None
                    while True:
                        line = process.stdout.readline(_MAX_LINE_BYTES + 1)
                        if not line:
                            stdout_queue.put(None)
                            return
                        stdout_queue.put(line)

                def read_stderr() -> None:
                    assert process is not None
                    assert process.stderr is not None
                    while True:
                        chunk = process.stderr.read(65_536)
                        if not chunk:
                            return
                        stderr_count[0] += len(chunk)
                        remaining = _MAX_STDERR_BYTES - sum(
                            len(item) for item in stderr_chunks
                        )
                        if remaining > 0:
                            stderr_chunks.append(chunk[:remaining])
                        if stderr_count[0] > _MAX_STDERR_BYTES:
                            stderr_overflow[0] = True

                stdout_thread = threading.Thread(
                    target=read_stdout,
                    name=f"gwip-capability-stdout-{ordinal}",
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=read_stderr,
                    name=f"gwip-capability-stderr-{ordinal}",
                    daemon=True,
                )
                stdout_thread.start()
                stderr_thread.start()
                try:
                    _write_message(process.stdin, checked_request)
                except Exception:
                    process.kill()
                    process.wait(timeout=5)
                    stdout_thread.join(timeout=2)
                    stderr_thread.join(timeout=2)
                    raise
                deadline = time.monotonic() + self.timeout_seconds
                while protocol.worker_result is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        process.kill()
                        process.wait(timeout=5)
                        raise EpisodeRunnerError(
                            "candidate worker timed out"
                        )
                    try:
                        raw_line = stdout_queue.get(timeout=remaining)
                    except queue.Empty as exc:
                        process.kill()
                        process.wait(timeout=5)
                        raise EpisodeRunnerError(
                            "candidate worker timed out"
                        ) from exc
                    if raw_line is None:
                        try:
                            return_code = process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            return_code = process.poll()
                        if return_code is not None and return_code != 0:
                            raise EpisodeRunnerError(
                                "candidate worker exited with code "
                                f"{return_code}"
                            )
                        raise EpisodeRunnerError(
                            "candidate worker exited before a result"
                        )
                    try:
                        message = _strict_json_line(
                            raw_line,
                            label="candidate worker output",
                        )
                    except Exception:
                        process.kill()
                        process.wait(timeout=5)
                        stdout_thread.join(timeout=2)
                        stderr_thread.join(timeout=2)
                        raise
                    try:
                        response = protocol.handle(message)
                    except Exception:
                        process.kill()
                        process.wait(timeout=5)
                        stdout_thread.join(timeout=2)
                        stderr_thread.join(timeout=2)
                        raise
                    if response is not None:
                        try:
                            _write_message(process.stdin, response)
                        except Exception:
                            process.kill()
                            process.wait(timeout=5)
                            stdout_thread.join(timeout=2)
                            stderr_thread.join(timeout=2)
                            raise
                try:
                    process.stdin.close()
                except OSError:
                    pass
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    return_code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.wait(timeout=5)
                    raise EpisodeRunnerError(
                        "candidate worker did not exit"
                    ) from exc
                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                if stdout_thread.is_alive() or stderr_thread.is_alive():
                    raise EpisodeRunnerError(
                        "candidate worker output readers did not terminate"
                    )
                trailing_stdout: list[bytes] = []
                while True:
                    try:
                        item = stdout_queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is not None:
                        trailing_stdout.append(item)
                if trailing_stdout:
                    raise EpisodeRunnerError(
                        "candidate worker emitted output after final result"
                    )
                if return_code != 0:
                    raise EpisodeRunnerError(
                        f"candidate worker exited with code {return_code}"
                    )
                if stderr_count[0] or stderr_overflow[0]:
                    raise EpisodeRunnerError(
                        "candidate worker emitted stderr anomaly "
                        f"({stderr_count[0]} bytes)"
                    )
                runtime_entries = sorted(
                    item.name for item in runtime_root.iterdir()
                )
                if runtime_entries:
                    raise EpisodeRunnerError(
                        "candidate worker wrote runtime files"
                    )
                process_evidence = {
                    "worker_pid": process.pid,
                    "return_code": return_code,
                    "stderr_bytes": stderr_count[0],
                    "stderr_sha256": hashlib.sha256(
                        b"".join(stderr_chunks)
                    ).hexdigest(),
                    "stderr_overflow": stderr_overflow[0],
                    "trailing_stdout_lines": len(trailing_stdout),
                    "runtime_entries": runtime_entries,
                    "runtime_root_sha256": hashlib.sha256(
                        str(runtime_root).encode("utf-8")
                    ).hexdigest(),
                    "environment_keys": sorted(environment),
                    "environment_secret_keys_forwarded": False,
                    "worker_source_sha256": worker_before,
                    "candidate_subprocess_isolated": True,
                }
            worker_after = hashlib.sha256(
                self.worker_script.read_bytes()
            ).hexdigest()
            archive_after = _candidate_read_only_manifest(
                self.candidate_root,
                repository_root=self.repository_root,
            )
            dependency_after = bind_runtime_dependency_root(
                self.runtime_dependency_root
            )
            _assert_runtime_dependency_tree_read_only(
                self.runtime_dependency_root
            )
            source_after = self._probe_source()
            if (
                worker_after != worker_before
                or archive_after != archive_before
                or dependency_after != dependency_before
                or source_after != source_before
            ):
                raise EpisodeRunnerError(
                    "candidate/evaluator source changed during episode"
                )
            assert protocol.worker_result is not None
            surfaces = protocol.evidence_surfaces()
            evidence.update(
                {
                    "status": "complete",
                    "candidate_archive_before": archive_before,
                    "candidate_archive_after": archive_after,
                    "runtime_dependency_before": dependency_before,
                    "runtime_dependency_after": dependency_after,
                    "runtime_dependency_binding_sha256": canonical_digest(
                        dependency_before
                    ),
                    "source_binding": source_before,
                    "source_binding_sha256": canonical_digest(source_before),
                    "process": process_evidence,
                    **surfaces,
                    "candidate_reported_isolation": {
                        "application_isolation": copy.deepcopy(
                            protocol.worker_result["application_isolation"]
                        ),
                        "repo_import_closure": copy.deepcopy(
                            protocol.worker_result["repo_import_closure"]
                        ),
                        "network_guard": copy.deepcopy(
                            protocol.worker_result["network_guard"]
                        ),
                        "accepted_as_parent_authority": False,
                    },
                    "worker_result_sha256": canonical_digest(
                        protocol.worker_result
                    ),
                }
            )
            self.evidence_sink.record(ordinal, evidence)
            return copy.deepcopy(protocol.worker_result)
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if stdout_thread is not None:
                stdout_thread.join(timeout=2)
            if stderr_thread is not None:
                stderr_thread.join(timeout=2)
            evidence.update(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "stderr_bytes": stderr_count[0],
                    "stderr_sha256": hashlib.sha256(
                        b"".join(stderr_chunks)
                    ).hexdigest(),
                }
            )
            if protocol is not None:
                evidence.update(protocol.evidence_surfaces())
            try:
                self.evidence_sink.record(ordinal, evidence)
            except Exception:
                pass
            raise


__all__ = [
    "APPROVED_RUNTIME_DEPENDENCIES",
    "RUNTIME_DEPENDENCY_BINDING_SCHEMA",
    "bind_runtime_dependency_root",
    "candidate_archive_manifest",
    "CandidateEpisodeRunner",
    "census_runtime_dependency_sources",
    "EpisodeRunnerError",
    "EvidenceSink",
    "materialized_runtime_dependencies",
    "RUNNER_EVIDENCE_SCHEMA",
    "ThreadSafeEvidenceSink",
    "validate_runtime_dependency_binding",
    "WORKER_RPC_SCHEMA",
]
