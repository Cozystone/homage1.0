"""Gold-free one-shot candidate used only by the local Docker isolation probe."""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any, Mapping

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows test import only
    resource = None  # type: ignore[assignment]


REQUEST_PATH = Path("/input/request.json")
STAGE_PATH = Path("/input/stage.json")
NETWORK_PROBE_PATH = Path("/input/network_probe.json")

REQUEST_SCHEMA = "atanor.science-e4-local-candidate-request.v1"
STAGE_SCHEMA = "atanor.science-e4-local-stage-fixture.v1"
RESPONSE_SCHEMA = "atanor.science-e4-local-candidate-response.v1"
NETWORK_PROBE_SCHEMA = "atanor.science-e4-local-network-probe.v1"
ALLOWED_NETWORK_BLOCK_ERRNOS = frozenset(
    {
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
    }
)
NETWORK_BLOCK_ERRNO_NAMES = {
    errno.EHOSTUNREACH: "EHOSTUNREACH",
    errno.ENETUNREACH: "ENETUNREACH",
}

EXPECTED_UID = 10001
EXPECTED_GID = 10001
MAX_REQUEST_BYTES = 128 * 1024
MAX_STAGE_BYTES = 128 * 1024
MAX_ITEMS = 64
MAX_FACTS = 256

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_REQUEST_FIELDS = frozenset({"schema_version", "run_id", "nonce", "items"})
_ITEM_FIELDS = frozenset({"item_id", "stem", "choices"})
_STAGE_FIELDS = frozenset({"schema_version", "facts"})
_FACT_FIELDS = frozenset(
    {"subject", "predicate", "object", "source_locator"}
)
_NETWORK_PROBE_FIELDS = frozenset({"schema_version", "host", "port"})
EXPECTED_PROBE_IDS = frozenset(
    {
        "candidate_numeric_uid_gid",
        "cgroup_cpu_quota_bounded",
        "cgroup_memory_max_bounded",
        "cgroup_pids_max_bounded",
        "docker_socket_absent",
        "environment_allowlist_exact",
        "evaluator_gold_mount_absent",
        "evaluator_key_mount_absent",
        "linux_default_route_absent",
        "network_probe_mount_write_blocked",
        "no_new_privileges_active",
        "privilege_escalation_setuid_zero_blocked",
        "raw_socket_blocked",
        "request_mount_write_blocked",
        "rlimit_nofile_bounded",
        "rootfs_new_file_write_blocked",
        "runner_owned_network_sentinel_blocked",
        "seccomp_filter_active",
        "stage_mount_write_blocked",
        "tmpfs_write_positive_control",
        "zero_effective_and_bounding_capabilities",
    }
)


class ProbeInputError(ValueError):
    """Fail-closed candidate input error."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeInputError("duplicate JSON object key")
        result[key] = value
    return result


def _read_canonical(path: Path, *, byte_limit: int) -> tuple[Any, bytes]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProbeInputError("input unavailable") from exc
    if size <= 0 or size > byte_limit:
        raise ProbeInputError("input byte bound violated")
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeInputError("input is not strict UTF-8 JSON") from exc
    if payload != canonical_json_bytes(value) + b"\n":
        raise ProbeInputError("input is not canonical JSON plus one newline")
    return value, payload


def _bounded_string(
    value: Any,
    *,
    field: str,
    minimum: int = 1,
    maximum_bytes: int = 4096,
) -> str:
    if not isinstance(value, str):
        raise ProbeInputError(f"{field} must be a string")
    encoded = value.encode("utf-8")
    if not minimum <= len(encoded) <= maximum_bytes:
        raise ProbeInputError(f"{field} byte bound violated")
    if value != value.strip():
        raise ProbeInputError(f"{field} must not have edge whitespace")
    return value


def validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != _REQUEST_FIELDS:
        raise ProbeInputError("candidate request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise ProbeInputError("candidate request schema mismatch")
    run_id = _bounded_string(
        value.get("run_id"),
        field="run_id",
        maximum_bytes=128,
    )
    nonce = _bounded_string(
        value.get("nonce"),
        field="nonce",
        maximum_bytes=128,
    )
    if _ID_RE.fullmatch(run_id) is None:
        raise ProbeInputError("run_id is invalid")
    if _NONCE_RE.fullmatch(nonce) is None:
        raise ProbeInputError("nonce is invalid")
    items = value.get("items")
    if (
        not isinstance(items, list)
        or isinstance(items, tuple)
        or not 1 <= len(items) <= MAX_ITEMS
    ):
        raise ProbeInputError("items bound violated")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or frozenset(item) != _ITEM_FIELDS:
            raise ProbeInputError("candidate item fields mismatch")
        item_id = _bounded_string(
            item.get("item_id"),
            field="item_id",
            maximum_bytes=128,
        )
        if _ID_RE.fullmatch(item_id) is None or item_id in seen:
            raise ProbeInputError("item_id is invalid or duplicated")
        seen.add(item_id)
        _bounded_string(
            item.get("stem"),
            field="stem",
            maximum_bytes=4096,
        )
        choices = item.get("choices")
        if not isinstance(choices, list) or not 2 <= len(choices) <= 10:
            raise ProbeInputError("choice count is invalid")
        checked = [
            _bounded_string(
                choice,
                field="choice",
                maximum_bytes=2048,
            )
            for choice in choices
        ]
        if len(set(checked)) != len(checked):
            raise ProbeInputError("choices must be unique")
    return json.loads(canonical_json_bytes(value))


def validate_stage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != _STAGE_FIELDS:
        raise ProbeInputError("stage fields mismatch")
    if value.get("schema_version") != STAGE_SCHEMA:
        raise ProbeInputError("stage schema mismatch")
    facts = value.get("facts")
    if not isinstance(facts, list) or not 1 <= len(facts) <= MAX_FACTS:
        raise ProbeInputError("stage fact bound violated")
    for fact in facts:
        if not isinstance(fact, dict) or frozenset(fact) != _FACT_FIELDS:
            raise ProbeInputError("stage fact fields mismatch")
        for field in sorted(_FACT_FIELDS):
            _bounded_string(
                fact.get(field),
                field=f"stage.{field}",
                maximum_bytes=2048,
            )
    return json.loads(canonical_json_bytes(value))


def validate_network_probe(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _NETWORK_PROBE_FIELDS
        or value.get("schema_version") != NETWORK_PROBE_SCHEMA
    ):
        raise ProbeInputError("network probe fields mismatch")
    host = _bounded_string(
        value.get("host"),
        field="network_probe.host",
        maximum_bytes=255,
    )
    port = value.get("port")
    if (
        re.fullmatch(
            r"(?:\d{1,3}\.){3}\d{1,3}",
            host,
        )
        is None
        or type(port) is not int
        or not 1024 <= port <= 65535
    ):
        raise ProbeInputError("network probe endpoint invalid")
    octets = host.split(".")
    if any(int(octet) > 255 for octet in octets):
        raise ProbeInputError("network probe address invalid")
    return json.loads(canonical_json_bytes(value))


def _error_name(exc: BaseException) -> str:
    return type(exc).__name__


def _existing_file_write_blocked(path: Path) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_WRONLY)
    except OSError as exc:
        return {"passed": True, "error_type": _error_name(exc)}
    else:
        os.close(descriptor)
        return {"passed": False, "error_type": None}


def _new_root_file_write_blocked(path: Path) -> dict[str, Any]:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except OSError as exc:
        return {"passed": True, "error_type": _error_name(exc)}
    else:
        os.close(descriptor)
        try:
            path.unlink()
        except OSError:
            pass
        return {"passed": False, "error_type": None}


def _path_absent(path: Path) -> dict[str, Any]:
    return {"passed": not os.path.lexists(path), "error_type": None}


def _no_default_route() -> dict[str, Any]:
    try:
        lines = Path("/proc/net/route").read_text(
            encoding="ascii",
            errors="strict",
        ).splitlines()
    except (OSError, UnicodeError) as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    default_present = False
    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "00000000":
            default_present = True
            break
    return {"passed": not default_present, "error_type": None}


def _sentinel_connect_blocked(
    network_probe: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        connection = socket.create_connection(
            (str(network_probe["host"]), int(network_probe["port"])),
            timeout=0.25,
        )
    except OSError as exc:
        explicitly_blocked = exc.errno in ALLOWED_NETWORK_BLOCK_ERRNOS
        error_code = NETWORK_BLOCK_ERRNO_NAMES.get(
            exc.errno,
            errno.errorcode.get(exc.errno, "NO_ERRNO"),
        )
        return {
            "passed": explicitly_blocked,
            "error_type": f"{_error_name(exc)}:{error_code}",
        }
    else:
        connection.close()
        return {"passed": False, "error_type": None}


def _raw_socket_blocked() -> dict[str, Any]:
    try:
        raw = socket.socket(
            socket.AF_INET,
            socket.SOCK_RAW,
            socket.IPPROTO_ICMP,
        )
    except OSError as exc:
        return {"passed": True, "error_type": _error_name(exc)}
    else:
        raw.close()
        return {"passed": False, "error_type": None}


def _setuid_zero_blocked() -> dict[str, Any]:
    try:
        os.setuid(0)
    except OSError as exc:
        return {"passed": True, "error_type": _error_name(exc)}
    return {"passed": False, "error_type": None}


def _proc_status_field(name: str) -> str:
    try:
        lines = Path("/proc/self/status").read_text(
            encoding="ascii",
            errors="strict",
        ).splitlines()
    except (OSError, UnicodeError) as exc:
        raise ProbeInputError("process status unavailable") from exc
    prefix = name + ":"
    values = [
        line.split(":", 1)[1].strip()
        for line in lines
        if line.startswith(prefix)
    ]
    if len(values) != 1:
        raise ProbeInputError(f"process status field missing: {name}")
    return values[0]


def _proc_status_equals(name: str, expected: str) -> dict[str, Any]:
    try:
        actual = _proc_status_field(name)
    except ProbeInputError as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {"passed": actual == expected, "error_type": None}


def _zero_capabilities() -> dict[str, Any]:
    try:
        effective = _proc_status_field("CapEff")
        bounding = _proc_status_field("CapBnd")
    except ProbeInputError as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {
        "passed": (
            effective == "0000000000000000"
            and bounding == "0000000000000000"
        ),
        "error_type": None,
    }


def _cgroup_integer_limit(
    path: Path,
    *,
    expected: int,
) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="ascii", errors="strict").strip()
        actual = int(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {"passed": actual == expected, "error_type": None}


def _cgroup_cpu_bounded() -> dict[str, Any]:
    try:
        fields = Path("/sys/fs/cgroup/cpu.max").read_text(
            encoding="ascii",
            errors="strict",
        ).strip().split()
        quota = int(fields[0])
        period = int(fields[1])
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {
        "passed": quota > 0 and period > 0 and quota <= period,
        "error_type": None,
    }


def _rlimit_nofile_bounded() -> dict[str, Any]:
    if resource is None:
        return {"passed": False, "error_type": "ModuleNotFoundError"}
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError) as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {"passed": soft == 128 and hard == 128, "error_type": None}


def _tmpfs_write_positive_control() -> dict[str, Any]:
    path = Path("/tmp/atanor-science-e4-positive-control")
    try:
        path.write_bytes(b"ok")
        matched = path.read_bytes() == b"ok"
        path.unlink()
    except OSError as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {"passed": matched, "error_type": None}


def _environment_allowlist_exact() -> dict[str, Any]:
    return {
        "passed": frozenset(os.environ) == {"LANG", "PATH"},
        "error_type": None,
    }


def collect_probes(
    network_probe: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    probes = {
        "candidate_numeric_uid_gid": {
            "passed": (
                os.getuid() == EXPECTED_UID
                and os.getgid() == EXPECTED_GID
            ),
            "error_type": None,
        },
        "cgroup_cpu_quota_bounded": _cgroup_cpu_bounded(),
        "cgroup_memory_max_bounded": _cgroup_integer_limit(
            Path("/sys/fs/cgroup/memory.max"),
            expected=256 * 1024 * 1024,
        ),
        "cgroup_pids_max_bounded": _cgroup_integer_limit(
            Path("/sys/fs/cgroup/pids.max"),
            expected=64,
        ),
        "docker_socket_absent": _path_absent(
            Path("/var/run/docker.sock")
        ),
        "environment_allowlist_exact": _environment_allowlist_exact(),
        "evaluator_gold_mount_absent": _path_absent(
            Path("/fixture/gold.json")
        ),
        "evaluator_key_mount_absent": _path_absent(
            Path("/run/secrets/local_fixture_signing_key")
        ),
        "linux_default_route_absent": _no_default_route(),
        "network_probe_mount_write_blocked": (
            _existing_file_write_blocked(NETWORK_PROBE_PATH)
        ),
        "no_new_privileges_active": _proc_status_equals(
            "NoNewPrivs",
            "1",
        ),
        "privilege_escalation_setuid_zero_blocked": (
            _setuid_zero_blocked()
        ),
        "raw_socket_blocked": _raw_socket_blocked(),
        "request_mount_write_blocked": _existing_file_write_blocked(
            REQUEST_PATH
        ),
        "rlimit_nofile_bounded": _rlimit_nofile_bounded(),
        "rootfs_new_file_write_blocked": _new_root_file_write_blocked(
            Path("/atanor-science-e4-probe-write-test")
        ),
        "runner_owned_network_sentinel_blocked": (
            _sentinel_connect_blocked(network_probe)
        ),
        "seccomp_filter_active": _proc_status_equals("Seccomp", "2"),
        "stage_mount_write_blocked": _existing_file_write_blocked(
            STAGE_PATH
        ),
        "tmpfs_write_positive_control": _tmpfs_write_positive_control(),
        "zero_effective_and_bounding_capabilities": _zero_capabilities(),
    }
    if frozenset(probes) != EXPECTED_PROBE_IDS:
        raise ProbeInputError("candidate probe inventory mismatch")
    return probes


def build_response() -> dict[str, Any]:
    request_value, request_payload = _read_canonical(
        REQUEST_PATH,
        byte_limit=MAX_REQUEST_BYTES,
    )
    stage_value, stage_payload = _read_canonical(
        STAGE_PATH,
        byte_limit=MAX_STAGE_BYTES,
    )
    network_probe_value, network_probe_payload = _read_canonical(
        NETWORK_PROBE_PATH,
        byte_limit=16 * 1024,
    )
    request = validate_request(request_value)
    validate_stage(stage_value)
    network_probe = validate_network_probe(network_probe_value)
    probes = collect_probes(network_probe)
    items = [
        {
            "decision": "ABSTAIN",
            "item_id": item["item_id"],
            "reason": "local_isolation_probe_no_capability_evaluation",
        }
        for item in request["items"]
    ]
    return {
        "all_probes_passed": all(
            probe["passed"] is True for probe in probes.values()
        ),
        "items": items,
        "nonce": request["nonce"],
        "network_probe_sha256": hashlib.sha256(
            network_probe_payload
        ).hexdigest(),
        "probes": probes,
        "request_sha256": hashlib.sha256(request_payload).hexdigest(),
        "run_id": request["run_id"],
        "runtime": {
            "gid": os.getgid(),
            "uid": os.getuid(),
        },
        "schema_version": RESPONSE_SCHEMA,
        "scope": {
            "capability_evaluation_performed": False,
            "local_isolation_probe_only": True,
        },
        "stage_sha256": hashlib.sha256(stage_payload).hexdigest(),
    }


def main() -> int:
    try:
        response = build_response()
    except Exception as exc:
        print(
            f"science-e4 local candidate failed closed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(response) + b"\n")
    return 0 if response["all_probes_passed"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
