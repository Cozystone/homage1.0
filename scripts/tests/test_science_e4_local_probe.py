from __future__ import annotations

from copy import deepcopy
import errno
import hashlib
import hmac
import json
from pathlib import Path
import subprocess

import pytest

from deploy.science_e4_local.candidate import candidate_probe
from deploy.science_e4_local.evaluator import fixture_evaluator
from deploy.science_e4_local import runner


def _canonical_fixture(path: Path) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    assert payload == runner.canonical_json_bytes(value) + b"\n"
    return value, payload


def _probe_map(ids: frozenset[str]) -> dict[str, dict]:
    return {
        name: {"error_type": None, "passed": True}
        for name in sorted(ids)
    }


def _request_and_payload() -> tuple[dict, bytes]:
    value, _ = _canonical_fixture(runner.REQUEST_FIXTURE)
    value["run_id"] = "science-e4-local-unit"
    value["nonce"] = "local:unit-test-nonce-0001"
    value = runner.validate_candidate_request(value)
    return value, runner.canonical_json_bytes(value) + b"\n"


def _network_probe_and_payload() -> tuple[dict, bytes]:
    value = {
        "host": "172.30.0.2",
        "port": runner.NETWORK_SENTINEL_PORT,
        "schema_version": runner.NETWORK_PROBE_SCHEMA,
    }
    return value, runner.canonical_json_bytes(value) + b"\n"


def _candidate_response(
    request: dict,
    request_payload: bytes,
    stage_payload: bytes,
    network_probe_payload: bytes,
) -> tuple[dict, bytes]:
    value = {
        "all_probes_passed": True,
        "items": [
            {
                "decision": "ABSTAIN",
                "item_id": item["item_id"],
                "reason": (
                    "local_isolation_probe_no_capability_evaluation"
                ),
            }
            for item in request["items"]
        ],
        "nonce": request["nonce"],
        "network_probe_sha256": hashlib.sha256(
            network_probe_payload
        ).hexdigest(),
        "probes": _probe_map(runner.EXPECTED_CANDIDATE_PROBE_IDS),
        "request_sha256": hashlib.sha256(request_payload).hexdigest(),
        "run_id": request["run_id"],
        "runtime": {
            "gid": runner.CANDIDATE_UID,
            "uid": runner.CANDIDATE_UID,
        },
        "schema_version": runner.CANDIDATE_RESPONSE_SCHEMA,
        "scope": {
            "capability_evaluation_performed": False,
            "local_isolation_probe_only": True,
        },
        "stage_sha256": hashlib.sha256(stage_payload).hexdigest(),
    }
    payload = runner.canonical_json_bytes(value) + b"\n"
    return value, payload


def _fixture_evaluation(
    *,
    request: dict,
    request_payload: bytes,
    response_payload: bytes,
    gold_payload: bytes,
    network_probe_payload: bytes,
    key: bytes,
) -> tuple[dict, bytes]:
    unsigned = {
        "candidate_response_contract_passed": True,
        "candidate_response_sha256": hashlib.sha256(
            response_payload
        ).hexdigest(),
        "claims": dict(runner.FIXTURE_FALSE_CLAIMS),
        "fixture_gold_digest_sha256": hashlib.sha256(
            gold_payload
        ).hexdigest(),
        "fixture_gold_item_id_alignment_passed": True,
        "fixture_gold_used_for_capability_scoring": False,
        "local_fixture_only": True,
        "nonce": request["nonce"],
        "network_probe_sha256": hashlib.sha256(
            network_probe_payload
        ).hexdigest(),
        "probes": _probe_map(runner.EXPECTED_EVALUATOR_PROBE_IDS),
        "request_sha256": hashlib.sha256(request_payload).hexdigest(),
        "run_id": request["run_id"],
        "runtime": {
            "gid": runner.EVALUATOR_UID,
            "uid": runner.EVALUATOR_UID,
        },
        "schema_version": runner.FIXTURE_EVALUATION_SCHEMA,
    }
    signed_payload = runner.canonical_json_bytes(unsigned)
    value = deepcopy(unsigned)
    value["signature"] = {
        "key_id": (
            "local-fixture:"
            + hashlib.sha256(key).hexdigest()[:24]
        ),
        "payload_sha256": hashlib.sha256(signed_payload).hexdigest(),
        "scheme": runner.LOCAL_SIGNATURE_SCHEME,
        "signature_hex": hmac.new(
            key,
            signed_payload,
            hashlib.sha256,
        ).hexdigest(),
    }
    return value, runner.canonical_json_bytes(value) + b"\n"


def _image(
    role: str,
    digest_char: str,
    *,
    source_context_sha256: str | None = None,
) -> dict:
    return {
        "architecture": "amd64",
        "id": "sha256:" + digest_char * 64,
        "os": "linux",
        "repo_digests": [],
        "rootfs_layers": ["sha256:" + digest_char * 64],
        "source_context_sha256": (
            source_context_sha256 or digest_char * 64
        ),
    }


def _synthetic_source_context(
    paths: tuple[str, ...],
    digest_char: str,
) -> dict:
    files = [
        {
            "bytes": index + 1,
            "path": path,
            "sha256": digest_char * 64,
        }
        for index, path in enumerate(sorted(paths))
    ]
    return {
        "content_sha256": hashlib.sha256(
            runner.canonical_json_bytes(files)
        ).hexdigest(),
        "files": files,
    }


def _network_control() -> dict:
    checks = [
        {"checkpoint": checkpoint, "reachable": True}
        for checkpoint in runner.NETWORK_LIVENESS_CHECKPOINTS
    ]
    return {
        "endpoint_disclosed": False,
        "internal_network": True,
        "liveness_check_count": len(checks),
        "liveness_checks": checks,
        "positive_control_reachable": True,
        "same_sentinel_bound_to_isolated_runs": True,
        "sentinel_instance_count": 1,
    }


def _raw_inspect(
    *,
    role: str,
    image: dict,
    uid: int,
    mounts: dict[str, Path],
) -> dict:
    role_label = (
        "candidate" if role == "candidate"
        else "local-fixture-evaluator"
    )
    return {
        "Config": {
            "ExposedPorts": None,
            "Labels": {
                "org.atanor.science-e4-local.authority": "none",
                "org.atanor.science-e4-local.context-sha256": (
                    image["source_context_sha256"]
                ),
                "org.atanor.science-e4-local.role": role_label,
            },
            "User": f"{uid}:{uid}",
        },
        "HostConfig": {
            "CapDrop": ["ALL"],
            "DeviceRequests": None,
            "Devices": [],
            "IpcMode": "private",
            "Memory": runner.MEMORY_BYTES,
            "MemorySwap": runner.MEMORY_BYTES,
            "NanoCpus": runner.NANO_CPUS,
            "NetworkMode": "none",
            "PidMode": "",
            "PidsLimit": runner.PIDS_LIMIT,
            "PortBindings": {},
            "Privileged": False,
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {
                "/tmp": (
                    "rw,noexec,nosuid,nodev,"
                    f"size={runner.TMPFS_BYTES}"
                )
            },
            "Ulimits": [
                {
                    "Hard": runner.NOFILE_LIMIT,
                    "Name": "nofile",
                    "Soft": runner.NOFILE_LIMIT,
                }
            ],
        },
        "Image": image["id"],
        "Mounts": [
            {
                "Destination": destination,
                "RW": False,
                "Source": str(source.resolve()),
                "Type": "bind",
            }
            for destination, source in sorted(mounts.items())
        ],
        "NetworkSettings": {"Networks": {"none": {}}},
        "State": {
            "Dead": False,
            "Error": "",
            "ExitCode": 0,
            "OOMKilled": False,
            "Running": False,
        },
    }


def _artifact_descriptors(
    sources: dict[str, Path],
) -> dict[str, dict]:
    return {
        name: {
            "bytes": len(path.read_bytes()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for name, path in sources.items()
    }


def _normalized_containers(
    tmp_path: Path,
) -> tuple[dict, dict, dict[str, dict]]:
    sources: dict[str, Path] = {}
    for name in (
        "request",
        "stage",
        "gold",
        "candidate_response",
        "local_fixture_key",
        "network_probe",
    ):
        path = tmp_path / name
        path.write_bytes((name + "\n").encode("utf-8"))
        sources[name] = path
    descriptors = _artifact_descriptors(sources)
    candidate_image = _image("candidate", "a")
    evaluator_image = _image("evaluator", "b")
    candidate_mounts = {
        "/input/network_probe.json": sources["network_probe"],
        "/input/request.json": sources["request"],
        "/input/stage.json": sources["stage"],
    }
    evaluator_mounts = {
        "/fixture/gold.json": sources["gold"],
        "/input/candidate_response.json": sources[
            "candidate_response"
        ],
        "/input/network_probe.json": sources["network_probe"],
        "/input/request.json": sources["request"],
        "/run/secrets/local_fixture_signing_key": sources[
            "local_fixture_key"
        ],
    }
    candidate = runner.normalize_container_inspect(
        role="candidate",
        inspect_row=_raw_inspect(
            role="candidate",
            image=candidate_image,
            uid=runner.CANDIDATE_UID,
            mounts=candidate_mounts,
        ),
        image=candidate_image,
        expected_uid=runner.CANDIDATE_UID,
        expected_mounts=candidate_mounts,
        artifact_descriptors=descriptors,
    )
    evaluator = runner.normalize_container_inspect(
        role="evaluator",
        inspect_row=_raw_inspect(
            role="evaluator",
            image=evaluator_image,
            uid=runner.EVALUATOR_UID,
            mounts=evaluator_mounts,
        ),
        image=evaluator_image,
        expected_uid=runner.EVALUATOR_UID,
        expected_mounts=evaluator_mounts,
        artifact_descriptors=descriptors,
    )
    return candidate, evaluator, descriptors


def _manifest(tmp_path: Path) -> dict:
    request, request_payload = _request_and_payload()
    _, stage_payload = _canonical_fixture(runner.STAGE_FIXTURE)
    _, gold_payload = _canonical_fixture(runner.GOLD_FIXTURE)
    _, network_probe_payload = _network_probe_and_payload()
    response, response_payload = _candidate_response(
        request,
        request_payload,
        stage_payload,
        network_probe_payload,
    )
    key = b"k" * 32
    evaluation, evaluation_payload = _fixture_evaluation(
        request=request,
        request_payload=request_payload,
        response_payload=response_payload,
        gold_payload=gold_payload,
        network_probe_payload=network_probe_payload,
        key=key,
    )
    candidate, evaluator, _ = _normalized_containers(tmp_path)
    candidate_source = _synthetic_source_context(
        runner.CANDIDATE_CONTEXT_FILES,
        "a",
    )
    evaluator_source = _synthetic_source_context(
        runner.EVALUATOR_CONTEXT_FILES,
        "b",
    )
    source = {
        "candidate_context": candidate_source,
        "evaluator_context": evaluator_source,
        "runner": {
            "bytes": 1,
            "sha256": "c" * 64,
        },
    }
    artifacts = {
        "candidate_response": {
            "bytes": len(response_payload),
            "sha256": hashlib.sha256(response_payload).hexdigest(),
        },
        "fixture_evaluation": {
            "bytes": len(evaluation_payload),
            "sha256": hashlib.sha256(evaluation_payload).hexdigest(),
        },
        "gold": {
            "bytes": len(gold_payload),
            "sha256": hashlib.sha256(gold_payload).hexdigest(),
        },
        "local_fixture_key": {
            "bytes": 32,
            "ephemeral": True,
            "material_recorded": False,
            "sha256": hashlib.sha256(key).hexdigest(),
        },
        "network_probe": {
            "bytes": len(network_probe_payload),
            "sha256": hashlib.sha256(
                network_probe_payload
            ).hexdigest(),
        },
        "request": {
            "bytes": len(request_payload),
            "sha256": hashlib.sha256(request_payload).hexdigest(),
        },
        "stage": {
            "bytes": len(stage_payload),
            "sha256": hashlib.sha256(stage_payload).hexdigest(),
        },
    }
    for inspect_value, mount_contract in (
        (candidate, runner.CANDIDATE_MOUNTS),
        (evaluator, runner.EVALUATOR_MOUNTS),
    ):
        for mount in inspect_value["mounts"]:
            artifact_name = mount_contract[mount["destination"]]
            mount["source_bytes"] = artifacts[artifact_name]["bytes"]
            mount["source_sha256"] = artifacts[artifact_name]["sha256"]
    docker = {
        "containers": {
            "candidate": {
                "inspect": candidate,
                "post_run": {
                    "dead": False,
                    "error_present": False,
                    "exit_code": 0,
                    "oom_killed": False,
                    "running": False,
                },
            },
            "evaluator": {
                "inspect": evaluator,
                "post_run": {
                    "dead": False,
                    "error_present": False,
                    "exit_code": 0,
                    "oom_killed": False,
                    "running": False,
                },
            },
        },
        "environment": {
            "architecture": "x86_64",
            "cgroup_driver": "cgroupfs",
            "cgroup_version": "2",
            "client_version": "unit-client",
            "context": "unit",
            "kernel_version": "unit-kernel",
            "operating_system": "unit-linux",
            "os_type": "linux",
            "security_options": [
                "name=cgroupns",
                "name=seccomp,profile=builtin",
            ],
            "server_version": "unit-server",
            "storage_driver": "overlay2",
        },
        "images": {
            "candidate": _image(
                "candidate",
                "a",
                source_context_sha256=candidate_source[
                    "content_sha256"
                ],
            ),
            "evaluator": _image(
                "evaluator",
                "b",
                source_context_sha256=evaluator_source[
                    "content_sha256"
                ],
            ),
        },
    }
    return runner._build_manifest(
        run_id=request["run_id"],
        nonce=request["nonce"],
        source=source,
        docker=docker,
        artifacts=artifacts,
        candidate_request=request,
        candidate_response=response,
        fixture_evaluation=evaluation,
        network_control=_network_control(),
    )


def _rebind_fixture_artifact(manifest: dict) -> None:
    fixture = manifest["fixture_evaluation"]
    unsigned = deepcopy(fixture)
    unsigned.pop("signature")
    fixture["signature"]["payload_sha256"] = hashlib.sha256(
        runner.canonical_json_bytes(unsigned)
    ).hexdigest()
    payload = runner.canonical_json_bytes(fixture) + b"\n"
    manifest["artifacts"]["fixture_evaluation"] = {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def test_build_contexts_are_separate_minimal_and_digest_pinned() -> None:
    candidate_scope = runner._source_scope(
        runner.CANDIDATE_CONTEXT,
        expected_files=runner.CANDIDATE_CONTEXT_FILES,
    )
    evaluator_scope = runner._source_scope(
        runner.EVALUATOR_CONTEXT,
        expected_files=runner.EVALUATOR_CONTEXT_FILES,
    )
    assert candidate_scope["content_sha256"] != (
        evaluator_scope["content_sha256"]
    )
    assert {
        row["path"] for row in candidate_scope["files"]
    } == set(runner.CANDIDATE_CONTEXT_FILES)
    assert {
        row["path"] for row in evaluator_scope["files"]
    } == set(runner.EVALUATOR_CONTEXT_FILES)

    candidate_dockerfile = (
        runner.CANDIDATE_CONTEXT / "Dockerfile"
    ).read_text(encoding="utf-8")
    evaluator_dockerfile = (
        runner.EVALUATOR_CONTEXT / "Dockerfile"
    ).read_text(encoding="utf-8")
    for text, uid, copied in (
        (candidate_dockerfile, 10001, "candidate_probe.py"),
        (evaluator_dockerfile, 10002, "fixture_evaluator.py"),
    ):
        assert "python:3.11-slim@sha256:" in text
        assert f"USER {uid}:{uid}" in text
        assert f"COPY {copied} " in text
        assert "COPY . " not in text
        assert '"/usr/bin/env", "-i"' in text


@pytest.mark.parametrize(
    "field",
    [
        "Architecture",
        "Os",
        "Id",
        "Layers",
        "RepoDigests",
        "Config",
    ],
)
def test_image_evidence_rejects_missing_or_untyped_required_fields(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    context_digest = "c" * 64
    row = {
        "Architecture": "amd64",
        "Config": {
            "Labels": {
                "org.atanor.science-e4-local.authority": "none",
                "org.atanor.science-e4-local.context-sha256": (
                    context_digest
                ),
                "org.atanor.science-e4-local.role": "candidate",
            }
        },
        "Id": "sha256:" + "a" * 64,
        "Os": "linux",
        "RepoDigests": [],
        "RootFS": {"Layers": ["sha256:" + "b" * 64]},
    }
    if field == "Layers":
        row["RootFS"]["Layers"] = [None]
    elif field == "RepoDigests":
        row["RepoDigests"] = [None]
    else:
        row[field] = None
    monkeypatch.setattr(runner, "_docker_json", lambda args: [row])
    with pytest.raises(runner.LocalIsolationError):
        runner.image_evidence(
            "candidate:test",
            role_label="candidate",
            context_sha256=context_digest,
        )


@pytest.mark.parametrize(
    ("record", "field"),
    [
        ("info", "Architecture"),
        ("info", "Driver"),
        ("client", "Version"),
        ("server", "Version"),
        ("security", "SecurityOptions"),
    ],
)
def test_docker_environment_rejects_none_required_fields(
    monkeypatch: pytest.MonkeyPatch,
    record: str,
    field: str,
) -> None:
    version = {
        "Client": {"Version": "unit-client"},
        "Server": {"Version": "unit-server"},
    }
    info = {
        "Architecture": "x86_64",
        "CgroupDriver": "cgroupfs",
        "CgroupVersion": "2",
        "Driver": "overlayfs",
        "KernelVersion": "unit-kernel",
        "OperatingSystem": "unit-linux",
        "OSType": "linux",
        "SecurityOptions": [
            "name=cgroupns",
            "name=seccomp,profile=builtin",
        ],
    }
    if record == "info":
        info[field] = None
    elif record == "client":
        version["Client"][field] = None
    elif record == "server":
        version["Server"][field] = None
    else:
        info[field] = [None]
    monkeypatch.setattr(
        runner,
        "_run_docker",
        lambda args: subprocess.CompletedProcess(
            args=["docker", *args],
            returncode=0,
            stdout=b"unit-context\n",
            stderr=b"",
        ),
    )

    def fake_docker_json(args: list[str]) -> dict:
        return version if args[0] == "version" else info

    monkeypatch.setattr(runner, "_docker_json", fake_docker_json)
    with pytest.raises(runner.LocalIsolationError):
        runner.docker_environment()


def test_candidate_context_contains_no_gold_key_or_evaluator_file() -> None:
    relative = {
        path.relative_to(runner.CANDIDATE_CONTEXT).as_posix()
        for path in runner.CANDIDATE_CONTEXT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    assert relative == set(runner.CANDIDATE_CONTEXT_FILES)
    assert not any(
        token in path.casefold()
        for path in relative
        for token in ("gold", "key", "evaluator")
    )


def test_fixture_request_is_canonical_gold_free_and_strict() -> None:
    request, payload = _canonical_fixture(runner.REQUEST_FIXTURE)
    checked = runner.validate_candidate_request(request)
    assert payload == runner.canonical_json_bytes(checked) + b"\n"
    assert frozenset(checked) == {
        "schema_version",
        "run_id",
        "nonce",
        "items",
    }
    assert all(
        frozenset(item) == {"item_id", "stem", "choices"}
        for item in checked["items"]
    )
    serialized = payload.decode("utf-8").casefold()
    for forbidden in (
        '"answer"',
        '"answer_key"',
        '"evaluator"',
        '"gold"',
        '"label"',
        '"score"',
        '"target"',
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "field",
    [
        "answer",
        "answer_key",
        "evaluator",
        "gold",
        "label",
        "score",
        "target",
    ],
)
def test_candidate_request_rejects_forbidden_metadata(field: str) -> None:
    request, _ = _request_and_payload()
    tampered = deepcopy(request)
    tampered[field] = "forbidden"
    with pytest.raises(runner.LocalIsolationError):
        runner.validate_candidate_request(tampered)

    nested = deepcopy(request)
    nested["items"][0][field] = "forbidden"
    with pytest.raises(runner.LocalIsolationError):
        runner.validate_candidate_request(nested)


def test_container_create_policy_is_hardened_and_mount_exact(
    tmp_path: Path,
) -> None:
    network_probe = tmp_path / "network_probe.json"
    request = tmp_path / "request.json"
    stage = tmp_path / "stage.json"
    network_probe.write_bytes(b"network-probe")
    request.write_bytes(b"request")
    stage.write_bytes(b"stage")
    args = runner.container_create_arguments(
        name="candidate-test",
        image="candidate:test",
        uid=runner.CANDIDATE_UID,
        mounts={
            "/input/network_probe.json": network_probe,
            "/input/request.json": request,
            "/input/stage.json": stage,
        },
    )
    joined = "\n".join(args)
    for required in (
        "--network\nnone",
        "--read-only",
        "--user\n10001:10001",
        "--cap-drop\nALL",
        "--security-opt\nno-new-privileges:true",
        "--pids-limit\n64",
        f"--memory\n{runner.MEMORY_BYTES}",
        f"--memory-swap\n{runner.MEMORY_BYTES}",
        "--cpus\n1.0",
        "--ipc\nprivate",
    ):
        assert required in joined
    assert "--pid" not in args
    assert "readonly" in joined
    assert "/var/run/docker.sock" not in joined
    assert "/fixture/gold.json" not in joined
    assert "/run/secrets/local_fixture_signing_key" not in joined


def test_normalized_inspect_captures_exact_local_policy(
    tmp_path: Path,
) -> None:
    candidate, evaluator, _ = _normalized_containers(tmp_path)
    for record, user, destinations in (
        (
            candidate,
            "10001:10001",
            set(runner.CANDIDATE_MOUNTS),
        ),
        (
            evaluator,
            "10002:10002",
            set(runner.EVALUATOR_MOUNTS),
        ),
    ):
        assert record["user"] == user
        assert record["network_mode"] == "none"
        assert record["read_only_rootfs"] is True
        assert record["cap_drop"] == ["ALL"]
        assert record["no_new_privileges"] is True
        assert record["privileged"] is False
        assert record["pids_limit"] == 64
        assert record["memory_bytes"] == 256 * 1024 * 1024
        assert record["nano_cpus"] == 1_000_000_000
        assert {
            mount["destination"] for mount in record["mounts"]
        } == destinations
        assert all(
            mount["read_only"] is True
            and mount["source_path_recorded"] is False
            for mount in record["mounts"]
        )


@pytest.mark.parametrize(
    "raw_options",
    [
        "rw,noexec,nosuid,nodev,size=16777216,exec",
        "rw,noexec,nosuid,nodev,size=16777216,suid",
        "rw,noexec,nosuid,nodev,size=16777216,dev",
        "rw,noexec,nosuid,nodev,size=16777216,ro",
        "ro,noexec,nosuid,nodev,size=16777216",
        "rw,rw,noexec,nosuid,nodev,size=16777216",
        (
            "rw,noexec,nosuid,nodev,size=16777216,"
            "size=16777216"
        ),
        "rw,noexec,nosuid,nodev,size=16777215",
        "rw,noexec,nosuid,nodev,size=16m",
        "rw,noexec,nosuid,nodev,size=16777216,relatime",
        "noexec,rw,nosuid,nodev,size=16777216",
    ],
)
def test_tmpfs_raw_options_fail_closed(
    tmp_path: Path,
    raw_options: str,
) -> None:
    network_probe = tmp_path / "network_probe"
    request = tmp_path / "request"
    stage = tmp_path / "stage"
    for path in (network_probe, request, stage):
        path.write_bytes(path.name.encode("utf-8"))
    mounts = {
        "/input/network_probe.json": network_probe,
        "/input/request.json": request,
        "/input/stage.json": stage,
    }
    descriptors = _artifact_descriptors(
        {
            "network_probe": network_probe,
            "request": request,
            "stage": stage,
        }
    )
    image = _image("candidate", "a")
    inspect_value = _raw_inspect(
        role="candidate",
        image=image,
        uid=runner.CANDIDATE_UID,
        mounts=mounts,
    )
    inspect_value["HostConfig"]["Tmpfs"] = {"/tmp": raw_options}
    assert runner._tmpfs_policy_valid(
        inspect_value["HostConfig"]["Tmpfs"]
    ) is False
    with pytest.raises(runner.LocalIsolationError):
        runner.normalize_container_inspect(
            role="candidate",
            inspect_row=inspect_value,
            image=image,
            expected_uid=runner.CANDIDATE_UID,
            expected_mounts=mounts,
            artifact_descriptors=descriptors,
        )


def test_tmpfs_normalized_evidence_derives_from_exact_raw_options() -> None:
    raw = {
        "/tmp": (
            "rw,noexec,nosuid,nodev,"
            f"size={runner.TMPFS_BYTES}"
        )
    }
    assert runner._tmpfs_policy_valid(raw) is True
    assert runner._normalize_tmpfs_policy(raw) == {
        "destination": "/tmp",
        "noexec": True,
        "nodev": True,
        "nosuid": True,
        "size_bytes": runner.TMPFS_BYTES,
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("NetworkMode", "bridge"),
        ("ReadonlyRootfs", False),
        ("Privileged", True),
        ("CapDrop", []),
        ("SecurityOpt", []),
        (
            "SecurityOpt",
            [
                "no-new-privileges:true",
                "no-new-privileges:true",
            ],
        ),
        ("SecurityOpt", ["no-new-privileges:true:true"]),
        ("SecurityOpt", [1]),
        ("PidsLimit", 0),
        ("Memory", 0),
        ("NanoCpus", 0),
        ("PidsLimit", float(runner.PIDS_LIMIT)),
        ("Memory", float(runner.MEMORY_BYTES)),
        ("MemorySwap", float(runner.MEMORY_BYTES)),
        ("NanoCpus", float(runner.NANO_CPUS)),
    ],
)
def test_inspect_policy_tamper_fails_closed(
    tmp_path: Path,
    field: str,
    bad_value: object,
) -> None:
    network_probe = tmp_path / "network_probe"
    request = tmp_path / "request"
    stage = tmp_path / "stage"
    network_probe.write_bytes(b"network-probe")
    request.write_bytes(b"request")
    stage.write_bytes(b"stage")
    mounts = {
        "/input/network_probe.json": network_probe,
        "/input/request.json": request,
        "/input/stage.json": stage,
    }
    descriptors = _artifact_descriptors(
        {
            "network_probe": network_probe,
            "request": request,
            "stage": stage,
        }
    )
    image = _image("candidate", "a")
    inspect_value = _raw_inspect(
        role="candidate",
        image=image,
        uid=runner.CANDIDATE_UID,
        mounts=mounts,
    )
    inspect_value["HostConfig"][field] = bad_value
    with pytest.raises(runner.LocalIsolationError):
        runner.normalize_container_inspect(
            role="candidate",
            inspect_row=inspect_value,
            image=image,
            expected_uid=runner.CANDIDATE_UID,
            expected_mounts=mounts,
            artifact_descriptors=descriptors,
        )


@pytest.mark.parametrize("field", ["Hard", "Soft"])
def test_inspect_ulimit_rejects_float_coercion(
    tmp_path: Path,
    field: str,
) -> None:
    network_probe = tmp_path / "network_probe"
    request = tmp_path / "request"
    stage = tmp_path / "stage"
    for path in (network_probe, request, stage):
        path.write_bytes(path.name.encode("utf-8"))
    mounts = {
        "/input/network_probe.json": network_probe,
        "/input/request.json": request,
        "/input/stage.json": stage,
    }
    descriptors = _artifact_descriptors(
        {
            "network_probe": network_probe,
            "request": request,
            "stage": stage,
        }
    )
    image = _image("candidate", "a")
    inspect_value = _raw_inspect(
        role="candidate",
        image=image,
        uid=runner.CANDIDATE_UID,
        mounts=mounts,
    )
    inspect_value["HostConfig"]["Ulimits"][0][field] = float(
        runner.NOFILE_LIMIT
    )
    with pytest.raises(runner.LocalIsolationError):
        runner.normalize_container_inspect(
            role="candidate",
            inspect_row=inspect_value,
            image=image,
            expected_uid=runner.CANDIDATE_UID,
            expected_mounts=mounts,
            artifact_descriptors=descriptors,
        )


def test_candidate_inspect_rejects_extra_or_writable_mount(
    tmp_path: Path,
) -> None:
    network_probe = tmp_path / "network_probe"
    request = tmp_path / "request"
    stage = tmp_path / "stage"
    extra = tmp_path / "gold"
    for path in (network_probe, request, stage, extra):
        path.write_bytes(path.name.encode("utf-8"))
    mounts = {
        "/input/network_probe.json": network_probe,
        "/input/request.json": request,
        "/input/stage.json": stage,
    }
    descriptors = _artifact_descriptors(
        {
            "network_probe": network_probe,
            "request": request,
            "stage": stage,
        }
    )
    image = _image("candidate", "a")
    base = _raw_inspect(
        role="candidate",
        image=image,
        uid=runner.CANDIDATE_UID,
        mounts=mounts,
    )
    writable = deepcopy(base)
    writable["Mounts"][0]["RW"] = True
    with pytest.raises(runner.LocalIsolationError):
        runner.normalize_container_inspect(
            role="candidate",
            inspect_row=writable,
            image=image,
            expected_uid=runner.CANDIDATE_UID,
            expected_mounts=mounts,
            artifact_descriptors=descriptors,
        )
    extra_mount = deepcopy(base)
    extra_mount["Mounts"].append(
        {
            "Destination": "/fixture/gold.json",
            "RW": False,
            "Source": str(extra.resolve()),
            "Type": "bind",
        }
    )
    with pytest.raises(runner.LocalIsolationError):
        runner.normalize_container_inspect(
            role="candidate",
            inspect_row=extra_mount,
            image=image,
            expected_uid=runner.CANDIDATE_UID,
            expected_mounts=mounts,
            artifact_descriptors=descriptors,
        )


@pytest.mark.parametrize("bad_source", [None, 7, True])
def test_candidate_inspect_requires_string_mount_source(
    tmp_path: Path,
    bad_source: object,
) -> None:
    network_probe = tmp_path / "network_probe"
    request = tmp_path / "request"
    stage = tmp_path / "stage"
    for path in (network_probe, request, stage):
        path.write_bytes(path.name.encode("utf-8"))
    mounts = {
        "/input/network_probe.json": network_probe,
        "/input/request.json": request,
        "/input/stage.json": stage,
    }
    descriptors = _artifact_descriptors(
        {
            "network_probe": network_probe,
            "request": request,
            "stage": stage,
        }
    )
    image = _image("candidate", "a")
    inspect_value = _raw_inspect(
        role="candidate",
        image=image,
        uid=runner.CANDIDATE_UID,
        mounts=mounts,
    )
    inspect_value["Mounts"][0]["Source"] = bad_source
    with pytest.raises(runner.LocalIsolationError):
        runner.normalize_container_inspect(
            role="candidate",
            inspect_row=inspect_value,
            image=image,
            expected_uid=runner.CANDIDATE_UID,
            expected_mounts=mounts,
            artifact_descriptors=descriptors,
        )


def test_portable_host_path_preserves_posix_case_sensitivity() -> None:
    assert runner._portable_host_path(
        r"C:\Workspace\Input\Request.json"
    ) == runner._portable_host_path(
        "c:/workspace/input/request.json"
    )
    assert runner._portable_host_path(
        "/run/desktop/mnt/host/c/Workspace/Input/Request.json"
    ) == runner._portable_host_path(
        "C:/workspace/input/request.json"
    )
    assert runner._portable_host_path(
        "/srv/ATANOR/Input.json"
    ) != runner._portable_host_path(
        "/srv/atanor/input.json"
    )


def test_candidate_response_requires_exact_probe_inventory() -> None:
    request, request_payload = _request_and_payload()
    _, stage_payload = _canonical_fixture(runner.STAGE_FIXTURE)
    _, network_probe_payload = _network_probe_and_payload()
    response, _ = _candidate_response(
        request,
        request_payload,
        stage_payload,
        network_probe_payload,
    )
    assert runner.validate_candidate_response(
        response,
        request=request,
        request_payload=request_payload,
        stage_payload=stage_payload,
        network_probe_payload=network_probe_payload,
    ) == response
    reduced = deepcopy(response)
    reduced["probes"] = {
        "self_declared_pass": {"error_type": None, "passed": True}
    }
    with pytest.raises(runner.LocalIsolationError):
        runner.validate_candidate_response(
            reduced,
            request=request,
            request_payload=request_payload,
            stage_payload=stage_payload,
            network_probe_payload=network_probe_payload,
        )


def test_local_fixture_hmac_is_bound_but_never_authority() -> None:
    request, request_payload = _request_and_payload()
    _, stage_payload = _canonical_fixture(runner.STAGE_FIXTURE)
    _, gold_payload = _canonical_fixture(runner.GOLD_FIXTURE)
    _, network_probe_payload = _network_probe_and_payload()
    _, response_payload = _candidate_response(
        request,
        request_payload,
        stage_payload,
        network_probe_payload,
    )
    key = b"fixture-key-material-32-bytes!!!"
    assert len(key) == 32
    value, payload = _fixture_evaluation(
        request=request,
        request_payload=request_payload,
        response_payload=response_payload,
        gold_payload=gold_payload,
        network_probe_payload=network_probe_payload,
        key=key,
    )
    checked = runner.verify_local_fixture_evaluation(
        value,
        payload=payload,
        key=key,
        request=request,
        request_payload=request_payload,
        response_payload=response_payload,
        gold_payload=gold_payload,
        network_probe_payload=network_probe_payload,
    )
    assert checked["claims"] == runner.FIXTURE_FALSE_CLAIMS
    assert checked["signature"]["scheme"] == (
        "hmac-sha256-local-fixture-not-authority"
    )
    assert "ed25519" not in checked["signature"]["scheme"]

    tampered = deepcopy(value)
    tampered["signature"]["signature_hex"] = "0" * 64
    tampered_payload = runner.canonical_json_bytes(tampered) + b"\n"
    with pytest.raises(runner.LocalIsolationError):
        runner.verify_local_fixture_evaluation(
            tampered,
            payload=tampered_payload,
            key=key,
            request=request,
            request_payload=request_payload,
            response_payload=response_payload,
            gold_payload=gold_payload,
            network_probe_payload=network_probe_payload,
        )


def test_manifest_records_only_same_host_observation_gate(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    assert runner.validate_manifest(manifest) == []
    assert (
        manifest["gates"][
            "same_host_docker_isolation_gate_passed"
        ]
        is True
    )
    assert manifest["claims"] == runner.FALSE_CLAIMS == {
        "canonical_e4_established": False,
        "e5_established": False,
        "independent_evaluation_established": False,
        "os_isolation_established": False,
    }
    assert manifest["scope"] == runner.NON_CLAIM_SCOPE == {
        "benchmark_capability_evaluated": False,
        "external_authenticity_evaluated": False,
        "local_fixture_only": True,
        "production_authority_evaluated": False,
        "resource_curve_measured": False,
    }
    assert manifest["network_control"] == _network_control()
    assert "host" not in manifest["network_control"]
    assert manifest["artifacts"]["network_probe"]["sha256"] == (
        manifest["candidate_response"]["network_probe_sha256"]
    )
    assert manifest["artifacts"]["network_probe"]["sha256"] == (
        manifest["fixture_evaluation"]["network_probe_sha256"]
    )
    assert manifest["manifest_checksum_sha256"] == (
        runner._manifest_checksum(manifest)
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("claims", "os_isolation_established", True),
        ("claims", "independent_evaluation_established", True),
        ("claims", "canonical_e4_established", True),
        ("claims", "e5_established", True),
        ("scope", "external_authenticity_evaluated", True),
        ("scope", "resource_curve_measured", True),
        ("gates", "candidate_inspect_policy_passed", False),
    ],
)
def test_manifest_authority_or_gate_tamper_is_rejected(
    tmp_path: Path,
    section: str,
    field: str,
    value: bool,
) -> None:
    manifest = _manifest(tmp_path)
    manifest[section][field] = value
    manifest["manifest_checksum_sha256"] = runner._manifest_checksum(
        manifest
    )
    assert runner.validate_manifest(manifest)


@pytest.mark.parametrize(
    ("group", "numeric_value"),
    [
        ("root_claims", 0),
        ("root_claims", 0.0),
        ("root_scope_false", 0),
        ("root_scope_true", 1.0),
        ("fixture_claims", 0),
        ("fixture_claims", 0.0),
    ],
)
def test_manifest_boolean_numeric_coercion_is_rejected(
    tmp_path: Path,
    group: str,
    numeric_value: int | float,
) -> None:
    manifest = _manifest(tmp_path)
    if group == "root_claims":
        manifest["claims"]["os_isolation_established"] = numeric_value
    elif group == "root_scope_false":
        manifest["scope"]["resource_curve_measured"] = numeric_value
    elif group == "root_scope_true":
        manifest["scope"]["local_fixture_only"] = numeric_value
    else:
        manifest["fixture_evaluation"]["claims"][
            "os_isolation_established"
        ] = numeric_value
        _rebind_fixture_artifact(manifest)
    manifest["manifest_checksum_sha256"] = runner._manifest_checksum(
        manifest
    )
    assert runner.validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "numeric_value"),
    [
        ("dead", 0),
        ("error_present", 0.0),
        ("oom_killed", 0),
        ("running", 0.0),
    ],
)
def test_manifest_post_run_boolean_coercion_is_rejected(
    tmp_path: Path,
    field: str,
    numeric_value: int | float,
) -> None:
    manifest = _manifest(tmp_path)
    manifest["docker"]["containers"]["candidate"]["post_run"][
        field
    ] = numeric_value
    manifest["manifest_checksum_sha256"] = runner._manifest_checksum(
        manifest
    )
    assert runner.validate_manifest(manifest)


def test_manifest_checksum_and_exclusive_write(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    path = tmp_path / "manifest.json"
    runner.write_manifest_exclusive(path, manifest)
    assert path.read_bytes() == (
        runner.canonical_json_bytes(manifest) + b"\n"
    )
    assert runner.verify_manifest_file(path) == {
        "canonical_bytes": True,
        "findings": [],
        "valid": True,
    }
    with pytest.raises(runner.LocalIsolationError):
        runner.write_manifest_exclusive(path, manifest)

    tampered = deepcopy(manifest)
    tampered["claims"]["independent_evaluation_established"] = True
    path2 = tmp_path / "tampered.json"
    path2.write_bytes(runner.canonical_json_bytes(tampered) + b"\n")
    assert runner.verify_manifest_file(path2)["valid"] is False


def test_rechecksummed_nested_historical_tampering_is_rejected(
    tmp_path: Path,
) -> None:
    base = _manifest(tmp_path)
    mutations = [
        (
            ("candidate_request", "nonce"),
            "local:tampered-request-nonce",
        ),
        (
            ("candidate_response", "run_id"),
            "science-e4-local-tampered",
        ),
        (
            ("fixture_evaluation", "nonce"),
            "local:tampered-fixture-nonce",
        ),
        (
            ("artifacts", "candidate_response", "bytes"),
            base["artifacts"]["candidate_response"]["bytes"] + 1,
        ),
        (
            (
                "source",
                "candidate_context",
                "files",
                0,
                "sha256",
            ),
            "d" * 64,
        ),
        (
            (
                "docker",
                "images",
                "candidate",
                "architecture",
            ),
            "x86_64",
        ),
        (
            (
                "docker",
                "images",
                "candidate",
                "source_context_sha256",
            ),
            "d" * 64,
        ),
        (
            (
                "docker",
                "containers",
                "candidate",
                "inspect",
                "image_id",
            ),
            "sha256:" + "d" * 64,
        ),
        (
            (
                "docker",
                "containers",
                "candidate",
                "inspect",
                "mounts",
                0,
                "source_sha256",
            ),
            "d" * 64,
        ),
        (
            (
                "docker",
                "containers",
                "evaluator",
                "post_run",
                "exit_code",
            ),
            7,
        ),
        (
            (
                "fixture_evaluation",
                "signature",
                "payload_sha256",
            ),
            "d" * 64,
        ),
        (
            ("network_control", "liveness_check_count"),
            2,
        ),
        (
            ("gates", "candidate_inspect_policy_passed"),
            False,
        ),
    ]
    for path, replacement in mutations:
        manifest = deepcopy(base)
        cursor = manifest
        for component in path[:-1]:
            cursor = cursor[component]
        cursor[path[-1]] = replacement
        manifest["manifest_checksum_sha256"] = (
            runner._manifest_checksum(manifest)
        )
        assert runner.validate_manifest(manifest), path


@pytest.mark.parametrize(
    "module",
    [candidate_probe, fixture_evaluator],
)
def test_sentinel_probe_rejects_irrelevant_oserror(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    def fail_with_emfile(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EMFILE, "too many open files")

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        fail_with_emfile,
    )
    result = module._sentinel_connect_blocked(
        {
            "host": "172.30.0.2",
            "port": runner.NETWORK_SENTINEL_PORT,
        }
    )
    assert result["passed"] is False
    assert result["error_type"] == "OSError:EMFILE"


@pytest.mark.parametrize(
    "module",
    [candidate_probe, fixture_evaluator],
)
def test_sentinel_probe_accepts_only_explicit_network_block(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    def fail_unreachable(*args: object, **kwargs: object) -> None:
        raise OSError(errno.ENETUNREACH, "network unreachable")

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        fail_unreachable,
    )
    result = module._sentinel_connect_blocked(
        {
            "host": "172.30.0.2",
            "port": runner.NETWORK_SENTINEL_PORT,
        }
    )
    assert result["passed"] is True
    assert result["error_type"] == "OSError:ENETUNREACH"


@pytest.mark.parametrize(
    ("module", "error_number"),
    [
        (candidate_probe, errno.ECONNREFUSED),
        (candidate_probe, errno.ETIMEDOUT),
        (fixture_evaluator, errno.ECONNREFUSED),
        (fixture_evaluator, errno.ETIMEDOUT),
    ],
)
def test_sentinel_probe_rejects_refusal_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    error_number: int,
) -> None:
    def fail_connection(*args: object, **kwargs: object) -> None:
        raise OSError(error_number, "not a network-none proof")

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        fail_connection,
    )
    assert module._sentinel_connect_blocked(
        {
            "host": "172.30.0.2",
            "port": runner.NETWORK_SENTINEL_PORT,
        }
    )["passed"] is False


@pytest.mark.parametrize(
    "module",
    [candidate_probe, fixture_evaluator],
)
def test_sentinel_probe_rejects_timeout_without_network_errno(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    def fail_timeout(*args: object, **kwargs: object) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        fail_timeout,
    )
    assert module._sentinel_connect_blocked(
        {
            "host": "172.30.0.2",
            "port": runner.NETWORK_SENTINEL_PORT,
        }
    )["passed"] is False


def test_dead_sentinel_fails_liveness_before_client_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_container_inspect",
        lambda name: {
            "Id": "a" * 64,
            "State": {
                "Dead": False,
                "Error": "",
                "OOMKilled": False,
                "Running": False,
            },
        },
    )
    with pytest.raises(
        runner.LocalIsolationError,
        match="sentinel is not live",
    ):
        runner._check_network_sentinel_liveness(
            image="candidate:test",
            network="internal-test",
            sentinel_name="sentinel-test",
            sentinel_id="a" * 64,
            network_probe={
                "host": "172.30.0.2",
                "port": runner.NETWORK_SENTINEL_PORT,
                "schema_version": runner.NETWORK_PROBE_SCHEMA,
            },
            checkpoint="after_candidate",
            created=[],
        )


def test_source_snapshot_rejects_stale_build_label_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_context = tmp_path / "candidate"
    evaluator_context = tmp_path / "evaluator"
    candidate_context.mkdir()
    evaluator_context.mkdir()
    for context, files in (
        (candidate_context, runner.CANDIDATE_CONTEXT_FILES),
        (evaluator_context, runner.EVALUATOR_CONTEXT_FILES),
    ):
        for relative in files:
            path = context / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("initial:" + relative).encode("utf-8"))
    monkeypatch.setattr(runner, "CANDIDATE_CONTEXT", candidate_context)
    monkeypatch.setattr(runner, "EVALUATOR_CONTEXT", evaluator_context)
    candidate_scope = runner._source_scope(
        candidate_context,
        expected_files=runner.CANDIDATE_CONTEXT_FILES,
    )
    evaluator_scope = runner._source_scope(
        evaluator_context,
        expected_files=runner.EVALUATOR_CONTEXT_FILES,
    )
    runner_descriptor = runner._descriptor(
        Path(runner.__file__).read_bytes()
    )
    (candidate_context / "candidate_probe.py").write_bytes(
        b"changed-after-source-sha-before-build"
    )
    with pytest.raises(
        runner.LocalIsolationError,
        match="source snapshot changed",
    ):
        runner._assert_source_snapshot_unchanged(
            candidate_scope=candidate_scope,
            evaluator_scope=evaluator_scope,
            runner_descriptor=runner_descriptor,
        )


def test_create_tracking_precedes_container_id_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_run_docker",
        lambda arguments: subprocess.CompletedProcess(
            args=["docker", *arguments],
            returncode=0,
            stdout=b"not-a-container-id\n",
            stderr=b"",
        ),
    )
    created: list[str] = []
    with pytest.raises(runner.LocalIsolationError):
        runner._create_tracked_container(
            arguments=["create", "--name", "tracked", "image:test"],
            name="tracked",
            created=created,
        )
    assert created == ["tracked"]


def test_failed_create_is_not_registered_for_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_create(arguments: object) -> None:
        raise runner.LocalIsolationError("create failed")

    monkeypatch.setattr(runner, "_run_docker", fail_create)
    created: list[str] = []
    with pytest.raises(runner.LocalIsolationError):
        runner._create_tracked_container(
            arguments=["create", "--name", "failed", "image:test"],
            name="failed",
            created=created,
        )
    assert created == []


def test_network_tracking_precedes_network_id_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_run_docker",
        lambda arguments: subprocess.CompletedProcess(
            args=["docker", *arguments],
            returncode=0,
            stdout=b"not-a-network-id\n",
            stderr=b"",
        ),
    )
    created: list[str] = []
    with pytest.raises(runner.LocalIsolationError):
        runner._create_internal_network(
            "tracked-network",
            created=created,
        )
    assert created == ["tracked-network"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Id", "b" * 64),
        ("Internal", False),
        ("Driver", "overlay"),
    ],
)
def test_created_network_requires_exact_inspect_binding(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    network_id = "a" * 64
    monkeypatch.setattr(
        runner,
        "_run_docker",
        lambda arguments: subprocess.CompletedProcess(
            args=["docker", *arguments],
            returncode=0,
            stdout=(network_id + "\n").encode("ascii"),
            stderr=b"",
        ),
    )
    inspect_row = {
        "Driver": "bridge",
        "Id": network_id,
        "Internal": True,
        "Labels": {
            "org.atanor.science-e4-local.role": "network-sentinel"
        },
        "Name": "tracked-network",
    }
    inspect_row[field] = value
    monkeypatch.setattr(
        runner,
        "_network_inspect",
        lambda name: inspect_row,
    )
    created: list[str] = []
    with pytest.raises(runner.LocalIsolationError):
        runner._create_internal_network(
            "tracked-network",
            created=created,
        )
    assert created == ["tracked-network"]


def test_create_id_and_cleanup_not_found_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(
        runner.LocalIsolationError,
        match="does not match",
    ):
        runner._require_container_id(
            {"Id": "b" * 64},
            expected_id="a" * 64,
        )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["docker", "rm"],
            returncode=1,
            stdout=b"",
            stderr=b"Error: No such container: missing",
        ),
    )
    assert runner._remove_container("missing") == "not_found"


def test_readme_names_the_same_host_limits() -> None:
    readme = (runner.BASE_DIR / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    for phrase in (
        "does **not** prove evaluator independence",
        "not production authority",
        "not remote attestation",
        "do not establish a clean or reproducible resource curve",
        "A canonical independent E4 still requires",
    ):
        assert phrase in normalized
