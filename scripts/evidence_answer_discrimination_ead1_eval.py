"""Write-once EAD-1 model-free live-wiring evaluator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    environment_record,
    strict_json_bytes,
    utc_now,
)


PREREG_V1 = (
    REPO / "data" / "eval" / "evidence_answer_discrimination_ead1_preregister_v1.json"
)
PREREG_V2 = (
    REPO / "data" / "eval" / "evidence_answer_discrimination_ead1_preregister_v2.json"
)
PREREG = PREREG_V2
SCHEMA = "atanor.ead1-report.v1"


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        return strict_json_bytes(path.read_bytes(), label=label)
    except OSError as exc:
        raise BenchmarkEvidenceError(f"{label} unreadable") from exc


def _raw_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BenchmarkEvidenceError("EAD-1 bound lineage file unreadable") from exc


def _destinations(preregistration_id: str) -> tuple[Path, Path, Path]:
    stems = {
        "ead1-live-wiring-authority-v1-20260726": (
            "ead1_live_wiring_authority_v1_20260726"
        ),
        "ead1-live-wiring-authority-v2-20260726": (
            "ead1_live_wiring_authority_v2_20260726"
        ),
    }
    try:
        stem = stems[preregistration_id]
    except KeyError as exc:
        raise BenchmarkEvidenceError("EAD-1 destination identity mismatch") from exc
    report = ensure_safe_report_output(
        REPO, REPO / "reports" / "benchmarks" / f"{stem}.json"
    )
    return (
        report,
        report.with_name(report.stem + ".attempt.json"),
        report.with_name(report.stem + ".failure.json"),
    )


def load_preregistration(path: Path = PREREG) -> tuple[dict[str, Any], str]:
    value = _load(path.resolve(strict=True), "EAD-1 preregistration")
    base_fields = {
        "schema_version",
        "preregistration_id",
        "frozen_at",
        "time_budget",
        "claim_boundary",
        "production_contract",
        "candidate_paths",
        "source_paths",
        "pytest_nodes",
        "gates",
        "rerun_policy",
    }
    identity = (
        value.get("schema_version"),
        value.get("preregistration_id"),
    )
    v1_identity = (
        "atanor.ead1-preregister.v1",
        "ead1-live-wiring-authority-v1-20260726",
    )
    v2_identity = (
        "atanor.ead1-preregister.v2",
        "ead1-live-wiring-authority-v2-20260726",
    )
    expected_fields = base_fields | ({"lineage"} if identity == v2_identity else set())
    if frozenset(value) != expected_fields:
        raise BenchmarkEvidenceError("EAD-1 preregistration fields mismatch")
    if identity not in {v1_identity, v2_identity}:
        raise BenchmarkEvidenceError("EAD-1 preregistration identity mismatch")
    if value["production_contract"] != {
        "answerability_checkpoint": "ace_hotpot.pt",
        "support_checkpoint": "ace_support.pt",
        "answerability_threshold": 0.9,
        "support_net_threshold": 0.9,
        "predicate": "same_evidence_row(p_ans>=0.90 AND p_support-p_refute>=0.90)",
        "selection_identity": "producer_index_not_caller_title",
        "missing_or_ambiguous_identity": "fail_closed",
        "public_verified_metadata": "forbidden",
    }:
        raise BenchmarkEvidenceError("EAD-1 production contract drift")
    if value["gates"] != {
        "pytest_exit_code": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "candidate_same_before_after": True,
        "source_same_before_after": True,
        "dataset_same_before_after": True,
        "all_contract_checks_required": True,
    }:
        raise BenchmarkEvidenceError("EAD-1 gates drift")
    for field in ("candidate_paths", "source_paths", "pytest_nodes"):
        rows = value.get(field)
        if (
            not isinstance(rows, list)
            or not rows
            or not all(isinstance(row, str) and row for row in rows)
            or len(rows) != len(set(rows))
        ):
            raise BenchmarkEvidenceError(f"EAD-1 {field} invalid")
    if value["candidate_paths"] != sorted(value["candidate_paths"]):
        raise BenchmarkEvidenceError("EAD-1 candidate paths must be sorted")
    if value["source_paths"] != sorted(value["source_paths"]):
        raise BenchmarkEvidenceError("EAD-1 source paths must be sorted")
    if identity == v2_identity:
        lineage = value.get("lineage")
        expected_lineage = {
            "supersedes_preregistration_id": (
                "ead1-live-wiring-authority-v1-20260726"
            ),
            "superseded_preregistration_path": (
                "data/eval/evidence_answer_discrimination_ead1_preregister_v1.json"
            ),
            "superseded_preregistration_raw_sha256": (
                "29d7790a71cf548643e68fc4a0a7f003804e88668be325c18a95df71c0d6e271"
            ),
            "superseded_report_path": (
                "reports/benchmarks/ead1_live_wiring_authority_v1_20260726.json"
            ),
            "superseded_report_raw_sha256": (
                "6c764f555abb122ea5956c70e516367f0d59538eee001e29919f2f93ab339f72"
            ),
            "frozen_candidate_content_sha256": (
                "819e0ff07cfb968109d7d219e6bb86c35c9b2c21565af8263b13c3486d6f0425"
            ),
            "frozen_pytest_nodes_sha256": (
                "71379e18c9827df63b961e36cce055f3954349224c097f4d3090bac69db1036f"
            ),
            "allowed_evaluator_delta": (
                "_pytest_counts sums immediate testsuite children instead of "
                "reading the outer testsuites wrapper"
            ),
            "candidate_or_test_contract_change_allowed": False,
        }
        if lineage != expected_lineage:
            raise BenchmarkEvidenceError("EAD-1 retry lineage drift")
        if (
            _raw_sha256(PREREG_V1)
            != lineage["superseded_preregistration_raw_sha256"]
            or _raw_sha256(REPO / lineage["superseded_report_path"])
            != lineage["superseded_report_raw_sha256"]
        ):
            raise BenchmarkEvidenceError("EAD-1 retry lineage bytes drift")
        original = _load(PREREG_V1, "EAD-1 superseded preregistration")
        for field in ("production_contract", "candidate_paths", "pytest_nodes", "gates"):
            if value[field] != original[field]:
                raise BenchmarkEvidenceError(
                    f"EAD-1 retry changed frozen {field}"
                )
        if (
            hashlib.sha256(canonical_json_bytes(value["pytest_nodes"])).hexdigest()
            != lineage["frozen_pytest_nodes_sha256"]
            or bind_files(REPO, value["candidate_paths"])["content_sha256"]
            != lineage["frozen_candidate_content_sha256"]
        ):
            raise BenchmarkEvidenceError("EAD-1 retry candidate/test closure drift")
    try:
        relative = path.resolve(strict=True).relative_to(REPO.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError("EAD-1 preregistration escapes repository") from exc
    return value, relative


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError(f"EAD-1 write-once path exists: {path}") from exc


def _checksum(value: Mapping[str, Any]) -> str:
    detached = dict(value)
    detached.pop("checksum_sha256", None)
    return hashlib.sha256(canonical_json_bytes(detached)).hexdigest()


def _pytest_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root.findall("./testsuite"))
    else:
        raise BenchmarkEvidenceError("EAD-1 JUnit root must be testsuite/testsuites")
    if not suites:
        raise BenchmarkEvidenceError("EAD-1 JUnit contains no testsuite")

    def total(field: str) -> int:
        values: list[int] = []
        for suite in suites:
            if field not in suite.attrib:
                raise BenchmarkEvidenceError(
                    f"EAD-1 JUnit testsuite missing {field}"
                )
            value = int(suite.attrib[field])
            if value < 0:
                raise BenchmarkEvidenceError(
                    f"EAD-1 JUnit testsuite has negative {field}"
                )
            values.append(value)
        return sum(values)

    return {
        "tests": total("tests"),
        "failed": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
        "xfailed": 0,
        "xpassed": 0,
    }


def run(preregistration_path: Path = PREREG) -> tuple[dict[str, Any], Path]:
    prereg, relative = load_preregistration(preregistration_path)
    report_path, attempt_path, failure_path = _destinations(
        prereg["preregistration_id"]
    )
    if any(path.exists() for path in (report_path, attempt_path, failure_path)):
        raise BenchmarkEvidenceError("EAD-1 result path already exists; rerun forbidden")
    source_before = bind_files(REPO, prereg["source_paths"])
    candidate_before = bind_files(REPO, prereg["candidate_paths"])
    dataset_before = bind_files(REPO, [relative])
    started_at = utc_now()
    _write_exclusive(
        attempt_path,
        {
            "schema_version": "atanor.ead1-attempt.v1",
            "preregistration_id": prereg["preregistration_id"],
            "started_at": started_at,
            "source_content_sha256": source_before["content_sha256"],
            "candidate_content_sha256": candidate_before["content_sha256"],
            "dataset_content_sha256": dataset_before["content_sha256"],
            "pytest_nodes": prereg["pytest_nodes"],
        },
    )
    try:
        with tempfile.TemporaryDirectory(prefix="atanor-ead1-") as directory:
            junit = Path(directory) / "pytest.xml"
            env = dict(os.environ)
            env.update(
                {
                    "PYTHONHASHSEED": "0",
                    "CUDA_VISIBLE_DEVICES": "-1",
                    "ATANOR_DISABLE_DAEMON_SELF_HEAL": "1",
                    "ATANOR_WEB_SEED_FEEDER_ON_TICK": "0",
                }
            )
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "--disable-warnings",
                    "--junitxml",
                    str(junit),
                    *prereg["pytest_nodes"],
                ],
                cwd=REPO,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600,
                check=False,
            )
            counts = _pytest_counts(junit)
            output_tail = (process.stdout + "\n" + process.stderr)[-4000:]
        source_after = bind_files(REPO, prereg["source_paths"])
        candidate_after = bind_files(REPO, prereg["candidate_paths"])
        dataset_after = bind_files(REPO, [relative])
        gate_results = {
            "pytest_exit_code": process.returncode == 0,
            "failed": counts["failed"] == 0,
            "errors": counts["errors"] == 0,
            "skipped": counts["skipped"] == 0,
            "xfailed": counts["xfailed"] == 0,
            "xpassed": counts["xpassed"] == 0,
            "candidate_same_before_after": candidate_before == candidate_after,
            "source_same_before_after": source_before == source_after,
            "dataset_same_before_after": dataset_before == dataset_after,
            "all_contract_checks_required": counts["tests"] > 0,
        }
        report = {
            "schema_version": SCHEMA,
            "preregistration_id": prereg["preregistration_id"],
            "started_at": started_at,
            "completed_at": utc_now(),
            "source": source_before,
            "candidate": candidate_before,
            "dataset": dataset_before,
            "environment": environment_record(),
            "pytest": {
                "nodes": prereg["pytest_nodes"],
                "returncode": process.returncode,
                "counts": counts,
                "output_tail": output_tail,
            },
            "gate_results": gate_results,
            "green": all(gate_results.values()),
            "claim_boundary": prereg["claim_boundary"],
        }
        report["checksum_sha256"] = _checksum(report)
        _write_exclusive(report_path, report)
        return report, report_path
    except Exception as exc:
        try:
            _write_exclusive(
                failure_path,
                {
                    "schema_version": "atanor.ead1-failure.v1",
                    "preregistration_id": prereg["preregistration_id"],
                    "started_at": started_at,
                    "failed_at": utc_now(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[-2000:],
                },
            )
        except Exception:
            pass
        raise


def verify(path: Path | None = None) -> dict[str, Any]:
    findings: list[str] = []
    report_green = False
    try:
        if path is None:
            path = _destinations(
                "ead1-live-wiring-authority-v2-20260726"
            )[0]
        report = _load(path.resolve(strict=True), "EAD-1 report")
        prereg_paths = {
            "ead1-live-wiring-authority-v1-20260726": PREREG_V1,
            "ead1-live-wiring-authority-v2-20260726": PREREG_V2,
        }
        try:
            prereg_path = prereg_paths[report.get("preregistration_id")]
        except KeyError as exc:
            raise BenchmarkEvidenceError(
                "EAD-1 report preregistration identity mismatch"
            ) from exc
        prereg, relative = load_preregistration(prereg_path)
        report_path, attempt_path, failure_path = _destinations(
            prereg["preregistration_id"]
        )
        if path.resolve(strict=True) != report_path.resolve(strict=True):
            raise BenchmarkEvidenceError("EAD-1 report path identity mismatch")
        if report.get("schema_version") != SCHEMA:
            raise BenchmarkEvidenceError("EAD-1 report schema mismatch")
        if report.get("checksum_sha256") != _checksum(report):
            raise BenchmarkEvidenceError("EAD-1 report checksum mismatch")
        if report.get("source") != bind_files(REPO, prereg["source_paths"]):
            raise BenchmarkEvidenceError("EAD-1 source no longer current")
        if report.get("candidate") != bind_files(REPO, prereg["candidate_paths"]):
            raise BenchmarkEvidenceError("EAD-1 candidate no longer current")
        if report.get("dataset") != bind_files(REPO, [relative]):
            raise BenchmarkEvidenceError("EAD-1 dataset no longer current")
        if report.get("green") is not all(report.get("gate_results", {}).values()):
            raise BenchmarkEvidenceError("EAD-1 GREEN derivation mismatch")
        if not attempt_path.is_file() or failure_path.exists():
            raise BenchmarkEvidenceError("EAD-1 attempt/failure receipt mismatch")
        report_green = bool(report.get("green"))
    except (BenchmarkEvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        findings.append(str(exc))
    return {
        "valid": not findings,
        "live_wiring_mechanism_established": not findings
        and report_green,
        "model_signal_measured": False,
        "capability_established": False,
        "authenticity_established": False,
        "findings": findings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "run", "verify"))
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        prereg, relative = load_preregistration(args.path or PREREG)
        value = {
            "valid": True,
            "preregistration_id": prereg["preregistration_id"],
            "source": bind_files(REPO, prereg["source_paths"]),
            "candidate": bind_files(REPO, prereg["candidate_paths"]),
            "dataset": bind_files(REPO, [relative]),
            "candidate_executed": False,
        }
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        report, destination = run(args.path or PREREG)
        print(json.dumps({"report": str(destination), "green": report["green"]}))
        return 0 if report["green"] else 2
    result = verify(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise SystemExit(2)
