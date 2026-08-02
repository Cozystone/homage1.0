"""Local-only fixture evaluator for the same-host Docker isolation probe.

The HMAC emitted here is intentionally not production authority.  It only
demonstrates that a key mounted to this evaluator was absent from the candidate
container's mount namespace.
"""
from __future__ import annotations

import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows test import only
    resource = None  # type: ignore[assignment]


REQUEST_PATH = Path("/input/request.json")
RESPONSE_PATH = Path("/input/candidate_response.json")
GOLD_PATH = Path("/fixture/gold.json")
KEY_PATH = Path("/run/secrets/local_fixture_signing_key")
NETWORK_PROBE_PATH = Path("/input/network_probe.json")

REQUEST_SCHEMA = "atanor.science-e4-local-candidate-request.v1"
CANDIDATE_RESPONSE_SCHEMA = (
    "atanor.science-e4-local-candidate-response.v1"
)
GOLD_SCHEMA = "atanor.science-e4-local-gold-fixture.v1"
EVALUATION_SCHEMA = (
    "atanor.science-e4-local-fixture-evaluation.v1"
)
SIGNATURE_SCHEME = "hmac-sha256-local-fixture-not-authority"
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

EXPECTED_UID = 10002
EXPECTED_GID = 10002
MAX_INPUT_BYTES = 256 * 1024
MAX_ITEMS = 64

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_FIELDS = frozenset({"schema_version", "run_id", "nonce", "items"})
_ITEM_FIELDS = frozenset({"item_id", "stem", "choices"})
_RESPONSE_FIELDS = frozenset(
    {
        "all_probes_passed",
        "items",
        "nonce",
        "network_probe_sha256",
        "probes",
        "request_sha256",
        "run_id",
        "runtime",
        "schema_version",
        "scope",
        "stage_sha256",
    }
)
_RESPONSE_ITEM_FIELDS = frozenset({"decision", "item_id", "reason"})
_GOLD_FIELDS = frozenset({"schema_version", "answers"})
_ANSWER_FIELDS = frozenset({"answer_index", "item_id"})
_NETWORK_PROBE_FIELDS = frozenset({"schema_version", "host", "port"})
EXPECTED_CANDIDATE_PROBE_IDS = frozenset(
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
EXPECTED_EVALUATOR_PROBE_IDS = frozenset(
    {
        "candidate_response_mount_write_blocked",
        "cgroup_cpu_quota_bounded",
        "cgroup_memory_max_bounded",
        "cgroup_pids_max_bounded",
        "docker_socket_absent",
        "environment_allowlist_exact",
        "evaluator_gold_mount_write_blocked",
        "evaluator_key_mount_write_blocked",
        "evaluator_numeric_uid_gid",
        "linux_default_route_absent",
        "network_probe_mount_write_blocked",
        "no_new_privileges_active",
        "raw_socket_blocked",
        "request_mount_write_blocked",
        "rlimit_nofile_bounded",
        "rootfs_new_file_write_blocked",
        "runner_owned_network_sentinel_blocked",
        "seccomp_filter_active",
        "tmpfs_write_positive_control",
        "zero_effective_and_bounding_capabilities",
    }
)

FALSE_AUTHORITY_CLAIMS = {
    "canonical_e4_established": False,
    "e5_established": False,
    "independent_evaluation_established": False,
    "os_isolation_established": False,
}


class FixtureEvaluationError(ValueError):
    """Fail-closed local fixture evaluation error."""


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
            raise FixtureEvaluationError("duplicate JSON object key")
        result[key] = value
    return result


def _read_canonical(path: Path, *, byte_limit: int) -> tuple[Any, bytes]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FixtureEvaluationError("fixture input unavailable") from exc
    if size <= 0 or size > byte_limit:
        raise FixtureEvaluationError("fixture input byte bound violated")
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FixtureEvaluationError(
            "fixture input is not strict UTF-8 JSON"
        ) from exc
    if payload != canonical_json_bytes(value) + b"\n":
        raise FixtureEvaluationError(
            "fixture input is not canonical JSON plus one newline"
        )
    return value, payload


def _bounded_string(
    value: Any,
    *,
    field: str,
    maximum_bytes: int,
) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value.encode("utf-8")) <= maximum_bytes
        or value != value.strip()
    ):
        raise FixtureEvaluationError(f"{field} is invalid")
    return value


def validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != _REQUEST_FIELDS:
        raise FixtureEvaluationError("candidate request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise FixtureEvaluationError("candidate request schema mismatch")
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
        raise FixtureEvaluationError("run_id is invalid")
    if _NONCE_RE.fullmatch(nonce) is None:
        raise FixtureEvaluationError("nonce is invalid")
    items = value.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise FixtureEvaluationError("request item bound violated")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or frozenset(item) != _ITEM_FIELDS:
            raise FixtureEvaluationError("candidate item fields mismatch")
        item_id = _bounded_string(
            item.get("item_id"),
            field="item_id",
            maximum_bytes=128,
        )
        if _ID_RE.fullmatch(item_id) is None or item_id in seen:
            raise FixtureEvaluationError("item_id invalid or duplicated")
        seen.add(item_id)
        _bounded_string(
            item.get("stem"),
            field="stem",
            maximum_bytes=4096,
        )
        choices = item.get("choices")
        if not isinstance(choices, list) or not 2 <= len(choices) <= 10:
            raise FixtureEvaluationError("choice count invalid")
        checked = [
            _bounded_string(
                choice,
                field="choice",
                maximum_bytes=2048,
            )
            for choice in choices
        ]
        if len(set(checked)) != len(checked):
            raise FixtureEvaluationError("choices are duplicated")
    return json.loads(canonical_json_bytes(value))


def validate_candidate_response(
    value: Any,
    *,
    request: dict[str, Any],
    request_sha256: str,
    network_probe_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != _RESPONSE_FIELDS:
        raise FixtureEvaluationError("candidate response fields mismatch")
    if value.get("schema_version") != CANDIDATE_RESPONSE_SCHEMA:
        raise FixtureEvaluationError("candidate response schema mismatch")
    if (
        value.get("run_id") != request["run_id"]
        or value.get("nonce") != request["nonce"]
        or value.get("request_sha256") != request_sha256
        or value.get("network_probe_sha256") != network_probe_sha256
        or _SHA256_RE.fullmatch(str(value.get("stage_sha256"))) is None
    ):
        raise FixtureEvaluationError("candidate response binding mismatch")
    if value.get("all_probes_passed") is not True:
        raise FixtureEvaluationError("candidate breach probes did not pass")
    runtime = value.get("runtime")
    if runtime != {"gid": 10001, "uid": 10001}:
        raise FixtureEvaluationError("candidate runtime identity mismatch")
    scope = value.get("scope")
    if scope != {
        "capability_evaluation_performed": False,
        "local_isolation_probe_only": True,
    }:
        raise FixtureEvaluationError("candidate scope mismatch")
    probes = value.get("probes")
    if (
        not isinstance(probes, dict)
        or frozenset(probes) != EXPECTED_CANDIDATE_PROBE_IDS
    ):
        raise FixtureEvaluationError("candidate probes missing")
    for probe in probes.values():
        if (
            not isinstance(probe, dict)
            or frozenset(probe) != {"passed", "error_type"}
            or probe.get("passed") is not True
            or (
                probe.get("error_type") is not None
                and not isinstance(probe.get("error_type"), str)
            )
        ):
            raise FixtureEvaluationError("candidate probe invalid")
    items = value.get("items")
    expected_ids = [item["item_id"] for item in request["items"]]
    if not isinstance(items, list) or len(items) != len(expected_ids):
        raise FixtureEvaluationError("candidate response item count mismatch")
    for index, item in enumerate(items):
        if (
            not isinstance(item, dict)
            or frozenset(item) != _RESPONSE_ITEM_FIELDS
            or item.get("item_id") != expected_ids[index]
            or item.get("decision") != "ABSTAIN"
            or item.get("reason")
            != "local_isolation_probe_no_capability_evaluation"
        ):
            raise FixtureEvaluationError("candidate response item invalid")
    return json.loads(canonical_json_bytes(value))


def validate_gold(
    value: Any,
    *,
    request: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != _GOLD_FIELDS:
        raise FixtureEvaluationError("gold fixture fields mismatch")
    if value.get("schema_version") != GOLD_SCHEMA:
        raise FixtureEvaluationError("gold fixture schema mismatch")
    answers = value.get("answers")
    if not isinstance(answers, list) or len(answers) != len(
        request["items"]
    ):
        raise FixtureEvaluationError("gold fixture item count mismatch")
    for index, answer in enumerate(answers):
        if (
            not isinstance(answer, dict)
            or frozenset(answer) != _ANSWER_FIELDS
            or answer.get("item_id")
            != request["items"][index]["item_id"]
            or type(answer.get("answer_index")) is not int
            or not 0
            <= answer["answer_index"]
            < len(request["items"][index]["choices"])
        ):
            raise FixtureEvaluationError("gold fixture answer invalid")
    return json.loads(canonical_json_bytes(value))


def validate_network_probe(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _NETWORK_PROBE_FIELDS
        or value.get("schema_version") != NETWORK_PROBE_SCHEMA
    ):
        raise FixtureEvaluationError("network probe fields mismatch")
    host = _bounded_string(
        value.get("host"),
        field="network_probe.host",
        maximum_bytes=255,
    )
    port = value.get("port")
    if (
        re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", host) is None
        or any(int(octet) > 255 for octet in host.split("."))
        or type(port) is not int
        or not 1024 <= port <= 65535
    ):
        raise FixtureEvaluationError("network probe endpoint invalid")
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


def _no_default_route() -> dict[str, Any]:
    try:
        lines = Path("/proc/net/route").read_text(
            encoding="ascii",
            errors="strict",
        ).splitlines()
    except (OSError, UnicodeError) as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    default_present = any(
        len(fields) >= 2 and fields[1] == "00000000"
        for fields in (line.split() for line in lines[1:])
    )
    return {"passed": not default_present, "error_type": None}


def _sentinel_connect_blocked(
    network_probe: dict[str, Any],
) -> dict[str, Any]:
    try:
        connection = socket.create_connection(
            (network_probe["host"], network_probe["port"]),
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


def _proc_status_field(name: str) -> str:
    try:
        lines = Path("/proc/self/status").read_text(
            encoding="ascii",
            errors="strict",
        ).splitlines()
    except (OSError, UnicodeError) as exc:
        raise FixtureEvaluationError(
            "process status unavailable"
        ) from exc
    prefix = name + ":"
    values = [
        line.split(":", 1)[1].strip()
        for line in lines
        if line.startswith(prefix)
    ]
    if len(values) != 1:
        raise FixtureEvaluationError(
            f"process status field missing: {name}"
        )
    return values[0]


def _proc_status_equals(name: str, expected: str) -> dict[str, Any]:
    try:
        actual = _proc_status_field(name)
    except FixtureEvaluationError as exc:
        return {"passed": False, "error_type": _error_name(exc)}
    return {"passed": actual == expected, "error_type": None}


def _zero_capabilities() -> dict[str, Any]:
    try:
        effective = _proc_status_field("CapEff")
        bounding = _proc_status_field("CapBnd")
    except FixtureEvaluationError as exc:
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
    path = Path("/tmp/atanor-science-e4-evaluator-positive-control")
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
    network_probe: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    probes = {
        "candidate_response_mount_write_blocked": (
            _existing_file_write_blocked(RESPONSE_PATH)
        ),
        "cgroup_cpu_quota_bounded": _cgroup_cpu_bounded(),
        "cgroup_memory_max_bounded": _cgroup_integer_limit(
            Path("/sys/fs/cgroup/memory.max"),
            expected=256 * 1024 * 1024,
        ),
        "cgroup_pids_max_bounded": _cgroup_integer_limit(
            Path("/sys/fs/cgroup/pids.max"),
            expected=64,
        ),
        "docker_socket_absent": {
            "passed": not os.path.lexists("/var/run/docker.sock"),
            "error_type": None,
        },
        "environment_allowlist_exact": _environment_allowlist_exact(),
        "evaluator_gold_mount_write_blocked": (
            _existing_file_write_blocked(GOLD_PATH)
        ),
        "evaluator_key_mount_write_blocked": (
            _existing_file_write_blocked(KEY_PATH)
        ),
        "evaluator_numeric_uid_gid": {
            "passed": (
                os.getuid() == EXPECTED_UID
                and os.getgid() == EXPECTED_GID
            ),
            "error_type": None,
        },
        "linux_default_route_absent": _no_default_route(),
        "network_probe_mount_write_blocked": (
            _existing_file_write_blocked(NETWORK_PROBE_PATH)
        ),
        "no_new_privileges_active": _proc_status_equals(
            "NoNewPrivs",
            "1",
        ),
        "raw_socket_blocked": _raw_socket_blocked(),
        "request_mount_write_blocked": _existing_file_write_blocked(
            REQUEST_PATH
        ),
        "rlimit_nofile_bounded": _rlimit_nofile_bounded(),
        "rootfs_new_file_write_blocked": _new_root_file_write_blocked(
            Path("/atanor-science-e4-evaluator-write-test")
        ),
        "runner_owned_network_sentinel_blocked": (
            _sentinel_connect_blocked(network_probe)
        ),
        "seccomp_filter_active": _proc_status_equals("Seccomp", "2"),
        "tmpfs_write_positive_control": _tmpfs_write_positive_control(),
        "zero_effective_and_bounding_capabilities": _zero_capabilities(),
    }
    if frozenset(probes) != EXPECTED_EVALUATOR_PROBE_IDS:
        raise FixtureEvaluationError("evaluator probe inventory mismatch")
    return probes


def build_evaluation() -> dict[str, Any]:
    request_value, request_payload = _read_canonical(
        REQUEST_PATH,
        byte_limit=MAX_INPUT_BYTES,
    )
    response_value, response_payload = _read_canonical(
        RESPONSE_PATH,
        byte_limit=MAX_INPUT_BYTES,
    )
    gold_value, gold_payload = _read_canonical(
        GOLD_PATH,
        byte_limit=MAX_INPUT_BYTES,
    )
    network_probe_value, network_probe_payload = _read_canonical(
        NETWORK_PROBE_PATH,
        byte_limit=16 * 1024,
    )
    request = validate_request(request_value)
    network_probe = validate_network_probe(network_probe_value)
    response = validate_candidate_response(
        response_value,
        request=request,
        request_sha256=hashlib.sha256(request_payload).hexdigest(),
        network_probe_sha256=hashlib.sha256(
            network_probe_payload
        ).hexdigest(),
    )
    gold = validate_gold(gold_value, request=request)
    try:
        key = KEY_PATH.read_bytes()
    except OSError as exc:
        raise FixtureEvaluationError(
            "local fixture signing key unavailable"
        ) from exc
    if len(key) != 32:
        raise FixtureEvaluationError(
            "local fixture signing key must be exactly 32 bytes"
        )
    probes = collect_probes(network_probe)
    unsigned = {
        "candidate_response_contract_passed": True,
        "candidate_response_sha256": hashlib.sha256(
            response_payload
        ).hexdigest(),
        "claims": dict(FALSE_AUTHORITY_CLAIMS),
        "fixture_gold_digest_sha256": hashlib.sha256(
            gold_payload
        ).hexdigest(),
        "fixture_gold_item_id_alignment_passed": (
            [answer["item_id"] for answer in gold["answers"]]
            == [item["item_id"] for item in request["items"]]
        ),
        "fixture_gold_used_for_capability_scoring": False,
        "local_fixture_only": True,
        "nonce": response["nonce"],
        "network_probe_sha256": hashlib.sha256(
            network_probe_payload
        ).hexdigest(),
        "probes": probes,
        "request_sha256": hashlib.sha256(request_payload).hexdigest(),
        "run_id": response["run_id"],
        "runtime": {"gid": os.getgid(), "uid": os.getuid()},
        "schema_version": EVALUATION_SCHEMA,
    }
    payload = canonical_json_bytes(unsigned)
    unsigned["signature"] = {
        "key_id": (
            "local-fixture:"
            + hashlib.sha256(key).hexdigest()[:24]
        ),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "scheme": SIGNATURE_SCHEME,
        "signature_hex": hmac.new(
            key,
            payload,
            hashlib.sha256,
        ).hexdigest(),
    }
    return unsigned


def main() -> int:
    try:
        evaluation = build_evaluation()
    except Exception as exc:
        print(
            f"science-e4 local evaluator failed closed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 2
    probes_passed = all(
        probe["passed"] is True
        for probe in evaluation["probes"].values()
    )
    sys.stdout.buffer.write(canonical_json_bytes(evaluation) + b"\n")
    return 0 if probes_passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
