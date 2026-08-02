"""Sealed execution and RunLease harness for the GWIP capability pilot.

This module is deliberately *not* the capability evaluator.  It owns the
precommitted semantic schedule, just-in-time RunLease issuance, the exact
four-worker execution boundary, write-once episode shards, and evidence
surfaces consumed by an evaluator.  In particular it never imports or calls a
candidate verifier to decide whether a trace, rule, receipt, or memory is
valid.

The production path is fail closed:

* semantic ordinals and micro-wave placement are reconstructed here;
* every authority identity except issue/expiry/signature is committed before
  execution;
* an evaluator-owned Ed25519 signer issues one unique RunLease per episode;
* target memories are detached and target policy updates are disabled;
* worker requests/results have exact schemas;
* every episode gets one exclusive-created evidence shard and no retry;
* the twelve hard gates are accepted only from evaluator-owned verifier
  callbacks, never from worker claims.

Focused tests may use ``fixture_nonproduction=True`` and fixture verifier
callbacks.  That marker is part of every resulting receipt and cannot pass the
production schedule validator.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]

SCHEDULE_SCHEMA = "atanor.gwip-capability-semantic-schedule.v1"
WORKER_REQUEST_SCHEMA = "atanor.gwip-capability-worker-request.v1"
WORKER_RESULT_SCHEMA = "atanor.gwip-capability-worker-result.v1"
SHARD_SCHEMA = "atanor.gwip-capability-episode-shard.v1"
HARNESS_RESULT_SCHEMA = "atanor.gwip-capability-harness-result.v1"
GATE_SURFACE_SCHEMA = "atanor.gwip-capability-hard-gate-surfaces.v1"
SOURCE_BINDING_SCHEMA = "atanor.gwip-capability-source-binding.v1"

FINAL_PAIR_COUNT = 64
EXACT_WORKER_COUNT = 4
SUPPORT_EPISODES_PER_PAIR = 4
TARGET_STARTS_PER_ARM = 4
TARGET_ARMS = ("matched_warm", "cold", "mismatched_warm")
ARM_CODES = {name: index for index, name in enumerate(TARGET_ARMS)}
LATIN_ARM_ORDERS = (
    ("matched_warm", "cold", "mismatched_warm"),
    ("matched_warm", "mismatched_warm", "cold"),
    ("cold", "matched_warm", "mismatched_warm"),
    ("cold", "mismatched_warm", "matched_warm"),
    ("mismatched_warm", "matched_warm", "cold"),
    ("mismatched_warm", "cold", "matched_warm"),
)

STEP_BUDGET = 24
LEASE_TTL_SECONDS = 3_600
ISSUE_TO_ACTIVATION_MAX_SECONDS = 120
WORKER_TIMEOUT_SECONDS = 1_200
FINISH_TO_SEAL_MAX_SECONDS = 120
TOTAL_LEASE_PATH_MAX_SECONDS = 1_440

REQUIRED_HARD_GATES = (
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

# These are evaluator probe locations, not a statement that a value at the
# location is trustworthy.  ``apply_forgery_hook`` deliberately mutates a
# worker-shaped result so an independent evaluator can prove rejection.
FORGERY_HOOK_PATHS = {
    "decision_receipt": (
        "/trace/semantic_trace/steps/0/decision_receipt"
    ),
    "world_snapshot": "/trace/semantic_trace/steps/0/world_snapshot",
    "authority_witness": (
        "/trace/semantic_trace/steps/0/authorization"
    ),
    "target_constraint": (
        "/trace/semantic_trace/goal/metadata/target_constraints/0/value"
    ),
    "rule_ir": (
        "/trace/semantic_trace/steps/0/proposal_proof/metadata/"
        "transition_rule_hypotheses/0/expression"
    ),
    "action_payload": (
        "/trace/semantic_trace/steps/0/valid_actions/0/payload"
    ),
    "support_citations": (
        "/trace/semantic_trace/steps/0/proposal_proof/metadata/"
        "transition_rule_hypotheses/0/support_edge_refs"
    ),
    "transfer_memory_chain": "/memory_before",
    "memory_before_digest": "/memory_before_sha256",
    "source_binding": "/source_binding_sha256",
    "semantic_ordinal": "/ordinal",
    "schedule_row_binding": "/schedule_row_sha256",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")

_SOURCE_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_commit",
        "candidate_source_sha256",
        "evaluator_commit",
        "evaluator_source_sha256",
        "seed_manifest_sha256",
    }
)
_SCHEDULE_FIELDS = frozenset(
    {
        "schema_version",
        "fixture_nonproduction",
        "pair_count",
        "worker_concurrency",
        "support_episode_count",
        "target_episode_count",
        "candidate_episode_count",
        "step_budget",
        "source_binding",
        "source_binding_sha256",
        "operator_key_id",
        "operator_root_path_sha256",
        "rows",
    }
)
_ROW_FIELDS = frozenset(
    {
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
        "lease_id",
        "nonce",
        "boundary_config_path",
        "live_context",
    }
)
_WORKER_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "schedule_row_sha256",
        "phase",
        "pair_index",
        "episode_index",
        "arm",
        "environment_seed",
        "policy_seed",
        "step_budget",
        "retain_policy_updates",
        "session_id",
        "goal_ir",
        "environment_spec",
        "policy_memory",
        "policy_memory_sha256",
        "episode_input_sha256",
        "source_binding_sha256",
    }
)
_WORKER_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "schedule_row_sha256",
        "trace",
        "operational_authority",
        "memory_before",
        "memory_before_sha256",
        "memory_after",
        "memory_after_sha256",
        "source_binding_sha256",
        "application_isolation",
        "repo_import_closure",
        "network_guard",
        "worker_claims",
    }
)


class HarnessContractError(ValueError):
    """A frozen harness contract or independently bound witness is invalid."""


class EpisodeExecutionError(HarnessContractError):
    """One semantic episode failed; the ordinal is never retried."""

    def __init__(self, ordinal: int, message: str) -> None:
        super().__init__(f"episode {ordinal}: {message}")
        self.ordinal = ordinal


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def episode_input_digest(
    *,
    goal_ir: Mapping[str, Any],
    environment_spec: Mapping[str, Any],
) -> str:
    """Bind the complete evaluator-owned goal and environment worker input."""

    if type(goal_ir) is not dict or type(environment_spec) is not dict:
        raise HarnessContractError(
            "episode goal and environment input must be exact objects"
        )
    return canonical_digest(
        {
            "schema_version": "atanor.gwip-capability-episode-input.v1",
            "goal_ir": copy.deepcopy(dict(goal_ir)),
            "environment_spec": copy.deepcopy(dict(environment_spec)),
        }
    )


def _lease_input_manifest_digest(
    row: Mapping[str, Any],
    *,
    seed_manifest_sha256: str,
) -> str:
    """Bind one lease to its seed and independently supplied episode input."""

    return canonical_digest(
        {
            "schema_version": (
                "atanor.gwip-capability-lease-input-binding.v1"
            ),
            "seed_manifest_sha256": seed_manifest_sha256,
            "ordinal": row["ordinal"],
            "phase": row["phase"],
            "pair_index": row["pair_index"],
            "episode_index": row["episode_index"],
            "start_index": row["start_index"],
            "arm": row["arm"],
            "arm_code": row["arm_code"],
            "memory_source_pair_index": row[
                "memory_source_pair_index"
            ],
            "retain_policy_updates": row["retain_policy_updates"],
            "environment_seed": row["environment_seed"],
            "policy_seed": row["policy_seed"],
            "step_budget": row["step_budget"],
            "episode_input_sha256": row["episode_input_sha256"],
        }
    )


def _json_artifact_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_once_bytes(path: Path, payload: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _resolved_outside_repository(path: Path, repository_root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise HarnessContractError("external path must be absolute")
    repository = Path(repository_root).resolve(strict=True)
    parent = candidate.parent.resolve(strict=True)
    resolved = parent / candidate.name
    try:
        resolved.relative_to(repository)
    except ValueError:
        return resolved
    raise HarnessContractError("external path must be outside repository")


def validate_source_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != _SOURCE_FIELDS:
        raise HarnessContractError("source binding fields mismatch")
    if value.get("schema_version") != SOURCE_BINDING_SCHEMA:
        raise HarnessContractError("source binding schema mismatch")
    for name in (
        "candidate_source_sha256",
        "evaluator_source_sha256",
        "seed_manifest_sha256",
    ):
        if _SHA256_RE.fullmatch(str(value.get(name))) is None:
            raise HarnessContractError(f"source binding {name} invalid")
    for name in ("candidate_commit", "evaluator_commit"):
        raw = value.get(name)
        if type(raw) is not str or re.fullmatch(r"[0-9a-f]{40}", raw) is None:
            raise HarnessContractError(f"source binding {name} invalid")
    return copy.deepcopy(dict(value))


def semantic_ordinal(
    *,
    pair_index: int,
    episode_index: int | None = None,
    arm: str | None = None,
    start_index: int | None = None,
) -> int:
    """Return the preregistered semantic ordinal, independent of wall time."""

    if type(pair_index) is not int or pair_index < 0:
        raise HarnessContractError("pair_index must be a nonnegative integer")
    if arm is None:
        if (
            type(episode_index) is not int
            or not 0 <= episode_index < SUPPORT_EPISODES_PER_PAIR
            or start_index is not None
        ):
            raise HarnessContractError("invalid support ordinal inputs")
        return pair_index * SUPPORT_EPISODES_PER_PAIR + episode_index
    if (
        arm not in ARM_CODES
        or type(start_index) is not int
        or not 0 <= start_index < TARGET_STARTS_PER_ARM
        or episode_index is not None
    ):
        raise HarnessContractError("invalid target ordinal inputs")
    return (
        FINAL_PAIR_COUNT * SUPPORT_EPISODES_PER_PAIR
        + pair_index * len(TARGET_ARMS) * TARGET_STARTS_PER_ARM
        + ARM_CODES[arm] * TARGET_STARTS_PER_ARM
        + start_index
    )


def latin_arm_order(pair_index: int) -> tuple[str, str, str]:
    if type(pair_index) is not int or pair_index < 0:
        raise HarnessContractError("pair_index must be nonnegative")
    return LATIN_ARM_ORDERS[pair_index % len(LATIN_ARM_ORDERS)]


def _stable_identifier(prefix: str, nonce: str, ordinal: int) -> str:
    suffix = hashlib.sha256(
        f"{prefix}:{nonce}:{ordinal}".encode("utf-8")
    ).hexdigest()
    return f"{prefix}-{ordinal:04d}-{suffix[:20]}"


def _unbound_rows(
    *,
    pair_count: int,
    schedule_nonce: str,
) -> list[dict[str, Any]]:
    if type(pair_count) is not int or pair_count <= 0 or pair_count % 4 != 0:
        raise HarnessContractError("pair_count must be a positive multiple of four")
    if type(schedule_nonce) is not str or len(schedule_nonce) < 16:
        raise HarnessContractError("schedule_nonce must contain at least 16 characters")

    rows: list[dict[str, Any]] = []
    support_waves = pair_count
    for pair_index in range(pair_count):
        lane = pair_index % EXACT_WORKER_COUNT
        group = pair_index // EXACT_WORKER_COUNT
        for episode_index in range(SUPPORT_EPISODES_PER_PAIR):
            ordinal = pair_index * SUPPORT_EPISODES_PER_PAIR + episode_index
            micro_wave = group * SUPPORT_EPISODES_PER_PAIR + episode_index
            rows.append(
                {
                    "ordinal": ordinal,
                    "phase": "support",
                    "pair_index": pair_index,
                    "episode_index": episode_index,
                    "start_index": None,
                    "arm": None,
                    "arm_code": None,
                    "memory_source_pair_index": pair_index,
                    "retain_policy_updates": True,
                    "micro_wave": micro_wave,
                    "lane": lane,
                    "execution_position": micro_wave * EXACT_WORKER_COUNT + lane,
                    "environment_seed": episode_index,
                    "policy_seed": 0,
                    "step_budget": STEP_BUDGET,
                    "episode_input_sha256": None,
                    "lease_id": _stable_identifier(
                        "gwip-capability-lease", schedule_nonce, ordinal
                    ),
                    "nonce": _stable_identifier(
                        "gwip-capability-nonce", schedule_nonce, ordinal
                    ),
                    "boundary_config_path": None,
                    "live_context": None,
                }
            )

    target_base = pair_count * SUPPORT_EPISODES_PER_PAIR
    for pair_index in range(pair_count):
        lane = pair_index % EXACT_WORKER_COUNT
        group = pair_index // EXACT_WORKER_COUNT
        for arm_position, arm in enumerate(latin_arm_order(pair_index)):
            for start_index in range(TARGET_STARTS_PER_ARM):
                ordinal = (
                    target_base
                    + pair_index * len(TARGET_ARMS) * TARGET_STARTS_PER_ARM
                    + ARM_CODES[arm] * TARGET_STARTS_PER_ARM
                    + start_index
                )
                micro_wave = (
                    support_waves
                    + group * len(TARGET_ARMS) * TARGET_STARTS_PER_ARM
                    + arm_position * TARGET_STARTS_PER_ARM
                    + start_index
                )
                if arm == "matched_warm":
                    memory_source = pair_index
                elif arm == "mismatched_warm":
                    memory_source = (pair_index + 1) % pair_count
                else:
                    memory_source = None
                rows.append(
                    {
                        "ordinal": ordinal,
                        "phase": "target",
                        "pair_index": pair_index,
                        "episode_index": None,
                        "start_index": start_index,
                        "arm": arm,
                        "arm_code": ARM_CODES[arm],
                        "memory_source_pair_index": memory_source,
                        "retain_policy_updates": False,
                        "micro_wave": micro_wave,
                        "lane": lane,
                        "execution_position": (
                            micro_wave * EXACT_WORKER_COUNT + lane
                        ),
                        "environment_seed": start_index,
                        "policy_seed": 0,
                        "step_budget": STEP_BUDGET,
                        "episode_input_sha256": None,
                        "lease_id": _stable_identifier(
                            "gwip-capability-lease", schedule_nonce, ordinal
                        ),
                        "nonce": _stable_identifier(
                            "gwip-capability-nonce", schedule_nonce, ordinal
                        ),
                        "boundary_config_path": None,
                        "live_context": None,
                    }
                )
    return sorted(rows, key=lambda item: item["ordinal"])


@dataclass(frozen=True)
class PreparedSchedule:
    schedule: dict[str, Any]
    schedule_sha256: str


class JITRunLeaseIssuer:
    """Evaluator-owned signer and precommitted external RunLease boundary.

    Call ``prepare_schedule`` before committing a schedule.  It provisions
    public keys and replay-domain identities, but no signed lease document.
    After the exact returned schedule is committed, call ``seal_schedule``.
    ``issue`` then fills only ``issued_at``, ``expires_at``, and the detached
    signature envelope.
    """

    def __init__(
        self,
        external_root: Path,
        *,
        repository_root: Path = REPO,
    ) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        self.repository_root = Path(repository_root).resolve(strict=True)
        requested = _resolved_outside_repository(
            Path(external_root),
            self.repository_root,
        )
        try:
            requested.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise HarnessContractError(
                "external issuer root already exists"
            ) from exc
        self.external_root = requested.resolve(strict=True)
        self._private_key = Ed25519PrivateKey.generate()
        public_key = self._private_key.public_key()
        public_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.key_id = (
            f"ed25519:{hashlib.sha256(public_raw).hexdigest()[:24]}"
        )
        self.public_key_path = self.external_root / "operator-public.pem"
        _write_once_bytes(
            self.public_key_path,
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )
        self._sealed_schedule_sha256: str | None = None
        self._sealed_schedule: dict[str, Any] | None = None
        self._prepared_episode_input_sha256: dict[int, str] | None = None
        self._execution_schedule_object_id: int | None = None
        self._issued_ordinals: set[int] = set()
        self._schedule_commit_binding: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def _provision_authority(
        self,
        row: Mapping[str, Any],
        *,
        source_binding: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        from packages.autonomy_envelope.run_lease import (
            GENERAL_INTERACTION_RUNNER_ID,
            RUN_LEASE_ACTIVE_RELATIVE_PATH,
            RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
            RUN_LEASE_CLAIMS_RELATIVE_PATH,
            RUN_LEASE_LOCK_RELATIVE_PATH,
            RUN_LEASE_REPLAY_IDENTITY_FILENAME,
            RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
            RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
            RunLeaseBoundaryConfig,
        )

        ordinal = int(row["ordinal"])
        episode_root = self.external_root / f"episode-{ordinal:04d}"
        replay_root = episode_root / "replay"
        replay_root.mkdir(parents=True, exist_ok=False)
        (replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH).mkdir()
        (replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH).mkdir()

        deployment_id = _stable_identifier(
            "atanor-gwip-capability-deployment",
            row["nonce"],
            ordinal,
        )
        ledger_id = (
            "atanor:autonomy-run-ledger:"
            + _stable_identifier("gwip-capability", row["nonce"], ordinal)
        )
        identity = {
            "schema_version": RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
            "ledger_id": ledger_id,
            "deployment_id": deployment_id,
            "resolved_root_sha256": hashlib.sha256(
                str(replay_root.resolve(strict=True)).encode("utf-8")
            ).hexdigest(),
            "lock_relative_path": RUN_LEASE_LOCK_RELATIVE_PATH,
            "claims_relative_path": RUN_LEASE_CLAIMS_RELATIVE_PATH,
            "active_relative_path": RUN_LEASE_ACTIVE_RELATIVE_PATH,
        }
        _write_once_bytes(
            replay_root / RUN_LEASE_REPLAY_IDENTITY_FILENAME,
            _json_artifact_bytes(identity),
        )
        boundary_config = {
            "schema_version": RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
            "operator_public_key_path": str(self.public_key_path),
            "expected_key_id": self.key_id,
            "operator_boundary_id": _stable_identifier(
                "atanor-gwip-capability-boundary",
                row["nonce"],
                ordinal,
            ),
            "deployment_id": deployment_id,
            "replay_root": str(replay_root.resolve(strict=True)),
            "emergency_stop_path": str(
                (episode_root / "EMERGENCY_STOP").resolve()
            ),
        }
        boundary_path = episode_root / "run-lease-trust.json"
        _write_once_bytes(boundary_path, _json_artifact_bytes(boundary_config))
        boundary = RunLeaseBoundaryConfig.from_external_file(
            boundary_path,
            repository_root=self.repository_root,
        )
        live_context = {
            "runner_id": GENERAL_INTERACTION_RUNNER_ID,
            "deployment_id": boundary.deployment_id,
            "runtime_instance_id": _stable_identifier(
                "gwip-capability-runtime",
                row["nonce"],
                ordinal,
            ),
            "runner_artifact_sha256": source_binding[
                "candidate_source_sha256"
            ],
            "config_sha256": source_binding["evaluator_source_sha256"],
            "input_manifest_sha256": _lease_input_manifest_digest(
                row,
                seed_manifest_sha256=source_binding[
                    "seed_manifest_sha256"
                ],
            ),
            "capability_manifest": {
                "schema_version": RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
                "action_classes": ["interaction.step"],
                "filesystem_policy_sha256": hashlib.sha256(
                    b"atanor.gwip.filesystem.none.v1"
                ).hexdigest(),
                "network_policy_sha256": hashlib.sha256(
                    b"atanor.gwip.network.none.v1"
                ).hexdigest(),
                "child_task_policy_sha256": hashlib.sha256(
                    b"atanor.gwip.child-task.none.v1"
                ).hexdigest(),
            },
            "limits": {
                "max_runtime_sec": LEASE_TTL_SECONDS,
                "max_cycles": STEP_BUDGET,
                "max_actions": STEP_BUDGET,
                "max_external_requests": 0,
                "max_external_response_bytes": 0,
                "max_scratch_write_bytes": 0,
                "max_child_tasks": 0,
                "max_concurrent_child_tasks": 0,
            },
            "scratch_boundary": {
                "boundary_id": f"gwip-capability-no-scratch-{ordinal:04d}",
                "resolved_root_sha256": hashlib.sha256(
                    f"atanor.gwip.capability.no-scratch.root.v1:{ordinal}".encode(
                        "utf-8"
                    )
                ).hexdigest(),
                "identity_manifest_sha256": hashlib.sha256(
                    (
                        "atanor.gwip.capability.no-scratch.identity.v1:"
                        f"{ordinal}"
                    ).encode("utf-8")
                ).hexdigest(),
            },
            "operator_boundary_id": boundary.operator_boundary_id,
            "operator_boundary_config_sha256": (
                boundary.operator_boundary_config_sha256
            ),
            "nonce_replay_domain": copy.deepcopy(boundary.replay_domain),
        }
        return str(boundary_path.resolve(strict=True)), live_context

    def prepare_schedule(
        self,
        *,
        source_binding: Mapping[str, Any],
        schedule_nonce: str,
        pair_count: int = FINAL_PAIR_COUNT,
        fixture_nonproduction: bool = False,
        episode_inputs: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> PreparedSchedule:
        if self._sealed_schedule_sha256 is not None:
            raise HarnessContractError("issuer schedule is already sealed")
        source = validate_source_binding(source_binding)
        if fixture_nonproduction is not True and pair_count != FINAL_PAIR_COUNT:
            raise HarnessContractError(
                "production schedule requires exactly 64 pairs"
            )
        if fixture_nonproduction is False and pair_count != FINAL_PAIR_COUNT:
            raise HarnessContractError("nonfinal pair count needs fixture marker")
        rows = _unbound_rows(
            pair_count=pair_count,
            schedule_nonce=schedule_nonce,
        )
        if type(episode_inputs) is not dict or set(episode_inputs) != set(
            range(len(rows))
        ):
            raise HarnessContractError(
                "evaluator-owned episode inputs are incomplete"
            )
        for row in rows:
            raw_input = episode_inputs[row["ordinal"]]
            if (
                type(raw_input) is not dict
                or frozenset(raw_input) != {"goal_ir", "environment_spec"}
                or type(raw_input["goal_ir"]) is not dict
                or type(raw_input["environment_spec"]) is not dict
            ):
                raise HarnessContractError(
                    "evaluator-owned episode input fields mismatch"
                )
            row["episode_input_sha256"] = episode_input_digest(
                goal_ir=raw_input["goal_ir"],
                environment_spec=raw_input["environment_spec"],
            )
        self._prepared_episode_input_sha256 = {
            row["ordinal"]: row["episode_input_sha256"] for row in rows
        }
        for row in rows:
            boundary_path, live_context = self._provision_authority(
                row,
                source_binding=source,
            )
            row["boundary_config_path"] = boundary_path
            row["live_context"] = live_context
        support_count = pair_count * SUPPORT_EPISODES_PER_PAIR
        target_count = (
            pair_count * len(TARGET_ARMS) * TARGET_STARTS_PER_ARM
        )
        schedule = {
            "schema_version": SCHEDULE_SCHEMA,
            "fixture_nonproduction": fixture_nonproduction,
            "pair_count": pair_count,
            "worker_concurrency": EXACT_WORKER_COUNT,
            "support_episode_count": support_count,
            "target_episode_count": target_count,
            "candidate_episode_count": support_count + target_count,
            "step_budget": STEP_BUDGET,
            "source_binding": source,
            "source_binding_sha256": canonical_digest(source),
            "operator_key_id": self.key_id,
            "operator_root_path_sha256": hashlib.sha256(
                str(self.external_root).encode("utf-8")
            ).hexdigest(),
            "rows": rows,
        }
        checked = validate_semantic_schedule(
            schedule,
            production=not fixture_nonproduction,
            repository_root=self.repository_root,
        )
        return PreparedSchedule(
            schedule=checked,
            schedule_sha256=canonical_digest(checked),
        )

    def seal_schedule(
        self,
        schedule: Mapping[str, Any],
        *,
        expected_sha256: str,
        schedule_commit: str | None = None,
        seed_commit: str | None = None,
        schedule_relative_path: str | None = None,
    ) -> dict[str, Any]:
        checked = validate_semantic_schedule(
            schedule,
            production=not bool(schedule.get("fixture_nonproduction")),
            repository_root=self.repository_root,
        )
        digest = canonical_digest(checked)
        if digest != expected_sha256 or _SHA256_RE.fullmatch(digest) is None:
            raise HarnessContractError("committed schedule digest mismatch")
        if checked["operator_key_id"] != self.key_id:
            raise HarnessContractError("schedule operator key mismatch")
        if (
            self._prepared_episode_input_sha256 is None
            or {
                row["ordinal"]: row["episode_input_sha256"]
                for row in checked["rows"]
            }
            != self._prepared_episode_input_sha256
        ):
            raise HarnessContractError(
                "schedule episode inputs differ from evaluator-owned design"
            )
        if checked["operator_root_path_sha256"] != hashlib.sha256(
            str(self.external_root).encode("utf-8")
        ).hexdigest():
            raise HarnessContractError("schedule operator root mismatch")
        if checked["fixture_nonproduction"] is False:
            if (
                type(schedule_commit) is not str
                or _COMMIT_RE.fullmatch(schedule_commit) is None
                or type(seed_commit) is not str
                or _COMMIT_RE.fullmatch(seed_commit) is None
                or type(schedule_relative_path) is not str
                or not schedule_relative_path
                or Path(schedule_relative_path).is_absolute()
                or ".." in Path(schedule_relative_path).parts
            ):
                raise HarnessContractError(
                    "production schedule requires an exact S/L git binding"
                )

            def git_bytes(arguments: Sequence[str]) -> bytes:
                completed = subprocess.run(
                    ["git", *arguments],
                    cwd=self.repository_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
                if completed.returncode != 0:
                    raise HarnessContractError(
                        "production schedule git binding failed"
                    )
                return completed.stdout

            resolved_l = git_bytes(
                ["rev-parse", f"{schedule_commit}^{{commit}}"]
            ).decode("ascii").strip()
            resolved_s = git_bytes(
                ["rev-parse", f"{seed_commit}^{{commit}}"]
            ).decode("ascii").strip()
            if resolved_l != schedule_commit or resolved_s != seed_commit:
                raise HarnessContractError(
                    "production schedule commit IDs are not canonical"
                )
            ancestry = subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    seed_commit,
                    schedule_commit,
                ],
                cwd=self.repository_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            if ancestry.returncode != 0 or seed_commit == schedule_commit:
                raise HarnessContractError(
                    "production schedule lacks strict S-to-L ancestry"
                )
            expected_raw = _json_artifact_bytes(checked)
            blob = git_bytes(
                ["show", f"{schedule_commit}:{schedule_relative_path}"]
            )
            working_path = (
                self.repository_root / schedule_relative_path
            ).resolve(strict=True)
            try:
                working_path.relative_to(self.repository_root)
            except ValueError as exc:
                raise HarnessContractError(
                    "production schedule path escapes repository"
                ) from exc
            working = working_path.read_bytes()
            if blob != expected_raw or working != expected_raw:
                raise HarnessContractError(
                    "production schedule differs from exact L blob"
                )
            for commit_field in ("candidate_commit", "evaluator_commit"):
                sealed_commit = checked["source_binding"][commit_field]
                precedes = subprocess.run(
                    [
                        "git",
                        "merge-base",
                        "--is-ancestor",
                        sealed_commit,
                        schedule_commit,
                    ],
                    cwd=self.repository_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
                if precedes.returncode != 0 or sealed_commit == schedule_commit:
                    raise HarnessContractError(
                        f"production schedule L does not follow {commit_field}"
                    )
            self._schedule_commit_binding = {
                "seed_commit": seed_commit,
                "schedule_commit": schedule_commit,
                "schedule_relative_path": schedule_relative_path,
                "schedule_blob_sha256": hashlib.sha256(blob).hexdigest(),
                "schedule_canonical_sha256": digest,
                "passed": True,
            }
        else:
            self._schedule_commit_binding = {
                "fixture_nonproduction": True,
                "schedule_canonical_sha256": digest,
                "passed": True,
            }
        self._sealed_schedule_sha256 = digest
        self._sealed_schedule = checked
        return copy.deepcopy(self._schedule_commit_binding)

    @property
    def schedule_commit_binding(self) -> dict[str, Any]:
        if self._schedule_commit_binding is None:
            raise HarnessContractError("schedule has not been commit-bound")
        return copy.deepcopy(self._schedule_commit_binding)

    def issue(
        self,
        schedule: Mapping[str, Any],
        *,
        ordinal: int,
    ) -> "BoundEpisodeAuthority":
        from packages.autonomy_envelope.operator_trust import (
            ED25519_SCHEME,
            SIGNATURE_FIELD,
            canonical_payload_bytes,
            payload_sha256,
        )
        from packages.autonomy_envelope.run_lease import (
            RUN_LEASE_PURPOSE,
            RUN_LEASE_SCHEMA_VERSION,
            RunLeaseBoundaryConfig,
            RunLeaseStore,
            verify_run_lease,
        )

        with self._lock:
            if self._sealed_schedule is None:
                raise HarnessContractError("schedule was not sealed by this issuer")
            if self._execution_schedule_object_id is None:
                checked_once = validate_semantic_schedule(
                    schedule,
                    production=not bool(
                        schedule.get("fixture_nonproduction")
                    ),
                    repository_root=self.repository_root,
                )
                if (
                    canonical_digest(checked_once)
                    != self._sealed_schedule_sha256
                ):
                    raise HarnessContractError(
                        "schedule was not sealed by this issuer"
                    )
                self._execution_schedule_object_id = id(schedule)
            elif id(schedule) != self._execution_schedule_object_id:
                raise HarnessContractError(
                    "execution schedule object changed after issuance began"
                )
            checked = self._sealed_schedule
            if (
                type(ordinal) is not int
                or not 0 <= ordinal < len(checked["rows"])
            ):
                raise HarnessContractError("lease ordinal out of range")
            if ordinal in self._issued_ordinals:
                raise HarnessContractError("semantic ordinal already issued")
            self._issued_ordinals.add(ordinal)
        row = checked["rows"][ordinal]
        expected_input_manifest = _lease_input_manifest_digest(
            row,
            seed_manifest_sha256=checked["source_binding"][
                "seed_manifest_sha256"
            ],
        )
        if (
            row["live_context"].get("input_manifest_sha256")
            != expected_input_manifest
        ):
            raise HarnessContractError(
                "RunLease episode input binding mismatch"
            )
        issued_monotonic = time.monotonic()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        issued = now - timedelta(seconds=1)
        expires = issued + timedelta(seconds=LEASE_TTL_SECONDS)
        document = {
            "schema_version": RUN_LEASE_SCHEMA_VERSION,
            "purpose": RUN_LEASE_PURPOSE,
            "lease_id": row["lease_id"],
            **copy.deepcopy(row["live_context"]),
            "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "nonce": row["nonce"],
            SIGNATURE_FIELD: {
                "scheme": ED25519_SCHEME,
                "key_id": self.key_id,
                "payload_sha256": "",
                "signature": "",
            },
        }
        digest = payload_sha256(document)
        document[SIGNATURE_FIELD] = {
            "scheme": ED25519_SCHEME,
            "key_id": self.key_id,
            "payload_sha256": digest,
            "signature": base64.b64encode(
                self._private_key.sign(canonical_payload_bytes(document))
            ).decode("ascii"),
        }
        boundary = RunLeaseBoundaryConfig.from_external_file(
            row["boundary_config_path"],
            repository_root=self.repository_root,
        )
        verified = verify_run_lease(
            document,
            trust_root=boundary.trust_root,
            live_context=row["live_context"],
        )
        if (
            verified.ok is not True
            or verified.reason != "run_lease_valid"
            or verified.lease_id != row["lease_id"]
        ):
            raise HarnessContractError(
                f"JIT RunLease verification failed: {verified.reason}"
            )
        return BoundEpisodeAuthority(
            ordinal=ordinal,
            schedule_row_sha256=canonical_digest(row),
            document=document,
            live_context=row["live_context"],
            store=RunLeaseStore(boundary),
            issued_monotonic=issued_monotonic,
        )


def validate_semantic_schedule(
    value: Mapping[str, Any],
    *,
    production: bool,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != _SCHEDULE_FIELDS:
        raise HarnessContractError("schedule fields mismatch")
    if value.get("schema_version") != SCHEDULE_SCHEMA:
        raise HarnessContractError("schedule schema mismatch")
    if type(value.get("fixture_nonproduction")) is not bool:
        raise HarnessContractError("schedule fixture marker invalid")
    if production and value["fixture_nonproduction"] is not False:
        raise HarnessContractError("fixture schedule cannot pass production validation")
    pair_count = value.get("pair_count")
    if (
        type(pair_count) is not int
        or pair_count <= 0
        or pair_count % EXACT_WORKER_COUNT != 0
        or (production and pair_count != FINAL_PAIR_COUNT)
    ):
        raise HarnessContractError("schedule pair count invalid")
    source = validate_source_binding(value.get("source_binding"))
    if value.get("source_binding_sha256") != canonical_digest(source):
        raise HarnessContractError("schedule source binding digest mismatch")
    if (
        value.get("worker_concurrency") != EXACT_WORKER_COUNT
        or value.get("step_budget") != STEP_BUDGET
        or type(value.get("operator_key_id")) is not str
        or not value["operator_key_id"]
        or _SHA256_RE.fullmatch(str(value.get("operator_root_path_sha256")))
        is None
    ):
        raise HarnessContractError("schedule fixed execution fields mismatch")
    support_count = pair_count * SUPPORT_EPISODES_PER_PAIR
    target_count = pair_count * len(TARGET_ARMS) * TARGET_STARTS_PER_ARM
    if (
        value.get("support_episode_count") != support_count
        or value.get("target_episode_count") != target_count
        or value.get("candidate_episode_count")
        != support_count + target_count
        or type(value.get("rows")) is not list
        or len(value["rows"]) != support_count + target_count
    ):
        raise HarnessContractError("schedule census mismatch")

    rows = copy.deepcopy(value["rows"])
    leases: set[str] = set()
    nonces: set[str] = set()
    boundaries: set[str] = set()
    positions: set[int] = set()
    wave_lanes: set[tuple[int, int]] = set()
    actual_by_ordinal: dict[int, dict[str, Any]] = {}
    repository = Path(repository_root).resolve(strict=True)
    for row in rows:
        if type(row) is not dict or frozenset(row) != _ROW_FIELDS:
            raise HarnessContractError("schedule row fields mismatch")
        ordinal = row.get("ordinal")
        if type(ordinal) is not int or ordinal in actual_by_ordinal:
            raise HarnessContractError("schedule ordinal invalid or repeated")
        actual_by_ordinal[ordinal] = row
        lease_id = row.get("lease_id")
        nonce = row.get("nonce")
        if (
            type(lease_id) is not str
            or _IDENTIFIER_RE.fullmatch(lease_id) is None
            or lease_id in leases
            or type(nonce) is not str
            or _NONCE_RE.fullmatch(nonce) is None
            or nonce in nonces
        ):
            raise HarnessContractError("schedule lease/nonce invalid or reused")
        leases.add(lease_id)
        nonces.add(nonce)
        raw_boundary = row.get("boundary_config_path")
        if type(raw_boundary) is not str or not raw_boundary:
            raise HarnessContractError("schedule boundary path missing")
        boundary = Path(raw_boundary)
        if not boundary.is_absolute():
            raise HarnessContractError("schedule boundary path is not absolute")
        boundary = boundary.resolve(strict=True)
        try:
            boundary.relative_to(repository)
        except ValueError:
            pass
        else:
            raise HarnessContractError("schedule boundary is inside repository")
        boundary_text = str(boundary)
        if boundary_text in boundaries:
            raise HarnessContractError("schedule boundary path reused")
        boundaries.add(boundary_text)
        if type(row.get("live_context")) is not dict:
            raise HarnessContractError("schedule live context missing")
        live = row["live_context"]
        if (
            live.get("runner_artifact_sha256")
            != source["candidate_source_sha256"]
            or live.get("config_sha256")
            != source["evaluator_source_sha256"]
            or _SHA256_RE.fullmatch(
                str(row.get("episode_input_sha256"))
            )
            is None
            or live.get("input_manifest_sha256")
            != _lease_input_manifest_digest(
                row,
                seed_manifest_sha256=source["seed_manifest_sha256"],
            )
            or live.get("limits", {}).get("max_runtime_sec")
            != LEASE_TTL_SECONDS
            or live.get("limits", {}).get("max_cycles") != STEP_BUDGET
            or live.get("limits", {}).get("max_actions") != STEP_BUDGET
        ):
            raise HarnessContractError("schedule live source/limit binding mismatch")
        position = row.get("execution_position")
        wave = row.get("micro_wave")
        lane = row.get("lane")
        if (
            type(position) is not int
            or position in positions
            or type(wave) is not int
            or wave < 0
            or type(lane) is not int
            or not 0 <= lane < EXACT_WORKER_COUNT
            or position != wave * EXACT_WORKER_COUNT + lane
            or (wave, lane) in wave_lanes
        ):
            raise HarnessContractError("schedule execution placement invalid")
        positions.add(position)
        wave_lanes.add((wave, lane))

    # Reconstruct all semantic and wall-clock fields instead of accepting rows
    # that are merely self-consistent.
    expected = _unbound_rows(
        pair_count=pair_count,
        schedule_nonce="validation-placeholder-0000",
    )
    # Lease IDs/nonces depend on the hidden schedule nonce, and authority fields
    # depend on external paths.  Every other field is exactly reconstructible.
    exempt = {
        "lease_id",
        "nonce",
        "boundary_config_path",
        "live_context",
        "episode_input_sha256",
    }
    for expected_row in expected:
        ordinal = expected_row["ordinal"]
        actual = actual_by_ordinal.get(ordinal)
        if actual is None:
            raise HarnessContractError("schedule ordinal census is incomplete")
        for field in _ROW_FIELDS - exempt:
            if actual.get(field) != expected_row.get(field):
                raise HarnessContractError(
                    f"schedule row {ordinal} {field} mismatch"
                )
    wave_counts: dict[int, int] = {}
    for row in rows:
        wave_counts[row["micro_wave"]] = wave_counts.get(row["micro_wave"], 0) + 1
    expected_waves = pair_count + (
        pair_count // EXACT_WORKER_COUNT
    ) * len(TARGET_ARMS) * TARGET_STARTS_PER_ARM
    if (
        sorted(wave_counts) != list(range(expected_waves))
        or any(count != EXACT_WORKER_COUNT for count in wave_counts.values())
    ):
        raise HarnessContractError("schedule does not form exact four-row waves")
    result = copy.deepcopy(dict(value))
    result["rows"] = sorted(rows, key=lambda item: item["ordinal"])
    return result


@dataclass
class BoundEpisodeAuthority:
    """One evaluator-owned, independently signed, single-use episode lease."""

    ordinal: int
    schedule_row_sha256: str
    document: dict[str, Any]
    live_context: dict[str, Any]
    store: Any
    issued_monotonic: float
    activated_monotonic: float | None = None
    finished_monotonic: float | None = None
    sealed_monotonic: float | None = None
    activation_receipt: dict[str, Any] | None = None
    finish_receipt: dict[str, Any] | None = None
    _authorization_count: int = 0
    _replay_reason: str | None = None

    def activate(self) -> dict[str, Any]:
        if self.activated_monotonic is not None:
            raise HarnessContractError("RunLease activation attempted twice")
        now = time.monotonic()
        if now - self.issued_monotonic > ISSUE_TO_ACTIVATION_MAX_SECONDS:
            raise HarnessContractError("RunLease issue-to-activation deadline exceeded")
        result = self.store.activate(
            document=self.document,
            live_context=self.live_context,
        )
        receipt = result.to_dict()
        if result.allowed is not True or result.reason != "run_lease_activated":
            raise HarnessContractError(
                f"RunLease activation rejected: {result.reason}"
            )
        self.activated_monotonic = time.monotonic()
        self.activation_receipt = receipt
        return copy.deepcopy(receipt)

    def authorize(self, *, action_id: str, step_index: int) -> dict[str, Any]:
        from packages.autonomy_envelope.run_lease import (
            GENERAL_INTERACTION_RUNNER_ID,
        )

        if self.activated_monotonic is None or self.finished_monotonic is not None:
            raise HarnessContractError("RunLease is not active")
        if type(action_id) is not str or not action_id:
            raise HarnessContractError("action_id must be non-empty")
        if step_index != self._authorization_count:
            raise HarnessContractError("RunLease authorization order mismatch")
        result = self.store.authorize(
            lease_id=self.document["lease_id"],
            runner_id=GENERAL_INTERACTION_RUNNER_ID,
            action_class="interaction.step",
            costs={
                "cycles": 1,
                "actions": 1,
                "external_requests": 0,
                "external_response_bytes": 0,
                "scratch_write_bytes": 0,
                "child_tasks": 0,
                "concurrent_child_tasks": 0,
            },
        )
        if result.allowed is not True:
            raise HarnessContractError(
                f"RunLease authorization rejected: {result.reason}"
            )
        self._authorization_count += 1
        return {
            "action_id": action_id,
            "step_index": step_index,
            "granted": True,
            "reason": result.reason,
            "authority_kind": "externally_signed_run_lease",
            "operational_evidence": {
                "runner_id": GENERAL_INTERACTION_RUNNER_ID,
                "action_class": "interaction.step",
                "lease_id_sha256": canonical_digest(
                    self.document["lease_id"]
                ),
                "counters": copy.deepcopy(result.counters),
            },
        }

    def finish(self, reason: str) -> dict[str, Any]:
        from packages.autonomy_envelope.run_lease import (
            GENERAL_INTERACTION_RUNNER_ID,
        )

        if self.activated_monotonic is None or self.finished_monotonic is not None:
            raise HarnessContractError("RunLease finish order invalid")
        result = self.store.finish(
            lease_id=self.document["lease_id"],
            runner_id=GENERAL_INTERACTION_RUNNER_ID,
            reason=reason,
        )
        if result.finished is not True or result.reason != "run_lease_finished":
            raise HarnessContractError(
                f"RunLease finish rejected: {result.reason}"
            )
        self.finished_monotonic = time.monotonic()
        self.finish_receipt = result.to_dict()
        return copy.deepcopy(self.finish_receipt)

    def seal(self, *, shard_sha256: str) -> dict[str, Any]:
        from packages.autonomy_envelope.run_lease import (
            GENERAL_INTERACTION_RUNNER_ID,
        )

        if (
            self.activated_monotonic is None
            or self.finished_monotonic is None
            or self.finish_receipt is None
            or _SHA256_RE.fullmatch(shard_sha256) is None
        ):
            raise HarnessContractError("RunLease cannot seal incomplete episode")
        now = time.monotonic()
        if now - self.finished_monotonic > FINISH_TO_SEAL_MAX_SECONDS:
            raise HarnessContractError("RunLease finish-to-seal deadline exceeded")
        if (
            self.finished_monotonic - self.activated_monotonic
            > WORKER_TIMEOUT_SECONDS
        ):
            raise HarnessContractError("RunLease worker deadline exceeded")
        if now - self.issued_monotonic > TOTAL_LEASE_PATH_MAX_SECONDS:
            raise HarnessContractError("RunLease committed path deadline exceeded")
        status = self.store.status()
        runner = status.get("runners", {}).get(GENERAL_INTERACTION_RUNNER_ID)
        if (
            status.get("state_ok") is not True
            or type(runner) is not dict
            or runner.get("state_ok") is not True
            or runner.get("status") != "finished"
            or runner.get("lease_id") != self.document["lease_id"]
            or runner.get("authorization_count") != self._authorization_count
        ):
            raise HarnessContractError("RunLease durable ledger is not sealed")
        replay = self.store.activate(
            document=self.document,
            live_context=self.live_context,
        )
        if replay.allowed is not False or replay.reason != "run_lease_replay":
            raise HarnessContractError("RunLease single-use replay check failed")
        self._replay_reason = replay.reason
        self.sealed_monotonic = time.monotonic()
        return {
            "ordinal": self.ordinal,
            "schedule_row_sha256": self.schedule_row_sha256,
            "lease_id_sha256": canonical_digest(self.document["lease_id"]),
            "nonce_sha256": canonical_digest(self.document["nonce"]),
            "authorization_count": self._authorization_count,
            "shard_sha256": shard_sha256,
            "activation_reason": self.activation_receipt["reason"],
            "finish_reason": self.finish_receipt["reason"],
            "single_use_replay_reason": self._replay_reason,
            "issue_to_activation_seconds": (
                self.activated_monotonic - self.issued_monotonic
            ),
            "worker_seconds": self.finished_monotonic
            - self.activated_monotonic,
            "finish_to_seal_seconds": self.sealed_monotonic
            - self.finished_monotonic,
            "total_seconds": self.sealed_monotonic
            - self.issued_monotonic,
            "passed": True,
        }


def validate_worker_request(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != _WORKER_REQUEST_FIELDS:
        raise HarnessContractError("worker request fields mismatch")
    if value.get("schema_version") != WORKER_REQUEST_SCHEMA:
        raise HarnessContractError("worker request schema mismatch")
    if (
        type(value.get("ordinal")) is not int
        or _SHA256_RE.fullmatch(str(value.get("schedule_row_sha256"))) is None
        or value.get("phase") not in {"support", "target"}
        or type(value.get("pair_index")) is not int
        or value.get("pair_index") < 0
        or value.get("step_budget") != STEP_BUDGET
        or type(value.get("retain_policy_updates")) is not bool
        or (value["phase"] == "target" and value["retain_policy_updates"])
        or type(value.get("session_id")) is not str
        or not value["session_id"]
        or type(value.get("goal_ir")) is not dict
        or type(value.get("environment_spec")) is not dict
        or type(value.get("policy_memory")) is not dict
        or value.get("policy_memory_sha256")
        != canonical_digest(value["policy_memory"])
        or value.get("episode_input_sha256")
        != episode_input_digest(
            goal_ir=value["goal_ir"],
            environment_spec=value["environment_spec"],
        )
        or _SHA256_RE.fullmatch(str(value.get("source_binding_sha256")))
        is None
    ):
        raise HarnessContractError("worker request value invalid")
    if value["phase"] == "support":
        if (
            type(value.get("episode_index")) is not int
            or value.get("arm") is not None
        ):
            raise HarnessContractError("support worker request identity invalid")
    elif (
        value.get("episode_index") is not None
        or value.get("arm") not in TARGET_ARMS
    ):
        raise HarnessContractError("target worker request identity invalid")
    return copy.deepcopy(dict(value))


def validate_worker_result(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    checked_request = validate_worker_request(request)
    if type(value) is not dict or frozenset(value) != _WORKER_RESULT_FIELDS:
        raise HarnessContractError("worker result fields mismatch")
    if (
        value.get("schema_version") != WORKER_RESULT_SCHEMA
        or value.get("ordinal") != checked_request["ordinal"]
        or value.get("schedule_row_sha256")
        != checked_request["schedule_row_sha256"]
        or value.get("source_binding_sha256")
        != checked_request["source_binding_sha256"]
        or type(value.get("trace")) is not dict
        or type(value.get("operational_authority")) is not list
        or type(value.get("memory_before")) is not dict
        or value.get("memory_before") != checked_request["policy_memory"]
        or value.get("memory_before_sha256")
        != checked_request["policy_memory_sha256"]
        or type(value.get("memory_after")) is not dict
        or value.get("memory_after_sha256")
        != canonical_digest(value["memory_after"])
        or any(
            type(value.get(name)) is not dict
            for name in (
                "application_isolation",
                "repo_import_closure",
                "network_guard",
                "worker_claims",
            )
        )
    ):
        raise HarnessContractError("worker result binding invalid")
    # Target output cannot mutate the detached starting memory.
    if (
        checked_request["retain_policy_updates"] is False
        and value["memory_after"] != checked_request["policy_memory"]
    ):
        raise HarnessContractError("target worker retained policy updates")
    return copy.deepcopy(dict(value))


class WriteOnceShardStore:
    """Exclusive-created, fsync'd, per-ordinal episode evidence."""

    def __init__(
        self,
        root: Path,
        *,
        schedule_sha256: str,
        attempt_sha256: str,
        repository_root: Path = REPO,
    ) -> None:
        if (
            _SHA256_RE.fullmatch(schedule_sha256) is None
            or _SHA256_RE.fullmatch(attempt_sha256) is None
        ):
            raise HarnessContractError("shard store seal digests invalid")
        path = _resolved_outside_repository(Path(root), repository_root)
        try:
            path.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise HarnessContractError("shard root already exists") from exc
        self.root = path.resolve(strict=True)
        self.schedule_sha256 = schedule_sha256
        self.attempt_sha256 = attempt_sha256
        self._written: set[int] = set()
        self._lock = threading.Lock()

    def write(
        self,
        *,
        ordinal: int,
        status: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if type(ordinal) is not int or ordinal < 0:
            raise HarnessContractError("shard ordinal invalid")
        if status not in {"complete", "failed"} or type(payload) is not dict:
            raise HarnessContractError("shard status/payload invalid")
        with self._lock:
            if ordinal in self._written:
                raise HarnessContractError("episode shard already written")
            self._written.add(ordinal)
        body = {
            "schema_version": SHARD_SCHEMA,
            "ordinal": ordinal,
            "status": status,
            "schedule_sha256": self.schedule_sha256,
            "attempt_sha256": self.attempt_sha256,
            "payload": copy.deepcopy(dict(payload)),
        }
        envelope = {
            **body,
            "payload_sha256": canonical_digest(body["payload"]),
            "shard_checksum_sha256": canonical_digest(body),
        }
        path = self.root / f"episode-{ordinal:04d}.json"
        raw = _json_artifact_bytes(envelope)
        _write_once_bytes(path, raw)
        if path.read_bytes() != raw:
            raise HarnessContractError("episode shard readback mismatch")
        return {
            "ordinal": ordinal,
            "path": str(path.resolve(strict=True)),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "shard_checksum_sha256": envelope["shard_checksum_sha256"],
            "status": status,
        }


@dataclass(frozen=True)
class IndependentGateRegistry:
    """Exact evaluator-owned verifier set for the twelve conjunctive gates."""

    verifiers: Mapping[
        str,
        Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ]
    fixture_nonproduction: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.fixture_nonproduction) is not bool
            or type(self.verifiers) is not dict
            or frozenset(self.verifiers) != frozenset(REQUIRED_HARD_GATES)
            or any(not callable(item) for item in self.verifiers.values())
        ):
            raise HarnessContractError(
                "independent gate registry must contain exactly twelve callables"
            )

    def evaluate(self, context: Mapping[str, Any]) -> dict[str, Any]:
        surfaces: dict[str, Any] = {}
        for name in REQUIRED_HARD_GATES:
            raw = self.verifiers[name](copy.deepcopy(dict(context)))
            if (
                type(raw) is not dict
                or raw.get("passed") not in {True, False}
                or type(raw.get("evidence")) is not dict
            ):
                raise HarnessContractError(
                    f"independent hard-gate verifier {name} returned invalid evidence"
                )
            evidence = copy.deepcopy(dict(raw["evidence"]))
            surfaces[name] = {
                "passed": raw["passed"],
                "evidence": evidence,
                "evidence_sha256": canonical_digest(evidence),
                "origin": (
                    "fixture_nonproduction"
                    if self.fixture_nonproduction
                    else "evaluator_recomputed"
                ),
            }
        return {
            "schema_version": GATE_SURFACE_SCHEMA,
            "fixture_nonproduction": self.fixture_nonproduction,
            "gates": surfaces,
            "all_passed": all(
                item["passed"] is True for item in surfaces.values()
            ),
            "worker_claims_accepted_as_evidence": False,
        }


def _pointer_tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise HarnessContractError("forgery pointer must be absolute")
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    ]


def apply_forgery_hook(
    worker_result: Mapping[str, Any],
    hook: str,
) -> dict[str, Any]:
    """Mutate one preregistered self-attestation surface for adversarial tests.

    The helper also reseals worker-owned digests where mechanically possible.
    It never updates evaluator-owned source, schedule, authority, or shard
    bindings, which is precisely what the independent verifier must notice.
    """

    if hook not in FORGERY_HOOK_PATHS:
        raise HarnessContractError("unknown forgery hook")
    forged = copy.deepcopy(dict(worker_result))
    tokens = _pointer_tokens(FORGERY_HOOK_PATHS[hook])
    parent: Any = forged
    for token in tokens[:-1]:
        if type(parent) is dict:
            if token not in parent:
                raise HarnessContractError(
                    f"forgery hook {hook} path is absent"
                )
            parent = parent[token]
        elif type(parent) is list and token.isdigit():
            index = int(token)
            if not 0 <= index < len(parent):
                raise HarnessContractError(
                    f"forgery hook {hook} index is absent"
                )
            parent = parent[index]
        else:
            raise HarnessContractError(
                f"forgery hook {hook} path is not traversable"
            )
    leaf = tokens[-1]
    if type(parent) is dict and leaf in parent:
        prior = parent[leaf]
        parent[leaf] = _forged_value(prior)
    elif type(parent) is list and leaf.isdigit() and int(leaf) < len(parent):
        index = int(leaf)
        parent[index] = _forged_value(parent[index])
    else:
        raise HarnessContractError(f"forgery hook {hook} leaf is absent")
    if type(forged.get("memory_before")) is dict:
        forged["memory_before_sha256"] = canonical_digest(
            forged["memory_before"]
        )
    if type(forged.get("memory_after")) is dict:
        forged["memory_after_sha256"] = canonical_digest(
            forged["memory_after"]
        )
    claims = forged.get("worker_claims")
    if type(claims) is dict:
        claims["self_resealed_after_forgery"] = True
        claims["forgery_hook"] = hook
    return forged


def _forged_value(value: Any) -> Any:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return value + ":forged"
    if type(value) is list:
        return [*value, "forged"]
    if type(value) is dict:
        return {**value, "caller_attested_forgery": True}
    if value is None:
        return "forged"
    raise HarnessContractError("forgery target type is unsupported")


EpisodeRequestFactory = Callable[
    [Mapping[str, Any], Mapping[str, Any]],
    Mapping[str, Any],
]
EpisodeRunner = Callable[
    [Mapping[str, Any], BoundEpisodeAuthority],
    Mapping[str, Any],
]
SourceBindingProbe = Callable[[], Mapping[str, Any] | str]


class CapabilityHarness:
    """Execute a frozen schedule in exact four-row micro-waves, once."""

    def __init__(
        self,
        *,
        schedule: Mapping[str, Any],
        schedule_sha256: str,
        issuer: JITRunLeaseIssuer,
        shard_store: WriteOnceShardStore,
        request_factory: EpisodeRequestFactory,
        episode_runner: EpisodeRunner,
        gate_registry: IndependentGateRegistry,
        empty_memory: Mapping[str, Any],
        source_binding_probe: SourceBindingProbe,
    ) -> None:
        self.schedule = validate_semantic_schedule(
            schedule,
            production=not bool(schedule.get("fixture_nonproduction")),
            repository_root=issuer.repository_root,
        )
        if canonical_digest(self.schedule) != schedule_sha256:
            raise HarnessContractError("harness schedule digest mismatch")
        if shard_store.schedule_sha256 != schedule_sha256:
            raise HarnessContractError("shard store schedule binding mismatch")
        if (
            gate_registry.fixture_nonproduction
            != self.schedule["fixture_nonproduction"]
        ):
            raise HarnessContractError("gate/schedule fixture status mismatch")
        if not all(
            callable(item)
            for item in (
                request_factory,
                episode_runner,
                source_binding_probe,
            )
        ):
            raise HarnessContractError("harness callbacks must be callable")
        if type(empty_memory) is not dict:
            raise HarnessContractError("canonical empty memory must be an object")
        self.schedule_sha256 = schedule_sha256
        self.issuer = issuer
        self.shard_store = shard_store
        self.request_factory = request_factory
        self.episode_runner = episode_runner
        self.gate_registry = gate_registry
        self.empty_memory = copy.deepcopy(dict(empty_memory))
        self.source_binding_probe = source_binding_probe
        self._attempted: set[int] = set()
        self._attempt_lock = threading.Lock()

    def _probe_sources(self) -> dict[str, Any]:
        raw = self.source_binding_probe()
        if type(raw) is dict:
            binding = validate_source_binding(raw)
            if binding != self.schedule["source_binding"]:
                raise HarnessContractError(
                    "clean candidate/evaluator source binding mismatch"
                )
            return {
                "kind": "full_candidate_evaluator_seed_binding",
                "binding": binding,
                "binding_sha256": canonical_digest(binding),
                "fixture_nonproduction": self.schedule[
                    "fixture_nonproduction"
                ],
            }
        if (
            self.schedule["fixture_nonproduction"] is True
            and type(raw) is str
            and raw
            == self.schedule["source_binding"]["evaluator_source_sha256"]
        ):
            return {
                "kind": "fixture_evaluator_digest_only",
                "evaluator_source_sha256": raw,
                "fixture_nonproduction": True,
            }
        raise HarnessContractError(
            "production source probe must rebind candidate, evaluator, and seed"
        )

    def _memory_for_row(
        self,
        row: Mapping[str, Any],
        support_memories: Mapping[int, Mapping[str, Any]],
    ) -> dict[str, Any]:
        if row["phase"] == "support":
            if row["episode_index"] == 0:
                return copy.deepcopy(self.empty_memory)
            prior = support_memories.get(row["pair_index"])
            if type(prior) is not dict:
                raise EpisodeExecutionError(
                    row["ordinal"], "support memory chain is incomplete"
                )
            return copy.deepcopy(dict(prior))
        source_pair = row["memory_source_pair_index"]
        if source_pair is None:
            return copy.deepcopy(self.empty_memory)
        source = support_memories.get(source_pair)
        if type(source) is not dict:
            raise EpisodeExecutionError(
                row["ordinal"], "target support memory source is missing"
            )
        return copy.deepcopy(dict(source))

    def _build_request(
        self,
        row: Mapping[str, Any],
        memory: Mapping[str, Any],
    ) -> dict[str, Any]:
        supplied = self.request_factory(
            copy.deepcopy(dict(row)),
            copy.deepcopy(dict(memory)),
        )
        if type(supplied) is not dict:
            raise EpisodeExecutionError(
                row["ordinal"], "request factory returned a non-object"
            )
        goal_ir = supplied.get("goal_ir")
        environment_spec = supplied.get("environment_spec")
        input_sha256 = episode_input_digest(
            goal_ir=goal_ir,
            environment_spec=environment_spec,
        )
        if input_sha256 != row["episode_input_sha256"]:
            raise EpisodeExecutionError(
                row["ordinal"],
                "evaluator-owned episode input differs from committed schedule",
            )
        expected = {
            "schema_version": WORKER_REQUEST_SCHEMA,
            "ordinal": row["ordinal"],
            "schedule_row_sha256": canonical_digest(row),
            "phase": row["phase"],
            "pair_index": row["pair_index"],
            "episode_index": row["episode_index"],
            "arm": row["arm"],
            "environment_seed": row["environment_seed"],
            "policy_seed": row["policy_seed"],
            "step_budget": row["step_budget"],
            "retain_policy_updates": row["retain_policy_updates"],
            "session_id": (
                "gwip-session:"
                + hashlib.sha256(
                    (
                        "atanor.gwip.capability.session.v1:"
                        + row["nonce"]
                    ).encode("utf-8")
                ).hexdigest()[:32]
            ),
            "goal_ir": goal_ir,
            "environment_spec": environment_spec,
            "policy_memory": copy.deepcopy(dict(memory)),
            "policy_memory_sha256": canonical_digest(memory),
            "episode_input_sha256": input_sha256,
            "source_binding_sha256": self.schedule[
                "source_binding_sha256"
            ],
        }
        return validate_worker_request(expected)

    def _run_one(
        self,
        row: Mapping[str, Any],
        memory: Mapping[str, Any],
        source_before: str,
    ) -> dict[str, Any]:
        ordinal = row["ordinal"]
        with self._attempt_lock:
            if ordinal in self._attempted:
                raise EpisodeExecutionError(ordinal, "retry attempted")
            self._attempted.add(ordinal)
        authority: BoundEpisodeAuthority | None = None
        try:
            if canonical_digest(self._probe_sources()) != source_before:
                raise HarnessContractError("source binding changed before episode")
            authority = self.issuer.issue(self.schedule, ordinal=ordinal)
            if authority.schedule_row_sha256 != canonical_digest(row):
                raise HarnessContractError(
                    "issued RunLease does not match execution schedule row"
                )
            authority.activate()
            request = self._build_request(row, memory)
            started = time.monotonic()
            raw_result = self.episode_runner(
                copy.deepcopy(request),
                authority,
            )
            elapsed = time.monotonic() - started
            if elapsed > WORKER_TIMEOUT_SECONDS:
                raise HarnessContractError("worker timeout exceeded")
            result = validate_worker_result(raw_result, request=request)
            if authority.finished_monotonic is None:
                raise HarnessContractError(
                    "worker returned before evaluator authority finish"
                )
            if canonical_digest(self._probe_sources()) != source_before:
                raise HarnessContractError("source binding changed during episode")
            shard = self.shard_store.write(
                ordinal=ordinal,
                status="complete",
                payload={
                    "request": request,
                    "worker_result": result,
                    "worker_claims_are_non_authoritative": True,
                },
            )
            lease = authority.seal(shard_sha256=shard["raw_sha256"])
            return {
                "ordinal": ordinal,
                "request": request,
                "worker_result": result,
                "shard": shard,
                "run_lease": lease,
            }
        except Exception as exc:
            if (
                authority is not None
                and authority.activated_monotonic is not None
                and authority.finished_monotonic is None
            ):
                try:
                    authority.finish("harness_failure")
                except Exception:
                    pass
            failure = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "retry_forbidden": True,
            }
            try:
                self.shard_store.write(
                    ordinal=ordinal,
                    status="failed",
                    payload=failure,
                )
            except Exception as shard_exc:
                failure["shard_error"] = (
                    f"{type(shard_exc).__name__}:{shard_exc}"
                )
            raise EpisodeExecutionError(ordinal, str(exc)) from exc

    def execute(self) -> dict[str, Any]:
        source_before_receipt = self._probe_sources()
        source_before = canonical_digest(source_before_receipt)
        rows_by_wave: dict[int, list[dict[str, Any]]] = {}
        for row in self.schedule["rows"]:
            rows_by_wave.setdefault(row["micro_wave"], []).append(row)
        support_memories: dict[int, dict[str, Any]] = {}
        episodes: list[dict[str, Any]] = []
        with ThreadPoolExecutor(
            max_workers=EXACT_WORKER_COUNT,
            thread_name_prefix="gwip-capability",
        ) as pool:
            for wave in sorted(rows_by_wave):
                rows = sorted(
                    rows_by_wave[wave],
                    key=lambda item: item["lane"],
                )
                if (
                    len(rows) != EXACT_WORKER_COUNT
                    or [item["lane"] for item in rows]
                    != list(range(EXACT_WORKER_COUNT))
                ):
                    raise HarnessContractError(
                        "execution wave is not an exact four-worker wave"
                    )
                futures: dict[Future[dict[str, Any]], dict[str, Any]] = {}
                for row in rows:
                    memory = self._memory_for_row(row, support_memories)
                    future = pool.submit(
                        self._run_one,
                        row,
                        memory,
                        source_before,
                    )
                    futures[future] = row
                done, pending = wait(
                    futures,
                    timeout=WORKER_TIMEOUT_SECONDS,
                )
                if pending:
                    for future in pending:
                        future.cancel()
                    first = min(futures[future]["ordinal"] for future in pending)
                    raise EpisodeExecutionError(first, "worker hard timeout")
                wave_results = [future.result() for future in done]
                wave_results.sort(key=lambda item: item["ordinal"])
                for episode in wave_results:
                    row = self.schedule["rows"][episode["ordinal"]]
                    if row["phase"] == "support":
                        support_memories[row["pair_index"]] = copy.deepcopy(
                            episode["worker_result"]["memory_after"]
                        )
                    episodes.append(episode)
        if len(self._attempted) != self.schedule["candidate_episode_count"]:
            raise HarnessContractError("candidate episode census incomplete")
        source_after_receipt = self._probe_sources()
        if canonical_digest(source_after_receipt) != source_before:
            raise HarnessContractError("source binding changed across harness run")
        episodes.sort(key=lambda item: item["ordinal"])
        gate_context = {
            "schedule": copy.deepcopy(self.schedule),
            "schedule_sha256": self.schedule_sha256,
            "episodes": copy.deepcopy(episodes),
            "attempted_ordinals": sorted(self._attempted),
            "source_before": source_before_receipt,
            "source_after": source_after_receipt,
            "forgery_hooks": copy.deepcopy(FORGERY_HOOK_PATHS),
        }
        gates = self.gate_registry.evaluate(gate_context)
        return {
            "schema_version": HARNESS_RESULT_SCHEMA,
            "fixture_nonproduction": self.schedule[
                "fixture_nonproduction"
            ],
            "schedule_sha256": self.schedule_sha256,
            "source_binding_sha256": self.schedule[
                "source_binding_sha256"
            ],
            "worker_concurrency": EXACT_WORKER_COUNT,
            "candidate_episode_count": len(episodes),
            "attempted_ordinals": sorted(self._attempted),
            "retried_ordinals": [],
            "support_memory_final_sha256": {
                str(pair): canonical_digest(memory)
                for pair, memory in sorted(support_memories.items())
            },
            "source_before": source_before_receipt,
            "source_after": source_after_receipt,
            "episodes": episodes,
            "hard_gate_surfaces": gates,
            "forgery_hook_paths": copy.deepcopy(FORGERY_HOOK_PATHS),
            "production_activation_authorized": False,
            "capability_claim": False,
        }


__all__ = [
    "ARM_CODES",
    "BoundEpisodeAuthority",
    "CapabilityHarness",
    "EpisodeExecutionError",
    "EXACT_WORKER_COUNT",
    "FINAL_PAIR_COUNT",
    "FORGERY_HOOK_PATHS",
    "GATE_SURFACE_SCHEMA",
    "HARNESS_RESULT_SCHEMA",
    "HarnessContractError",
    "IndependentGateRegistry",
    "ISSUE_TO_ACTIVATION_MAX_SECONDS",
    "JITRunLeaseIssuer",
    "LATIN_ARM_ORDERS",
    "PreparedSchedule",
    "REQUIRED_HARD_GATES",
    "SCHEDULE_SCHEMA",
    "SHARD_SCHEMA",
    "SOURCE_BINDING_SCHEMA",
    "STEP_BUDGET",
    "TARGET_ARMS",
    "TOTAL_LEASE_PATH_MAX_SECONDS",
    "WORKER_REQUEST_SCHEMA",
    "WORKER_RESULT_SCHEMA",
    "WORKER_TIMEOUT_SECONDS",
    "WriteOnceShardStore",
    "apply_forgery_hook",
    "canonical_digest",
    "canonical_json_bytes",
    "episode_input_digest",
    "latin_arm_order",
    "semantic_ordinal",
    "validate_semantic_schedule",
    "validate_source_binding",
    "validate_worker_request",
    "validate_worker_result",
]
