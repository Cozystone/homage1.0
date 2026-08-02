"""Fresh-process worker for the preregistered Pattern #9 OFF/ON comparison.

This worker is deliberately label-blind: it receives only the request inputs
needed to call the two public speech endpoints. Metric labels, forged targets,
gold expectations, thresholds, and verdict logic stay in the parent evaluator.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import tempfile
import hashlib
import ipaddress
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "atanor.pattern09-public-speech-worker-request.v1"
RESULT_SCHEMA = "atanor.pattern09-public-speech-worker-result.v1"
SMOKE_SCHEMA = "atanor.pattern09-public-speech-isolation-smoke.v1"
_MAX_REQUEST_BYTES = 2 * 1024 * 1024
_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "preregistration_id",
        "block_id",
        "condition",
        "python_hash_seed",
        "items",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "query",
        "semantic_context",
        "surface_plan",
    }
)


class WorkerInputError(RuntimeError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WorkerInputError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _load_request(payload: bytes) -> dict[str, Any]:
    if len(payload) > _MAX_REQUEST_BYTES:
        raise WorkerInputError("worker request exceeds size limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                WorkerInputError(f"non-finite JSON number: {token}")
            ),
        )
    except WorkerInputError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise WorkerInputError("worker request is not strict JSON") from exc
    if not isinstance(value, dict):
        raise WorkerInputError("worker request root must be an object")
    return value


def _validate_request(value: dict[str, Any]) -> dict[str, Any]:
    if frozenset(value) != _REQUEST_FIELDS:
        raise WorkerInputError("worker request fields mismatch")
    if (
        value.get("schema_version") != REQUEST_SCHEMA
        or value.get("preregistration_id")
        != "pattern09-public-speech-capability-v1-20260727"
        or value.get("block_id") not in {"OFF_BASELINE", "ON_CANDIDATE"}
        or value.get("condition") not in {"OFF", "ON"}
        or value.get("python_hash_seed") != "0"
    ):
        raise WorkerInputError("worker request identity mismatch")
    if (
        (value["condition"] == "OFF" and value["block_id"] != "OFF_BASELINE")
        or (
            value["condition"] == "ON"
            and value["block_id"] != "ON_CANDIDATE"
        )
    ):
        raise WorkerInputError("worker block/condition mismatch")
    items = value.get("items")
    if not isinstance(items, list) or len(items) != 12:
        raise WorkerInputError("worker requires exactly 12 items")
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or frozenset(item) != _ITEM_FIELDS:
            raise WorkerInputError(f"worker item {index} fields mismatch")
        item_key = item.get("item_key")
        if (
            item.get("index") != index
            or not isinstance(item_key, str)
            or len(item_key) != 64
            or any(char not in "0123456789abcdef" for char in item_key)
            or item_key in seen
            or not isinstance(item.get("query"), str)
            or not item["query"].strip()
            or not isinstance(item.get("semantic_context"), dict)
            or (
                item.get("surface_plan") is not None
                and not isinstance(item.get("surface_plan"), dict)
            )
        ):
            raise WorkerInputError(f"worker item {index} invalid")
        seen.add(item_key)
    return value


def _configure_source_root() -> tuple[Path, Path]:
    raw = os.environ.get("ATANOR_PATTERN09_SOURCE_ROOT")
    if not raw:
        raise WorkerInputError("ATANOR_PATTERN09_SOURCE_ROOT is required")
    source_root = Path(raw).resolve(strict=True)
    api_root = (source_root / "apps" / "api").resolve(strict=True)
    if not (source_root / "packages").is_dir():
        raise WorkerInputError("source root does not contain packages")

    worker_repo = Path(__file__).resolve().parents[1]
    retained: list[str] = []
    for entry in sys.path:
        try:
            resolved = Path(entry or os.curdir).resolve()
            resolved.relative_to(worker_repo)
        except (OSError, ValueError):
            retained.append(entry)
    sys.path[:] = [str(api_root), str(source_root), *retained]
    return source_root, api_root


def _module_path(module: Any) -> str:
    path = Path(str(module.__file__)).resolve(strict=True)
    return str(path)


def _install_network_guard() -> None:
    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_loopback(address: Any) -> bool:
        if not isinstance(address, tuple) or not address:
            return False
        host = str(address[0]).strip("[]").casefold()
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Pattern #9 worker network access is disabled")

    def guarded_create_connection(
        address: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if not is_loopback(address):
            return blocked()
        return original_create_connection(address, *args, **kwargs)

    def guarded_connect(instance: Any, address: Any) -> Any:
        if not is_loopback(address):
            return blocked()
        return original_connect(instance, address)

    def guarded_connect_ex(instance: Any, address: Any) -> Any:
        if not is_loopback(address):
            return blocked()
        return original_connect_ex(instance, address)

    socket.create_connection = guarded_create_connection  # type: ignore[assignment]
    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]


def _network_guard_receipt() -> dict[str, Any]:
    address = ("198.51.100.1", 9)

    def create_connection_blocked() -> bool:
        try:
            socket.create_connection(address, timeout=0.001)
        except RuntimeError as exc:
            return str(exc) == "Pattern #9 worker network access is disabled"
        return False

    def method_blocked(method_name: str) -> bool:
        instance = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                getattr(instance, method_name)(address)
            except RuntimeError as exc:
                return (
                    str(exc)
                    == "Pattern #9 worker network access is disabled"
                )
            return False
        finally:
            instance.close()

    return {
        "external_socket_create_connection_blocked": (
            create_connection_blocked()
        ),
        "external_socket_connect_blocked": method_blocked("connect"),
        "external_socket_connect_ex_blocked": method_blocked("connect_ex"),
        "loopback_only": True,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _repo_import_closure(
    source_root: Path,
    worker_repo: Path,
) -> dict[str, Any]:
    source_records: list[dict[str, str]] = []
    violations: list[dict[str, str]] = []
    for name, module in sorted(sys.modules.items()):
        raw = getattr(module, "__file__", None)
        if not raw:
            continue
        try:
            path = Path(str(raw)).resolve(strict=True)
        except OSError:
            continue
        under_source = _is_within(path, source_root)
        repo_namespace = (
            name == "app"
            or name.startswith("app.")
            or name == "packages"
            or name.startswith("packages.")
        )
        if under_source and repo_namespace:
            source_records.append(
                {
                    "module": name,
                    "path": path.relative_to(source_root).as_posix(),
                }
            )
        elif repo_namespace or (
            _is_within(path, worker_repo)
            and path != Path(__file__).resolve(strict=True)
        ):
            violations.append({"module": name, "path": str(path)})
    encoded = json.dumps(
        source_records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "source_module_count": len(source_records),
        "source_modules_sha256": hashlib.sha256(encoded).hexdigest(),
        "outside_source_repo_modules": violations,
        "forbidden_source_modules_loaded": sorted(
            name
            for name in sys.modules
            if name == "app.main" or name.startswith("app.main.")
        ),
    }


def _build_router_only_app(surface_router: Any) -> Any:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(surface_router.router)
    return app


def _application_isolation(app: Any) -> dict[str, Any]:
    route_paths = {
        str(getattr(route, "path", ""))
        for route in app.routes
        if getattr(route, "path", None)
    }
    return {
        "router_only": True,
        "global_app_main_loaded": "app.main" in sys.modules,
        "startup_handler_count": len(app.router.on_startup),
        "shutdown_handler_count": len(app.router.on_shutdown),
        "target_routes_present": sorted(
            route_paths & {"/api/speech/plan", "/api/speech/realize"}
        ),
    }


def _assert_application_isolation(value: dict[str, Any]) -> None:
    if value != {
        "router_only": True,
        "global_app_main_loaded": False,
        "startup_handler_count": 0,
        "shutdown_handler_count": 0,
        "target_routes_present": [
            "/api/speech/plan",
            "/api/speech/realize",
        ],
    }:
        raise WorkerInputError("router-only application isolation failed")


def _evaluate(request: dict[str, Any]) -> dict[str, Any]:
    source_root, _api_root = _configure_source_root()
    worker_repo = Path(__file__).resolve().parents[1]
    _install_network_guard()
    network_guard = _network_guard_receipt()
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="atanor-pattern09-speech-") as raw_root:
        runtime_root = Path(raw_root).resolve(strict=True)
        try:
            runtime_root.relative_to(source_root)
            outside_source = False
        except ValueError:
            outside_source = True
        os.chdir(runtime_root)
        try:
            from fastapi.testclient import TestClient

            from app.routers import surface_brain as surface_router
            from packages.surface_brain import realization_planner

            app = _build_router_only_app(surface_router)
            _assert_application_isolation(_application_isolation(app))
            rows: list[dict[str, Any]] = []
            with TestClient(app) as client:
                for expected, item in enumerate(request["items"]):
                    error: str | None = None
                    plan_status = 0
                    answer_status = 0
                    planned: dict[str, Any] = {}
                    answered: dict[str, Any] = {}
                    try:
                        plan_response = client.post(
                            "/api/speech/plan",
                            json={
                                "query": item["query"],
                                "semantic_context": item["semantic_context"],
                                "language": "en",
                            },
                        )
                        plan_status = int(plan_response.status_code)
                        planned = plan_response.json()
                        realize_plan = (
                            item["surface_plan"]
                            if item["surface_plan"] is not None
                            else planned
                        )
                        answer_response = client.post(
                            "/api/speech/realize",
                            json={
                                "query": item["query"],
                                "surface_plan": realize_plan,
                                "semantic_context": item["semantic_context"],
                            },
                        )
                        answer_status = int(answer_response.status_code)
                        answered = answer_response.json()
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {str(exc)[-500:]}"
                    plan_trace_present = "trace" in planned
                    plan_trace = planned.get("trace")
                    plan_trace_dict = (
                        plan_trace if isinstance(plan_trace, dict) else {}
                    )
                    plan_summary_present = (
                        "semantic_context_summary" in plan_trace_dict
                    )
                    plan_summary = plan_trace_dict.get(
                        "semantic_context_summary"
                    )
                    plan_summary_dict = (
                        plan_summary if isinstance(plan_summary, dict) else {}
                    )
                    answer_trace_present = "trace_summary" in answered
                    answer_trace = answered.get("trace_summary")
                    answer_trace_dict = (
                        answer_trace if isinstance(answer_trace, dict) else {}
                    )
                    rows.append(
                        {
                            "index": expected,
                            "item_key": item["item_key"],
                            "condition": request["condition"],
                            "plan_status": plan_status,
                            "answer_status": answer_status,
                            "field_presence": {
                                "plan_trace": plan_trace_present,
                                "plan_summary": plan_summary_present,
                                "plan_relation_count": (
                                    "relation_count" in plan_summary_dict
                                ),
                                "plan_evidence_count": (
                                    "evidence_count" in plan_summary_dict
                                ),
                                "plan_input_trust": (
                                    "input_trust" in plan_trace_dict
                                ),
                                "answer": "answer" in answered,
                                "semantic_sources": (
                                    "semantic_sources" in answered
                                ),
                                "answer_trace": answer_trace_present,
                                "answer_no_evidence": (
                                    "no_evidence" in answer_trace_dict
                                ),
                                "answer_input_trust": (
                                    "input_trust" in answer_trace_dict
                                ),
                                "surface_plan_id": (
                                    "surface_plan_id" in answered
                                ),
                            },
                            "plan_relation_count": plan_summary_dict.get(
                                "relation_count"
                            ),
                            "plan_evidence_count": plan_summary_dict.get(
                                "evidence_count"
                            ),
                            "plan_input_trust": plan_trace_dict.get(
                                "input_trust"
                            ),
                            "answer": answered.get("answer"),
                            "semantic_sources": answered.get(
                                "semantic_sources"
                            ),
                            "answer_no_evidence": answer_trace_dict.get(
                                "no_evidence"
                            ),
                            "answer_input_trust": answer_trace_dict.get(
                                "input_trust"
                            ),
                            "surface_plan_id": answered.get(
                                "surface_plan_id"
                            ),
                            "error": error,
                        }
                    )
            runtime_files = sorted(
                path.relative_to(runtime_root).as_posix()
                for path in runtime_root.rglob("*")
                if path.is_file()
            )
            loaded_modules = {
                "surface_router": _module_path(surface_router),
                "realization_planner": _module_path(realization_planner),
            }
            application_isolation = _application_isolation(app)
            _assert_application_isolation(application_isolation)
            import_closure = _repo_import_closure(source_root, worker_repo)
            if import_closure["forbidden_source_modules_loaded"]:
                raise WorkerInputError("app.main entered router-only import closure")
        finally:
            os.chdir(original_cwd)

    return {
        "schema_version": RESULT_SCHEMA,
        "preregistration_id": request["preregistration_id"],
        "block_id": request["block_id"],
        "condition": request["condition"],
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "python": platform.python_version(),
        "source_root": str(source_root),
        "loaded_modules": loaded_modules,
        "application_isolation": application_isolation,
        "repo_import_closure": import_closure,
        "environment": {
            "keys": sorted(os.environ),
            "unexpected_atanor_keys": sorted(
                key
                for key in os.environ
                if key.startswith("ATANOR_")
                and key != "ATANOR_PATTERN09_SOURCE_ROOT"
            ),
        },
        "network_guard": network_guard,
        "runtime_isolation": {
            "temporary_root_outside_source": outside_source,
            "files": runtime_files,
        },
        "items": rows,
    }


def _isolation_smoke() -> dict[str, Any]:
    source_root, _api_root = _configure_source_root()
    worker_repo = Path(__file__).resolve().parents[1]
    _install_network_guard()
    network_guard = _network_guard_receipt()
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(
        prefix="atanor-pattern09-isolation-smoke-"
    ) as raw_root:
        runtime_root = Path(raw_root).resolve(strict=True)
        try:
            runtime_root.relative_to(source_root)
            outside_source = False
        except ValueError:
            outside_source = True
        os.chdir(runtime_root)
        try:
            from fastapi.testclient import TestClient

            from app.routers import surface_brain as surface_router
            from packages.surface_brain import realization_planner

            app = _build_router_only_app(surface_router)
            _assert_application_isolation(_application_isolation(app))
            with TestClient(app) as client:
                plan_response = client.post(
                    "/api/speech/plan",
                    json={
                        "query": "Explain the isolation-smoke token.",
                        "semantic_context": {
                            "concepts": ["isolation-smoke"]
                        },
                        "language": "en",
                    },
                )
                plan_payload = plan_response.json()
                realize_response = client.post(
                    "/api/speech/realize",
                    json={
                        "query": "Explain the isolation-smoke token.",
                        "surface_plan": plan_payload,
                        "semantic_context": {
                            "concepts": ["isolation-smoke"]
                        },
                    },
                )
            application_isolation = _application_isolation(app)
            _assert_application_isolation(application_isolation)
            import_closure = _repo_import_closure(source_root, worker_repo)
            if import_closure["forbidden_source_modules_loaded"]:
                raise WorkerInputError("app.main entered isolation smoke")
            runtime_files = sorted(
                path.relative_to(runtime_root).as_posix()
                for path in runtime_root.rglob("*")
                if path.is_file()
            )
            loaded_modules = {
                "surface_router": _module_path(surface_router),
                "realization_planner": _module_path(realization_planner),
            }
        finally:
            os.chdir(original_cwd)
    valid = bool(
        plan_response.status_code == 200
        and realize_response.status_code == 200
        and outside_source
        and not import_closure["outside_source_repo_modules"]
        and not import_closure["forbidden_source_modules_loaded"]
    )
    return {
        "schema_version": SMOKE_SCHEMA,
        "valid": valid,
        "source_root": str(source_root),
        "plan_status": int(plan_response.status_code),
        "answer_status": int(realize_response.status_code),
        "application_isolation": application_isolation,
        "repo_import_closure": import_closure,
        "loaded_modules": loaded_modules,
        "network_guard": network_guard,
        "runtime_isolation": {
            "temporary_root_outside_source": outside_source,
            "files": runtime_files,
        },
        "target_cohort_executed": False,
    }


def main() -> int:
    try:
        if sys.argv[1:] == ["--isolation-smoke"]:
            sys.stdout.write(
                json.dumps(
                    _isolation_smoke(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            )
            sys.stdout.flush()
            return 0
        if sys.argv[1:]:
            raise WorkerInputError("unsupported worker arguments")
        request = _validate_request(
            _load_request(sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1))
        )
        result = _evaluate(request)
        sys.stdout.write(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        sys.stdout.flush()
    except Exception as exc:
        sys.stderr.write(
            json.dumps(
                {
                    "error": str(exc)[-2000:],
                    "type": type(exc).__name__,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
