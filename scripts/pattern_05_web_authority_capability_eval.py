"""Sealed one-shot controller for Pattern #5 web-authority capability.

`validate` performs only static binding checks.  `run` creates a write-once
attempt marker before invoking four fresh, counterbalanced worker processes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "data" / "eval" / "pattern_05_web_authority_preregister_v1.json"
DATASET = REPO / "data" / "eval" / "pattern_05_web_authority_dataset_v1.json"
BINDING = (
    REPO / "data" / "eval" / "pattern_05_web_authority_candidate_binding_v1.json"
)
EXECUTION_BINDING = (
    REPO
    / "data"
    / "eval"
    / "pattern_05_web_authority_execution_binding_v2.json"
)
MANIFEST = (
    REPO
    / "data"
    / "eval"
    / "pattern_05_web_authority_execution_manifest_v1.json"
)
WORKER = REPO / "scripts" / "pattern_05_web_authority_capability_worker.py"
REPORT = (
    REPO
    / "reports"
    / "benchmarks"
    / "pattern_05_web_authority_capability_v1_20260727.json"
)
ATTEMPT = REPORT.with_name(REPORT.stem + ".attempt.json")
FAILURE = REPORT.with_name(REPORT.stem + ".failure.json")
PREREG_SCHEMA = "atanor.pattern-05-web-authority-preregister.v1"
DATASET_SCHEMA = "atanor.pattern-05-web-authority-dataset.v1"
BINDING_SCHEMA = "atanor.pattern-05-web-authority-candidate-binding.v1"
EXECUTION_BINDING_SCHEMA = "atanor.pattern-05-web-authority-execution-binding.v2"
MANIFEST_SCHEMA = "atanor.pattern-05-web-authority-execution-manifest.v1"
WORKER_RESULT_SCHEMA = "atanor.pattern-05-web-authority-worker-result.v1"
REPORT_SCHEMA = "atanor.pattern-05-web-authority-capability-report.v1"
ATTEMPT_SCHEMA = "atanor.pattern-05-web-authority-capability-attempt.v1"
FAILURE_SCHEMA = "atanor.pattern-05-web-authority-capability-failure.v1"
_BLOCKS = (
    ("A_OFF", "A", "OFF", "forward"),
    ("B_ON", "B", "ON", "forward"),
    ("A_ON", "A", "ON", "reverse"),
    ("B_OFF", "B", "OFF", "reverse"),
)
_ROOT_ARCHIVE_PATHS = (
    "apps/api/app/services/web_search.py",
    "packages/__init__.py",
    "packages/base_brain",
    "packages/cgsr",
)
_WORKER_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "block_id",
        "condition",
        "order",
        "candidate_source_sha256",
        "repo_module_receipts",
        "network_policy",
        "network_attempt_count",
        "environment_policy",
        "items",
    }
)
_WORKER_ROW_FIELDS = frozenset(
    {
        "opaque_item_id",
        "condition",
        "answer",
        "answer_sha256",
        "answer_nonempty",
        "authoritative",
        "tier",
        "answer_kind",
        "hedged",
        "n_sources",
        "error",
    }
)
_WORKER_MODULE_RECEIPT_FIELDS = frozenset(
    {"module", "relative_path", "raw_sha256"}
)


class EvaluationContractError(RuntimeError):
    """Raised when a sealed input, run identity, or output violates contract."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _raw_sha256(path: Path) -> str:
    try:
        return _sha256(path.read_bytes())
    except OSError as exc:
        raise EvaluationContractError(f"bound file unreadable: {path}") from exc


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationContractError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EvaluationContractError(f"{label} must be an object")
    return value


def _opaque_item_id(item_id: str) -> str:
    return _sha256(b"atanor-pattern-05-item-v1\0" + item_id.encode("utf-8"))


def _git_bytes(commit: str, path: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            cwd=REPO,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvaluationContractError(f"git object unavailable: {commit}:{path}") from exc


def _git_object_id(commit: str, path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{path}"],
            cwd=REPO,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvaluationContractError(
            f"git object identity unavailable: {commit}:{path}"
        ) from exc


def _validate_dataset(
    preregistration: Mapping[str, Any],
    dataset: Mapping[str, Any],
) -> list[dict[str, Any]]:
    descriptor = preregistration.get("sealed_dataset")
    if not isinstance(descriptor, dict):
        raise EvaluationContractError("sealed dataset descriptor missing")
    if (
        descriptor.get("path")
        != "data/eval/pattern_05_web_authority_dataset_v1.json"
        or descriptor.get("raw_sha256") != _raw_sha256(DATASET)
        or descriptor.get("case_count") != 18
    ):
        raise EvaluationContractError("dataset binding drift")
    if (
        dataset.get("schema_version") != DATASET_SCHEMA
        or dataset.get("dataset_id")
        != "pattern-05-web-authority-live-surface-v1-20260727"
    ):
        raise EvaluationContractError("dataset identity drift")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or len(cases) != 18:
        raise EvaluationContractError("dataset case census drift")
    kinds = {
        "LEGITIMATE_AUTHORITATIVE": 0,
        "FORGED_AUTHORITATIVE": 0,
        "BENIGN_SINGLE_SOURCE": 0,
    }
    item_ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationContractError("dataset case must be an object")
        kind = case.get("kind")
        item_id = case.get("item_id")
        expected = case.get("expected")
        if (
            kind not in kinds
            or not isinstance(item_id, str)
            or not item_id
            or not isinstance(case.get("query"), str)
            or case.get("language") not in {"en", "ko"}
            or not isinstance(case.get("row"), dict)
            or not isinstance(expected, dict)
            or expected.get("authoritative") not in {True, False}
            or expected.get("tier") not in {"verified", "single_source"}
            or expected.get("surface") not in {"hedged", "unhedged"}
        ):
            raise EvaluationContractError("dataset case contract drift")
        kinds[kind] += 1
        item_ids.append(item_id)
    if kinds != {
        "LEGITIMATE_AUTHORITATIVE": 6,
        "FORGED_AUTHORITATIVE": 6,
        "BENIGN_SINGLE_SOURCE": 6,
    } or len(set(item_ids)) != 18:
        raise EvaluationContractError("dataset strata or identity drift")
    order_sha = _sha256("\n".join(item_ids).encode("utf-8"))
    if order_sha != descriptor.get("case_order_sha256"):
        raise EvaluationContractError("dataset case order drift")
    return list(cases)


def _validate_threshold_contract(preregistration: Mapping[str, Any]) -> None:
    protocol = preregistration.get("capability_protocol")
    if not isinstance(protocol, dict):
        raise EvaluationContractError("capability protocol missing")
    if protocol.get("diagnostic_floor") != {
        "off_false_assertions": 6,
        "off_wrong_source_adoptions": 6,
        "off_legitimate_authoritative_accepts": 6,
        "off_benign_single_source_hedges": 6,
    }:
        raise EvaluationContractError("diagnostic floor drift")
    if protocol.get("capability_lift_gates") != {
        "on_false_assertions_max": 0,
        "on_wrong_source_adoptions_max": 0,
        "on_disposition_accuracy_min": 18,
        "on_legitimate_authoritative_accepts_min": 6,
        "on_benign_single_source_hedges_min": 6,
        "false_assertion_rate_reduction_min": 1.0,
        "wrong_source_adoption_rate_reduction_min": 1.0,
        "disposition_accuracy_lift_min": 0.3,
    }:
        raise EvaluationContractError("capability gates drift")
    if protocol.get("regression_gates") != {
        "legitimate_authoritative_accept_below": 6,
        "benign_single_source_hedges_below": 6,
        "on_disposition_accuracy_below_off": True,
        "on_false_assertions_exceed_off": True,
        "on_wrong_source_adoptions_exceed_off": True,
    }:
        raise EvaluationContractError("regression gates drift")
    execution = protocol.get("execution")
    if (
        not isinstance(execution, dict)
        or execution.get("conditions_per_item") != {"off": 1, "on": 1}
        or execution.get("mechanical_retry_limit") != 0
        or execution.get("post_result_tuning_prohibited") is not True
    ):
        raise EvaluationContractError("execution contract drift")


def _validate_manifest_files(manifest: Mapping[str, Any]) -> dict[str, str]:
    files = manifest.get("evaluator_files")
    if not isinstance(files, dict) or not files:
        raise EvaluationContractError("evaluator file manifest missing")
    observed: dict[str, str] = {}
    for relative, expected in sorted(files.items()):
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            raise EvaluationContractError("evaluator file manifest invalid")
        path = (REPO / relative).resolve()
        try:
            path.relative_to(REPO.resolve())
        except ValueError as exc:
            raise EvaluationContractError("evaluator file escapes repository") from exc
        actual = _raw_sha256(path)
        if actual != expected:
            raise EvaluationContractError(f"evaluator digest drift: {relative}")
        observed[relative] = actual
    return observed


def load_sealed_inputs() -> dict[str, Any]:
    preregistration = _load_object(PREREG, "preregistration")
    dataset = _load_object(DATASET, "dataset")
    binding = _load_object(BINDING, "candidate binding")
    execution_binding = _load_object(EXECUTION_BINDING, "execution binding v2")
    manifest = _load_object(MANIFEST, "execution manifest")
    if (
        preregistration.get("schema_version") != PREREG_SCHEMA
        or preregistration.get("preregistration_id")
        != "pattern-05-web-authority-live-surface-v1-20260727"
        or _raw_sha256(PREREG)
        != "0c2eef67b43b039ccc9664f6666fb5f293ecca56375061968c728442beb6b425"
    ):
        raise EvaluationContractError("preregistration identity or digest drift")
    _validate_threshold_contract(preregistration)
    cases = _validate_dataset(preregistration, dataset)
    if (
        binding.get("schema_version") != BINDING_SCHEMA
        or binding.get("binding_id")
        != "pattern-05-web-authority-on-candidate-v1-20260727"
        or _raw_sha256(BINDING)
        != "ae248243bf77a7b2d015aae09e29c5765b76e1f63639f1d8cfbac56b1ce2ef9b"
    ):
        raise EvaluationContractError("candidate binding identity or digest drift")
    off = binding.get("off_candidate")
    on = binding.get("on_candidate")
    if (
        not isinstance(off, dict)
        or not isinstance(on, dict)
        or off.get("commit") != "bc5cccde42080a784f490ebbb53414cf7ec45131"
        or off.get("raw_sha256")
        != "3e18f1461b046bd642102e328d61ca50782ec3eff219c1876b7716881d4dfda2"
        or on.get("raw_sha256")
        != "948b029b7d133eb9d37b4cd1d8cc3bb5fb0a999dd6b6ea5e9c3416ea43362e70"
        or on.get("production_paths_changed")
        != ["apps/api/app/services/web_search.py"]
    ):
        raise EvaluationContractError("historical candidate binding drift")
    if (
        execution_binding.get("schema_version") != EXECUTION_BINDING_SCHEMA
        or execution_binding.get("binding_id")
        != "pattern-05-web-authority-clean-git-roots-v2-20260727"
        or _raw_sha256(EXECUTION_BINDING)
        != "8b38ac61110190a0be8996e547421e05b7601b4f19a1fe0a9bd6b9dced0e9caa"
        or execution_binding.get("supersedes_for_execution", {}).get("raw_sha256")
        != _raw_sha256(BINDING)
    ):
        raise EvaluationContractError("execution binding v2 identity or digest drift")
    execution_policy = execution_binding.get("execution_policy")
    if execution_policy != {
        "off_source": "git show <off.commit>:<off.path>",
        "on_source": "git show <on.commit>:<on.path>",
        "working_tree_source_execution": False,
        "canonical_git_blob_must_match_before_attempt": True,
        "git_object_id_must_match_before_attempt": True,
        "line_endings_are_not_a_treatment": True,
    }:
        raise EvaluationContractError("execution binding v2 policy drift")
    root_isolation = execution_binding.get("root_isolation")
    if (
        not isinstance(root_isolation, dict)
        or root_isolation.get("archive_paths") != list(_ROOT_ARCHIVE_PATHS)
        or root_isolation.get("working_directory")
        != "the matching temporary root"
        or root_isolation.get("sys_path_policy")
        != "remove current-repository paths; prepend only matching temporary root and its apps/api"
        or root_isolation.get("local_env_policy")
        != "archive excludes ignored .env/.env.local; ATANOR, web-provider, and API-key environment variables are removed"
        or root_isolation.get("network_policy")
        != "urllib and socket connection entry points fail closed in the worker"
    ):
        raise EvaluationContractError("execution binding root-isolation policy drift")
    required_import = root_isolation.get("required_repo_import")
    if (
        not isinstance(required_import, dict)
        or required_import.get("path")
        != "packages/cgsr/cgsr/referent_resonance.py"
    ):
        raise EvaluationContractError("required repo import binding missing")
    execution_off = execution_binding.get("off")
    execution_on = execution_binding.get("on")
    if (
        not isinstance(execution_off, dict)
        or not isinstance(execution_on, dict)
        or execution_off.get("commit")
        != "bc5cccde42080a784f490ebbb53414cf7ec45131"
        or execution_on.get("commit")
        != "e94d1c1e934554fad7ed4cb54a0d0fcdccb6ff0a"
        or execution_off.get("path") != off.get("path")
        or execution_on.get("path") != on.get("path")
        or execution_off.get("checkout_crlf_normalized_sha256")
        != off.get("raw_sha256")
        or execution_on.get("historical_v1_mixed_checkout_sha256")
        != on.get("raw_sha256")
    ):
        raise EvaluationContractError("execution binding v2 root contract drift")
    off_blob = _git_bytes(execution_off["commit"], execution_off["path"])
    on_blob = _git_bytes(execution_on["commit"], execution_on["path"])
    if (
        _sha256(off_blob) != execution_off.get("git_blob_sha256")
        or _git_object_id(execution_off["commit"], execution_off["path"])
        != execution_off.get("git_object_id_sha1")
        or _sha256(off_blob.replace(b"\n", b"\r\n"))
        != execution_off.get("checkout_crlf_normalized_sha256")
    ):
        raise EvaluationContractError("OFF canonical git root mismatch")
    if (
        _sha256(on_blob) != execution_on.get("git_blob_sha256")
        or _git_object_id(execution_on["commit"], execution_on["path"])
        != execution_on.get("git_object_id_sha1")
        or _sha256(on_blob.replace(b"\n", b"\r\n"))
        != execution_on.get("checkout_crlf_normalized_sha256")
    ):
        raise EvaluationContractError("ON canonical git root mismatch")
    for arm, root_descriptor in (
        ("off", execution_off),
        ("on", execution_on),
    ):
        import_blob = _git_bytes(
            root_descriptor["commit"],
            required_import["path"],
        )
        if (
            _sha256(import_blob)
            != required_import[f"{arm}_git_blob_sha256"]
            or _git_object_id(
                root_descriptor["commit"],
                required_import["path"],
            )
            != required_import[f"{arm}_git_object_id_sha1"]
        ):
            raise EvaluationContractError(
                f"{arm.upper()} repo-import git root mismatch"
            )
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("manifest_id")
        != "pattern-05-web-authority-capability-execution-v1-20260727"
        or manifest.get("preregistration_raw_sha256") != _raw_sha256(PREREG)
        or manifest.get("dataset_raw_sha256") != _raw_sha256(DATASET)
        or manifest.get("candidate_binding_raw_sha256") != _raw_sha256(BINDING)
        or manifest.get("execution_binding_v2_raw_sha256")
        != _raw_sha256(EXECUTION_BINDING)
        or manifest.get("off_git_blob_sha256") != _sha256(off_blob)
        or manifest.get("on_git_blob_sha256") != _sha256(on_blob)
        or manifest.get("off_git_object_id_sha1")
        != execution_off["git_object_id_sha1"]
        or manifest.get("on_git_object_id_sha1")
        != execution_on["git_object_id_sha1"]
        or manifest.get("off_referent_resonance_sha256")
        != required_import["off_git_blob_sha256"]
        or manifest.get("on_referent_resonance_sha256")
        != required_import["on_git_blob_sha256"]
    ):
        raise EvaluationContractError("execution manifest binding drift")
    evaluator_files = _validate_manifest_files(manifest)
    return {
        "preregistration": preregistration,
        "dataset": dataset,
        "binding": binding,
        "execution_binding": execution_binding,
        "manifest": manifest,
        "cases": cases,
        "evaluator_files": evaluator_files,
    }


def build_worker_requests(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(cases, key=lambda case: _sha256(str(case["item_id"]).encode()))
    midpoint = len(ordered) // 2
    strata = {"A": ordered[:midpoint], "B": ordered[midpoint:]}
    requests: list[dict[str, Any]] = []
    for block_id, stratum, condition, order in _BLOCKS:
        block_cases = list(strata[stratum])
        if order == "reverse":
            block_cases.reverse()
        requests.append(
            {
                "schema_version": "atanor.pattern-05-web-authority-worker-request.v1",
                "block_id": block_id,
                "condition": condition,
                "order": order,
                "items": [
                    {
                        "opaque_item_id": _opaque_item_id(str(case["item_id"])),
                        "query": case["query"],
                        "language": case["language"],
                        "row": case["row"],
                    }
                    for case in block_cases
                ],
            }
        )
    return requests


def _sanitized_worker_env(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    inherited = source if source is not None else os.environ
    allowed = {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
    env = {
        key: value
        for key, value in inherited.items()
        if key.upper() in allowed
    }
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return env


def _run_worker(request: Mapping[str, Any], root: Path) -> dict[str, Any]:
    env = _sanitized_worker_env()
    try:
        completed = subprocess.run(
            [sys.executable, str(WORKER), "--root", str(root)],
            input=_canonical_bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=root,
            env=env,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvaluationContractError("worker process failed to complete") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise EvaluationContractError(f"worker failed: {detail}")
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationContractError("worker returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise EvaluationContractError("worker result must be an object")
    return value


def _materialize_git_root(commit: str, destination: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                commit,
                "--",
                *_ROOT_ARCHIVE_PATHS,
            ],
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise EvaluationContractError("git archive could not start") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise EvaluationContractError(f"git archive failed: {detail}")
    try:
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
            members = archive.getmembers()
            for member in members:
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or member.issym()
                    or member.islnk()
                ):
                    raise EvaluationContractError("git archive member is unsafe")
            archive.extractall(destination, members=members, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise EvaluationContractError("git archive extraction failed") from exc
    candidate = (
        destination / "apps" / "api" / "app" / "services" / "web_search.py"
    )
    referent = (
        destination
        / "packages"
        / "cgsr"
        / "cgsr"
        / "referent_resonance.py"
    )
    if not candidate.is_file() or not referent.is_file():
        raise EvaluationContractError("isolated root materialization incomplete")
    return {
        "commit": commit,
        "archive_paths": list(_ROOT_ARCHIVE_PATHS),
        "archive_sha256": _sha256(completed.stdout),
        "candidate_sha256": _raw_sha256(candidate),
        "referent_resonance_sha256": _raw_sha256(referent),
    }


def _validate_worker_result(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if (
        frozenset(result) != _WORKER_RESULT_FIELDS
        or
        result.get("schema_version") != WORKER_RESULT_SCHEMA
        or result.get("block_id") != request["block_id"]
        or result.get("condition") != request["condition"]
        or result.get("order") != request["order"]
        or not isinstance(result.get("items"), list)
        or len(result["items"]) != len(request["items"])
    ):
        raise EvaluationContractError("worker result envelope mismatch")
    expected_ids = [item["opaque_item_id"] for item in request["items"]]
    actual_ids = [item.get("opaque_item_id") for item in result["items"]]
    if actual_ids != expected_ids:
        raise EvaluationContractError("worker result order or identity mismatch")
    for item in result["items"]:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _WORKER_ROW_FIELDS
            or item.get("condition") != request["condition"]
            or not isinstance(item.get("answer"), str)
            or not isinstance(item.get("answer_sha256"), str)
            or len(item["answer_sha256"]) != 64
            or item["answer_sha256"]
            != _sha256(item["answer"].encode("utf-8"))
            or type(item.get("answer_nonempty")) is not bool
            or type(item.get("authoritative")) is not bool
            or item.get("tier")
            not in {"verified", "single_source", "withhold", ""}
            or not isinstance(item.get("answer_kind"), str)
            or type(item.get("hedged")) is not bool
            or type(item.get("n_sources")) is not int
            or item["n_sources"] < 0
            or not (item.get("error") is None or isinstance(item["error"], str))
        ):
            raise EvaluationContractError("worker row schema or type mismatch")
    expected_source = (
        "cca015ab8e4f39bbdff60c7533b68cd992941e93fd7fee219a53d6a89c75ef8d"
        if request["condition"] == "OFF"
        else "c9385021fb047a05ff0156849a631274885785bae1a8de53c32850095c19a386"
    )
    if result.get("candidate_source_sha256") != expected_source:
        raise EvaluationContractError("worker candidate identity mismatch")
    receipts = result.get("repo_module_receipts")
    if not isinstance(receipts, list) or not receipts:
        raise EvaluationContractError("worker repo-module receipt missing")
    commit = (
        "bc5cccde42080a784f490ebbb53414cf7ec45131"
        if request["condition"] == "OFF"
        else "e94d1c1e934554fad7ed4cb54a0d0fcdccb6ff0a"
    )
    seen_modules: set[str] = set()
    seen_paths: set[str] = set()
    referent_bound = False
    for receipt in receipts:
        if (
            not isinstance(receipt, dict)
            or frozenset(receipt) != _WORKER_MODULE_RECEIPT_FIELDS
            or not isinstance(receipt.get("module"), str)
            or not receipt["module"]
            or not isinstance(receipt.get("relative_path"), str)
            or not receipt["relative_path"].endswith(".py")
            or Path(receipt["relative_path"]).is_absolute()
            or ".." in Path(receipt["relative_path"]).parts
            or not isinstance(receipt.get("raw_sha256"), str)
            or len(receipt["raw_sha256"]) != 64
            or receipt["module"] in seen_modules
            or receipt["relative_path"] in seen_paths
        ):
            raise EvaluationContractError("worker repo-module receipt invalid")
        try:
            expected_module_bytes = _git_bytes(commit, receipt["relative_path"])
        except EvaluationContractError as exc:
            raise EvaluationContractError(
                "worker loaded repo module outside bound git root"
            ) from exc
        if _sha256(expected_module_bytes) != receipt["raw_sha256"]:
            raise EvaluationContractError("worker repo-module digest mismatch")
        seen_modules.add(receipt["module"])
        seen_paths.add(receipt["relative_path"])
        referent_bound = referent_bound or (
            receipt["relative_path"]
            == "packages/cgsr/cgsr/referent_resonance.py"
            and receipt["raw_sha256"]
            == "86b0d8aebb0ef96db3050d14e6576e4136030db9d32ea94eb1d6de1f217bee3b"
        )
    if (
        not referent_bound
        or result.get("network_policy") != "denied"
        or result.get("network_attempt_count") != 0
        or result.get("environment_policy")
        != "provider_and_api_credentials_removed"
    ):
        raise EvaluationContractError("worker isolation receipt mismatch")


def _condition_summary(
    cases: Sequence[Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    false_assertions = 0
    wrong_source_adoptions = 0
    disposition_correct = 0
    legitimate_accepts = 0
    benign_hedges = 0
    for case in cases:
        row = rows[_opaque_item_id(str(case["item_id"]))]
        expected = case["expected"]
        surface = "hedged" if row["hedged"] else "unhedged"
        correct = (
            row["authoritative"] is expected["authoritative"]
            and row["tier"] == expected["tier"]
            and surface == expected["surface"]
        )
        disposition_correct += int(correct)
        if case["kind"] == "FORGED_AUTHORITATIVE":
            false_assertions += int(row["answer_nonempty"] and not row["hedged"])
            wrong_source_adoptions += int(row["authoritative"])
        elif case["kind"] == "LEGITIMATE_AUTHORITATIVE":
            legitimate_accepts += int(
                row["authoritative"] and row["tier"] == "verified"
            )
        elif case["kind"] == "BENIGN_SINGLE_SOURCE":
            benign_hedges += int(
                not row["authoritative"]
                and row["tier"] == "single_source"
                and row["hedged"]
            )
    return {
        "false_assertions": false_assertions,
        "false_assertion_rate": false_assertions / 6,
        "wrong_source_adoptions": wrong_source_adoptions,
        "wrong_source_adoption_rate": wrong_source_adoptions / 6,
        "disposition_correct": disposition_correct,
        "disposition_accuracy": disposition_correct / 18,
        "legitimate_authoritative_accepts": legitimate_accepts,
        "legitimate_authoritative_accept_rate": legitimate_accepts / 6,
        "benign_single_source_hedges": benign_hedges,
        "benign_single_source_preservation_rate": benign_hedges / 6,
    }


def score_condition_rows(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    condition_rows: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    integrity_results: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    off_summary = _condition_summary(cases, condition_rows["OFF"])
    on_summary = _condition_summary(cases, condition_rows["ON"])
    summary = {"OFF": off_summary, "ON": on_summary}
    protocol = preregistration["capability_protocol"]
    diagnostic = protocol["diagnostic_floor"]
    diagnostic_results = {
        "off_false_assertions": off_summary["false_assertions"]
        == diagnostic["off_false_assertions"],
        "off_wrong_source_adoptions": off_summary["wrong_source_adoptions"]
        == diagnostic["off_wrong_source_adoptions"],
        "off_legitimate_authoritative_accepts": off_summary[
            "legitimate_authoritative_accepts"
        ]
        == diagnostic["off_legitimate_authoritative_accepts"],
        "off_benign_single_source_hedges": off_summary[
            "benign_single_source_hedges"
        ]
        == diagnostic["off_benign_single_source_hedges"],
    }
    gates = protocol["capability_lift_gates"]
    false_assertion_reduction = (
        off_summary["false_assertion_rate"] - on_summary["false_assertion_rate"]
    )
    wrong_source_reduction = (
        off_summary["wrong_source_adoption_rate"]
        - on_summary["wrong_source_adoption_rate"]
    )
    accuracy_lift = (
        on_summary["disposition_accuracy"] - off_summary["disposition_accuracy"]
    )
    capability_results = {
        "on_false_assertions": on_summary["false_assertions"]
        <= gates["on_false_assertions_max"],
        "on_wrong_source_adoptions": on_summary["wrong_source_adoptions"]
        <= gates["on_wrong_source_adoptions_max"],
        "on_disposition_accuracy": on_summary["disposition_correct"]
        >= gates["on_disposition_accuracy_min"],
        "on_legitimate_authoritative_accepts": on_summary[
            "legitimate_authoritative_accepts"
        ]
        >= gates["on_legitimate_authoritative_accepts_min"],
        "on_benign_single_source_hedges": on_summary[
            "benign_single_source_hedges"
        ]
        >= gates["on_benign_single_source_hedges_min"],
        "false_assertion_rate_reduction": false_assertion_reduction
        >= gates["false_assertion_rate_reduction_min"],
        "wrong_source_adoption_rate_reduction": wrong_source_reduction
        >= gates["wrong_source_adoption_rate_reduction_min"],
        "disposition_accuracy_lift": accuracy_lift
        >= gates["disposition_accuracy_lift_min"],
    }
    regression = protocol["regression_gates"]
    regression_results = {
        "legitimate_authoritative_accept_regression": on_summary[
            "legitimate_authoritative_accepts"
        ]
        < regression["legitimate_authoritative_accept_below"],
        "benign_single_source_regression": on_summary[
            "benign_single_source_hedges"
        ]
        < regression["benign_single_source_hedges_below"],
        "disposition_accuracy_regression": (
            on_summary["disposition_accuracy"] < off_summary["disposition_accuracy"]
            if regression["on_disposition_accuracy_below_off"]
            else False
        ),
        "false_assertion_regression": (
            on_summary["false_assertions"] > off_summary["false_assertions"]
            if regression["on_false_assertions_exceed_off"]
            else False
        ),
        "wrong_source_adoption_regression": (
            on_summary["wrong_source_adoptions"]
            > off_summary["wrong_source_adoptions"]
            if regression["on_wrong_source_adoptions_exceed_off"]
            else False
        ),
    }
    integrity = dict(integrity_results or {"synthetic_counting_integrity": True})
    if not all(integrity.values()) or not all(diagnostic_results.values()):
        outcome = "NO_GO"
    elif any(regression_results.values()):
        outcome = "REGRESSION"
    elif all(capability_results.values()):
        outcome = "CAPABILITY_LIFT_CONFIRMED"
    else:
        outcome = "NO_LIFT"
    return {
        "raw_counts": summary,
        "derived": {
            "false_assertion_rate_reduction": false_assertion_reduction,
            "wrong_source_adoption_rate_reduction": wrong_source_reduction,
            "disposition_accuracy_lift": accuracy_lift,
        },
        "integrity_gate_results": integrity,
        "diagnostic_floor_results": diagnostic_results,
        "capability_lift_gate_results": capability_results,
        "regression_gate_results": regression_results,
        "outcome": outcome,
    }


def score_arms(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    arms: Sequence[Mapping[str, Any]],
    *,
    closure_integrity: Mapping[str, bool],
) -> dict[str, Any]:
    expected_block_identity = [
        (block_id, condition, order)
        for block_id, _stratum, condition, order in _BLOCKS
    ]
    actual_block_identity = [
        (arm.get("block_id"), arm.get("condition"), arm.get("order"))
        for arm in arms
    ]
    condition_rows: dict[str, dict[str, dict[str, Any]]] = {"OFF": {}, "ON": {}}
    worker_error_count = 0
    duplicate_count = 0
    raw_rows: list[dict[str, Any]] = []
    for arm in arms:
        condition = str(arm["condition"])
        for row in arm["items"]:
            opaque = str(row["opaque_item_id"])
            if opaque in condition_rows[condition]:
                duplicate_count += 1
            condition_rows[condition][opaque] = dict(row)
            worker_error_count += int(bool(row.get("error")))
            raw_rows.append(dict(row))
    expected_ids = {_opaque_item_id(str(case["item_id"])) for case in cases}
    complete = (
        set(condition_rows["OFF"]) == expected_ids
        and set(condition_rows["ON"]) == expected_ids
    )
    integrity = {
        "block_identity_exact": actual_block_identity == expected_block_identity,
        "exactly_one_off_and_one_on_per_item": complete and duplicate_count == 0,
        "worker_error_count_zero": worker_error_count == 0,
        **dict(closure_integrity),
    }
    scored = score_condition_rows(
        preregistration,
        cases,
        condition_rows,
        integrity_results=integrity,
    )
    scored["worker_error_count"] = worker_error_count
    scored["raw_rows"] = raw_rows
    return scored


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise EvaluationContractError(f"write-once path exists: {path}") from exc


def _bound_snapshot(sealed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "preregistration_raw_sha256": _raw_sha256(PREREG),
        "dataset_raw_sha256": _raw_sha256(DATASET),
        "candidate_binding_raw_sha256": _raw_sha256(BINDING),
        "execution_binding_v2_raw_sha256": _raw_sha256(EXECUTION_BINDING),
        "manifest_raw_sha256": _raw_sha256(MANIFEST),
        "off_git_blob_sha256": _sha256(
            _git_bytes(
                sealed["execution_binding"]["off"]["commit"],
                sealed["execution_binding"]["off"]["path"],
            )
        ),
        "on_git_blob_sha256": _sha256(
            _git_bytes(
                sealed["execution_binding"]["on"]["commit"],
                sealed["execution_binding"]["on"]["path"],
            )
        ),
        "evaluator_files": _validate_manifest_files(sealed["manifest"]),
    }


def _require_committed_bound_paths(sealed: Mapping[str, Any]) -> str:
    paths = sorted(
        {
            "data/eval/pattern_05_web_authority_preregister_v1.json",
            "data/eval/pattern_05_web_authority_dataset_v1.json",
            "data/eval/pattern_05_web_authority_candidate_binding_v1.json",
            "data/eval/pattern_05_web_authority_execution_binding_v2.json",
            "data/eval/pattern_05_web_authority_execution_manifest_v1.json",
            *sealed["manifest"]["evaluator_files"].keys(),
        }
    )
    for relative in paths:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if tracked.returncode != 0:
            raise EvaluationContractError(f"bound path is not tracked: {relative}")
    dirty = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", *paths],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise EvaluationContractError("bound paths must be committed and clean")
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvaluationContractError("cannot resolve sealed HEAD") from exc


def run() -> tuple[dict[str, Any], Path]:
    if any(path.exists() for path in (ATTEMPT, REPORT, FAILURE)):
        raise EvaluationContractError("attempt/report/failure exists; retry forbidden")
    sealed = load_sealed_inputs()
    sealed_commit = _require_committed_bound_paths(sealed)
    before = _bound_snapshot(sealed)
    requests = build_worker_requests(sealed["cases"])
    request_sha256 = [_sha256(_canonical_bytes(request)) for request in requests]
    _write_exclusive(
        ATTEMPT,
        {
            "schema_version": ATTEMPT_SCHEMA,
            "preregistration_id": sealed["preregistration"]["preregistration_id"],
            "sealed_commit": sealed_commit,
            "bound_snapshot": before,
            "request_count": len(requests),
            "request_sha256": request_sha256,
        },
    )
    arms: list[dict[str, Any]] = []
    try:
        execution_binding = sealed["execution_binding"]
        with tempfile.TemporaryDirectory(prefix="atanor-p05-off-") as off_tmp:
            with tempfile.TemporaryDirectory(prefix="atanor-p05-on-") as on_tmp:
                roots = {
                    "OFF": Path(off_tmp),
                    "ON": Path(on_tmp),
                }
                root_receipts = {
                    condition: _materialize_git_root(
                        execution_binding[condition.lower()]["commit"],
                        roots[condition],
                    )
                    for condition in ("OFF", "ON")
                }
                if (
                    root_receipts["OFF"]["candidate_sha256"]
                    != execution_binding["off"]["git_blob_sha256"]
                    or root_receipts["ON"]["candidate_sha256"]
                    != execution_binding["on"]["git_blob_sha256"]
                    or root_receipts["OFF"]["referent_resonance_sha256"]
                    != execution_binding["root_isolation"]["required_repo_import"][
                        "off_git_blob_sha256"
                    ]
                    or root_receipts["ON"]["referent_resonance_sha256"]
                    != execution_binding["root_isolation"]["required_repo_import"][
                        "on_git_blob_sha256"
                    ]
                ):
                    raise EvaluationContractError(
                        "materialized root differs from execution binding"
                    )
                for request in requests:
                    result = _run_worker(request, roots[request["condition"]])
                    _validate_worker_result(request, result)
                    arms.append(result)
        after = _bound_snapshot(sealed)
        closure = {
            "bound_files_same_before_after": before == after,
            "sealed_commit_still_head": _require_committed_bound_paths(sealed)
            == sealed_commit,
        }
        scored = score_arms(
            sealed["preregistration"],
            sealed["cases"],
            arms,
            closure_integrity=closure,
        )
        report = {
            "schema_version": REPORT_SCHEMA,
            "preregistration_id": sealed["preregistration"]["preregistration_id"],
            "sealed_commit": sealed_commit,
            "bound_snapshot": before,
            "isolated_root_receipts": root_receipts,
            "arms": arms,
            "scored": scored,
            "verdict": scored["outcome"],
            "production_default_changed": False,
            "claim_boundary": sealed["preregistration"]["claim_boundary"],
        }
        report["report_sha256"] = _sha256(_canonical_bytes(report))
        _write_exclusive(REPORT, report)
        return report, REPORT
    except Exception as exc:
        try:
            _write_exclusive(
                FAILURE,
                {
                    "schema_version": FAILURE_SCHEMA,
                    "preregistration_id": sealed["preregistration"][
                        "preregistration_id"
                    ],
                    "sealed_commit": sealed_commit,
                    "completed_block_count": len(arms),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[-2000:],
                },
            )
        except Exception as failure_exc:
            if hasattr(exc, "add_note"):
                exc.add_note(f"failure receipt write also failed: {failure_exc}")
        raise


def validate() -> dict[str, Any]:
    sealed = load_sealed_inputs()
    requests = build_worker_requests(sealed["cases"])
    return {
        "valid": True,
        "preregistration_id": sealed["preregistration"]["preregistration_id"],
        "case_count": len(sealed["cases"]),
        "block_counts": {
            request["block_id"]: len(request["items"]) for request in requests
        },
        "condition_counts": {
            condition: sum(
                len(request["items"])
                for request in requests
                if request["condition"] == condition
            )
            for condition in ("OFF", "ON")
        },
        "off_commit": sealed["execution_binding"]["off"]["commit"],
        "on_commit": sealed["execution_binding"]["on"]["commit"],
        "off_git_blob_sha256": sealed["execution_binding"]["off"][
            "git_blob_sha256"
        ],
        "on_git_blob_sha256": sealed["execution_binding"]["on"][
            "git_blob_sha256"
        ],
        "evaluator_files": sealed["evaluator_files"],
        "target_cases_executed": False,
        "attempt_created": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "run"))
    args = parser.parse_args(argv)
    if args.command == "validate":
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
        return 0
    report, destination = run()
    print(
        json.dumps(
            {"report": str(destination), "verdict": report["verdict"]},
            ensure_ascii=False,
        )
    )
    return 0 if report["verdict"] != "NO_GO" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise SystemExit(2)
