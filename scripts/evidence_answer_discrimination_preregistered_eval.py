"""EAD-0 exposed, staging-only evidence/answer discrimination diagnostic.

This harness reconstructs 20 positive/wrong-source pairs and 12 unknown
negatives from the sealed LiveMemory v2 preregistration and replay-A/ON report.
It obtains only raw ACE answerability/support signals in two counterbalanced
fresh CPU workers, then evaluates one preregistered conjunction predicate via
deterministic grouped five-fold out-of-fold calibration.

This is an exposed mechanism diagnostic.  It does not modify or import the
live RealTimeThinker path, does not establish capability, and grants no
promotion authority.  ``run`` is write-once: the attempt tombstone is written
immediately before the first worker, and no mechanical retry is allowed.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
import unicodedata
from fractions import Fraction
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
from scripts.evidence_answer_discrimination_worker import (  # noqa: E402
    REQUEST_SCHEMA as WORKER_REQUEST_SCHEMA,
    RESULT_SCHEMA as WORKER_RESULT_SCHEMA,
)


PREREG_SCHEMA = "atanor.ead0-preregister.v1"
REPORT_SCHEMA = "atanor.ead0-report.v1"
ATTEMPT_SCHEMA = "atanor.ead0-attempt.v1"
FAILURE_SCHEMA = "atanor.ead0-failure.v1"
WORKER = REPO / "scripts" / "evidence_answer_discrimination_worker.py"
REPORTS = REPO / "reports" / "benchmarks"
DEFAULT_PREREG = REPO / "data" / "eval" / "evidence_answer_discrimination_preregister_v1.json"
_SOURCE_PATHS = [
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/evidence_answer_discrimination_preregistered_eval.py",
    "scripts/evidence_answer_discrimination_worker.py",
]
_SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")
_PREREG_FIELDS = frozenset(
    {
        "schema_version",
        "preregistration_id",
        "frozen_at",
        "claim_boundary",
        "sealed_inputs",
        "candidate",
        "protocol",
        "wrong_source_pairs",
        "unknown_negatives",
    }
)
_WORKER_REQUEST_ITEM_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "question",
        "evidence",
        "answer_start",
        "answer_end",
    }
)
_WORKER_RESULT_FIELDS = frozenset(
    {"schema_version", "device", "python_hash_seed", "versions", "items"}
)
_WORKER_RESULT_ITEM_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "p_ans",
        "p_support",
        "p_nei",
        "p_refute",
        "p_sup_net",
    }
)
_TOKEN_RE = __import__("re").compile(r"[^\W_]+", flags=__import__("re").UNICODE)
_ARTICLES = frozenset({"a", "an", "the"})
_CLAIM_LIMITATIONS = [
    "All cases are selected from the already exposed LiveMemory v2 result.",
    "This is a mechanism diagnostic, not fresh capability evidence.",
    "The evaluator, labels, inputs, and candidate share one local repository.",
    "No hidden holdout, independent evaluator, signature, or E5 attestation exists.",
    "POS candidate spans are oracle gold spans, so answer extraction is not measured.",
    "Negatives were selected post hoc from already exposed LiveMemory failures.",
    "Five OOF thresholds diagnose separability and do not define one deployable live threshold.",
    "The two-reader answerability/support composition is not the current live DoubtGate configuration.",
]


def _raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"bound input unreadable: {path.name}: {type(exc).__name__}"
        ) from exc
    return digest.hexdigest()


def _safe_repo_path(relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise BenchmarkEvidenceError("EAD-0 path must be a POSIX repository path")
    lexical = Path(relative)
    if lexical.is_absolute() or "." in lexical.parts or ".." in lexical.parts:
        raise BenchmarkEvidenceError("EAD-0 unsafe repository path")
    try:
        resolved = (REPO / lexical).resolve(strict=True)
        resolved.relative_to(REPO.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError("EAD-0 bound path missing or escaping") from exc
    if (REPO / lexical).is_symlink() or not resolved.is_file():
        raise BenchmarkEvidenceError("EAD-0 bound path must be a regular file")
    return resolved


def _strict_file(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(f"{label} unreadable") from exc
    return strict_json_bytes(payload, label=label)


def _find_exact_span(evidence: str, answer: str) -> tuple[int, int]:
    folded_evidence = evidence.casefold()
    folded_answer = answer.casefold()
    start = folded_evidence.find(folded_answer)
    if start < 0 or folded_evidence.find(folded_answer, start + 1) >= 0:
        raise BenchmarkEvidenceError(
            "EAD-0 answer must identify one unambiguous contiguous evidence span"
        )
    end = start + len(answer)
    if evidence[start:end].casefold() != folded_answer:
        raise BenchmarkEvidenceError("EAD-0 answer span boundary mismatch")
    return start, end


def _sealed_normalize_tokens(text: str) -> list[str]:
    """Exact LiveMemory-v2 evaluator normalization for source/gold binding."""
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return [
        token
        for token in _TOKEN_RE.findall(normalized)
        if token not in _ARTICLES
    ]


def _validate_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise BenchmarkEvidenceError(f"{label} must be lowercase SHA-256")


def _validate_preregistration(value: dict[str, Any]) -> dict[str, Any]:
    if frozenset(value) != _PREREG_FIELDS:
        raise BenchmarkEvidenceError("EAD-0 preregistration fields mismatch")
    if value.get("schema_version") != PREREG_SCHEMA:
        raise BenchmarkEvidenceError("EAD-0 preregistration schema mismatch")
    if value.get("preregistration_id") != "ead0-exposed-binding-diagnostic-v1-20260726":
        raise BenchmarkEvidenceError("EAD-0 preregistration ID mismatch")
    if value.get("frozen_at") != "2026-07-26T08:45:16Z":
        raise BenchmarkEvidenceError("EAD-0 freeze timestamp mismatch")
    boundary = value.get("claim_boundary")
    if boundary != {
        "measurement": "exposed_staging_only_evidence_answer_discrimination_diagnostic",
        "capability_claimed": False,
        "live_wiring_claimed": False,
        "limitations": _CLAIM_LIMITATIONS,
    }:
        raise BenchmarkEvidenceError("EAD-0 claim boundary must deny capability/live claims")

    sealed = value.get("sealed_inputs")
    if not isinstance(sealed, dict) or frozenset(sealed) != {
        "live_preregistration",
        "live_report",
    }:
        raise BenchmarkEvidenceError("EAD-0 sealed inputs mismatch")
    expected_inputs = {
        "live_preregistration": (
            "data/eval/live_memory_realtime_preregister_v2.json",
            "88fd657098c5c19e4da5f05ec7a9221f5376305b7b732f5ae539d6dfd1042a91",
        ),
        "live_report": (
            "reports/benchmarks/live_memory_realtime_lmrt-novel-single-hop-v2-20260726.json",
            "c409411e7748c8c5c216aaabd6ff61a932e9d518fa13f487871bcf1d563d3718",
        ),
    }
    for name, expected in expected_inputs.items():
        descriptor = sealed.get(name)
        if (
            not isinstance(descriptor, dict)
            or frozenset(descriptor) != {"path", "raw_sha256"}
            or (descriptor.get("path"), descriptor.get("raw_sha256")) != expected
        ):
            raise BenchmarkEvidenceError(f"EAD-0 {name} binding mismatch")

    candidate = value.get("candidate")
    if (
        not isinstance(candidate, dict)
        or frozenset(candidate)
        != {
            "paths",
            "content_sha256",
            "checkpoints",
            "checkpoint_raw_sha256",
        }
        or candidate.get("checkpoints")
        != {"answerability": "ace_hotpot.pt", "support": "ace_support.pt"}
        or candidate.get("checkpoint_raw_sha256")
        != {
            "ace_hotpot.pt": "87134bd43971cfd43f6ea488d9088d686bee70bf977dcf8be19190d4b6906137",
            "ace_support.pt": "eef7b80905fa3e2c065643fdb21e4caf78a9be5cefbceb07db832227c42b3448",
        }
        or candidate.get("content_sha256")
        != "02e30e438c333f5bbf5b05329bf4c6477c28ad2d8c9991893f42327604b87ee1"
    ):
        raise BenchmarkEvidenceError("EAD-0 candidate binding mismatch")
    paths = candidate.get("paths")
    if (
        not isinstance(paths, list)
        or not paths
        or paths != sorted(paths)
        or len(paths) != len(set(paths))
    ):
        raise BenchmarkEvidenceError("EAD-0 candidate paths invalid")

    protocol = value.get("protocol")
    if not isinstance(protocol, dict):
        raise BenchmarkEvidenceError("EAD-0 protocol invalid")
    if protocol.get("replays") != [
        {"id": "forward", "order": "forward"},
        {"id": "reverse", "order": "reverse"},
    ]:
        raise BenchmarkEvidenceError("EAD-0 replay order mismatch")
    if (
        protocol.get("device_policy") != "cpu_only"
        or protocol.get("python_hash_seed") != "0"
        or protocol.get("fold_count") != 5
        or protocol.get("predicate_family")
        != "p_ans>=tau_a AND p_sup_net>=tau_s"
    ):
        raise BenchmarkEvidenceError("EAD-0 fixed protocol mismatch")
    gates = protocol.get("gates")
    if gates != {
        "positive_accept_min": 17,
        "positive_total": 20,
        "aggregate_hard_negative_accept_max": 6,
        "aggregate_hard_negative_total": 32,
        "wrong_source_accept_max": 4,
        "wrong_source_total": 20,
        "unknown_accept_max": 2,
        "unknown_total": 12,
        "replay_exact_required": True,
        "worker_error_count_max": 0,
        "all_training_folds_feasible_required": True,
    }:
        raise BenchmarkEvidenceError("EAD-0 frozen gates mismatch")
    rerun = protocol.get("rerun_policy")
    if (
        not isinstance(rerun, dict)
        or rerun.get("result_run_limit") != 1
        or rerun.get("mechanical_retry_limit") != 0
        or rerun.get("post_result_tuning_prohibited") is not True
    ):
        raise BenchmarkEvidenceError("EAD-0 rerun policy mismatch")
    calibration = protocol.get("calibration")
    required_grids = {
        "p_ans_min_grid": [round(i * 0.05, 2) for i in range(21)],
        "p_sup_net_min_grid": [round(-1.0 + i * 0.05, 2) for i in range(41)],
    }
    if not isinstance(calibration, dict):
        raise BenchmarkEvidenceError("EAD-0 calibration invalid")
    for field, expected in required_grids.items():
        if calibration.get(field) != expected:
            raise BenchmarkEvidenceError(f"EAD-0 {field} grid mismatch")
    if calibration.get("selection_order") != [
        "training feasibility (POS accept rate >= 0.85 and hard-negative false accept rate <= 0.20), true before false",
        "balanced accuracy descending",
        "false accept count ascending",
        "positive accept count descending",
        "tau_a descending",
        "tau_s descending",
    ] or calibration.get("fallback") != (
        "If no training-grid point is feasible, apply the same total order to "
        "all grid points with feasibility false; the fold is marked "
        "infeasible and can never contribute to a GREEN result."
    ) or calibration.get("grouping") != (
        "question-pair plus connected components of repeated source_id or "
        "LiveMemory-normalized candidate answer; components assigned once to "
        "five frozen folds before signal observation"
    ) or calibration.get("fold_case_counts") != [10, 10, 11, 10, 11]:
        raise BenchmarkEvidenceError("EAD-0 calibration total order/fallback mismatch")

    pairs, unknown = value.get("wrong_source_pairs"), value.get("unknown_negatives")
    if not isinstance(pairs, list) or len(pairs) != 20:
        raise BenchmarkEvidenceError("EAD-0 requires 20 wrong-source pairs")
    if not isinstance(unknown, list) or len(unknown) != 12:
        raise BenchmarkEvidenceError("EAD-0 requires 12 unknown negatives")
    groups: set[str] = set()
    frozen_folds = {
        **{
            group: fold
            for fold, groups in {
                0: ("P13", "P16", "P19", "U07", "U02", "U03", "U11"),
                1: ("P02", "P07", "P18", "P10", "U08", "U12"),
                2: ("P03", "P05", "P09", "P01", "U01", "P08"),
                3: ("P06", "P17", "P04", "U04", "P12", "U10"),
                4: ("P11", "P14", "P15", "P20", "U05", "U06", "U09"),
            }.items()
            for group in groups
        }
    }
    for rows, fields, prefix in (
        (
            pairs,
            {"group_id", "fold", "positive_item_id", "wrong_source_id", "wrong_answer"},
            "P",
        ),
        (
            unknown,
            {"group_id", "fold", "unknown_item_id", "source_id", "answer"},
            "U",
        ),
    ):
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or frozenset(row) != fields:
                raise BenchmarkEvidenceError(f"EAD-0 {prefix} row {index} fields mismatch")
            group = row.get("group_id")
            if (
                group != f"{prefix}{index + 1:02d}"
                or group in groups
                or row.get("fold") != frozen_folds.get(group)
            ):
                raise BenchmarkEvidenceError(f"EAD-0 {prefix} row {index} grouping invalid")
            groups.add(group)
            identifier = row.get(
                "positive_item_id" if prefix == "P" else "unknown_item_id"
            )
            _validate_sha(identifier, f"EAD-0 {prefix} item ID")
    return value


def load_preregistration(path: Path) -> tuple[dict[str, Any], str]:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(REPO.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError(
            "EAD-0 preregistration must be a repository file"
        ) from exc
    if path.is_symlink() or relative != "data/eval/evidence_answer_discrimination_preregister_v1.json":
        raise BenchmarkEvidenceError("EAD-0 preregistration path identity mismatch")
    return _validate_preregistration(_strict_file(resolved, "EAD-0 preregistration")), relative


def _load_sealed_inputs(
    preregistration: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    loaded = []
    for name in ("live_preregistration", "live_report"):
        descriptor = preregistration["sealed_inputs"][name]
        path = _safe_repo_path(descriptor["path"])
        if _raw_sha256(path) != descriptor["raw_sha256"]:
            raise BenchmarkEvidenceError(f"EAD-0 sealed {name} raw SHA mismatch")
        loaded.append(_strict_file(path, f"EAD-0 sealed {name}"))
    live_prereg, live_report = loaded
    if live_prereg.get("preregistration_id") != "lmrt-novel-single-hop-v2-20260726":
        raise BenchmarkEvidenceError("EAD-0 sealed LiveMemory preregistration mismatch")
    if live_report.get("config", {}).get("preregistration_id") != live_prereg.get(
        "preregistration_id"
    ):
        raise BenchmarkEvidenceError("EAD-0 sealed LiveMemory report/prereg mismatch")
    return live_prereg, live_report


def _case_key(case: Mapping[str, Any]) -> str:
    # Only worker-visible bytes participate.  Internal kind/label/fold/group
    # and source metadata must not leak through this opaque identifier.
    return hashlib.sha256(
        canonical_json_bytes(
            {
                key: case[key]
                for key in (
                    "question",
                    "evidence",
                    "answer_start",
                    "answer_end",
                )
            }
        )
    ).hexdigest()


def reconstruct_cases(preregistration: Mapping[str, Any]) -> list[dict[str, Any]]:
    live_prereg, live_report = _load_sealed_inputs(preregistration)
    positives = {row["item_id"]: row for row in live_prereg["items"]}
    sources = {row["source_id"]: row for row in live_prereg["items"]}
    unknowns = {row["item_id"]: row for row in live_prereg["unknown_controls"]}
    on_rows = [
        row
        for row in live_report["items"]
        if row.get("metadata", {}).get("replay_id") == "replay_a"
        and row.get("metadata", {}).get("condition") == "ON"
    ]
    if len(on_rows) != 60:
        raise BenchmarkEvidenceError("EAD-0 expected exactly 60 sealed replay-A/ON rows")
    observed = {
        row["metadata"]["preregistered_item_id"]: row["metadata"] for row in on_rows
    }
    if len(observed) != 60:
        raise BenchmarkEvidenceError("EAD-0 sealed observation IDs are not unique")

    cases: list[dict[str, Any]] = []
    for selector in preregistration["wrong_source_pairs"]:
        own = positives.get(selector["positive_item_id"])
        wrong = sources.get(selector["wrong_source_id"])
        metadata = observed.get(selector["positive_item_id"])
        if own is None or wrong is None or metadata is None:
            raise BenchmarkEvidenceError("EAD-0 paired selector is not source-bound")
        if (
            metadata.get("normalized_exact_match") is not False
            or str(metadata.get("candidate_answer", "")).casefold()
            != selector["wrong_answer"].casefold()
            or _sealed_normalize_tokens(selector["wrong_answer"])
            != _sealed_normalize_tokens(wrong["gold"])
            or f"live:{selector['wrong_source_id']}" not in metadata.get("support", [])
            or own["source_id"] == selector["wrong_source_id"]
        ):
            raise BenchmarkEvidenceError("EAD-0 wrong-source selector drifted from sealed result")
        for kind, source, answer in (
            ("POS", own, own["gold"]),
            ("WRONG_SOURCE", wrong, selector["wrong_answer"]),
        ):
            start, end = _find_exact_span(source["fact"], answer)
            case = {
                "group_id": selector["group_id"],
                "kind": kind,
                "label": kind == "POS",
                "fold": selector["fold"],
                "question": own["question"],
                "evidence": source["fact"],
                "answer_start": start,
                "answer_end": end,
                "source_id": source["source_id"],
            }
            case["item_key"] = _case_key(case)
            cases.append(case)

    for selector in preregistration["unknown_negatives"]:
        unknown = unknowns.get(selector["unknown_item_id"])
        source = sources.get(selector["source_id"])
        metadata = observed.get(selector["unknown_item_id"])
        if unknown is None or source is None or metadata is None:
            raise BenchmarkEvidenceError("EAD-0 unknown selector is not source-bound")
        if (
            str(metadata.get("candidate_answer", "")).casefold()
            != selector["answer"].casefold()
            or f"live:{selector['source_id']}" not in metadata.get("support", [])
            or metadata.get("used_live") is not True
            or metadata.get("grounded") is not True
        ):
            raise BenchmarkEvidenceError("EAD-0 unknown selector drifted from sealed result")
        start, end = _find_exact_span(source["fact"], selector["answer"])
        case = {
            "group_id": selector["group_id"],
            "kind": "UNKNOWN",
            "label": False,
            "fold": selector["fold"],
            "question": unknown["question"],
            "evidence": source["fact"],
            "answer_start": start,
            "answer_end": end,
            "source_id": source["source_id"],
        }
        case["item_key"] = _case_key(case)
        cases.append(case)
    if (
        len(cases) != 52
        or len({case["item_key"] for case in cases}) != 52
        or sum(case["kind"] == "POS" for case in cases) != 20
        or sum(case["kind"] == "WRONG_SOURCE" for case in cases) != 20
        or sum(case["kind"] == "UNKNOWN" for case in cases) != 12
        or [sum(case["fold"] == fold for case in cases) for fold in range(5)]
        != [10, 10, 11, 10, 11]
    ):
        raise BenchmarkEvidenceError("EAD-0 reconstructed case census mismatch")
    for field, values in (
        ("source", [case["source_id"] for case in cases]),
        (
            "normalized answer",
            [
                tuple(
                    _sealed_normalize_tokens(
                        case["evidence"][
                            case["answer_start"] : case["answer_end"]
                        ]
                    )
                )
                for case in cases
            ],
        ),
    ):
        folds_by_value: dict[Any, set[int]] = {}
        for case, value in zip(cases, values):
            folds_by_value.setdefault(value, set()).add(case["fold"])
        if any(len(folds) != 1 for folds in folds_by_value.values()):
            raise BenchmarkEvidenceError(
                f"EAD-0 connected-component {field} leaked across folds"
            )
    return cases


def build_worker_request(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    order: str,
) -> dict[str, Any]:
    # Base order is label-independent: item_key hashes only worker-visible
    # content.  The second replay is the exact reverse of that fixed order.
    ordered = sorted(cases, key=lambda case: case["item_key"])
    if order == "reverse":
        ordered.reverse()
    elif order != "forward":
        raise BenchmarkEvidenceError("EAD-0 worker order invalid")
    items = []
    for index, case in enumerate(ordered):
        row = {
            "index": index,
            "item_key": case["item_key"],
            "question": case["question"],
            "evidence": case["evidence"],
            "answer_start": case["answer_start"],
            "answer_end": case["answer_end"],
        }
        if frozenset(row) != _WORKER_REQUEST_ITEM_FIELDS:
            raise BenchmarkEvidenceError("EAD-0 worker boundary fields drifted")
        items.append(row)
    return {
        "schema_version": WORKER_REQUEST_SCHEMA,
        "answerability_checkpoint": preregistration["candidate"]["checkpoints"][
            "answerability"
        ],
        "support_checkpoint": preregistration["candidate"]["checkpoints"]["support"],
        "device_policy": "cpu_only",
        "items": items,
    }


def dry_run_record(preregistration: Mapping[str, Any], relative: str) -> dict[str, Any]:
    cases = reconstruct_cases(preregistration)
    candidate = bind_files(REPO, preregistration["candidate"]["paths"])
    requests = [
        build_worker_request(preregistration, cases, replay["order"])
        for replay in preregistration["protocol"]["replays"]
    ]
    forbidden = {"label", "kind", "fold", "gate", "threshold", "gold"}
    if any(
        forbidden.intersection(row)
        for request in requests
        for row in request["items"]
    ):
        raise BenchmarkEvidenceError("EAD-0 labels/gates crossed worker boundary")
    return {
        "schema_version": "atanor.ead0-dry-run.v1",
        "candidate_executed": False,
        "live_path_imported": False,
        "source": bind_files(REPO, _SOURCE_PATHS),
        "candidate": candidate,
        "candidate_matches_preregistered_digest": candidate["content_sha256"]
        == preregistration["candidate"]["content_sha256"],
        "dataset": bind_files(REPO, [relative]),
        "case_counts": {"POS": 20, "WRONG_SOURCE": 20, "UNKNOWN": 12},
        "request_sha256": [
            hashlib.sha256(canonical_json_bytes(request)).hexdigest()
            for request in requests
        ],
        "worker_payload_contains_labels_or_gates": False,
        "claim_boundary": "exposed_staging_only_mechanism_diagnostic_no_capability",
    }


def _run_worker(request: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    environment["CUDA_VISIBLE_DEVICES"] = "-1"
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(WORKER)],
            cwd=REPO,
            env=environment,
            input=canonical_json_bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"EAD-0 worker launch failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2_000:]
        raise BenchmarkEvidenceError(
            f"EAD-0 worker exited {completed.returncode}: {detail}"
        )
    return strict_json_bytes(completed.stdout, label="EAD-0 worker result")


def _probability(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def validate_worker_result(
    value: dict[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    if frozenset(value) != _WORKER_RESULT_FIELDS:
        raise BenchmarkEvidenceError("EAD-0 worker result fields mismatch")
    if (
        value.get("schema_version") != WORKER_RESULT_SCHEMA
        or value.get("device") != "cpu"
        or value.get("python_hash_seed") != "0"
    ):
        raise BenchmarkEvidenceError("EAD-0 worker execution policy mismatch")
    versions = value.get("versions")
    if (
        not isinstance(versions, dict)
        or frozenset(versions) != {"python", "torch", "numpy"}
        or any(
            not isinstance(versions.get(field), str) or not versions[field].strip()
            for field in ("python", "torch", "numpy")
        )
    ):
        raise BenchmarkEvidenceError("EAD-0 worker environment versions invalid")
    rows = value.get("items")
    if not isinstance(rows, list) or len(rows) != len(request["items"]):
        raise BenchmarkEvidenceError("EAD-0 worker result count mismatch")
    for expected, (row, requested) in enumerate(zip(rows, request["items"])):
        if (
            not isinstance(row, dict)
            or frozenset(row) != _WORKER_RESULT_ITEM_FIELDS
            or row.get("index") != expected
            or row.get("item_key") != requested["item_key"]
        ):
            raise BenchmarkEvidenceError(f"EAD-0 worker row {expected} identity mismatch")
        for field in ("p_ans", "p_support", "p_nei", "p_refute"):
            if not _probability(row.get(field)):
                raise BenchmarkEvidenceError(f"EAD-0 worker row {expected} {field} invalid")
        if (
            not math.isfinite(float(row.get("p_sup_net", math.nan)))
            or not -1.0 <= float(row["p_sup_net"]) <= 1.0
            or abs(
                float(row["p_support"])
                + float(row["p_nei"])
                + float(row["p_refute"])
                - 1.0
            )
            > 1e-5
            or abs(
                float(row["p_sup_net"])
                - (float(row["p_support"]) - float(row["p_refute"]))
            )
            > 1e-12
        ):
            raise BenchmarkEvidenceError(f"EAD-0 worker row {expected} support vector invalid")
    return value


def _accept(signal: Mapping[str, Any], threshold: Sequence[float]) -> bool:
    return (
        float(signal["p_ans"]) >= threshold[0]
        and float(signal["p_sup_net"]) >= threshold[1]
    )


def _choose_threshold(
    rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
) -> tuple[tuple[float, float], bool]:
    positives = [row for row in rows if row["label"] is True]
    negatives = [row for row in rows if row["label"] is False]
    if not positives or not negatives:
        raise BenchmarkEvidenceError("EAD-0 calibration fold lacks both classes")
    best_key: tuple[Any, ...] | None = None
    best: tuple[float, float] | None = None
    for threshold in itertools.product(
        calibration["p_ans_min_grid"],
        calibration["p_sup_net_min_grid"],
    ):
        tp = sum(_accept(row, threshold) for row in positives)
        fp = sum(_accept(row, threshold) for row in negatives)
        feasible = (
            tp * 100 >= 85 * len(positives)
            and fp * 100 <= 20 * len(negatives)
        )
        # Exact rational comparison prevents platform-dependent float ties.
        balanced = Fraction(tp, len(positives)) + Fraction(
            len(negatives) - fp, len(negatives)
        )
        key = (feasible, balanced, -fp, tp, *threshold)
        if best_key is None or key > best_key:
            best_key, best = key, tuple(float(x) for x in threshold)
    if best is None:  # pragma: no cover - non-empty frozen grids
        raise BenchmarkEvidenceError("EAD-0 calibration grid is empty")
    return best, bool(best_key[0])


def score_signals(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    arms: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(arms) != 2:
        raise BenchmarkEvidenceError("EAD-0 requires exactly two replay arms")
    maps = [
        {row["item_key"]: row for row in arm["result"]["items"]} for arm in arms
    ]
    expected_keys = {case["item_key"] for case in cases}
    if any(set(mapping) != expected_keys for mapping in maps):
        raise BenchmarkEvidenceError("EAD-0 replay item census mismatch")
    signal_fields = ("p_ans", "p_support", "p_nei", "p_refute", "p_sup_net")
    replay_exact = all(
        all(maps[0][key][field] == maps[1][key][field] for field in signal_fields)
        for key in expected_keys
    )
    joined = [
        {
            **case,
            **{field: maps[0][case["item_key"]][field] for field in signal_fields},
        }
        for case in cases
    ]
    calibration = preregistration["protocol"]["calibration"]
    thresholds: list[dict[str, Any]] = []
    predictions: dict[str, bool] = {}
    for fold in range(5):
        train = [row for row in joined if row["fold"] != fold]
        threshold, training_feasible = _choose_threshold(train, calibration)
        thresholds.append(
            {
                "fold": fold,
                "p_ans_min": threshold[0],
                "p_sup_net_min": threshold[1],
                "training_feasible": training_feasible,
                "training_positive_count": sum(row["label"] is True for row in train),
                "training_negative_count": sum(row["label"] is False for row in train),
            }
        )
        for row in joined:
            if row["fold"] == fold:
                predictions[row["item_key"]] = _accept(row, threshold)
    if set(predictions) != expected_keys:
        raise BenchmarkEvidenceError("EAD-0 OOF prediction census mismatch")
    raw_rows = [
        {
            "item_key": row["item_key"],
            "group_id": row["group_id"],
            "kind": row["kind"],
            "fold": row["fold"],
            "source_id": row["source_id"],
            "question_sha256": hashlib.sha256(row["question"].encode()).hexdigest(),
            "evidence_sha256": hashlib.sha256(row["evidence"].encode()).hexdigest(),
            "answer_start": row["answer_start"],
            "answer_end": row["answer_end"],
            "signals": {field: row[field] for field in signal_fields},
            "accepted_oof": predictions[row["item_key"]],
        }
        for row in joined
    ]
    counts = {
        kind: sum(row["accepted_oof"] for row in raw_rows if row["kind"] == kind)
        for kind in ("POS", "WRONG_SOURCE", "UNKNOWN")
    }
    gates = preregistration["protocol"]["gates"]
    all_training_folds_feasible = all(
        row["training_feasible"] for row in thresholds
    )
    gate_results = {
        "positive_accept": counts["POS"] >= gates["positive_accept_min"],
        "aggregate_hard_negative": counts["WRONG_SOURCE"] + counts["UNKNOWN"]
        <= gates["aggregate_hard_negative_accept_max"],
        "wrong_source": counts["WRONG_SOURCE"] <= gates["wrong_source_accept_max"],
        "unknown": counts["UNKNOWN"] <= gates["unknown_accept_max"],
        "replay_exact": replay_exact,
        "worker_errors": True,
        "all_training_folds_feasible": all_training_folds_feasible,
    }
    return {
        "predicate_family": preregistration["protocol"]["predicate_family"],
        "calibration": thresholds,
        "raw_rows": raw_rows,
        "summary": {
            "positive_accept": counts["POS"],
            "positive_total": 20,
            "wrong_source_accept": counts["WRONG_SOURCE"],
            "wrong_source_total": 20,
            "unknown_accept": counts["UNKNOWN"],
            "unknown_total": 12,
            "aggregate_hard_negative_accept": counts["WRONG_SOURCE"]
            + counts["UNKNOWN"],
            "aggregate_hard_negative_total": 32,
            "replay_exact": replay_exact,
            "worker_error_count": 0,
            "all_training_folds_feasible": all_training_folds_feasible,
        },
        "gate_results": gate_results,
        "green": all(gate_results.values()),
        "claim_boundary": "exposed_staging_only_mechanism_diagnostic_no_capability",
    }


def _destinations(preregistration_id: str) -> tuple[Path, Path, Path]:
    stem = f"ead0_{preregistration_id}"
    return tuple(
        ensure_safe_report_output(REPO, REPORTS / f"{stem}{suffix}.json")
        for suffix in ("", ".attempt", ".failure")
    )  # type: ignore[return-value]


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError(f"EAD-0 write-once path exists: {path}") from exc


def _checksum(value: Mapping[str, Any]) -> str:
    detached = dict(value)
    detached.pop("checksum_sha256", None)
    return hashlib.sha256(canonical_json_bytes(detached)).hexdigest()


def run(preregistration_path: Path = DEFAULT_PREREG) -> tuple[dict[str, Any], Path]:
    preregistration, relative = load_preregistration(preregistration_path)
    destination, attempt_path, failure_path = _destinations(
        preregistration["preregistration_id"]
    )
    if any(path.exists() for path in (destination, attempt_path, failure_path)):
        raise BenchmarkEvidenceError(
            "EAD-0 report/attempt/failure already exists; retry is forbidden"
        )
    cases = reconstruct_cases(preregistration)
    source_before = bind_files(REPO, _SOURCE_PATHS)
    candidate_before = bind_files(REPO, preregistration["candidate"]["paths"])
    dataset_before = bind_files(REPO, [relative])
    if candidate_before["content_sha256"] != preregistration["candidate"]["content_sha256"]:
        raise BenchmarkEvidenceError("EAD-0 candidate bytes differ from preregistration")
    requests = [
        build_worker_request(preregistration, cases, replay["order"])
        for replay in preregistration["protocol"]["replays"]
    ]
    started_at = utc_now()
    _write_exclusive(
        attempt_path,
        {
            "schema_version": ATTEMPT_SCHEMA,
            "preregistration_id": preregistration["preregistration_id"],
            "started_at": started_at,
            "status": "started",
            "source_content_sha256": source_before["content_sha256"],
            "candidate_content_sha256": candidate_before["content_sha256"],
            "dataset_content_sha256": dataset_before["content_sha256"],
            "request_count": len(requests),
            "request_sha256": [
                hashlib.sha256(canonical_json_bytes(request)).hexdigest()
                for request in requests
            ],
        },
    )
    arms: list[dict[str, Any]] = []
    try:
        for replay, request in zip(preregistration["protocol"]["replays"], requests):
            result = validate_worker_result(
                _run_worker(request, preregistration["protocol"]["worker_timeout_seconds"]),
                request,
            )
            arms.append(
                {
                    "replay_id": replay["id"],
                    "order": replay["order"],
                    "request_sha256": hashlib.sha256(
                        canonical_json_bytes(request)
                    ).hexdigest(),
                    "result": result,
                }
            )
        source_after = bind_files(REPO, _SOURCE_PATHS)
        candidate_after = bind_files(REPO, preregistration["candidate"]["paths"])
        dataset_after = bind_files(REPO, [relative])
        if (
            source_before != source_after
            or candidate_before != candidate_after
            or dataset_before != dataset_after
        ):
            raise BenchmarkEvidenceError("EAD-0 bound bytes changed during run")
        derived = score_signals(preregistration, cases, arms)
        report = {
            "schema_version": REPORT_SCHEMA,
            "preregistration_id": preregistration["preregistration_id"],
            "started_at": started_at,
            "completed_at": utc_now(),
            "source": source_before,
            "candidate": candidate_before,
            "dataset": dataset_before,
            "sealed_input_raw_sha256": {
                name: descriptor["raw_sha256"]
                for name, descriptor in preregistration["sealed_inputs"].items()
            },
            "environment": {
                "harness": environment_record(),
                "worker_versions": [arm["result"]["versions"] for arm in arms],
            },
            "arms": arms,
            "derived": derived,
            "integrity": {
                "source_same_before_after": True,
                "candidate_same_before_after": True,
                "dataset_same_before_after": True,
                "write_once_attempt_present": True,
                "live_path_mutated": False,
                "production_authority": False,
                "capability_claimed": False,
                "limitations": preregistration["claim_boundary"]["limitations"],
            },
        }
        report["checksum_sha256"] = _checksum(report)
        _write_exclusive(destination, report)
        return report, destination
    except Exception as exc:
        try:
            _write_exclusive(
                failure_path,
                {
                    "schema_version": FAILURE_SCHEMA,
                    "preregistration_id": preregistration["preregistration_id"],
                    "started_at": started_at,
                    "failed_at": utc_now(),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[-2_000:],
                    "completed_arm_count": len(arms),
                },
            )
        except Exception as failure_error:
            if hasattr(exc, "add_note"):
                exc.add_note(f"failure receipt write failed: {failure_error}")
        raise


def verify(path: Path) -> dict[str, Any]:
    findings: list[str] = []
    try:
        report = _strict_file(path.resolve(strict=True), "EAD-0 report")
        expected_fields = {
            "schema_version",
            "preregistration_id",
            "started_at",
            "completed_at",
            "source",
            "candidate",
            "dataset",
            "sealed_input_raw_sha256",
            "environment",
            "arms",
            "derived",
            "integrity",
            "checksum_sha256",
        }
        if frozenset(report) != expected_fields or report.get("schema_version") != REPORT_SCHEMA:
            raise BenchmarkEvidenceError("EAD-0 report fields/schema mismatch")
        if report.get("checksum_sha256") != _checksum(report):
            raise BenchmarkEvidenceError("EAD-0 report checksum mismatch")
        preregistration, relative = load_preregistration(DEFAULT_PREREG)
        if report.get("preregistration_id") != preregistration["preregistration_id"]:
            raise BenchmarkEvidenceError("EAD-0 report preregistration mismatch")
        fixed_destination, _attempt, _failure = _destinations(
            preregistration["preregistration_id"]
        )
        if path.resolve(strict=True) != fixed_destination.resolve(strict=True):
            raise BenchmarkEvidenceError("EAD-0 report path identity mismatch")
        if report.get("source") != bind_files(REPO, _SOURCE_PATHS):
            raise BenchmarkEvidenceError("EAD-0 report source binding is not current")
        if report.get("candidate") != bind_files(REPO, preregistration["candidate"]["paths"]):
            raise BenchmarkEvidenceError("EAD-0 report candidate binding is not current")
        if report.get("dataset") != bind_files(REPO, [relative]):
            raise BenchmarkEvidenceError("EAD-0 report dataset binding is not current")
        expected_raw = {
            name: descriptor["raw_sha256"]
            for name, descriptor in preregistration["sealed_inputs"].items()
        }
        if report.get("sealed_input_raw_sha256") != expected_raw:
            raise BenchmarkEvidenceError("EAD-0 report sealed-input binding mismatch")
        expected_integrity = {
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "dataset_same_before_after": True,
            "write_once_attempt_present": True,
            "live_path_mutated": False,
            "production_authority": False,
            "capability_claimed": False,
            "limitations": preregistration["claim_boundary"]["limitations"],
        }
        if report.get("integrity") != expected_integrity:
            raise BenchmarkEvidenceError("EAD-0 report integrity/claim boundary mismatch")
        environment = report.get("environment")
        if (
            not isinstance(environment, dict)
            or frozenset(environment) != {"harness", "worker_versions"}
            or not isinstance(environment.get("harness"), dict)
            or not isinstance(environment.get("worker_versions"), list)
            or len(environment["worker_versions"]) != 2
        ):
            raise BenchmarkEvidenceError("EAD-0 report environment binding invalid")
        cases = reconstruct_cases(preregistration)
        arms = report.get("arms")
        if not isinstance(arms, list) or len(arms) != 2:
            raise BenchmarkEvidenceError("EAD-0 report arm count mismatch")
        for arm, replay in zip(arms, preregistration["protocol"]["replays"]):
            request = build_worker_request(preregistration, cases, replay["order"])
            if (
                arm.get("replay_id") != replay["id"]
                or arm.get("order") != replay["order"]
                or arm.get("request_sha256")
                != hashlib.sha256(canonical_json_bytes(request)).hexdigest()
            ):
                raise BenchmarkEvidenceError("EAD-0 report arm identity mismatch")
            validate_worker_result(arm.get("result"), request)
        if environment["worker_versions"] != [
            arm["result"]["versions"] for arm in arms
        ]:
            raise BenchmarkEvidenceError("EAD-0 worker version receipt mismatch")
        recomputed = score_signals(preregistration, cases, arms)
        if report.get("derived") != recomputed:
            raise BenchmarkEvidenceError("EAD-0 report derivation mismatch")
        _destination, attempt_path, failure_path = _destinations(
            preregistration["preregistration_id"]
        )
        attempt = _strict_file(attempt_path, "EAD-0 attempt tombstone")
        expected_requests = [
            hashlib.sha256(
                canonical_json_bytes(
                    build_worker_request(preregistration, cases, replay["order"])
                )
            ).hexdigest()
            for replay in preregistration["protocol"]["replays"]
        ]
        if (
            frozenset(attempt)
            != {
                "schema_version",
                "preregistration_id",
                "started_at",
                "status",
                "source_content_sha256",
                "candidate_content_sha256",
                "dataset_content_sha256",
                "request_count",
                "request_sha256",
            }
            or attempt.get("schema_version") != ATTEMPT_SCHEMA
            or attempt.get("preregistration_id") != preregistration["preregistration_id"]
            or attempt.get("started_at") != report.get("started_at")
            or attempt.get("status") != "started"
            or attempt.get("source_content_sha256") != report["source"]["content_sha256"]
            or attempt.get("candidate_content_sha256")
            != report["candidate"]["content_sha256"]
            or attempt.get("dataset_content_sha256") != report["dataset"]["content_sha256"]
            or attempt.get("request_count") != 2
            or attempt.get("request_sha256") != expected_requests
            or failure_path.exists()
        ):
            raise BenchmarkEvidenceError("EAD-0 attempt/failure receipt mismatch")
    except (BenchmarkEvidenceError, KeyError, TypeError, ValueError, OSError) as exc:
        findings.append(str(exc))
    return {
        "valid": not findings,
        "authenticity_established": False,
        "capability_established": False,
        "live_wiring_established": False,
        "findings": findings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("preregistration", nargs="?", type=Path, default=DEFAULT_PREREG)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("preregistration", nargs="?", type=Path, default=DEFAULT_PREREG)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        preregistration, relative = load_preregistration(args.preregistration)
        print(json.dumps(dry_run_record(preregistration, relative), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        report, destination = run(args.preregistration)
        print(
            json.dumps(
                {"report": str(destination), "derived": report["derived"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    result = verify(args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise SystemExit(2)
