"""Isolated candidate subprocess for the sealed GWIP capability evaluator.

This program is deliberately a transport boundary, not an evaluator.  It
loads only the candidate's public interaction types from an externally
materialized, read-only candidate tree; relays environment and operational
authority calls to the parent; and returns candidate-owned evidence whose
claims remain non-authoritative.

The parent evaluator must independently validate every trace, RunLease
witness, memory transition, source binding, and hard gate.  The Python audit
guard below is defense in depth and is reported honestly as such; it is not an
OS sandbox.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import sysconfig
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


WORKER_REQUEST_SCHEMA = "atanor.gwip-capability-worker-request.v1"
WORKER_RESULT_SCHEMA = "atanor.gwip-capability-worker-result.v1"
WORKER_RPC_SCHEMA = "atanor.gwip-capability-worker-rpc.v1"

_STEP_BUDGET = 24
_MAX_LINE_BYTES = 32 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")

_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "schedule_row_sha256",
        "phase",
        "pair_index",
        "episode_index",
        "arm",
        "environment_seed",
        "policy_seed",
        "step_budget",
        "retain_policy_updates",
        "session_id",
        "goal_ir",
        "environment_spec",
        "policy_memory",
        "policy_memory_sha256",
        "episode_input_sha256",
        "source_binding_sha256",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "schedule_row_sha256",
        "trace",
        "operational_authority",
        "memory_before",
        "memory_before_sha256",
        "memory_after",
        "memory_after_sha256",
        "source_binding_sha256",
        "application_isolation",
        "repo_import_closure",
        "network_guard",
        "worker_claims",
    }
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
_GOAL_INITIALIZER_FIELDS = frozenset(
    {
        "statement",
        "origin",
        "priority",
        "parent_goal_ids",
        "constraints",
        "metadata",
    }
)
_GOAL_REQUIRED_FIELDS = frozenset({"statement", "origin", "metadata"})
_GOAL_CANONICAL_FIELDS = frozenset(
    {
        "schema_version",
        "contract_id",
        "content_hash",
        "contract_type",
        "statement",
        "origin",
        "priority",
        "parent_goal_ids",
        "constraints",
        "metadata",
        "can_authorize_actions",
        "can_override_safety",
    }
)
_AUXILIARY_SESSIONS = (
    "structural_reexecution",
    "determinism_a",
    "determinism_b",
    "fresh_reexecution",
)

_PROTOCOL_OUT: Any = None


class CapabilityWorkerError(ValueError):
    """A worker transport, isolation, or candidate contract is invalid."""


class _UnavailableOptionalDependency(ModuleType):
    """Fail closed if an unrelated eager package import touches NumPy.

    ``packages.fusion_loop.__init__`` eagerly imports the legacy membrane,
    which imports NumPy but does not use it while the two sealed interactive
    modules are loaded or executed.  NumPy is installed only in the operator's
    user site on the evaluation host, and exposing that entire unsealed site
    would weaken the subprocess source boundary.  This sentinel permits the
    otherwise inert import statement while making any actual NumPy access a
    terminal worker failure.
    """

    def __getattr__(self, name: str) -> Any:
        raise CapabilityWorkerError(
            "sealed interactive candidate attempted to use unavailable "
            f"optional dependency numpy.{name}"
        )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def episode_input_digest(
    *,
    goal_ir: Mapping[str, Any],
    environment_spec: Mapping[str, Any],
) -> str:
    if type(goal_ir) is not dict or type(environment_spec) is not dict:
        raise CapabilityWorkerError("episode input must contain exact objects")
    return canonical_digest(
        {
            "schema_version": "atanor.gwip-capability-episode-input.v1",
            "goal_ir": copy.deepcopy(dict(goal_ir)),
            "environment_spec": copy.deepcopy(dict(environment_spec)),
        }
    )


def _strict_json_line(raw: bytes, *, label: str) -> dict[str, Any]:
    if (
        not raw
        or len(raw) > _MAX_LINE_BYTES
        or not raw.endswith(b"\n")
    ):
        raise CapabilityWorkerError(f"{label} line is missing or too large")

    def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CapabilityWorkerError(
                    f"{label} duplicate JSON key: {key}"
                )
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CapabilityWorkerError(
                    f"{label} contains non-finite number: {token}"
                )
            ),
        )
    except CapabilityWorkerError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CapabilityWorkerError(f"{label} is not strict JSON") from exc
    if type(value) is not dict:
        raise CapabilityWorkerError(f"{label} root must be an exact object")
    return value


def _read_protocol_line(*, label: str) -> dict[str, Any]:
    return _strict_json_line(
        sys.stdin.buffer.readline(_MAX_LINE_BYTES + 1),
        label=label,
    )


def _emit(value: Mapping[str, Any]) -> None:
    if _PROTOCOL_OUT is None:
        raise CapabilityWorkerError("worker protocol output is not initialized")
    _PROTOCOL_OUT.write(
        canonical_json_bytes(dict(value)).decode("utf-8") + "\n"
    )
    _PROTOCOL_OUT.flush()


def validate_worker_request(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact harness request without importing the harness."""

    if type(value) is not dict or frozenset(value) != _REQUEST_FIELDS:
        raise CapabilityWorkerError("worker request fields mismatch")
    if value.get("schema_version") != WORKER_REQUEST_SCHEMA:
        raise CapabilityWorkerError("worker request schema mismatch")
    phase = value.get("phase")
    retain = value.get("retain_policy_updates")
    if (
        type(value.get("ordinal")) is not int
        or value["ordinal"] < 0
        or _SHA256_RE.fullmatch(str(value.get("schedule_row_sha256")))
        is None
        or phase not in {"support", "target"}
        or type(value.get("pair_index")) is not int
        or value["pair_index"] < 0
        or type(value.get("environment_seed")) is not int
        or type(value.get("policy_seed")) is not int
        or value.get("step_budget") != _STEP_BUDGET
        or type(retain) is not bool
        or (phase == "target" and retain)
        or type(value.get("session_id")) is not str
        or _SESSION_RE.fullmatch(value["session_id"]) is None
        or type(value.get("goal_ir")) is not dict
        or type(value.get("environment_spec")) is not dict
        or type(value.get("policy_memory")) is not dict
        or value.get("policy_memory_sha256")
        != canonical_digest(value["policy_memory"])
        or value.get("episode_input_sha256")
        != episode_input_digest(
            goal_ir=value["goal_ir"],
            environment_spec=value["environment_spec"],
        )
        or _SHA256_RE.fullmatch(str(value.get("source_binding_sha256")))
        is None
    ):
        raise CapabilityWorkerError("worker request value invalid")
    if phase == "support":
        if (
            type(value.get("episode_index")) is not int
            or value["episode_index"] < 0
            or value.get("arm") is not None
        ):
            raise CapabilityWorkerError(
                "support worker request identity invalid"
            )
    elif (
        value.get("episode_index") is not None
        or value.get("arm")
        not in {"matched_warm", "cold", "mismatched_warm"}
    ):
        raise CapabilityWorkerError("target worker request identity invalid")
    goal_fields = frozenset(value["goal_ir"])
    if not (
        _GOAL_REQUIRED_FIELDS <= goal_fields <= _GOAL_INITIALIZER_FIELDS
        or goal_fields == _GOAL_CANONICAL_FIELDS
    ):
        raise CapabilityWorkerError("GoalIR input fields mismatch")
    if (
        type(value["goal_ir"].get("statement")) is not str
        or not value["goal_ir"]["statement"].strip()
        or type(value["goal_ir"].get("origin")) is not str
        or not value["goal_ir"]["origin"]
        or type(value["goal_ir"].get("metadata")) is not dict
    ):
        raise CapabilityWorkerError("GoalIR input value invalid")
    return copy.deepcopy(dict(value))


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_within(left, right) or _path_within(right, left)


def _stdlib_import_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for name in ("stdlib", "platstdlib"):
        raw = sysconfig.get_path(name)
        if raw:
            path = Path(raw).resolve(strict=True)
            if path.is_dir():
                roots.append(path)
    dlls = (Path(sys.base_prefix) / "DLLs").resolve()
    if dlls.is_dir():
        roots.append(dlls)
    return tuple(dict.fromkeys(roots))


def _third_party_import_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for name in ("purelib", "platlib"):
        raw = sysconfig.get_path(name)
        if raw:
            path = Path(raw).resolve()
            if path.is_dir():
                roots.append(path)
    return tuple(dict.fromkeys(roots))


def _within_stdlib(
    path: Path,
    *,
    stdlib_roots: tuple[Path, ...],
    third_party_roots: tuple[Path, ...],
) -> bool:
    return any(_path_within(path, root) for root in stdlib_roots) and not any(
        _path_within(path, root) for root in third_party_roots
    )


def _configure_candidate_root() -> tuple[Path, Path, Path, Path]:
    candidate_raw = os.environ.pop(
        "ATANOR_GWIP_CAPABILITY_CANDIDATE_ROOT",
        "",
    )
    dependency_raw = os.environ.pop(
        "ATANOR_GWIP_CAPABILITY_DEPENDENCY_ROOT",
        "",
    )
    runtime_raw = os.environ.pop(
        "ATANOR_GWIP_CAPABILITY_RUNTIME_ROOT",
        "",
    )
    if (
        not candidate_raw
        or not dependency_raw
        or not runtime_raw
        or sys.flags.no_site != 1
        or sys.flags.no_user_site != 1
    ):
        raise CapabilityWorkerError(
            "sealed roots and -S/PYTHONNOUSERSITE isolation are required"
        )
    candidate_root = Path(candidate_raw).resolve(strict=True)
    dependency_root = Path(dependency_raw).resolve(strict=True)
    runtime_root = Path(runtime_raw).resolve(strict=True)
    worker_repo = Path(__file__).resolve(strict=True).parents[1]
    if (
        not (candidate_root / "packages").is_dir()
        or not dependency_root.is_dir()
        or not runtime_root.is_dir()
        or _paths_overlap(candidate_root, worker_repo)
        or _paths_overlap(dependency_root, worker_repo)
        or _paths_overlap(runtime_root, worker_repo)
        or _paths_overlap(candidate_root, dependency_root)
        or _paths_overlap(candidate_root, runtime_root)
        or _paths_overlap(dependency_root, runtime_root)
    ):
        raise CapabilityWorkerError(
            "candidate/dependency/runtime roots are invalid or not isolated"
        )
    for root in (candidate_root, dependency_root, runtime_root):
        if root.is_symlink():
            raise CapabilityWorkerError(
                "candidate/dependency/runtime root is a symlink"
            )

    # No working-tree package object or import path may survive into the
    # candidate context.
    for name in tuple(sys.modules):
        if name == "packages" or name.startswith("packages."):
            del sys.modules[name]
    stdlib_roots = _stdlib_import_roots()
    third_party_roots = _third_party_import_roots()
    retained: list[str] = []
    for raw in sys.path:
        try:
            resolved = Path(raw or os.curdir).resolve()
        except OSError:
            continue
        if _within_stdlib(
            resolved,
            stdlib_roots=stdlib_roots,
            third_party_roots=third_party_roots,
        ):
            retained.append(raw)
    sys.path[:] = [
        str(candidate_root),
        str(dependency_root),
        *retained,
    ]
    os.chdir(runtime_root)

    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
    windir = os.environ.get("WINDIR")
    os.environ.clear()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["TMP"] = str(runtime_root)
    os.environ["TEMP"] = str(runtime_root)
    if system_root:
        os.environ["SYSTEMROOT"] = system_root
    if windir:
        os.environ["WINDIR"] = windir
    sys.argv[:] = ["gwip-capability-worker"]
    return candidate_root, dependency_root, runtime_root, worker_repo


class _WorkerIsolationGuard:
    """In-process defense-in-depth guard; explicitly not an OS sandbox."""

    def __init__(
        self,
        *,
        candidate_root: Path,
        dependency_root: Path,
        runtime_root: Path,
        worker_repo: Path,
    ) -> None:
        self.candidate_root = candidate_root
        self.dependency_root = dependency_root
        self.runtime_root = runtime_root
        self.worker_repo = worker_repo
        self.blocked_network = 0
        self.blocked_child = 0
        self.blocked_write = 0
        self.blocked_workspace_read = 0
        self._installed = False
        self._network_probe_socket: Any = None
        self._deny_read_roots = _third_party_import_roots()
        self._denied_source_probe: Path | None = None
        self._denied_extension_probe: Path | None = None
        for root in self._deny_read_roots:
            for relative in (
                Path("_distutils_hack") / "__init__.py",
                Path("requests") / "__init__.py",
            ):
                candidate = root / relative
                if candidate.is_file():
                    self._denied_source_probe = candidate
                    break
            if self._denied_source_probe is not None:
                break
        for root in self._deny_read_roots:
            extensions = sorted(
                root.glob("_cffi_backend.*"),
                key=lambda item: item.name,
            )
            self._denied_extension_probe = next(
                (path for path in extensions if path.is_file()),
                None,
            )
            if self._denied_extension_probe is not None:
                break
        import_roots: list[Path] = []
        for raw in sys.path:
            try:
                path = Path(raw or os.curdir).resolve(strict=True)
            except OSError:
                continue
            if path.is_dir() and not _path_within(path, worker_repo):
                import_roots.append(path)
        self._read_roots = tuple(
            dict.fromkeys(
                Path(item).resolve()
                for item in (
                    candidate_root,
                    dependency_root,
                    runtime_root,
                    *import_roots,
                )
            )
        )

    @staticmethod
    def _path(value: Any) -> Path | None:
        if isinstance(value, int):
            return None
        try:
            return Path(os.path.abspath(os.fsdecode(value)))
        except (OSError, TypeError, ValueError):
            return None

    def _read_allowed(self, path: Path) -> bool:
        if any(
            _path_within(path, root) for root in self._deny_read_roots
        ):
            return False
        return any(_path_within(path, root) for root in self._read_roots)

    @staticmethod
    def _open_is_write(mode: Any, flags: Any) -> bool:
        if isinstance(mode, str) and any(
            item in mode for item in ("w", "a", "x", "+")
        ):
            return True
        if isinstance(flags, int):
            mask = (
                os.O_WRONLY
                | os.O_RDWR
                | os.O_APPEND
                | os.O_CREAT
                | os.O_TRUNC
            )
            return bool(flags & mask)
        return False

    def _audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args:
            path = self._path(args[0])
            is_write = self._open_is_write(
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
            )
            if is_write:
                self.blocked_write += 1
                raise PermissionError("GWIP candidate writes are disabled")
            if path is not None and not self._read_allowed(path):
                self.blocked_workspace_read += 1
                raise PermissionError(
                    "GWIP external filesystem reads are disabled"
                )
        elif event == "import" and len(args) > 1 and args[1]:
            path = self._path(args[1])
            if path is not None and not self._read_allowed(path):
                self.blocked_workspace_read += 1
                raise PermissionError(
                    "GWIP unbound module loading is disabled"
                )
        elif event in {"os.listdir", "os.scandir"} and args:
            path = self._path(args[0])
            if path is not None and not self._read_allowed(path):
                self.blocked_workspace_read += 1
                raise PermissionError(
                    "GWIP external filesystem enumeration is disabled"
                )
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chdir",
            "os.chmod",
            "os.truncate",
            "os.utime",
            "os.rename",
            "os.replace",
        }:
            self.blocked_write += 1
            raise PermissionError(
                "GWIP candidate filesystem mutation is disabled"
            )
        elif event.startswith("subprocess.") or event in {
            "os.system",
            "os.posix_spawn",
            "os.spawn",
            "ctypes.dlopen",
            "ctypes.dlsym",
        }:
            self.blocked_child += 1
            raise PermissionError("GWIP child/native execution is disabled")
        elif event in {
            "socket.__new__",
            "socket.bind",
            "socket.connect",
            "socket.getaddrinfo",
            "socket.sendto",
        }:
            self.blocked_network += 1
            raise PermissionError("GWIP network access is disabled")

    def install(self) -> None:
        if self._installed:
            raise CapabilityWorkerError("candidate worker guard already installed")
        self._installed = True

        def network_blocked(*_args: Any, **_kwargs: Any) -> Any:
            self.blocked_network += 1
            raise PermissionError("GWIP network access is disabled")

        def child_blocked(*_args: Any, **_kwargs: Any) -> Any:
            self.blocked_child += 1
            raise PermissionError("GWIP child/native execution is disabled")

        import ctypes  # noqa: PLC0415
        import socket  # noqa: PLC0415

        try:
            import _winapi  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError:  # pragma: no cover - non-Windows
            _winapi = None

        original_socket_type = socket.socket
        self._network_probe_socket = original_socket_type(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        sys.addaudithook(self._audit)

        for name in (
            "accept",
            "bind",
            "connect",
            "connect_ex",
            "listen",
            "recv",
            "recv_into",
            "recvfrom",
            "recvfrom_into",
            "recvmsg",
            "recvmsg_into",
            "send",
            "sendall",
            "sendmsg",
            "sendto",
        ):
            if hasattr(original_socket_type, name):
                setattr(original_socket_type, name, network_blocked)
        socket.create_connection = network_blocked  # type: ignore[assignment]
        if hasattr(socket, "create_server"):
            socket.create_server = network_blocked  # type: ignore[assignment]
        if hasattr(socket, "socketpair"):
            socket.socketpair = network_blocked  # type: ignore[assignment]
        for name in (
            "getaddrinfo",
            "gethostbyaddr",
            "gethostbyname",
            "gethostbyname_ex",
            "getnameinfo",
        ):
            if hasattr(socket, name):
                setattr(socket, name, network_blocked)
        if _winapi is not None and hasattr(_winapi, "CreateProcess"):
            _winapi.CreateProcess = child_blocked  # type: ignore[assignment]
        if _winapi is not None:
            for name in (
                "CreateFile",
                "DeleteFile",
                "MoveFileEx",
                "ReadFile",
                "WriteFile",
            ):
                if hasattr(_winapi, name):
                    setattr(_winapi, name, child_blocked)
        subprocess.Popen = child_blocked  # type: ignore[assignment]
        os.system = child_blocked  # type: ignore[assignment]
        if hasattr(os, "startfile"):
            os.startfile = child_blocked  # type: ignore[assignment]
        for name in tuple(dir(os)):
            if name.startswith("spawn") and callable(getattr(os, name)):
                setattr(os, name, child_blocked)
        # Keep ctypes imported before the hook so a candidate cannot bypass the
        # audit boundary merely by reusing an already-loaded native loader.
        _ = ctypes

    def application_probes(self) -> dict[str, bool]:
        import ctypes  # noqa: PLC0415

        results = {
            "child_process_blocked": False,
            "native_child_process_blocked": False,
            "native_library_loading_blocked": False,
            "native_file_access_blocked": False,
            "nonledger_write_blocked": False,
            "evaluator_source_read_blocked": False,
            "seed_manifest_read_blocked": False,
            "evaluator_workspace_enumeration_blocked": False,
            "system_site_source_read_blocked": False,
            "system_site_extension_load_blocked": False,
            "evaluator_main_hidden": False,
            "runtime_cwd_isolated": Path.cwd() == self.runtime_root,
            "sensitive_environment_scrubbed": not any(
                key.startswith("ATANOR_") for key in os.environ
            )
            and "PYTHONPATH" not in os.environ,
        }
        try:
            subprocess.Popen([sys.executable, "-c", "pass"])
        except PermissionError:
            results["child_process_blocked"] = True
        if os.name == "nt":
            try:
                import _winapi  # type: ignore[import-not-found]  # noqa: PLC0415

                _winapi.CreateProcess()
            except PermissionError:
                results["native_child_process_blocked"] = True
        else:
            results["native_child_process_blocked"] = True
        try:
            ctypes.CDLL("atanor-gwip-capability-forbidden-native-library")
        except PermissionError:
            results["native_library_loading_blocked"] = True
        if os.name == "nt":
            try:
                import _winapi  # type: ignore[import-not-found]  # noqa: PLC0415

                _winapi.CreateFile()
            except PermissionError:
                results["native_file_access_blocked"] = True
        else:
            results["native_file_access_blocked"] = True
        try:
            (self.runtime_root / "forbidden-write-probe").write_text(
                "blocked",
                encoding="utf-8",
            )
        except PermissionError:
            results["nonledger_write_blocked"] = True
        try:
            Path(__file__).resolve(strict=True).read_bytes()
        except PermissionError:
            results["evaluator_source_read_blocked"] = True
        try:
            (
                self.worker_repo
                / "data"
                / "eval"
                / "gwip_capability_seed_manifest_v1.json"
            ).read_bytes()
        except PermissionError:
            results["seed_manifest_read_blocked"] = True
        try:
            list(self.worker_repo.iterdir())
        except PermissionError:
            results["evaluator_workspace_enumeration_blocked"] = True
        if self._denied_source_probe is None:
            raise CapabilityWorkerError(
                "system-site source denial probe is unavailable"
            )
        try:
            self._denied_source_probe.read_bytes()
        except PermissionError:
            results["system_site_source_read_blocked"] = True
        if self._denied_extension_probe is None:
            raise CapabilityWorkerError(
                "system-site extension denial probe is unavailable"
            )
        try:
            import importlib.machinery  # noqa: PLC0415
            import importlib.util  # noqa: PLC0415

            loader = importlib.machinery.ExtensionFileLoader(
                "_cffi_backend",
                str(self._denied_extension_probe),
            )
            spec = importlib.util.spec_from_file_location(
                "_cffi_backend",
                self._denied_extension_probe,
                loader=loader,
            )
            if spec is None:
                raise CapabilityWorkerError(
                    "system-site extension denial probe spec is unavailable"
                )
            importlib.util.module_from_spec(spec)
        except PermissionError:
            results["system_site_extension_load_blocked"] = True
        results["evaluator_main_hidden"] = not any(
            hasattr(sys.modules["__main__"], name)
            for name in (
                "validate_worker_request",
                "_candidate_run",
                "_configure_candidate_root",
                "CapabilityWorkerError",
            )
        )
        return results

    def network_probes(self) -> dict[str, bool]:
        import socket  # noqa: PLC0415

        results = {
            "external_network_blocked": False,
            "udp_sendto_blocked": False,
            "dns_resolution_blocked": False,
        }
        try:
            socket.create_connection(("198.51.100.1", 9), timeout=0.001)
        except PermissionError:
            results["external_network_blocked"] = True
        try:
            assert self._network_probe_socket is not None
            self._network_probe_socket.sendto(b"x", ("127.0.0.1", 9))
        except PermissionError:
            results["udp_sendto_blocked"] = True
        finally:
            if self._network_probe_socket is not None:
                self._network_probe_socket.close()
                self._network_probe_socket = None
        try:
            socket.getaddrinfo("example.invalid", 443)
        except PermissionError:
            results["dns_resolution_blocked"] = True
        return results

    def application_receipt(
        self,
        probes: Mapping[str, bool],
    ) -> dict[str, Any]:
        return {
            "schema_version": "atanor.gwip-capability-application-isolation.v1",
            "kind": "python_audit_guard_not_os_sandbox",
            "probes": copy.deepcopy(dict(probes)),
            "blocked_event_counts": {
                "child_or_native": self.blocked_child,
                "write": self.blocked_write,
                "workspace_read": self.blocked_workspace_read,
            },
            "passed": bool(probes) and all(probes.values()),
        }

    def network_receipt(
        self,
        probes: Mapping[str, bool],
    ) -> dict[str, Any]:
        return {
            "schema_version": "atanor.gwip-capability-network-guard.v1",
            "kind": "python_audit_and_socket_guard_not_network_namespace",
            "probes": copy.deepcopy(dict(probes)),
            "blocked_event_count": self.blocked_network,
            "passed": bool(probes) and all(probes.values()),
        }


class _RpcEnvironment:
    __slots__ = ("_session", "_call_id")

    def __init__(self, session: str) -> None:
        self._session = session
        self._call_id = 0

    def _call(self, operation: str, payload: Mapping[str, Any]) -> Any:
        call_id = self._call_id
        self._call_id += 1
        _emit(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "environment_request",
                "session": self._session,
                "call_id": call_id,
                "operation": operation,
                "payload": copy.deepcopy(dict(payload)),
            }
        )
        response = _read_protocol_line(
            label="candidate worker environment response"
        )
        if (
            frozenset(response) != _RPC_RESPONSE_FIELDS
            or response.get("schema_version") != WORKER_RPC_SCHEMA
            or response.get("type") != "environment_response"
            or response.get("session") != self._session
            or response.get("call_id") != call_id
            or response.get("ok") is not True
            or response.get("error") is not None
        ):
            raise CapabilityWorkerError(
                "candidate worker environment response invalid"
            )
        return copy.deepcopy(response["result"])

    def reset(self, seed: int) -> Any:
        return self._call("reset", {"seed": seed})

    def observe(self) -> Any:
        return self._call("observe", {})

    def valid_actions(self) -> Any:
        return self._call("valid_actions", {})

    def step(self, action_id: str) -> Any:
        return self._call("step", {"action_id": action_id})

    def stop(self, reason: str) -> Any:
        return self._call("stop", {"reason": reason})


def _authority_rpc(
    *,
    operation: str,
    call_id: int,
    payload: Mapping[str, Any],
) -> Any:
    _emit(
        {
            "schema_version": WORKER_RPC_SCHEMA,
            "type": "authority_request",
            "session": "authority:primary",
            "call_id": call_id,
            "operation": operation,
            "payload": copy.deepcopy(dict(payload)),
        }
    )
    response = _read_protocol_line(
        label="candidate worker authority response"
    )
    if (
        frozenset(response) != _RPC_RESPONSE_FIELDS
        or response.get("schema_version") != WORKER_RPC_SCHEMA
        or response.get("type") != "authority_response"
        or response.get("session") != "authority:primary"
        or response.get("call_id") != call_id
        or response.get("ok") is not True
        or response.get("error") is not None
    ):
        raise CapabilityWorkerError(
            "candidate worker authority response invalid"
        )
    return copy.deepcopy(response["result"])


def _build_goal(
    raw: Mapping[str, Any],
    *,
    goal_type: type,
    origin_type: type,
) -> Any:
    """Rehydrate every caller-supplied GoalIR field; never hard-code a goal."""

    fields = frozenset(raw)
    canonical_input = fields == _GOAL_CANONICAL_FIELDS
    initializer = {
        "statement": raw["statement"],
        "origin": origin_type(raw["origin"]),
        "metadata": copy.deepcopy(raw["metadata"]),
    }
    if "priority" in raw:
        initializer["priority"] = raw["priority"]
    if "parent_goal_ids" in raw:
        if type(raw["parent_goal_ids"]) is not list:
            raise CapabilityWorkerError("GoalIR parent IDs must be an array")
        initializer["parent_goal_ids"] = tuple(raw["parent_goal_ids"])
    if "constraints" in raw:
        if type(raw["constraints"]) is not list:
            raise CapabilityWorkerError("GoalIR constraints must be an array")
        initializer["constraints"] = tuple(raw["constraints"])
    goal = goal_type(**initializer)
    materialized = goal.to_dict()
    if canonical_input:
        if materialized != raw:
            raise CapabilityWorkerError(
                "canonical GoalIR input failed identity reconstruction"
            )
    else:
        for name, expected in raw.items():
            actual = materialized.get(name)
            if actual != expected:
                raise CapabilityWorkerError(
                    f"GoalIR field changed during reconstruction: {name}"
                )
    return goal


def _module_closure(
    candidate_root: Path,
    dependency_root: Path,
    worker_repo: Path,
) -> dict[str, Any]:
    source: list[dict[str, str]] = []
    dependencies: list[dict[str, str]] = []
    outside_candidate: list[dict[str, str]] = []
    outside_allowed: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    stdlib_count = 0
    stdlib_roots = _stdlib_import_roots()
    third_party_roots = _third_party_import_roots()
    for name, module in sorted(sys.modules.items()):
        raw = getattr(module, "__file__", None)
        if not raw:
            continue
        try:
            path = Path(str(raw)).resolve(strict=True)
        except OSError:
            if not str(raw).startswith("<"):
                unresolved.append({"module": name, "path": str(raw)})
            continue
        is_candidate_namespace = (
            name == "packages" or name.startswith("packages.")
        )
        row = {
            "module": name,
            "path": "",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if _path_within(path, candidate_root):
            row["path"] = path.relative_to(candidate_root).as_posix()
            if is_candidate_namespace:
                source.append(row)
            else:
                outside_allowed.append(
                    {"module": name, "path": str(path)}
                )
        elif _path_within(path, dependency_root):
            row["path"] = path.relative_to(dependency_root).as_posix()
            if name == "_cffi_backend" or name == "cryptography" or name.startswith(
                "cryptography."
            ):
                dependencies.append(row)
            else:
                outside_allowed.append(
                    {"module": name, "path": str(path)}
                )
        elif _within_stdlib(
            path,
            stdlib_roots=stdlib_roots,
            third_party_roots=third_party_roots,
        ):
            stdlib_count += 1
            if is_candidate_namespace:
                outside_candidate.append(
                    {"module": name, "path": str(path)}
                )
        else:
            outside_allowed.append({"module": name, "path": str(path)})
            if is_candidate_namespace:
                outside_candidate.append(
                    {"module": name, "path": str(path)}
                )
    source.sort(key=lambda item: (item["module"], item["path"]))
    dependencies.sort(key=lambda item: (item["module"], item["path"]))
    names = {item["module"] for item in source}
    required = {
        "packages.cognitive_core",
        "packages.fusion_loop.interactive",
        "packages.fusion_loop.interactive_organs",
    }
    worker_repo_loaded = [
        item
        for item in source
        if _path_within(candidate_root / item["path"], worker_repo)
    ]
    return {
        "schema_version": "atanor.gwip-capability-import-closure.v1",
        "candidate_modules": source,
        "candidate_modules_sha256": canonical_digest(source),
        "dependency_modules": dependencies,
        "dependency_modules_sha256": canonical_digest(dependencies),
        "approved_dependency_modules": [
            "_cffi_backend",
            "cryptography",
        ],
        "outside_candidate_root_modules": outside_candidate,
        "outside_allowed_root_modules": outside_allowed,
        "unresolved_file_modules": unresolved,
        "stdlib_module_count": stdlib_count,
        "required_public_modules": sorted(required),
        "missing_public_modules": sorted(required - names),
        "working_tree_modules": worker_repo_loaded,
        "passed": (
            bool(source)
            and required <= names
            and not outside_candidate
            and not outside_allowed
            and not unresolved
            and not worker_repo_loaded
        ),
    }


def _candidate_run(
    safe_request: Mapping[str, Any],
    *,
    candidate_root: Path,
    dependency_root: Path,
    runtime_root: Path,
    worker_repo: Path,
) -> dict[str, Any]:
    guard = _WorkerIsolationGuard(
        candidate_root=candidate_root,
        dependency_root=dependency_root,
        runtime_root=runtime_root,
        worker_repo=worker_repo,
    )
    guard.install()
    # Candidate code cannot recover this worker by importing ``__main__``.
    sys.modules["__main__"] = ModuleType("__main__")
    # Do not expose the operator's unsealed user-site dependency tree merely
    # because the legacy package initializer contains an unused eager import.
    numpy_sentinel = _UnavailableOptionalDependency("numpy")
    # The evaluator's own module-census code reads ``__file__`` from every
    # loaded module.  Make that introspection inert without making any NumPy
    # capability available to candidate code.
    numpy_sentinel.__file__ = None
    sys.modules["numpy"] = numpy_sentinel
    application_probes = guard.application_probes()
    network_probes = guard.network_probes()

    from packages.cognitive_core import GoalIR, GoalOrigin  # noqa: PLC0415
    from packages.fusion_loop.interactive import (  # noqa: PLC0415
        AuthorizationWitness,
        GenericWorldInteractionLoop,
        reexecute_interactive_trace,
    )
    from packages.fusion_loop.interactive_organs import (  # noqa: PLC0415
        AtanorInteractivePolicy,
    )

    class ParentAuthority:
        def __init__(self) -> None:
            self._call_id = 0

        def authorize(self, action_id: str, step_index: int) -> Any:
            raw = _authority_rpc(
                operation="authorize",
                call_id=self._call_id,
                payload={
                    "action_id": action_id,
                    "step_index": step_index,
                },
            )
            self._call_id += 1
            if type(raw) is not dict:
                raise CapabilityWorkerError(
                    "parent authority witness is not an object"
                )
            expected = {
                "action_id",
                "step_index",
                "granted",
                "reason",
                "authority_kind",
                "operational_evidence",
            }
            if frozenset(raw) != expected:
                raise CapabilityWorkerError(
                    "parent authority witness fields mismatch"
                )
            return AuthorizationWitness(
                action_id=raw["action_id"],
                step_index=raw["step_index"],
                granted=raw["granted"],
                reason=raw["reason"],
                authority_kind=raw["authority_kind"],
                operational_evidence=raw["operational_evidence"],
            )

        def finish(self, reason: str) -> Any:
            raw = _authority_rpc(
                operation="finish",
                call_id=self._call_id,
                payload={"reason": reason},
            )
            self._call_id += 1
            if type(raw) is not dict:
                raise CapabilityWorkerError(
                    "parent authority finish receipt is not an object"
                )
            return raw

    class AuxiliaryAuthority:
        """Non-production authority used only after primary evidence is sealed."""

        def authorize(self, action_id: str, step_index: int) -> Any:
            return AuthorizationWitness(
                action_id=action_id,
                step_index=step_index,
                granted=True,
                reason="auxiliary_reexecution_fixture_granted",
                authority_kind="non_authoritative_auxiliary_fixture",
                operational_evidence={
                    "production_authority": False,
                    "worker_claim_only": True,
                },
            )

        def finish(self, reason: str) -> Any:
            return {
                "finished": True,
                "reason": reason,
                "production_authority": False,
            }

    memory_before = copy.deepcopy(safe_request["policy_memory"])
    goal = _build_goal(
        safe_request["goal_ir"],
        goal_type=GoalIR,
        origin_type=GoalOrigin,
    )
    policy = AtanorInteractivePolicy.from_memory(memory_before)
    trace = GenericWorldInteractionLoop(
        authority=ParentAuthority(),
        policy=policy,
        require_run_lease=False,
    ).run(
        _RpcEnvironment("primary"),
        goal,
        environment_seed=safe_request["environment_seed"],
        policy_seed=safe_request["policy_seed"],
        step_budget=safe_request["step_budget"],
        retain_policy_updates=safe_request["retain_policy_updates"],
        session_id=safe_request["session_id"],
    )
    trace_dict = trace.to_dict()
    memory_after = trace.memory_after.to_dict()
    primary_result = {
        "trace": trace_dict,
        "operational_authority": [
            step.authorization.to_dict() for step in trace.steps
        ],
        "memory_before": memory_before,
        "memory_before_sha256": canonical_digest(memory_before),
        "memory_after": memory_after,
        "memory_after_sha256": canonical_digest(memory_after),
    }
    if frozenset(primary_result) != _PRIMARY_RESULT_FIELDS:
        raise AssertionError("primary result fields drifted")
    # The parent seals the production-authority result before any replay,
    # determinism, or fresh-environment auxiliary session can begin.
    _emit(
        {
            "schema_version": WORKER_RPC_SCHEMA,
            "type": "primary_result",
            "session": "primary_result",
            "call_id": 0,
            "result": primary_result,
        }
    )
    primary_ack = _read_protocol_line(
        label="candidate worker primary-result acknowledgement"
    )
    if (
        frozenset(primary_ack) != _RPC_RESPONSE_FIELDS
        or primary_ack.get("schema_version") != WORKER_RPC_SCHEMA
        or primary_ack.get("type") != "primary_result_ack"
        or primary_ack.get("session") != "primary_result"
        or primary_ack.get("call_id") != 0
        or primary_ack.get("ok") is not True
        or primary_ack.get("result") != {"sealed": True}
        or primary_ack.get("error") is not None
    ):
        raise CapabilityWorkerError("candidate primary result was not sealed")

    structural = reexecute_interactive_trace(
        lambda: _RpcEnvironment(_AUXILIARY_SESSIONS[0]),
        trace,
        fixture_authority_verifier=lambda witness: witness.granted is True,
        expected_goal=goal,
        expected_memory_before=memory_before,
    )

    def duplicate(environment_session: str) -> Any:
        duplicate_policy = AtanorInteractivePolicy.from_memory(memory_before)
        return GenericWorldInteractionLoop(
            authority=AuxiliaryAuthority(),
            policy=duplicate_policy,
            require_run_lease=False,
        ).run(
            _RpcEnvironment(environment_session),
            goal,
            environment_seed=safe_request["environment_seed"],
            policy_seed=safe_request["policy_seed"],
            step_budget=safe_request["step_budget"],
            retain_policy_updates=safe_request["retain_policy_updates"],
            session_id=f"{safe_request['session_id']}:determinism",
        )

    duplicate_a = duplicate(_AUXILIARY_SESSIONS[1])
    duplicate_b = duplicate(_AUXILIARY_SESSIONS[2])
    fresh = reexecute_interactive_trace(
        lambda: _RpcEnvironment(_AUXILIARY_SESSIONS[3]),
        trace,
        fixture_authority_verifier=lambda witness: witness.granted is True,
        expected_goal=goal,
        expected_memory_before=memory_before,
    )
    closure = _module_closure(
        candidate_root,
        dependency_root,
        worker_repo,
    )
    application = guard.application_receipt(application_probes)
    network = guard.network_receipt(network_probes)
    determinism = {
        "trace_a_sha256": duplicate_a.semantic_trace_digest,
        "trace_b_sha256": duplicate_b.semantic_trace_digest,
        "memory_after_a_sha256": canonical_digest(
            duplicate_a.memory_after.to_dict()
        ),
        "memory_after_b_sha256": canonical_digest(
            duplicate_b.memory_after.to_dict()
        ),
        "passed": (
            duplicate_a.semantic_trace_digest
            == duplicate_b.semantic_trace_digest
            and duplicate_a.memory_after == duplicate_b.memory_after
        ),
    }
    result = {
        "schema_version": WORKER_RESULT_SCHEMA,
        "ordinal": safe_request["ordinal"],
        "schedule_row_sha256": safe_request["schedule_row_sha256"],
        **primary_result,
        "source_binding_sha256": safe_request["source_binding_sha256"],
        "application_isolation": application,
        "repo_import_closure": closure,
        "network_guard": network,
        "worker_claims": {
            "schema_version": "atanor.gwip-capability-worker-claims.v1",
            "non_authoritative": True,
            "parent_evaluator_must_reconstruct": True,
            "primary_result_sealed_before_auxiliary_sessions": True,
            "auxiliary_sessions": list(_AUXILIARY_SESSIONS),
            "auxiliary_used_production_authority": False,
            "candidate_structural_verification": structural.to_dict(),
            "candidate_semantic_determinism": determinism,
            "candidate_determinism_trace_a": duplicate_a.to_dict(),
            "candidate_determinism_trace_b": duplicate_b.to_dict(),
            "candidate_fresh_environment_reexecution": fresh.to_dict(),
            "capability_verdict": None,
            "hard_gate_verdict": None,
        },
    }
    if frozenset(result) != _RESULT_FIELDS:
        raise AssertionError("worker result fields drifted")
    return result


def _candidate_worker_main() -> int:
    """Run one exact request.  This entry point is intentionally single-shot."""

    global _PROTOCOL_OUT
    _PROTOCOL_OUT = sys.stdout
    try:
        request = validate_worker_request(
            _read_protocol_line(label="candidate worker request")
        )
        candidate_root, dependency_root, runtime_root, worker_repo = (
            _configure_candidate_root()
        )
        # The evaluator-owned environment specification is used only to bind
        # the request digest.  It is not passed into, or retained on, the
        # candidate execution stack.
        safe_request = {
            key: copy.deepcopy(request[key])
            for key in (
                "ordinal",
                "schedule_row_sha256",
                "environment_seed",
                "policy_seed",
                "step_budget",
                "retain_policy_updates",
                "session_id",
                "goal_ir",
                "policy_memory",
                "source_binding_sha256",
            )
        }
        del request
        with contextlib.redirect_stdout(sys.stderr):
            result = _candidate_run(
                safe_request,
                candidate_root=candidate_root,
                dependency_root=dependency_root,
                runtime_root=runtime_root,
                worker_repo=worker_repo,
            )
        _emit(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "worker_result",
                "result": result,
            }
        )
        return 0
    except Exception as exc:
        _emit(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "worker_failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        return 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments != ["candidate-worker"]:
        raise SystemExit(
            "usage: gwip_capability_worker.py candidate-worker"
        )
    return _candidate_worker_main()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CapabilityWorkerError",
    "WORKER_REQUEST_SCHEMA",
    "WORKER_RESULT_SCHEMA",
    "WORKER_RPC_SCHEMA",
    "canonical_digest",
    "canonical_json_bytes",
    "episode_input_digest",
    "validate_worker_request",
]
