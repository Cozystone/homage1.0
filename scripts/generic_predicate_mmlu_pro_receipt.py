"""Paired offline counterfactual evaluation of the generic-predicate lane.

This evaluator uses the exposed, fixed 40-item MMLU-Pro ``slice_5`` only after
an explicit Stage 5 receipt has passed.  It is development-only evidence.

OFF is the direct declared baseline answer.  ON first obtains that same
baseline answer and then, evaluator-side only, substitutes a generic-predicate
choice if and only if the synchronous generic pipeline fires and its proof
receipt verifies again.  The substitution is never returned to a live answer
surface and establishes no live answer authority.

Gold and category metadata are excluded from worker arguments.  This is
logical argument separation only: evaluator and worker share a local
filesystem and no OS sandbox proves that gold was unreadable to the worker.

The final receipt retains proof and replay digests, flags, and scored outcomes,
not complete proof/replay payloads.  A current validator can rescore the fixed
gold labels, but cannot independently re-run proof verification or reverse
replay from the receipt alone.  Therefore this artifact cannot be sealed,
promotional, E4, E5, independent, or externally authenticated evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    strict_json_bytes,
    write_manifest_exclusive,
)
from scripts import deliberator_benchmark_receipt as bench  # noqa: E402
from scripts import science_stage_mmlu_pro_receipt as mmlu  # noqa: E402


SCHEMA_VERSION = "atanor.generic-predicate-mmlu-pro-paired-dev-receipt.v1"
EVIDENCE_KIND = (
    "strict_self_measured_exposed_mmlu_pro_offline_counterfactual_receipt"
)
FROZEN_CANDIDATE_COMMIT = "1399eec46dd3786caf95edfc083ae395888c8277"
STAGE5_SCHEMA_VERSION = (
    "atanor.a2.stage5.source-separated-self-measurement.v1"
)
EXPECTED_STAGE5_RED_SHA256 = (
    "c85461625cc22af59adbacffc2a066ec183277d998252f3b6f5dbb66027fc6ed"
)
TRUSTED_STAGE5_GREEN_SHA256 = frozenset()
WORKER_TIMEOUT_SECONDS = 7200
EXPECTED_ITEMS = 40
CLAIMS_CLASSIFICATION = (
    "exposed_mmlu_pro_slice5_offline_counterfactual_development_only"
)
DATASET_PATH = mmlu.DATASET_PATH
EXPECTED_DATASET_SHA256 = mmlu.EXPECTED_DATASET_SHA256
GPQA_PATH = "data/benchmarks/gpqa/gpqa_diamond.csv"
EXPECTED_GPQA_SHA256 = (
    "41d1213cd7a4998605a26c2798500652572007161b3a92817ba46b35befcd305"
)
DEFAULT_OUTPUT = (
    REPO
    / "reports"
    / "benchmarks"
    / "generic_predicate_mmlu_pro_stage6_v1.json"
)

SOURCE_PATHS = (
    "packages/eval_evidence/receipt.py",
    "scripts/atanor_a2_stage5_fresh_holdout.py",
    "scripts/deliberator_benchmark_receipt.py",
    "scripts/generic_predicate_mmlu_pro_receipt.py",
    "scripts/science_stage_e4_receipt.py",
    "scripts/science_stage_mmlu_pro_receipt.py",
)
STAGE5_CANDIDATE_PATHS = (
    "packages/cognitive_core/canonical.py",
    "packages/graph_scale/graph_paths.py",
    "packages/graph_scale/sharded_term_dict.py",
    "packages/graph_scale/triple_store.py",
    "packages/reasoning_vm/deliberator/relation_role_extractor.py",
    "packages/reasoning_vm/deliberator/generic_predicate_socket.py",
    "packages/reasoning_vm/deliberator/generic_predicate_goal.py",
    "packages/reasoning_vm/deliberator/generic_predicate_staging.py",
)
EXPLICIT_CANDIDATE_CONTROLLERS = (
    "packages/__init__.py",
    "packages/cognitive_core/__init__.py",
    "packages/cognitive_core/adapters.py",
    "packages/cognitive_core/canonical.py",
    "packages/cognitive_core/chat_shadow.py",
    "packages/cognitive_core/contracts.py",
    "packages/cognitive_core/cycle.py",
    "packages/cognitive_core/cycle_ledger.py",
    "packages/cognitive_core/replay.py",
    "packages/cognitive_core/shadow.py",
    "packages/evolution/rational_evolver.py",
    "packages/reasoning_vm/__init__.py",
    "packages/reasoning_vm/deduction.py",
    "packages/reasoning_vm/quantity.py",
    "packages/reasoning_vm/science_candidate.py",
    "packages/reasoning_vm/science_exam.py",
    "packages/reasoning_vm/science_route.py",
    "packages/reasoning_vm/science_staging.py",
    "packages/reasoning_vm/deliberator/__init__.py",
    "packages/reasoning_vm/deliberator/back_chain.py",
    "packages/reasoning_vm/deliberator/generic_predicate_goal.py",
    "packages/reasoning_vm/deliberator/generic_predicate_shadow.py",
    "packages/reasoning_vm/deliberator/generic_predicate_socket.py",
    "packages/reasoning_vm/deliberator/generic_predicate_staging.py",
    "packages/reasoning_vm/deliberator/reasoner.py",
    "packages/reasoning_vm/deliberator/relation_role_extractor.py",
    "packages/reasoning_vm/deliberator/science_goal.py",
)
FROZEN_CANDIDATE_EXTRA_PATHS = (
    "packages/__init__.py",
    "packages/cognitive_core/__init__.py",
    "packages/cognitive_core/adapters.py",
    "packages/cognitive_core/canonical.py",
    "packages/cognitive_core/chat_shadow.py",
    "packages/cognitive_core/contracts.py",
    "packages/cognitive_core/cycle.py",
    "packages/cognitive_core/cycle_ledger.py",
    "packages/cognitive_core/replay.py",
    "packages/cognitive_core/shadow.py",
    "packages/evolution/rational_evolver.py",
    "scripts/benchmark_openbook.py",
)
REQUIRED_CANDIDATE_BINDINGS = tuple(
    sorted(
        {
            *STAGE5_CANDIDATE_PATHS,
            *EXPLICIT_CANDIDATE_CONTROLLERS,
            *FROZEN_CANDIDATE_EXTRA_PATHS,
        }
    )
)
STAGE_ROOTS = (
    "data/graph_scale/staging_b1_wikidata",
    "data/graph_scale/staging_s1_wikidata_literals",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "protocol",
        "claims",
        "frozen_candidate",
        "stage5_prerequisite",
        "source",
        "candidate",
        "dataset",
        "stage",
        "baseline_store",
        "selection",
        "gpqa_blocker",
        "metrics",
        "items",
        "integrity",
        "manifest_checksum_sha256",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "classification",
        "development_only",
        "offline_counterfactual_only",
        "live_answer_authority",
        "counterfactual_policy_evaluated",
        "sealed",
        "promotion_allowed",
        "e4_claimed",
        "e5_claimed",
        "benchmark_capability_claimed",
        "independent",
        "externally_signed",
        "external_authenticity_established",
        "production_authority",
        "firing_is_correctness",
        "proof_verification_is_benchmark_correctness",
        "gold_filesystem_isolation_established",
        "independent_proof_reverification_available",
        "independent_replay_reverification_available",
        "gpqa_accuracy_claimed",
    }
)
_GENERIC_FIELDS = frozenset(
    {
        "eligible",
        "role_extracted",
        "context_ready",
        "compiled",
        "engine_called",
        "fired",
        "proof_verified",
        "grounded",
        "status",
        "reason",
        "error_kind",
        "prepared_input_digest_sha256",
        "prepared_choices_digest_sha256",
        "role_receipt_digest_sha256",
        "context_digest_sha256",
        "compiler_receipt_digest_sha256",
        "proof_decision_digest_sha256",
        "proof_receipt_digest_sha256",
        "choice_key",
        "answer_authority_established",
    }
)
_CONDITION_FIELDS = frozenset(
    {
        "baseline_choice_key",
        "baseline_choice_digest_sha256",
        "baseline_mode",
        "baseline_semantic_digest_sha256",
        "live_choice_key",
        "live_semantic_digest_sha256",
        "counterfactual_choice_key",
        "counterfactual_choice_digest_sha256",
        "counterfactual_override_applied",
        "generic",
        "condition_semantic_digest_sha256",
    }
)
_STAGE5_ROOT_FIELDS = frozenset(
    {
        "authority_disclaimer",
        "dataset",
        "execution_disclosure",
        "failures",
        "filesystem_delta",
        "frozen_candidate",
        "gate_pass",
        "gates",
        "measurement_class",
        "metrics",
        "replay",
        "schema_version",
        "sources",
    }
)
_STAGE5_METRIC_FIELDS = frozenset(
    {
        "bounded_context_failures",
        "bounded_contexts_checked",
        "compile_coverage",
        "compile_coverage_rate",
        "critical_source_digest_no_write_delta",
        "deterministic_replay_equal",
        "exact_choice_key",
        "filesystem_no_write_delta",
        "invariance_failures",
        "invariance_variants_checked",
        "mutation_rejection_checked",
        "mutation_rejection_failures",
        "negative_final_firing",
        "negative_total",
        "positive_exact_subject_predicate",
        "positive_exact_subject_predicate_rate",
        "positive_total",
        "proof_verified_and_grounded",
        "proof_verified_and_grounded_rate",
        "provenance_pid_separation_checked",
        "provenance_pid_separation_failures",
        "wrong_compile",
    }
)
_STAGE5_GATE_FIELDS = frozenset(
    {
        "bounded_rows",
        "choice_order_distractor_goal_digest_invariance",
        "compile_coverage",
        "deterministic_replay",
        "filesystem_no_write_delta",
        "mutation_rejection",
        "negative_final_firing_zero",
        "positive_exact_subject_predicate",
        "proof_verified_grounded",
        "provenance_pid_separation",
        "source_candidate_dataset_digests_present",
        "wrong_compile_zero",
    }
)
_STAGE5_DATASET_FIELDS = frozenset(
    {
        "answer_position_counts",
        "candidate_input_path",
        "candidate_input_sha256",
        "evaluator_expected_path",
        "evaluator_expected_sha256",
        "invariance_variant_count",
        "negative_category_counts",
        "negative_count",
        "positive_count",
        "predicate_counts",
        "salt",
    }
)
_STAGE5_SOURCE_FIELDS = frozenset(
    {
        "critical_source_digests_after",
        "critical_source_digests_before",
        "source_binding_digest_sha256",
        "stage_bindings",
    }
)
_STAGE5_REPLAY_FIELDS = frozenset(
    {
        "byte_equal",
        "run1_path",
        "run1_sha256",
        "run2_path",
        "run2_sha256",
    }
)
_STAGE5_FILESYSTEM_FIELDS = frozenset(
    {
        "after_file_count",
        "after_inventory_sha256",
        "before_file_count",
        "before_inventory_sha256",
        "changed",
    }
)
_STAGE5_EXECUTION_DISCLOSURE_FIELDS = frozenset(
    {
        "candidate_changed",
        "candidate_input_sha256_verified",
        "dataset_regenerated",
        "dataset_resampled",
        "evaluator_expected_sha256_verified",
        "initial_candidate_calls",
        "initial_incident_path",
        "initial_incident_sha256",
        "plumbing_change",
        "resumed_from_exact_existing_artifacts",
    }
)
_STAGE5_BINDING_FIELDS = frozenset(
    {
        "artifact_identity_digest_sha256",
        "descriptor_name",
        "index_generation",
        "qid_pid_sidecar_digest_sha256",
        "qid_pid_sidecar_record_format",
        "qid_pid_sidecar_records",
        "role",
        "root",
        "row_count",
        "source_digest_sha256",
        "source_registry_name",
        "stage_digest_sha256",
        "stage_id",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "ordinal",
        "category",
        "primary_execution_order",
        "replay_execution_order",
        "conditions",
        "outcomes",
        "transition",
        "replay",
        "gold_absent_from_candidate_arguments",
    }
)
_OUTCOME_FIELDS = frozenset(
    {
        "baseline_correct",
        "live_off_correct",
        "live_on_correct",
        "counterfactual_on_correct",
        "generic_wrong_fire",
        "regression",
        "win",
    }
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise BenchmarkEvidenceError("metric denominator must be positive")
    return round(numerator / denominator, 12)


def _choice_digest(choice: str | None) -> str | None:
    return None if choice is None else _sha256(choice.encode("utf-8"))


def _checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _repo_relative_file(path: Path, *, repo_root: Path = REPO) -> str:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(repo_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError(
            "Stage 5 receipt must be a repository-local regular file"
        ) from exc
    if path.is_symlink() or not resolved.is_file():
        raise BenchmarkEvidenceError("Stage 5 receipt is not a regular file")
    return relative.as_posix()


def _frozen_candidate_paths(
    *, repo_root: Path = REPO
) -> tuple[str, ...]:
    raw = _git_bytes(
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        FROZEN_CANDIDATE_COMMIT,
        "--",
        repo_root=repo_root,
    )
    try:
        tree_paths = {
            entry.decode("utf-8")
            for entry in raw.split(b"\0")
            if entry
        }
    except UnicodeError as exc:
        raise BenchmarkEvidenceError(
            "candidate freeze tree paths are not UTF-8"
        ) from exc
    package_paths = {
        relative
        for relative in tree_paths
        if relative.endswith(".py")
        and relative.startswith(
            ("packages/reasoning_vm/", "packages/graph_scale/")
        )
        and "tests" not in PurePosixPath(relative).parts
        and "__pycache__" not in PurePosixPath(relative).parts
    }
    explicit = {
        *EXPLICIT_CANDIDATE_CONTROLLERS,
        *FROZEN_CANDIDATE_EXTRA_PATHS,
    }
    if not explicit.issubset(tree_paths):
        missing = sorted(explicit - tree_paths)
        raise BenchmarkEvidenceError(
            f"explicit candidate controller absent from freeze: {missing}"
        )
    paths = tuple(sorted(package_paths | explicit))
    if not paths or len(paths) != len(set(paths)):
        raise BenchmarkEvidenceError(
            "frozen candidate inventory is empty or ambiguous"
        )
    return paths


def _files_under(
    relative_roots: Sequence[str], *, repo_root: Path = REPO
) -> tuple[str, ...]:
    paths: list[str] = []
    for relative_root in relative_roots:
        root = repo_root / relative_root
        if not root.is_dir() or root.is_symlink():
            raise BenchmarkEvidenceError(
                f"bound directory unavailable or linked: {relative_root}"
            )
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise BenchmarkEvidenceError(
                    f"linked bound entry is forbidden: {path}"
                )
            if path.is_file():
                paths.append(path.relative_to(repo_root).as_posix())
    if not paths:
        raise BenchmarkEvidenceError("bound directory scope is empty")
    return tuple(paths)


def _store_paths(
    store_name: str, *, repo_root: Path = REPO
) -> tuple[str, ...]:
    if (
        not store_name
        or "/" in store_name
        or "\\" in store_name
        or ".." in store_name
    ):
        raise BenchmarkEvidenceError("baseline store name is unsafe")
    return _files_under(
        (f"data/graph_scale/{store_name}",), repo_root=repo_root
    )


def _git_bytes(
    *arguments: str, repo_root: Path = REPO
) -> bytes:
    try:
        return subprocess.check_output(
            ("git", *arguments),
            cwd=repo_root,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BenchmarkEvidenceError(
            "candidate freeze could not be resolved"
        ) from exc


def _frozen_candidate_scope(
    *, repo_root: Path = REPO
) -> dict[str, Any]:
    resolved = _git_bytes(
        "rev-parse", FROZEN_CANDIDATE_COMMIT, repo_root=repo_root
    ).decode("ascii").strip()
    if resolved != FROZEN_CANDIDATE_COMMIT:
        raise BenchmarkEvidenceError("candidate freeze does not resolve exactly")
    paths = _frozen_candidate_paths(repo_root=repo_root)
    blobs: dict[str, str] = {}
    for relative in paths:
        current_path = repo_root / relative
        if current_path.is_symlink() or not current_path.is_file():
            raise BenchmarkEvidenceError(
                f"candidate path is unavailable or linked: {relative}"
            )
        try:
            current = current_path.read_bytes()
        except OSError as exc:
            raise BenchmarkEvidenceError(
                f"candidate path is unreadable: {relative}"
            ) from exc
        current_blob = _git_bytes(
            "hash-object",
            f"--path={relative}",
            "--",
            relative,
            repo_root=repo_root,
        ).decode("ascii").strip()
        frozen_blob = _git_bytes(
            "rev-parse",
            f"{FROZEN_CANDIDATE_COMMIT}:{relative}",
            repo_root=repo_root,
        ).decode("ascii").strip()
        if current_blob != frozen_blob:
            raise BenchmarkEvidenceError(
                f"candidate path differs from freeze: {relative}"
            )
        blobs[relative] = _sha256(current)
    scope = bind_files(repo_root, paths)
    if {
        row["path"]: row["sha256"] for row in scope["files"]
    } != blobs:
        raise BenchmarkEvidenceError("candidate freeze digest binding failed")
    return scope


def _stage5_frozen_candidate_contract(
    *, repo_root: Path = REPO
) -> tuple[str, dict[str, str]]:
    stage6_paths = set(_frozen_candidate_paths(repo_root=repo_root))
    if not set(STAGE5_CANDIDATE_PATHS).issubset(stage6_paths):
        raise BenchmarkEvidenceError(
            "Stage 5 candidate surface is not contained in Stage 6 scope"
        )
    body = hashlib.sha256()
    blobs: dict[str, str] = {}
    for relative in STAGE5_CANDIDATE_PATHS:
        frozen = _git_bytes(
            "show",
            f"{FROZEN_CANDIDATE_COMMIT}:{relative}",
            repo_root=repo_root,
        )
        blobs[relative] = _sha256(frozen)
        body.update(relative.encode("utf-8"))
        body.update(b"\0")
        body.update(frozen)
        body.update(b"\0")
    return body.hexdigest(), blobs


def _stage5_expected_gates(value: Mapping[str, Any]) -> dict[str, bool]:
    metrics = value.get("metrics")
    frozen = value.get("frozen_candidate")
    dataset = value.get("dataset")
    sources = value.get("sources")
    if (
        not isinstance(metrics, Mapping)
        or frozenset(metrics) != _STAGE5_METRIC_FIELDS
        or not isinstance(frozen, Mapping)
        or not isinstance(dataset, Mapping)
        or not isinstance(sources, Mapping)
    ):
        raise BenchmarkEvidenceError(
            "Stage 5 derived gate inputs are malformed"
        )
    positive_total = metrics.get("positive_total")
    negative_total = metrics.get("negative_total")
    if (
        type(positive_total) is not int
        or positive_total <= 0
        or type(negative_total) is not int
        or negative_total <= 0
    ):
        raise BenchmarkEvidenceError("Stage 5 denominators are invalid")
    expected_rates = (
        (
            "positive_exact_subject_predicate_rate",
            metrics.get("positive_exact_subject_predicate"),
        ),
        ("compile_coverage_rate", metrics.get("compile_coverage")),
        (
            "proof_verified_and_grounded_rate",
            metrics.get("proof_verified_and_grounded"),
        ),
    )
    for field, numerator in expected_rates:
        if (
            type(numerator) is not int
            or metrics.get(field) != numerator / positive_total
        ):
            raise BenchmarkEvidenceError(
                f"Stage 5 metric {field} does not derive"
            )
    stage_bindings = sources.get("stage_bindings")
    digests_present = (
        isinstance(frozen.get("candidate_source_digest_sha256"), str)
        and _SHA256.fullmatch(
            frozen["candidate_source_digest_sha256"]
        )
        is not None
        and isinstance(dataset.get("candidate_input_sha256"), str)
        and _SHA256.fullmatch(dataset["candidate_input_sha256"]) is not None
        and isinstance(stage_bindings, list)
        and len(stage_bindings) >= 2
        and all(
            isinstance(row, Mapping)
            and isinstance(row.get("stage_digest_sha256"), str)
            and _SHA256.fullmatch(row["stage_digest_sha256"]) is not None
            for row in stage_bindings[:2]
        )
    )
    return {
        "positive_exact_subject_predicate": (
            metrics.get("positive_exact_subject_predicate")
            == positive_total
        ),
        "compile_coverage": metrics.get("compile_coverage") == positive_total,
        "proof_verified_grounded": (
            metrics.get("proof_verified_and_grounded") == positive_total
        ),
        "wrong_compile_zero": metrics.get("wrong_compile") == 0,
        "negative_final_firing_zero": (
            metrics.get("negative_final_firing") == 0
        ),
        "provenance_pid_separation": (
            type(metrics.get("provenance_pid_separation_checked")) is int
            and metrics["provenance_pid_separation_checked"] > 0
            and metrics.get("provenance_pid_separation_failures") == 0
        ),
        "mutation_rejection": (
            type(metrics.get("mutation_rejection_checked")) is int
            and metrics["mutation_rejection_checked"] > 0
            and metrics.get("mutation_rejection_failures") == 0
        ),
        "choice_order_distractor_goal_digest_invariance": (
            metrics.get("invariance_variants_checked")
            == positive_total * 2
            and metrics.get("invariance_failures") == 0
        ),
        "deterministic_replay": (
            metrics.get("deterministic_replay_equal") is True
        ),
        "bounded_rows": (
            type(metrics.get("bounded_contexts_checked")) is int
            and metrics["bounded_contexts_checked"] > 0
            and metrics.get("bounded_context_failures") == 0
        ),
        "source_candidate_dataset_digests_present": digests_present,
        "filesystem_no_write_delta": (
            metrics.get("filesystem_no_write_delta") is True
            and metrics.get("critical_source_digest_no_write_delta") is True
        ),
    }


def _validate_stage5_document(
    value: Mapping[str, Any],
    *,
    repo_root: Path,
) -> None:
    if (
        frozenset(value) != _STAGE5_ROOT_FIELDS
        or value.get("schema_version") != STAGE5_SCHEMA_VERSION
        or value.get("measurement_class")
        != "unsigned_source_separated_self_measurement"
    ):
        raise BenchmarkEvidenceError("Stage 5 root schema is invalid")
    gates = value.get("gates")
    if (
        not isinstance(gates, Mapping)
        or frozenset(gates) != _STAGE5_GATE_FIELDS
        or any(type(result) is not bool for result in gates.values())
    ):
        raise BenchmarkEvidenceError("Stage 5 gates schema is invalid")
    expected_gates = _stage5_expected_gates(value)
    if dict(gates) != expected_gates:
        raise BenchmarkEvidenceError("Stage 5 gates do not derive")
    if value.get("gate_pass") is not all(expected_gates.values()):
        raise BenchmarkEvidenceError("Stage 5 aggregate gate does not derive")
    dataset = value.get("dataset")
    sources = value.get("sources")
    replay = value.get("replay")
    filesystem = value.get("filesystem_delta")
    disclosure = value.get("execution_disclosure")
    if (
        not isinstance(dataset, Mapping)
        or frozenset(dataset) != _STAGE5_DATASET_FIELDS
        or not isinstance(sources, Mapping)
        or frozenset(sources) != _STAGE5_SOURCE_FIELDS
        or not isinstance(replay, Mapping)
        or frozenset(replay) != _STAGE5_REPLAY_FIELDS
        or not isinstance(filesystem, Mapping)
        or frozenset(filesystem) != _STAGE5_FILESYSTEM_FIELDS
        or not isinstance(disclosure, Mapping)
        or frozenset(disclosure)
        != _STAGE5_EXECUTION_DISCLOSURE_FIELDS
    ):
        raise BenchmarkEvidenceError(
            "Stage 5 required sub-schema is invalid"
        )
    stage_bindings = sources.get("stage_bindings")
    if (
        not isinstance(stage_bindings, list)
        or len(stage_bindings) != 2
        or any(
            not isinstance(row, Mapping)
            or frozenset(row) != _STAGE5_BINDING_FIELDS
            for row in stage_bindings
        )
    ):
        raise BenchmarkEvidenceError(
            "Stage 5 stage binding schema is invalid"
        )
    frozen = value.get("frozen_candidate")
    expected_digest, expected_blobs = _stage5_frozen_candidate_contract(
        repo_root=repo_root
    )
    if (
        not isinstance(frozen, Mapping)
        or frozenset(frozen)
        != {
            "commit",
            "candidate_source_digest_sha256",
            "candidate_surface_blob_sha256",
        }
        or frozen.get("commit") != FROZEN_CANDIDATE_COMMIT
        or frozen.get("candidate_source_digest_sha256") != expected_digest
        or frozen.get("candidate_surface_blob_sha256") != expected_blobs
    ):
        raise BenchmarkEvidenceError(
            "Stage 5 candidate digest does not match Stage 6 frozen scope"
        )
    failures = value.get("failures")
    if not isinstance(failures, list):
        raise BenchmarkEvidenceError("Stage 5 failures schema is invalid")
    if value.get("gate_pass") is True and failures:
        raise BenchmarkEvidenceError("Stage 5 green receipt carries failures")
    if value.get("gate_pass") is False and not failures:
        raise BenchmarkEvidenceError("Stage 5 RED receipt has no failures")


def _read_stage5_prerequisite(
    path: Path,
    *,
    allow_red_diagnostic: bool = False,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    relative = _repo_relative_file(path, repo_root=repo_root)
    try:
        raw = (repo_root / relative).read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError("Stage 5 receipt is unreadable") from exc
    value = strict_json_bytes(raw, label="Stage 5 receipt")
    _validate_stage5_document(value, repo_root=repo_root)
    frozen = value.get("frozen_candidate")
    disclaimer = value.get("authority_disclaimer")
    failures = value.get("failures")
    gate_pass = value.get("gate_pass")
    disclaimer_fields = {
        "external_evaluation",
        "external_authenticity",
        "independent_evaluation",
        "e4",
        "e5",
        "capability_claim",
    }
    if (
        value.get("schema_version") != STAGE5_SCHEMA_VERSION
        or type(gate_pass) is not bool
        or not isinstance(failures, list)
        or not isinstance(frozen, Mapping)
        or frozen.get("commit") != FROZEN_CANDIDATE_COMMIT
        or not isinstance(
            frozen.get("candidate_source_digest_sha256"), str
        )
        or _SHA256.fullmatch(
            frozen["candidate_source_digest_sha256"]
        )
        is None
        or not isinstance(disclaimer, Mapping)
        or set(disclaimer) != disclaimer_fields
        or any(value is not False for value in disclaimer.values())
    ):
        raise BenchmarkEvidenceError("Stage 5 prerequisite binding is invalid")
    if gate_pass is True:
        if failures != []:
            raise BenchmarkEvidenceError(
                "Stage 5 green prerequisite carries failures"
            )
        stage5_status = "sealed_green"
        prerequisite_passed = True
        if _sha256(raw) not in TRUSTED_STAGE5_GREEN_SHA256:
            raise BenchmarkEvidenceError(
                "Stage 5 green receipt digest is not explicitly trusted"
            )
    else:
        if not allow_red_diagnostic:
            raise BenchmarkEvidenceError("Stage 5 prerequisite is not sealed")
        if not failures:
            raise BenchmarkEvidenceError(
                "Stage 5 RED diagnostic has no recorded failures"
            )
        if _sha256(raw) != EXPECTED_STAGE5_RED_SHA256:
            raise BenchmarkEvidenceError(
                "Stage 5 RED diagnostic receipt hash is not the pinned artifact"
            )
        stage5_status = "red_unsealed_diagnostic"
        prerequisite_passed = False
    return {
        "path": relative,
        "sha256": _sha256(raw),
        "schema_version": STAGE5_SCHEMA_VERSION,
        "stage5_status": stage5_status,
        "gate_pass": gate_pass,
        "stage5_failures": len(failures),
        "prerequisite_passed": prerequisite_passed,
        "frozen_candidate_commit": FROZEN_CANDIDATE_COMMIT,
        "candidate_source_digest_sha256": frozen[
            "candidate_source_digest_sha256"
        ],
    }


def _gpqa_blocker(*, repo_root: Path = REPO) -> dict[str, Any]:
    path = repo_root / GPQA_PATH
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != EXPECTED_GPQA_SHA256:
        raise BenchmarkEvidenceError("GPQA blocker bytes changed")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise BenchmarkEvidenceError("GPQA blocker is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = list(reader)
    malformed: list[int] = []
    for ordinal, row in enumerate(rows):
        options = [
            str(row.get("Correct Answer") or "").strip(),
            *[
                str(row.get(f"Incorrect Answer {index}") or "").strip()
                for index in (1, 2, 3)
            ],
        ]
        if (
            not all(options)
            or len({option.casefold() for option in options}) != 4
        ):
            malformed.append(ordinal)
    loader_rejected = False
    try:
        bench._load_gpqa_bytes(raw, nonce=b"\0" * 32)
    except BenchmarkEvidenceError:
        loader_rejected = True
    if (
        len(rows) != 198
        or malformed != [89, 126, 191]
        or not loader_rejected
    ):
        raise BenchmarkEvidenceError(
            "GPQA blocker no longer matches the fail-closed contract"
        )
    return {
        "status": "blocked_fail_closed",
        "dataset_path": GPQA_PATH,
        "dataset_sha256": digest,
        "row_count": len(rows),
        "malformed_row_count": len(malformed),
        "malformed_zero_based_ordinals": malformed,
        "reason": "duplicate_normalized_answer_text_across_labels",
        "strict_loader_rejected": True,
        "accuracy_available": False,
        "baseline_available": False,
        "lift_available": False,
    }


def _protocol(
    baseline_store: str, *, stage5_status: str
) -> dict[str, Any]:
    return {
        "benchmark": "MMLU-Pro",
        "slice": "slice_5",
        "classification": (
            "exposed_local_development_offline_counterfactual_not_e5"
        ),
        "fixed_denominator": EXPECTED_ITEMS,
        "baseline": {
            "function": "packages.reasoning_vm.exam_answer.answer_exam",
            "store": baseline_store,
            "store_read_only_required": True,
            "passages": None,
            "content_index": None,
            "gold_in_call": False,
        },
        "off": "direct declared baseline answer",
        "on": (
            "same baseline plus evaluator-only override iff synchronous "
            "generic proof fires and independently verifies"
        ),
        "live_output": "unchanged baseline answer in both conditions",
        "gold_separation": {
            "gold_in_worker_arguments": False,
            "gold_filesystem_isolation_established": False,
            "scope": (
                "logical argument separation only; evaluator and worker "
                "share a local filesystem without an OS sandbox"
            ),
        },
        "counterbalance": (
            "even ordinals OFF-then-ON; odd ordinals ON-then-OFF; "
            "20 items in each primary order"
        ),
        "replay": "fresh process with reverse per-item condition order",
        "strict_scoring": "abstentions and errors are incorrect on all 40 items",
        "stage5_status": stage5_status,
        "promotion_rule": (
            "measurement integrity is reported separately from the Stage 5 "
            "prerequisite; this exposed development receipt never promotes"
        ),
        "limitations": [
            "the MMLU-Pro slice is exposed development data",
            "the evaluator is local, unsigned, and not independent",
            "the ON answer is evaluator-applied and has no live authority",
            "proof verification and firing are not benchmark correctness",
            "complete proof payloads are absent, so final-receipt proof "
            "verification is not independently replayable",
            "reverse replay payloads are absent, so final-receipt replay "
            "verification is not independently reproducible",
            "gold is excluded from worker arguments but filesystem isolation "
            "from evaluator-owned gold is not established",
            "network isolation is not established",
        ],
    }


def _safe_worker_item(
    row: Mapping[str, Any],
    ordinal: int,
    *,
    replay: bool,
) -> dict[str, Any]:
    primary_order = ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
    execution_order = list(reversed(primary_order)) if replay else primary_order
    return {
        "item_id": mmlu._item_identity(row, ordinal),
        "ordinal": ordinal,
        "execution_order": execution_order,
        "question": row["q"],
        "choices": json.loads(canonical_json_bytes(row["choices"])),
    }


def _write_worker_input(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    replay: bool,
) -> None:
    try:
        with path.open("xb") as handle:
            for ordinal, row in enumerate(rows):
                item = _safe_worker_item(row, ordinal, replay=replay)
                if frozenset(item) != {
                    "item_id",
                    "ordinal",
                    "execution_order",
                    "question",
                    "choices",
                }:
                    raise BenchmarkEvidenceError(
                        "worker input boundary fields mismatch"
                    )
                handle.write(canonical_json_bytes(item) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError("worker input already exists") from exc


def _read_worker_input(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_bytes().splitlines()
    except OSError as exc:
        raise BenchmarkEvidenceError("worker input is unreadable") from exc
    if len(lines) != EXPECTED_ITEMS:
        raise BenchmarkEvidenceError("worker denominator is not exactly 40")
    items: list[dict[str, Any]] = []
    for ordinal, line in enumerate(lines):
        item = strict_json_bytes(line, label=f"worker input {ordinal}")
        if (
            frozenset(item)
            != {
                "item_id",
                "ordinal",
                "execution_order",
                "question",
                "choices",
            }
            or item.get("ordinal") != ordinal
            or item.get("execution_order")
            not in (["off", "on"], ["on", "off"])
            or not isinstance(item.get("question"), str)
            or not isinstance(item.get("choices"), dict)
            or not item["choices"]
        ):
            raise BenchmarkEvidenceError(
                f"worker input {ordinal} is invalid"
            )
        items.append(item)
    return items


def _empty_generic_record() -> dict[str, Any]:
    return {
        "eligible": False,
        "role_extracted": False,
        "context_ready": False,
        "compiled": False,
        "engine_called": False,
        "fired": False,
        "proof_verified": False,
        "grounded": False,
        "status": "disabled",
        "reason": "condition_off",
        "error_kind": None,
        "prepared_input_digest_sha256": None,
        "prepared_choices_digest_sha256": None,
        "role_receipt_digest_sha256": None,
        "context_digest_sha256": None,
        "compiler_receipt_digest_sha256": None,
        "proof_decision_digest_sha256": None,
        "proof_receipt_digest_sha256": None,
        "choice_key": None,
        "answer_authority_established": False,
    }


def _generic_record(prepared: object) -> dict[str, Any]:
    from packages.reasoning_vm.deliberator import (
        generic_predicate_shadow as shadow,
    )
    from packages.reasoning_vm.deliberator.generic_predicate_staging import (
        verify_generic_predicate_proof_receipt,
    )

    telemetry = shadow._process_item(prepared)
    verified = False
    choice_key = None
    if (
        telemetry.fired is True
        and telemetry.proof_verified is True
        and telemetry.proof_receipt is not None
        and telemetry.compiler_receipt is not None
        and telemetry.role_receipt is not None
        and telemetry.context_receipt is not None
    ):
        verified = bool(
            verify_generic_predicate_proof_receipt(
                telemetry.proof_receipt,
                prepared.stem,
                telemetry.compiler_receipt,
                role_receipt=telemetry.role_receipt,
                context=telemetry.context_receipt,
            )
        )
        if verified:
            candidate = telemetry.proof_receipt.choice_key
            if candidate in dict(prepared.choice_items):
                choice_key = candidate
            else:
                verified = False
    return {
        "eligible": telemetry.eligible is True,
        "role_extracted": telemetry.role_extracted is True,
        "context_ready": telemetry.context_ready is True,
        "compiled": telemetry.compiled is True,
        "engine_called": telemetry.engine_called is True,
        "fired": telemetry.fired is True,
        "proof_verified": verified,
        "grounded": verified,
        "status": telemetry.status,
        "reason": telemetry.reason,
        "error_kind": telemetry.error_kind,
        "prepared_input_digest_sha256": (
            telemetry.prepared_input_digest_sha256
        ),
        "prepared_choices_digest_sha256": (
            telemetry.prepared_choices_digest_sha256
        ),
        "role_receipt_digest_sha256": (
            telemetry.role_receipt_digest_sha256
        ),
        "context_digest_sha256": telemetry.context_digest_sha256,
        "compiler_receipt_digest_sha256": (
            telemetry.compiler_receipt_digest_sha256
        ),
        "proof_decision_digest_sha256": (
            telemetry.proof_decision_digest_sha256
        ),
        "proof_receipt_digest_sha256": (
            telemetry.proof_receipt_digest_sha256
        ),
        "choice_key": choice_key,
        "answer_authority_established": False,
    }


def _condition_record(
    question: str,
    choices: Mapping[str, str],
    facts_about: Any,
    *,
    condition: str,
) -> dict[str, Any]:
    from packages.cognitive_core.canonical import canonical_digest
    from packages.reasoning_vm.exam_answer import answer_exam
    from packages.reasoning_vm.science_candidate import prepare_science_input

    baseline = answer_exam(
        question,
        dict(choices),
        facts_about,
        passages=None,
        content_index=None,
    )
    baseline_choice = baseline.get("choice_key")
    if baseline_choice is not None and baseline_choice not in choices:
        raise BenchmarkEvidenceError("baseline returned an invalid choice")
    baseline_digest = canonical_digest(baseline)
    generic = _empty_generic_record()
    counterfactual_choice = baseline_choice
    override = False
    if condition == "on":
        prepared = prepare_science_input(question, dict(choices))
        generic = _generic_record(prepared)
        if (
            generic["fired"] is True
            and generic["proof_verified"] is True
            and generic["choice_key"] in choices
        ):
            counterfactual_choice = generic["choice_key"]
            override = True
    elif condition != "off":
        raise BenchmarkEvidenceError("worker condition is invalid")
    core = {
        "baseline_choice_key": baseline_choice,
        "baseline_choice_digest_sha256": _choice_digest(baseline_choice),
        "baseline_mode": baseline.get("mode"),
        "baseline_semantic_digest_sha256": baseline_digest,
        "live_choice_key": baseline_choice,
        "live_semantic_digest_sha256": baseline_digest,
        "counterfactual_choice_key": counterfactual_choice,
        "counterfactual_choice_digest_sha256": _choice_digest(
            counterfactual_choice
        ),
        "counterfactual_override_applied": override,
        "generic": generic,
    }
    return {
        **core,
        "condition_semantic_digest_sha256": canonical_digest(core),
    }


def _worker(
    input_path: Path,
    output_path: Path,
    *,
    baseline_store: str,
) -> None:
    os.environ.pop("ATANOR_GENERIC_PREDICATE_SHADOW", None)
    os.environ["WORLD_PACK_STORE"] = baseline_store
    os.environ["ATANOR_S2_ENGINE"] = "1"
    os.environ["ATANOR_MEMBERSHIP"] = "1"
    os.environ.pop("ATANOR_PMI", None)

    from scripts.benchmark_openbook import _load_store, _resolving_fa

    items = _read_worker_input(input_path)
    store = None
    results: list[dict[str, Any]] = []
    try:
        store, metadata = _load_store(read_only=True)
        if metadata.get("store") != baseline_store:
            raise BenchmarkEvidenceError(
                "baseline store silently fell back"
            )
        if hasattr(store, "shards"):
            read_only = all(
                getattr(shard, "_read_only", False)
                for shard in store.shards
            )
        else:
            read_only = getattr(store, "_read_only", False)
        if not read_only:
            raise BenchmarkEvidenceError(
                "baseline store did not open read-only"
            )

        def raw_facts(term: str) -> Any:
            return store.facts_about(term, limit=24)

        facts_about = _resolving_fa(raw_facts)
        for item in items:
            conditions: dict[str, dict[str, Any]] = {}
            for condition in item["execution_order"]:
                conditions[condition] = _condition_record(
                    item["question"],
                    item["choices"],
                    facts_about,
                    condition=condition,
                )
            results.append(
                {
                    "item_id": item["item_id"],
                    "ordinal": item["ordinal"],
                    "execution_order": item["execution_order"],
                    "conditions": {
                        name: conditions[name] for name in ("off", "on")
                    },
                }
            )
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()
    payload = {
        "schema_version": SCHEMA_VERSION + ".worker.v1",
        "baseline_store": baseline_store,
        "gold_received": False,
        "items": results,
    }
    write_manifest_exclusive(output_path, payload)


def _read_worker_output(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError("worker output is unreadable") from exc
    return strict_json_bytes(payload, label="Stage 6 worker output")


def _run_worker(
    input_path: Path,
    output_path: Path,
    *,
    baseline_store: str,
) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    environment.pop("ATANOR_GENERIC_PREDICATE_SHADOW", None)
    try:
        subprocess.run(
            (
                sys.executable,
                str(Path(__file__).resolve()),
                "_worker",
                str(input_path),
                str(output_path),
                "--baseline-store",
                baseline_store,
            ),
            cwd=REPO,
            env=environment,
            check=True,
            timeout=WORKER_TIMEOUT_SECONDS,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise BenchmarkEvidenceError(
            "Stage 6 candidate worker failed closed"
        ) from exc
    return _read_worker_output(output_path)


def _validate_generic(value: Any, *, label: str) -> list[str]:
    findings: list[str] = []
    if not isinstance(value, Mapping) or frozenset(value) != _GENERIC_FIELDS:
        return [f"{label} fields mismatch"]
    for field in (
        "eligible",
        "role_extracted",
        "context_ready",
        "compiled",
        "engine_called",
        "fired",
        "proof_verified",
        "grounded",
        "answer_authority_established",
    ):
        if type(value.get(field)) is not bool:
            findings.append(f"{label}.{field} must be boolean")
    if value.get("answer_authority_established") is not False:
        findings.append(f"{label} claims answer authority")
    if value.get("grounded") is not value.get("proof_verified"):
        findings.append(f"{label}.grounded is not proof_verified")
    if value.get("proof_verified") is True and (
        value.get("fired") is not True
        or value.get("choice_key") is None
        or value.get("proof_receipt_digest_sha256") is None
    ):
        findings.append(f"{label} verified proof is incomplete")
    for field in (
        "prepared_input_digest_sha256",
        "prepared_choices_digest_sha256",
        "role_receipt_digest_sha256",
        "context_digest_sha256",
        "compiler_receipt_digest_sha256",
        "proof_decision_digest_sha256",
        "proof_receipt_digest_sha256",
    ):
        digest = value.get(field)
        if digest is not None and (
            not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
        ):
            findings.append(f"{label}.{field} is invalid")
    return findings


def _validate_condition(value: Any, *, label: str) -> list[str]:
    findings: list[str] = []
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != _CONDITION_FIELDS
    ):
        return [f"{label} fields mismatch"]
    findings.extend(_validate_generic(value.get("generic"), label=f"{label}.generic"))
    baseline = value.get("baseline_choice_key")
    live = value.get("live_choice_key")
    if live != baseline:
        findings.append(f"{label} live answer differs from baseline")
    if value.get("live_semantic_digest_sha256") != value.get(
        "baseline_semantic_digest_sha256"
    ):
        findings.append(f"{label} live semantics differ from baseline")
    if value.get("baseline_choice_digest_sha256") != _choice_digest(baseline):
        findings.append(f"{label} baseline choice digest mismatch")
    counterfactual = value.get("counterfactual_choice_key")
    if value.get("counterfactual_choice_digest_sha256") != _choice_digest(
        counterfactual
    ):
        findings.append(f"{label} counterfactual choice digest mismatch")
    generic = value.get("generic")
    if isinstance(generic, Mapping):
        expected_override = (
            generic.get("fired") is True
            and generic.get("proof_verified") is True
            and generic.get("choice_key") is not None
        )
        if value.get("counterfactual_override_applied") is not expected_override:
            findings.append(f"{label} counterfactual override is not derived")
        expected_choice = (
            generic.get("choice_key") if expected_override else baseline
        )
        if counterfactual != expected_choice:
            findings.append(f"{label} counterfactual choice is not derived")
    core = {
        key: value.get(key)
        for key in sorted(
            _CONDITION_FIELDS - {"condition_semantic_digest_sha256"}
        )
    }
    from packages.cognitive_core.canonical import canonical_digest

    if value.get("condition_semantic_digest_sha256") != canonical_digest(core):
        findings.append(f"{label} semantic digest mismatch")
    return findings


def _validate_worker_output(
    value: Mapping[str, Any],
    *,
    baseline_store: str,
    label: str,
) -> list[Mapping[str, Any]]:
    if (
        frozenset(value)
        != {
            "schema_version",
            "baseline_store",
            "gold_received",
            "items",
        }
        or value.get("schema_version") != SCHEMA_VERSION + ".worker.v1"
        or value.get("baseline_store") != baseline_store
        or value.get("gold_received") is not False
        or not isinstance(value.get("items"), list)
        or len(value["items"]) != EXPECTED_ITEMS
    ):
        raise BenchmarkEvidenceError(f"{label} root schema mismatch")
    for ordinal, item in enumerate(value["items"]):
        if (
            not isinstance(item, Mapping)
            or frozenset(item)
            != {"item_id", "ordinal", "execution_order", "conditions"}
            or item.get("ordinal") != ordinal
            or item.get("execution_order")
            not in (["off", "on"], ["on", "off"])
            or not isinstance(item.get("conditions"), Mapping)
            or frozenset(item["conditions"]) != {"off", "on"}
        ):
            raise BenchmarkEvidenceError(
                f"{label} item {ordinal} schema mismatch"
            )
    return value["items"]


def _score_worker_results(
    rows: Sequence[Mapping[str, Any]],
    primary: Mapping[str, Any],
    repeated: Mapping[str, Any],
    *,
    baseline_store: str,
) -> list[dict[str, Any]]:
    primary_items = _validate_worker_output(
        primary, baseline_store=baseline_store, label="primary worker"
    )
    replay_items = _validate_worker_output(
        repeated, baseline_store=baseline_store, label="replay worker"
    )
    if len(primary_items) != len(rows) or len(replay_items) != len(rows):
        raise BenchmarkEvidenceError("worker output census is invalid")
    results: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows):
        first = primary_items[ordinal]
        second = replay_items[ordinal]
        item_id = mmlu._item_identity(row, ordinal)
        expected_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        if (
            first.get("item_id") != item_id
            or second.get("item_id") != item_id
            or first.get("ordinal") != ordinal
            or second.get("ordinal") != ordinal
            or first.get("execution_order") != expected_order
            or second.get("execution_order")
            != list(reversed(expected_order))
        ):
            raise BenchmarkEvidenceError(
                f"worker item {ordinal} identity/order mismatch"
            )
        conditions = first.get("conditions")
        replay_conditions = second.get("conditions")
        if (
            not isinstance(conditions, Mapping)
            or frozenset(conditions) != {"off", "on"}
            or not isinstance(replay_conditions, Mapping)
            or frozenset(replay_conditions) != {"off", "on"}
        ):
            raise BenchmarkEvidenceError(
                f"worker item {ordinal} conditions mismatch"
            )
        for condition in ("off", "on"):
            findings = _validate_condition(
                conditions[condition],
                label=f"worker[{ordinal}].{condition}",
            )
            findings.extend(
                _validate_condition(
                    replay_conditions[condition],
                    label=f"replay[{ordinal}].{condition}",
                )
            )
            if findings:
                raise BenchmarkEvidenceError("; ".join(findings))
            for record in (
                conditions[condition],
                replay_conditions[condition],
            ):
                for choice_field in (
                    "baseline_choice_key",
                    "live_choice_key",
                    "counterfactual_choice_key",
                ):
                    choice = record.get(choice_field)
                    if choice is not None and choice not in row["choices"]:
                        raise BenchmarkEvidenceError(
                            f"worker item {ordinal} returned invalid choice"
                        )
                generic_choice = record["generic"].get("choice_key")
                if (
                    generic_choice is not None
                    and generic_choice not in row["choices"]
                ):
                    raise BenchmarkEvidenceError(
                        f"worker item {ordinal} generic choice is invalid"
                    )
        off = conditions["off"]
        on = conditions["on"]
        gold = row["gold"]
        baseline_choice = off["baseline_choice_key"]
        counterfactual_choice = on["counterfactual_choice_key"]
        baseline_correct = baseline_choice == gold
        counterfactual_correct = counterfactual_choice == gold
        generic_verified = on["generic"]["proof_verified"] is True
        generic_wrong_fire = (
            generic_verified and on["generic"]["choice_key"] != gold
        )
        replay = {
            condition + "_semantic_same": (
                conditions[condition]["condition_semantic_digest_sha256"]
                == replay_conditions[condition][
                    "condition_semantic_digest_sha256"
                ]
            )
            for condition in ("off", "on")
        }
        results.append(
            {
                "item_id": item_id,
                "ordinal": ordinal,
                "category": row["category"],
                "primary_execution_order": expected_order,
                "replay_execution_order": list(reversed(expected_order)),
                "conditions": conditions,
                "outcomes": {
                    "baseline_correct": baseline_correct,
                    "live_off_correct": baseline_correct,
                    "live_on_correct": on["live_choice_key"] == gold,
                    "counterfactual_on_correct": counterfactual_correct,
                    "generic_wrong_fire": generic_wrong_fire,
                    "regression": (
                        baseline_correct and not counterfactual_correct
                    ),
                    "win": (
                        not baseline_correct and counterfactual_correct
                    ),
                },
                "transition": (
                    f"{'correct' if baseline_correct else 'incorrect'}_to_"
                    f"{'correct' if counterfactual_correct else 'incorrect'}"
                ),
                "replay": replay,
                "gold_absent_from_candidate_arguments": True,
            }
        )
    return results


def _condition_counts(
    items: Sequence[Mapping[str, Any]], condition: str
) -> dict[str, int]:
    generic_rows = [
        item["conditions"][condition]["generic"] for item in items
    ]
    return {
        "eligible": sum(int(row["eligible"]) for row in generic_rows),
        "role_extracted": sum(
            int(row["role_extracted"]) for row in generic_rows
        ),
        "context_ready": sum(
            int(row["context_ready"]) for row in generic_rows
        ),
        "compiled": sum(int(row["compiled"]) for row in generic_rows),
        "engine_called": sum(
            int(row["engine_called"]) for row in generic_rows
        ),
        "fired": sum(int(row["fired"]) for row in generic_rows),
        "proof_verified": sum(
            int(row["proof_verified"]) for row in generic_rows
        ),
        "error": sum(
            int(row["error_kind"] is not None) for row in generic_rows
        ),
    }


def _rescore_fixed_items(
    items: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if len(items) != EXPECTED_ITEMS or len(rows) != EXPECTED_ITEMS:
        raise BenchmarkEvidenceError(
            "fixed MMLU-Pro rescore denominator mismatch"
        )
    for ordinal, (item, row) in enumerate(zip(items, rows)):
        expected_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        if (
            not isinstance(item, Mapping)
            or frozenset(item) != _ITEM_FIELDS
            or item.get("item_id") != mmlu._item_identity(row, ordinal)
            or item.get("ordinal") != ordinal
            or item.get("category") != row["category"]
            or item.get("primary_execution_order") != expected_order
            or item.get("replay_execution_order")
            != list(reversed(expected_order))
            or item.get("gold_absent_from_candidate_arguments") is not True
        ):
            raise BenchmarkEvidenceError(
                f"fixed MMLU-Pro item {ordinal} identity/category mismatch"
            )
        conditions = item.get("conditions")
        if (
            not isinstance(conditions, Mapping)
            or frozenset(conditions) != {"off", "on"}
        ):
            raise BenchmarkEvidenceError(
                f"fixed MMLU-Pro item {ordinal} conditions mismatch"
            )
        for condition in ("off", "on"):
            for field in (
                "baseline_choice_key",
                "live_choice_key",
                "counterfactual_choice_key",
            ):
                choice = conditions[condition].get(field)
                if choice is not None and choice not in row["choices"]:
                    raise BenchmarkEvidenceError(
                        f"fixed MMLU-Pro item {ordinal} choice mismatch"
                    )
            generic_choice = conditions[condition].get("generic", {}).get(
                "choice_key"
            )
            if (
                generic_choice is not None
                and generic_choice not in row["choices"]
            ):
                raise BenchmarkEvidenceError(
                    f"fixed MMLU-Pro item {ordinal} generic choice mismatch"
                )
        off = conditions["off"]
        on = conditions["on"]
        gold = row["gold"]
        baseline_correct = off["baseline_choice_key"] == gold
        counterfactual_correct = (
            on["counterfactual_choice_key"] == gold
        )
        generic_verified = on["generic"]["proof_verified"] is True
        expected_outcomes = {
            "baseline_correct": baseline_correct,
            "live_off_correct": off["live_choice_key"] == gold,
            "live_on_correct": on["live_choice_key"] == gold,
            "counterfactual_on_correct": counterfactual_correct,
            "generic_wrong_fire": (
                generic_verified and on["generic"]["choice_key"] != gold
            ),
            "regression": (
                baseline_correct and not counterfactual_correct
            ),
            "win": (
                not baseline_correct and counterfactual_correct
            ),
        }
        if (
            not isinstance(item.get("outcomes"), Mapping)
            or frozenset(item["outcomes"]) != _OUTCOME_FIELDS
            or dict(item["outcomes"]) != expected_outcomes
        ):
            raise BenchmarkEvidenceError(
                f"fixed MMLU-Pro item {ordinal} outcomes do not rescore"
            )
        expected_transition = (
            f"{'correct' if baseline_correct else 'incorrect'}_to_"
            f"{'correct' if counterfactual_correct else 'incorrect'}"
        )
        if item.get("transition") != expected_transition:
            raise BenchmarkEvidenceError(
                f"fixed MMLU-Pro item {ordinal} transition does not rescore"
            )
        replay = item.get("replay")
        if (
            not isinstance(replay, Mapping)
            or frozenset(replay)
            != {"off_semantic_same", "on_semantic_same"}
            or any(type(value) is not bool for value in replay.values())
        ):
            raise BenchmarkEvidenceError(
                f"fixed MMLU-Pro item {ordinal} replay flags mismatch"
            )


def _derive_metrics(
    items: Sequence[Mapping[str, Any]],
    *,
    prerequisite_passed: bool,
) -> dict[str, Any]:
    if type(prerequisite_passed) is not bool:
        raise BenchmarkEvidenceError(
            "prerequisite_passed must be an exact boolean"
        )
    n = len(items)
    off_counts = _condition_counts(items, "off")
    on_counts = _condition_counts(items, "on")
    baseline_correct = sum(
        int(item["outcomes"]["baseline_correct"]) for item in items
    )
    live_off_correct = sum(
        int(item["outcomes"]["live_off_correct"]) for item in items
    )
    live_on_correct = sum(
        int(item["outcomes"]["live_on_correct"]) for item in items
    )
    counterfactual_correct = sum(
        int(item["outcomes"]["counterfactual_on_correct"])
        for item in items
    )
    wrong_fires = sum(
        int(item["outcomes"]["generic_wrong_fire"]) for item in items
    )
    regressions = sum(
        int(item["outcomes"]["regression"]) for item in items
    )
    wins = sum(int(item["outcomes"]["win"]) for item in items)
    invariant = sum(
        int(
            item["conditions"]["off"]["baseline_choice_key"]
            == item["conditions"]["on"]["baseline_choice_key"]
            and item["conditions"]["off"][
                "baseline_semantic_digest_sha256"
            ]
            == item["conditions"]["on"][
                "baseline_semantic_digest_sha256"
            ]
            and item["conditions"]["on"]["live_choice_key"]
            == item["conditions"]["on"]["baseline_choice_key"]
        )
        for item in items
    )
    order_counts = Counter(
        "off_then_on"
        if item["primary_execution_order"] == ["off", "on"]
        else "on_then_off"
        for item in items
    )
    transitions = Counter(item["transition"] for item in items)
    replay_all = all(
        all(item["replay"].values()) for item in items
    )
    off_disabled_all = all(
        item["conditions"]["off"]["generic"] == _empty_generic_record()
        for item in items
    )
    per_condition: dict[str, Any] = {}
    for name, counts in (("off", off_counts), ("on", on_counts)):
        per_condition[name] = {
            "n": n,
            **counts,
            **{
                key + "_rate": _ratio(value, n)
                for key, value in counts.items()
            },
        }
    return {
        "denominator": n,
        "primary_order_counts": dict(sorted(order_counts.items())),
        "conditions": per_condition,
        "baseline_correct": baseline_correct,
        "baseline_strict_accuracy": _ratio(baseline_correct, n),
        "live_off_correct": live_off_correct,
        "live_off_strict_accuracy": _ratio(live_off_correct, n),
        "live_on_correct": live_on_correct,
        "live_on_strict_accuracy": _ratio(live_on_correct, n),
        "live_answer_invariant": invariant,
        "live_answer_invariance_rate": _ratio(invariant, n),
        "counterfactual_on_correct": counterfactual_correct,
        "counterfactual_on_strict_accuracy": _ratio(
            counterfactual_correct, n
        ),
        "counterfactual_strict_accuracy_delta": round(
            _ratio(counterfactual_correct, n)
            - _ratio(baseline_correct, n),
            12,
        ),
        "generic_wrong_fires": wrong_fires,
        "generic_wrong_fire_rate": _ratio(wrong_fires, n),
        "regressions": regressions,
        "wins": wins,
        "transition_counts": dict(sorted(transitions.items())),
        "exact_two_sided_mcnemar_p": mmlu._exact_mcnemar_p(
            regressions, wins
        ),
        "semantic_replay_all": replay_all,
        "off_generic_structurally_disabled_all": off_disabled_all,
        "measurement_integrity_passed": (
            n == EXPECTED_ITEMS
            and dict(order_counts)
            == {"off_then_on": 20, "on_then_off": 20}
            and invariant == n
            and replay_all
            and off_disabled_all
            and off_counts["compiled"]
            == off_counts["fired"]
            == off_counts["proof_verified"]
            == 0
        ),
        "prerequisite_passed": prerequisite_passed,
        "promotion_gate_passed": False,
    }


def _selection(
    rows: Sequence[Mapping[str, Any]], dataset_bytes: bytes
) -> dict[str, Any]:
    return mmlu._selection(rows, dataset_bytes)


def _assemble_receipt(
    *,
    rows: Sequence[Mapping[str, Any]],
    dataset_bytes: bytes,
    primary: Mapping[str, Any],
    repeated: Mapping[str, Any],
    baseline_store: str,
    stage5: Mapping[str, Any],
    scopes: Mapping[str, Mapping[str, Any]],
    gpqa_blocker: Mapping[str, Any],
) -> dict[str, Any]:
    items = _score_worker_results(
        rows,
        primary,
        repeated,
        baseline_store=baseline_store,
    )
    prerequisite_passed = stage5.get("prerequisite_passed")
    if type(prerequisite_passed) is not bool:
        raise BenchmarkEvidenceError(
            "Stage 5 prerequisite status is invalid"
        )
    metrics = _derive_metrics(
        items, prerequisite_passed=prerequisite_passed
    )
    if not metrics["measurement_integrity_passed"]:
        raise BenchmarkEvidenceError(
            "Stage 6 measurement integrity failed closed"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "protocol": _protocol(
            baseline_store,
            stage5_status=str(stage5.get("stage5_status")),
        ),
        "claims": {
            "classification": CLAIMS_CLASSIFICATION,
            "development_only": True,
            "offline_counterfactual_only": True,
            "live_answer_authority": False,
            "counterfactual_policy_evaluated": True,
            "sealed": False,
            "promotion_allowed": False,
            "e4_claimed": False,
            "e5_claimed": False,
            "benchmark_capability_claimed": False,
            "independent": False,
            "externally_signed": False,
            "external_authenticity_established": False,
            "production_authority": False,
            "firing_is_correctness": False,
            "proof_verification_is_benchmark_correctness": False,
            "gold_filesystem_isolation_established": False,
            "independent_proof_reverification_available": False,
            "independent_replay_reverification_available": False,
            "gpqa_accuracy_claimed": False,
        },
        "frozen_candidate": {
            "commit": FROZEN_CANDIDATE_COMMIT,
            "candidate_digest_sha256": scopes["candidate"][
                "content_sha256"
            ],
        },
        "stage5_prerequisite": dict(stage5),
        "source": dict(scopes["source"]),
        "candidate": dict(scopes["candidate"]),
        "dataset": dict(scopes["dataset"]),
        "stage": dict(scopes["stage"]),
        "baseline_store": {
            "name": baseline_store,
            **dict(scopes["baseline_store"]),
        },
        "selection": _selection(rows, dataset_bytes),
        "gpqa_blocker": dict(gpqa_blocker),
        "metrics": metrics,
        "items": items,
        "integrity": {
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "dataset_same_before_after": True,
            "stage_same_before_after": True,
            "baseline_store_same_before_after": True,
            "candidate_matches_freeze": True,
            "stage5_artifact_bound": True,
            "stage5_gate_bound": prerequisite_passed,
            "stage5_red_diagnostic_explicit": (
                stage5.get("stage5_status")
                == "red_unsealed_diagnostic"
            ),
            "measurement_integrity_passed": metrics[
                "measurement_integrity_passed"
            ],
            "promotion_gate_passed": False,
            "same_items_choices_off_on": True,
            "gold_absent_from_candidate_arguments_all": True,
            "live_answer_invariant_all": (
                metrics["live_answer_invariant"] == EXPECTED_ITEMS
            ),
            "semantic_replay_all": metrics["semantic_replay_all"],
            "baseline_store_read_only": True,
            "generic_async_submit_used_for_scoring": False,
            "gold_filesystem_isolation_enforced": False,
            "proof_payload_embedded": False,
            "replay_payload_embedded": False,
            "independent_proof_reverification_available": False,
            "independent_replay_reverification_available": False,
            "network_isolation_enforced": False,
            "production_authority": False,
        },
    }
    manifest = json.loads(canonical_json_bytes(payload))
    manifest["manifest_checksum_sha256"] = _checksum(manifest)
    return manifest


def _current_scopes(
    *,
    baseline_store: str,
    stage5_relative: str,
    repo_root: Path = REPO,
) -> dict[str, dict[str, Any]]:
    return {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": _frozen_candidate_scope(repo_root=repo_root),
        "dataset": bind_files(repo_root, (DATASET_PATH, GPQA_PATH)),
        "stage": bind_files(
            repo_root, _files_under(STAGE_ROOTS, repo_root=repo_root)
        ),
        "baseline_store": bind_files(
            repo_root,
            _store_paths(baseline_store, repo_root=repo_root),
        ),
        "stage5": bind_files(repo_root, (stage5_relative,)),
    }


def _scope_shape_valid(value: Any) -> bool:
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != {"files", "content_sha256"}
        or not isinstance(value.get("files"), list)
        or not value["files"]
        or not isinstance(value.get("content_sha256"), str)
        or _SHA256.fullmatch(value["content_sha256"]) is None
    ):
        return False
    files = value["files"]
    paths = [
        row.get("path") if isinstance(row, Mapping) else None
        for row in files
    ]
    if (
        any(not isinstance(path, str) or not path for path in paths)
        or paths != sorted(paths)
        or len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
    ):
        return False
    if not all(
        isinstance(row, Mapping)
        and frozenset(row) == {"path", "bytes", "sha256"}
        and "\\" not in row["path"]
        and not Path(row["path"]).is_absolute()
        and "." not in Path(row["path"]).parts
        and ".." not in Path(row["path"]).parts
        and type(row.get("bytes")) is int
        and row["bytes"] >= 0
        and isinstance(row.get("sha256"), str)
        and _SHA256.fullmatch(row["sha256"]) is not None
        for row in files
    ):
        return False
    return value["content_sha256"] == _sha256(canonical_json_bytes(files))


def validate_receipt(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
    require_current: bool = True,
) -> list[str]:
    findings: list[str] = []
    try:
        if frozenset(manifest) != _ROOT_FIELDS:
            findings.append("root fields mismatch")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            findings.append("schema version mismatch")
        if manifest.get("evidence_kind") != EVIDENCE_KIND:
            findings.append("evidence kind mismatch")
        if manifest.get("manifest_checksum_sha256") != _checksum(manifest):
            findings.append("manifest checksum mismatch")
        for name in ("source", "candidate", "dataset", "stage"):
            if not _scope_shape_valid(manifest.get(name)):
                findings.append(f"{name} scope shape mismatch")
        source_scope = manifest.get("source")
        source_paths = (
            {
                row.get("path")
                for row in source_scope.get("files", [])
                if isinstance(row, Mapping)
            }
            if isinstance(source_scope, Mapping)
            else set()
        )
        if source_paths != set(SOURCE_PATHS):
            findings.append("source inventory mismatch")
        candidate_scope = manifest.get("candidate")
        candidate_paths = (
            {
                row.get("path")
                for row in candidate_scope.get("files", [])
                if isinstance(row, Mapping)
            }
            if isinstance(candidate_scope, Mapping)
            else set()
        )
        expected_candidate_paths = set(
            _frozen_candidate_paths(repo_root=repo_root)
        )
        if candidate_paths != expected_candidate_paths:
            findings.append("candidate inventory mismatch")
        baseline_scope = manifest.get("baseline_store")
        if (
            not isinstance(baseline_scope, Mapping)
            or not isinstance(baseline_scope.get("name"), str)
            or not _scope_shape_valid(
                {
                    key: baseline_scope.get(key)
                    for key in ("files", "content_sha256")
                }
            )
        ):
            findings.append("baseline store scope shape mismatch")
        claims = manifest.get("claims")
        if (
            not isinstance(claims, Mapping)
            or frozenset(claims) != _CLAIM_FIELDS
            or claims.get("classification") != CLAIMS_CLASSIFICATION
            or claims.get("development_only") is not True
            or claims.get("offline_counterfactual_only") is not True
            or claims.get("counterfactual_policy_evaluated") is not True
            or any(
                claims.get(field) is not False
                for field in (
                    "live_answer_authority",
                    "sealed",
                    "promotion_allowed",
                    "e4_claimed",
                    "e5_claimed",
                    "benchmark_capability_claimed",
                    "independent",
                    "externally_signed",
                    "external_authenticity_established",
                    "production_authority",
                    "firing_is_correctness",
                    "proof_verification_is_benchmark_correctness",
                    "gold_filesystem_isolation_established",
                    "independent_proof_reverification_available",
                    "independent_replay_reverification_available",
                    "gpqa_accuracy_claimed",
                )
            )
        ):
            findings.append("claims mismatch")
        frozen = manifest.get("frozen_candidate")
        candidate = manifest.get("candidate")
        if (
            not isinstance(frozen, Mapping)
            or frozen.get("commit") != FROZEN_CANDIDATE_COMMIT
            or not isinstance(candidate, Mapping)
            or frozen.get("candidate_digest_sha256")
            != candidate.get("content_sha256")
        ):
            findings.append("frozen candidate binding mismatch")
        stage5 = manifest.get("stage5_prerequisite")
        stage5_fields = {
            "path",
            "sha256",
            "schema_version",
            "stage5_status",
            "gate_pass",
            "stage5_failures",
            "prerequisite_passed",
            "frozen_candidate_commit",
            "candidate_source_digest_sha256",
        }
        stage5_mode_valid = False
        if (
            not isinstance(stage5, Mapping)
            or set(stage5) != stage5_fields
            or stage5.get("schema_version") != STAGE5_SCHEMA_VERSION
            or stage5.get("frozen_candidate_commit")
            != FROZEN_CANDIDATE_COMMIT
            or not isinstance(stage5.get("sha256"), str)
            or _SHA256.fullmatch(stage5["sha256"]) is None
            or not isinstance(
                stage5.get("candidate_source_digest_sha256"), str
            )
            or _SHA256.fullmatch(
                stage5["candidate_source_digest_sha256"]
            )
            is None
        ):
            findings.append("Stage 5 prerequisite binding mismatch")
        else:
            expected_stage5_digest, _ = (
                _stage5_frozen_candidate_contract(repo_root=repo_root)
            )
            if (
                stage5.get("candidate_source_digest_sha256")
                != expected_stage5_digest
            ):
                findings.append(
                    "Stage 5 candidate digest does not cross-bind freeze"
                )
            green = (
                stage5.get("stage5_status") == "sealed_green"
                and stage5.get("gate_pass") is True
                and stage5.get("stage5_failures") == 0
                and stage5.get("prerequisite_passed") is True
                and stage5.get("sha256")
                in TRUSTED_STAGE5_GREEN_SHA256
            )
            red = (
                stage5.get("stage5_status")
                == "red_unsealed_diagnostic"
                and stage5.get("gate_pass") is False
                and type(stage5.get("stage5_failures")) is int
                and stage5["stage5_failures"] > 0
                and stage5.get("prerequisite_passed") is False
                and stage5.get("sha256") == EXPECTED_STAGE5_RED_SHA256
            )
            stage5_mode_valid = green or red
            if not stage5_mode_valid:
                findings.append("Stage 5 prerequisite mode is inconsistent")
        protocol = manifest.get("protocol")
        baseline_name = (
            baseline_scope.get("name")
            if isinstance(baseline_scope, Mapping)
            else None
        )
        stage5_status = (
            stage5.get("stage5_status")
            if isinstance(stage5, Mapping)
            else None
        )
        if (
            not isinstance(baseline_name, str)
            or not isinstance(stage5_status, str)
            or protocol
            != _protocol(
                baseline_name,
                stage5_status=stage5_status,
            )
        ):
            findings.append("protocol mismatch")
        gold_separation = (
            protocol.get("gold_separation")
            if isinstance(protocol, Mapping)
            else None
        )
        if (
            not isinstance(gold_separation, Mapping)
            or gold_separation.get("gold_in_worker_arguments") is not False
            or gold_separation.get(
                "gold_filesystem_isolation_established"
            )
            is not False
        ):
            findings.append("gold isolation disclosure mismatch")
        selection = manifest.get("selection")
        fixed_rows, fixed_dataset_bytes = mmlu._load_dataset(repo_root)
        expected_selection = _selection(
            fixed_rows, fixed_dataset_bytes
        )
        if (
            not isinstance(selection, Mapping)
            or frozenset(selection) != mmlu._SELECTION_FIELDS
            or selection.get("dataset_path") != DATASET_PATH
            or selection.get("expected_dataset_sha256")
            != EXPECTED_DATASET_SHA256
            or selection.get("actual_dataset_sha256")
            != EXPECTED_DATASET_SHA256
            or selection.get("expected_item_count") != EXPECTED_ITEMS
            or not isinstance(selection.get("item_ids"), list)
            or len(selection["item_ids"]) != EXPECTED_ITEMS
            or selection != expected_selection
        ):
            findings.append("selection binding mismatch")
        dataset_scope = manifest.get("dataset")
        if isinstance(dataset_scope, Mapping):
            dataset_files = {
                row.get("path"): row.get("sha256")
                for row in dataset_scope.get("files", [])
                if isinstance(row, Mapping)
            }
            if (
                dataset_files.get(DATASET_PATH)
                != EXPECTED_DATASET_SHA256
                or dataset_files.get(GPQA_PATH) != EXPECTED_GPQA_SHA256
            ):
                findings.append("dataset file digest binding mismatch")
        items = manifest.get("items")
        if not isinstance(items, list) or len(items) != EXPECTED_ITEMS:
            findings.append("items denominator mismatch")
        else:
            for ordinal, item in enumerate(items):
                expected_order = (
                    ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
                )
                if (
                    not isinstance(item, Mapping)
                    or item.get("ordinal") != ordinal
                    or item.get("primary_execution_order")
                    != expected_order
                    or item.get("replay_execution_order")
                    != list(reversed(expected_order))
                    or item.get(
                        "gold_absent_from_candidate_arguments"
                    )
                    is not True
                ):
                    findings.append(f"items[{ordinal}] identity/order mismatch")
                    continue
                conditions = item.get("conditions")
                if (
                    not isinstance(conditions, Mapping)
                    or frozenset(conditions) != {"off", "on"}
                ):
                    findings.append(f"items[{ordinal}] conditions mismatch")
                    continue
                for condition in ("off", "on"):
                    findings.extend(
                        _validate_condition(
                            conditions[condition],
                            label=f"items[{ordinal}].{condition}",
                        )
                    )
            try:
                _rescore_fixed_items(items, fixed_rows)
            except BenchmarkEvidenceError as exc:
                findings.append(str(exc))
            prerequisite_passed = (
                stage5.get("prerequisite_passed")
                if isinstance(stage5, Mapping)
                else None
            )
            if type(prerequisite_passed) is not bool:
                findings.append("metrics prerequisite status is invalid")
            elif manifest.get("metrics") != _derive_metrics(
                items, prerequisite_passed=prerequisite_passed
            ):
                findings.append("metrics do not recompute")
        gpqa = manifest.get("gpqa_blocker")
        if (
            not isinstance(gpqa, Mapping)
            or gpqa.get("status") != "blocked_fail_closed"
            or gpqa.get("accuracy_available") is not False
            or gpqa.get("malformed_row_count") != 3
            or gpqa.get("strict_loader_rejected") is not True
            or gpqa.get("dataset_sha256") != EXPECTED_GPQA_SHA256
        ):
            findings.append("GPQA blocker mismatch")
        integrity = manifest.get("integrity")
        red_diagnostic = (
            isinstance(stage5, Mapping)
            and stage5.get("stage5_status")
            == "red_unsealed_diagnostic"
        )
        prerequisite_passed = (
            stage5.get("prerequisite_passed")
            if isinstance(stage5, Mapping)
            else None
        )
        if (
            not isinstance(integrity, Mapping)
            or integrity.get("generic_async_submit_used_for_scoring")
            is not False
            or integrity.get("production_authority") is not False
            or integrity.get("network_isolation_enforced") is not False
            or integrity.get("gold_filesystem_isolation_enforced") is not False
            or integrity.get("proof_payload_embedded") is not False
            or integrity.get("replay_payload_embedded") is not False
            or integrity.get(
                "independent_proof_reverification_available"
            )
            is not False
            or integrity.get(
                "independent_replay_reverification_available"
            )
            is not False
            or integrity.get("promotion_gate_passed") is not False
            or integrity.get("stage5_gate_bound")
            is not prerequisite_passed
            or integrity.get("stage5_red_diagnostic_explicit")
            is not red_diagnostic
            or any(
                integrity.get(field) is not True
                for field in (
                    "source_same_before_after",
                    "candidate_same_before_after",
                    "dataset_same_before_after",
                    "stage_same_before_after",
                    "baseline_store_same_before_after",
                    "candidate_matches_freeze",
                    "stage5_artifact_bound",
                    "measurement_integrity_passed",
                    "same_items_choices_off_on",
                    "gold_absent_from_candidate_arguments_all",
                    "live_answer_invariant_all",
                    "semantic_replay_all",
                    "baseline_store_read_only",
                )
            )
        ):
            findings.append("integrity mismatch")
        if require_current:
            stage5 = manifest.get("stage5_prerequisite")
            baseline = manifest.get("baseline_store")
            if (
                not isinstance(protocol, Mapping)
                or not isinstance(stage5, Mapping)
                or not isinstance(baseline, Mapping)
            ):
                findings.append("current binding metadata missing")
            else:
                current_stage5 = _read_stage5_prerequisite(
                    repo_root / str(stage5.get("path")),
                    allow_red_diagnostic=(
                        stage5.get("stage5_status")
                        == "red_unsealed_diagnostic"
                    ),
                    repo_root=repo_root,
                )
                if dict(stage5) != current_stage5:
                    findings.append("Stage 5 prerequisite differs from current")
                scopes = _current_scopes(
                    baseline_store=str(baseline.get("name")),
                    stage5_relative=str(stage5.get("path")),
                    repo_root=repo_root,
                )
                for name in (
                    "source",
                    "candidate",
                    "dataset",
                    "stage",
                    "baseline_store",
                ):
                    declared = manifest.get(name)
                    expected = (
                        {
                            "name": baseline.get("name"),
                            **scopes[name],
                        }
                        if name == "baseline_store"
                        else scopes[name]
                    )
                    if declared != expected:
                        findings.append(f"{name} differs from current scope")
                if manifest.get("gpqa_blocker") != _gpqa_blocker(
                    repo_root=repo_root
                ):
                    findings.append("GPQA blocker differs from current")
    except Exception as exc:
        findings.append(
            f"receipt validation failed closed: {type(exc).__name__}: {exc}"
        )
    return findings


def build_receipt(
    *,
    stage5_seal_path: Path,
    baseline_store: str,
    diagnostic_with_red_stage5: bool = False,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    if type(diagnostic_with_red_stage5) is not bool:
        raise BenchmarkEvidenceError(
            "diagnostic_with_red_stage5 must be an exact boolean"
        )
    stage5 = _read_stage5_prerequisite(
        stage5_seal_path,
        allow_red_diagnostic=diagnostic_with_red_stage5,
        repo_root=repo_root,
    )
    red_diagnostic = (
        stage5["stage5_status"] == "red_unsealed_diagnostic"
    )
    if diagnostic_with_red_stage5 is not red_diagnostic:
        raise BenchmarkEvidenceError(
            "diagnostic flag and Stage 5 prerequisite mode do not agree"
        )
    rows, dataset_bytes = mmlu._load_dataset(repo_root)
    gpqa = _gpqa_blocker(repo_root=repo_root)
    scopes_before = _current_scopes(
        baseline_store=baseline_store,
        stage5_relative=stage5["path"],
        repo_root=repo_root,
    )
    with tempfile.TemporaryDirectory(
        prefix="atanor-stage6-generic-"
    ) as temporary:
        root = Path(temporary)
        primary_input = root / "primary-input.jsonl"
        replay_input = root / "replay-input.jsonl"
        primary_output = root / "primary-output.json"
        replay_output = root / "replay-output.json"
        _write_worker_input(primary_input, rows, replay=False)
        _write_worker_input(replay_input, rows, replay=True)
        primary = _run_worker(
            primary_input,
            primary_output,
            baseline_store=baseline_store,
        )
        repeated = _run_worker(
            replay_input,
            replay_output,
            baseline_store=baseline_store,
        )
    scopes_after = _current_scopes(
        baseline_store=baseline_store,
        stage5_relative=stage5["path"],
        repo_root=repo_root,
    )
    if scopes_before != scopes_after:
        raise BenchmarkEvidenceError(
            "bound bytes changed during Stage 6 measurement"
        )
    manifest = _assemble_receipt(
        rows=rows,
        dataset_bytes=dataset_bytes,
        primary=primary,
        repeated=repeated,
        baseline_store=baseline_store,
        stage5=stage5,
        scopes=scopes_before,
        gpqa_blocker=gpqa,
    )
    findings = validate_receipt(
        manifest, repo_root=repo_root, require_current=False
    )
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return manifest


def read_receipt(path: Path) -> dict[str, Any]:
    try:
        return strict_json_bytes(
            path.read_bytes(), label="generic-predicate MMLU-Pro receipt"
        )
    except OSError as exc:
        raise BenchmarkEvidenceError("receipt is unreadable") from exc


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--stage5-seal", type=Path, required=True)
    build_parser.add_argument(
        "--baseline-store", default="world_pack_full"
    )
    build_parser.add_argument(
        "--diagnostic-with-red-stage5",
        action="store_true",
        help=(
            "allow only the pinned RED Stage 5 artifact for an explicitly "
            "unsealed diagnostic curve; never enables promotion"
        ),
    )
    build_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("receipt", type=Path)
    validate_parser.add_argument("--historical", action="store_true")

    worker_parser = subparsers.add_parser("_worker")
    worker_parser.add_argument("input", type=Path)
    worker_parser.add_argument("output", type=Path)
    worker_parser.add_argument("--baseline-store", required=True)

    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.command == "_worker":
            _worker(
                arguments.input.resolve(),
                arguments.output.resolve(),
                baseline_store=arguments.baseline_store,
            )
            return 0
        if arguments.command == "validate":
            receipt = read_receipt(arguments.receipt)
            findings = validate_receipt(
                receipt,
                require_current=not arguments.historical,
            )
            print(
                json.dumps(
                    {"valid": not findings, "findings": findings},
                    sort_keys=True,
                )
            )
            return 0 if not findings else 2
        destination = ensure_safe_report_output(REPO, arguments.output)
        if destination.exists():
            raise BenchmarkEvidenceError(
                f"evidence path already exists: {destination}"
            )
        manifest = build_receipt(
            stage5_seal_path=arguments.stage5_seal,
            baseline_store=arguments.baseline_store,
            diagnostic_with_red_stage5=(
                arguments.diagnostic_with_red_stage5
            ),
        )
        write_manifest_exclusive(destination, manifest)
        print(
            json.dumps(
                {
                    "receipt": str(destination.resolve()),
                    "manifest_checksum_sha256": manifest[
                        "manifest_checksum_sha256"
                    ],
                    "metrics": manifest["metrics"],
                    "stage5_status": manifest["stage5_prerequisite"][
                        "stage5_status"
                    ],
                    "promotion_allowed": False,
                    "e4_claimed": False,
                    "e5_claimed": False,
                    "live_answer_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except (BenchmarkEvidenceError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": str(exc), "type": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
