"""Hardened same-host Docker isolation probe for the science E4 boundary.

This runner captures normalized Docker inspect evidence and produces a
canonical local-isolation manifest.  A successful observation is recorded
only as ``gates.same_host_docker_isolation_gate_passed``.  Every authoritative
OS-isolation, independence, authenticity, capability, E4, E5,
production-authority, and resource-curve claim remains false by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence
import uuid


SCHEMA_VERSION = "atanor.science-e4-local-isolation-manifest.v1"
EVIDENCE_KIND = "same_host_docker_isolation_probe"
REQUEST_SCHEMA = "atanor.science-e4-local-candidate-request.v1"
CANDIDATE_RESPONSE_SCHEMA = (
    "atanor.science-e4-local-candidate-response.v1"
)
FIXTURE_EVALUATION_SCHEMA = (
    "atanor.science-e4-local-fixture-evaluation.v1"
)
LOCAL_SIGNATURE_SCHEME = "hmac-sha256-local-fixture-not-authority"
NETWORK_PROBE_SCHEMA = "atanor.science-e4-local-network-probe.v1"

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
CANDIDATE_CONTEXT = BASE_DIR / "candidate"
EVALUATOR_CONTEXT = BASE_DIR / "evaluator"
FIXTURE_DIR = BASE_DIR / "fixtures"
REQUEST_FIXTURE = FIXTURE_DIR / "request.json"
STAGE_FIXTURE = FIXTURE_DIR / "stage.json"
GOLD_FIXTURE = FIXTURE_DIR / "gold.json"

CANDIDATE_UID = 10001
EVALUATOR_UID = 10002
MEMORY_BYTES = 256 * 1024 * 1024
NANO_CPUS = 1_000_000_000
PIDS_LIMIT = 64
NOFILE_LIMIT = 128
TMPFS_BYTES = 16 * 1024 * 1024
CONTAINER_TIMEOUT_SECONDS = 30
DOCKER_TIMEOUT_SECONDS = 300
MAX_JSON_BYTES = 512 * 1024
NETWORK_SENTINEL_PORT = 18080

CANDIDATE_CONTEXT_FILES = (
    ".dockerignore",
    "Dockerfile",
    "candidate_probe.py",
)
EVALUATOR_CONTEXT_FILES = (
    ".dockerignore",
    "Dockerfile",
    "fixture_evaluator.py",
)
CANDIDATE_MOUNTS = {
    "/input/network_probe.json": "network_probe",
    "/input/request.json": "request",
    "/input/stage.json": "stage",
}
EVALUATOR_MOUNTS = {
    "/fixture/gold.json": "gold",
    "/input/candidate_response.json": "candidate_response",
    "/input/network_probe.json": "network_probe",
    "/input/request.json": "request",
    "/run/secrets/local_fixture_signing_key": "local_fixture_key",
}
PROHIBITED_CANDIDATE_DESTINATIONS = frozenset(
    {
        "/fixture/gold.json",
        "/run/secrets/local_fixture_signing_key",
        "/var/run/docker.sock",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
NETWORK_LIVENESS_CHECKPOINTS = (
    "before_candidate",
    "after_candidate",
    "after_evaluator",
)
_REQUEST_FIELDS = frozenset({"schema_version", "run_id", "nonce", "items"})
_REQUEST_ITEM_FIELDS = frozenset({"item_id", "stem", "choices"})
_CANDIDATE_RESPONSE_FIELDS = frozenset(
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
_FIXTURE_EVALUATION_FIELDS = frozenset(
    {
        "candidate_response_contract_passed",
        "candidate_response_sha256",
        "claims",
        "fixture_gold_digest_sha256",
        "fixture_gold_item_id_alignment_passed",
        "fixture_gold_used_for_capability_scoring",
        "local_fixture_only",
        "nonce",
        "network_probe_sha256",
        "probes",
        "request_sha256",
        "run_id",
        "runtime",
        "schema_version",
        "signature",
    }
)
_LOCAL_SIGNATURE_FIELDS = frozenset(
    {"key_id", "payload_sha256", "scheme", "signature_hex"}
)
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

FALSE_CLAIMS = {
    "canonical_e4_established": False,
    "e5_established": False,
    "independent_evaluation_established": False,
    "os_isolation_established": False,
}

FIXTURE_FALSE_CLAIMS = dict(FALSE_CLAIMS)

NON_CLAIM_SCOPE = {
    "benchmark_capability_evaluated": False,
    "external_authenticity_evaluated": False,
    "local_fixture_only": True,
    "production_authority_evaluated": False,
    "resource_curve_measured": False,
}

LIMITATIONS = (
    "same host and Docker daemon control both containers",
    "local operator can inspect or alter images, mounts, and fixture key",
    "fixture HMAC is ephemeral local plumbing evidence, not production authority",
    "Docker network none retains an isolated loopback interface",
    "normalized Docker inspect evidence is same-host evidence, not remote attestation",
    "bounded resources do not establish a clean or reproducible resource curve",
    "candidate abstains; no science capability evaluation is performed",
)


class LocalIsolationError(RuntimeError):
    """Fail-closed local isolation probe error."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalIsolationError("duplicate JSON object key")
        result[key] = value
    return result


def _decode_canonical_json(
    payload: bytes,
    *,
    byte_limit: int = MAX_JSON_BYTES,
) -> Any:
    if not 0 < len(payload) <= byte_limit:
        raise LocalIsolationError("canonical JSON byte bound violated")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_no_duplicate_object,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LocalIsolationError("invalid strict UTF-8 JSON") from exc
    if payload != canonical_json_bytes(value) + b"\n":
        raise LocalIsolationError(
            "payload is not canonical JSON plus one newline"
        )
    return value


def _read_canonical_json(path: Path) -> tuple[Any, bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise LocalIsolationError(
            f"required fixture unreadable: {path.name}"
        ) from exc
    return _decode_canonical_json(payload), payload


def _descriptor(payload: bytes) -> dict[str, Any]:
    return {"bytes": len(payload), "sha256": _sha256(payload)}


def _source_scope(
    context: Path,
    *,
    expected_files: Sequence[str],
) -> dict[str, Any]:
    if not context.is_dir():
        raise LocalIsolationError("Docker build context missing")
    actual = tuple(
        sorted(
            path.relative_to(context).as_posix()
            for path in context.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    )
    if actual != tuple(sorted(expected_files)):
        raise LocalIsolationError("Docker build context file scope mismatch")
    files: list[dict[str, Any]] = []
    for relative in actual:
        path = context / relative
        if path.is_symlink():
            raise LocalIsolationError(
                "Docker build context symlink is not allowed"
            )
        payload = path.read_bytes()
        files.append(
            {
                "bytes": len(payload),
                "path": relative,
                "sha256": _sha256(payload),
            }
        )
    return {
        "content_sha256": _sha256(canonical_json_bytes(files)),
        "files": files,
    }


def _assert_source_snapshot_unchanged(
    *,
    candidate_scope: Mapping[str, Any],
    evaluator_scope: Mapping[str, Any],
    runner_descriptor: Mapping[str, Any],
) -> None:
    current_candidate = _source_scope(
        CANDIDATE_CONTEXT,
        expected_files=CANDIDATE_CONTEXT_FILES,
    )
    current_evaluator = _source_scope(
        EVALUATOR_CONTEXT,
        expected_files=EVALUATOR_CONTEXT_FILES,
    )
    current_runner = _descriptor(Path(__file__).read_bytes())
    if (
        current_candidate != candidate_scope
        or current_evaluator != evaluator_scope
        or current_runner != runner_descriptor
    ):
        raise LocalIsolationError(
            "source snapshot changed during image build or probe run"
        )


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
        raise LocalIsolationError(f"{field} is invalid")
    return value


def validate_candidate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != _REQUEST_FIELDS:
        raise LocalIsolationError("candidate request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise LocalIsolationError("candidate request schema mismatch")
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
        raise LocalIsolationError("run_id is invalid")
    if _NONCE_RE.fullmatch(nonce) is None:
        raise LocalIsolationError("nonce is invalid")
    items = value.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 64:
        raise LocalIsolationError("candidate request item bound violated")
    seen: set[str] = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _REQUEST_ITEM_FIELDS
        ):
            raise LocalIsolationError("candidate request item fields mismatch")
        item_id = _bounded_string(
            item.get("item_id"),
            field="item_id",
            maximum_bytes=128,
        )
        if _ID_RE.fullmatch(item_id) is None or item_id in seen:
            raise LocalIsolationError("item_id invalid or duplicated")
        seen.add(item_id)
        _bounded_string(
            item.get("stem"),
            field="stem",
            maximum_bytes=4096,
        )
        choices = item.get("choices")
        if not isinstance(choices, list) or not 2 <= len(choices) <= 10:
            raise LocalIsolationError("candidate choice count invalid")
        checked = [
            _bounded_string(
                choice,
                field="choice",
                maximum_bytes=2048,
            )
            for choice in choices
        ]
        if len(set(checked)) != len(checked):
            raise LocalIsolationError("candidate choices are duplicated")
    return json.loads(canonical_json_bytes(value))


def _validate_probe_map(
    value: Any,
    *,
    name: str,
    expected_ids: frozenset[str],
) -> None:
    if (
        not isinstance(value, dict)
        or frozenset(value) != expected_ids
    ):
        raise LocalIsolationError(f"{name} probe map missing")
    for probe in value.values():
        if (
            not isinstance(probe, dict)
            or frozenset(probe) != {"passed", "error_type"}
            or probe.get("passed") is not True
            or (
                probe.get("error_type") is not None
                and not isinstance(probe.get("error_type"), str)
            )
        ):
            raise LocalIsolationError(f"{name} probe failed or malformed")


def validate_candidate_response(
    value: Any,
    *,
    request: Mapping[str, Any],
    request_payload: bytes,
    stage_payload: bytes,
    network_probe_payload: bytes,
) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _CANDIDATE_RESPONSE_FIELDS
    ):
        raise LocalIsolationError("candidate response fields mismatch")
    if value.get("schema_version") != CANDIDATE_RESPONSE_SCHEMA:
        raise LocalIsolationError("candidate response schema mismatch")
    if (
        value.get("run_id") != request["run_id"]
        or value.get("nonce") != request["nonce"]
        or value.get("request_sha256") != _sha256(request_payload)
        or value.get("stage_sha256") != _sha256(stage_payload)
        or value.get("network_probe_sha256")
        != _sha256(network_probe_payload)
        or not _strict_literal_equal(
            value.get("runtime"),
            {"gid": CANDIDATE_UID, "uid": CANDIDATE_UID},
        )
        or not _strict_literal_equal(
            value.get("scope"),
            {
                "capability_evaluation_performed": False,
                "local_isolation_probe_only": True,
            },
        )
        or value.get("all_probes_passed") is not True
    ):
        raise LocalIsolationError("candidate response binding mismatch")
    _validate_probe_map(
        value.get("probes"),
        name="candidate",
        expected_ids=EXPECTED_CANDIDATE_PROBE_IDS,
    )
    expected_ids = [item["item_id"] for item in request["items"]]
    items = value.get("items")
    if not isinstance(items, list) or len(items) != len(expected_ids):
        raise LocalIsolationError("candidate response item count mismatch")
    for index, item in enumerate(items):
        if (
            not isinstance(item, dict)
            or frozenset(item) != {"decision", "item_id", "reason"}
            or item.get("item_id") != expected_ids[index]
            or item.get("decision") != "ABSTAIN"
            or item.get("reason")
            != "local_isolation_probe_no_capability_evaluation"
        ):
            raise LocalIsolationError("candidate response item mismatch")
    return json.loads(canonical_json_bytes(value))


def verify_local_fixture_evaluation(
    value: Any,
    *,
    payload: bytes,
    key: bytes,
    request: Mapping[str, Any],
    request_payload: bytes,
    response_payload: bytes,
    gold_payload: bytes,
    network_probe_payload: bytes,
) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _FIXTURE_EVALUATION_FIELDS
    ):
        raise LocalIsolationError("fixture evaluation fields mismatch")
    if (
        value.get("schema_version") != FIXTURE_EVALUATION_SCHEMA
        or value.get("local_fixture_only") is not True
        or value.get("candidate_response_contract_passed") is not True
        or value.get("fixture_gold_item_id_alignment_passed") is not True
        or value.get("fixture_gold_used_for_capability_scoring") is not False
        or value.get("run_id") != request["run_id"]
        or value.get("nonce") != request["nonce"]
        or value.get("request_sha256") != _sha256(request_payload)
        or value.get("network_probe_sha256")
        != _sha256(network_probe_payload)
        or value.get("candidate_response_sha256")
        != _sha256(response_payload)
        or value.get("fixture_gold_digest_sha256")
        != _sha256(gold_payload)
        or not _strict_literal_equal(
            value.get("runtime"),
            {"gid": EVALUATOR_UID, "uid": EVALUATOR_UID},
        )
        or not _strict_literal_equal(
            value.get("claims"),
            FIXTURE_FALSE_CLAIMS,
        )
    ):
        raise LocalIsolationError("fixture evaluation binding mismatch")
    _validate_probe_map(
        value.get("probes"),
        name="evaluator",
        expected_ids=EXPECTED_EVALUATOR_PROBE_IDS,
    )
    signature = value.get("signature")
    if (
        not isinstance(signature, dict)
        or frozenset(signature) != _LOCAL_SIGNATURE_FIELDS
        or signature.get("scheme") != LOCAL_SIGNATURE_SCHEME
        or signature.get("key_id")
        != "local-fixture:" + _sha256(key)[:24]
        or _SHA256_RE.fullmatch(str(signature.get("payload_sha256")))
        is None
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(signature.get("signature_hex")),
        )
        is None
    ):
        raise LocalIsolationError("local fixture signature envelope invalid")
    unsigned = json.loads(canonical_json_bytes(value))
    unsigned.pop("signature")
    signed_payload = canonical_json_bytes(unsigned)
    if (
        signature["payload_sha256"] != _sha256(signed_payload)
        or not hmac.compare_digest(
            signature["signature_hex"],
            hmac.new(
                key,
                signed_payload,
                hashlib.sha256,
            ).hexdigest(),
        )
    ):
        raise LocalIsolationError("local fixture HMAC invalid")
    if payload != canonical_json_bytes(value) + b"\n":
        raise LocalIsolationError("fixture evaluation bytes changed")
    return json.loads(canonical_json_bytes(value))


def _run_docker(
    arguments: Sequence[str],
    *,
    timeout: int = DOCKER_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            ["docker", *arguments],
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalIsolationError(
            f"Docker command failed to execute: {arguments[0]}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode(
            "utf-8",
            errors="replace",
        )[-2000:]
        raise LocalIsolationError(
            f"Docker command failed: {arguments[0]}: {detail}"
        )
    return completed


def _docker_json(arguments: Sequence[str]) -> Any:
    payload = _run_docker(arguments).stdout
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LocalIsolationError("Docker returned invalid JSON") from exc


def docker_environment() -> dict[str, Any]:
    context = _run_docker(["context", "show"]).stdout.decode(
        "utf-8",
        errors="strict",
    ).strip()
    version = _docker_json(["version", "--format", "{{json .}}"])
    info = _docker_json(["info", "--format", "{{json .}}"])
    client = version.get("Client") if isinstance(version, dict) else None
    server = version.get("Server") if isinstance(version, dict) else None
    if (
        not isinstance(client, dict)
        or not isinstance(server, dict)
        or not isinstance(info, dict)
        or not context
    ):
        raise LocalIsolationError("Docker environment metadata missing")
    security_options = info.get("SecurityOptions")
    raw_string_fields = (
        info.get("Architecture"),
        info.get("CgroupDriver"),
        info.get("CgroupVersion"),
        client.get("Version"),
        info.get("KernelVersion"),
        info.get("OperatingSystem"),
        info.get("OSType"),
        server.get("Version"),
        info.get("Driver"),
    )
    if (
        not isinstance(security_options, list)
        or not security_options
        or not all(
            isinstance(option, str) and bool(option)
            for option in security_options
        )
        or not all(
            isinstance(field, str) and bool(field)
            for field in raw_string_fields
        )
    ):
        raise LocalIsolationError("Docker security options missing")
    normalized = {
        "architecture": info["Architecture"],
        "cgroup_driver": info["CgroupDriver"],
        "cgroup_version": info["CgroupVersion"],
        "client_version": client["Version"],
        "context": context,
        "kernel_version": info["KernelVersion"],
        "operating_system": info["OperatingSystem"],
        "os_type": info["OSType"],
        "security_options": sorted(security_options),
        "server_version": server["Version"],
        "storage_driver": info["Driver"],
    }
    if (
        normalized["os_type"] != "linux"
        or not any(
            option.startswith("name=seccomp")
            for option in normalized["security_options"]
        )
        or not any(
            option.startswith("name=cgroupns")
            for option in normalized["security_options"]
        )
        or normalized["cgroup_version"] != "2"
    ):
        raise LocalIsolationError(
            "required Docker Linux seccomp/cgroup isolation unavailable"
        )
    return normalized


def build_image(
    *,
    role: str,
    context: Path,
    source_scope: Mapping[str, Any],
) -> str:
    tag = (
        f"atanor-science-e4-local-{role}:"
        f"{str(source_scope['content_sha256'])[:20]}"
    )
    _run_docker(
        [
            "build",
            "--pull",
            "--platform",
            "linux/amd64",
            "--build-arg",
            f"SOURCE_SHA256={source_scope['content_sha256']}",
            "--tag",
            tag,
            str(context),
        ]
    )
    return tag


def image_evidence(
    image: str,
    *,
    role_label: str,
    context_sha256: str,
) -> dict[str, Any]:
    value = _docker_json(["image", "inspect", image])
    if not isinstance(value, list) or len(value) != 1:
        raise LocalIsolationError("Docker image inspect shape invalid")
    row = value[0]
    config = row.get("Config") if isinstance(row, dict) else None
    labels = config.get("Labels") if isinstance(config, dict) else None
    rootfs = row.get("RootFS") if isinstance(row, dict) else None
    layers = rootfs.get("Layers") if isinstance(rootfs, dict) else None
    if (
        not isinstance(row, dict)
        or not isinstance(config, dict)
        or not isinstance(labels, dict)
        or labels.get("org.atanor.science-e4-local.role") != role_label
        or labels.get(
            "org.atanor.science-e4-local.context-sha256"
        )
        != context_sha256
        or labels.get("org.atanor.science-e4-local.authority") != "none"
        or not isinstance(layers, list)
        or not layers
        or not all(
            isinstance(layer, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", layer) is not None
            for layer in layers
        )
        or not isinstance(row.get("Id"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", row["Id"]) is None
        or row.get("Architecture") != "amd64"
        or row.get("Os") != "linux"
    ):
        raise LocalIsolationError("Docker image labels or rootfs invalid")
    repo_digests = row.get("RepoDigests")
    if repo_digests is None:
        repo_digests = []
    if (
        not isinstance(repo_digests, list)
        or not all(
            isinstance(digest, str) and bool(digest)
            for digest in repo_digests
        )
    ):
        raise LocalIsolationError("Docker image repo digests invalid")
    return {
        "architecture": row["Architecture"],
        "id": row["Id"],
        "os": row["Os"],
        "repo_digests": sorted(repo_digests),
        "rootfs_layers": list(layers),
        "source_context_sha256": context_sha256,
    }


def _mount_argument(source: Path, destination: str) -> str:
    resolved = source.resolve()
    if not resolved.is_file():
        raise LocalIsolationError("Docker mount source is not a file")
    if "," in str(resolved):
        raise LocalIsolationError(
            "Docker mount source contains unsupported comma"
        )
    return (
        f"type=bind,source={resolved},"
        f"target={destination},readonly"
    )


def container_create_arguments(
    *,
    name: str,
    image: str,
    uid: int,
    mounts: Mapping[str, Path],
) -> list[str]:
    arguments = [
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--user",
        f"{uid}:{uid}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(PIDS_LIMIT),
        "--memory",
        str(MEMORY_BYTES),
        "--memory-swap",
        str(MEMORY_BYTES),
        "--cpus",
        "1.0",
        "--ulimit",
        f"nofile={NOFILE_LIMIT}:{NOFILE_LIMIT}",
        "--tmpfs",
        (
            "/tmp:rw,noexec,nosuid,nodev,"
            f"size={TMPFS_BYTES}"
        ),
        "--ipc",
        "private",
    ]
    for destination in sorted(mounts):
        arguments.extend(
            ["--mount", _mount_argument(mounts[destination], destination)]
        )
    arguments.append(image)
    return arguments


def _control_container_arguments(
    *,
    name: str,
    image: str,
    network: str,
    code: str,
) -> list[str]:
    return [
        "create",
        "--name",
        name,
        "--network",
        network,
        "--read-only",
        "--user",
        "10003:10003",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "16",
        "--memory",
        str(64 * 1024 * 1024),
        "--memory-swap",
        str(64 * 1024 * 1024),
        "--cpus",
        "0.25",
        "--ulimit",
        "nofile=64:64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=4194304",
        "--ipc",
        "private",
        "--entrypoint",
        "/usr/bin/env",
        image,
        "-i",
        "LANG=C.UTF-8",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "python",
        "-I",
        "-B",
        "-c",
        code,
    ]


def _create_tracked_container(
    *,
    arguments: Sequence[str],
    name: str,
    created: list[str],
) -> str:
    completed = _run_docker(arguments)
    # Docker create has succeeded at this point.  Register cleanup before
    # decoding or trusting any returned identifier.
    created.append(name)
    try:
        container_id = completed.stdout.decode(
            "ascii",
            errors="strict",
        ).strip()
    except UnicodeError as exc:
        raise LocalIsolationError(
            "created container id is not strict ASCII"
        ) from exc
    if _CONTAINER_ID_RE.fullmatch(container_id) is None:
        raise LocalIsolationError("created container id is invalid")
    return container_id


def _require_container_id(
    inspect_row: Mapping[str, Any],
    *,
    expected_id: str,
) -> None:
    if inspect_row.get("Id") != expected_id:
        raise LocalIsolationError(
            "Docker create id does not match container inspect id"
        )


def _network_inspect(name: str) -> dict[str, Any]:
    value = _docker_json(["network", "inspect", name])
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not isinstance(value[0], dict)
    ):
        raise LocalIsolationError("Docker network inspect shape invalid")
    return value[0]


def _create_internal_network(
    name: str,
    *,
    created: list[str],
) -> str:
    completed = _run_docker(
        [
            "network",
            "create",
            "--driver",
            "bridge",
            "--internal",
            "--label",
            "org.atanor.science-e4-local.role=network-sentinel",
            name,
        ]
    )
    # Network creation has succeeded. Register cleanup before decoding or
    # trusting the daemon-returned identifier.
    created.append(name)
    try:
        network_id = completed.stdout.decode(
            "ascii",
            errors="strict",
        ).strip()
    except UnicodeError as exc:
        raise LocalIsolationError(
            "created network id is not strict ASCII"
        ) from exc
    if _CONTAINER_ID_RE.fullmatch(network_id) is None:
        raise LocalIsolationError("created network id is invalid")
    inspect_row = _network_inspect(name)
    labels = inspect_row.get("Labels")
    if (
        inspect_row.get("Id") != network_id
        or inspect_row.get("Name") != name
        or inspect_row.get("Driver") != "bridge"
        or inspect_row.get("Internal") is not True
        or not isinstance(labels, dict)
        or labels.get("org.atanor.science-e4-local.role")
        != "network-sentinel"
    ):
        raise LocalIsolationError(
            "Docker internal network binding mismatch"
        )
    return network_id


def _sentinel_address(name: str, network: str) -> str:
    inspect_row = _container_inspect(name)
    settings = inspect_row.get("NetworkSettings")
    networks = settings.get("Networks") if isinstance(settings, dict) else None
    record = networks.get(network) if isinstance(networks, dict) else None
    address = record.get("IPAddress") if isinstance(record, dict) else None
    if (
        not isinstance(address, str)
        or re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", address) is None
        or any(int(octet) > 255 for octet in address.split("."))
    ):
        raise LocalIsolationError("network sentinel address unavailable")
    return address


def _run_network_positive_control(
    *,
    image: str,
    network: str,
    sentinel_name: str,
    created: list[str],
) -> tuple[dict[str, Any], bytes, str, dict[str, Any]]:
    sentinel_code = (
        "import socket\n"
        "s=socket.socket()\n"
        "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
        f"s.bind(('0.0.0.0',{NETWORK_SENTINEL_PORT}))\n"
        "s.listen(8)\n"
        "while True:\n"
        " c,_=s.accept()\n"
        " c.sendall(b'atanor-local-sentinel')\n"
        " c.close()\n"
    )
    sentinel_id = _create_tracked_container(
        arguments=_control_container_arguments(
            name=sentinel_name,
            image=image,
            network=network,
            code=sentinel_code,
        ),
        name=sentinel_name,
        created=created,
    )
    _run_docker(["start", sentinel_name], timeout=30)
    sentinel_inspect = _container_inspect(sentinel_name)
    _require_container_id(
        sentinel_inspect,
        expected_id=sentinel_id,
    )
    address = _sentinel_address(sentinel_name, network)
    network_probe = {
        "host": address,
        "port": NETWORK_SENTINEL_PORT,
        "schema_version": NETWORK_PROBE_SCHEMA,
    }
    liveness = _check_network_sentinel_liveness(
        image=image,
        network=network,
        sentinel_name=sentinel_name,
        sentinel_id=sentinel_id,
        network_probe=network_probe,
        checkpoint=NETWORK_LIVENESS_CHECKPOINTS[0],
        created=created,
    )
    return (
        network_probe,
        canonical_json_bytes(network_probe) + b"\n",
        sentinel_id,
        liveness,
    )


def _check_network_sentinel_liveness(
    *,
    image: str,
    network: str,
    sentinel_name: str,
    sentinel_id: str,
    network_probe: Mapping[str, Any],
    checkpoint: str,
    created: list[str],
) -> dict[str, Any]:
    if checkpoint not in NETWORK_LIVENESS_CHECKPOINTS:
        raise LocalIsolationError("network liveness checkpoint invalid")
    sentinel_inspect = _container_inspect(sentinel_name)
    _require_container_id(
        sentinel_inspect,
        expected_id=sentinel_id,
    )
    state = sentinel_inspect.get("State")
    if (
        not isinstance(state, dict)
        or state.get("Running") is not True
        or state.get("Dead") is True
        or state.get("OOMKilled") is True
        or bool(state.get("Error"))
    ):
        raise LocalIsolationError(
            f"network sentinel is not live at {checkpoint}"
        )
    address = _sentinel_address(sentinel_name, network)
    if (
        address != network_probe.get("host")
        or network_probe.get("port") != NETWORK_SENTINEL_PORT
        or network_probe.get("schema_version") != NETWORK_PROBE_SCHEMA
    ):
        raise LocalIsolationError(
            "network sentinel endpoint changed during isolated runs"
        )
    positive_name = (
        "atanor-science-e4-positive-" + uuid.uuid4().hex
    )
    client_code = (
        "import socket,sys,time\n"
        f"target=('{address}',{NETWORK_SENTINEL_PORT})\n"
        "last=None\n"
        "for _ in range(40):\n"
        " try:\n"
        "  s=socket.create_connection(target,timeout=0.25)\n"
        "  data=s.recv(64)\n"
        "  s.close()\n"
        "  if data==b'atanor-local-sentinel':\n"
        "   sys.stdout.write('sentinel-reachable\\n')\n"
        "   raise SystemExit(0)\n"
        " except OSError as exc:\n"
        "  last=exc\n"
        "  time.sleep(0.05)\n"
        "raise SystemExit(3)\n"
    )
    positive_id = _create_tracked_container(
        arguments=_control_container_arguments(
            name=positive_name,
            image=image,
            network=network,
            code=client_code,
        ),
        name=positive_name,
        created=created,
    )
    positive_inspect = _container_inspect(positive_name)
    _require_container_id(
        positive_inspect,
        expected_id=positive_id,
    )
    output = _start_attached(positive_name)
    _post_run_state(_container_inspect(positive_name))
    if output != b"sentinel-reachable\n":
        raise LocalIsolationError(
            "runner-owned network positive control failed"
        )
    return {
        "checkpoint": checkpoint,
        "reachable": True,
    }


def _portable_host_path(value: str | Path) -> str:
    text = str(value).replace("\\", "/").rstrip("/")
    lowered = text.lower()
    windows_semantics = (
        re.fullmatch(r"[A-Za-z]:/.*", text) is not None
    )
    for prefix in (
        "/run/desktop/mnt/host/",
        "/host_mnt/",
        "/mnt/host/",
    ):
        if lowered.startswith(prefix):
            rest = text[len(prefix):]
            if len(rest) >= 2 and rest[1] == "/":
                text = rest[0] + ":" + rest[1:]
                windows_semantics = True
            break
    return text.casefold() if windows_semantics else text


def _normalize_tmpfs_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != {"/tmp"}:
        raise LocalIsolationError("Docker tmpfs destination mismatch")
    raw_options = value.get("/tmp")
    if not isinstance(raw_options, str):
        raise LocalIsolationError("Docker tmpfs options are not a string")
    options = raw_options.split(",")
    expected = [
        "rw",
        "noexec",
        "nosuid",
        "nodev",
        f"size={TMPFS_BYTES}",
    ]
    if options != expected:
        raise LocalIsolationError(
            "Docker tmpfs options are not the exact hardened policy"
        )
    size_key, size_text = options[4].split("=", 1)
    if size_key != "size" or not size_text.isascii() or not size_text.isdigit():
        raise LocalIsolationError("Docker tmpfs size option is invalid")
    size_bytes = int(size_text, 10)
    if size_bytes != TMPFS_BYTES:
        raise LocalIsolationError("Docker tmpfs size is not exact")
    return {
        "destination": "/tmp",
        "noexec": options[1] == "noexec",
        "nodev": options[3] == "nodev",
        "nosuid": options[2] == "nosuid",
        "size_bytes": size_bytes,
    }


def _tmpfs_policy_valid(value: Any) -> bool:
    try:
        _normalize_tmpfs_policy(value)
    except LocalIsolationError:
        return False
    return True


def normalize_container_inspect(
    *,
    role: str,
    inspect_row: Mapping[str, Any],
    image: Mapping[str, Any],
    expected_uid: int,
    expected_mounts: Mapping[str, Path],
    artifact_descriptors: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    config = inspect_row.get("Config")
    host = inspect_row.get("HostConfig")
    state = inspect_row.get("State")
    mounts = inspect_row.get("Mounts")
    network = inspect_row.get("NetworkSettings")
    if not all(
        isinstance(value, dict)
        for value in (config, host, state, network)
    ) or not isinstance(mounts, list):
        raise LocalIsolationError("Docker container inspect shape invalid")
    tmpfs_policy = _normalize_tmpfs_policy(host.get("Tmpfs"))
    labels = config.get("Labels")
    expected_role_label = (
        "candidate" if role == "candidate" else "local-fixture-evaluator"
    )
    if (
        config.get("User") != f"{expected_uid}:{expected_uid}"
        or inspect_row.get("Image") != image["id"]
        or not isinstance(labels, dict)
        or labels.get("org.atanor.science-e4-local.role")
        != expected_role_label
        or labels.get("org.atanor.science-e4-local.authority") != "none"
        or host.get("NetworkMode") != "none"
        or host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or sorted(host.get("CapDrop") or []) != ["ALL"]
        or type(host.get("PidsLimit")) is not int
        or host.get("PidsLimit") != PIDS_LIMIT
        or type(host.get("Memory")) is not int
        or host.get("Memory") != MEMORY_BYTES
        or type(host.get("MemorySwap")) is not int
        or host.get("MemorySwap") != MEMORY_BYTES
        or type(host.get("NanoCpus")) is not int
        or host.get("NanoCpus") != NANO_CPUS
        or host.get("IpcMode") != "private"
        or host.get("PidMode") not in ("", "private")
        or host.get("Devices") not in (None, [])
        or host.get("DeviceRequests") not in (None, [])
        or host.get("PortBindings") not in (None, {})
        or config.get("ExposedPorts") not in (None, {})
    ):
        raise LocalIsolationError(
            f"{role} Docker hardening policy mismatch"
        )
    if not _strict_literal_equal(
        host.get("SecurityOpt"),
        ["no-new-privileges:true"],
    ):
        raise LocalIsolationError(
            f"{role} no-new-privileges policy mismatch"
        )
    ulimits = host.get("Ulimits")
    if not _strict_literal_equal(
        ulimits,
        [
            {
                "Hard": NOFILE_LIMIT,
                "Name": "nofile",
                "Soft": NOFILE_LIMIT,
            }
        ],
    ):
        raise LocalIsolationError(f"{role} ulimit policy mismatch")
    actual_by_destination: dict[str, Mapping[str, Any]] = {}
    for mount in mounts:
        if not isinstance(mount, dict):
            raise LocalIsolationError("Docker mount record invalid")
        destination = mount.get("Destination")
        if not isinstance(destination, str) or destination in (
            actual_by_destination
        ):
            raise LocalIsolationError("Docker mount destination invalid")
        actual_by_destination[destination] = mount
    if frozenset(actual_by_destination) != frozenset(expected_mounts):
        raise LocalIsolationError(f"{role} mount scope mismatch")
    normalized_mounts: list[dict[str, Any]] = []
    role_mount_contract = (
        CANDIDATE_MOUNTS if role == "candidate" else EVALUATOR_MOUNTS
    )
    for destination in sorted(expected_mounts):
        mount = actual_by_destination[destination]
        expected_source = expected_mounts[destination].resolve()
        if (
            mount.get("Type") != "bind"
            or mount.get("RW") is not False
            or not isinstance(mount.get("Source"), str)
            or _portable_host_path(mount["Source"])
            != _portable_host_path(expected_source)
        ):
            raise LocalIsolationError(
                f"{role} mount is not the exact read-only source"
            )
        artifact_name = role_mount_contract[destination]
        descriptor = artifact_descriptors[artifact_name]
        normalized_mounts.append(
            {
                "destination": destination,
                "read_only": True,
                "source_artifact": artifact_name,
                "source_bytes": descriptor["bytes"],
                "source_path_recorded": False,
                "source_sha256": descriptor["sha256"],
                "type": "bind",
            }
        )
    if role == "candidate" and (
        frozenset(actual_by_destination)
        & PROHIBITED_CANDIDATE_DESTINATIONS
    ):
        raise LocalIsolationError("candidate received prohibited mount")
    networks = network.get("Networks")
    if not isinstance(networks, dict) or not set(networks).issubset({"none"}):
        raise LocalIsolationError(f"{role} network attachment mismatch")
    return {
        "cap_drop": ["ALL"],
        "devices": [],
        "image_id": image["id"],
        "ipc_mode": "private",
        "memory_bytes": MEMORY_BYTES,
        "memory_swap_bytes": MEMORY_BYTES,
        "mounts": normalized_mounts,
        "nano_cpus": NANO_CPUS,
        "network_mode": "none",
        "no_new_privileges": True,
        "pids_limit": PIDS_LIMIT,
        "pid_mode": "private",
        "port_bindings": {},
        "privileged": False,
        "read_only_rootfs": True,
        "tmpfs": tmpfs_policy,
        "ulimit_nofile": {
            "hard": NOFILE_LIMIT,
            "soft": NOFILE_LIMIT,
        },
        "user": f"{expected_uid}:{expected_uid}",
    }


def _container_inspect(name: str) -> dict[str, Any]:
    value = _docker_json(["inspect", name])
    if not isinstance(value, list) or len(value) != 1:
        raise LocalIsolationError("Docker container inspect shape invalid")
    if not isinstance(value[0], dict):
        raise LocalIsolationError("Docker container inspect record invalid")
    return value[0]


def _post_run_state(inspect_row: Mapping[str, Any]) -> dict[str, Any]:
    state = inspect_row.get("State")
    if not isinstance(state, dict):
        raise LocalIsolationError("Docker post-run state missing")
    if (
        type(state.get("Dead")) is not bool
        or not isinstance(state.get("Error"), str)
        or type(state.get("ExitCode")) is not int
        or type(state.get("OOMKilled")) is not bool
        or type(state.get("Running")) is not bool
    ):
        raise LocalIsolationError("Docker post-run state types invalid")
    result = {
        "dead": state.get("Dead") is True,
        "error_present": bool(state.get("Error")),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled") is True,
        "running": state.get("Running") is True,
    }
    if (
        result["dead"]
        or result["error_present"]
        or result["exit_code"] != 0
        or result["oom_killed"]
        or result["running"]
    ):
        raise LocalIsolationError("Docker container did not exit cleanly")
    return result


def _start_attached(name: str) -> bytes:
    completed = _run_docker(
        ["start", "--attach", name],
        timeout=CONTAINER_TIMEOUT_SECONDS,
    )
    if len(completed.stdout) > MAX_JSON_BYTES:
        raise LocalIsolationError("container stdout byte bound violated")
    return completed.stdout


def _remove_container(name: str) -> str:
    try:
        completed = subprocess.run(
            ["docker", "rm", "--force", name],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "remove_failed"
    if completed.returncode == 0:
        return "removed"
    detail = completed.stderr.decode("utf-8", errors="replace").casefold()
    if "no such container" in detail or "not found" in detail:
        return "not_found"
    return "remove_failed"


def _remove_network(name: str) -> str:
    try:
        completed = subprocess.run(
            ["docker", "network", "rm", name],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "remove_failed"
    if completed.returncode == 0:
        return "removed"
    detail = completed.stderr.decode("utf-8", errors="replace").casefold()
    if "no such network" in detail or "not found" in detail:
        return "not_found"
    return "remove_failed"


def _write_temp(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def _manifest_checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _build_claims() -> dict[str, Any]:
    return dict(FALSE_CLAIMS)


def _require_contract(condition: bool, message: str) -> None:
    if not condition:
        raise LocalIsolationError(message)


def _strict_literal_equal(value: Any, expected: Any) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (
            frozenset(value) == frozenset(expected)
            and all(
                _strict_literal_equal(value[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return len(value) == len(expected) and all(
            _strict_literal_equal(actual, wanted)
            for actual, wanted in zip(value, expected)
        )
    return value == expected


def _validate_descriptor(
    value: Any,
    *,
    name: str,
    key_descriptor: bool = False,
) -> dict[str, Any]:
    expected_fields = (
        {"bytes", "ephemeral", "material_recorded", "sha256"}
        if key_descriptor
        else {"bytes", "sha256"}
    )
    _require_contract(
        isinstance(value, dict) and frozenset(value) == expected_fields,
        f"{name} descriptor fields mismatch",
    )
    _require_contract(
        type(value.get("bytes")) is int and value["bytes"] > 0,
        f"{name} descriptor byte count invalid",
    )
    _require_contract(
        isinstance(value.get("sha256"), str)
        and _SHA256_RE.fullmatch(value["sha256"]) is not None,
        f"{name} descriptor digest invalid",
    )
    if key_descriptor:
        _require_contract(
            value["bytes"] == 32
            and value.get("ephemeral") is True
            and value.get("material_recorded") is False,
            "local fixture key descriptor scope invalid",
        )
    return value


def _validate_artifacts(value: Any) -> dict[str, Any]:
    expected_names = {
        "candidate_response",
        "fixture_evaluation",
        "gold",
        "local_fixture_key",
        "network_probe",
        "request",
        "stage",
    }
    _require_contract(
        isinstance(value, dict) and frozenset(value) == expected_names,
        "artifact inventory mismatch",
    )
    for name in sorted(expected_names - {"local_fixture_key"}):
        _validate_descriptor(value[name], name=f"artifact {name}")
    _validate_descriptor(
        value["local_fixture_key"],
        name="artifact local_fixture_key",
        key_descriptor=True,
    )
    return value


def _validate_source_context(
    value: Any,
    *,
    name: str,
    expected_files: Sequence[str],
) -> dict[str, Any]:
    _require_contract(
        isinstance(value, dict)
        and frozenset(value) == {"content_sha256", "files"},
        f"{name} source context fields mismatch",
    )
    files = value.get("files")
    expected_paths = list(sorted(expected_files))
    _require_contract(
        isinstance(files, list) and len(files) == len(expected_paths),
        f"{name} source file inventory mismatch",
    )
    actual_paths: list[str] = []
    for row in files:
        _require_contract(
            isinstance(row, dict)
            and frozenset(row) == {"bytes", "path", "sha256"},
            f"{name} source file fields mismatch",
        )
        path = row.get("path")
        _require_contract(
            isinstance(path, str)
            and path
            and "\\" not in path
            and not path.startswith("/")
            and ".." not in path.split("/"),
            f"{name} source path invalid",
        )
        _require_contract(
            type(row.get("bytes")) is int and row["bytes"] > 0,
            f"{name} source byte count invalid",
        )
        _require_contract(
            isinstance(row.get("sha256"), str)
            and _SHA256_RE.fullmatch(row["sha256"]) is not None,
            f"{name} source digest invalid",
        )
        actual_paths.append(path)
    _require_contract(
        actual_paths == expected_paths,
        f"{name} source paths mismatch",
    )
    _require_contract(
        isinstance(value.get("content_sha256"), str)
        and value["content_sha256"]
        == _sha256(canonical_json_bytes(files)),
        f"{name} aggregate source digest mismatch",
    )
    return value


def _validate_source(value: Any) -> dict[str, Any]:
    _require_contract(
        isinstance(value, dict)
        and frozenset(value)
        == {"candidate_context", "evaluator_context", "runner"},
        "source evidence fields mismatch",
    )
    candidate = _validate_source_context(
        value["candidate_context"],
        name="candidate",
        expected_files=CANDIDATE_CONTEXT_FILES,
    )
    evaluator = _validate_source_context(
        value["evaluator_context"],
        name="evaluator",
        expected_files=EVALUATOR_CONTEXT_FILES,
    )
    _validate_descriptor(value["runner"], name="runner source")
    _require_contract(
        candidate["content_sha256"] != evaluator["content_sha256"]
        and candidate["files"] != evaluator["files"],
        "candidate and evaluator source contexts are not separate",
    )
    return value


def _validate_image(
    value: Any,
    *,
    name: str,
    source_context_sha256: str,
) -> dict[str, Any]:
    expected_fields = {
        "architecture",
        "id",
        "os",
        "repo_digests",
        "rootfs_layers",
        "source_context_sha256",
    }
    _require_contract(
        isinstance(value, dict) and frozenset(value) == expected_fields,
        f"{name} image evidence fields mismatch",
    )
    _require_contract(
        value.get("architecture") == "amd64",
        f"{name} image architecture invalid",
    )
    _require_contract(
        isinstance(value.get("id"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value["id"])
        is not None,
        f"{name} image id invalid",
    )
    _require_contract(
        value.get("os") == "linux",
        f"{name} image OS invalid",
    )
    repo_digests = value.get("repo_digests")
    _require_contract(
        isinstance(repo_digests, list)
        and all(
            isinstance(row, str) and bool(row)
            for row in repo_digests
        )
        and repo_digests == sorted(set(repo_digests)),
        f"{name} image repo digests invalid",
    )
    layers = value.get("rootfs_layers")
    _require_contract(
        isinstance(layers, list)
        and bool(layers)
        and all(
            isinstance(row, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", row) is not None
            for row in layers
        ),
        f"{name} image rootfs layers invalid",
    )
    _require_contract(
        value.get("source_context_sha256") == source_context_sha256,
        f"{name} image source context binding mismatch",
    )
    return value


def _validate_environment(value: Any) -> dict[str, Any]:
    expected_fields = {
        "architecture",
        "cgroup_driver",
        "cgroup_version",
        "client_version",
        "context",
        "kernel_version",
        "operating_system",
        "os_type",
        "security_options",
        "server_version",
        "storage_driver",
    }
    _require_contract(
        isinstance(value, dict) and frozenset(value) == expected_fields,
        "Docker environment fields mismatch",
    )
    for field in expected_fields - {"security_options"}:
        _require_contract(
            isinstance(value.get(field), str) and bool(value[field]),
            f"Docker environment {field} invalid",
        )
    security_options = value.get("security_options")
    _require_contract(
        isinstance(security_options, list)
        and security_options == sorted(set(security_options))
        and all(
            isinstance(option, str) and bool(option)
            for option in security_options
        )
        and any(
            option.startswith("name=seccomp")
            for option in security_options
        )
        and any(
            option.startswith("name=cgroupns")
            for option in security_options
        )
        and value.get("cgroup_version") == "2"
        and value.get("os_type") == "linux",
        "Docker environment isolation prerequisites invalid",
    )
    return value


def _validate_historical_inspect(
    value: Any,
    *,
    role: str,
    image_id: str,
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    expected_fields = {
        "cap_drop",
        "devices",
        "image_id",
        "ipc_mode",
        "memory_bytes",
        "memory_swap_bytes",
        "mounts",
        "nano_cpus",
        "network_mode",
        "no_new_privileges",
        "pids_limit",
        "pid_mode",
        "port_bindings",
        "privileged",
        "read_only_rootfs",
        "tmpfs",
        "ulimit_nofile",
        "user",
    }
    _require_contract(
        isinstance(value, dict) and frozenset(value) == expected_fields,
        f"{role} inspect fields mismatch",
    )
    expected_uid = CANDIDATE_UID if role == "candidate" else EVALUATOR_UID
    fixed = {
        "cap_drop": ["ALL"],
        "devices": [],
        "image_id": image_id,
        "ipc_mode": "private",
        "memory_bytes": MEMORY_BYTES,
        "memory_swap_bytes": MEMORY_BYTES,
        "nano_cpus": NANO_CPUS,
        "network_mode": "none",
        "no_new_privileges": True,
        "pids_limit": PIDS_LIMIT,
        "pid_mode": "private",
        "port_bindings": {},
        "privileged": False,
        "read_only_rootfs": True,
        "tmpfs": {
            "destination": "/tmp",
            "noexec": True,
            "nodev": True,
            "nosuid": True,
            "size_bytes": TMPFS_BYTES,
        },
        "ulimit_nofile": {
            "hard": NOFILE_LIMIT,
            "soft": NOFILE_LIMIT,
        },
        "user": f"{expected_uid}:{expected_uid}",
    }
    for field, expected in fixed.items():
        _require_contract(
            _strict_literal_equal(value.get(field), expected),
            f"{role} inspect {field} mismatch",
        )
    mount_contract = (
        CANDIDATE_MOUNTS if role == "candidate" else EVALUATOR_MOUNTS
    )
    mounts = value.get("mounts")
    _require_contract(
        isinstance(mounts, list)
        and len(mounts) == len(mount_contract),
        f"{role} inspect mount count mismatch",
    )
    expected_destinations = list(sorted(mount_contract))
    actual_destinations: list[str] = []
    for mount in mounts:
        _require_contract(
            isinstance(mount, dict)
            and frozenset(mount)
            == {
                "destination",
                "read_only",
                "source_artifact",
                "source_bytes",
                "source_path_recorded",
                "source_sha256",
                "type",
            },
            f"{role} inspect mount fields mismatch",
        )
        destination = mount.get("destination")
        _require_contract(
            isinstance(destination, str)
            and destination in mount_contract,
            f"{role} inspect mount destination invalid",
        )
        artifact_name = mount_contract[destination]
        artifact = artifacts[artifact_name]
        _require_contract(
            mount.get("read_only") is True
            and mount.get("source_path_recorded") is False
            and mount.get("type") == "bind"
            and mount.get("source_artifact") == artifact_name
            and type(mount.get("source_bytes")) is int
            and mount.get("source_bytes") == artifact["bytes"]
            and mount.get("source_sha256") == artifact["sha256"],
            f"{role} inspect mount artifact binding mismatch",
        )
        actual_destinations.append(destination)
    _require_contract(
        actual_destinations == expected_destinations,
        f"{role} inspect mount order or inventory mismatch",
    )
    return value


def _validate_post_run(value: Any, *, role: str) -> dict[str, Any]:
    expected = {
        "dead": False,
        "error_present": False,
        "exit_code": 0,
        "oom_killed": False,
        "running": False,
    }
    _require_contract(
        isinstance(value, dict)
        and frozenset(value) == frozenset(expected)
        and _strict_literal_equal(value, expected),
        f"{role} post-run state invalid",
    )
    return value


def _validate_docker(
    value: Any,
    *,
    source: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    _require_contract(
        isinstance(value, dict)
        and frozenset(value) == {"containers", "environment", "images"},
        "Docker evidence fields mismatch",
    )
    _validate_environment(value["environment"])
    images = value.get("images")
    _require_contract(
        isinstance(images, dict)
        and frozenset(images) == {"candidate", "evaluator"},
        "Docker image inventory mismatch",
    )
    candidate_image = _validate_image(
        images["candidate"],
        name="candidate",
        source_context_sha256=source["candidate_context"][
            "content_sha256"
        ],
    )
    evaluator_image = _validate_image(
        images["evaluator"],
        name="evaluator",
        source_context_sha256=source["evaluator_context"][
            "content_sha256"
        ],
    )
    _require_contract(
        candidate_image["id"] != evaluator_image["id"],
        "candidate and evaluator image ids coincide",
    )
    containers = value.get("containers")
    _require_contract(
        isinstance(containers, dict)
        and frozenset(containers) == {"candidate", "evaluator"},
        "Docker container inventory mismatch",
    )
    for role, image in (
        ("candidate", candidate_image),
        ("evaluator", evaluator_image),
    ):
        record = containers.get(role)
        _require_contract(
            isinstance(record, dict)
            and frozenset(record) == {"inspect", "post_run"},
            f"{role} container evidence fields mismatch",
        )
        _validate_historical_inspect(
            record["inspect"],
            role=role,
            image_id=image["id"],
            artifacts=artifacts,
        )
        _validate_post_run(record["post_run"], role=role)
    return value


def _validate_historical_candidate(
    value: Any,
    *,
    request: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    _require_contract(
        isinstance(value, dict)
        and frozenset(value) == _CANDIDATE_RESPONSE_FIELDS,
        "candidate response fields mismatch",
    )
    _require_contract(
        value.get("schema_version") == CANDIDATE_RESPONSE_SCHEMA
        and value.get("run_id") == request["run_id"]
        and value.get("nonce") == request["nonce"]
        and value.get("request_sha256") == artifacts["request"]["sha256"]
        and value.get("stage_sha256") == artifacts["stage"]["sha256"]
        and value.get("network_probe_sha256")
        == artifacts["network_probe"]["sha256"]
        and _strict_literal_equal(
            value.get("runtime"),
            {"gid": CANDIDATE_UID, "uid": CANDIDATE_UID},
        )
        and _strict_literal_equal(
            value.get("scope"),
            {
                "capability_evaluation_performed": False,
                "local_isolation_probe_only": True,
            },
        )
        and value.get("all_probes_passed") is True,
        "candidate response historical binding mismatch",
    )
    _validate_probe_map(
        value.get("probes"),
        name="candidate",
        expected_ids=EXPECTED_CANDIDATE_PROBE_IDS,
    )
    items = value.get("items")
    expected_ids = [item["item_id"] for item in request["items"]]
    _require_contract(
        isinstance(items, list) and len(items) == len(expected_ids),
        "candidate response item count mismatch",
    )
    for index, item in enumerate(items):
        _require_contract(
            isinstance(item, dict)
            and frozenset(item) == {"decision", "item_id", "reason"}
            and item.get("item_id") == expected_ids[index]
            and item.get("decision") == "ABSTAIN"
            and item.get("reason")
            == "local_isolation_probe_no_capability_evaluation",
            "candidate response item binding mismatch",
        )
    candidate_payload = canonical_json_bytes(value) + b"\n"
    _require_contract(
        artifacts["candidate_response"] == _descriptor(candidate_payload),
        "candidate response artifact does not match embedded bytes",
    )
    return value


def _validate_historical_fixture(
    value: Any,
    *,
    request: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    _require_contract(
        isinstance(value, dict)
        and frozenset(value) == _FIXTURE_EVALUATION_FIELDS,
        "fixture evaluation fields mismatch",
    )
    _require_contract(
        value.get("schema_version") == FIXTURE_EVALUATION_SCHEMA
        and value.get("local_fixture_only") is True
        and value.get("candidate_response_contract_passed") is True
        and value.get("fixture_gold_item_id_alignment_passed") is True
        and value.get("fixture_gold_used_for_capability_scoring") is False
        and value.get("run_id") == request["run_id"]
        and value.get("nonce") == request["nonce"]
        and value.get("request_sha256") == artifacts["request"]["sha256"]
        and value.get("network_probe_sha256")
        == artifacts["network_probe"]["sha256"]
        and value.get("candidate_response_sha256")
        == artifacts["candidate_response"]["sha256"]
        and value.get("fixture_gold_digest_sha256")
        == artifacts["gold"]["sha256"]
        and _strict_literal_equal(
            value.get("runtime"),
            {"gid": EVALUATOR_UID, "uid": EVALUATOR_UID},
        )
        and _strict_literal_equal(
            value.get("claims"),
            FIXTURE_FALSE_CLAIMS,
        ),
        "fixture evaluation historical binding mismatch",
    )
    _validate_probe_map(
        value.get("probes"),
        name="evaluator",
        expected_ids=EXPECTED_EVALUATOR_PROBE_IDS,
    )
    signature = value.get("signature")
    _require_contract(
        isinstance(signature, dict)
        and frozenset(signature) == _LOCAL_SIGNATURE_FIELDS
        and signature.get("scheme") == LOCAL_SIGNATURE_SCHEME
        and signature.get("key_id")
        == (
            "local-fixture:"
            + artifacts["local_fixture_key"]["sha256"][:24]
        )
        and isinstance(signature.get("payload_sha256"), str)
        and _SHA256_RE.fullmatch(signature["payload_sha256"]) is not None
        and isinstance(signature.get("signature_hex"), str)
        and _SHA256_RE.fullmatch(signature["signature_hex"]) is not None,
        "fixture signature envelope invalid",
    )
    unsigned = json.loads(canonical_json_bytes(value))
    unsigned.pop("signature")
    _require_contract(
        signature["payload_sha256"]
        == _sha256(canonical_json_bytes(unsigned)),
        "fixture signature payload binding mismatch",
    )
    fixture_payload = canonical_json_bytes(value) + b"\n"
    _require_contract(
        artifacts["fixture_evaluation"] == _descriptor(fixture_payload),
        "fixture evaluation artifact does not match embedded bytes",
    )
    return value


def _validate_network_control(value: Any) -> dict[str, Any]:
    expected_fields = {
        "endpoint_disclosed",
        "internal_network",
        "liveness_check_count",
        "liveness_checks",
        "positive_control_reachable",
        "same_sentinel_bound_to_isolated_runs",
        "sentinel_instance_count",
    }
    _require_contract(
        isinstance(value, dict) and frozenset(value) == expected_fields,
        "network control fields mismatch",
    )
    checks = value.get("liveness_checks")
    _require_contract(
        isinstance(checks, list)
        and len(checks) == len(NETWORK_LIVENESS_CHECKPOINTS),
        "network liveness check inventory mismatch",
    )
    for index, checkpoint in enumerate(NETWORK_LIVENESS_CHECKPOINTS):
        row = checks[index]
        _require_contract(
            isinstance(row, dict)
            and frozenset(row) == {"checkpoint", "reachable"}
            and row.get("checkpoint") == checkpoint
            and row.get("reachable") is True,
            "network liveness check binding mismatch",
        )
    _require_contract(
        value.get("endpoint_disclosed") is False
        and value.get("internal_network") is True
        and type(value.get("liveness_check_count")) is int
        and value.get("liveness_check_count") == len(checks)
        and value.get("positive_control_reachable") is True
        and value.get("same_sentinel_bound_to_isolated_runs") is True
        and type(value.get("sentinel_instance_count")) is int
        and value.get("sentinel_instance_count") == 1,
        "network positive-control evidence invalid",
    )
    return value


def _derive_historical_gates(
    *,
    source: Mapping[str, Any],
    docker: Mapping[str, Any],
    candidate_response: Mapping[str, Any],
    fixture_evaluation: Mapping[str, Any],
    network_control: Mapping[str, Any],
) -> dict[str, bool]:
    candidate_destinations = {
        row["destination"]
        for row in docker["containers"]["candidate"]["inspect"]["mounts"]
    }
    gates = {
        "candidate_breach_probes_passed": all(
            row["passed"] is True
            for row in candidate_response["probes"].values()
        ),
        "candidate_inspect_policy_passed": True,
        "candidate_request_contract_passed": True,
        "candidate_response_contract_passed": True,
        "evaluator_breach_probes_passed": all(
            row["passed"] is True
            for row in fixture_evaluation["probes"].values()
        ),
        "evaluator_inspect_policy_passed": True,
        "local_fixture_signature_structure_bound": True,
        "no_candidate_gold_key_or_docker_socket_mounts": not (
            candidate_destinations & PROHIBITED_CANDIDATE_DESTINATIONS
        ),
        "runner_owned_network_positive_control_passed": (
            network_control["positive_control_reachable"] is True
            and network_control["same_sentinel_bound_to_isolated_runs"]
            is True
            and network_control["liveness_check_count"]
            == len(NETWORK_LIVENESS_CHECKPOINTS)
        ),
        "separate_build_contexts_passed": (
            source["candidate_context"]["content_sha256"]
            != source["evaluator_context"]["content_sha256"]
            and docker["images"]["candidate"]["id"]
            != docker["images"]["evaluator"]["id"]
        ),
    }
    gates["same_host_docker_isolation_gate_passed"] = all(gates.values())
    return gates


def _build_manifest(
    *,
    run_id: str,
    nonce: str,
    source: Mapping[str, Any],
    docker: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    candidate_request: Mapping[str, Any],
    candidate_response: Mapping[str, Any],
    fixture_evaluation: Mapping[str, Any],
    network_control: Mapping[str, Any],
) -> dict[str, Any]:
    gates = _derive_historical_gates(
        source=source,
        docker=docker,
        candidate_response=candidate_response,
        fixture_evaluation=fixture_evaluation,
        network_control=network_control,
    )
    manifest: dict[str, Any] = {
        "artifacts": dict(artifacts),
        "candidate_request": dict(candidate_request),
        "candidate_response": dict(candidate_response),
        "claims": _build_claims(),
        "docker": dict(docker),
        "evidence_kind": EVIDENCE_KIND,
        "fixture_evaluation": dict(fixture_evaluation),
        "gates": gates,
        "limitations": list(LIMITATIONS),
        "network_control": dict(network_control),
        "nonce": nonce,
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "scope": dict(NON_CLAIM_SCOPE),
        "source": dict(source),
    }
    manifest["manifest_checksum_sha256"] = _manifest_checksum(manifest)
    return manifest


def validate_manifest(manifest: Any) -> list[str]:
    expected_fields = {
        "artifacts",
        "candidate_request",
        "candidate_response",
        "claims",
        "docker",
        "evidence_kind",
        "fixture_evaluation",
        "gates",
        "limitations",
        "manifest_checksum_sha256",
        "network_control",
        "nonce",
        "run_id",
        "schema_version",
        "scope",
        "source",
    }
    try:
        _require_contract(
            isinstance(manifest, dict)
            and frozenset(manifest) == expected_fields,
            "manifest fields mismatch",
        )
        _require_contract(
            manifest.get("schema_version") == SCHEMA_VERSION
            and manifest.get("evidence_kind") == EVIDENCE_KIND
            and _strict_literal_equal(
                manifest.get("limitations"),
                list(LIMITATIONS),
            )
            and _strict_literal_equal(
                manifest.get("claims"),
                _build_claims(),
            )
            and _strict_literal_equal(
                manifest.get("scope"),
                NON_CLAIM_SCOPE,
            ),
            "manifest scope or schema mismatch",
        )
        run_id = manifest.get("run_id")
        nonce = manifest.get("nonce")
        _require_contract(
            isinstance(run_id, str)
            and _ID_RE.fullmatch(run_id) is not None
            and isinstance(nonce, str)
            and _NONCE_RE.fullmatch(nonce) is not None,
            "manifest run binding invalid",
        )
        request = validate_candidate_request(
            manifest["candidate_request"]
        )
        _require_contract(
            request["run_id"] == run_id and request["nonce"] == nonce,
            "candidate request does not bind manifest run",
        )
        artifacts = _validate_artifacts(manifest["artifacts"])
        request_payload = canonical_json_bytes(request) + b"\n"
        _require_contract(
            artifacts["request"] == _descriptor(request_payload),
            "request artifact does not match embedded canonical request",
        )
        source = _validate_source(manifest["source"])
        docker = _validate_docker(
            manifest["docker"],
            source=source,
            artifacts=artifacts,
        )
        candidate = _validate_historical_candidate(
            manifest["candidate_response"],
            request=request,
            artifacts=artifacts,
        )
        fixture = _validate_historical_fixture(
            manifest["fixture_evaluation"],
            request=request,
            artifacts=artifacts,
        )
        network_control = _validate_network_control(
            manifest["network_control"]
        )
        expected_gates = _derive_historical_gates(
            source=source,
            docker=docker,
            candidate_response=candidate,
            fixture_evaluation=fixture,
            network_control=network_control,
        )
        _require_contract(
            manifest.get("gates") == expected_gates
            and all(
                type(value) is bool
                for value in manifest["gates"].values()
            )
            and expected_gates[
                "same_host_docker_isolation_gate_passed"
            ]
            is True,
            "manifest gates do not exactly rederive",
        )
        checksum = manifest.get("manifest_checksum_sha256")
        _require_contract(
            isinstance(checksum, str)
            and _SHA256_RE.fullmatch(checksum) is not None
            and checksum == _manifest_checksum(manifest),
            "manifest checksum mismatch",
        )
    except (
        KeyError,
        LocalIsolationError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        return [str(exc) or type(exc).__name__]
    return []


def write_manifest_exclusive(path: Path, manifest: Mapping[str, Any]) -> None:
    findings = validate_manifest(manifest)
    if findings:
        raise LocalIsolationError("; ".join(findings))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(manifest) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise LocalIsolationError(
            "refusing to overwrite existing local isolation manifest"
        ) from exc


def verify_manifest_file(path: Path) -> dict[str, Any]:
    value, payload = _read_canonical_json(path)
    findings = validate_manifest(value)
    return {
        "canonical_bytes": (
            payload == canonical_json_bytes(value) + b"\n"
        ),
        "findings": findings,
        "valid": not findings,
    }


def run_probe(
    *,
    run_id: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    runner_descriptor = _descriptor(Path(__file__).read_bytes())
    candidate_scope = _source_scope(
        CANDIDATE_CONTEXT,
        expected_files=CANDIDATE_CONTEXT_FILES,
    )
    evaluator_scope = _source_scope(
        EVALUATOR_CONTEXT,
        expected_files=EVALUATOR_CONTEXT_FILES,
    )
    docker_meta = docker_environment()
    fixture_request, _ = _read_canonical_json(
        REQUEST_FIXTURE
    )
    _, stage_payload = _read_canonical_json(STAGE_FIXTURE)
    _, gold_payload = _read_canonical_json(GOLD_FIXTURE)
    request = validate_candidate_request(fixture_request)
    actual_run_id = run_id or (
        "science-e4-local-" + uuid.uuid4().hex
    )
    actual_nonce = nonce or (
        "local:" + secrets.token_hex(24)
    )
    request["run_id"] = actual_run_id
    request["nonce"] = actual_nonce
    request = validate_candidate_request(request)
    request_payload = canonical_json_bytes(request) + b"\n"
    candidate_image_tag = build_image(
        role="candidate",
        context=CANDIDATE_CONTEXT,
        source_scope=candidate_scope,
    )
    _assert_source_snapshot_unchanged(
        candidate_scope=candidate_scope,
        evaluator_scope=evaluator_scope,
        runner_descriptor=runner_descriptor,
    )
    evaluator_image_tag = build_image(
        role="evaluator",
        context=EVALUATOR_CONTEXT,
        source_scope=evaluator_scope,
    )
    _assert_source_snapshot_unchanged(
        candidate_scope=candidate_scope,
        evaluator_scope=evaluator_scope,
        runner_descriptor=runner_descriptor,
    )
    candidate_image = image_evidence(
        candidate_image_tag,
        role_label="candidate",
        context_sha256=candidate_scope["content_sha256"],
    )
    evaluator_image = image_evidence(
        evaluator_image_tag,
        role_label="local-fixture-evaluator",
        context_sha256=evaluator_scope["content_sha256"],
    )
    if candidate_image["id"] == evaluator_image["id"]:
        raise LocalIsolationError("candidate and evaluator images coincide")

    candidate_name = "atanor-science-e4-candidate-" + uuid.uuid4().hex
    evaluator_name = "atanor-science-e4-evaluator-" + uuid.uuid4().hex
    sentinel_name = "atanor-science-e4-sentinel-" + uuid.uuid4().hex
    network_name = "atanor-science-e4-network-" + uuid.uuid4().hex
    created: list[str] = []
    networks: list[str] = []
    with tempfile.TemporaryDirectory(
        prefix="atanor-science-e4-local-"
    ) as temporary:
        runtime_dir = Path(temporary)
        if "," in str(runtime_dir.resolve()):
            raise LocalIsolationError(
                "temporary Docker mount root contains unsupported comma"
            )
        request_path = runtime_dir / "request.json"
        stage_path = runtime_dir / "stage.json"
        gold_path = runtime_dir / "gold.json"
        response_path = runtime_dir / "candidate_response.json"
        network_probe_path = runtime_dir / "network_probe.json"
        key_path = runtime_dir / "local_fixture_signing_key"
        _write_temp(request_path, request_payload)
        _write_temp(stage_path, stage_payload)
        _write_temp(gold_path, gold_payload)
        local_key = secrets.token_bytes(32)
        _write_temp(key_path, local_key)
        try:
            key_path.chmod(0o600)
        except OSError:
            pass

        try:
            _create_internal_network(
                network_name,
                created=networks,
            )
            (
                network_probe,
                network_probe_payload,
                sentinel_id,
                initial_liveness,
            ) = _run_network_positive_control(
                image=candidate_image_tag,
                network=network_name,
                sentinel_name=sentinel_name,
                created=created,
            )
            liveness_checks = [initial_liveness]
            _write_temp(network_probe_path, network_probe_payload)
            artifact_descriptors: dict[str, dict[str, Any]] = {
                "gold": _descriptor(gold_payload),
                "local_fixture_key": _descriptor(local_key),
                "network_probe": _descriptor(network_probe_payload),
                "request": _descriptor(request_payload),
                "stage": _descriptor(stage_payload),
            }
            candidate_mounts = {
                "/input/network_probe.json": network_probe_path,
                "/input/request.json": request_path,
                "/input/stage.json": stage_path,
            }
            candidate_id = _create_tracked_container(
                arguments=container_create_arguments(
                    name=candidate_name,
                    image=candidate_image_tag,
                    uid=CANDIDATE_UID,
                    mounts=candidate_mounts,
                ),
                name=candidate_name,
                created=created,
            )
            candidate_pre = _container_inspect(candidate_name)
            _require_container_id(
                candidate_pre,
                expected_id=candidate_id,
            )
            candidate_inspect = normalize_container_inspect(
                role="candidate",
                inspect_row=candidate_pre,
                image=candidate_image,
                expected_uid=CANDIDATE_UID,
                expected_mounts=candidate_mounts,
                artifact_descriptors=artifact_descriptors,
            )
            candidate_output = _start_attached(candidate_name)
            candidate_post = _post_run_state(
                _container_inspect(candidate_name)
            )
            candidate_value = _decode_canonical_json(candidate_output)
            candidate_response = validate_candidate_response(
                candidate_value,
                request=request,
                request_payload=request_payload,
                stage_payload=stage_payload,
                network_probe_payload=network_probe_payload,
            )
            response_payload = (
                canonical_json_bytes(candidate_response) + b"\n"
            )
            _write_temp(response_path, response_payload)
            artifact_descriptors["candidate_response"] = _descriptor(
                response_payload
            )
            liveness_checks.append(
                _check_network_sentinel_liveness(
                    image=candidate_image_tag,
                    network=network_name,
                    sentinel_name=sentinel_name,
                    sentinel_id=sentinel_id,
                    network_probe=network_probe,
                    checkpoint=NETWORK_LIVENESS_CHECKPOINTS[1],
                    created=created,
                )
            )

            evaluator_mounts = {
                "/fixture/gold.json": gold_path,
                "/input/candidate_response.json": response_path,
                "/input/network_probe.json": network_probe_path,
                "/input/request.json": request_path,
                "/run/secrets/local_fixture_signing_key": key_path,
            }
            evaluator_id = _create_tracked_container(
                arguments=container_create_arguments(
                    name=evaluator_name,
                    image=evaluator_image_tag,
                    uid=EVALUATOR_UID,
                    mounts=evaluator_mounts,
                ),
                name=evaluator_name,
                created=created,
            )
            evaluator_pre = _container_inspect(evaluator_name)
            _require_container_id(
                evaluator_pre,
                expected_id=evaluator_id,
            )
            evaluator_inspect = normalize_container_inspect(
                role="evaluator",
                inspect_row=evaluator_pre,
                image=evaluator_image,
                expected_uid=EVALUATOR_UID,
                expected_mounts=evaluator_mounts,
                artifact_descriptors=artifact_descriptors,
            )
            evaluator_output = _start_attached(evaluator_name)
            evaluator_post = _post_run_state(
                _container_inspect(evaluator_name)
            )
            evaluator_value = _decode_canonical_json(evaluator_output)
            fixture_evaluation = verify_local_fixture_evaluation(
                evaluator_value,
                payload=evaluator_output,
                key=local_key,
                request=request,
                request_payload=request_payload,
                response_payload=response_payload,
                gold_payload=gold_payload,
                network_probe_payload=network_probe_payload,
            )
            artifact_descriptors["fixture_evaluation"] = _descriptor(
                evaluator_output
            )
            liveness_checks.append(
                _check_network_sentinel_liveness(
                    image=candidate_image_tag,
                    network=network_name,
                    sentinel_name=sentinel_name,
                    sentinel_id=sentinel_id,
                    network_probe=network_probe,
                    checkpoint=NETWORK_LIVENESS_CHECKPOINTS[2],
                    created=created,
                )
            )
            network_control = {
                "endpoint_disclosed": False,
                "internal_network": True,
                "liveness_check_count": len(liveness_checks),
                "liveness_checks": liveness_checks,
                "positive_control_reachable": all(
                    row["reachable"] is True
                    for row in liveness_checks
                ),
                "same_sentinel_bound_to_isolated_runs": True,
                "sentinel_instance_count": 1,
            }
        finally:
            cleanup_failures: list[str] = []
            for name in reversed(created):
                outcome = _remove_container(name)
                if outcome != "removed":
                    cleanup_failures.append(
                        f"container:{name}:{outcome}"
                    )
            for name in reversed(networks):
                outcome = _remove_network(name)
                if outcome != "removed":
                    cleanup_failures.append(f"network:{name}:{outcome}")
            if cleanup_failures:
                raise LocalIsolationError(
                    "Docker cleanup failed or could not be verified: "
                    + ", ".join(cleanup_failures)
                )

    source = {
        "candidate_context": candidate_scope,
        "evaluator_context": evaluator_scope,
        "runner": runner_descriptor,
    }
    artifacts = {
        name: descriptor
        for name, descriptor in sorted(artifact_descriptors.items())
        if name != "local_fixture_key"
    }
    artifacts["local_fixture_key"] = {
        "bytes": artifact_descriptors["local_fixture_key"]["bytes"],
        "ephemeral": True,
        "material_recorded": False,
        "sha256": artifact_descriptors["local_fixture_key"]["sha256"],
    }
    docker = {
        "containers": {
            "candidate": {
                "inspect": candidate_inspect,
                "post_run": candidate_post,
            },
            "evaluator": {
                "inspect": evaluator_inspect,
                "post_run": evaluator_post,
            },
        },
        "environment": docker_meta,
        "images": {
            "candidate": candidate_image,
            "evaluator": evaluator_image,
        },
    }
    manifest = _build_manifest(
        run_id=actual_run_id,
        nonce=actual_nonce,
        source=source,
        docker=docker,
        artifacts=artifacts,
        candidate_request=request,
        candidate_response=candidate_response,
        fixture_evaluation=fixture_evaluation,
        network_control=network_control,
    )
    findings = validate_manifest(manifest)
    if findings:
        raise LocalIsolationError("; ".join(findings))
    _assert_source_snapshot_unchanged(
        candidate_scope=candidate_scope,
        evaluator_scope=evaluator_scope,
        runner_descriptor=runner_descriptor,
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run or verify the same-host Docker science-E4 isolation probe"
        )
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--output",
        type=Path,
        help="write a new canonical manifest exclusively",
    )
    actions.add_argument(
        "--verify",
        type=Path,
        help="verify canonical structure and honest local-only claims",
    )
    args = parser.parse_args(argv)
    try:
        if args.verify is not None:
            report = verify_manifest_file(args.verify)
            print(canonical_json_bytes(report).decode("utf-8"))
            return 0 if report["valid"] else 1
        manifest = run_probe()
        if args.output is not None:
            write_manifest_exclusive(args.output, manifest)
        print(canonical_json_bytes(manifest).decode("utf-8"))
        return 0
    except Exception as exc:
        print(
            f"science-e4 local isolation failed closed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
