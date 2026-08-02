"""Sealed one-shot evaluator for the GWIP/ARC-I0 capability pilot.

This program is evaluator-owned.  It keeps hidden mechanics, control
policies, RunLease signing, scoring, and verdict authority outside the
candidate process.  The candidate receives only a bounded GoalIR, public
observations/actions through JSON-line RPC, and a detached policy-memory
input.  Candidate-carried receipts, rule labels, digests, and pass flags are
comparison inputs only.

The immutable production chronology is:

    prereg P -> candidate C -> evaluator E -> seed S -> schedule L
    -> write-once attempt -> one execution -> raw evidence -> receipt

No CLI phase in this file activates the production default.  A positive
verdict is limited to the preregistered affine cross-modulus cohort and is not
an ARC benchmark claim.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from scripts import gwip_mechanism_eval as mechanism
from scripts.gwip_capability_design import (
    CapabilityEnvironment,
    CapabilityPair,
    CounterfactualRuleCheck,
    EpisodeOutcome,
    PairRuleEvidence,
    RandomControl,
    ReactiveControl,
    RuleCheckpoint,
    audit_prior_mechanism_nonoverlap,
    build_prior_mechanism_nonoverlap_input,
    canonical_digest,
    derive_capability_metrics,
    generate_capability_pairs,
    load_preregistration,
    private_cohort_digest,
    score_counterfactual_rule_set,
    select_human_exemplar,
)
from scripts.gwip_capability_harness import (
    CapabilityHarness,
    episode_input_digest,
    FORGERY_HOOK_PATHS,
    HARNESS_RESULT_SCHEMA,
    IndependentGateRegistry,
    JITRunLeaseIssuer,
    REQUIRED_HARD_GATES,
    SOURCE_BINDING_SCHEMA,
    WORKER_RESULT_SCHEMA,
    WriteOnceShardStore,
    _unbound_rows,
    apply_forgery_hook,
    canonical_digest as harness_digest,
    validate_semantic_schedule,
)
from scripts.gwip_capability_episode_runner import (
    CandidateEpisodeRunner,
    ThreadSafeEvidenceSink,
    bind_runtime_dependency_root,
    candidate_archive_manifest,
    census_runtime_dependency_sources,
    materialized_runtime_dependencies,
    validate_runtime_dependency_binding,
)
from scripts.gwip_capability_gates import (
    CapabilityGateInputs,
    evaluate_hard_gates,
    make_independent_gate_registry,
)
from scripts.gwip_capability_semantics import canonical_empty_memory
from scripts.gwip_capability_verifier import verify_capability_evidence
from scripts import gwip_capability_semantics as semantics


REPO = Path(__file__).resolve().parents[1]
PREREG_COMMIT = "c560369ecace2c61110e9c6b6849cba1aadd7a1d"
CANDIDATE_COMMIT = "51de7aadf188f9889ff1ea051012693e5aa529e2"
MECHANISM_BASE_COMMIT = "84e63520a2f59df62faaa5dbc74e0bfbb99deabd"
PRIOR_EVIDENCE_COMMIT = "1ebad766b28b242475b1286b7757b1b5a9e92808"

SEED_SCHEMA = "atanor.gwip-capability-seed-manifest.v1"
SEED_RELATIVE_PATH = "data/eval/gwip_capability_seed_manifest_v1.json"
SCHEDULE_RELATIVE_PATH = "data/eval/gwip_capability_semantic_schedule_v1.json"
ATTEMPT_RELATIVE_PATH = "data/eval/gwip_capability_attempt_v1.json"
RAW_RELATIVE_PATH = "data/eval/gwip_capability_raw_evidence_v1.json.gz"
RECEIPT_RELATIVE_PATH = "data/eval/gwip_capability_receipt_v1.json"
AUTHORITY_RELATIVE_PATH = "data/eval/gwip_capability_authority_v1.tar.gz"
PRIOR_SEED_RELATIVE_PATH = "data/eval/gwip_mechanism_seed_manifest_v1.json"
PRIOR_RECEIPT_RELATIVE_PATH = "data/eval/gwip_mechanism_receipt_v1.json"
PREREG_RELATIVE_PATH = "data/eval/gwip_capability_prereg_v1.json"
PREREG_DOC_RELATIVE_PATH = (
    "docs/ATANOR_GWIP_CAPABILITY_PREREG_2026-07-27.md"
)
PREREG_SEALED_PATHS = (
    PREREG_RELATIVE_PATH,
    PREREG_DOC_RELATIVE_PATH,
)

EVALUATOR_SOURCE_PATHS = (
    "scripts/gwip_capability_design.py",
    "scripts/gwip_capability_semantics.py",
    "scripts/gwip_capability_harness.py",
    "scripts/gwip_capability_cycle_verify.py",
    "scripts/gwip_capability_episode_runner.py",
    "scripts/gwip_capability_gates.py",
    "scripts/gwip_capability_verifier.py",
    "scripts/gwip_capability_worker.py",
    "scripts/gwip_capability_eval.py",
    "scripts/gwip_mechanism_eval.py",
)
CANDIDATE_DIRECT_PATHS = (
    "packages/fusion_loop/interactive.py",
    "packages/fusion_loop/interactive_organs.py",
)
CANDIDATE_ALLOWED_PATHS = (
    "packages/fusion_loop/interactive.py",
    "packages/fusion_loop/interactive_organs.py",
    "packages/fusion_loop/tests/test_interactive_loop.py",
    "packages/fusion_loop/tests/test_interactive_rule_transfer.py",
)

PUBLIC_ENVIRONMENT_SCHEMA = "atanor.gwip-capability-public-environment.v1"
ATTEMPT_SCHEMA = "atanor.gwip-capability-attempt.v1"
RAW_SCHEMA = "atanor.gwip-capability-raw-evidence.v1"
RECEIPT_SCHEMA = "atanor.gwip-capability-receipt.v1"
MAX_WORKER_LINE_BYTES = 64 * 1024 * 1024

V1_PREREG_RELATIVE_PATH = PREREG_RELATIVE_PATH
V1_SEED_RELATIVE_PATH = SEED_RELATIVE_PATH
V1_SCHEDULE_RELATIVE_PATH = SCHEDULE_RELATIVE_PATH
V1_ATTEMPT_RELATIVE_PATH = ATTEMPT_RELATIVE_PATH
V1_RAW_RELATIVE_PATH = RAW_RELATIVE_PATH
V1_RECEIPT_RELATIVE_PATH = RECEIPT_RELATIVE_PATH
V1_AUTHORITY_RELATIVE_PATH = AUTHORITY_RELATIVE_PATH

V3_PREREG_COMMIT = "673de62994f54d553ee4e40ea7a2b1de2875d906"
V3_PREREG_RELATIVE_PATH = "data/eval/gwip_capability_prereg_v3.json"
V3_PREREG_DOC_RELATIVE_PATH = (
    "docs/ATANOR_GWIP_CAPABILITY_RESEAL_PREREG_V3_2026-07-27.md"
)
V3_SEED_RELATIVE_PATH = "data/eval/gwip_capability_seed_manifest_v3.json"
V3_SCHEDULE_RELATIVE_PATH = (
    "data/eval/gwip_capability_semantic_schedule_v3.json"
)
V3_ATTEMPT_RELATIVE_PATH = "data/eval/gwip_capability_attempt_v3.json"
V3_RAW_RELATIVE_PATH = "data/eval/gwip_capability_raw_evidence_v3.json.gz"
V3_RECEIPT_RELATIVE_PATH = "data/eval/gwip_capability_receipt_v3.json"
V3_AUTHORITY_RELATIVE_PATH = (
    "data/eval/gwip_capability_authority_v3.tar.gz"
)
V3_SEED_SCHEMA = "atanor.gwip-capability-seed-manifest.v3"
V3_ATTEMPT_SCHEMA = "atanor.gwip-capability-attempt.v3"
V3_RAW_SCHEMA = "atanor.gwip-capability-raw-evidence.v3"
V3_RECEIPT_SCHEMA = "atanor.gwip-capability-receipt.v3"
V1_SEED_COMMIT = "31d4a5ede60aab1e5ddf470be8c987d721519983"
V1_EVALUATOR_COMMIT = "6346519eab4fcb7e9bc841ee860abc9d9068a541"
V1_EVALUATOR_SOURCE_SHA256 = (
    "fb8ea910dd0d510e0e5d4a41a79587d84b32330429f876ca3d0b7c785334ebb2"
)
V3_GATE_FIX_COMMIT = "c7f7161714ab29107b15ffdee9cd840ed5b8f7fd"
V3_RULE_VERIFIER_FIX_COMMIT = (
    "7752bbd430aec0613aca8d20b91c102f4c565934"
)
V3_CANDIDATE_SOURCE_SHA256 = (
    "b5709ea5852b56f447d20238a816fa88d1f7b74128daaf77bb7cfa6c833f30ce"
)
V3_PRIVATE_COHORT_SHA256 = (
    "31d343f80960ebbef860fc75cda46f852ea7fc87dfa579b4461c602c68d30a0b"
)
V3_V1_ARTIFACT_SHA256 = {
    V1_PREREG_RELATIVE_PATH: (
        "12d9bd9f7a22d6463ddae53ac543507fa2e102dea4ce4cd7f8835547d63155da"
    ),
    V1_SEED_RELATIVE_PATH: (
        "fc73d4a1b127ce6bfc0a950dcf9d012cd22d90c7d80261d975c574a3da6e2604"
    ),
    V1_SCHEDULE_RELATIVE_PATH: (
        "17d4e1c75b0a8eb01caa98d62f1f57dd77f01ffd8ba9ec307ed27aff38ec681b"
    ),
    V1_ATTEMPT_RELATIVE_PATH: (
        "ab34458e0cb5ed53e9ced69c5274a3ea993f198347766073b1bf45ca668af936"
    ),
    V1_RAW_RELATIVE_PATH: (
        "0612a080e549918eabfe8f453abba1f8176daf48b5cddd9cff2ff50f02a429c3"
    ),
    V1_RECEIPT_RELATIVE_PATH: (
        "d12d75fdce8c0d97eba53559eb82a29c15ef0ac424e809e758a69ed8833c213a"
    ),
    V1_AUTHORITY_RELATIVE_PATH: (
        "c8da1fc3310198f80b33ff212ab415ed6ba44657d5bdcd238f8aa1c16ea35a95"
    ),
}
V3_V1_RECEIPT_CHECKSUM = (
    "5677e18f9ea900253d0aeabb0c62d4b5a2985d90a27a998402e924b23b2a2cd5"
)
V3_EXPECTED_HARD_GATES = (
    "call_order_and_stop",
    "step_budget_and_pre_mutation_denial",
    "run_lease_direct_authority",
    "run_lease_single_use_and_replay_rejection",
    "adversarial_self_attestation_rejection",
    "complete_lineage",
    "structural_cycle_replay",
    "semantic_reexecution_determinism",
    "fresh_environment_reexecution",
    "candidate_domain_neutrality",
    "candidate_runtime_import_closure",
    "candidate_fixed_source_guard_controls",
)
V3_ALLOWED_EVALUATOR_CHANGED_PATHS = (
    "scripts/gwip_capability_cycle_verify.py",
    "scripts/gwip_capability_eval.py",
    "scripts/gwip_capability_gates.py",
)
V3_V2_ABSENT_PATHS = tuple(
    f"data/eval/gwip_capability_{stem}_v2{suffix}"
    for stem, suffix in (
        ("prereg", ".json"),
        ("seed_manifest", ".json"),
        ("semantic_schedule", ".json"),
        ("attempt", ".json"),
        ("raw_evidence", ".json.gz"),
        ("authority", ".tar.gz"),
        ("receipt", ".json"),
    )
)

_RUN_PROFILE_LOCK = threading.RLock()
_ACTIVE_RUN_PROFILE = "v1"
_ACTIVE_VERIFICATION_LINEAGE_BASE: dict[str, Any] | None = None


class CapabilityEvaluationError(RuntimeError):
    """A frozen evaluator contract or independent witness failed."""


def _raw_file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise CapabilityEvaluationError(
            f"sealed artifact is unreadable: {path}"
        ) from exc


def _v1_artifact_hashes(
    *, repository_root: Path = REPO
) -> dict[str, str]:
    observed = {
        relative: _raw_file_sha256(repository_root / relative)
        for relative in V3_V1_ARTIFACT_SHA256
    }
    if observed != V3_V1_ARTIFACT_SHA256:
        changed = sorted(
            relative
            for relative, expected in V3_V1_ARTIFACT_SHA256.items()
            if observed.get(relative) != expected
        )
        raise CapabilityEvaluationError(
            "v1 capability evidence changed: " + ",".join(changed)
        )
    receipt = _strict_json_bytes(
        (repository_root / V1_RECEIPT_RELATIVE_PATH).read_bytes(),
        label="v1 capability receipt",
    )
    if (
        receipt.get("checksum_sha256") != V3_V1_RECEIPT_CHECKSUM
        or receipt.get("verdict") != "CAPABILITY_RED"
    ):
        raise CapabilityEvaluationError(
            "v1 capability receipt checksum/verdict changed"
        )
    return observed


def _require_v2_absent(*, repository_root: Path = REPO) -> None:
    present = sorted(
        relative
        for relative in V3_V2_ABSENT_PATHS
        if (repository_root / relative).exists()
    )
    if present:
        raise CapabilityEvaluationError(
            "v2 was declared unmaterialized but artifacts exist: "
            + ",".join(present)
        )


def _load_v1_seed_for_v3(
    *, repository_root: Path = REPO
) -> dict[str, Any]:
    path = repository_root / V1_SEED_RELATIVE_PATH
    if _raw_file_sha256(path) != V3_V1_ARTIFACT_SHA256[
        V1_SEED_RELATIVE_PATH
    ]:
        raise CapabilityEvaluationError("v1 seed bytes changed")
    value = _strict_json_bytes(
        path.read_bytes(),
        label="v1 capability seed",
    )
    if (
        value.get("schema_version") != "atanor.gwip-capability-seed-manifest.v1"
        or value.get("candidate_commit") != CANDIDATE_COMMIT
        or value.get("candidate_source_sha256")
        != V3_CANDIDATE_SOURCE_SHA256
        or value.get("private_cohort_sha256")
        != V3_PRIVATE_COHORT_SHA256
    ):
        raise CapabilityEvaluationError("v1 seed identity changed")
    return value


def _v3_dataset_binding(
    *, repository_root: Path = REPO
) -> dict[str, Any]:
    v1_preregistration, v1_preregistration_sha256 = load_preregistration(
        repository_root / V1_PREREG_RELATIVE_PATH
    )
    v3_preregistration, v3_preregistration_sha256 = load_preregistration(
        repository_root / V3_PREREG_RELATIVE_PATH
    )
    if (
        v1_preregistration != v3_preregistration
        or v1_preregistration_sha256
        != V3_V1_ARTIFACT_SHA256[V1_PREREG_RELATIVE_PATH]
        or v3_preregistration_sha256 != v1_preregistration_sha256
    ):
        raise CapabilityEvaluationError(
            "v3 scoring contract differs from v1"
        )
    seed = _load_v1_seed_for_v3(repository_root=repository_root)
    pairs = generate_capability_pairs(
        v1_preregistration,
        generator_seed=seed["generator_seed"],
        generator_nonce=seed["generator_nonce"],
    )
    if (
        len(pairs) != 64
        or private_cohort_digest(pairs) != V3_PRIVATE_COHORT_SHA256
    ):
        raise CapabilityEvaluationError(
            "v3 regenerated cohort differs from v1"
        )
    schedule_path = repository_root / V1_SCHEDULE_RELATIVE_PATH
    schedule = _strict_json_bytes(
        schedule_path.read_bytes(),
        label="v1 capability semantic schedule",
    )
    if (
        _raw_file_sha256(schedule_path)
        != V3_V1_ARTIFACT_SHA256[V1_SCHEDULE_RELATIVE_PATH]
        or type(schedule.get("rows")) is not list
        or len(schedule["rows"]) != 1024
    ):
        raise CapabilityEvaluationError("v1 semantic schedule changed")
    expected_by_ordinal = {
        row.get("ordinal"): row.get("episode_input_sha256")
        for row in schedule["rows"]
        if type(row) is dict
    }
    if set(expected_by_ordinal) != set(range(1024)):
        raise CapabilityEvaluationError(
            "v1 episode input digest census changed"
        )
    inputs = build_episode_inputs(
        pairs,
        schedule_nonce="v3-fixed-dataset-input-audit",
    )
    observed_by_ordinal = {
        ordinal: episode_input_digest(
            goal_ir=value["goal_ir"],
            environment_spec=value["environment_spec"],
        )
        for ordinal, value in inputs.items()
    }
    if observed_by_ordinal != expected_by_ordinal:
        mismatched = sorted(
            ordinal
            for ordinal in range(1024)
            if observed_by_ordinal.get(ordinal)
            != expected_by_ordinal.get(ordinal)
        )
        raise CapabilityEvaluationError(
            "v3 episode input digest differs from v1: "
            + ",".join(str(item) for item in mismatched[:16])
        )
    ordered = [
        {
            "ordinal": ordinal,
            "episode_input_sha256": observed_by_ordinal[ordinal],
        }
        for ordinal in range(1024)
    ]
    return {
        "candidate_episode_count": 1024,
        "pair_count": 64,
        "private_cohort_sha256": V3_PRIVATE_COHORT_SHA256,
        "ordered_episode_input_binding_sha256": canonical_digest(ordered),
        "all_episode_input_digests_equal_v1": True,
        "generator_seed_equal_v1": True,
        "generator_nonce_equal_v1": True,
        "metric_thresholds_equal_v1": True,
        "v1_preregistration_raw_sha256": v1_preregistration_sha256,
        "v3_preregistration_raw_sha256": v3_preregistration_sha256,
    }


def _v3_validate_prepared_schedule(
    schedule: Mapping[str, Any],
    *,
    repository_root: Path = REPO,
) -> str:
    v1_schedule = _strict_json_bytes(
        (repository_root / V1_SCHEDULE_RELATIVE_PATH).read_bytes(),
        label="v1 capability semantic schedule",
    )
    v1_rows = v1_schedule.get("rows")
    v3_rows = schedule.get("rows")
    if (
        type(v1_rows) is not list
        or type(v3_rows) is not list
        or len(v1_rows) != 1024
        or len(v3_rows) != 1024
    ):
        raise CapabilityEvaluationError(
            "v3 semantic schedule row census differs from v1"
        )
    semantic_fields = (
        "ordinal",
        "phase",
        "pair_index",
        "episode_index",
        "start_index",
        "arm",
        "arm_code",
        "memory_source_pair_index",
        "retain_policy_updates",
        "micro_wave",
        "lane",
        "execution_position",
        "environment_seed",
        "policy_seed",
        "step_budget",
        "episode_input_sha256",
    )
    v1_semantics = [
        {field: row.get(field) for field in semantic_fields}
        for row in v1_rows
        if type(row) is dict
    ]
    v3_semantics = [
        {field: row.get(field) for field in semantic_fields}
        for row in v3_rows
        if type(row) is dict
    ]
    if v3_semantics != v1_semantics:
        raise CapabilityEvaluationError(
            "v3 schedule changed dataset semantics or arm ordering"
        )
    return canonical_digest(v3_semantics)


def _v3_lineage_checksum(value: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            key: copy.deepcopy(item)
            for key, item in value.items()
            if key != "checksum_sha256"
        }
    )


def _validate_v3_evaluator_delta(
    *,
    evaluator_commit: str,
    expected_source_sha256: str | None = None,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Independently bind E3 to exactly the two approved fixes plus harness."""

    evaluator_commit = _full_commit(
        evaluator_commit,
        repository_root=repository_root,
    )
    if evaluator_commit == V1_EVALUATOR_COMMIT:
        raise CapabilityEvaluationError(
            "v3 evaluator commit must differ from E1"
        )
    evaluator_git_binding = mechanism.bind_git_paths(
        evaluator_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    if (
        expected_source_sha256 is not None
        and expected_source_sha256
        != evaluator_git_binding.get("source_digest")
    ):
        raise CapabilityEvaluationError(
            "v3 evaluator source digest differs from E3"
        )
    changed_paths = sorted(
        item
        for item in mechanism._git_bytes(
            [
                "diff",
                "--name-only",
                f"{V1_EVALUATOR_COMMIT}..{evaluator_commit}",
                "--",
                *EVALUATOR_SOURCE_PATHS,
            ],
            repository_root=repository_root,
        )
        .decode("utf-8")
        .splitlines()
        if item
    )
    if tuple(changed_paths) != V3_ALLOWED_EVALUATOR_CHANGED_PATHS:
        raise CapabilityEvaluationError(
            "v3 evaluator delta escaped the preregistered source paths"
        )
    if (
        _git_blob(
            evaluator_commit,
            "scripts/gwip_capability_gates.py",
            repository_root=repository_root,
        )
        != _git_blob(
            V3_GATE_FIX_COMMIT,
            "scripts/gwip_capability_gates.py",
            repository_root=repository_root,
        )
        or _git_blob(
            evaluator_commit,
            "scripts/gwip_capability_cycle_verify.py",
            repository_root=repository_root,
        )
        != _git_blob(
            V3_RULE_VERIFIER_FIX_COMMIT,
            "scripts/gwip_capability_cycle_verify.py",
            repository_root=repository_root,
        )
    ):
        raise CapabilityEvaluationError(
            "v3 evaluator changed an approved behavioral fix"
        )
    for relative in EVALUATOR_SOURCE_PATHS:
        if relative in V3_ALLOWED_EVALUATOR_CHANGED_PATHS:
            continue
        if _git_blob(
            evaluator_commit,
            relative,
            repository_root=repository_root,
        ) != _git_blob(
            V1_EVALUATOR_COMMIT,
            relative,
            repository_root=repository_root,
        ):
            raise CapabilityEvaluationError(
                "v3 changed an unapproved evaluator source: " + relative
            )
    return {
        "evaluator_commit": evaluator_commit,
        "evaluator_source_binding": evaluator_git_binding,
        "changed_paths": changed_paths,
    }


def _v3_verification_lineage_base(
    *,
    source_binding: Mapping[str, Any] | None = None,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    _require_v2_absent(repository_root=repository_root)
    v1_hashes = _v1_artifact_hashes(repository_root=repository_root)
    if tuple(REQUIRED_HARD_GATES) != V3_EXPECTED_HARD_GATES:
        raise CapabilityEvaluationError("v3 hard-gate contract changed")
    candidate = mechanism.bind_git_candidate_tree(
        CANDIDATE_COMMIT,
        repository_root=repository_root,
    )
    candidate_unchanged = (
        candidate.get("source_digest") == V3_CANDIDATE_SOURCE_SHA256
        and mechanism._git_working_paths_unchanged(
            CANDIDATE_COMMIT,
            ("packages",),
            repository_root=repository_root,
        )
    )
    if not candidate_unchanged:
        raise CapabilityEvaluationError(
            "v3 candidate/package bytes differ from C"
        )
    evaluator_changed_paths: list[str] = []
    if source_binding is not None:
        if (
            source_binding.get("candidate_commit") != CANDIDATE_COMMIT
            or source_binding.get("candidate_source_sha256")
            != V3_CANDIDATE_SOURCE_SHA256
            or source_binding.get("evaluator_commit") in {
                None,
                V1_EVALUATOR_COMMIT,
            }
        ):
            raise CapabilityEvaluationError(
                "v3 evaluator source binding is malformed"
            )
        evaluator_delta = _validate_v3_evaluator_delta(
            evaluator_commit=str(source_binding["evaluator_commit"]),
            expected_source_sha256=str(
                source_binding["evaluator_source_sha256"]
            ),
            repository_root=repository_root,
        )
        evaluator_changed_paths = evaluator_delta["changed_paths"]
    value: dict[str, Any] = {
        "schema_version": (
            "atanor.gwip-capability-verification-lineage.v3"
        ),
        "operator_sequence_label": "v3",
        "measurement_kind": (
            "fixed_candidate_fixed_dataset_verifier_only_reseal"
        ),
        "materialized_predecessors": [
            {
                "label": "v1",
                "attempt_materialized": True,
                "receipt_path": V1_RECEIPT_RELATIVE_PATH,
                "receipt_raw_sha256": v1_hashes[
                    V1_RECEIPT_RELATIVE_PATH
                ],
                "receipt_checksum_sha256": V3_V1_RECEIPT_CHECKSUM,
                "verdict": "CAPABILITY_RED",
            }
        ],
        "v2": {
            "status": "not_materialized",
            "preregistration_absent": True,
            "attempt_absent": True,
            "raw_evidence_absent": True,
            "receipt_absent": True,
        },
        "allowed_evaluator_delta": [
            {
                "commit": V3_GATE_FIX_COMMIT,
                "scope": (
                    "terminal_stop_state_machine_and_untruncated_failure_count"
                ),
            },
            {
                "commit": V3_RULE_VERIFIER_FIX_COMMIT,
                "scope": "parent_witnessed_per_step_rule_memory_cursor",
            },
        ],
        "preregistration_lineage": {
            "commit": V3_PREREG_COMMIT,
            "machine_path": V3_PREREG_RELATIVE_PATH,
            "human_path": V3_PREREG_DOC_RELATIVE_PATH,
            "scope": "versioned_write_once_paths_and_lineage_only",
        },
        "candidate_binding": {
            "commit": CANDIDATE_COMMIT,
            "source_sha256": candidate["source_digest"],
            "packages_unchanged_from_candidate_commit": True,
        },
        "dataset_binding": _v3_dataset_binding(
            repository_root=repository_root
        ),
        "hard_gate_binding": {
            "count": 12,
            "names": list(REQUIRED_HARD_GATES),
            "identical_to_v1": True,
            "conjunctive": True,
        },
        "v1_artifacts_before": v1_hashes,
        "v1_artifacts_after": None,
        "v1_artifacts_preserved": None,
        "evaluator_source_binding": (
            copy.deepcopy(dict(source_binding))
            if source_binding is not None
            else None
        ),
        "v1_evaluator_binding": {
            "commit": V1_EVALUATOR_COMMIT,
            "source_sha256": V1_EVALUATOR_SOURCE_SHA256,
        },
        "v3_evaluator_changed_paths": evaluator_changed_paths,
        "v3_evaluator_commit": (
            source_binding.get("evaluator_commit")
            if source_binding is not None
            else None
        ),
        "v3_evaluator_source_sha256": (
            source_binding.get("evaluator_source_sha256")
            if source_binding is not None
            else None
        ),
        "production_default_on": False,
        "public_benchmark_claim": False,
        "retry_authorized": False,
    }
    value["checksum_sha256"] = _v3_lineage_checksum(value)
    return value


def _finalize_v3_verification_lineage(
    base: Mapping[str, Any],
    *,
    repository_root: Path = REPO,
    fail_closed: bool,
) -> dict[str, Any]:
    value = copy.deepcopy(dict(base))
    value["pre_attempt_lineage_sha256"] = base.get(
        "checksum_sha256"
    )
    expected_before = value.get("v1_artifacts_before")
    observed_after: dict[str, str] = {}
    preserved = False
    try:
        observed_after = _v1_artifact_hashes(
            repository_root=repository_root
        )
        _require_v2_absent(repository_root=repository_root)
        candidate_preserved = mechanism._git_working_paths_unchanged(
            CANDIDATE_COMMIT,
            ("packages",),
            repository_root=repository_root,
        )
        preserved = (
            observed_after == expected_before
            and candidate_preserved
        )
    except CapabilityEvaluationError:
        if fail_closed:
            raise
    value["v1_artifacts_after"] = observed_after
    value["v1_artifacts_preserved"] = preserved
    value["checksum_sha256"] = _v3_lineage_checksum(value)
    if fail_closed and not preserved:
        raise CapabilityEvaluationError(
            "v1 evidence or candidate changed during v3 execution"
        )
    return value


def _active_verification_lineage(
    *,
    repository_root: Path = REPO,
    fail_closed: bool,
) -> dict[str, Any] | None:
    if _ACTIVE_RUN_PROFILE != "v3":
        return None
    if _ACTIVE_VERIFICATION_LINEAGE_BASE is None:
        raise CapabilityEvaluationError(
            "v3 verification lineage was not initialized"
        )
    return _finalize_v3_verification_lineage(
        _ACTIVE_VERIFICATION_LINEAGE_BASE,
        repository_root=repository_root,
        fail_closed=fail_closed,
    )


@contextlib.contextmanager
def _v3_run_profile() -> Any:
    """Temporarily select immutable v3 artifact names for one CLI process."""

    global _ACTIVE_RUN_PROFILE
    global _ACTIVE_VERIFICATION_LINEAGE_BASE
    names = {
        "PREREG_COMMIT": V3_PREREG_COMMIT,
        "SEED_SCHEMA": V3_SEED_SCHEMA,
        "SEED_RELATIVE_PATH": V3_SEED_RELATIVE_PATH,
        "SCHEDULE_RELATIVE_PATH": V3_SCHEDULE_RELATIVE_PATH,
        "ATTEMPT_RELATIVE_PATH": V3_ATTEMPT_RELATIVE_PATH,
        "RAW_RELATIVE_PATH": V3_RAW_RELATIVE_PATH,
        "RECEIPT_RELATIVE_PATH": V3_RECEIPT_RELATIVE_PATH,
        "AUTHORITY_RELATIVE_PATH": V3_AUTHORITY_RELATIVE_PATH,
        "PREREG_RELATIVE_PATH": V3_PREREG_RELATIVE_PATH,
        "PREREG_DOC_RELATIVE_PATH": V3_PREREG_DOC_RELATIVE_PATH,
        "PREREG_SEALED_PATHS": (
            V3_PREREG_RELATIVE_PATH,
            V3_PREREG_DOC_RELATIVE_PATH,
        ),
        "ATTEMPT_SCHEMA": V3_ATTEMPT_SCHEMA,
        "RAW_SCHEMA": V3_RAW_SCHEMA,
        "RECEIPT_SCHEMA": V3_RECEIPT_SCHEMA,
    }
    with _RUN_PROFILE_LOCK:
        if _ACTIVE_RUN_PROFILE != "v1":
            raise CapabilityEvaluationError(
                "a capability artifact profile is already active"
            )
        saved = {name: globals()[name] for name in names}
        previous_lineage = _ACTIVE_VERIFICATION_LINEAGE_BASE
        try:
            globals().update(names)
            _ACTIVE_RUN_PROFILE = "v3"
            _ACTIVE_VERIFICATION_LINEAGE_BASE = None
            yield
        finally:
            globals().update(saved)
            _ACTIVE_RUN_PROFILE = "v1"
            _ACTIVE_VERIFICATION_LINEAGE_BASE = previous_lineage


@contextlib.contextmanager
def sealed_capability_candidate_source(
    candidate_commit: str = CANDIDATE_COMMIT,
    *,
    repository_root: Path = REPO,
) -> Any:
    """Wrap the mechanism archive with a read-only root-directory boundary."""

    with mechanism.sealed_candidate_source(
        candidate_commit,
        repository_root=repository_root,
    ) as (root, binding):
        root_mode = stat.S_IMODE(root.stat().st_mode)
        root.chmod(stat.S_IREAD | stat.S_IEXEC)
        try:
            if stat.S_IMODE(root.stat().st_mode) & (
                stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
            ):
                raise CapabilityEvaluationError(
                    "candidate archive root did not become read-only"
                )
            yield root, binding
        finally:
            root.chmod(root_mode | stat.S_IWRITE)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _strict_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise CapabilityEvaluationError(
                    f"{label} contains duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CapabilityEvaluationError(
                    f"{label} contains non-finite number {token}"
                )
            ),
        )
    except CapabilityEvaluationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CapabilityEvaluationError(f"{label} is not strict JSON") from exc
    if type(value) is not dict:
        raise CapabilityEvaluationError(f"{label} root is not an exact object")
    return value


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return _strict_json_bytes(Path(path).read_bytes(), label=label)
    except OSError as exc:
        raise CapabilityEvaluationError(f"{label} is unreadable") from exc


def _write_once(path: Path, payload: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise CapabilityEvaluationError(
            f"write-once artifact already exists: {destination}"
        ) from exc
    if destination.read_bytes() != payload:
        raise CapabilityEvaluationError(
            f"write-once artifact readback failed: {destination}"
        )


def _full_commit(value: str, *, repository_root: Path = REPO) -> str:
    raw = mechanism._git_bytes(
        ["rev-parse", f"{value}^{{commit}}"],
        repository_root=repository_root,
    ).decode("ascii").strip()
    if len(raw) != 40 or any(char not in "0123456789abcdef" for char in raw):
        raise CapabilityEvaluationError(f"invalid commit: {value}")
    return raw


def _head(*, repository_root: Path = REPO) -> str:
    return _full_commit("HEAD", repository_root=repository_root)


def _git_blob(
    commit: str,
    relative_path: str,
    *,
    repository_root: Path = REPO,
) -> bytes:
    return mechanism._git_bytes(
        ["show", f"{commit}:{relative_path}"],
        repository_root=repository_root,
    )


def _require_ancestry(
    older: str,
    newer: str,
    *,
    strict: bool = True,
    repository_root: Path = REPO,
) -> None:
    if not mechanism._git_is_ancestor(
        older,
        newer,
        strict=strict,
        repository_root=repository_root,
    ):
        raise CapabilityEvaluationError(
            f"required git ancestry is absent: {older} -> {newer}"
        )


def _require_unchanged(
    older: str,
    newer: str,
    paths: Sequence[str],
    *,
    repository_root: Path = REPO,
) -> None:
    if not mechanism._git_paths_unchanged(
        older,
        newer,
        paths,
        repository_root=repository_root,
    ):
        raise CapabilityEvaluationError(
            f"sealed paths changed between {older} and {newer}: {paths}"
        )


def _candidate_restricted_diff(
    *,
    candidate_commit: str = CANDIDATE_COMMIT,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    raw = mechanism._git_bytes(
        [
            "diff",
            "--name-only",
            MECHANISM_BASE_COMMIT,
            candidate_commit,
            "--",
            "packages",
        ],
        repository_root=repository_root,
    ).decode("utf-8")
    changed = sorted(item for item in raw.splitlines() if item)
    unexpected = sorted(set(changed) - set(CANDIDATE_ALLOWED_PATHS))
    missing_direct = sorted(set(CANDIDATE_DIRECT_PATHS) - set(changed))
    result = {
        "base_commit": MECHANISM_BASE_COMMIT,
        "candidate_commit": candidate_commit,
        "changed_paths": changed,
        "allowed_paths": list(CANDIDATE_ALLOWED_PATHS),
        "unexpected_paths": unexpected,
        "missing_direct_paths": missing_direct,
        "passed": not unexpected and not missing_direct,
    }
    if not result["passed"]:
        raise CapabilityEvaluationError(
            "candidate changed paths outside the frozen allowlist"
        )
    return result


def _sealed_preregistration_binding(
    *,
    comparison_commit: str,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Bind working/comparison preregistration bytes to the independent P seal."""

    comparison = _full_commit(
        comparison_commit,
        repository_root=repository_root,
    )
    _require_ancestry(
        PREREG_COMMIT,
        comparison,
        strict=True,
        repository_root=repository_root,
    )
    records: list[dict[str, Any]] = []
    for relative in PREREG_SEALED_PATHS:
        at_p = _git_blob(
            PREREG_COMMIT,
            relative,
            repository_root=repository_root,
        )
        at_comparison = _git_blob(
            comparison,
            relative,
            repository_root=repository_root,
        )
        working = (repository_root / relative).read_bytes()
        if at_comparison != at_p or working != at_p:
            raise CapabilityEvaluationError(
                f"preregistration bytes changed after P: {relative}"
            )
        records.append(
            {
                "path": relative,
                "raw_sha256": hashlib.sha256(at_p).hexdigest(),
                "size_bytes": len(at_p),
            }
        )
    preregistration, working_raw_sha256 = load_preregistration(
        repository_root / PREREG_RELATIVE_PATH
    )
    json_record = next(
        item for item in records if item["path"] == PREREG_RELATIVE_PATH
    )
    if working_raw_sha256 != json_record["raw_sha256"]:
        raise CapabilityEvaluationError(
            "loaded preregistration digest differs from P blob"
        )
    return {
        "commit": PREREG_COMMIT,
        "files": records,
        "binding_sha256": canonical_digest(records),
        "json_raw_sha256": working_raw_sha256,
        "validated_pair_count": preregistration["pair_count"],
    }


def _source_binding(
    *,
    candidate_commit: str,
    evaluator_commit: str,
    seed_raw_sha256: str,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    candidate = mechanism.bind_git_candidate_tree(
        candidate_commit,
        repository_root=repository_root,
    )
    evaluator = mechanism.bind_git_paths(
        evaluator_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    return {
        "schema_version": SOURCE_BINDING_SCHEMA,
        "candidate_commit": candidate_commit,
        "candidate_source_sha256": candidate["source_digest"],
        "evaluator_commit": evaluator_commit,
        "evaluator_source_sha256": evaluator["source_digest"],
        "seed_manifest_sha256": seed_raw_sha256,
    }


def _probe_clean_source_binding(
    expected: Mapping[str, Any],
    *,
    seed_path: Path,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    candidate_commit = str(expected["candidate_commit"])
    evaluator_commit = str(expected["evaluator_commit"])
    if not mechanism._git_working_paths_unchanged(
        candidate_commit,
        ("packages",),
        repository_root=repository_root,
    ):
        raise CapabilityEvaluationError("working candidate packages changed")
    candidate = mechanism.bind_git_candidate_tree(
        candidate_commit,
        repository_root=repository_root,
    )
    evaluator_working = mechanism.bind_working_paths(
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    evaluator_git = mechanism.bind_git_paths(
        evaluator_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    seed_sha = hashlib.sha256(Path(seed_path).read_bytes()).hexdigest()
    actual = {
        "schema_version": SOURCE_BINDING_SCHEMA,
        "candidate_commit": candidate_commit,
        "candidate_source_sha256": candidate["source_digest"],
        "evaluator_commit": evaluator_commit,
        "evaluator_source_sha256": evaluator_git["source_digest"],
        "seed_manifest_sha256": seed_sha,
    }
    if (
        evaluator_working["files"] != evaluator_git["files"]
        or actual != dict(expected)
    ):
        raise CapabilityEvaluationError(
            "candidate/evaluator/seed clean source binding mismatch"
        )
    return actual


def _prior_mechanism_inventory(
    *,
    repository_root: Path = REPO,
) -> tuple[Any, dict[str, Any]]:
    seed_path = repository_root / PRIOR_SEED_RELATIVE_PATH
    receipt_path = repository_root / PRIOR_RECEIPT_RELATIVE_PATH
    prior_commit = _full_commit(
        PRIOR_EVIDENCE_COMMIT,
        repository_root=repository_root,
    )
    seed_raw = seed_path.read_bytes()
    receipt_raw = receipt_path.read_bytes()
    if (
        seed_raw
        != _git_blob(
            prior_commit,
            PRIOR_SEED_RELATIVE_PATH,
            repository_root=repository_root,
        )
        or receipt_raw
        != _git_blob(
            prior_commit,
            PRIOR_RECEIPT_RELATIVE_PATH,
            repository_root=repository_root,
        )
    ):
        raise CapabilityEvaluationError(
            "prior mechanism seed/receipt differ from their immutable evidence seal"
        )
    manifest = _strict_json_bytes(
        seed_raw,
        label="prior mechanism seed manifest",
    )
    receipt = _strict_json_bytes(
        receipt_raw,
        label="prior mechanism receipt",
    )
    if (
        receipt.get("checksum_sha256")
        != mechanism.receipt_checksum(receipt)
        or receipt.get("hard_gates_passed") is not True
        or receipt.get("verdict") != "MECHANISM_GREEN"
    ):
        raise CapabilityEvaluationError(
            "prior mechanism receipt checksum/verdict is invalid"
        )
    preregistration, prereg_raw_sha256 = mechanism.load_preregistration()
    if (
        manifest.get("schema_version")
        != "atanor.gwip-mechanism-seed-manifest.v1"
        or manifest.get("preregistration_raw_sha256") != prereg_raw_sha256
    ):
        raise CapabilityEvaluationError(
            "prior mechanism seed/preregistration binding mismatch"
        )
    mechanics = mechanism.generate_hidden_mechanics(
        preregistration,
        generator_seed=manifest["generator_seed"],
        generator_nonce=manifest["generator_nonce"],
    )
    cohort_sha = mechanism.private_cohort_digest(mechanics)
    if (
        receipt.get("cohort_binding", {}).get("private_cohort_sha256")
        != cohort_sha
    ):
        raise CapabilityEvaluationError(
            "regenerated prior mechanism cohort differs from sealed receipt"
        )
    prior = build_prior_mechanism_nonoverlap_input(
        [item.private_dict() for item in mechanics],
        cohort_binding=cohort_sha,
        payload_cues=(),
    )
    binding = {
        "evidence_commit": prior_commit,
        "seed_manifest_raw_sha256": hashlib.sha256(seed_raw).hexdigest(),
        "receipt_raw_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "receipt_checksum_sha256": receipt["checksum_sha256"],
        "private_cohort_sha256": cohort_sha,
        "mechanic_count": len(mechanics),
        "observation_token_count": len(prior.observation_tokens),
        "transition_edge_token_count": len(prior.transition_edge_tokens),
    }
    return prior, binding


def _validate_seed_manifest(
    value: Mapping[str, Any],
    *,
    repository_root: Path = REPO,
) -> None:
    fields = {
        "schema_version",
        "preregistration_commit",
        "preregistration_raw_sha256",
        "preregistration_binding",
        "candidate_commit",
        "candidate_source_sha256",
        "evaluator_commit",
        "evaluator_source_sha256",
        "generator_seed",
        "generator_nonce",
        "private_cohort_sha256",
        "prior_mechanism_binding",
        "nonoverlap_audit",
        "candidate_restricted_diff",
        "candidate_domain_audit",
        "runtime_dependency_binding",
        "candidate_policy_seed",
        "environment_seed_rule",
        "target_arm_schedule",
        "production_default_on",
        "public_benchmark_claim",
    }
    if type(value) is not dict or set(value) != fields:
        raise CapabilityEvaluationError("capability seed manifest fields mismatch")
    if value.get("schema_version") != SEED_SCHEMA:
        raise CapabilityEvaluationError("capability seed manifest schema mismatch")
    preregistration, prereg_raw_sha256 = load_preregistration(
        repository_root / PREREG_RELATIVE_PATH
    )
    prereg_binding = _sealed_preregistration_binding(
        comparison_commit=value.get("evaluator_commit", ""),
        repository_root=repository_root,
    )
    if (
        value.get("preregistration_commit") != PREREG_COMMIT
        or value.get("preregistration_raw_sha256") != prereg_raw_sha256
        or value.get("preregistration_binding") != prereg_binding
        or value.get("candidate_commit") != CANDIDATE_COMMIT
        or value.get("candidate_policy_seed") != 0
        or value.get("environment_seed_rule")
        != "support_episode_or_target_start_index"
        or value.get("target_arm_schedule") != "fixed_six_permutation_latin"
        or value.get("production_default_on") is not False
        or value.get("public_benchmark_claim") is not False
    ):
        raise CapabilityEvaluationError("capability seed fixed fields mismatch")
    _require_ancestry(
        CANDIDATE_COMMIT,
        str(value.get("evaluator_commit", "")),
        strict=True,
        repository_root=repository_root,
    )
    restricted = _candidate_restricted_diff(
        repository_root=repository_root
    )
    domain = mechanism.audit_candidate_sources(
        [repository_root / item for item in CANDIDATE_DIRECT_PATHS],
        repository_root=repository_root,
    )
    runtime_dependencies = census_runtime_dependency_sources(
        repository_root=repository_root
    )
    if (
        value.get("candidate_restricted_diff") != restricted
        or value.get("candidate_domain_audit") != domain
        or value.get("runtime_dependency_binding")
        != runtime_dependencies
        or restricted.get("passed") is not True
        or domain.get("passed") is not True
    ):
        raise CapabilityEvaluationError(
            "capability seed candidate audit evidence is not independently reproduced"
        )
    pairs = generate_capability_pairs(
        preregistration,
        generator_seed=value["generator_seed"],
        generator_nonce=value["generator_nonce"],
    )
    if private_cohort_digest(pairs) != value.get("private_cohort_sha256"):
        raise CapabilityEvaluationError("capability seed cohort digest mismatch")
    if _ACTIVE_RUN_PROFILE == "v3":
        v1_seed = _load_v1_seed_for_v3(
            repository_root=repository_root
        )
        if (
            value.get("generator_seed") != v1_seed["generator_seed"]
            or value.get("generator_nonce") != v1_seed["generator_nonce"]
            or value.get("private_cohort_sha256")
            != V3_PRIVATE_COHORT_SHA256
        ):
            raise CapabilityEvaluationError(
                "v3 seed did not reuse the exact v1 cohort"
            )
        binding = _v3_dataset_binding(
            repository_root=repository_root
        )
        if (
            binding["all_episode_input_digests_equal_v1"] is not True
            or binding["candidate_episode_count"] != 1024
        ):
            raise CapabilityEvaluationError(
                "v3 seed episode inputs differ from v1"
            )
    prior, prior_binding = _prior_mechanism_inventory(
        repository_root=repository_root
    )
    nonoverlap = audit_prior_mechanism_nonoverlap(pairs, prior)
    if (
        prior_binding != value.get("prior_mechanism_binding")
        or nonoverlap != value.get("nonoverlap_audit")
        or nonoverlap.get("passed") is not True
    ):
        raise CapabilityEvaluationError(
            "capability seed prior non-overlap binding mismatch"
        )


def create_seed_manifest(
    *,
    evaluator_commit: str,
    output_path: Path = REPO / SEED_RELATIVE_PATH,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Create S once, only after the exact evaluator commit E exists."""

    evaluator_commit = _full_commit(
        evaluator_commit,
        repository_root=repository_root,
    )
    if _head(repository_root=repository_root) != evaluator_commit:
        raise CapabilityEvaluationError(
            "seed creation requires HEAD to equal evaluator seal E"
        )
    _require_ancestry(
        PREREG_COMMIT,
        CANDIDATE_COMMIT,
        strict=True,
        repository_root=repository_root,
    )
    _require_ancestry(
        CANDIDATE_COMMIT,
        evaluator_commit,
        strict=True,
        repository_root=repository_root,
    )
    _require_unchanged(
        CANDIDATE_COMMIT,
        evaluator_commit,
        ("packages",),
        repository_root=repository_root,
    )
    if not mechanism._git_working_paths_unchanged(
        CANDIDATE_COMMIT,
        ("packages",),
        repository_root=repository_root,
    ):
        raise CapabilityEvaluationError("working packages differ from candidate C")
    evaluator_git = mechanism.bind_git_paths(
        evaluator_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    evaluator_working = mechanism.bind_working_paths(
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    if evaluator_working["files"] != evaluator_git["files"]:
        raise CapabilityEvaluationError(
            "working evaluator bytes differ from evaluator E"
        )
    restricted = _candidate_restricted_diff(
        repository_root=repository_root
    )
    domain = mechanism.audit_candidate_sources(
        [repository_root / item for item in CANDIDATE_DIRECT_PATHS],
        repository_root=repository_root,
    )
    if domain.get("passed") is not True:
        raise CapabilityEvaluationError("candidate domain audit failed")
    preregistration, prereg_raw_sha256 = load_preregistration()
    prereg_binding = _sealed_preregistration_binding(
        comparison_commit=evaluator_commit,
        repository_root=repository_root,
    )
    generator_seed = secrets.token_hex(32)
    generator_nonce = secrets.token_urlsafe(32)
    pairs = generate_capability_pairs(
        preregistration,
        generator_seed=generator_seed,
        generator_nonce=generator_nonce,
    )
    prior, prior_binding = _prior_mechanism_inventory(
        repository_root=repository_root
    )
    nonoverlap = audit_prior_mechanism_nonoverlap(pairs, prior)
    if nonoverlap.get("passed") is not True:
        raise CapabilityEvaluationError(
            "fresh capability cohort overlaps the prior mechanism cohort"
        )
    candidate_git = mechanism.bind_git_candidate_tree(
        CANDIDATE_COMMIT,
        repository_root=repository_root,
    )
    runtime_dependencies = census_runtime_dependency_sources(
        repository_root=repository_root
    )
    manifest = {
        "schema_version": SEED_SCHEMA,
        "preregistration_commit": PREREG_COMMIT,
        "preregistration_raw_sha256": prereg_raw_sha256,
        "preregistration_binding": prereg_binding,
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_source_sha256": candidate_git["source_digest"],
        "evaluator_commit": evaluator_commit,
        "evaluator_source_sha256": evaluator_git["source_digest"],
        "generator_seed": generator_seed,
        "generator_nonce": generator_nonce,
        "private_cohort_sha256": private_cohort_digest(pairs),
        "prior_mechanism_binding": prior_binding,
        "nonoverlap_audit": nonoverlap,
        "candidate_restricted_diff": restricted,
        "candidate_domain_audit": domain,
        "runtime_dependency_binding": runtime_dependencies,
        "candidate_policy_seed": 0,
        "environment_seed_rule": (
            "support_episode_or_target_start_index"
        ),
        "target_arm_schedule": "fixed_six_permutation_latin",
        "production_default_on": False,
        "public_benchmark_claim": False,
    }
    _validate_seed_manifest(manifest, repository_root=repository_root)
    _write_once(output_path, _json_bytes(manifest))
    return {
        "path": str(Path(output_path).resolve()),
        "raw_sha256": hashlib.sha256(Path(output_path).read_bytes()).hexdigest(),
        "private_cohort_sha256": manifest["private_cohort_sha256"],
    }


def create_v3_seed_manifest(
    *,
    evaluator_commit: str,
    output_path: Path = REPO / V3_SEED_RELATIVE_PATH,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Bind E3 to the exact v1 seed/nonce; never sample another cohort."""

    _v1_artifact_hashes(repository_root=repository_root)
    _require_v2_absent(repository_root=repository_root)
    dataset_binding = _v3_dataset_binding(
        repository_root=repository_root
    )
    v1_seed = _load_v1_seed_for_v3(
        repository_root=repository_root
    )
    with _v3_run_profile():
        evaluator_commit = _full_commit(
            evaluator_commit,
            repository_root=repository_root,
        )
        if _head(repository_root=repository_root) != evaluator_commit:
            raise CapabilityEvaluationError(
                "v3 seed creation requires HEAD to equal evaluator seal E3"
            )
        for ancestor in (
            CANDIDATE_COMMIT,
            V3_GATE_FIX_COMMIT,
            V3_RULE_VERIFIER_FIX_COMMIT,
            V3_PREREG_COMMIT,
        ):
            _require_ancestry(
                ancestor,
                evaluator_commit,
                strict=True,
                repository_root=repository_root,
            )
        _require_unchanged(
            CANDIDATE_COMMIT,
            evaluator_commit,
            ("packages",),
            repository_root=repository_root,
        )
        if not mechanism._git_working_paths_unchanged(
            CANDIDATE_COMMIT,
            ("packages",),
            repository_root=repository_root,
        ):
            raise CapabilityEvaluationError(
                "working packages differ from candidate C"
            )
        evaluator_delta = _validate_v3_evaluator_delta(
            evaluator_commit=evaluator_commit,
            repository_root=repository_root,
        )
        evaluator_git = evaluator_delta["evaluator_source_binding"]
        evaluator_working = mechanism.bind_working_paths(
            EVALUATOR_SOURCE_PATHS,
            repository_root=repository_root,
        )
        if evaluator_working["files"] != evaluator_git["files"]:
            raise CapabilityEvaluationError(
                "working evaluator bytes differ from evaluator E3"
            )
        _v3_verification_lineage_base(
            source_binding={
                "schema_version": SOURCE_BINDING_SCHEMA,
                "candidate_commit": CANDIDATE_COMMIT,
                "candidate_source_sha256": V3_CANDIDATE_SOURCE_SHA256,
                "evaluator_commit": evaluator_commit,
                "evaluator_source_sha256": evaluator_git[
                    "source_digest"
                ],
                "seed_manifest_sha256": "0" * 64,
            },
            repository_root=repository_root,
        )
        preregistration, prereg_raw_sha256 = load_preregistration(
            repository_root / V3_PREREG_RELATIVE_PATH
        )
        prereg_binding = _sealed_preregistration_binding(
            comparison_commit=evaluator_commit,
            repository_root=repository_root,
        )
        pairs = generate_capability_pairs(
            preregistration,
            generator_seed=v1_seed["generator_seed"],
            generator_nonce=v1_seed["generator_nonce"],
        )
        if (
            private_cohort_digest(pairs) != V3_PRIVATE_COHORT_SHA256
            or dataset_binding[
                "all_episode_input_digests_equal_v1"
            ]
            is not True
        ):
            raise CapabilityEvaluationError(
                "v3 fixed dataset binding failed before seed write"
            )
        prior, prior_binding = _prior_mechanism_inventory(
            repository_root=repository_root
        )
        nonoverlap = audit_prior_mechanism_nonoverlap(pairs, prior)
        if nonoverlap.get("passed") is not True:
            raise CapabilityEvaluationError(
                "reused v1 cohort failed the frozen non-overlap audit"
            )
        restricted = _candidate_restricted_diff(
            repository_root=repository_root
        )
        domain = mechanism.audit_candidate_sources(
            [
                repository_root / item
                for item in CANDIDATE_DIRECT_PATHS
            ],
            repository_root=repository_root,
        )
        candidate_git = mechanism.bind_git_candidate_tree(
            CANDIDATE_COMMIT,
            repository_root=repository_root,
        )
        if (
            candidate_git["source_digest"]
            != V3_CANDIDATE_SOURCE_SHA256
        ):
            raise CapabilityEvaluationError(
                "v3 candidate source digest differs from C"
            )
        manifest = {
            "schema_version": V3_SEED_SCHEMA,
            "preregistration_commit": V3_PREREG_COMMIT,
            "preregistration_raw_sha256": prereg_raw_sha256,
            "preregistration_binding": prereg_binding,
            "candidate_commit": CANDIDATE_COMMIT,
            "candidate_source_sha256": candidate_git["source_digest"],
            "evaluator_commit": evaluator_commit,
            "evaluator_source_sha256": evaluator_git["source_digest"],
            "generator_seed": v1_seed["generator_seed"],
            "generator_nonce": v1_seed["generator_nonce"],
            "private_cohort_sha256": V3_PRIVATE_COHORT_SHA256,
            "prior_mechanism_binding": prior_binding,
            "nonoverlap_audit": nonoverlap,
            "candidate_restricted_diff": restricted,
            "candidate_domain_audit": domain,
            "runtime_dependency_binding": (
                census_runtime_dependency_sources(
                    repository_root=repository_root
                )
            ),
            "candidate_policy_seed": 0,
            "environment_seed_rule": (
                "support_episode_or_target_start_index"
            ),
            "target_arm_schedule": "fixed_six_permutation_latin",
            "production_default_on": False,
            "public_benchmark_claim": False,
        }
        _validate_seed_manifest(
            manifest,
            repository_root=repository_root,
        )
        _write_once(output_path, _json_bytes(manifest))
        return {
            "path": str(Path(output_path).resolve()),
            "raw_sha256": _raw_file_sha256(output_path),
            "private_cohort_sha256": manifest[
                "private_cohort_sha256"
            ],
            "ordered_episode_input_binding_sha256": (
                dataset_binding[
                    "ordered_episode_input_binding_sha256"
                ]
            ),
            "reused_v1_seed_and_nonce": True,
        }


def load_sealed_seed(
    *,
    seed_commit: str,
    seed_path: Path | None = None,
    repository_root: Path = REPO,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if seed_path is None:
        seed_path = repository_root / SEED_RELATIVE_PATH
    seed_commit = _full_commit(
        seed_commit,
        repository_root=repository_root,
    )
    raw = Path(seed_path).read_bytes()
    committed = _git_blob(
        seed_commit,
        SEED_RELATIVE_PATH,
        repository_root=repository_root,
    )
    if raw != committed:
        raise CapabilityEvaluationError(
            "working capability seed differs from committed S"
        )
    value = _strict_json_bytes(raw, label="capability seed manifest")
    _validate_seed_manifest(value, repository_root=repository_root)
    _require_ancestry(
        value["candidate_commit"],
        seed_commit,
        strict=True,
        repository_root=repository_root,
    )
    _require_ancestry(
        value["evaluator_commit"],
        seed_commit,
        strict=True,
        repository_root=repository_root,
    )
    _require_unchanged(
        value["candidate_commit"],
        seed_commit,
        ("packages",),
        repository_root=repository_root,
    )
    _require_unchanged(
        value["evaluator_commit"],
        seed_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    source = _source_binding(
        candidate_commit=value["candidate_commit"],
        evaluator_commit=value["evaluator_commit"],
        seed_raw_sha256=hashlib.sha256(raw).hexdigest(),
        repository_root=repository_root,
    )
    if (
        source["candidate_source_sha256"]
        != value["candidate_source_sha256"]
        or source["evaluator_source_sha256"]
        != value["evaluator_source_sha256"]
    ):
        raise CapabilityEvaluationError(
            "capability seed source digests mismatch"
        )
    return value, {
        "commit": seed_commit,
        "path": SEED_RELATIVE_PATH,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "source_binding": source,
    }


def _goal_ir_input(environment: CapabilityEnvironment, index: int) -> dict[str, Any]:
    return {
        "statement": "Satisfy the structured target constraint.",
        "origin": "explicit_user",
        "priority": 50,
        "parent_goal_ids": [],
        "constraints": [],
        "metadata": environment.goal_metadata(index),
    }


def _public_environment_input(
    environment: CapabilityEnvironment,
    index: int,
) -> dict[str, Any]:
    episode = environment.episodes[index]
    return {
        "schema_version": PUBLIC_ENVIRONMENT_SCHEMA,
        "observation_schema_version": environment.schema_version,
        "start_ref": episode.start_ref,
        "goal_ref": episode.goal_ref,
        "valid_actions": list(environment.public_actions()),
    }


def build_episode_inputs(
    pairs: Sequence[CapabilityPair],
    *,
    schedule_nonce: str,
) -> dict[int, dict[str, Any]]:
    rows = _unbound_rows(
        pair_count=len(pairs),
        schedule_nonce=schedule_nonce,
    )
    output: dict[int, dict[str, Any]] = {}
    for row in rows:
        pair = pairs[row["pair_index"]]
        if row["phase"] == "support":
            environment = pair.source
            index = row["episode_index"]
        else:
            environment = pair.target
            index = row["start_index"]
        output[row["ordinal"]] = {
            "goal_ir": _goal_ir_input(environment, index),
            "environment_spec": _public_environment_input(
                environment,
                index,
            ),
        }
    return output


class EvaluatorCapabilityEnvironment:
    """Parent-owned exact environment; hidden transition truth never crosses RPC."""

    def __init__(
        self,
        environment: CapabilityEnvironment,
        *,
        episode_index: int,
        step_budget: int = 24,
    ) -> None:
        if (
            type(episode_index) is not int
            or not 0 <= episode_index < len(environment.episodes)
            or step_budget != 24
        ):
            raise CapabilityEvaluationError(
                "capability environment episode/budget invalid"
            )
        self.environment = environment
        self.episode_index = episode_index
        self.step_budget = step_budget
        self._state_ref: str | None = None
        self._steps = 0
        self._reset = False
        self._stopped = False
        self._log: list[dict[str, Any]] = []

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._log)

    @property
    def current_state_ref(self) -> str:
        if self._state_ref is None:
            raise CapabilityEvaluationError("environment has not reset")
        return self._state_ref

    @property
    def episode(self) -> Any:
        return self.environment.episodes[self.episode_index]

    def _observation(self) -> dict[str, Any]:
        return self.environment.observation(
            self.current_state_ref,
            goal_ref=self.episode.goal_ref,
        )

    def _require_live(self) -> None:
        if not self._reset or self._stopped:
            raise CapabilityEvaluationError("environment is not live")

    def reset(self, seed: int) -> dict[str, Any]:
        if self._reset or seed != self.episode_index:
            raise CapabilityEvaluationError("environment reset binding invalid")
        self._state_ref = self.episode.start_ref
        self._steps = 0
        self._reset = True
        result = {"reset": True}
        self._log.append(
            {
                "operation": "reset",
                "seed": seed,
                "result": copy.deepcopy(result),
            }
        )
        return result

    def observe(self) -> dict[str, Any]:
        self._require_live()
        result = self._observation()
        self._log.append(
            {
                "operation": "observe",
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result

    def valid_actions(self) -> list[dict[str, Any]]:
        self._require_live()
        result = list(self.environment.public_actions())
        self._log.append(
            {
                "operation": "valid_actions",
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result

    def step(self, action_id: str) -> dict[str, Any]:
        self._require_live()
        if (
            type(action_id) is not str
            or action_id
            not in {
                item.action_ref for item in self.environment.actions
            }
        ):
            raise CapabilityEvaluationError(
                "step action is outside evaluator valid set"
            )
        if self._steps >= self.step_budget:
            raise CapabilityEvaluationError(
                "step budget exhausted before environment mutation"
            )
        before = self.current_state_ref
        after = self.environment.transition(before, action_id)
        self._state_ref = after
        step_index = self._steps
        self._steps += 1
        observation = self._observation()
        success = after == self.episode.goal_ref
        result = {
            "observation": observation,
            "terminal": success,
            "success": success,
            "stop_reason": "goal_reached" if success else None,
        }
        self._log.append(
            {
                "operation": "step",
                "step_index": step_index,
                "action_id": action_id,
                "before_state_ref": before,
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result

    def stop(self, reason: str) -> dict[str, Any]:
        self._require_live()
        if type(reason) is not str or not reason:
            raise CapabilityEvaluationError("environment stop reason invalid")
        self._stopped = True
        result = {
            "stopped": True,
            "reason": reason,
            "steps": self._steps,
            "success": self.current_state_ref == self.episode.goal_ref,
        }
        self._log.append(
            {
                "operation": "stop",
                "result": copy.deepcopy(result),
                "result_sha256": canonical_digest(result),
            }
        )
        return result


def audit_call_order(
    call_log: Sequence[Mapping[str, Any]],
    *,
    step_budget: int = 24,
) -> dict[str, Any]:
    findings: list[str] = []
    phase = "reset"
    expected_step = 0
    stop_count = 0
    for row in call_log:
        operation = row.get("operation")
        if phase == "reset":
            if operation != "reset":
                findings.append("first_call_not_reset")
            phase = "observe"
        elif phase == "observe":
            if operation != "observe":
                findings.append("observe_order_mismatch")
            phase = "valid_actions"
        elif phase == "valid_actions":
            if operation != "valid_actions":
                findings.append("valid_actions_order_mismatch")
            phase = "step_or_stop"
        elif phase == "step_or_stop":
            if operation == "step":
                if row.get("step_index") != expected_step:
                    findings.append("step_index_mismatch")
                expected_step += 1
                if expected_step > step_budget:
                    findings.append("step_budget_exceeded")
                result = row.get("result")
                terminal = (
                    type(result) is dict
                    and (
                        result.get("terminal") is True
                        or result.get("success") is True
                    )
                )
                phase = (
                    "stop"
                    if terminal or expected_step == step_budget
                    else "observe"
                )
            elif operation == "stop":
                stop_count += 1
                phase = "done"
            else:
                findings.append("step_or_stop_order_mismatch")
        elif phase == "stop":
            if operation != "stop":
                findings.append("terminal_step_not_followed_by_stop")
            else:
                stop_count += 1
            phase = "done"
        else:
            findings.append("call_after_stop")
    if phase != "done" or stop_count != 1:
        findings.append("terminal_stop_census_mismatch")
    return {
        "passed": not findings,
        "findings": sorted(set(findings)),
        "executed_steps": expected_step,
        "stop_count": stop_count,
    }


def _outcome_from_log(
    pair_index: int,
    episode_index: int,
    episode: Any,
    call_log: Sequence[Mapping[str, Any]],
) -> EpisodeOutcome:
    audit = audit_call_order(call_log)
    if not audit["passed"]:
        raise CapabilityEvaluationError(
            "cannot score an invalid evaluator call log"
        )
    stop = call_log[-1]["result"]
    return EpisodeOutcome(
        pair_index=pair_index,
        episode_index=episode_index,
        success=bool(stop["success"]),
        optimal_steps=episode.optimal_steps,
        executed_steps=audit["executed_steps"],
        step_budget=24,
    )


def run_control_episode(
    *,
    pair: CapabilityPair,
    episode_index: int,
    policy: Any,
    policy_label: str,
    random_seed: int | None,
) -> dict[str, Any]:
    environment = EvaluatorCapabilityEnvironment(
        pair.source,
        episode_index=episode_index,
    )
    environment.reset(episode_index)
    for _ in range(24):
        observation = environment.observe()
        actions = environment.valid_actions()
        action_refs = [item["action_id"] for item in actions]
        selected = policy.choose_action(observation, action_refs)
        result = environment.step(selected)
        if result["success"] or result["terminal"]:
            break
    environment.stop(
        "goal_reached"
        if environment.current_state_ref
        == pair.source.episodes[episode_index].goal_ref
        else "step_budget_exhausted"
    )
    outcome = _outcome_from_log(
        pair.pair_index,
        episode_index,
        pair.source.episodes[episode_index],
        environment.call_log,
    )
    return {
        "schema_version": "atanor.gwip-capability-control-episode.v1",
        "policy": policy_label,
        "random_seed": random_seed,
        "pair_index": pair.pair_index,
        "episode_index": episode_index,
        "call_log": environment.call_log,
        "outcome": asdict(outcome),
        "aggregate_metrics": None,
        "verdict": None,
    }


def run_controls(
    pairs: Sequence[CapabilityPair],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    reactive: list[dict[str, Any]] = []
    random_rows: dict[str, list[dict[str, Any]]] = {
        str(seed): [] for seed in preregistration["random_policy_seeds"]
    }
    for pair in pairs:
        for episode_index in range(4):
            reactive.append(
                run_control_episode(
                    pair=pair,
                    episode_index=episode_index,
                    policy=ReactiveControl(),
                    policy_label="reactive",
                    random_seed=None,
                )
            )
        for seed in preregistration["random_policy_seeds"]:
            policy = RandomControl(
                policy_seed=seed,
                pair_binding=pair.private_ref,
            )
            for episode_index in range(4):
                random_rows[str(seed)].append(
                    run_control_episode(
                        pair=pair,
                        episode_index=episode_index,
                        policy=policy,
                        policy_label="random",
                        random_seed=seed,
                    )
                )
    return {
        "reactive": reactive,
        "random": random_rows,
    }


def _gzip_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Deterministic gzip envelope for the potentially large raw artifact."""

    destination = io.BytesIO()
    with gzip.GzipFile(
        fileobj=destination,
        mode="wb",
        compresslevel=9,
        mtime=0,
    ) as handle:
        handle.write(_json_bytes(value, pretty=False))
    return destination.getvalue()


def _read_gzip_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        with gzip.open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise CapabilityEvaluationError(f"{label} gzip is unreadable") from exc
    return _strict_json_bytes(raw, label=label)


class CleanSourceProbe:
    """Cheap per-episode rebind of the sources the candidate can execute.

    The candidate subprocess imports only the immutable, read-only C archive.
    Its full tree is bound separately before and after execution.  This probe
    therefore rehashes the small evaluator surface and the committed seed on
    every harness boundary, while returning the complete precomputed source
    binding required by the harness.
    """

    def __init__(
        self,
        expected: Mapping[str, Any],
        *,
        seed_path: Path,
        repository_root: Path = REPO,
    ) -> None:
        self.expected = copy.deepcopy(dict(expected))
        self.seed_path = Path(seed_path).resolve(strict=True)
        self.repository_root = Path(repository_root).resolve(strict=True)
        self._evaluator_git = mechanism.bind_git_paths(
            str(expected["evaluator_commit"]),
            EVALUATOR_SOURCE_PATHS,
            repository_root=self.repository_root,
        )
        self._lock = threading.Lock()

    def __call__(self) -> dict[str, Any]:
        with self._lock:
            working = mechanism.bind_working_paths(
                EVALUATOR_SOURCE_PATHS,
                repository_root=self.repository_root,
            )
            if working["files"] != self._evaluator_git["files"]:
                raise CapabilityEvaluationError(
                    "working evaluator changed during execution"
                )
            if (
                hashlib.sha256(self.seed_path.read_bytes()).hexdigest()
                != self.expected["seed_manifest_sha256"]
            ):
                raise CapabilityEvaluationError(
                    "seed manifest changed during execution"
                )
            return copy.deepcopy(self.expected)


def _pairs_from_seed(
    seed: Mapping[str, Any],
    preregistration: Mapping[str, Any] | None = None,
) -> tuple[CapabilityPair, ...]:
    if preregistration is None:
        preregistration, _digest = load_preregistration()
    pairs = generate_capability_pairs(
        preregistration,
        generator_seed=seed["generator_seed"],
        generator_nonce=seed["generator_nonce"],
    )
    if private_cohort_digest(pairs) != seed["private_cohort_sha256"]:
        raise CapabilityEvaluationError(
            "regenerated capability cohort differs from sealed seed"
        )
    return pairs


class EpisodeUniverse:
    """Exact schedule-to-hidden-environment map owned by the evaluator."""

    def __init__(
        self,
        pairs: Sequence[CapabilityPair],
        schedule: Mapping[str, Any],
    ) -> None:
        if len(pairs) != 64:
            raise CapabilityEvaluationError("episode universe requires 64 pairs")
        self.pairs = tuple(pairs)
        self.schedule = validate_semantic_schedule(
            schedule,
            production=True,
            repository_root=REPO,
        )
        self.rows = {
            int(row["ordinal"]): copy.deepcopy(row)
            for row in self.schedule["rows"]
        }

    def binding_for_request(
        self,
        request: Mapping[str, Any],
    ) -> tuple[CapabilityEnvironment, int, dict[str, Any]]:
        ordinal = request.get("ordinal")
        if type(ordinal) is not int or ordinal not in self.rows:
            raise CapabilityEvaluationError("episode ordinal is not sealed")
        row = self.rows[ordinal]
        for field in (
            "phase",
            "pair_index",
            "episode_index",
            "arm",
            "environment_seed",
            "policy_seed",
            "step_budget",
            "retain_policy_updates",
        ):
            if request.get(field) != row[field]:
                raise CapabilityEvaluationError(
                    f"episode request differs from schedule: {field}"
                )
        pair = self.pairs[row["pair_index"]]
        if row["phase"] == "support":
            environment = pair.source
            episode_index = row["episode_index"]
        else:
            environment = pair.target
            episode_index = row["start_index"]
        if request.get("environment_seed") != episode_index:
            raise CapabilityEvaluationError(
                "episode environment seed is not its sealed start index"
            )
        return environment, episode_index, row

    def environment_factory(
        self,
        request: Mapping[str, Any],
        _session: str,
    ) -> EvaluatorCapabilityEnvironment:
        environment, episode_index, _row = self.binding_for_request(request)
        return EvaluatorCapabilityEnvironment(
            environment,
            episode_index=episode_index,
        )


def _request_factory(
    episode_inputs: Mapping[int, Mapping[str, Any]],
) -> Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]:
    frozen = copy.deepcopy(dict(episode_inputs))

    def build(
        row: Mapping[str, Any],
        _memory: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ordinal = int(row["ordinal"])
        if ordinal not in frozen:
            raise CapabilityEvaluationError(
                "episode input ordinal is not evaluator-owned"
            )
        return copy.deepcopy(frozen[ordinal])

    return build


def run_budget_pre_mutation_probes(
    pairs: Sequence[CapabilityPair],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        environment = EvaluatorCapabilityEnvironment(
            pair.source,
            episode_index=0,
        )
        environment.reset(0)
        action_id = pair.source.public_actions()[0]["action_id"]
        for _index in range(24):
            environment.step(action_id)
        before_state = environment.current_state_ref
        before_log = environment.call_log
        rejected = False
        try:
            environment.step(action_id)
        except CapabilityEvaluationError as exc:
            rejected = str(exc) == (
                "step budget exhausted before environment mutation"
            )
        rows.append(
            {
                "pair_index": pair.pair_index,
                "rejected": rejected,
                "state_unchanged": (
                    environment.current_state_ref == before_state
                ),
                "log_unchanged": environment.call_log == before_log,
                "executed_step_count": sum(
                    item["operation"] == "step" for item in before_log
                ),
            }
        )
    return {
        "schema_version": "atanor.gwip-capability-budget-probes.v1",
        "rows": rows,
        "passed": len(rows) == 64
        and all(
            row["rejected"]
            and row["state_unchanged"]
            and row["log_unchanged"]
            and row["executed_step_count"] == 24
            for row in rows
        ),
    }


def _attempt_payload(
    *,
    seed_commit: str,
    schedule_commit: str,
    seed_binding: Mapping[str, Any],
    schedule: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": ATTEMPT_SCHEMA,
        "preregistration_commit": PREREG_COMMIT,
        "candidate_commit": CANDIDATE_COMMIT,
        "evaluator_commit": seed_binding["source_binding"][
            "evaluator_commit"
        ],
        "seed_commit": seed_commit,
        "seed_manifest_sha256": seed_binding["raw_sha256"],
        "schedule_commit": schedule_commit,
        "schedule_sha256": harness_digest(schedule),
        "source_binding_sha256": harness_digest(
            seed_binding["source_binding"]
        ),
        "candidate_episode_count": 1024,
        "designated_local_attempt_claimed": True,
        "retry_authorized": False,
        "production_default_on": False,
    }
    if _ACTIVE_RUN_PROFILE == "v3":
        if _ACTIVE_VERIFICATION_LINEAGE_BASE is None:
            raise CapabilityEvaluationError(
                "v3 attempt cannot precede lineage initialization"
            )
        payload.update(
            {
                "operator_sequence_label": "v3",
                "empirical_predecessor_count": 1,
                "v2_materialized": False,
                "fixed_candidate_fixed_dataset": True,
                "verification_lineage_sha256": (
                    _ACTIVE_VERIFICATION_LINEAGE_BASE[
                        "checksum_sha256"
                    ]
                ),
            }
        )
    return payload


def _claim_attempt(
    *,
    seed_commit: str,
    schedule_commit: str,
    seed_binding: Mapping[str, Any],
    schedule: Mapping[str, Any],
    output_path: Path = REPO / ATTEMPT_RELATIVE_PATH,
) -> dict[str, Any]:
    payload = _attempt_payload(
        seed_commit=seed_commit,
        schedule_commit=schedule_commit,
        seed_binding=seed_binding,
        schedule=schedule,
    )
    raw = _json_bytes(payload)
    _write_once(output_path, raw)
    return {
        "path": ATTEMPT_RELATIVE_PATH,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "payload": payload,
    }


def _archive_authority_root(
    external_root: Path,
    *,
    shard_root: Path | None = None,
    runtime_dependency_root: Path | None = None,
    expected_runtime_dependency_binding: Mapping[str, Any] | None = None,
    output_path: Path = REPO / AUTHORITY_RELATIVE_PATH,
) -> dict[str, Any]:
    """Persist public authority/lease/shard evidence, never the signer."""

    root = Path(external_root).resolve(strict=True)
    repository = REPO.resolve(strict=True)
    if (runtime_dependency_root is None) != (
        expected_runtime_dependency_binding is None
    ):
        raise CapabilityEvaluationError(
            "runtime dependency root and seed binding must be supplied together"
        )
    sealed_runtime_binding: dict[str, Any] | None = None
    if runtime_dependency_root is not None:
        sealed_runtime_binding = validate_runtime_dependency_binding(
            expected_runtime_dependency_binding
        )
        rebound = bind_runtime_dependency_root(runtime_dependency_root)
        if rebound != sealed_runtime_binding:
            raise CapabilityEvaluationError(
                "runtime dependency root differs from seed binding"
            )
    roots: list[tuple[str, Path]] = [("authority", root)]
    if shard_root is not None:
        roots.append(("shards", Path(shard_root).resolve(strict=True)))
    if runtime_dependency_root is not None:
        roots.append(
            (
                "runtime-dependencies",
                Path(runtime_dependency_root).resolve(strict=True),
            )
        )
    for _label, evidence_root in roots:
        try:
            evidence_root.relative_to(repository)
        except ValueError:
            pass
        else:
            raise CapabilityEvaluationError(
                "authority/shard evidence root must remain outside repository"
            )
        if evidence_root.is_symlink():
            raise CapabilityEvaluationError(
                "authority/shard evidence root is a symlink"
            )
    files = [
        (label, evidence_root, item)
        for label, evidence_root in roots
        for item in sorted(
            evidence_root.rglob("*"),
            key=lambda path: path.as_posix(),
        )
        if item.is_file()
    ]
    if not files or any(item.is_symlink() for _, _, item in files):
        raise CapabilityEvaluationError(
            "authority evidence file census is empty or unsafe"
        )
    tar_buffer = io.BytesIO()
    manifest: list[dict[str, Any]] = []
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        for label, evidence_root, path in files:
            raw = path.read_bytes()
            relative = (
                f"{label}/"
                + path.relative_to(evidence_root).as_posix()
            )
            info = tarfile.TarInfo(relative)
            info.size = len(raw)
            info.mode = 0o400
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(raw))
            manifest.append(
                {
                    "path": relative,
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    runtime_rows: list[dict[str, Any]] = []
    if sealed_runtime_binding is not None:
        expected_by_path = {
            row["path"]: row for row in sealed_runtime_binding["files"]
        }
        for row in manifest:
            prefix = "runtime-dependencies/"
            if not row["path"].startswith(prefix):
                continue
            logical_path = row["path"][len(prefix) :]
            expected_row = expected_by_path.get(logical_path)
            if expected_row is None:
                raise CapabilityEvaluationError(
                    "authority archive contains an unsealed runtime dependency"
                )
            runtime_rows.append(
                {
                    "dependency": expected_row["dependency"],
                    "path": logical_path,
                    "size_bytes": row["size_bytes"],
                    "sha256": row["sha256"],
                }
            )
        if runtime_rows != sealed_runtime_binding["files"]:
            raise CapabilityEvaluationError(
                "authority archive runtime dependency bytes differ from seed binding"
            )
    compressed = io.BytesIO()
    with gzip.GzipFile(
        fileobj=compressed,
        mode="wb",
        compresslevel=9,
        mtime=0,
    ) as handle:
        handle.write(tar_buffer.getvalue())
    raw_archive = compressed.getvalue()
    _write_once(output_path, raw_archive)
    if output_path.read_bytes() != raw_archive:
        raise CapabilityEvaluationError(
            "persisted authority archive differs from verified bytes"
        )
    return {
        "path": AUTHORITY_RELATIVE_PATH,
        "raw_sha256": hashlib.sha256(raw_archive).hexdigest(),
        "file_count": len(manifest),
        "manifest_sha256": canonical_digest(manifest),
        "external_root_path_sha256": {
            label: hashlib.sha256(
                str(evidence_root).encode("utf-8")
            ).hexdigest()
            for label, evidence_root in roots
        },
        "episode_shards_archived": shard_root is not None,
        "runtime_dependencies_archived": (
            runtime_dependency_root is not None
        ),
        "runtime_dependency_archive_verified": (
            sealed_runtime_binding is not None
        ),
        "runtime_dependency_binding_sha256": (
            canonical_digest(sealed_runtime_binding)
            if sealed_runtime_binding is not None
            else None
        ),
        "private_signing_key_persisted": False,
    }


@contextlib.contextmanager
def _archive_runtime_dependencies_on_failure(
    *,
    external_root: Path,
    shard_root: Path,
    runtime_dependency_root: Path,
    expected_runtime_dependency_binding: Mapping[str, Any],
    output_path: Path,
    binding_sink: dict[str, Any],
) -> Any:
    """Archive seed-bound dependency bytes before ExitStack removes the root."""

    if type(binding_sink) is not dict or binding_sink:
        raise CapabilityEvaluationError(
            "failure authority binding sink must start as an empty exact object"
        )
    try:
        yield
    except Exception:
        if not output_path.exists():
            binding_sink["authority_binding"] = _archive_authority_root(
                external_root,
                shard_root=shard_root if shard_root.exists() else None,
                runtime_dependency_root=runtime_dependency_root,
                expected_runtime_dependency_binding=(
                    expected_runtime_dependency_binding
                ),
                output_path=output_path,
            )
        raise


def _schedule_blob_binding(
    *,
    seed_commit: str,
    schedule_commit: str,
    schedule: Mapping[str, Any],
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Independently establish exact S -> L chronology and bytes."""

    seed_commit = _full_commit(
        seed_commit,
        repository_root=repository_root,
    )
    schedule_commit = _full_commit(
        schedule_commit,
        repository_root=repository_root,
    )
    if _head(repository_root=repository_root) != schedule_commit:
        raise CapabilityEvaluationError(
            "schedule sealing requires HEAD to equal L"
        )
    _require_ancestry(
        seed_commit,
        schedule_commit,
        strict=True,
        repository_root=repository_root,
    )
    _require_unchanged(
        CANDIDATE_COMMIT,
        schedule_commit,
        ("packages",),
        repository_root=repository_root,
    )
    evaluator_commit = str(schedule["source_binding"]["evaluator_commit"])
    _require_unchanged(
        evaluator_commit,
        schedule_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    _require_unchanged(
        seed_commit,
        schedule_commit,
        (SEED_RELATIVE_PATH,),
        repository_root=repository_root,
    )
    raw = _json_bytes(schedule)
    working = (repository_root / SCHEDULE_RELATIVE_PATH).read_bytes()
    blob = _git_blob(
        schedule_commit,
        SCHEDULE_RELATIVE_PATH,
        repository_root=repository_root,
    )
    if working != raw or blob != raw:
        raise CapabilityEvaluationError(
            "working schedule/exact L blob differs from prepared schedule"
        )
    return {
        "seed_commit": seed_commit,
        "schedule_commit": schedule_commit,
        "path": SCHEDULE_RELATIVE_PATH,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_sha256": harness_digest(schedule),
        "strict_seed_to_schedule_ancestry": True,
        "candidate_and_evaluator_unchanged": True,
    }


def _revalidate_before_attempt(
    *,
    seed_commit: str,
    schedule_commit: str,
    schedule: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    preregistration: Mapping[str, Any],
    preregistration_raw_sha256: str,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Rebind every frozen input immediately before consuming attempt A."""

    sealed_preregistration = _sealed_preregistration_binding(
        comparison_commit=schedule_commit,
        repository_root=repository_root,
    )
    current_preregistration, current_preregistration_sha256 = (
        load_preregistration(repository_root / PREREG_RELATIVE_PATH)
    )
    if (
        current_preregistration != dict(preregistration)
        or current_preregistration_sha256 != preregistration_raw_sha256
        or sealed_preregistration["json_raw_sha256"]
        != preregistration_raw_sha256
    ):
        raise CapabilityEvaluationError(
            "working preregistration differs from the frozen P bytes"
        )
    clean_source = _probe_clean_source_binding(
        source_binding,
        seed_path=repository_root / SEED_RELATIVE_PATH,
        repository_root=repository_root,
    )
    schedule_binding = _schedule_blob_binding(
        seed_commit=seed_commit,
        schedule_commit=schedule_commit,
        schedule=schedule,
        repository_root=repository_root,
    )
    if _ACTIVE_RUN_PROFILE == "v3":
        _v1_artifact_hashes(repository_root=repository_root)
        _require_v2_absent(repository_root=repository_root)
        _active_verification_lineage(
            repository_root=repository_root,
            fail_closed=True,
        )
    return {
        "preregistration": copy.deepcopy(current_preregistration),
        "preregistration_raw_sha256": current_preregistration_sha256,
        "preregistration_binding": sealed_preregistration,
        "source_binding": clean_source,
        "schedule_binding": schedule_binding,
    }


def _terminal_raw(
    *,
    seed_binding: Mapping[str, Any],
    schedule_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    attempt_binding: Mapping[str, Any],
    cohort_binding: Mapping[str, Any],
    failure: BaseException,
    candidate_episodes: Sequence[Mapping[str, Any]] = (),
    parent_evidence: Mapping[int, Mapping[str, Any]] | None = None,
    budget_probe: Mapping[str, Any] | None = None,
    authority_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": RAW_SCHEMA,
        "preregistration_binding": copy.deepcopy(
            seed_binding["manifest"]["preregistration_binding"]
        ),
        "seed_manifest_binding": copy.deepcopy(dict(seed_binding)),
        "schedule_binding": copy.deepcopy(dict(schedule_binding)),
        "source_binding": copy.deepcopy(dict(source_binding)),
        "attempt_binding": copy.deepcopy(dict(attempt_binding)),
        "cohort_binding": copy.deepcopy(dict(cohort_binding)),
        "authority_archive_binding": copy.deepcopy(authority_binding),
        "budget_pre_mutation_probe": copy.deepcopy(budget_probe),
        "candidate_episodes": copy.deepcopy(list(candidate_episodes)),
        "parent_evidence": {
            str(key): copy.deepcopy(dict(value))
            for key, value in sorted((parent_evidence or {}).items())
        },
        "controls": None,
        "source_audit": None,
        "execution_failure": {
            "error_type": type(failure).__name__,
            "error": str(failure)[:1000],
            "retry_forbidden": True,
            "terminal_verdict": "CAPABILITY_RED",
        },
        "aggregate_metrics": None,
        "verdict": None,
    }
    lineage = _active_verification_lineage(
        fail_closed=False,
    )
    if lineage is not None:
        payload["verification_lineage"] = lineage
    return payload


def _receipt_checksum(value: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            key: copy.deepcopy(item)
            for key, item in value.items()
            if key != "checksum_sha256"
        }
    )


def _receipt_verification_lineage(
    raw_evidence: Mapping[str, Any],
    *,
    require_preserved: bool,
) -> dict[str, Any] | None:
    lineage = raw_evidence.get("verification_lineage")
    if lineage is None:
        if _ACTIVE_RUN_PROFILE == "v3":
            raise CapabilityEvaluationError(
                "v3 raw evidence lacks verification lineage"
            )
        return None
    if (
        type(lineage) is not dict
        or lineage.get("schema_version")
        != "atanor.gwip-capability-verification-lineage.v3"
        or lineage.get("checksum_sha256")
        != _v3_lineage_checksum(lineage)
        or lineage.get("operator_sequence_label") != "v3"
        or lineage.get("measurement_kind")
        != "fixed_candidate_fixed_dataset_verifier_only_reseal"
    ):
        raise CapabilityEvaluationError(
            "v3 verification lineage checksum/identity is invalid"
        )
    source_binding = raw_evidence.get("source_binding")
    attempt_binding = raw_evidence.get("attempt_binding")
    attempt_payload = (
        attempt_binding.get("payload")
        if type(attempt_binding) is dict
        else None
    )
    if (
        type(source_binding) is not dict
        or lineage.get("evaluator_source_binding")
        != source_binding
        or lineage.get("v3_evaluator_commit")
        != source_binding.get("evaluator_commit")
        or lineage.get("v3_evaluator_source_sha256")
        != source_binding.get("evaluator_source_sha256")
        or type(attempt_payload) is not dict
        or lineage.get("pre_attempt_lineage_sha256")
        != attempt_payload.get("verification_lineage_sha256")
    ):
        raise CapabilityEvaluationError(
            "v3 lineage/source/attempt binding is inconsistent"
        )
    preregistration_binding = raw_evidence.get(
        "preregistration_binding"
    )
    preregistration_paths = {
        row.get("path")
        for row in (
            preregistration_binding.get("files", [])
            if type(preregistration_binding) is dict
            else []
        )
        if type(row) is dict
    }
    seed_binding = raw_evidence.get("seed_manifest_binding")
    schedule_binding = raw_evidence.get("schedule_binding")
    authority_binding = raw_evidence.get("authority_archive_binding")
    if (
        preregistration_paths
        != {
            V3_PREREG_RELATIVE_PATH,
            V3_PREREG_DOC_RELATIVE_PATH,
        }
        or type(seed_binding) is not dict
        or seed_binding.get("path") != V3_SEED_RELATIVE_PATH
        or type(schedule_binding) is not dict
        or schedule_binding.get("path") != V3_SCHEDULE_RELATIVE_PATH
        or type(attempt_binding) is not dict
        or attempt_binding.get("path") != V3_ATTEMPT_RELATIVE_PATH
        or (
            authority_binding is not None
            and (
                type(authority_binding) is not dict
                or authority_binding.get("path")
                != V3_AUTHORITY_RELATIVE_PATH
            )
        )
    ):
        raise CapabilityEvaluationError(
            "v3 raw evidence references a non-v3 artifact path"
        )
    if require_preserved and (
        lineage.get("v1_artifacts_preserved") is not True
        or lineage.get("candidate_binding", {}).get(
            "packages_unchanged_from_candidate_commit"
        )
        is not True
        or lineage.get("dataset_binding", {}).get(
            "all_episode_input_digests_equal_v1"
        )
        is not True
        or lineage.get("dataset_binding", {}).get(
            "v3_schedule_semantics_equal_v1"
        )
        is not True
        or type(authority_binding) is not dict
        or authority_binding.get("path") != V3_AUTHORITY_RELATIVE_PATH
    ):
        raise CapabilityEvaluationError(
            "v3 fixed candidate/dataset lineage did not pass"
        )
    return copy.deepcopy(lineage)


def _terminal_red_receipt(
    *,
    raw_path: Path,
    raw_evidence: Mapping[str, Any],
    failure: BaseException,
) -> dict[str, Any]:
    hard_gates = {name: False for name in REQUIRED_HARD_GATES}
    lineage = _receipt_verification_lineage(
        raw_evidence,
        require_preserved=False,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "raw_evidence_binding": {
            "path": RAW_RELATIVE_PATH,
            "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "canonical_sha256": canonical_digest(raw_evidence),
        },
        "verdict": "CAPABILITY_RED",
        "explanatory_sublabel": "INCOMPLETE_OR_FAILED_ONE_SHOT",
        "hard_gates": hard_gates,
        "hard_gates_passed": False,
        "metrics": None,
        "representative_episode": None,
        "failure": {
            "error_type": type(failure).__name__,
            "error": str(failure)[:1000],
        },
        "capability_claim": False,
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
        "production_default_on": False,
        "retry_authorized": False,
        "limitations": [
            "terminal failure or incomplete one-shot evidence",
            "not an ARC or public benchmark result",
            "production default remains OFF",
        ],
    }
    if lineage is not None:
        receipt["verification_lineage"] = lineage
    receipt["checksum_sha256"] = _receipt_checksum(receipt)
    return receipt


def _capability_receipt(
    *,
    raw_path: Path,
    raw_evidence: Mapping[str, Any],
    gate_results: Mapping[str, Mapping[str, Any]],
    metrics: Mapping[str, Any],
    exemplar: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if (
        set(gate_results) != set(REQUIRED_HARD_GATES)
        or any(
            type(item) is not dict
            or item.get("passed") not in {True, False}
            or type(item.get("evidence")) is not dict
            for item in gate_results.values()
        )
    ):
        raise CapabilityEvaluationError(
            "receipt hard-gate evidence is malformed"
        )
    hard_gates = {
        name: gate_results[name]["passed"] is True
        for name in REQUIRED_HARD_GATES
    }
    if (
        metrics.get("hard_gates") != hard_gates
        or metrics.get("verdict")
        not in {"CAPABILITY_GREEN", "CAPABILITY_RED", "NO_GO"}
        or metrics.get("capability_claim")
        is not (metrics.get("verdict") == "CAPABILITY_GREEN")
    ):
        raise CapabilityEvaluationError(
            "receipt metrics/gate verdict binding is inconsistent"
        )
    lineage = _receipt_verification_lineage(
        raw_evidence,
        require_preserved=True,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "raw_evidence_binding": {
            "path": RAW_RELATIVE_PATH,
            "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "canonical_sha256": canonical_digest(raw_evidence),
        },
        "preregistration_binding": copy.deepcopy(
            raw_evidence["preregistration_binding"]
        ),
        "seed_manifest_binding": copy.deepcopy(
            raw_evidence["seed_manifest_binding"]
        ),
        "schedule_binding": copy.deepcopy(
            raw_evidence["schedule_binding"]
        ),
        "source_binding": copy.deepcopy(raw_evidence["source_binding"]),
        "attempt_binding": copy.deepcopy(raw_evidence["attempt_binding"]),
        "cohort_binding": copy.deepcopy(raw_evidence["cohort_binding"]),
        "authority_archive_binding": copy.deepcopy(
            raw_evidence["authority_archive_binding"]
        ),
        "hard_gates": hard_gates,
        "hard_gate_evidence": {
            name: {
                "evidence_sha256": canonical_digest(
                    gate_results[name]["evidence"]
                ),
                "passed": hard_gates[name],
            }
            for name in REQUIRED_HARD_GATES
        },
        "hard_gates_passed": all(hard_gates.values()),
        "metrics": copy.deepcopy(dict(metrics)),
        "representative_episode": copy.deepcopy(exemplar),
        "verdict": metrics["verdict"],
        "explanatory_sublabel": metrics.get("explanatory_sublabel"),
        "capability_claim": metrics["verdict"] == "CAPABILITY_GREEN",
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
        "production_default_on": False,
        "retry_authorized": False,
        "limitations": [
            (
                "claim limited to the preregistered affine "
                "cross-modulus unseen-mechanics cohort"
            ),
            "not an ARC-AGI-3 or other public benchmark result",
            "not a general world-model, AGI, E5, or E6 claim",
            "reviewed Python isolation guard, not an OS sandbox",
            "production default remains OFF",
            (
                "designated local one-shot claim; global uniqueness is "
                "not externally notarized"
            ),
        ],
    }
    if lineage is not None:
        receipt["verification_lineage"] = lineage
    receipt["checksum_sha256"] = _receipt_checksum(receipt)
    return receipt


def _verify_receipt_identity(
    receipt: Mapping[str, Any],
    *,
    raw_path: Path,
    raw_evidence: Mapping[str, Any],
    gate_results: Mapping[str, Mapping[str, Any]],
    metrics: Mapping[str, Any],
    exemplar: Mapping[str, Any] | None,
) -> dict[str, Any]:
    expected = _capability_receipt(
        raw_path=raw_path,
        raw_evidence=raw_evidence,
        gate_results=gate_results,
        metrics=metrics,
        exemplar=exemplar,
    )
    passed = (
        type(receipt) is dict
        and dict(receipt) == expected
        and receipt.get("checksum_sha256")
        == _receipt_checksum(receipt)
    )
    return {
        "passed": passed,
        "verdict": expected["verdict"] if passed else None,
        "findings": [] if passed else [
            "receipt differs from raw-evidence recomputation"
        ],
    }


def _publish_verified_receipt(
    receipt: Mapping[str, Any],
    *,
    execution_context_unwound: bool,
    receipt_path: Path,
    raw_path: Path,
    raw_evidence: Mapping[str, Any],
    gate_results: Mapping[str, Mapping[str, Any]],
    metrics: Mapping[str, Any],
    exemplar: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Publish once only after the complete receipt is verified in memory."""

    if execution_context_unwound is not True:
        raise CapabilityEvaluationError(
            "execution contexts did not unwind before receipt publish"
        )
    identity = _verify_receipt_identity(
        receipt,
        raw_path=raw_path,
        raw_evidence=raw_evidence,
        gate_results=gate_results,
        metrics=metrics,
        exemplar=exemplar,
    )
    if identity["passed"] is not True:
        raise CapabilityEvaluationError(
            "receipt failed independent identity reconstruction before publish"
        )
    _write_once(receipt_path, _json_bytes(receipt))
    return copy.deepcopy(dict(receipt))


def validate_evaluator_readiness(
    *,
    comparison_commit: str = "HEAD",
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Read-only pre-E validation; it never creates a seed or an attempt."""

    comparison = _full_commit(
        comparison_commit,
        repository_root=repository_root,
    )
    preregistration = _sealed_preregistration_binding(
        comparison_commit=comparison,
        repository_root=repository_root,
    )
    _require_ancestry(
        PREREG_COMMIT,
        CANDIDATE_COMMIT,
        strict=True,
        repository_root=repository_root,
    )
    if not mechanism._git_working_paths_unchanged(
        CANDIDATE_COMMIT,
        ("packages",),
        repository_root=repository_root,
    ):
        raise CapabilityEvaluationError(
            "working packages differ from candidate C"
        )
    restricted = _candidate_restricted_diff(
        repository_root=repository_root
    )
    domain = mechanism.audit_candidate_sources(
        [repository_root / item for item in CANDIDATE_DIRECT_PATHS],
        repository_root=repository_root,
    )
    if domain.get("passed") is not True:
        raise CapabilityEvaluationError(
            "candidate domain-neutrality audit failed"
        )
    prior, prior_binding = _prior_mechanism_inventory(
        repository_root=repository_root
    )
    runtime_dependencies = census_runtime_dependency_sources(
        repository_root=repository_root
    )
    expected_sources = {
        item: (repository_root / item).is_file()
        for item in EVALUATOR_SOURCE_PATHS
    }
    if not all(expected_sources.values()):
        raise CapabilityEvaluationError(
            "evaluator source module census is incomplete"
        )
    return {
        "schema_version": "atanor.gwip-capability-evaluator-readiness.v1",
        "ready": True,
        "comparison_commit": comparison,
        "preregistration_binding": preregistration,
        "candidate_restricted_diff": restricted,
        "candidate_domain_audit": domain,
        "prior_mechanism_binding": prior_binding,
        "prior_observation_token_count": len(prior.observation_tokens),
        "prior_transition_edge_token_count": len(
            prior.transition_edge_tokens
        ),
        "runtime_dependency_binding": runtime_dependencies,
        "evaluator_source_paths": expected_sources,
        "final_seed_generated": False,
        "final_attempt_consumed": False,
    }


def _read_schedule_commit_from_stdin() -> str:
    raw = sys.stdin.buffer.readline(4097)
    value = _strict_json_bytes(raw, label="schedule commit acknowledgement")
    if set(value) != {"schedule_commit"}:
        raise CapabilityEvaluationError(
            "schedule acknowledgement fields mismatch"
        )
    return _full_commit(str(value["schedule_commit"]))


def _cohort_binding(
    seed: Mapping[str, Any],
    pairs: Sequence[CapabilityPair],
) -> dict[str, Any]:
    if (
        len(pairs) != 64
        or private_cohort_digest(pairs) != seed["private_cohort_sha256"]
    ):
        raise CapabilityEvaluationError(
            "capability cohort cannot be bound to the sealed seed"
        )
    return {
        "private_cohort_sha256": seed["private_cohort_sha256"],
        "pair_count": len(pairs),
        "source_modulus": 13,
        "target_modulus": 17,
        "counterfactual_modulus": 19,
        "prior_mechanism_nonoverlap_passed": (
            seed["nonoverlap_audit"].get("passed") is True
        ),
        "prior_mechanism_private_cohort_sha256": (
            seed["prior_mechanism_binding"]["private_cohort_sha256"]
        ),
    }


def _gate_inputs(
    *,
    schedule: Mapping[str, Any],
    episodes: Sequence[Mapping[str, Any]],
    parent_evidence: Mapping[int | str, Mapping[str, Any]],
    candidate_root: Path,
    candidate_binding: Mapping[str, Any],
    runtime_dependency_root: Path,
    runtime_dependency_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
    budget_probe: Mapping[str, Any],
    attempted_ordinals: Sequence[int],
    source_before: Mapping[str, Any],
    source_after: Mapping[str, Any],
    repository_root: Path = REPO,
) -> CapabilityGateInputs:
    return CapabilityGateInputs(
        schedule=copy.deepcopy(dict(schedule)),
        episodes=copy.deepcopy(list(episodes)),
        parent_evidence=copy.deepcopy(dict(parent_evidence)),
        candidate_root=Path(candidate_root),
        candidate_archive_binding=copy.deepcopy(dict(candidate_binding)),
        runtime_dependency_root=Path(runtime_dependency_root),
        runtime_dependency_binding=copy.deepcopy(
            dict(runtime_dependency_binding)
        ),
        frozen_source_binding=copy.deepcopy(dict(source_binding)),
        seed_manifest_audit=copy.deepcopy(dict(seed_manifest)),
        budget_probe=copy.deepcopy(dict(budget_probe)),
        repository_root=Path(repository_root),
        attempted_ordinals=list(attempted_ordinals),
        harness_source_before=copy.deepcopy(dict(source_before)),
        harness_source_after=copy.deepcopy(dict(source_after)),
        production=True,
    )


def _harness_gate_results(
    harness_result: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    surface = harness_result.get("hard_gate_surfaces")
    gates = surface.get("gates") if type(surface) is dict else None
    if (
        type(gates) is not dict
        or set(gates) != set(REQUIRED_HARD_GATES)
    ):
        raise CapabilityEvaluationError(
            "harness hard-gate surface census is invalid"
        )
    output: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_HARD_GATES:
        item = gates[name]
        if (
            type(item) is not dict
            or item.get("passed") not in {True, False}
            or type(item.get("evidence")) is not dict
        ):
            raise CapabilityEvaluationError(
                f"harness hard-gate surface is invalid: {name}"
            )
        output[name] = {
            "passed": item["passed"],
            "evidence": copy.deepcopy(item["evidence"]),
        }
    return output


def _gate_booleans(
    gate_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, bool]:
    if set(gate_results) != set(REQUIRED_HARD_GATES):
        raise CapabilityEvaluationError("hard-gate result census mismatch")
    output: dict[str, bool] = {}
    for name in REQUIRED_HARD_GATES:
        item = gate_results[name]
        if (
            type(item) is not dict
            or item.get("passed") not in {True, False}
            or type(item.get("evidence")) is not dict
        ):
            raise CapabilityEvaluationError(
                f"hard-gate result is malformed: {name}"
            )
        output[name] = item["passed"] is True
    return output


def _success_raw(
    *,
    seed_record: Mapping[str, Any],
    schedule_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    attempt_binding: Mapping[str, Any],
    cohort_binding: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    budget_probe: Mapping[str, Any],
    harness_result: Mapping[str, Any],
    parent_evidence: Mapping[int, Mapping[str, Any]],
    controls: Mapping[str, Any],
    candidate_binding: Mapping[str, Any],
    runtime_dependency_binding: Mapping[str, Any],
    independent_derivation: Mapping[str, Any],
) -> dict[str, Any]:
    harness_gates = _harness_gate_results(harness_result)
    payload = {
        "schema_version": RAW_SCHEMA,
        "preregistration_binding": copy.deepcopy(
            seed_record["manifest"]["preregistration_binding"]
        ),
        "seed_manifest_binding": copy.deepcopy(dict(seed_record)),
        "schedule_binding": copy.deepcopy(dict(schedule_binding)),
        "source_binding": copy.deepcopy(dict(source_binding)),
        "attempt_binding": copy.deepcopy(dict(attempt_binding)),
        "cohort_binding": copy.deepcopy(dict(cohort_binding)),
        "authority_archive_binding": copy.deepcopy(
            dict(authority_binding)
        ),
        "budget_pre_mutation_probe": copy.deepcopy(dict(budget_probe)),
        "candidate_episodes": copy.deepcopy(
            list(harness_result["episodes"])
        ),
        "parent_evidence": {
            str(key): copy.deepcopy(dict(value))
            for key, value in sorted(parent_evidence.items())
        },
        "controls": copy.deepcopy(dict(controls)),
        "source_audit": {
            "candidate_archive_binding": copy.deepcopy(
                dict(candidate_binding)
            ),
            "runtime_dependency_binding": copy.deepcopy(
                dict(runtime_dependency_binding)
            ),
            "attempted_ordinals": copy.deepcopy(
                list(harness_result["attempted_ordinals"])
            ),
            "harness_source_before": copy.deepcopy(
                dict(harness_result["source_before"])
            ),
            "harness_source_after": copy.deepcopy(
                dict(harness_result["source_after"])
            ),
            "harness_gate_surfaces": harness_gates,
            "worker_claims_accepted_as_authority": False,
        },
        "independent_derivation": copy.deepcopy(
            dict(independent_derivation)
        ),
        "execution_failure": None,
        "aggregate_metrics": None,
        "verdict": None,
    }
    lineage = _active_verification_lineage(
        fail_closed=True,
    )
    if lineage is not None:
        payload["verification_lineage"] = lineage
    return payload


def _write_terminal_after_attempt(
    *,
    failure: BaseException,
    seed_record: Mapping[str, Any],
    schedule_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    attempt_binding: Mapping[str, Any],
    cohort_binding: Mapping[str, Any],
    candidate_episodes: Sequence[Mapping[str, Any]],
    parent_evidence: Mapping[int, Mapping[str, Any]],
    budget_probe: Mapping[str, Any] | None,
    authority_binding: Mapping[str, Any] | None,
    raw_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    if raw_path.exists():
        raw_evidence = _read_gzip_json(
            raw_path,
            label="terminal capability raw evidence",
        )
    else:
        raw_evidence = _terminal_raw(
            seed_binding=seed_record,
            schedule_binding=schedule_binding,
            source_binding=source_binding,
            attempt_binding=attempt_binding,
            cohort_binding=cohort_binding,
            failure=failure,
            candidate_episodes=candidate_episodes,
            parent_evidence=parent_evidence,
            budget_probe=budget_probe,
            authority_binding=authority_binding,
        )
        _write_once(raw_path, _gzip_json_bytes(raw_evidence))
    receipt = _terminal_red_receipt(
        raw_path=raw_path,
        raw_evidence=raw_evidence,
        failure=failure,
    )
    if not receipt_path.exists():
        _write_once(receipt_path, _json_bytes(receipt))
    else:
        existing = _read_json(
            receipt_path,
            label="terminal capability receipt",
        )
        if existing != receipt:
            raise CapabilityEvaluationError(
                "existing terminal receipt differs from recomputation"
            )
    return receipt


def run_one_shot_capability(
    *,
    seed_commit: str,
    external_root: Path,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Prepare L interactively, claim A once, and seal the final verdict."""

    repository_root = Path(repository_root).resolve(strict=True)
    fixed_paths = {
        "schedule": repository_root / SCHEDULE_RELATIVE_PATH,
        "attempt": repository_root / ATTEMPT_RELATIVE_PATH,
        "raw": repository_root / RAW_RELATIVE_PATH,
        "receipt": repository_root / RECEIPT_RELATIVE_PATH,
        "authority": repository_root / AUTHORITY_RELATIVE_PATH,
    }
    if any(path.exists() for path in fixed_paths.values()):
        present = sorted(
            name for name, path in fixed_paths.items() if path.exists()
        )
        raise CapabilityEvaluationError(
            "one-shot artifacts already exist: " + ",".join(present)
        )
    seed_commit = _full_commit(
        seed_commit,
        repository_root=repository_root,
    )
    if _head(repository_root=repository_root) != seed_commit:
        raise CapabilityEvaluationError(
            "run preparation requires HEAD to equal the seed seal S"
        )
    seed, seed_binding = load_sealed_seed(
        seed_commit=seed_commit,
        repository_root=repository_root,
    )
    seed_record = {
        "manifest": copy.deepcopy(seed),
        **copy.deepcopy(seed_binding),
    }
    preregistration, preregistration_raw_sha256 = load_preregistration(
        repository_root / PREREG_RELATIVE_PATH
    )
    if preregistration_raw_sha256 != seed["preregistration_raw_sha256"]:
        raise CapabilityEvaluationError(
            "working preregistration differs from the seed-bound P bytes"
        )
    pairs = _pairs_from_seed(seed, preregistration)
    cohort_binding = _cohort_binding(seed, pairs)
    source_binding = copy.deepcopy(seed_binding["source_binding"])
    schedule_nonce = secrets.token_urlsafe(32)
    episode_inputs = build_episode_inputs(
        pairs,
        schedule_nonce=schedule_nonce,
    )
    issuer = JITRunLeaseIssuer(
        Path(external_root),
        repository_root=repository_root,
    )
    prepared = issuer.prepare_schedule(
        source_binding=source_binding,
        schedule_nonce=schedule_nonce,
        pair_count=len(pairs),
        fixture_nonproduction=False,
        episode_inputs=episode_inputs,
    )
    if _ACTIVE_RUN_PROFILE == "v3":
        semantic_binding = _v3_validate_prepared_schedule(
            prepared.schedule,
            repository_root=repository_root,
        )
        if _ACTIVE_VERIFICATION_LINEAGE_BASE is None:
            raise CapabilityEvaluationError(
                "v3 schedule preceded lineage initialization"
            )
        _ACTIVE_VERIFICATION_LINEAGE_BASE["dataset_binding"][
            "v3_schedule_semantics_equal_v1"
        ] = True
        _ACTIVE_VERIFICATION_LINEAGE_BASE["dataset_binding"][
            "v3_schedule_semantic_binding_sha256"
        ] = semantic_binding
        _ACTIVE_VERIFICATION_LINEAGE_BASE["checksum_sha256"] = (
            _v3_lineage_checksum(
                _ACTIVE_VERIFICATION_LINEAGE_BASE
            )
        )
    _write_once(
        fixed_paths["schedule"],
        _json_bytes(prepared.schedule),
    )
    print(
        json.dumps(
            {
                "state": "AWAITING_SCHEDULE_COMMIT_L",
                "schedule_path": SCHEDULE_RELATIVE_PATH,
                "schedule_sha256": prepared.schedule_sha256,
                "seed_commit": seed_commit,
                "candidate_episode_count": prepared.schedule[
                    "candidate_episode_count"
                ],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    schedule_commit = _read_schedule_commit_from_stdin()
    schedule_binding = _schedule_blob_binding(
        seed_commit=seed_commit,
        schedule_commit=schedule_commit,
        schedule=prepared.schedule,
        repository_root=repository_root,
    )
    issuer.seal_schedule(
        prepared.schedule,
        expected_sha256=prepared.schedule_sha256,
        schedule_commit=schedule_commit,
        seed_commit=seed_commit,
        schedule_relative_path=SCHEDULE_RELATIVE_PATH,
    )
    pre_attempt = _revalidate_before_attempt(
        seed_commit=seed_commit,
        schedule_commit=schedule_commit,
        schedule=prepared.schedule,
        source_binding=source_binding,
        preregistration=preregistration,
        preregistration_raw_sha256=preregistration_raw_sha256,
        repository_root=repository_root,
    )
    schedule_binding = pre_attempt["schedule_binding"]
    preregistration = pre_attempt["preregistration"]

    candidate_episodes: list[dict[str, Any]] = []
    parent_evidence: dict[int, dict[str, Any]] = {}
    budget_probe: dict[str, Any] | None = None
    authority_binding: dict[str, Any] | None = None
    failure_authority_state: dict[str, Any] = {}
    shard_root = Path(str(Path(external_root)) + "-shards")
    sink = ThreadSafeEvidenceSink()
    execution_context_unwound = False
    pending_receipt: dict[str, Any] | None = None
    attempt_binding: dict[str, Any] | None = None
    try:
        attempt_binding = _claim_attempt(
            seed_commit=seed_commit,
            schedule_commit=schedule_commit,
            seed_binding=seed_binding,
            schedule=prepared.schedule,
            output_path=fixed_paths["attempt"],
        )
        with contextlib.ExitStack() as stack:
            dependency_root, dependency_binding = stack.enter_context(
                materialized_runtime_dependencies(
                    seed["runtime_dependency_binding"],
                    repository_root=repository_root,
                )
            )
            stack.enter_context(
                _archive_runtime_dependencies_on_failure(
                    external_root=Path(external_root),
                    shard_root=shard_root,
                    runtime_dependency_root=dependency_root,
                    expected_runtime_dependency_binding=seed[
                        "runtime_dependency_binding"
                    ],
                    output_path=fixed_paths["authority"],
                    binding_sink=failure_authority_state,
                )
            )
            candidate_root, archive_git_binding = stack.enter_context(
                sealed_capability_candidate_source(
                    CANDIDATE_COMMIT,
                    repository_root=repository_root,
                )
            )
            archive_binding = candidate_archive_manifest(
                candidate_root,
                repository_root=repository_root,
            )
            candidate_git = mechanism.bind_git_candidate_tree(
                CANDIDATE_COMMIT,
                repository_root=repository_root,
            )
            if (
                candidate_git["source_digest"]
                != source_binding["candidate_source_sha256"]
                or archive_git_binding.get("files")
                != candidate_git["files"]
            ):
                raise CapabilityEvaluationError(
                    "materialized candidate archive differs from sealed C"
                )
            source_probe = CleanSourceProbe(
                source_binding,
                seed_path=repository_root / SEED_RELATIVE_PATH,
                repository_root=repository_root,
            )
            budget_probe = run_budget_pre_mutation_probes(pairs)
            universe = EpisodeUniverse(pairs, prepared.schedule)
            runner = CandidateEpisodeRunner(
                candidate_root=candidate_root,
                worker_script=(
                    repository_root
                    / "scripts"
                    / "gwip_capability_worker.py"
                ),
                evidence_sink=sink,
                environment_factory=universe.environment_factory,
                source_probe=source_probe,
                repository_root=repository_root,
                runtime_dependency_root=dependency_root,
                runtime_dependency_binding=dependency_binding,
            )
            shard_store = WriteOnceShardStore(
                shard_root,
                schedule_sha256=prepared.schedule_sha256,
                attempt_sha256=attempt_binding["raw_sha256"],
                repository_root=repository_root,
            )

            def provide_gate_inputs(
                context: Mapping[str, Any],
            ) -> CapabilityGateInputs:
                return _gate_inputs(
                    schedule=context["schedule"],
                    episodes=context["episodes"],
                    parent_evidence=sink.snapshot(),
                    candidate_root=candidate_root,
                    candidate_binding=archive_binding,
                    runtime_dependency_root=dependency_root,
                    runtime_dependency_binding=dependency_binding,
                    source_binding=source_binding,
                    seed_manifest=seed,
                    budget_probe=budget_probe,
                    attempted_ordinals=context["attempted_ordinals"],
                    source_before=context["source_before"],
                    source_after=context["source_after"],
                    repository_root=repository_root,
                )

            harness = CapabilityHarness(
                schedule=prepared.schedule,
                schedule_sha256=prepared.schedule_sha256,
                issuer=issuer,
                shard_store=shard_store,
                request_factory=_request_factory(episode_inputs),
                episode_runner=runner,
                gate_registry=make_independent_gate_registry(
                    provide_gate_inputs,
                    fixture_nonproduction=False,
                ),
                empty_memory=canonical_empty_memory(),
                source_binding_probe=source_probe,
            )
            harness_result = harness.execute()
            candidate_episodes = copy.deepcopy(
                harness_result["episodes"]
            )
            parent_evidence = sink.snapshot()
            controls = run_controls(pairs, preregistration)
            authority_binding = _archive_authority_root(
                Path(external_root),
                shard_root=shard_root,
                runtime_dependency_root=dependency_root,
                expected_runtime_dependency_binding=seed[
                    "runtime_dependency_binding"
                ],
                output_path=fixed_paths["authority"],
            )
            final_gate_inputs = _gate_inputs(
                schedule=prepared.schedule,
                episodes=candidate_episodes,
                parent_evidence=parent_evidence,
                candidate_root=candidate_root,
                candidate_binding=archive_binding,
                runtime_dependency_root=dependency_root,
                runtime_dependency_binding=dependency_binding,
                source_binding=source_binding,
                seed_manifest=seed,
                budget_probe=budget_probe,
                attempted_ordinals=harness_result["attempted_ordinals"],
                source_before=harness_result["source_before"],
                source_after=harness_result["source_after"],
                repository_root=repository_root,
            )
            gate_results = evaluate_hard_gates(final_gate_inputs)
            harness_gate_results = _harness_gate_results(harness_result)
            if _gate_booleans(gate_results) != _gate_booleans(
                harness_gate_results
            ):
                raise CapabilityEvaluationError(
                    "hard-gate pass values changed on independent recomputation"
                )
            verification = verify_capability_evidence(
                pairs=pairs,
                episodes=candidate_episodes,
                parent_evidence=parent_evidence,
                controls=controls,
                hard_gates=_gate_booleans(gate_results),
                preregistration=preregistration,
            )
            raw_evidence = _success_raw(
                seed_record=seed_record,
                schedule_binding=schedule_binding,
                source_binding=source_binding,
                attempt_binding=attempt_binding,
                cohort_binding=cohort_binding,
                authority_binding=authority_binding,
                budget_probe=budget_probe,
                harness_result=harness_result,
                parent_evidence=parent_evidence,
                controls=controls,
                candidate_binding=archive_binding,
                runtime_dependency_binding=dependency_binding,
                independent_derivation=verification.raw_evidence,
            )
            _write_once(
                fixed_paths["raw"],
                _gzip_json_bytes(raw_evidence),
            )

            reopened = _read_gzip_json(
                fixed_paths["raw"],
                label="sealed capability raw evidence",
            )
            if reopened != raw_evidence:
                raise CapabilityEvaluationError(
                    "raw evidence differs after durable reopen"
                )
            reopened_audit = reopened["source_audit"]
            reopened_gate_results = evaluate_hard_gates(
                _gate_inputs(
                    schedule=prepared.schedule,
                    episodes=reopened["candidate_episodes"],
                    parent_evidence=reopened["parent_evidence"],
                    candidate_root=candidate_root,
                    candidate_binding=reopened_audit[
                        "candidate_archive_binding"
                    ],
                    runtime_dependency_root=dependency_root,
                    runtime_dependency_binding=reopened_audit[
                        "runtime_dependency_binding"
                    ],
                    source_binding=reopened["source_binding"],
                    seed_manifest=seed,
                    budget_probe=reopened[
                        "budget_pre_mutation_probe"
                    ],
                    attempted_ordinals=reopened_audit[
                        "attempted_ordinals"
                    ],
                    source_before=reopened_audit[
                        "harness_source_before"
                    ],
                    source_after=reopened_audit[
                        "harness_source_after"
                    ],
                    repository_root=repository_root,
                )
            )
            if _gate_booleans(reopened_gate_results) != _gate_booleans(
                gate_results
            ):
                raise CapabilityEvaluationError(
                    "hard-gate pass values changed after raw reopen"
                )
            reopened_verification = verify_capability_evidence(
                pairs=pairs,
                episodes=reopened["candidate_episodes"],
                parent_evidence=reopened["parent_evidence"],
                controls=reopened["controls"],
                hard_gates=_gate_booleans(reopened_gate_results),
                preregistration=preregistration,
            )
            if (
                reopened_verification.raw_evidence
                != reopened["independent_derivation"]
            ):
                raise CapabilityEvaluationError(
                    "semantic derivation changed after raw reopen"
                )
            receipt = _capability_receipt(
                raw_path=fixed_paths["raw"],
                raw_evidence=reopened,
                gate_results=reopened_gate_results,
                metrics=reopened_verification.metrics,
                exemplar=reopened_verification.exemplar,
            )
            identity = _verify_receipt_identity(
                receipt,
                raw_path=fixed_paths["raw"],
                raw_evidence=reopened,
                gate_results=reopened_gate_results,
                metrics=reopened_verification.metrics,
                exemplar=reopened_verification.exemplar,
            )
            if identity["passed"] is not True:
                raise CapabilityEvaluationError(
                    "receipt failed independent identity reconstruction "
                    "before execution-context teardown"
                )
            pending_receipt = receipt
        execution_context_unwound = True
        if pending_receipt is None:
            raise CapabilityEvaluationError(
                "verified receipt is absent after execution-context teardown"
            )
        receipt = _publish_verified_receipt(
            pending_receipt,
            execution_context_unwound=execution_context_unwound,
            receipt_path=fixed_paths["receipt"],
            raw_path=fixed_paths["raw"],
            raw_evidence=reopened,
            gate_results=reopened_gate_results,
            metrics=reopened_verification.metrics,
            exemplar=reopened_verification.exemplar,
        )
        return {
            "verdict": receipt["verdict"],
            "receipt_path": RECEIPT_RELATIVE_PATH,
            "raw_path": RAW_RELATIVE_PATH,
            "receipt_checksum_sha256": receipt["checksum_sha256"],
            "capability_claim": receipt["capability_claim"],
        }
    except Exception as exc:
        if attempt_binding is None:
            if not fixed_paths["attempt"].exists():
                raise
            expected_attempt = _attempt_payload(
                seed_commit=seed_commit,
                schedule_commit=schedule_commit,
                seed_binding=seed_binding,
                schedule=prepared.schedule,
            )
            observed_attempt = _read_json(
                fixed_paths["attempt"],
                label="write-once capability attempt",
            )
            if observed_attempt != expected_attempt:
                raise CapabilityEvaluationError(
                    "partially written attempt differs from frozen payload"
                ) from exc
            attempt_binding = {
                "path": ATTEMPT_RELATIVE_PATH,
                "raw_sha256": _raw_file_sha256(
                    fixed_paths["attempt"]
                ),
                "payload": observed_attempt,
            }
        parent_evidence = sink.snapshot()
        if authority_binding is None:
            archived_on_failure = failure_authority_state.get(
                "authority_binding"
            )
            if type(archived_on_failure) is dict:
                authority_binding = copy.deepcopy(archived_on_failure)
        if authority_binding is None and not fixed_paths["authority"].exists():
            try:
                with materialized_runtime_dependencies(
                    seed["runtime_dependency_binding"],
                    repository_root=repository_root,
                ) as (failure_dependency_root, _failure_dependency_binding):
                    authority_binding = _archive_authority_root(
                        Path(external_root),
                        shard_root=(
                            shard_root if shard_root.exists() else None
                        ),
                        runtime_dependency_root=failure_dependency_root,
                        expected_runtime_dependency_binding=seed[
                            "runtime_dependency_binding"
                        ],
                        output_path=fixed_paths["authority"],
                    )
            except Exception:
                authority_binding = None
        terminal = _write_terminal_after_attempt(
            failure=exc,
            seed_record=seed_record,
            schedule_binding=schedule_binding,
            source_binding=source_binding,
            attempt_binding=attempt_binding,
            cohort_binding=cohort_binding,
            candidate_episodes=candidate_episodes,
            parent_evidence=parent_evidence,
            budget_probe=budget_probe,
            authority_binding=authority_binding,
            raw_path=fixed_paths["raw"],
            receipt_path=fixed_paths["receipt"],
        )
        return {
            "verdict": terminal["verdict"],
            "receipt_path": RECEIPT_RELATIVE_PATH,
            "raw_path": RAW_RELATIVE_PATH,
            "receipt_checksum_sha256": terminal["checksum_sha256"],
            "capability_claim": False,
            "terminal_failure": terminal["failure"],
        }


def validate_v3_reseal_readiness(
    *,
    comparison_commit: str = "HEAD",
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Read-only proof that E3 may create the fixed-dataset v3 seed."""

    comparison = _full_commit(
        comparison_commit,
        repository_root=repository_root,
    )
    for ancestor in (
        CANDIDATE_COMMIT,
        V3_GATE_FIX_COMMIT,
        V3_RULE_VERIFIER_FIX_COMMIT,
        V3_PREREG_COMMIT,
    ):
        _require_ancestry(
            ancestor,
            comparison,
            strict=True,
            repository_root=repository_root,
        )
    _require_unchanged(
        CANDIDATE_COMMIT,
        comparison,
        ("packages",),
        repository_root=repository_root,
    )
    evaluator_delta = _validate_v3_evaluator_delta(
        evaluator_commit=comparison,
        repository_root=repository_root,
    )
    evaluator_git = evaluator_delta["evaluator_source_binding"]
    evaluator_working = mechanism.bind_working_paths(
        EVALUATOR_SOURCE_PATHS,
        repository_root=repository_root,
    )
    if evaluator_working["files"] != evaluator_git["files"]:
        raise CapabilityEvaluationError(
            "working evaluator bytes differ from proposed E3"
        )
    with _v3_run_profile():
        preregistration_binding = _sealed_preregistration_binding(
            comparison_commit=comparison,
            repository_root=repository_root,
        )
    v1_hashes = _v1_artifact_hashes(
        repository_root=repository_root
    )
    _require_v2_absent(repository_root=repository_root)
    dataset = _v3_dataset_binding(repository_root=repository_root)
    candidate = mechanism.bind_git_candidate_tree(
        CANDIDATE_COMMIT,
        repository_root=repository_root,
    )
    if (
        candidate["source_digest"] != V3_CANDIDATE_SOURCE_SHA256
        or not mechanism._git_working_paths_unchanged(
            CANDIDATE_COMMIT,
            ("packages",),
            repository_root=repository_root,
        )
    ):
        raise CapabilityEvaluationError(
            "candidate/package bytes differ from C"
        )
    lineage_preview = _v3_verification_lineage_base(
        source_binding={
            "schema_version": SOURCE_BINDING_SCHEMA,
            "candidate_commit": CANDIDATE_COMMIT,
            "candidate_source_sha256": candidate["source_digest"],
            "evaluator_commit": comparison,
            "evaluator_source_sha256": evaluator_git[
                "source_digest"
            ],
            "seed_manifest_sha256": "0" * 64,
        },
        repository_root=repository_root,
    )
    return {
        "schema_version": (
            "atanor.gwip-capability-reseal-readiness.v3"
        ),
        "passed": True,
        "comparison_commit": comparison,
        "preregistration_binding": preregistration_binding,
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_source_sha256": candidate["source_digest"],
        "evaluator_source_sha256": evaluator_git["source_digest"],
        "evaluator_changed_paths": lineage_preview[
            "v3_evaluator_changed_paths"
        ],
        "dataset_binding": dataset,
        "hard_gates": list(REQUIRED_HARD_GATES),
        "v1_artifacts": v1_hashes,
        "v2_status": "not_materialized",
        "production_default_on": False,
        "public_benchmark_claim": False,
        "writes_performed": False,
    }


def run_one_shot_capability_v3(
    *,
    seed_commit: str,
    external_root: Path,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Run exactly one v3 attempt with v1 candidate/data and E3 verifier."""

    global _ACTIVE_VERIFICATION_LINEAGE_BASE
    _v1_artifact_hashes(repository_root=repository_root)
    _require_v2_absent(repository_root=repository_root)
    with _v3_run_profile():
        _seed, seed_binding = load_sealed_seed(
            seed_commit=seed_commit,
            seed_path=repository_root / V3_SEED_RELATIVE_PATH,
            repository_root=repository_root,
        )
        _validate_v3_evaluator_delta(
            evaluator_commit=str(
                seed_binding["source_binding"]["evaluator_commit"]
            ),
            expected_source_sha256=str(
                seed_binding["source_binding"][
                    "evaluator_source_sha256"
                ]
            ),
            repository_root=repository_root,
        )
        _ACTIVE_VERIFICATION_LINEAGE_BASE = (
            _v3_verification_lineage_base(
                source_binding=seed_binding["source_binding"],
                repository_root=repository_root,
            )
        )
        return run_one_shot_capability(
            seed_commit=seed_commit,
            external_root=external_root,
            repository_root=repository_root,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sealed GWIP capability evaluator"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-evaluator")
    validate.add_argument("--comparison-commit", default="HEAD")
    seed = commands.add_parser("create-seed")
    seed.add_argument("--evaluator-commit", required=True)
    run = commands.add_parser("prepare-run")
    run.add_argument("--seed-commit", required=True)
    run.add_argument("--external-root", type=Path, required=True)
    validate_v3 = commands.add_parser("validate-reseal-v3")
    validate_v3.add_argument("--comparison-commit", default="HEAD")
    seed_v3 = commands.add_parser("create-seed-v3")
    seed_v3.add_argument("--evaluator-commit", required=True)
    run_v3 = commands.add_parser("prepare-run-v3")
    run_v3.add_argument("--seed-commit", required=True)
    run_v3.add_argument("--external-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "validate-evaluator":
        result = validate_evaluator_readiness(
            comparison_commit=args.comparison_commit
        )
    elif args.command == "create-seed":
        result = create_seed_manifest(
            evaluator_commit=args.evaluator_commit
        )
    elif args.command == "prepare-run":
        result = run_one_shot_capability(
            seed_commit=args.seed_commit,
            external_root=args.external_root,
        )
    elif args.command == "validate-reseal-v3":
        result = validate_v3_reseal_readiness(
            comparison_commit=args.comparison_commit
        )
    elif args.command == "create-seed-v3":
        result = create_v3_seed_manifest(
            evaluator_commit=args.evaluator_commit
        )
    elif args.command == "prepare-run-v3":
        result = run_one_shot_capability_v3(
            seed_commit=args.seed_commit,
            external_root=args.external_root,
        )
    else:  # pragma: no cover - argparse makes this unreachable.
        raise AssertionError(args.command)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
