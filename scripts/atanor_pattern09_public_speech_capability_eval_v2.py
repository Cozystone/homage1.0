"""Verifier-hardened, one-shot v2 evaluator for Pattern #9.

The v1 evaluator, worker, preregistration, attempt, and raw report are immutable
forensic evidence.  This module reuses the frozen v1 worker and cohort while
giving the new preregistration its own write-once output paths.  It adds three
fail-closed controls:

* an arm binding must match the independently derived condition binding;
* the verifier replays ``validate_worker_result`` over every raw worker receipt;
* the materialized arm source is rebound after execution and the before/after
  bindings are retained in the report.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import BenchmarkEvidenceError
from scripts import atanor_pattern09_public_speech_capability_eval as _v1


if REPO != _v1.REPO:
    raise RuntimeError("Pattern #9 v2 repository root mismatch")
V1_PREREG = _v1.PREREG
V1_REPORT = _v1.REPORT
V1_ATTEMPT = _v1.ATTEMPT
PREREG = (
    REPO
    / "data"
    / "eval"
    / "atanor_pattern09_public_speech_capability_preregister_v2.json"
)
DATASET = _v1.DATASET
ADVERSARIAL_FIXTURE = (
    REPO / "data" / "eval" / "atanor_pattern09_verifier_adversarial_v2.json"
)
WORKER = _v1.WORKER
REPORT = _v1.ensure_safe_report_output(
    REPO,
    REPO
    / "reports"
    / "benchmarks"
    / "atanor_pattern09_public_speech_capability_v2_20260727.json",
)
ATTEMPT = REPORT.with_name(REPORT.stem + ".attempt.json")
FAILURE = REPORT.with_name(REPORT.stem + ".failure.json")

PREREG_SCHEMA = "atanor.pattern09-public-speech-preregister.v2"
PREREGISTRATION_ID = "pattern09-public-speech-capability-v2-20260727"
REPORT_SCHEMA = "atanor.pattern09-public-speech-report.v2"
ATTEMPT_SCHEMA = "atanor.pattern09-public-speech-attempt.v2"
FAILURE_SCHEMA = "atanor.pattern09-public-speech-failure.v2"
WORKER_REQUEST_SCHEMA = _v1.WORKER_REQUEST_SCHEMA
WORKER_RESULT_SCHEMA = _v1.WORKER_RESULT_SCHEMA
OFF_COMMIT = _v1.OFF_COMMIT
PREREG_SEAL_COMMIT = _v1.PREREG_SEAL_COMMIT
PUBLIC_TRUST = _v1.PUBLIC_TRUST
_CANDIDATE_PATHS = _v1._CANDIDATE_PATHS
_OFF_ORDER = _v1._OFF_ORDER
_ON_ORDER = _v1._ON_ORDER
_CASE_CONTRACT = _v1._CASE_CONTRACT
_EVALUATOR_PATHS = [
    "scripts/atanor_pattern09_public_speech_capability_eval_v2.py",
    "scripts/atanor_pattern09_public_speech_capability_eval.py",
    "scripts/atanor_pattern09_public_speech_capability_worker.py",
    "packages/eval_evidence/receipt.py",
    "scripts/tests/test_atanor_pattern09_public_speech_capability_eval_v2.py",
    "data/eval/atanor_pattern09_verifier_adversarial_v2.json",
    "docs/ATANOR_PATTERN_09_EVALUATOR_V2_PREREG_2026-07-27.md",
]
_DATASET_PREREG_PATHS = [
    "data/eval/atanor_pattern09_public_speech_capability_dataset_v1.json",
    "data/eval/atanor_pattern09_public_speech_capability_preregister_v2.json",
]
_EXECUTION_SEAL_PATHS = sorted(
    [*_CANDIDATE_PATHS, *_EVALUATOR_PATHS, *_DATASET_PREREG_PATHS]
)
_DURABLE_MODULES = {
    "surface_router": "apps/api/app/routers/surface_brain.py",
    "realization_planner": "packages/surface_brain/realization_planner.py",
}
_RECEIPT_FIELD = "source_rebind_receipt"
_RECEIPT_SCHEMA = "atanor.pattern09-arm-source-rebind.v2"
_V1_PREREGISTRATION_ID = "pattern09-public-speech-capability-v1-20260727"

bind_files = _v1.bind_files
canonical_json_bytes = _v1.canonical_json_bytes
_checksum = _v1._checksum
_sha = _v1._sha
_opaque_item_key = _v1._opaque_item_key
_bind_git_commit = _v1._bind_git_commit
_resolve_commit = _v1._resolve_commit

_V1_RUN = _v1.run
_V1_VERIFY = _v1.verify
_V1_MAIN = _v1.main
_V1_DRY_RUN = _v1.dry_run_record
_V1_VALIDATE_WORKER = _v1.validate_worker_result
_V1_SCORE_RESULTS = _v1.score_results
_V1_RUN_CONDITION = _v1._run_condition
_V1_TEMPORARY_ARM_SOURCE = _v1._temporary_arm_source

_ACTIVE_ARMS: dict[str, dict[str, Any]] = {}


def _strict_preregistration(path: Path = PREREG) -> tuple[dict[str, Any], str]:
    value = _v1._load(
        path.resolve(strict=True), "Pattern #9 v2 preregistration"
    )
    expected_fields = {
        "schema_version",
        "preregistration_id",
        "frozen_from",
        "supersedes",
        "claim_boundary",
        "sealed_dataset",
        "off_candidate",
        "on_candidate",
        "evaluator",
        "verifier_adversarial_fixture",
        "execution_seal_policy",
        "protocol",
        "scoring_policy",
        "metrics",
        "capability_lift_gates",
        "regression_gates",
        "integrity_gates",
        "outcome_rule",
        "rerun_policy",
        "limitations",
    }
    if frozenset(value) != expected_fields:
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 preregistration fields mismatch"
        )
    if (
        value.get("schema_version") != PREREG_SCHEMA
        or value.get("preregistration_id") != PREREGISTRATION_ID
        or value.get("frozen_from")
        != "docs/ATANOR_PATTERN_09_EVALUATOR_V2_PREREG_2026-07-27.md"
        or value.get("supersedes")
        != {
            "preregistration_id": _V1_PREREGISTRATION_ID,
            "raw_report_preserved": (
                "reports/benchmarks/"
                "atanor_pattern09_public_speech_capability_v1_20260727.json"
            ),
            "attempt_preserved": (
                "reports/benchmarks/"
                "atanor_pattern09_public_speech_capability_v1_20260727."
                "attempt.json"
            ),
            "v1_target_not_reused": True,
        }
    ):
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 preregistration identity drift"
        )
    baseline = _v1._load(V1_PREREG, "Pattern #9 v1 preregistration")
    frozen_fields = (
        "claim_boundary",
        "sealed_dataset",
        "off_candidate",
        "on_candidate",
        "protocol",
        "scoring_policy",
        "metrics",
        "capability_lift_gates",
        "regression_gates",
        "outcome_rule",
    )
    if any(value.get(field) != baseline.get(field) for field in frozen_fields):
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 frozen cohort/scoring drift"
        )
    evaluator = value.get("evaluator")
    if (
        not isinstance(evaluator, dict)
        or evaluator.get("paths") != _EVALUATOR_PATHS
        or evaluator.get("binding") != bind_files(REPO, _EVALUATOR_PATHS)
    ):
        raise BenchmarkEvidenceError("Pattern #9 v2 evaluator binding drift")
    fixture = value.get("verifier_adversarial_fixture")
    if (
        not isinstance(fixture, dict)
        or fixture.get("path")
        != "data/eval/atanor_pattern09_verifier_adversarial_v2.json"
        or fixture.get("raw_sha256") != _v1._raw_sha256(ADVERSARIAL_FIXTURE)
        or fixture.get("attack_count") != 3
    ):
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 adversarial fixture drift"
        )
    expected_seal_policy = {
        **baseline["execution_seal_policy"],
        "required_tracked_paths": _EXECUTION_SEAL_PATHS,
        "arm_binding_matches_condition": True,
        "raw_worker_receipt_revalidated": True,
        "post_execution_arm_rebind_required": True,
    }
    if value.get("execution_seal_policy") != expected_seal_policy:
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 execution seal policy drift"
        )
    expected_integrity = {
        **baseline["integrity_gates"],
        "arm_condition_source_binding": True,
        "worker_isolation_receipt_revalidated": True,
        "post_execution_source_rebind": True,
    }
    if value.get("integrity_gates") != expected_integrity:
        raise BenchmarkEvidenceError("Pattern #9 v2 integrity gates drift")
    expected_rerun = {
        **baseline["rerun_policy"],
        "superseded_v1_preregistration_not_reused": True,
    }
    if value.get("rerun_policy") != expected_rerun:
        raise BenchmarkEvidenceError("Pattern #9 v2 rerun policy drift")
    expected_limitations = [
        *baseline["limitations"],
        (
            "The v1 raw report and attempt remain forensic evidence and are "
            "not rewritten or reinterpreted as a valid capability seal."
        ),
        (
            "The v2 run reuses the same frozen local synthetic cohort and "
            "production candidate; only evaluator integrity changes."
        ),
        (
            "The evaluator remains local, unsigned, and non-independent; "
            "the new checks establish internal receipt consistency only."
        ),
    ]
    if value.get("limitations") != expected_limitations:
        raise BenchmarkEvidenceError("Pattern #9 v2 limitations drift")
    try:
        relative = path.resolve(strict=True).relative_to(
            REPO.resolve(strict=True)
        )
    except ValueError as exc:
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 preregistration outside repository"
        ) from exc
    return value, relative.as_posix()


def load_preregistration(
    path: Path = PREREG,
) -> tuple[dict[str, Any], str]:
    return _strict_preregistration(path)


def load_dataset(
    preregistration: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    return _v1.load_dataset(preregistration)


def build_worker_requests(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return _v1.build_worker_requests(preregistration, cases)


def _durable_worker_result(
    value: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["source_root"] = {
        "kind": "ephemeral_arm_root",
        "condition": request["condition"],
    }
    result["loaded_modules"] = dict(_DURABLE_MODULES)
    return result


def _validate_durable_worker_result(
    value: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("source_root")
        != {
            "kind": "ephemeral_arm_root",
            "condition": request["condition"],
        }
        or value.get("loaded_modules") != _DURABLE_MODULES
    ):
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 durable worker identity mismatch"
        )
    receipt = value.get(_RECEIPT_FIELD)
    if not isinstance(receipt, dict):
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 source rebind receipt missing"
        )
    replay = copy.deepcopy(dict(value))
    replay.pop(_RECEIPT_FIELD, None)
    with tempfile.TemporaryDirectory(
        prefix="atanor-pattern09-v2-revalidate-"
    ) as raw_root:
        root = Path(raw_root).resolve(strict=True)
        for relative in _DURABLE_MODULES.values():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"receipt-shape-replay\n")
        replay["source_root"] = str(root)
        replay["loaded_modules"] = {
            name: str((root / relative).resolve(strict=True))
            for name, relative in _DURABLE_MODULES.items()
        }
        _V1_VALIDATE_WORKER(replay, request, root)
    return dict(value)


def validate_worker_result(
    value: dict[str, Any],
    request: Mapping[str, Any],
    source_root: Path | None = None,
) -> dict[str, Any]:
    if source_root is None:
        return _validate_durable_worker_result(value, request)
    validated = _V1_VALIDATE_WORKER(value, request, source_root)
    durable = _durable_worker_result(validated, request)
    key = str(source_root.resolve(strict=True))
    state = _ACTIVE_ARMS.get(key)
    if state is None or state.get("condition") != request["condition"]:
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 active arm binding state missing"
        )
    state["worker_result"] = durable
    return durable


def _run_condition(
    request: Mapping[str, Any],
    source_root: Path,
    sealed_head: str,
    timeout: int = 1800,
) -> dict[str, Any]:
    compatibility_request = copy.deepcopy(dict(request))
    compatibility_request["preregistration_id"] = _V1_PREREGISTRATION_ID
    result = _V1_RUN_CONDITION(
        compatibility_request,
        source_root,
        sealed_head,
        timeout=timeout,
    )
    result["preregistration_id"] = request["preregistration_id"]
    return result


@contextlib.contextmanager
def _temporary_arm_source(
    condition: str,
    sealed_head: str,
) -> Iterator[Path]:
    with _V1_TEMPORARY_ARM_SOURCE(condition, sealed_head) as source_root:
        root = source_root.resolve(strict=True)
        key = str(root)
        before = bind_files(root, _CANDIDATE_PATHS)
        state: dict[str, Any] = {
            "condition": condition,
            "before": before,
            "worker_result": None,
        }
        _ACTIVE_ARMS[key] = state
        try:
            yield root
        finally:
            try:
                after = bind_files(root, _CANDIDATE_PATHS)
                receipt = {
                    "schema_version": _RECEIPT_SCHEMA,
                    "condition": condition,
                    "before": before,
                    "after": after,
                    "same_before_after": before == after,
                }
                worker_result = state.get("worker_result")
                if isinstance(worker_result, dict):
                    worker_result[_RECEIPT_FIELD] = receipt
                if before != after:
                    raise BenchmarkEvidenceError(
                        "Pattern #9 v2 arm source binding changed after execution"
                    )
            finally:
                _ACTIVE_ARMS.pop(key, None)


def _receipt_gates(arms: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    condition_binding = True
    worker_revalidated = True
    post_rebind = True
    for arm in arms:
        result = arm.get("result")
        receipt = (
            result.get(_RECEIPT_FIELD)
            if isinstance(result, dict)
            else None
        )
        expected_condition = arm.get("condition")
        if not isinstance(receipt, dict):
            condition_binding = False
            worker_revalidated = False
            post_rebind = False
            continue
        condition_binding = condition_binding and (
            receipt.get("condition") == expected_condition
            and arm.get("source_binding") == receipt.get("before")
        )
        worker_revalidated = worker_revalidated and (
            result.get("source_root")
            == {
                "kind": "ephemeral_arm_root",
                "condition": expected_condition,
            }
            and result.get("loaded_modules") == _DURABLE_MODULES
        )
        post_rebind = post_rebind and (
            receipt.get("schema_version") == _RECEIPT_SCHEMA
            and receipt.get("before") == receipt.get("after")
            and receipt.get("same_before_after") is True
        )
    return {
        "arm_condition_source_binding": condition_binding,
        "worker_isolation_receipt_revalidated": worker_revalidated,
        "post_execution_source_rebind": post_rebind,
    }


def score_results(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    arms: Sequence[Mapping[str, Any]],
    *,
    closure_integrity: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    scored = _V1_SCORE_RESULTS(
        preregistration,
        cases,
        arms,
        closure_integrity=closure_integrity,
    )
    gates = _receipt_gates(arms)
    scored["integrity_gate_results"].update(gates)
    scored["measurement_valid"] = all(
        scored["integrity_gate_results"].values()
    )
    if not scored["measurement_valid"]:
        scored["outcome"] = "NO_GO"
    scored["capability_lift_confirmed"] = (
        scored["outcome"] == "CAPABILITY_LIFT_CONFIRMED"
    )
    return scored


@contextlib.contextmanager
def _configured_v1() -> Iterator[None]:
    replacements = {
        "PREREG": PREREG,
        "DATASET": DATASET,
        "WORKER": WORKER,
        "REPORT": REPORT,
        "ATTEMPT": ATTEMPT,
        "FAILURE": FAILURE,
        "PREREG_SCHEMA": PREREG_SCHEMA,
        "PREREGISTRATION_ID": PREREGISTRATION_ID,
        "REPORT_SCHEMA": REPORT_SCHEMA,
        "ATTEMPT_SCHEMA": ATTEMPT_SCHEMA,
        "FAILURE_SCHEMA": FAILURE_SCHEMA,
        "_EVALUATOR_PATHS": _EVALUATOR_PATHS,
        "_DATASET_PREREG_PATHS": _DATASET_PREREG_PATHS,
        "_EXECUTION_SEAL_PATHS": _EXECUTION_SEAL_PATHS,
        "load_preregistration": load_preregistration,
        "validate_worker_result": validate_worker_result,
        "score_results": score_results,
        "_run_condition": _run_condition,
        "_temporary_arm_source": _temporary_arm_source,
    }
    original = {name: getattr(_v1, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(_v1, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(_v1, name, value)


def _verify_v2_receipts(path: Path) -> None:
    report = _v1._load(path.resolve(strict=True), "Pattern #9 v2 report")
    if (
        path.resolve(strict=True) != REPORT.resolve(strict=True)
        or report.get("schema_version") != REPORT_SCHEMA
        or report.get("checksum_sha256") != _checksum(report)
    ):
        raise BenchmarkEvidenceError(
            "Pattern #9 v2 report identity/checksum mismatch"
        )
    preregistration, _ = load_preregistration()
    _dataset, cases, _ = load_dataset(preregistration)
    sealed_head = _v1._validate_recorded_execution_seal(
        report.get("execution_seal")
    )
    expected_bindings = {
        "OFF": _bind_git_commit(OFF_COMMIT, _CANDIDATE_PATHS),
        "ON": _bind_git_commit(sealed_head, _CANDIDATE_PATHS),
    }
    requests = build_worker_requests(preregistration, cases)
    arms = report.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise BenchmarkEvidenceError("Pattern #9 v2 report arm census mismatch")
    for arm, request in zip(arms, requests):
        expected = expected_bindings[request["condition"]]
        if (
            arm.get("condition") != request["condition"]
            or arm.get("source_binding") != expected
        ):
            raise BenchmarkEvidenceError(
                "Pattern #9 v2 arm source binding/condition mismatch"
            )
        result = arm.get("result")
        if not isinstance(result, dict):
            raise BenchmarkEvidenceError(
                "Pattern #9 v2 raw worker result missing"
            )
        validate_worker_result(result, request)
        receipt = result.get(_RECEIPT_FIELD)
        if (
            not isinstance(receipt, dict)
            or receipt
            != {
                "schema_version": _RECEIPT_SCHEMA,
                "condition": request["condition"],
                "before": expected,
                "after": expected,
                "same_before_after": True,
            }
        ):
            raise BenchmarkEvidenceError(
                "Pattern #9 v2 post-execution source rebind mismatch"
            )


def run(
    preregistration_path: Path = PREREG,
) -> tuple[dict[str, Any], Path]:
    with _configured_v1():
        return _V1_RUN(preregistration_path)


def verify(path: Path = REPORT) -> dict[str, Any]:
    try:
        with _configured_v1():
            _verify_v2_receipts(path)
            return _V1_VERIFY(path)
    except (
        BenchmarkEvidenceError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return {
            "valid": False,
            "measurement_outcome": None,
            "capability_lift_established": False,
            "production_activation_authorized": False,
            "independent_evaluator": False,
            "findings": [str(exc)],
        }


def dry_run_record(
    preregistration: Mapping[str, Any],
    prereg_relative: str,
    cases: Sequence[Mapping[str, Any]],
    dataset_relative: str,
) -> dict[str, Any]:
    with _configured_v1():
        return _V1_DRY_RUN(
            preregistration,
            prereg_relative,
            cases,
            dataset_relative,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "run", "verify"))
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        preregistration, prereg_relative = load_preregistration(
            args.path or PREREG
        )
        _dataset, cases, dataset_relative = load_dataset(preregistration)
        print(
            json.dumps(
                dry_run_record(
                    preregistration,
                    prereg_relative,
                    cases,
                    dataset_relative,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "run":
        report, destination = run(args.path or PREREG)
        print(
            json.dumps(
                {
                    "report": str(destination),
                    "outcome": report["derived"]["outcome"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    result = verify(args.path or REPORT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
