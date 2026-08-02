"""Frozen evaluator primitives for the GWIP / ARC-I0 mechanism gate.

This module deliberately does not contain a final cohort seed or nonce.  The
candidate and evaluator sources must first be sealed.  A later, separately
committed manifest supplies the seed and nonce to
:func:`generate_hidden_mechanics`; ``run-final`` refuses to proceed without
that manifest and an externally provisioned signed RunLease plan.

The evaluator owns the finite-state mechanics, controls, scoring, domain audit,
and write-once result envelope.  Candidate code receives only opaque
observations, evaluator-returned valid actions, step results, and the target
reference carried by its GoalIR.  Nothing in this module grants action
authority; the composition root must call the real RunLeaseStore directly.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import hashlib
import importlib
import io
import json
import math
import os
import queue
import random
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "data" / "eval" / "gwip_mechanism_prereg_v1.json"
WORKER = Path(__file__).resolve()

PREREG_SCHEMA = "atanor.gwip-mechanism-prereg.v1"
OBSERVATION_SCHEMA = "atanor.gwip-opaque-observation.v1"
RECEIPT_SCHEMA = "atanor.gwip-mechanism-evaluation-receipt.v1"
TRACE_SCHEMA = "atanor.gwip-episode-trace.v1"
SEED_MANIFEST_SCHEMA = "atanor.gwip-mechanism-seed-manifest.v1"
RUN_LEASE_PLAN_SCHEMA = "atanor.gwip-run-lease-plan.v1"
RAW_EVIDENCE_SCHEMA = "atanor.gwip-mechanism-raw-evidence.v1"
ATTEMPT_SCHEMA = "atanor.gwip-mechanism-attempt.v1"
WORKER_REQUEST_SCHEMA = "atanor.gwip-candidate-worker-request.v1"
WORKER_RESULT_SCHEMA = "atanor.gwip-candidate-worker-result.v1"
WORKER_RPC_SCHEMA = "atanor.gwip-environment-rpc.v1"

CANDIDATE_SOURCE_PATHS = (
    "packages/autonomy_envelope/run_lease.py",
    "packages/fusion_loop/__init__.py",
    "packages/fusion_loop/interactive.py",
    "packages/fusion_loop/interactive_organs.py",
)
EVALUATOR_SOURCE_PATHS = (
    "scripts/gwip_mechanism_eval.py",
    "data/eval/gwip_mechanism_prereg_v1.json",
    # These are the parent-owned authority implementation and detached
    # signature verifier.  They are bound as evaluator inputs as well as being
    # part of the candidate tree, and the final parent never imports them from
    # the candidate archive.
    "packages/autonomy_envelope/run_lease.py",
    "packages/autonomy_envelope/operator_trust.py",
)
TRUSTED_PARENT_SOURCE_PATHS = (
    "packages/autonomy_envelope/run_lease.py",
    "packages/autonomy_envelope/operator_trust.py",
)
SEED_MANIFEST_RELATIVE_PATH = "data/eval/gwip_mechanism_seed_manifest_v1.json"
CANDIDATE_POLICY_SEED = 0
FINAL_ATTEMPT = REPO / "data" / "eval" / "gwip_mechanism_attempt_v1.json"
FINAL_RAW_EVIDENCE = REPO / "data" / "eval" / "gwip_mechanism_raw_evidence_v1.json"
FINAL_RECEIPT = REPO / "data" / "eval" / "gwip_mechanism_receipt_v1.json"
PREPARED_RUN_LEASE_PLAN_FILENAME = "gwip_run_lease_plan_v1.json"

_PREREG_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_episode_count",
        "episodes_per_mechanic",
        "mechanic_count",
        "state_count_inclusive",
        "action_count_inclusive",
        "step_budget",
        "random_policy_seeds",
        "bootstrap_resamples",
        "bootstrap_seed",
        "minimum_mean_swae_delta",
        "minimum_one_sided_lcb",
        "require_no_success_regression",
        "candidate_source_must_precede_seed_manifest",
        "candidate_may_read_seed_manifest",
        "capability_claim",
        "public_benchmark_claim",
    }
)
_FROZEN_PREREG_VALUES = {
    "schema_version": PREREG_SCHEMA,
    "candidate_episode_count": 144,
    "episodes_per_mechanic": 3,
    "mechanic_count": 48,
    "state_count_inclusive": [8, 12],
    "action_count_inclusive": [3, 4],
    "step_budget": 20,
    "random_policy_seeds": list(range(32)),
    "bootstrap_resamples": 10_000,
    "bootstrap_seed": 2026072701,
    "minimum_mean_swae_delta": 0.05,
    "minimum_one_sided_lcb": 0.0,
    "require_no_success_regression": True,
    "candidate_source_must_precede_seed_manifest": True,
    "candidate_may_read_seed_manifest": False,
    "capability_claim": False,
    "public_benchmark_claim": False,
}

REQUIRED_HARD_GATES = (
    "call_order_and_stop",
    "step_budget_and_pre_mutation_denial",
    "run_lease_direct_authority",
    "run_lease_single_use_and_replay_rejection",
    "semantic_reexecution_determinism",
    "structural_cycle_replay",
    "fresh_environment_reexecution",
    "complete_lineage",
    "adversarial_self_attestation_rejection",
    "candidate_domain_neutrality",
    "candidate_runtime_import_closure",
    "candidate_fixed_source_guard_controls",
)

_DENIED_IMPORT_PREFIXES = (
    "packages.arc_agi",
    "packages.eval_evidence.arc_agi1_prediction",
    "packages.vsa_reasoning.tests.test_arc_probe",
    "scripts.arc_agi1_",
)
_DENIED_IMPORT_EXACT = {
    "__main__",
    "scripts.arc_agi1_emit",
    "scripts.arc_agi1_score",
    "scripts.gwip_mechanism_eval",
    "scripts.gwip_mechanism_worker",
}
_RUNTIME_ESCAPE_IMPORT_PREFIXES = (
    "_ctypes",
    "_socket",
    "_winapi",
    "ctypes",
    "importlib",
    "inspect",
    "multiprocessing",
    "pdb",
    "runpy",
    "socket",
    "subprocess",
)
_RUNTIME_ESCAPE_ATTRIBUTE_NAMES = {
    "__globals__",
    "__subclasses__",
    "_getframe",
    "ag_frame",
    "cr_frame",
    "f_back",
    "f_globals",
    "f_locals",
    "gi_frame",
    "tb_frame",
}
_RUNTIME_OBJECT_GRAPH_ESCAPE_ATTRIBUTES = {
    "get_objects",
    "get_referents",
    "get_referrers",
}
_DIRECT_FORBIDDEN_TOKEN = re.compile(
    r"\b(?:"
    r"arc_agi|arc-agi|"
    r"grid|cell|pixel|color|colour|"
    r"mechanic_id|fixture_seed|fixture_nonce|"
    r"generator_seed|generator_nonce|"
    r"hidden_transition_table|transition_table|oracle|"
    r"evaluator_index|private_ref|call_log"
    r"|seed_manifest|gwip_mechanism_eval|gwip_mechanism_worker"
    r")\b",
    re.IGNORECASE,
)
_DOMAIN_BRANCH_NAMES = {
    "domain",
    "domain_name",
    "environment_name",
    "game",
    "game_id",
    "mechanic",
    "mechanic_id",
    "task",
    "task_id",
}
_ARC_TASK_LITERAL = re.compile(r"^[0-9a-f]{8}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class EvaluationContractError(ValueError):
    """The frozen evaluator contract or an evaluator-owned witness is invalid."""


class StepBudgetExhausted(EvaluationContractError):
    """The environment refused a step beyond the preregistered budget."""


def canonical_json_bytes(value: Any) -> bytes:
    """Strict deterministic JSON bytes used by every evaluator binding."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_id(prefix: str, value: Any) -> tuple[str, str]:
    """Evaluator-owned implementation of the cognitive canonical-ID rule."""

    if type(prefix) is not str or not prefix or any(char.isspace() for char in prefix):
        raise EvaluationContractError("canonical ID prefix invalid")
    digest = canonical_digest(value)
    return f"{prefix}_{digest[:32]}", digest


_COGNITIVE_CONTRACT_PREFIXES = {
    "CognitiveEnvelope": "cenv",
    "GoalIR": "goal",
    "ProofCandidate": "proofc",
    "WorldSnapshot": "world",
    "CognitiveMoment": "moment",
    "DecisionReceipt": "decision",
}


def _independent_contract_identity(
    value: Any,
    expected_type: str,
) -> bool:
    """Verify a cognitive contract without its constructor or adapter."""

    if type(value) is not dict or value.get("contract_type") != expected_type:
        return False
    contract_id = value.get("contract_id")
    content_hash = value.get("content_hash")
    if type(contract_id) is not str or not _SHA256.fullmatch(str(content_hash)):
        return False
    payload = {
        key: copy.deepcopy(item)
        for key, item in value.items()
        if key not in {"contract_id", "content_hash"}
    }
    if expected_type == "ClaimEnvelope":
        tier = payload.get("tier")
        if type(tier) is not str or not tier:
            return False
        prefix = f"claim_{tier}"
    else:
        prefix = _COGNITIVE_CONTRACT_PREFIXES.get(expected_type)
        if prefix is None:
            return False
    expected_id, expected_hash = canonical_id(prefix, payload)
    return contract_id == expected_id and content_hash == expected_hash


def _apply_state_patch_independently(
    state: Mapping[str, Any],
    patch: Any,
) -> dict[str, Any]:
    """Evaluator-owned replay of the bounded root-level cycle reducer."""

    if type(state) is not dict or type(patch) is not dict:
        raise EvaluationContractError("cycle replay state/patch must be objects")
    if set(patch) - {"set", "delete"}:
        raise EvaluationContractError("cycle replay patch fields invalid")
    setters = patch.get("set", {})
    deleters = patch.get("delete", [])
    if type(setters) is not dict or type(deleters) is not list:
        raise EvaluationContractError("cycle replay patch shape invalid")
    if any(type(key) is not str or not key for key in setters):
        raise EvaluationContractError("cycle replay setter key invalid")
    if any(type(key) is not str or not key for key in deleters):
        raise EvaluationContractError("cycle replay delete key invalid")
    if len(deleters) != len(set(deleters)) or set(setters) & set(deleters):
        raise EvaluationContractError("cycle replay patch conflict")
    current = copy.deepcopy(dict(state))
    for key in deleters:
        current.pop(key, None)
    current.update(copy.deepcopy(setters))
    # Exercise the same strict JSON constraints used by the digest.
    canonical_json_bytes(current)
    return current


def sha256_text(value: str) -> str:
    if type(value) is not str:
        raise TypeError("sha256_text requires an exact string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationContractError(f"{label} is unreadable") from exc
    if type(value) is not dict:
        raise EvaluationContractError(f"{label} must be an exact JSON object")
    return value


def _validate_preregistration(value: Mapping[str, Any]) -> None:
    if type(value) is not dict or frozenset(value) != _PREREG_FIELDS:
        raise EvaluationContractError("GWIP preregistration fields mismatch")
    if dict(value) != _FROZEN_PREREG_VALUES:
        raise EvaluationContractError("GWIP frozen preregistration values changed")
    if (
        value["candidate_episode_count"]
        != value["mechanic_count"] * value["episodes_per_mechanic"]
    ):
        raise EvaluationContractError("GWIP preregistration episode census mismatch")


def load_preregistration(path: Path = PREREG) -> tuple[dict[str, Any], str]:
    """Load the exact preregistration frozen by commit 820ebdb3."""

    resolved = Path(path).resolve(strict=True)
    value = _load_json_object(resolved, "GWIP preregistration")
    _validate_preregistration(value)
    return copy.deepcopy(value), hashlib.sha256(resolved.read_bytes()).hexdigest()


def _validate_generator_inputs(generator_seed: str, generator_nonce: str) -> None:
    for value, label in (
        (generator_seed, "generator_seed"),
        (generator_nonce, "generator_nonce"),
    ):
        if type(value) is not str or not value.strip() or len(value) > 512:
            raise EvaluationContractError(f"{label} must be a bounded non-empty string")


def _derived_int(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def _opaque_ref(kind: str, secret: str, ordinal: int) -> str:
    digest = sha256_text(f"atanor.gwip.opaque.v1|{kind}|{secret}|{ordinal}")
    return f"{kind}_{digest[:24]}"


@dataclass(frozen=True)
class EpisodeSpec:
    episode_index: int
    start_ref: str
    optimal_steps: int

    def private_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Transition:
    state_ref: str
    action_ref: str
    next_state_ref: str

    def private_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class HiddenMechanic:
    """Evaluator-only deterministic FST.  Never pass this object to candidate code."""

    evaluator_index: int
    private_ref: str
    state_refs: tuple[str, ...]
    action_refs: tuple[str, ...]
    transitions: tuple[Transition, ...]
    goal_ref: str
    episodes: tuple[EpisodeSpec, ...]

    def transition(self, state_ref: str, action_ref: str) -> str:
        for edge in self.transitions:
            if edge.state_ref == state_ref and edge.action_ref == action_ref:
                return edge.next_state_ref
        raise EvaluationContractError("state/action pair is outside hidden mechanic")

    def public_descriptor(self) -> dict[str, Any]:
        """Non-secret census.  It contains no token, seed, table, or mechanic identity."""

        return {
            "schema_version": "atanor.gwip-opaque-mechanic-census.v1",
            "state_count": len(self.state_refs),
            "action_count": len(self.action_refs),
            "episode_count": len(self.episodes),
        }

    def private_dict(self) -> dict[str, Any]:
        return {
            "evaluator_index": self.evaluator_index,
            "private_ref": self.private_ref,
            "state_refs": list(self.state_refs),
            "action_refs": list(self.action_refs),
            "transitions": [item.private_dict() for item in self.transitions],
            "goal_ref": self.goal_ref,
            "episodes": [item.private_dict() for item in self.episodes],
        }


def shortest_path_steps(
    mechanic: HiddenMechanic,
    start_ref: str,
    goal_ref: str,
) -> int | None:
    """Evaluator oracle: shortest directed path under the hidden action table."""

    if start_ref not in mechanic.state_refs or goal_ref not in mechanic.state_refs:
        return None
    if start_ref == goal_ref:
        return 0
    queue: deque[tuple[str, int]] = deque([(start_ref, 0)])
    visited = {start_ref}
    while queue:
        state, depth = queue.popleft()
        for action in mechanic.action_refs:
            nxt = mechanic.transition(state, action)
            if nxt == goal_ref:
                return depth + 1
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))
    return None


def _build_mechanic(
    *,
    preregistration: Mapping[str, Any],
    generator_seed: str,
    generator_nonce: str,
    index: int,
) -> HiddenMechanic:
    secret = sha256_text(
        f"atanor.gwip.hidden-mechanic.v1|{generator_seed}|{generator_nonce}|{index}"
    )
    rng = random.Random(_derived_int("gwip-fst", secret))
    state_low, state_high = preregistration["state_count_inclusive"]
    action_low, action_high = preregistration["action_count_inclusive"]
    state_count = rng.randint(state_low, state_high)
    action_count = rng.randint(action_low, action_high)
    state_refs = tuple(_opaque_ref("state", secret, item) for item in range(state_count))
    action_values = [_opaque_ref("action", secret, item) for item in range(action_count)]
    rng.shuffle(action_values)
    action_refs = tuple(action_values)
    step_budget = preregistration["step_budget"]
    episodes_per_mechanic = preregistration["episodes_per_mechanic"]

    # Action-specific random permutations make every transition total and
    # deterministic without assigning any semantic meaning to an action token.
    # Regeneration is deterministic and bounded until at least three non-goal
    # starts are reachable inside the frozen budget.
    for attempt in range(256):
        attempt_rng = random.Random(_derived_int("gwip-fst-table", secret, str(attempt)))
        transitions: list[Transition] = []
        for action in action_refs:
            destinations = list(state_refs)
            attempt_rng.shuffle(destinations)
            transitions.extend(
                Transition(state, action, destination)
                for state, destination in zip(state_refs, destinations)
            )
        goal_ref = state_refs[attempt_rng.randrange(state_count)]
        provisional = HiddenMechanic(
            evaluator_index=index,
            private_ref="pending",
            state_refs=state_refs,
            action_refs=action_refs,
            transitions=tuple(transitions),
            goal_ref=goal_ref,
            episodes=(),
        )
        candidates: list[tuple[str, int]] = []
        for state in state_refs:
            distance = shortest_path_steps(provisional, state, goal_ref)
            if (
                state != goal_ref
                and distance is not None
                and 1 <= distance <= step_budget
            ):
                candidates.append((state, distance))
        if len(candidates) < episodes_per_mechanic:
            continue
        attempt_rng.shuffle(candidates)
        # Prefer nontrivial paths when available, but never alter the fixed
        # cohort size when a small random graph supplies only short paths.
        nontrivial = [item for item in candidates if item[1] >= 2]
        selected = (
            nontrivial[:episodes_per_mechanic]
            if len(nontrivial) >= episodes_per_mechanic
            else candidates[:episodes_per_mechanic]
        )
        episodes = tuple(
            EpisodeSpec(
                episode_index=episode_index,
                start_ref=start,
                optimal_steps=distance,
            )
            for episode_index, (start, distance) in enumerate(selected)
        )
        private_payload = {
            "evaluator_index": index,
            "state_refs": state_refs,
            "action_refs": action_refs,
            "transitions": [item.private_dict() for item in transitions],
            "goal_ref": goal_ref,
            "episodes": [item.private_dict() for item in episodes],
        }
        private_ref = f"mechanic_{canonical_digest(private_payload)[:24]}"
        return HiddenMechanic(
            evaluator_index=index,
            private_ref=private_ref,
            state_refs=state_refs,
            action_refs=action_refs,
            transitions=tuple(transitions),
            goal_ref=goal_ref,
            episodes=episodes,
        )
    raise EvaluationContractError(
        f"hidden mechanic {index} could not produce the frozen reachable cohort"
    )


def generate_hidden_mechanics(
    preregistration: Mapping[str, Any],
    *,
    generator_seed: str,
    generator_nonce: str,
) -> tuple[HiddenMechanic, ...]:
    """Generate the private cohort after candidate source seal.

    The function is pure and deterministic.  It does not persist a manifest or
    result and therefore cannot accidentally consume the final one-shot run.
    """

    # The final generator never accepts a caller-relaxed cohort or threshold
    # mapping.  Tests that need a smaller graph exercise ``_build_mechanic``
    # directly; the public cohort generator is tied to the committed contract.
    _validate_preregistration(preregistration)
    _validate_generator_inputs(generator_seed, generator_nonce)
    mechanic_count = preregistration["mechanic_count"]
    return tuple(
        _build_mechanic(
            preregistration=preregistration,
            generator_seed=generator_seed,
            generator_nonce=generator_nonce,
            index=index,
        )
        for index in range(mechanic_count)
    )


def private_cohort_digest(mechanics: Sequence[HiddenMechanic]) -> str:
    if not mechanics:
        raise EvaluationContractError("private cohort cannot be empty")
    if [item.evaluator_index for item in mechanics] != list(range(len(mechanics))):
        raise EvaluationContractError("private cohort indices are not contiguous")
    return canonical_digest([item.private_dict() for item in mechanics])


class OpaqueFSTEnvironment:
    """Evaluator-owned environment implementing the fixed public protocol."""

    def __init__(
        self,
        mechanic: HiddenMechanic,
        *,
        episode_index: int,
        step_budget: int,
    ) -> None:
        if type(mechanic) is not HiddenMechanic:
            raise TypeError("exact evaluator HiddenMechanic required")
        if (
            type(episode_index) is not int
            or episode_index < 0
            or episode_index >= len(mechanic.episodes)
        ):
            raise EvaluationContractError("episode_index is outside mechanic")
        if type(step_budget) is not int or step_budget <= 0:
            raise EvaluationContractError("step_budget must be a positive exact integer")
        self._mechanic = mechanic
        self._episode_index = episode_index
        self._step_budget = step_budget
        self._state_ref: str | None = None
        self._step_count = 0
        self._reset = False
        self._stopped = False
        self._call_log: list[dict[str, Any]] = []

    @property
    def state_ref(self) -> str:
        if self._state_ref is None:
            raise EvaluationContractError("environment has not reset")
        return self._state_ref

    @property
    def call_log(self) -> list[dict[str, Any]]:
        """Detached evaluator witness. Candidate output is never used to build it."""

        return copy.deepcopy(self._call_log)

    def _observation(self) -> dict[str, Any]:
        state = self.state_ref
        return {
            "schema_version": OBSERVATION_SCHEMA,
            "state_ref": state,
            "terminal": state == self._mechanic.goal_ref,
        }

    def reset(self, seed: int | None = None) -> dict[str, bool]:
        if self._reset:
            raise EvaluationContractError("environment reset may occur exactly once")
        if seed is not None and type(seed) is not int:
            raise EvaluationContractError("public reset seed must be an exact integer or null")
        self._state_ref = self._mechanic.episodes[self._episode_index].start_ref
        self._step_count = 0
        self._reset = True
        self._stopped = False
        self._call_log.append({"operation": "reset"})
        return {"reset": True}

    def _require_live(self) -> None:
        if not self._reset:
            raise EvaluationContractError("environment must reset before use")
        if self._stopped:
            raise EvaluationContractError("environment is already stopped")

    def observe(self) -> dict[str, Any]:
        self._require_live()
        observation = self._observation()
        self._call_log.append(
            {
                "operation": "observe",
                "observation": copy.deepcopy(observation),
                "observation_digest": canonical_digest(observation),
            }
        )
        return observation

    def valid_actions(self) -> tuple[str, ...]:
        self._require_live()
        actions = self._mechanic.action_refs
        self._call_log.append(
            {
                "operation": "valid_actions",
                "actions": list(actions),
                "actions_digest": canonical_digest(list(actions)),
            }
        )
        return actions

    def step(self, action_id: str) -> dict[str, Any]:
        self._require_live()
        if type(action_id) is not str or action_id not in self._mechanic.action_refs:
            raise EvaluationContractError("step action is not an evaluator valid action")
        if self._step_count >= self._step_budget:
            raise StepBudgetExhausted(
                "step budget exhausted before environment mutation"
            )
        before = self.state_ref
        after = self._mechanic.transition(before, action_id)
        self._state_ref = after
        self._step_count += 1
        observation = self._observation()
        terminal = bool(observation["terminal"])
        result = {
            "observation": observation,
            "terminal": terminal,
            "success": terminal,
            "stop_reason": "goal_reached" if terminal else None,
        }
        self._call_log.append(
            {
                "operation": "step",
                "step_index": self._step_count - 1,
                "action_id": action_id,
                "before_observation_digest": canonical_digest(
                    {
                        "schema_version": OBSERVATION_SCHEMA,
                        "state_ref": before,
                        "terminal": before == self._mechanic.goal_ref,
                    }
                ),
                "result": copy.deepcopy(result),
                "result_digest": canonical_digest(result),
            }
        )
        return result

    def stop(self, reason: str) -> dict[str, Any]:
        self._require_live()
        if type(reason) is not str or not reason.strip():
            raise EvaluationContractError("stop reason must be a non-empty exact string")
        self._stopped = True
        result = {
            "stopped": True,
            "reason": reason,
            "steps": self._step_count,
            "success": self.state_ref == self._mechanic.goal_ref,
        }
        self._call_log.append(
            {
                "operation": "stop",
                "result": copy.deepcopy(result),
                "result_digest": canonical_digest(result),
            }
        )
        return result


class ReactivePolicy:
    """Frozen stateless control from the preregistration."""

    @staticmethod
    def choose_action(
        observation: Mapping[str, Any],
        valid_actions: Sequence[str],
    ) -> str:
        actions = tuple(valid_actions)
        if not actions or any(type(item) is not str for item in actions):
            raise EvaluationContractError("reactive control requires valid action IDs")
        observation_digest = canonical_digest(dict(observation))
        return min(
            actions,
            key=lambda action: sha256_text(observation_digest + action),
        )


class RandomPolicy:
    """Uniform fixed-seed control, independently bound to one hidden mechanic."""

    def __init__(self, *, policy_seed: int, mechanic_binding: str) -> None:
        if type(policy_seed) is not int:
            raise EvaluationContractError("random policy seed must be an exact integer")
        if type(mechanic_binding) is not str or not mechanic_binding:
            raise EvaluationContractError("random policy mechanic binding required")
        self._rng = random.Random(
            _derived_int(
                "gwip-random-control-v1",
                str(policy_seed),
                mechanic_binding,
            )
        )

    def choose_action(
        self,
        observation: Mapping[str, Any],
        valid_actions: Sequence[str],
    ) -> str:
        del observation
        actions = tuple(valid_actions)
        if not actions or any(type(item) is not str for item in actions):
            raise EvaluationContractError("random control requires valid action IDs")
        return actions[self._rng.randrange(len(actions))]


_ARM_PERMUTATIONS = (
    ("candidate", "reactive", "random"),
    ("candidate", "random", "reactive"),
    ("reactive", "candidate", "random"),
    ("reactive", "random", "candidate"),
    ("random", "candidate", "reactive"),
    ("random", "reactive", "candidate"),
)


def counterbalanced_arm_order(mechanic_index: int) -> tuple[str, str, str]:
    if type(mechanic_index) is not int or mechanic_index < 0:
        raise EvaluationContractError("mechanic index must be nonnegative")
    return _ARM_PERMUTATIONS[mechanic_index % len(_ARM_PERMUTATIONS)]


def episode_swae(
    *,
    success: bool,
    optimal_steps: int,
    executed_steps: int,
) -> float:
    if type(success) is not bool:
        raise EvaluationContractError("episode success must be a literal boolean")
    if type(optimal_steps) is not int or optimal_steps <= 0:
        raise EvaluationContractError("optimal_steps must be a positive exact integer")
    if type(executed_steps) is not int or executed_steps < 0:
        raise EvaluationContractError("executed_steps must be a nonnegative exact integer")
    if not success:
        return 0.0
    if executed_steps == 0:
        raise EvaluationContractError("a successful episode cannot execute zero steps")
    value = optimal_steps / executed_steps
    if value > 1.0 + 1e-12:
        raise EvaluationContractError(
            "successful trace claims fewer steps than evaluator optimum"
        )
    return min(1.0, float(value))


@dataclass(frozen=True)
class EpisodeMetric:
    mechanic_index: int
    episode_index: int
    success: bool
    optimal_steps: int
    executed_steps: int
    swae: float
    stop_reason: str

    def __post_init__(self) -> None:
        if type(self.mechanic_index) is not int or self.mechanic_index < 0:
            raise EvaluationContractError("episode mechanic index invalid")
        if type(self.episode_index) is not int or self.episode_index < 0:
            raise EvaluationContractError("episode index invalid")
        expected = episode_swae(
            success=self.success,
            optimal_steps=self.optimal_steps,
            executed_steps=self.executed_steps,
        )
        if not math.isclose(float(self.swae), expected, abs_tol=1e-12):
            raise EvaluationContractError("episode SWAE does not match raw counts")
        if type(self.stop_reason) is not str or not self.stop_reason:
            raise EvaluationContractError("episode stop reason required")


@dataclass(frozen=True)
class PolicyAggregate:
    mechanic_swae: tuple[float, ...]
    mean_swae: float
    success_rate: float
    episode_count: int

    def __post_init__(self) -> None:
        if not self.mechanic_swae:
            raise EvaluationContractError("policy aggregate has no mechanics")
        values = tuple(float(item) for item in self.mechanic_swae)
        if any(not math.isfinite(item) or item < 0.0 or item > 1.0 for item in values):
            raise EvaluationContractError("mechanic SWAE values must be finite in [0,1]")
        if (
            not math.isfinite(float(self.mean_swae))
            or not math.isclose(
                float(self.mean_swae),
                sum(values) / len(values),
                abs_tol=1e-12,
            )
        ):
            raise EvaluationContractError("policy mean SWAE mismatch")
        if (
            not math.isfinite(float(self.success_rate))
            or not 0.0 <= float(self.success_rate) <= 1.0
        ):
            raise EvaluationContractError("policy success rate must be in [0,1]")
        if type(self.episode_count) is not int or self.episode_count <= 0:
            raise EvaluationContractError("policy episode count invalid")
        object.__setattr__(self, "mechanic_swae", values)
        object.__setattr__(self, "mean_swae", float(self.mean_swae))
        object.__setattr__(self, "success_rate", float(self.success_rate))

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanic_swae": list(self.mechanic_swae),
            "mean_swae": self.mean_swae,
            "success_rate": self.success_rate,
            "episode_count": self.episode_count,
        }


def aggregate_mechanics(
    episodes: Sequence[EpisodeMetric],
    *,
    mechanic_count: int,
    episodes_per_mechanic: int,
) -> PolicyAggregate:
    if type(mechanic_count) is not int or mechanic_count <= 0:
        raise EvaluationContractError("mechanic_count invalid")
    if type(episodes_per_mechanic) is not int or episodes_per_mechanic <= 0:
        raise EvaluationContractError("episodes_per_mechanic invalid")
    if len(episodes) != mechanic_count * episodes_per_mechanic:
        raise EvaluationContractError("episode metric census mismatch")
    grouped: dict[int, list[EpisodeMetric]] = {
        index: [] for index in range(mechanic_count)
    }
    seen: set[tuple[int, int]] = set()
    for episode in episodes:
        key = (episode.mechanic_index, episode.episode_index)
        if key in seen or episode.mechanic_index not in grouped:
            raise EvaluationContractError("episode metric identity mismatch")
        seen.add(key)
        grouped[episode.mechanic_index].append(episode)
    mechanic_values: list[float] = []
    for mechanic_index in range(mechanic_count):
        rows = sorted(grouped[mechanic_index], key=lambda item: item.episode_index)
        if (
            len(rows) != episodes_per_mechanic
            or [item.episode_index for item in rows]
            != list(range(episodes_per_mechanic))
        ):
            raise EvaluationContractError("per-mechanic episode census mismatch")
        mechanic_values.append(sum(item.swae for item in rows) / len(rows))
    success_rate = sum(1 for item in episodes if item.success) / len(episodes)
    return PolicyAggregate(
        mechanic_swae=tuple(mechanic_values),
        mean_swae=sum(mechanic_values) / len(mechanic_values),
        success_rate=success_rate,
        episode_count=len(episodes),
    )


def average_random_aggregates(
    aggregates: Sequence[PolicyAggregate],
    *,
    preregistration: Mapping[str, Any],
) -> PolicyAggregate:
    _validate_preregistration(preregistration)
    mechanic_count = preregistration["mechanic_count"]
    episodes_per_mechanic = preregistration["episodes_per_mechanic"]
    if len(aggregates) != len(preregistration["random_policy_seeds"]):
        raise EvaluationContractError("random aggregate seed census mismatch")
    expected_episode_count = mechanic_count * episodes_per_mechanic
    if any(
        len(item.mechanic_swae) != mechanic_count
        or item.episode_count != expected_episode_count
        for item in aggregates
    ):
        raise EvaluationContractError("random aggregate census mismatch")
    mechanic_values = tuple(
        sum(item.mechanic_swae[index] for item in aggregates) / len(aggregates)
        for index in range(mechanic_count)
    )
    success_rate = sum(item.success_rate for item in aggregates) / len(aggregates)
    return PolicyAggregate(
        mechanic_swae=mechanic_values,
        mean_swae=sum(mechanic_values) / mechanic_count,
        success_rate=success_rate,
        episode_count=expected_episode_count,
    )


def paired_bootstrap_lcb(
    candidate: Sequence[float],
    baseline: Sequence[float],
    *,
    resamples: int,
    seed: int,
) -> float:
    """One-sided 95% paired bootstrap LCB at mechanic grain.

    The quantile is the nearest-rank fifth percentile:
    ``sorted_bootstrap[ceil(0.05 * resamples) - 1]``.  Fixing this before
    results prevents a later percentile/interpolation choice from moving the
    gate.
    """

    candidate_values = tuple(float(item) for item in candidate)
    baseline_values = tuple(float(item) for item in baseline)
    if not candidate_values or len(candidate_values) != len(baseline_values):
        raise EvaluationContractError("paired bootstrap arrays must be equal and non-empty")
    if any(
        not math.isfinite(item) or not 0.0 <= item <= 1.0
        for item in (*candidate_values, *baseline_values)
    ):
        raise EvaluationContractError("paired bootstrap values must be finite in [0,1]")
    if type(resamples) is not int or resamples <= 0:
        raise EvaluationContractError("bootstrap resamples must be positive")
    if type(seed) is not int:
        raise EvaluationContractError("bootstrap seed must be an exact integer")
    differences = tuple(
        candidate_item - baseline_item
        for candidate_item, baseline_item in zip(candidate_values, baseline_values)
    )
    rng = random.Random(seed)
    count = len(differences)
    samples = [
        sum(differences[rng.randrange(count)] for _ in range(count)) / count
        for _ in range(resamples)
    ]
    samples.sort()
    index = max(0, math.ceil(0.05 * resamples) - 1)
    return float(samples[index])


def _compare_baseline(
    candidate: PolicyAggregate,
    baseline: PolicyAggregate,
    preregistration: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    if len(candidate.mechanic_swae) != len(baseline.mechanic_swae):
        raise EvaluationContractError(f"{label} mechanic census mismatch")
    mean_delta = candidate.mean_swae - baseline.mean_swae
    lcb = paired_bootstrap_lcb(
        candidate.mechanic_swae,
        baseline.mechanic_swae,
        resamples=int(preregistration["bootstrap_resamples"]),
        seed=int(preregistration["bootstrap_seed"]),
    )
    success_non_regression = (
        candidate.success_rate >= baseline.success_rate
        if preregistration["require_no_success_regression"] is True
        else True
    )
    material = mean_delta >= float(preregistration["minimum_mean_swae_delta"])
    confidence = lcb > float(preregistration["minimum_one_sided_lcb"])
    return {
        "baseline": label,
        "mean_delta": mean_delta,
        "one_sided_95pct_paired_bootstrap_lcb": lcb,
        "candidate_success_rate": candidate.success_rate,
        "baseline_success_rate": baseline.success_rate,
        "material_delta": material,
        "positive_lcb": confidence,
        "success_non_regression": success_non_regression,
        "passed": material and confidence and success_non_regression,
    }


def score_efficiency_gate(
    candidate: PolicyAggregate,
    reactive: PolicyAggregate,
    random_control: PolicyAggregate,
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the frozen no-go against both baselines independently."""

    _validate_preregistration(preregistration)
    reactive_result = _compare_baseline(
        candidate,
        reactive,
        preregistration,
        label="reactive",
    )
    random_result = _compare_baseline(
        candidate,
        random_control,
        preregistration,
        label="random",
    )
    return {
        "schema_version": "atanor.gwip-efficiency-gate.v1",
        "mechanic_grain": len(candidate.mechanic_swae),
        "bootstrap_resamples": preregistration["bootstrap_resamples"],
        "bootstrap_quantile": "nearest_rank_5pct",
        "minimum_mean_swae_delta": preregistration[
            "minimum_mean_swae_delta"
        ],
        "comparisons": {
            "reactive": reactive_result,
            "random": random_result,
        },
        "passed": reactive_result["passed"] and random_result["passed"],
    }


def _module_is_denied(module_name: str) -> bool:
    return module_name in _DENIED_IMPORT_EXACT or any(
        module_name == prefix or module_name.startswith(prefix)
        for prefix in _DENIED_IMPORT_PREFIXES
    )


def _path_to_module(path: Path, root: Path) -> str | None:
    try:
        relative = path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except ValueError:
        return None
    if relative.suffix != ".py":
        return None
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_to_path(module_name: str, root: Path) -> Path | None:
    parts = module_name.split(".")
    module_file = root.joinpath(*parts).with_suffix(".py")
    package_file = root.joinpath(*parts, "__init__.py")
    if module_file.is_file():
        return module_file.resolve(strict=True)
    if package_file.is_file():
        return package_file.resolve(strict=True)
    return None


def _import_names(
    tree: ast.AST,
    current_module: str | None,
    *,
    current_is_package: bool,
) -> set[str]:
    names: set[str] = set()
    module_parts = [item for item in (current_module or "").split(".") if item]
    package_parts = module_parts if current_is_package else module_parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = max(0, len(package_parts) - (node.level - 1))
                base_parts = package_parts[:keep]
                if node.module:
                    base_parts.extend(node.module.split("."))
                base = ".".join(item for item in base_parts if item)
            else:
                base = node.module or ""
            if base:
                names.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        names.add(f"{base}.{alias.name}")
    return names


def _branch_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            names.add(item.id.lower())
        elif isinstance(item, ast.Attribute):
            names.add(item.attr.lower())
    return names


def audit_candidate_sources(
    paths: Sequence[Path],
    *,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Static direct-source and local import-closure audit.

    Forbidden-vocabulary and domain-branch checks apply to candidate files
    themselves. The recursive local closure is used only for the explicit ARC
    import denylist, so ordinary reusable dependencies are not blamed for
    unrelated prose.
    """

    root = Path(repository_root).resolve(strict=True)
    queue: deque[Path] = deque()
    direct: set[Path] = set()
    findings: list[str] = []
    for raw in paths:
        try:
            resolved = Path(raw).resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            findings.append(f"candidate source outside repository: {raw}: {exc}")
            continue
        if resolved.suffix != ".py":
            findings.append(f"candidate source is not Python: {resolved}")
            continue
        direct.add(resolved)
        queue.append(resolved)
    visited: set[Path] = set()
    closure_modules: set[str] = set()
    while queue:
        path = queue.popleft()
        if path in visited:
            continue
        visited.add(path)
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(f"candidate source unreadable/unparseable: {path}: {exc}")
            continue
        module_name = _path_to_module(path, root)
        imports = _import_names(
            tree,
            module_name,
            current_is_package=path.name == "__init__.py",
        )
        closure_modules.update(imports)
        for imported in sorted(imports):
            if _module_is_denied(imported):
                findings.append(f"forbidden import in closure: {imported}")
            if any(
                imported == prefix or imported.startswith(prefix + ".")
                for prefix in _RUNTIME_ESCAPE_IMPORT_PREFIXES
            ):
                findings.append(
                    "runtime escape import in candidate closure: "
                    f"{path.relative_to(root).as_posix()}:{imported}"
                )
            local = _module_to_path(imported, root)
            if local is not None and local not in visited:
                queue.append(local)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value.strip()
                if any(
                    literal == prefix or literal.startswith(prefix + ".")
                    for prefix in _RUNTIME_ESCAPE_IMPORT_PREFIXES
                ) or literal in _RUNTIME_ESCAPE_ATTRIBUTE_NAMES:
                    findings.append(
                        f"runtime escape module literal in candidate closure: "
                        f"{path.name}:{node.lineno}"
                    )
            elif (
                isinstance(node, ast.Attribute)
                and node.attr in _RUNTIME_ESCAPE_ATTRIBUTE_NAMES
            ):
                findings.append(
                    f"runtime frame escape attribute in candidate closure: "
                    f"{path.name}:{node.lineno}:{node.attr}"
                )
            elif (
                isinstance(node, ast.Attribute)
                and node.attr in _RUNTIME_OBJECT_GRAPH_ESCAPE_ATTRIBUTES
            ):
                findings.append(
                    f"runtime object-graph escape attribute in candidate closure: "
                    f"{path.name}:{node.lineno}:{node.attr}"
                )
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "sys"
                and node.attr == "modules"
            ):
                findings.append(
                    f"runtime module-registry escape in candidate closure: "
                    f"{path.name}:{node.lineno}"
                )
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and _module_is_denied(node.args[0].value)
            ):
                findings.append(
                    f"forbidden dynamic import in candidate closure: "
                    f"{path.name}:{node.lineno}"
                )
        if path not in direct:
            continue
        for match in _DIRECT_FORBIDDEN_TOKEN.finditer(text):
            findings.append(
                f"forbidden candidate vocabulary {match.group(0)!r} in {path.name}"
            )
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and (
                _branch_names(node.test) & _DOMAIN_BRANCH_NAMES
            ):
                findings.append(f"domain-specific branch in {path.name}:{node.lineno}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _ARC_TASK_LITERAL.fullmatch(node.value.lower()):
                    findings.append(
                        f"possible benchmark task ID in {path.name}:{node.lineno}"
                    )
    unique_findings = sorted(set(findings))
    return {
        "schema_version": "atanor.gwip-candidate-domain-audit.v1",
        "passed": not unique_findings,
        "direct_paths": sorted(str(path.relative_to(root)).replace("\\", "/") for path in direct),
        "local_closure_paths": sorted(
            str(path.relative_to(root)).replace("\\", "/") for path in visited
        ),
        "import_names": sorted(closure_modules),
        "findings": unique_findings,
    }


def audit_runtime_import_delta(
    modules_before: Iterable[str],
    modules_after: Iterable[str],
) -> dict[str, Any]:
    before = {str(item) for item in modules_before}
    after = {str(item) for item in modules_after}
    introduced = sorted(after - before)
    denied = sorted(item for item in introduced if _module_is_denied(item))
    return {
        "schema_version": "atanor.gwip-runtime-import-audit.v1",
        "passed": not denied,
        "introduced_modules": introduced,
        "forbidden_introduced_modules": denied,
    }


def _git_bytes(
    arguments: Sequence[str],
    *,
    repository_root: Path = REPO,
) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=Path(repository_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise EvaluationContractError(
            f"git {' '.join(arguments)} failed: {detail[:500]}"
        )
    return completed.stdout


def _validate_relative_source_path(value: str) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise EvaluationContractError("source binding path must be repository-relative")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise EvaluationContractError("source binding path is not canonical")
    return candidate.as_posix()


def bind_git_paths(
    commit: str,
    paths: Sequence[str],
    *,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Bind exact git blobs, not caller-provided source digest strings."""

    if not _GIT_COMMIT.fullmatch(commit):
        raise EvaluationContractError("source binding commit must be full SHA-1")
    normalized = tuple(_validate_relative_source_path(item) for item in paths)
    if not normalized or len(set(normalized)) != len(normalized):
        raise EvaluationContractError("source binding path census invalid")
    blobs: list[dict[str, str]] = []
    for path in normalized:
        raw = _git_bytes(
            ["show", f"{commit}:{path}"],
            repository_root=repository_root,
        )
        blobs.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest()})
    payload = {"commit": commit, "files": blobs}
    return {**payload, "source_digest": canonical_digest(payload)}


def bind_git_candidate_tree(
    commit: str,
    *,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Bind every tracked byte below ``packages/`` at one exact commit.

    The parent evaluator imports transitive ATANOR modules as well as the four
    direct GWIP files.  Binding only those direct files would allow a
    post-seed dependency edit to change authority or verification semantics.
    """

    if not _GIT_COMMIT.fullmatch(commit):
        raise EvaluationContractError("candidate tree commit must be full SHA-1")
    archive = _git_bytes(
        ["archive", "--format=tar", commit, "packages"],
        repository_root=repository_root,
    )
    records: list[dict[str, Any]] = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as handle:
        for member in sorted(handle.getmembers(), key=lambda item: item.name):
            if member.issym() or member.islnk() or member.isdev():
                raise EvaluationContractError(
                    "candidate git tree contains unsupported member"
                )
            if not member.isfile():
                continue
            stream = handle.extractfile(member)
            if stream is None:
                raise EvaluationContractError("candidate git member is unreadable")
            raw = stream.read()
            records.append(
                {
                    "path": member.name,
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    if not records:
        raise EvaluationContractError("candidate git tree is empty")
    payload = {
        "commit": commit,
        "root": "packages",
        "file_count": len(records),
        "files": records,
    }
    return {**payload, "source_digest": canonical_digest(payload)}


def bind_working_paths(
    paths: Sequence[str],
    *,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Bind bytes actually importable by the final runner."""

    root = Path(repository_root).resolve(strict=True)
    normalized = tuple(_validate_relative_source_path(item) for item in paths)
    blobs: list[dict[str, str]] = []
    for relative in normalized:
        path = (root / relative).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise EvaluationContractError("working source escaped repository") from exc
        blobs.append(
            {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    payload = {"files": blobs}
    return {**payload, "source_digest": canonical_digest(payload)}


def _git_is_ancestor(
    ancestor: str,
    descendant: str,
    *,
    strict: bool,
    repository_root: Path = REPO,
) -> bool:
    if (
        not _GIT_COMMIT.fullmatch(ancestor)
        or not _GIT_COMMIT.fullmatch(descendant)
        or (strict and ancestor == descendant)
    ):
        return False
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=Path(repository_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    return completed.returncode == 0


def _git_paths_unchanged(
    older: str,
    newer: str,
    paths: Sequence[str],
    *,
    repository_root: Path = REPO,
) -> bool:
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            older,
            newer,
            "--",
            *[_validate_relative_source_path(item) for item in paths],
        ],
        cwd=Path(repository_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    return completed.returncode == 0


def _git_working_paths_unchanged(
    commit: str,
    paths: Sequence[str],
    *,
    repository_root: Path = REPO,
) -> bool:
    """Compare clean-filtered working content, tolerating checkout EOL policy."""

    if not _GIT_COMMIT.fullmatch(commit):
        return False
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            commit,
            "--",
            *[_validate_relative_source_path(item) for item in paths],
        ],
        cwd=Path(repository_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    return completed.returncode == 0


_SEED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "preregistration_commit",
        "preregistration_raw_sha256",
        "candidate_commit",
        "candidate_source_sha256",
        "evaluator_commit",
        "evaluator_source_sha256",
        "generator_seed",
        "generator_nonce",
        "candidate_policy_seed",
        "environment_seed_rule",
        "counterbalance_rule",
    }
)


def load_and_verify_seed_manifest(
    path: Path,
    *,
    seed_manifest_commit: str,
    repository_root: Path = REPO,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify the post-candidate manifest against git blobs and working bytes."""

    root = Path(repository_root).resolve(strict=True)
    resolved = Path(path).resolve(strict=True)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise EvaluationContractError("seed manifest must be inside repository") from exc
    if relative != SEED_MANIFEST_RELATIVE_PATH:
        raise EvaluationContractError("seed manifest path is not the frozen path")
    if not _GIT_COMMIT.fullmatch(seed_manifest_commit):
        raise EvaluationContractError("seed manifest commit must be full SHA-1")
    raw = resolved.read_bytes()
    committed_raw = _git_bytes(
        ["show", f"{seed_manifest_commit}:{relative}"],
        repository_root=root,
    )
    if raw != committed_raw:
        raise EvaluationContractError(
            "working seed manifest differs from its designated git blob"
        )
    value = _load_json_object(resolved, "GWIP seed manifest")
    if frozenset(value) != _SEED_MANIFEST_FIELDS:
        raise EvaluationContractError("seed manifest fields mismatch")
    if value.get("schema_version") != SEED_MANIFEST_SCHEMA:
        raise EvaluationContractError("seed manifest schema mismatch")
    for name in ("preregistration_commit", "candidate_commit", "evaluator_commit"):
        if not _GIT_COMMIT.fullmatch(str(value.get(name))):
            raise EvaluationContractError(f"seed manifest {name} invalid")
    for name in (
        "preregistration_raw_sha256",
        "candidate_source_sha256",
        "evaluator_source_sha256",
    ):
        if not _SHA256.fullmatch(str(value.get(name))):
            raise EvaluationContractError(f"seed manifest {name} invalid")
    _validate_generator_inputs(value.get("generator_seed"), value.get("generator_nonce"))
    if (
        value.get("candidate_policy_seed") != CANDIDATE_POLICY_SEED
        or value.get("environment_seed_rule") != "episode_index"
        or value.get("counterbalance_rule") != "mechanic_index_mod_6"
    ):
        raise EvaluationContractError("seed manifest execution seeds/rules mismatch")

    preregistration, prereg_digest = load_preregistration()
    del preregistration
    if value["preregistration_raw_sha256"] != prereg_digest:
        raise EvaluationContractError("seed manifest preregistration digest mismatch")
    if not _git_is_ancestor(
        value["preregistration_commit"],
        value["candidate_commit"],
        strict=False,
        repository_root=root,
    ):
        raise EvaluationContractError("preregistration does not precede candidate seal")
    if not _git_is_ancestor(
        value["preregistration_commit"],
        value["evaluator_commit"],
        strict=False,
        repository_root=root,
    ):
        raise EvaluationContractError("preregistration does not precede evaluator seal")
    if not _git_is_ancestor(
        value["candidate_commit"],
        seed_manifest_commit,
        strict=True,
        repository_root=root,
    ):
        raise EvaluationContractError("candidate seal does not strictly precede seed manifest")
    if not _git_is_ancestor(
        value["evaluator_commit"],
        seed_manifest_commit,
        strict=True,
        repository_root=root,
    ):
        raise EvaluationContractError("evaluator seal does not strictly precede seed manifest")
    if not _git_paths_unchanged(
        value["candidate_commit"],
        seed_manifest_commit,
        ("packages",),
        repository_root=root,
    ):
        raise EvaluationContractError(
            "candidate source changed in the seed-manifest commit range"
        )
    if not _git_paths_unchanged(
        value["evaluator_commit"],
        seed_manifest_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=root,
    ):
        raise EvaluationContractError(
            "evaluator source changed in the seed-manifest commit range"
        )

    candidate_at_seal = bind_git_candidate_tree(
        value["candidate_commit"],
        repository_root=root,
    )
    candidate_at_seed = bind_git_candidate_tree(
        seed_manifest_commit,
        repository_root=root,
    )
    evaluator_at_seal = bind_git_paths(
        value["evaluator_commit"],
        EVALUATOR_SOURCE_PATHS,
        repository_root=root,
    )
    evaluator_at_seed = bind_git_paths(
        seed_manifest_commit,
        EVALUATOR_SOURCE_PATHS,
        repository_root=root,
    )
    evaluator_working = bind_working_paths(
        EVALUATOR_SOURCE_PATHS,
        repository_root=root,
    )
    if not (
        candidate_at_seal["source_digest"] == value["candidate_source_sha256"]
        and candidate_at_seed["files"] == candidate_at_seal["files"]
        and _git_working_paths_unchanged(
            value["candidate_commit"],
            ("packages",),
            repository_root=root,
        )
    ):
        raise EvaluationContractError(
            "candidate full-tree git/manifest/working binding mismatch"
        )
    if not (
        evaluator_at_seal["source_digest"] == value["evaluator_source_sha256"]
        and evaluator_at_seed["files"] == evaluator_at_seal["files"]
        and evaluator_working["files"] == evaluator_at_seal["files"]
    ):
        raise EvaluationContractError("evaluator git/manifest/working source binding mismatch")
    binding = {
        "path": relative,
        "commit": seed_manifest_commit,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate": candidate_at_seal,
        "evaluator": evaluator_at_seal,
    }
    return copy.deepcopy(value), binding


def bind_source_tree(root: Path) -> dict[str, Any]:
    """Hash every regular file in an isolated candidate archive."""

    base = Path(root).resolve(strict=True)
    records: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise EvaluationContractError("candidate archive contains a symlink")
        if not path.is_file():
            continue
        raw = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(base).as_posix(),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    if not records:
        raise EvaluationContractError("candidate archive is empty")
    return {
        "file_count": len(records),
        "files": records,
        "tree_sha256": canonical_digest(records),
    }


def _set_tree_read_only(root: Path, *, read_only: bool) -> None:
    paths = sorted(
        Path(root).rglob("*"),
        key=lambda item: len(item.parts),
        reverse=not read_only,
    )
    for path in paths:
        try:
            if path.is_dir():
                mode = stat.S_IREAD | stat.S_IEXEC
                if not read_only:
                    mode |= stat.S_IWRITE
            else:
                mode = stat.S_IREAD
                if not read_only:
                    mode |= stat.S_IWRITE
            path.chmod(mode)
        except OSError:
            if read_only:
                raise


@contextlib.contextmanager
def sealed_candidate_source(
    candidate_commit: str,
    *,
    repository_root: Path = REPO,
) -> Iterable[tuple[Path, dict[str, Any]]]:
    """Materialize only ``packages/`` from the pre-seed candidate commit."""

    if not _GIT_COMMIT.fullmatch(candidate_commit):
        raise EvaluationContractError("candidate archive commit invalid")
    archive = _git_bytes(
        ["archive", "--format=tar", candidate_commit, "packages"],
        repository_root=repository_root,
    )
    with tempfile.TemporaryDirectory(prefix="atanor-gwip-candidate-") as raw:
        root = Path(raw).resolve(strict=True)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as handle:
            members = handle.getmembers()
            for member in members:
                destination = (root / member.name).resolve()
                try:
                    destination.relative_to(root)
                except ValueError as exc:
                    raise EvaluationContractError(
                        "candidate archive member escapes root"
                    ) from exc
                if member.issym() or member.islnk() or member.isdev():
                    raise EvaluationContractError(
                        "candidate archive contains unsupported member"
                    )
            handle.extractall(root, filter="data")
        before = bind_source_tree(root)
        expected = bind_git_candidate_tree(
            candidate_commit,
            repository_root=repository_root,
        )
        if before["files"] != expected["files"]:
            raise EvaluationContractError("candidate archive full-tree binding mismatch")
        _set_tree_read_only(root, read_only=True)
        try:
            yield root, before
        finally:
            _set_tree_read_only(root, read_only=False)


@contextlib.contextmanager
def sealed_package_imports(candidate_root: Path) -> Iterable[None]:
    """Resolve every local ``packages.*`` import from the sealed archive.

    The evaluator process may already contain working-tree package modules
    when invoked from pytest, so they are saved and restored around the
    sealed run.  No working-tree ATANOR dependency participates while the
    parent owns hidden mechanics, scoring, or RunLease verification.
    """

    root = Path(candidate_root).resolve(strict=True)
    saved_modules = {
        name: module
        for name, module in tuple(sys.modules.items())
        if name == "packages" or name.startswith("packages.")
    }
    original_path = list(sys.path)
    for name in saved_modules:
        sys.modules.pop(name, None)
    retained: list[str] = []
    for raw in original_path:
        try:
            Path(raw or os.curdir).resolve().relative_to(REPO.resolve())
        except (OSError, ValueError):
            retained.append(raw)
    sys.path[:] = [str(root), *retained]
    importlib.invalidate_caches()
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if name == "packages" or name.startswith("packages."):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        sys.path[:] = original_path
        importlib.invalidate_caches()


@contextlib.contextmanager
def sealed_candidate_runtime(
    candidate_commit: str,
    *,
    repository_root: Path = REPO,
) -> Iterable[tuple[Path, dict[str, Any]]]:
    """Materialize and import the complete candidate tree as one sealed unit."""

    with sealed_candidate_source(
        candidate_commit,
        repository_root=repository_root,
    ) as values:
        with sealed_package_imports(values[0]):
            yield values


_RUN_LEASE_PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_episode_count",
        "entries",
    }
)
_RUN_LEASE_ENTRY_FIELDS = frozenset(
    {
        "ordinal",
        "mechanic_index",
        "episode_index",
        "boundary_config_path",
        "lease_document",
        "live_context",
    }
)
_GWIP_RUN_LEASE_CONTEXT_FIELDS = frozenset(
    {
        "runner_id",
        "deployment_id",
        "runtime_instance_id",
        "runner_artifact_sha256",
        "config_sha256",
        "input_manifest_sha256",
        "capability_manifest",
        "limits",
        "scratch_boundary",
        "operator_boundary_id",
        "operator_boundary_config_sha256",
        "nonce_replay_domain",
    }
)
_GWIP_RUN_LEASE_DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "purpose",
        "lease_id",
        *_GWIP_RUN_LEASE_CONTEXT_FIELDS,
        "issued_at",
        "expires_at",
        "nonce",
        "operator_signature",
    }
)
_ZERO_RESOURCE_LIMITS = {
    "max_external_requests": 0,
    "max_external_response_bytes": 0,
    "max_scratch_write_bytes": 0,
    "max_child_tasks": 0,
    "max_concurrent_child_tasks": 0,
}
_ZERO_COUNTERS = {
    "external_requests": 0,
    "external_response_bytes": 0,
    "scratch_write_bytes": 0,
    "child_tasks": 0,
    "concurrent_child_tasks": 0,
}
_PARENT_RUN_LEASE_FIELDS = frozenset(
    {
        "lease_id_sha256",
        "activation_reason",
        "payload_sha256",
        "trusted_parent_source_sha256",
        "authority_transcript_sha256",
        "authorization_count",
        "final_counters",
        "finish_reason",
        "single_use_replay_reason",
        "active_state_raw_sha256",
        "nonce_claim_raw_sha256",
        "passed",
    }
)


def _trusted_parent_source_records(
    tree_binding: Mapping[str, Any],
) -> list[dict[str, Any]]:
    files = tree_binding.get("files")
    if type(files) is not list:
        raise EvaluationContractError("candidate tree source records missing")
    by_path = {
        item.get("path"): item
        for item in files
        if type(item) is dict and type(item.get("path")) is str
    }
    records: list[dict[str, Any]] = []
    for path in TRUSTED_PARENT_SOURCE_PATHS:
        item = by_path.get(path)
        if (
            type(item) is not dict
            or type(item.get("size_bytes")) is not int
            or not _SHA256.fullmatch(str(item.get("sha256")))
        ):
            raise EvaluationContractError(
                f"trusted parent source missing from candidate seal: {path}"
            )
        records.append(
            {
                "path": path,
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
        )
    return records


def _validate_run_lease_entry(
    value: Mapping[str, Any],
    *,
    ordinal: int,
    mechanic_index: int,
    episode_index: int,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != _RUN_LEASE_ENTRY_FIELDS:
        raise EvaluationContractError("RunLease plan entry fields mismatch")
    if (
        value.get("ordinal") != ordinal
        or value.get("mechanic_index") != mechanic_index
        or value.get("episode_index") != episode_index
    ):
        raise EvaluationContractError("RunLease plan entry identity mismatch")
    raw_path = value.get("boundary_config_path")
    if type(raw_path) is not str or not raw_path:
        raise EvaluationContractError("RunLease boundary path missing")
    boundary_path = Path(raw_path)
    if not boundary_path.is_absolute():
        raise EvaluationContractError("RunLease boundary path must be absolute")
    boundary_path = boundary_path.resolve(strict=True)
    try:
        boundary_path.relative_to(Path(repository_root).resolve(strict=True))
    except ValueError:
        pass
    else:
        raise EvaluationContractError("RunLease boundary must be outside repository")
    document = value.get("lease_document")
    context = value.get("live_context")
    if (
        type(document) is not dict
        or frozenset(document) != _GWIP_RUN_LEASE_DOCUMENT_FIELDS
        or type(context) is not dict
        or frozenset(context) != _GWIP_RUN_LEASE_CONTEXT_FIELDS
    ):
        raise EvaluationContractError("RunLease document/context must be objects")
    from packages.autonomy_envelope.operator_trust import (  # noqa: PLC0415
        ED25519_SCHEME,
        SIGNATURE_FIELD,
    )
    from packages.autonomy_envelope.run_lease import (  # noqa: PLC0415
        RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
        RUN_LEASE_PURPOSE,
        RUN_LEASE_SCHEMA_VERSION,
        RunLeaseBoundaryConfig,
    )

    lease_id = document.get("lease_id")
    nonce = document.get("nonce")
    if (
        type(lease_id) is not str
        or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}",
            lease_id,
        )
        is None
        or type(nonce) is not str
        or re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", nonce) is None
    ):
        raise EvaluationContractError("RunLease document identity missing")
    if (
        context.get("runner_id") != "general-interaction-loop-v1"
        or any(
            type(context.get(field)) is not str
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}",
                context[field],
            )
            is None
            for field in (
                "deployment_id",
                "runtime_instance_id",
                "operator_boundary_id",
            )
        )
        or any(
            not _SHA256.fullmatch(str(context.get(field)))
            for field in (
                "runner_artifact_sha256",
                "config_sha256",
                "input_manifest_sha256",
                "operator_boundary_config_sha256",
            )
        )
    ):
        raise EvaluationContractError("RunLease context runner mismatch")

    capability = context.get("capability_manifest")
    if (
        type(capability) is not dict
        or frozenset(capability)
        != {
            "schema_version",
            "action_classes",
            "filesystem_policy_sha256",
            "network_policy_sha256",
            "child_task_policy_sha256",
        }
        or capability.get("schema_version")
        != RUN_LEASE_CAPABILITY_SCHEMA_VERSION
        or capability.get("action_classes") != ["interaction.step"]
        or capability.get("filesystem_policy_sha256")
        != sha256_text("atanor.gwip.filesystem.none.v1")
        or capability.get("network_policy_sha256")
        != sha256_text("atanor.gwip.network.none.v1")
        or capability.get("child_task_policy_sha256")
        != sha256_text("atanor.gwip.child-task.none.v1")
    ):
        raise EvaluationContractError("RunLease interaction capability mismatch")
    limits = context.get("limits")
    if (
        type(limits) is not dict
        or frozenset(limits)
        != {
            "max_runtime_sec",
            "max_cycles",
            "max_actions",
            *_ZERO_RESOURCE_LIMITS,
        }
        or limits.get("max_runtime_sec") != 3_600
        or limits.get("max_cycles") != 20
        or limits.get("max_actions") != 20
        or any(limits.get(key) != expected for key, expected in _ZERO_RESOURCE_LIMITS.items())
    ):
        raise EvaluationContractError("RunLease limits are not the frozen zero-I/O profile")
    scratch = context.get("scratch_boundary")
    if (
        type(scratch) is not dict
        or frozenset(scratch)
        != {
            "boundary_id",
            "resolved_root_sha256",
            "identity_manifest_sha256",
        }
        or scratch.get("boundary_id") != f"gwip-no-scratch-{ordinal:03d}"
        or scratch.get("resolved_root_sha256")
        != sha256_text(f"atanor.gwip.no-scratch.root.v1:{ordinal}")
        or scratch.get("identity_manifest_sha256")
        != sha256_text(
            f"atanor.gwip.no-scratch.identity.v1:{ordinal}"
        )
    ):
        raise EvaluationContractError(
            "RunLease no-scratch sentinel mismatch"
        )
    if (
        document.get("schema_version") != RUN_LEASE_SCHEMA_VERSION
        or document.get("purpose") != RUN_LEASE_PURPOSE
    ):
        raise EvaluationContractError("RunLease document schema/purpose mismatch")
    signature = document.get(SIGNATURE_FIELD)
    if (
        type(signature) is not dict
        or frozenset(signature)
        != {"scheme", "key_id", "payload_sha256", "signature"}
        or signature.get("scheme") != ED25519_SCHEME
        or type(signature.get("key_id")) is not str
        or not signature["key_id"]
        or not _SHA256.fullmatch(str(signature.get("payload_sha256")))
        or type(signature.get("signature")) is not str
        or not signature["signature"]
    ):
        raise EvaluationContractError("RunLease signature envelope mismatch")
    issued = _parse_utc_second(document.get("issued_at"))
    expires = _parse_utc_second(document.get("expires_at"))
    if (
        issued is None
        or expires is None
        or expires <= issued
        or (expires - issued).total_seconds() > limits["max_runtime_sec"]
    ):
        raise EvaluationContractError("RunLease signed window invalid")
    for key, item in context.items():
        if document[key] != item:
            raise EvaluationContractError(
                f"RunLease document/live context mismatch for {key}"
            )
    boundary = RunLeaseBoundaryConfig.from_external_file(
        boundary_path,
        repository_root=repository_root,
    )
    if (
        context.get("deployment_id") != boundary.deployment_id
        or context.get("operator_boundary_id")
        != boundary.operator_boundary_id
        or context.get("operator_boundary_config_sha256")
        != boundary.operator_boundary_config_sha256
        or context.get("nonce_replay_domain") != boundary.replay_domain
    ):
        raise EvaluationContractError(
            "RunLease context does not match external boundary"
        )
    return {
        **copy.deepcopy(dict(value)),
        "boundary_config_path": str(boundary_path),
    }


def load_run_lease_plan(
    path: Path,
    *,
    preregistration: Mapping[str, Any],
    repository_root: Path = REPO,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load operator-signed per-episode leases; no lease enters candidate RPC."""

    _validate_preregistration(preregistration)
    resolved = Path(path).resolve(strict=True)
    repository = Path(repository_root).resolve(strict=True)
    try:
        resolved.relative_to(repository)
    except ValueError:
        pass
    else:
        raise EvaluationContractError(
            "RunLease plan must be outside repository"
        )
    value = _load_json_object(resolved, "GWIP RunLease plan")
    if frozenset(value) != _RUN_LEASE_PLAN_FIELDS:
        raise EvaluationContractError("RunLease plan fields mismatch")
    if (
        value.get("schema_version") != RUN_LEASE_PLAN_SCHEMA
        or value.get("candidate_episode_count")
        != preregistration["candidate_episode_count"]
        or type(value.get("entries")) is not list
        or len(value["entries"]) != preregistration["candidate_episode_count"]
    ):
        raise EvaluationContractError("RunLease plan census mismatch")
    entries: list[dict[str, Any]] = []
    lease_ids: set[str] = set()
    nonces: set[str] = set()
    boundary_paths: set[str] = set()
    replay_root_digests: set[str] = set()
    replay_ledger_ids: set[str] = set()
    deployment_ids: set[str] = set()
    runtime_instance_ids: set[str] = set()
    operator_boundary_ids: set[str] = set()
    ordinal = 0
    for mechanic_index in range(preregistration["mechanic_count"]):
        for episode_index in range(preregistration["episodes_per_mechanic"]):
            entry = _validate_run_lease_entry(
                value["entries"][ordinal],
                ordinal=ordinal,
                mechanic_index=mechanic_index,
                episode_index=episode_index,
                repository_root=repository_root,
            )
            lease_id = entry["lease_document"]["lease_id"]
            nonce = entry["lease_document"]["nonce"]
            if lease_id in lease_ids or nonce in nonces:
                raise EvaluationContractError("RunLease plan lease/nonce reused")
            boundary_path = entry["boundary_config_path"]
            if boundary_path in boundary_paths:
                raise EvaluationContractError(
                    "RunLease plan needs one durable boundary ledger per episode"
                )
            replay_domain = entry["live_context"]["nonce_replay_domain"]
            replay_root_digest = replay_domain["resolved_root_sha256"]
            replay_ledger_id = replay_domain["ledger_id"]
            deployment_id = entry["live_context"]["deployment_id"]
            runtime_instance_id = entry["live_context"][
                "runtime_instance_id"
            ]
            operator_boundary_id = entry["live_context"][
                "operator_boundary_id"
            ]
            if (
                replay_root_digest in replay_root_digests
                or replay_ledger_id in replay_ledger_ids
                or deployment_id in deployment_ids
                or runtime_instance_id in runtime_instance_ids
                or operator_boundary_id in operator_boundary_ids
            ):
                raise EvaluationContractError(
                    "RunLease plan replay/deployment identity reused"
                )
            lease_ids.add(lease_id)
            nonces.add(nonce)
            boundary_paths.add(boundary_path)
            replay_root_digests.add(replay_root_digest)
            replay_ledger_ids.add(replay_ledger_id)
            deployment_ids.add(deployment_id)
            runtime_instance_ids.add(runtime_instance_id)
            operator_boundary_ids.add(operator_boundary_id)
            entries.append(entry)
            ordinal += 1
    raw = resolved.read_bytes()
    binding = {
        "path_sha256": hashlib.sha256(str(resolved).encode("utf-8")).hexdigest(),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "entry_count": len(entries),
        "lease_id_set_sha256": canonical_digest(sorted(lease_ids)),
        "nonce_set_sha256": canonical_digest(sorted(nonces)),
        "boundary_set_sha256": canonical_digest(sorted(boundary_paths)),
        "replay_root_set_sha256": canonical_digest(
            sorted(replay_root_digests)
        ),
        "replay_ledger_set_sha256": canonical_digest(
            sorted(replay_ledger_ids)
        ),
        "deployment_set_sha256": canonical_digest(sorted(deployment_ids)),
        "runtime_instance_set_sha256": canonical_digest(
            sorted(runtime_instance_ids)
        ),
        "operator_boundary_set_sha256": canonical_digest(
            sorted(operator_boundary_ids)
        ),
    }
    return entries, binding


def verify_run_lease_plan_seed_binding(
    entries: Sequence[Mapping[str, Any]],
    *,
    seed_manifest_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the source/input binding instead of trusting signed claims."""

    try:
        expected = {
            "runner_artifact_sha256": seed_manifest_binding["candidate"][
                "source_digest"
            ],
            "config_sha256": seed_manifest_binding["evaluator"][
                "source_digest"
            ],
            "input_manifest_sha256": seed_manifest_binding["raw_sha256"],
        }
    except (KeyError, TypeError) as exc:
        raise EvaluationContractError(
            "seed manifest binding cannot authorize RunLease plan"
        ) from exc
    if not all(_SHA256.fullmatch(str(item)) for item in expected.values()):
        raise EvaluationContractError(
            "seed manifest binding digests are invalid"
        )
    for ordinal, entry in enumerate(entries):
        if type(entry) is not dict:
            raise EvaluationContractError("RunLease plan entry is not an object")
        document = entry.get("lease_document")
        context = entry.get("live_context")
        if type(document) is not dict or type(context) is not dict:
            raise EvaluationContractError(
                "RunLease plan source binding is unreadable"
            )
        for field, digest in expected.items():
            if context.get(field) != digest or document.get(field) != digest:
                raise EvaluationContractError(
                    f"RunLease plan entry {ordinal} {field} "
                    "does not match verified seed/source binding"
                )
    return {
        "passed": True,
        "entry_count": len(entries),
        **expected,
    }


_FINISHED_LEDGER_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "lease_id",
        "runner_id",
        "key_id",
        "payload_sha256",
        "nonce",
        "activated_at",
        "finished_at",
        "finish_reason",
        "lease_document",
        "live_context",
        "counters",
        "authorization_count",
        "last_authorized_at",
    }
)
_FINISHED_LEDGER_CLAIM_FIELDS = frozenset(
    {
        "schema_version",
        "key_id",
        "nonce",
        "deployment_id",
        "lease_id",
        "runner_id",
        "payload_sha256",
        "claimed_at",
    }
)


def _parse_utc_second(value: Any) -> Any:
    from datetime import datetime, timezone  # noqa: PLC0415

    if (
        type(value) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            value,
        )
        is None
    ):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def verify_finished_run_lease_ledger(
    entry: Mapping[str, Any],
    *,
    ordinal: int,
    mechanic_index: int,
    episode_index: int,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Verify immutable finished evidence without treating expiry as tampering.

    ``RunLeaseStore.status()`` correctly reports an expired live lease as no
    longer healthy.  A finished evidence verifier has a different question:
    whether the signed lease was activated, used, and finished while it was
    valid.  This routine verifies the pinned signature and exact external
    ledger records, then checks their recorded times against the signed window.
    It never turns the expired lease back into execution authority.
    """

    from packages.autonomy_envelope.operator_trust import (  # noqa: PLC0415
        SIGNATURE_FIELD,
    )
    from packages.autonomy_envelope.run_lease import (  # noqa: PLC0415
        GENERAL_INTERACTION_RUNNER_ID,
        RUN_LEASE_ACTIVE_RELATIVE_PATH,
        RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION,
        RUN_LEASE_CLAIMS_RELATIVE_PATH,
        RUN_LEASE_NONCE_CLAIM_SCHEMA_VERSION,
        RUN_LEASE_PURPOSE,
        RunLeaseBoundaryConfig,
    )

    validated = _validate_run_lease_entry(
        entry,
        ordinal=ordinal,
        mechanic_index=mechanic_index,
        episode_index=episode_index,
        repository_root=repository_root,
    )
    document = validated["lease_document"]
    context = validated["live_context"]
    boundary = RunLeaseBoundaryConfig.from_external_file(
        validated["boundary_config_path"],
        repository_root=repository_root,
    )
    signed = boundary.trust_root.verify_document(
        document,
        required_purpose=RUN_LEASE_PURPOSE,
    )
    if not signed.ok:
        raise EvaluationContractError(
            f"finished RunLease signature invalid: {signed.reason}"
        )
    signature = document[SIGNATURE_FIELD]
    if (
        signed.key_id != boundary.expected_key_id
        or signed.key_id != signature.get("key_id")
        or signed.payload_sha256 != signature.get("payload_sha256")
    ):
        raise EvaluationContractError(
            "finished RunLease signature binding mismatch"
        )

    active_dir = (
        boundary.replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH
    )
    claims_dir = (
        boundary.replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH
    )
    active_files = sorted(
        path for path in active_dir.iterdir() if path.is_file()
    )
    claim_files = sorted(
        path for path in claims_dir.iterdir() if path.is_file()
    )
    expected_active = active_dir / (
        hashlib.sha256(
            GENERAL_INTERACTION_RUNNER_ID.encode("utf-8")
        ).hexdigest()
        + ".json"
    )
    claim_id = hashlib.sha256(
        (
            f"{signed.key_id}|{document['nonce']}|"
            f"{boundary.deployment_id}"
        ).encode("utf-8")
    ).hexdigest()
    expected_claim = claims_dir / f"{claim_id}.json"
    if active_files != [expected_active] or claim_files != [expected_claim]:
        raise EvaluationContractError(
            "finished RunLease ledger file census mismatch"
        )
    state_raw = expected_active.read_bytes()
    claim_raw = expected_claim.read_bytes()
    try:
        state = json.loads(state_raw.decode("utf-8"))
        claim = json.loads(claim_raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationContractError(
            "finished RunLease ledger JSON is invalid"
        ) from exc
    if (
        frozenset(state) != _FINISHED_LEDGER_STATE_FIELDS
        or state.get("schema_version")
        != RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION
        or state.get("status") != "finished"
        or state.get("lease_id") != document["lease_id"]
        or state.get("runner_id") != GENERAL_INTERACTION_RUNNER_ID
        or state.get("key_id") != signed.key_id
        or state.get("payload_sha256") != signed.payload_sha256
        or state.get("nonce") != document["nonce"]
        or state.get("lease_document") != document
        or state.get("live_context") != context
        or type(state.get("finish_reason")) is not str
        or not state["finish_reason"]
        or type(state.get("authorization_count")) is not int
        or state["authorization_count"] < 0
        or type(state.get("counters")) is not dict
        or frozenset(state["counters"]) != frozenset(
            {
                "cycles",
                "actions",
                "external_requests",
                "external_response_bytes",
                "scratch_write_bytes",
                "child_tasks",
                "concurrent_child_tasks",
            }
        )
        or any(
            type(item) is not int or item < 0
            for item in state["counters"].values()
        )
        or state["authorization_count"] != state["counters"]["actions"]
        or state["authorization_count"] != state["counters"]["cycles"]
        or any(
            state["counters"][name] != 0
            for name in _ZERO_COUNTERS
        )
    ):
        raise EvaluationContractError(
            "finished RunLease state content mismatch"
        )
    if (
        frozenset(claim) != _FINISHED_LEDGER_CLAIM_FIELDS
        or claim.get("schema_version")
        != RUN_LEASE_NONCE_CLAIM_SCHEMA_VERSION
        or claim.get("key_id") != signed.key_id
        or claim.get("nonce") != document["nonce"]
        or claim.get("deployment_id") != boundary.deployment_id
        or claim.get("lease_id") != document["lease_id"]
        or claim.get("runner_id") != GENERAL_INTERACTION_RUNNER_ID
        or claim.get("payload_sha256") != signed.payload_sha256
    ):
        raise EvaluationContractError(
            "finished RunLease nonce claim mismatch"
        )

    issued = _parse_utc_second(document.get("issued_at"))
    expires = _parse_utc_second(document.get("expires_at"))
    activated = _parse_utc_second(state.get("activated_at"))
    finished = _parse_utc_second(state.get("finished_at"))
    claimed = _parse_utc_second(claim.get("claimed_at"))
    last_authorized = (
        _parse_utc_second(state.get("last_authorized_at"))
        if state["authorization_count"] > 0
        else None
    )
    if (
        None in {issued, expires, activated, finished, claimed}
        or not issued <= activated < expires
        or not activated <= finished < expires
        or claimed != activated
        or (
            state["authorization_count"] == 0
            and state.get("last_authorized_at") != ""
        )
        or (
            state["authorization_count"] > 0
            and (
                last_authorized is None
                or not activated <= last_authorized <= finished
            )
        )
    ):
        raise EvaluationContractError(
            "finished RunLease timestamps are outside signed window"
        )
    return {
        "state_ok": True,
        "status": "finished",
        "lease_id": state["lease_id"],
        "authorization_count": state["authorization_count"],
        "counters": copy.deepcopy(state["counters"]),
        "finish_reason": state["finish_reason"],
        "activated_at": state["activated_at"],
        "finished_at": state["finished_at"],
        "active_state_raw_sha256": hashlib.sha256(state_raw).hexdigest(),
        "nonce_claim_raw_sha256": hashlib.sha256(claim_raw).hexdigest(),
        "historical_signature_valid": True,
        "execution_authority_restored": False,
    }


def _create_external_provisioning_root(
    path: Path,
    *,
    repository_root: Path,
) -> Path:
    """Create one new external root; partial roots are never reused."""

    requested = Path(path)
    if not requested.is_absolute():
        raise EvaluationContractError(
            "RunLease provisioning root must be an absolute path"
        )
    repository = Path(repository_root).resolve(strict=True)
    parent = requested.parent.resolve(strict=True)
    resolved = parent / requested.name
    try:
        resolved.relative_to(repository)
    except ValueError:
        pass
    else:
        raise EvaluationContractError(
            "RunLease provisioning root must be outside repository"
        )
    try:
        resolved.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as exc:
        raise EvaluationContractError(
            "RunLease provisioning root already exists; use a fresh path"
        ) from exc
    return resolved.resolve(strict=True)


def _write_once_bytes(path: Path, payload: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def prepare_run_lease_plan(
    external_root: Path,
    *,
    seed_manifest_commit: str,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Provision 144 independently replay-protected leases outside the repo.

    The Ed25519 private key exists only in this process while all lease
    documents are signed.  Only its public key is persisted.  Every episode
    gets a distinct external boundary config and replay ledger.  The plan is
    exclusive-created last, so an interrupted provisioning attempt is never
    mistaken for a complete plan and must be retried at a fresh path.
    """

    import base64  # noqa: PLC0415
    import secrets  # noqa: PLC0415
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from cryptography.hazmat.primitives import serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: PLC0415
        Ed25519PrivateKey,
    )

    from packages.autonomy_envelope.operator_trust import (  # noqa: PLC0415
        ED25519_SCHEME,
        SIGNATURE_FIELD,
        canonical_payload_bytes,
        payload_sha256,
    )
    from packages.autonomy_envelope.run_lease import (  # noqa: PLC0415
        GENERAL_INTERACTION_RUNNER_ID,
        RUN_LEASE_ACTIVE_RELATIVE_PATH,
        RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
        RUN_LEASE_CLAIMS_RELATIVE_PATH,
        RUN_LEASE_LOCK_RELATIVE_PATH,
        RUN_LEASE_PURPOSE,
        RUN_LEASE_REPLAY_IDENTITY_FILENAME,
        RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
        RUN_LEASE_SCHEMA_VERSION,
        RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
        RunLeaseBoundaryConfig,
        verify_run_lease,
    )

    repository = Path(repository_root).resolve(strict=True)
    preregistration, _preregistration_digest = load_preregistration(
        repository / "data" / "eval" / "gwip_mechanism_prereg_v1.json"
    )
    del _preregistration_digest
    _seed_manifest, seed_binding = load_and_verify_seed_manifest(
        repository / SEED_MANIFEST_RELATIVE_PATH,
        seed_manifest_commit=seed_manifest_commit,
        repository_root=repository,
    )
    root = _create_external_provisioning_root(
        Path(external_root),
        repository_root=repository,
    )
    plan_path = root / PREPARED_RUN_LEASE_PLAN_FILENAME

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = f"ed25519:{hashlib.sha256(public_raw).hexdigest()[:24]}"
    public_key_path = root / "operator-public.pem"
    _write_once_bytes(
        public_key_path,
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued_at = now - timedelta(seconds=1)
    # GENERAL_INTERACTION_RUNNER_ID has a frozen 3,600 second ceiling.
    expires_at = issued_at + timedelta(seconds=3_600)
    issued_text = issued_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_text = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    entries: list[dict[str, Any]] = []
    ordinal = 0
    for mechanic_index in range(preregistration["mechanic_count"]):
        for episode_index in range(preregistration["episodes_per_mechanic"]):
            episode_root = root / f"episode-{ordinal:03d}"
            replay_root = episode_root / "replay"
            replay_root.mkdir(parents=True, exist_ok=False)
            (replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH).mkdir()
            (replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH).mkdir()

            deployment_id = f"atanor-gwip-mechanism-{ordinal:03d}"
            ledger_id = (
                "atanor:autonomy-run-ledger:"
                f"gwip-mechanism-episode-{ordinal:03d}"
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
            identity_path = (
                replay_root / RUN_LEASE_REPLAY_IDENTITY_FILENAME
            )
            write_once_json(identity_path, identity)

            boundary_config = {
                "schema_version": RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
                "operator_public_key_path": str(public_key_path),
                "expected_key_id": key_id,
                "operator_boundary_id": (
                    f"atanor-gwip-operator-boundary-{ordinal:03d}"
                ),
                "deployment_id": deployment_id,
                "replay_root": str(replay_root.resolve(strict=True)),
                "emergency_stop_path": str(
                    (episode_root / "EMERGENCY_STOP").resolve()
                ),
            }
            boundary_path = episode_root / "run-lease-trust.json"
            write_once_json(boundary_path, boundary_config)
            boundary = RunLeaseBoundaryConfig.from_external_file(
                boundary_path,
                repository_root=repository,
            )

            live_context = {
                "runner_id": GENERAL_INTERACTION_RUNNER_ID,
                "deployment_id": boundary.deployment_id,
                "runtime_instance_id": (
                    f"gwip-mechanism-runtime-{ordinal:03d}"
                ),
                "runner_artifact_sha256": seed_binding["candidate"][
                    "source_digest"
                ],
                "config_sha256": seed_binding["evaluator"]["source_digest"],
                "input_manifest_sha256": seed_binding["raw_sha256"],
                "capability_manifest": {
                    "schema_version": RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
                    "action_classes": ["interaction.step"],
                    "filesystem_policy_sha256": sha256_text(
                        "atanor.gwip.filesystem.none.v1"
                    ),
                    "network_policy_sha256": sha256_text(
                        "atanor.gwip.network.none.v1"
                    ),
                    "child_task_policy_sha256": sha256_text(
                        "atanor.gwip.child-task.none.v1"
                    ),
                },
                "limits": {
                    "max_runtime_sec": 3_600,
                    "max_cycles": preregistration["step_budget"],
                    "max_actions": preregistration["step_budget"],
                    **_ZERO_RESOURCE_LIMITS,
                },
                "scratch_boundary": {
                    "boundary_id": f"gwip-no-scratch-{ordinal:03d}",
                    "resolved_root_sha256": sha256_text(
                        f"atanor.gwip.no-scratch.root.v1:{ordinal}"
                    ),
                    "identity_manifest_sha256": sha256_text(
                        f"atanor.gwip.no-scratch.identity.v1:{ordinal}"
                    ),
                },
                "operator_boundary_id": boundary.operator_boundary_id,
                "operator_boundary_config_sha256": (
                    boundary.operator_boundary_config_sha256
                ),
                "nonce_replay_domain": copy.deepcopy(
                    boundary.replay_domain
                ),
            }
            lease_id = (
                f"gwip-mechanism-lease-{ordinal:03d}-"
                f"{secrets.token_hex(8)}"
            )
            nonce = (
                f"gwip-mechanism-nonce-{ordinal:03d}-"
                f"{secrets.token_hex(16)}"
            )
            document = {
                "schema_version": RUN_LEASE_SCHEMA_VERSION,
                "purpose": RUN_LEASE_PURPOSE,
                "lease_id": lease_id,
                **copy.deepcopy(live_context),
                "issued_at": issued_text,
                "expires_at": expires_text,
                "nonce": nonce,
                SIGNATURE_FIELD: {
                    "scheme": ED25519_SCHEME,
                    "key_id": key_id,
                    "payload_sha256": "",
                    "signature": "",
                },
            }
            digest = payload_sha256(document)
            document[SIGNATURE_FIELD] = {
                "scheme": ED25519_SCHEME,
                "key_id": key_id,
                "payload_sha256": digest,
                "signature": base64.b64encode(
                    private_key.sign(canonical_payload_bytes(document))
                ).decode("ascii"),
            }
            verified = verify_run_lease(
                document,
                trust_root=boundary.trust_root,
                live_context=live_context,
            )
            if (
                verified.ok is not True
                or verified.reason != "run_lease_valid"
                or verified.lease_id != lease_id
            ):
                raise EvaluationContractError(
                    f"provisioned RunLease failed verification: {verified.reason}"
                )
            entries.append(
                {
                    "ordinal": ordinal,
                    "mechanic_index": mechanic_index,
                    "episode_index": episode_index,
                    "boundary_config_path": str(
                        boundary_path.resolve(strict=True)
                    ),
                    "lease_document": document,
                    "live_context": live_context,
                }
            )
            ordinal += 1

    plan = {
        "schema_version": RUN_LEASE_PLAN_SCHEMA,
        "candidate_episode_count": preregistration[
            "candidate_episode_count"
        ],
        "entries": entries,
    }
    write_once_json(plan_path, plan)
    loaded_entries, binding = load_run_lease_plan(
        plan_path,
        preregistration=preregistration,
        repository_root=repository,
    )
    source_binding_check = verify_run_lease_plan_seed_binding(
        loaded_entries,
        seed_manifest_binding=seed_binding,
    )
    if len(loaded_entries) != preregistration["candidate_episode_count"]:
        raise EvaluationContractError("provisioned RunLease plan census mismatch")
    # The signing capability deliberately dies with this stack frame; no
    # private-key bytes are serialized anywhere under the external root.
    del private_key
    return {
        "schema_version": "atanor.gwip-run-lease-provisioning-receipt.v1",
        "plan_path": str(plan_path.resolve(strict=True)),
        "plan_raw_sha256": binding["raw_sha256"],
        "entry_count": len(loaded_entries),
        "boundary_count": len(
            {item["boundary_config_path"] for item in loaded_entries}
        ),
        "operator_public_key_path": str(public_key_path.resolve(strict=True)),
        "operator_key_id": key_id,
        "private_key_persisted": False,
        "issued_at": issued_text,
        "expires_at": expires_text,
        "usable_window_seconds_at_completion": max(
            0,
            int(
                (
                    expires_at
                    - datetime.now(timezone.utc)
                ).total_seconds()
            ),
        ),
        "run_must_complete_before_expiry": True,
        "authority_scope": (
            "evaluator_parent_vs_candidate_not_independent_operator_channel"
        ),
        "seed_manifest_commit": seed_manifest_commit,
        "seed_manifest_raw_sha256": seed_binding["raw_sha256"],
        "candidate_source_digest": source_binding_check[
            "runner_artifact_sha256"
        ],
        "evaluator_source_digest": source_binding_check["config_sha256"],
    }


def audit_environment_call_order(
    call_log: Sequence[Mapping[str, Any]],
    *,
    step_budget: int,
) -> dict[str, Any]:
    findings: list[str] = []
    operations = [
        item.get("operation") if isinstance(item, Mapping) else None
        for item in call_log
    ]
    if not operations or operations[0] != "reset":
        findings.append("first environment operation is not reset")
    if operations.count("reset") != 1:
        findings.append("environment reset count is not exactly one")
    if operations.count("stop") != 1:
        findings.append("environment stop count is not exactly one")
    if operations and operations[-1] != "stop":
        findings.append("environment stop is not the final operation")
    state = "reset"
    step_count = 0
    for index, operation in enumerate(operations[1:], start=1):
        if state == "reset":
            expected = {"observe"}
        elif state == "observed":
            # Operator stop is checked after the actual observation and before
            # action enumeration.  That path is a valid fail-closed terminal.
            expected = {"valid_actions", "stop"}
        elif state == "actions":
            expected = {"step", "stop"}
        elif state == "stepped":
            expected = {"observe", "stop"}
        else:
            expected = set()
        if operation not in expected:
            findings.append(
                f"operation {operation!r} at index {index} invalid after {state}"
            )
            state = "invalid"
            continue
        if operation == "observe":
            state = "observed"
        elif operation == "valid_actions":
            state = "actions"
        elif operation == "step":
            state = "stepped"
            step_count += 1
        elif operation == "stop":
            state = "stopped"
    if step_count > step_budget:
        findings.append("environment executed more than the frozen step budget")
    return {
        "schema_version": "atanor.gwip-call-order-audit.v1",
        "passed": not findings,
        "step_count": step_count,
        "stop_count": operations.count("stop"),
        "findings": findings,
    }


def verify_step_budget_pre_mutation_denial(
    mechanic: HiddenMechanic,
    *,
    episode_index: int,
    environment_seed: int,
    step_budget: int,
) -> bool:
    """Independently force step N+1 and require denial before state/log mutation."""

    environment = OpaqueFSTEnvironment(
        mechanic,
        episode_index=episode_index,
        step_budget=step_budget,
    )
    environment.reset(environment_seed)
    action = environment.valid_actions()[0]
    for _ in range(step_budget):
        environment.step(action)
    state_before = environment.state_ref
    log_before = copy.deepcopy(environment.call_log)
    try:
        environment.step(action)
    except StepBudgetExhausted:
        pass
    else:
        return False
    return (
        environment.state_ref == state_before
        and environment.call_log == log_before
    )


@dataclass(frozen=True)
class TraceStep:
    step_index: int
    observation: Mapping[str, Any]
    valid_actions: tuple[str, ...]
    selected_action: str
    authority_reason: str
    authority_binding: str
    post_observation: Mapping[str, Any]
    learned_edge_ref: str
    world_snapshot_ref: str
    goal_ir_ref: str
    proposal_ref: str
    decision_receipt_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "observation": copy.deepcopy(dict(self.observation)),
            "valid_actions": list(self.valid_actions),
            "valid_actions_digest": canonical_digest(list(self.valid_actions)),
            "selected_action": self.selected_action,
            "authority_reason": self.authority_reason,
            "authority_binding": self.authority_binding,
            "post_observation": copy.deepcopy(dict(self.post_observation)),
            "learned_edge_ref": self.learned_edge_ref,
            "world_snapshot_ref": self.world_snapshot_ref,
            "goal_ir_ref": self.goal_ir_ref,
            "proposal_ref": self.proposal_ref,
            "decision_receipt_ref": self.decision_receipt_ref,
        }


@dataclass(frozen=True)
class EpisodeTrace:
    policy: str
    evaluator_mechanic_index: int
    episode_index: int
    goal_ref: str
    initial_observation: Mapping[str, Any]
    steps: tuple[TraceStep, ...]
    stop_reason: str
    success: bool
    optimal_steps: int
    semantic_trace_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA,
            "policy": self.policy,
            "evaluator_mechanic_index": self.evaluator_mechanic_index,
            "episode_index": self.episode_index,
            "goal_ref": self.goal_ref,
            "initial_observation": copy.deepcopy(dict(self.initial_observation)),
            "steps": [item.to_dict() for item in self.steps],
            "stop_reason": self.stop_reason,
            "success": self.success,
            "optimal_steps": self.optimal_steps,
            "executed_steps": len(self.steps),
            "swae": episode_swae(
                success=self.success,
                optimal_steps=self.optimal_steps,
                executed_steps=len(self.steps),
            ),
            "semantic_trace_digest": self.semantic_trace_digest,
        }


def render_episode(trace: EpisodeTrace) -> str:
    """Render one complete reset-to-stop trace without exposing a private table."""

    lines = [
        (
            f"Episode policy={trace.policy} "
            f"mechanic={trace.evaluator_mechanic_index} "
            f"episode={trace.episode_index}"
        ),
        (
            "RESET "
            f"state={trace.initial_observation.get('state_ref')} "
            f"goal={trace.goal_ref}"
        ),
    ]
    for step in trace.steps:
        lines.append(
            f"STEP {step.step_index + 1:02d} "
            f"OBSERVE state={step.observation.get('state_ref')} | "
            f"VALID_ACTIONS [{', '.join(step.valid_actions)}] | "
            f"DECIDE {step.selected_action} | "
            f"AUTHORIZE {step.authority_reason} "
            f"binding={step.authority_binding[:12]}... | "
            f"STEP -> state={step.post_observation.get('state_ref')} "
            f"terminal={step.post_observation.get('terminal')} | "
            f"LINEAGE world={step.world_snapshot_ref} "
            f"goal={step.goal_ir_ref} proposal={step.proposal_ref} "
            f"decision={step.decision_receipt_ref} edge={step.learned_edge_ref}"
        )
    lines.append(
        f"STOP reason={trace.stop_reason} success={trace.success} "
        f"steps={len(trace.steps)} optimal={trace.optimal_steps} "
        f"semantic_trace={trace.semantic_trace_digest}"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class CandidatePublicTypes:
    loop_type: type
    policy_type: type


def resolve_candidate_public_types(
    *,
    importer: Callable[[str], ModuleType] = importlib.import_module,
) -> CandidatePublicTypes:
    """The only evaluator location coupled to candidate public symbol names."""

    loop_module = importer("packages.fusion_loop.interactive")
    organ_module = importer("packages.fusion_loop.interactive_organs")
    loop_type = getattr(loop_module, "GenericWorldInteractionLoop", None)
    policy_type = getattr(organ_module, "AtanorInteractivePolicy", None)
    if not isinstance(loop_type, type) or not isinstance(policy_type, type):
        raise EvaluationContractError("candidate public interaction types are missing")
    return CandidatePublicTypes(loop_type=loop_type, policy_type=policy_type)


_WORKER_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "goal_ref",
        "environment_seed",
        "policy_seed",
        "step_budget",
        "session_id",
        "policy_memory",
    }
)
_WORKER_RESPONSE_FIELDS = frozenset(
    {
        "schema_version",
        "type",
        "session",
        "call_id",
        "ok",
        "result",
        "error",
    }
)
_PRIMARY_RESULT_FIELDS = frozenset(
    {
        "trace",
        "operational_authority",
        "memory_after",
    }
)
_WORKER_MAX_LINE_BYTES = 16 * 1024 * 1024
_WORKER_PROTOCOL_OUT: Any = None


def _strict_json_line(raw: bytes, *, label: str) -> dict[str, Any]:
    if not raw or len(raw) > _WORKER_MAX_LINE_BYTES or not raw.endswith(b"\n"):
        raise EvaluationContractError(f"{label} line is missing or too large")

    def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise EvaluationContractError(f"{label} duplicate JSON key: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EvaluationContractError(f"{label} non-finite number: {token}")
            ),
        )
    except EvaluationContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvaluationContractError(f"{label} is not strict JSON") from exc
    if type(value) is not dict:
        raise EvaluationContractError(f"{label} root must be an exact object")
    return value


def _worker_read_line(*, label: str) -> dict[str, Any]:
    return _strict_json_line(
        sys.stdin.buffer.readline(_WORKER_MAX_LINE_BYTES + 1),
        label=label,
    )


def _worker_emit(value: Mapping[str, Any]) -> None:
    if _WORKER_PROTOCOL_OUT is None:
        raise EvaluationContractError("worker protocol output is not initialized")
    payload = canonical_json_bytes(dict(value)).decode("utf-8")
    _WORKER_PROTOCOL_OUT.write(payload + "\n")
    _WORKER_PROTOCOL_OUT.flush()


def _validate_worker_request(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != _WORKER_REQUEST_FIELDS:
        raise EvaluationContractError("candidate worker request fields mismatch")
    if value.get("schema_version") != WORKER_REQUEST_SCHEMA:
        raise EvaluationContractError("candidate worker request schema mismatch")
    for field in ("goal_ref", "session_id"):
        item = value.get(field)
        if type(item) is not str or not item.strip() or len(item) > 1024:
            raise EvaluationContractError(f"candidate worker {field} invalid")
    if type(value.get("environment_seed")) is not int:
        raise EvaluationContractError("candidate worker environment seed invalid")
    if type(value.get("policy_seed")) is not int:
        raise EvaluationContractError("candidate worker policy seed invalid")
    if type(value.get("step_budget")) is not int or not 1 <= value["step_budget"] <= 20:
        raise EvaluationContractError("candidate worker step budget invalid")
    memory = value.get("policy_memory")
    if memory is not None and type(memory) is not dict:
        raise EvaluationContractError("candidate worker policy memory invalid")
    return copy.deepcopy(dict(value))


def _worker_configure_source_root() -> tuple[Path, Path, Path]:
    candidate_raw = os.environ.pop("ATANOR_GWIP_CANDIDATE_ROOT", "")
    runtime_raw = os.environ.pop("ATANOR_GWIP_RUNTIME_ROOT", "")
    if not candidate_raw or not runtime_raw:
        raise EvaluationContractError("candidate worker roots are required")
    candidate_root = Path(candidate_raw).resolve(strict=True)
    runtime_root = Path(runtime_raw).resolve(strict=True)
    worker_repo = Path(__file__).resolve(strict=True).parents[1]
    if not (candidate_root / "packages").is_dir() or not runtime_root.is_dir():
        raise EvaluationContractError("candidate worker roots are invalid")
    retained: list[str] = []
    for raw in sys.path:
        try:
            Path(raw or os.curdir).resolve().relative_to(worker_repo)
        except (OSError, ValueError):
            retained.append(raw)
    sys.path[:] = [str(candidate_root), *retained]
    os.chdir(runtime_root)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return candidate_root, runtime_root, worker_repo


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class _WorkerIsolationGuard:
    """Candidate-process guard; reported as a guard, not an OS sandbox."""

    def __init__(
        self,
        *,
        candidate_root: Path,
        runtime_root: Path,
        worker_repo: Path,
    ) -> None:
        self.candidate_root = candidate_root
        self.runtime_root = runtime_root
        self.worker_repo = worker_repo
        self.blocked_network = 0
        self.blocked_child = 0
        self.blocked_write = 0
        self.blocked_workspace_read = 0
        self._installed = False
        self._network_probe_socket: Any = None
        import_roots: list[Path] = []
        for raw in sys.path:
            try:
                path = Path(raw or os.curdir).resolve(strict=True)
            except OSError:
                continue
            if path.is_dir() and not _path_within(path, worker_repo):
                import_roots.append(path)
        self._read_roots = tuple(
            dict.fromkeys(
                Path(item).resolve()
                for item in (
                    candidate_root,
                    runtime_root,
                    Path(sys.base_prefix),
                    Path(sys.prefix),
                    Path(sys.executable).parent,
                    *import_roots,
                )
            )
        )

    @staticmethod
    def _path(value: Any) -> Path | None:
        if isinstance(value, int):
            return None
        try:
            return Path(os.path.abspath(os.fsdecode(value)))
        except (OSError, TypeError, ValueError):
            return None

    def _read_allowed(self, path: Path) -> bool:
        return any(_path_within(path, root) for root in self._read_roots)

    @staticmethod
    def _open_is_write(mode: Any, flags: Any) -> bool:
        if isinstance(mode, str) and any(item in mode for item in ("w", "a", "x", "+")):
            return True
        if isinstance(flags, int):
            mask = (
                os.O_WRONLY
                | os.O_RDWR
                | os.O_APPEND
                | os.O_CREAT
                | os.O_TRUNC
            )
            return bool(flags & mask)
        return False

    def _audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args:
            path = self._path(args[0])
            is_write = self._open_is_write(
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
            )
            if is_write:
                self.blocked_write += 1
                raise PermissionError("GWIP candidate writes are disabled")
            if path is not None and not self._read_allowed(path):
                self.blocked_workspace_read += 1
                raise PermissionError(
                    f"GWIP external filesystem reads are disabled: {path}"
                )
        elif event in {"os.listdir", "os.scandir"} and args:
            path = self._path(args[0])
            if path is not None and not self._read_allowed(path):
                self.blocked_workspace_read += 1
                raise PermissionError(
                    f"GWIP external filesystem enumeration is disabled: {path}"
                )
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chdir",
            "os.chmod",
            "os.truncate",
            "os.utime",
            "os.rename",
            "os.replace",
        }:
            self.blocked_write += 1
            raise PermissionError("GWIP candidate filesystem mutation is disabled")
        elif event.startswith("subprocess.") or event in {
            "os.system",
            "os.posix_spawn",
            "os.spawn",
            "ctypes.dlopen",
            "ctypes.dlsym",
        }:
            self.blocked_child += 1
            raise PermissionError("GWIP child processes are disabled")
        elif event in {
            "socket.__new__",
            "socket.bind",
            "socket.connect",
            "socket.getaddrinfo",
            "socket.sendto",
        }:
            self.blocked_network += 1
            raise PermissionError("GWIP network access is disabled")

    def install(self) -> None:
        if self._installed:
            raise EvaluationContractError("candidate worker guard already installed")
        self._installed = True

        def network_blocked(*_args: Any, **_kwargs: Any) -> Any:
            self.blocked_network += 1
            raise PermissionError("GWIP network access is disabled")

        def child_blocked(*_args: Any, **_kwargs: Any) -> Any:
            self.blocked_child += 1
            raise PermissionError("GWIP child processes are disabled")

        import _socket  # noqa: PLC0415
        import ctypes  # noqa: PLC0415
        import socket  # noqa: PLC0415
        try:
            import _ctypes  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError:  # pragma: no cover - platform dependent
            _ctypes = None
        try:
            import _winapi  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError:  # pragma: no cover - non-Windows
            _winapi = None

        original_socket_type = socket.socket
        self._network_probe_socket = original_socket_type(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        sys.addaudithook(self._audit)

        for name in (
            "accept",
            "bind",
            "connect",
            "connect_ex",
            "listen",
            "recv",
            "recv_into",
            "recvfrom",
            "recvfrom_into",
            "recvmsg",
            "recvmsg_into",
            "send",
            "sendall",
            "sendmsg",
            "sendto",
        ):
            if hasattr(original_socket_type, name):
                setattr(original_socket_type, name, network_blocked)
        socket.create_connection = network_blocked  # type: ignore[assignment]
        if hasattr(socket, "create_server"):
            socket.create_server = network_blocked  # type: ignore[assignment]
        if hasattr(socket, "socketpair"):
            socket.socketpair = network_blocked  # type: ignore[assignment]
        for name in (
            "getaddrinfo",
            "gethostbyaddr",
            "gethostbyname",
            "gethostbyname_ex",
            "getnameinfo",
        ):
            if hasattr(socket, name):
                setattr(socket, name, network_blocked)
        if _winapi is not None and hasattr(_winapi, "CreateProcess"):
            _winapi.CreateProcess = child_blocked  # type: ignore[assignment]
        if _winapi is not None:
            for name in (
                "CreateFile",
                "DeleteFile",
                "MoveFileEx",
                "ReadFile",
                "WriteFile",
            ):
                if hasattr(_winapi, name):
                    setattr(_winapi, name, child_blocked)
        subprocess.Popen = child_blocked  # type: ignore[assignment]
        os.system = child_blocked  # type: ignore[assignment]
        if hasattr(os, "startfile"):
            os.startfile = child_blocked  # type: ignore[assignment]
        for name in tuple(dir(os)):
            if name.startswith("spawn") and callable(getattr(os, name)):
                setattr(os, name, child_blocked)

    def probes(self) -> dict[str, bool]:
        import ctypes  # noqa: PLC0415
        import socket  # noqa: PLC0415

        results = {
            "external_network_blocked": False,
            "udp_sendto_blocked": False,
            "child_process_blocked": False,
            "native_child_process_blocked": False,
            "native_library_loading_blocked": False,
            "native_file_access_blocked": False,
            "nonledger_write_blocked": False,
            "evaluator_workspace_read_blocked": False,
            "external_filesystem_enumeration_blocked": False,
        }
        try:
            socket.create_connection(("198.51.100.1", 9), timeout=0.001)
        except PermissionError:
            results["external_network_blocked"] = True
        try:
            assert self._network_probe_socket is not None
            self._network_probe_socket.sendto(b"x", ("127.0.0.1", 9))
        except PermissionError:
            results["udp_sendto_blocked"] = True
        finally:
            if self._network_probe_socket is not None:
                self._network_probe_socket.close()
                self._network_probe_socket = None
        try:
            subprocess.Popen([sys.executable, "-c", "pass"])
        except PermissionError:
            results["child_process_blocked"] = True
        if os.name == "nt":
            try:
                import _winapi  # type: ignore[import-not-found]  # noqa: PLC0415

                _winapi.CreateProcess()
            except PermissionError:
                results["native_child_process_blocked"] = True
        else:
            results["native_child_process_blocked"] = True
        try:
            ctypes.CDLL("atanor-gwip-forbidden-native-library")
        except PermissionError:
            results["native_library_loading_blocked"] = True
        if os.name == "nt":
            try:
                import _winapi  # type: ignore[import-not-found]  # noqa: PLC0415

                _winapi.CreateFile()
            except PermissionError:
                results["native_file_access_blocked"] = True
        else:
            results["native_file_access_blocked"] = True
        try:
            (self.runtime_root / "forbidden-write-probe").write_text(
                "blocked",
                encoding="utf-8",
            )
        except PermissionError:
            results["nonledger_write_blocked"] = True
        try:
            (
                self.worker_repo
                / "data"
                / "eval"
                / "gwip_mechanism_prereg_v1.json"
            ).read_bytes()
        except PermissionError:
            results["evaluator_workspace_read_blocked"] = True
        try:
            list(self.worker_repo.parent.iterdir())
        except PermissionError:
            results["external_filesystem_enumeration_blocked"] = True
        return results

    def receipt(self, probes: Mapping[str, bool]) -> dict[str, Any]:
        return {
            "schema_version": "atanor.gwip-worker-guard.v1",
            "kind": "python_audit_guard_not_os_sandbox",
            "probes": dict(probes),
            "blocked_event_counts": {
                "network": self.blocked_network,
                "child": self.blocked_child,
                "write": self.blocked_write,
                "workspace_read": self.blocked_workspace_read,
            },
            "passed": all(probes.values()),
        }


class _WorkerRpcEnvironment:
    __slots__ = ("_session", "_call_id")

    def __init__(self, session: str) -> None:
        self._session = session
        self._call_id = 0

    def _call(self, operation: str, payload: Mapping[str, Any]) -> Any:
        call_id = self._call_id
        self._call_id += 1
        _worker_emit(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "environment_request",
                "session": self._session,
                "call_id": call_id,
                "operation": operation,
                "payload": copy.deepcopy(dict(payload)),
            }
        )
        response = _worker_read_line(label="candidate worker environment response")
        if (
            frozenset(response) != _WORKER_RESPONSE_FIELDS
            or response.get("schema_version") != WORKER_RPC_SCHEMA
            or response.get("type") != "environment_response"
            or response.get("session") != self._session
            or response.get("call_id") != call_id
            or response.get("ok") is not True
        ):
            raise EvaluationContractError("candidate worker environment response invalid")
        return copy.deepcopy(response.get("result"))

    def reset(self, seed: int) -> Any:
        return self._call("reset", {"seed": seed})

    def observe(self) -> Any:
        return self._call("observe", {})

    def valid_actions(self) -> Any:
        return self._call("valid_actions", {})

    def step(self, action_id: str) -> Any:
        return self._call("step", {"action_id": action_id})

    def stop(self, reason: str) -> Any:
        return self._call("stop", {"reason": reason})


def _worker_rpc(
    *,
    message_type: str,
    operation: str,
    call_id: int,
    payload: Mapping[str, Any],
) -> Any:
    _worker_emit(
        {
            "schema_version": WORKER_RPC_SCHEMA,
            "type": message_type,
            "session": "authority",
            "call_id": call_id,
            "operation": operation,
            "payload": copy.deepcopy(dict(payload)),
        }
    )
    response = _worker_read_line(label="candidate worker authority response")
    if (
        frozenset(response) != _WORKER_RESPONSE_FIELDS
        or response.get("schema_version") != WORKER_RPC_SCHEMA
        or response.get("type") != "authority_response"
        or response.get("session") != "authority"
        or response.get("call_id") != call_id
        or response.get("ok") is not True
    ):
        raise EvaluationContractError("candidate worker authority response invalid")
    return copy.deepcopy(response.get("result"))


def _worker_module_closure(candidate_root: Path, worker_repo: Path) -> dict[str, Any]:
    source: list[dict[str, str]] = []
    outside: list[dict[str, str]] = []
    for name, module in sorted(sys.modules.items()):
        raw = getattr(module, "__file__", None)
        if not raw:
            continue
        try:
            path = Path(str(raw)).resolve(strict=True)
        except OSError:
            continue
        repo_namespace = name == "packages" or name.startswith("packages.")
        if repo_namespace and _path_within(path, candidate_root):
            source.append(
                {"module": name, "path": path.relative_to(candidate_root).as_posix()}
            )
        elif repo_namespace:
            outside.append({"module": name, "path": str(path)})
    return {
        "source_modules": source,
        "source_modules_sha256": canonical_digest(source),
        "outside_candidate_root_modules": outside,
        "passed": bool(source) and not outside,
    }


def _candidate_worker_run(request: Mapping[str, Any]) -> dict[str, Any]:
    candidate_root, runtime_root, worker_repo = _worker_configure_source_root()
    guard = _WorkerIsolationGuard(
        candidate_root=candidate_root,
        runtime_root=runtime_root,
        worker_repo=worker_repo,
    )
    guard.install()
    # Candidate modules must not be able to recover this evaluator program via
    # ``import __main__``.  The executing harness keeps its private globals,
    # while the import registry exposes only an inert facade before any
    # candidate package is imported.
    sys.modules["__main__"] = ModuleType("__main__")
    probes = {
        **guard.probes(),
        "evaluator_main_hidden": not any(
            hasattr(sys.modules["__main__"], name)
            for name in (
                "generate_hidden_mechanics",
                "OpaqueFSTEnvironment",
                "REPO",
                "run_final_once",
            )
        ),
    }

    from packages.cognitive_core import GoalIR, GoalOrigin  # noqa: PLC0415
    from packages.fusion_loop.interactive import (  # noqa: PLC0415
        AuthorizationWitness,
        GenericWorldInteractionLoop,
        reexecute_interactive_trace,
    )
    from packages.fusion_loop.interactive_organs import (  # noqa: PLC0415
        AtanorInteractivePolicy,
    )

    class ParentAuthority:
        def __init__(self) -> None:
            self._call_id = 0

        def authorize(self, action_id: str, step_index: int) -> Any:
            raw = _worker_rpc(
                message_type="authority_request",
                operation="authorize",
                call_id=self._call_id,
                payload={"action_id": action_id, "step_index": step_index},
            )
            self._call_id += 1
            if type(raw) is not dict:
                raise EvaluationContractError("parent authority witness is not an object")
            return AuthorizationWitness(
                action_id=raw.get("action_id"),
                step_index=raw.get("step_index"),
                granted=raw.get("granted"),
                reason=raw.get("reason"),
                authority_kind=raw.get("authority_kind"),
                operational_evidence=raw.get("operational_evidence", {}),
            )

        def finish(self, reason: str) -> Any:
            raw = _worker_rpc(
                message_type="authority_request",
                operation="finish",
                call_id=self._call_id,
                payload={"reason": reason},
            )
            self._call_id += 1
            return raw

    memory = request["policy_memory"]
    policy = (
        AtanorInteractivePolicy()
        if memory is None
        else AtanorInteractivePolicy.from_memory(memory)
    )
    goal = GoalIR(
        statement="Reach the opaque target reference.",
        origin=GoalOrigin.EXPLICIT_USER,
        metadata={"target_ref": request["goal_ref"]},
    )
    trace = GenericWorldInteractionLoop(
        authority=ParentAuthority(),
        policy=policy,
        require_run_lease=False,
    ).run(
        _WorkerRpcEnvironment("primary"),
        goal,
        environment_seed=request["environment_seed"],
        policy_seed=request["policy_seed"],
        step_budget=request["step_budget"],
        session_id=request["session_id"],
    )
    primary_result = {
        "trace": trace.to_dict(),
        "operational_authority": [
            step.authorization.to_dict() for step in trace.steps
        ],
        "memory_after": trace.memory_after.to_dict(),
    }
    _worker_emit(
        {
            "schema_version": WORKER_RPC_SCHEMA,
            "type": "primary_result",
            "session": "primary_result",
            "call_id": 0,
            "result": primary_result,
        }
    )
    primary_ack = _worker_read_line(label="candidate worker primary-result ack")
    if (
        frozenset(primary_ack) != _WORKER_RESPONSE_FIELDS
        or primary_ack.get("schema_version") != WORKER_RPC_SCHEMA
        or primary_ack.get("type") != "primary_result_ack"
        or primary_ack.get("session") != "primary_result"
        or primary_ack.get("call_id") != 0
        or primary_ack.get("ok") is not True
        or primary_ack.get("result") != {"sealed": True}
    ):
        raise EvaluationContractError("candidate primary result was not sealed")
    structural = reexecute_interactive_trace(
        lambda: _WorkerRpcEnvironment("replay"),
        trace,
        fixture_authority_verifier=lambda witness: witness.granted,
    )

    class DeterminismAuthority:
        def authorize(self, action_id: str, step_index: int) -> Any:
            return AuthorizationWitness(
                action_id=action_id,
                step_index=step_index,
                granted=True,
                reason="determinism_fixture_granted",
                authority_kind="determinism_fixture",
                operational_evidence={"fixture": "semantic_duplicate"},
            )

        def finish(self, reason: str) -> Any:
            return {"finished": True, "reason": reason}

    def duplicate(session: str) -> Any:
        duplicate_policy = (
            AtanorInteractivePolicy()
            if memory is None
            else AtanorInteractivePolicy.from_memory(memory)
        )
        return GenericWorldInteractionLoop(
            authority=DeterminismAuthority(),
            policy=duplicate_policy,
            require_run_lease=False,
        ).run(
            _WorkerRpcEnvironment(session),
            goal,
            environment_seed=request["environment_seed"],
            policy_seed=request["policy_seed"],
            step_budget=request["step_budget"],
            session_id=f"{request['session_id']}:determinism",
        )

    duplicate_a = duplicate("determinism_a")
    duplicate_b = duplicate("determinism_b")
    closure = _worker_module_closure(candidate_root, worker_repo)
    return {
        "schema_version": WORKER_RESULT_SCHEMA,
        **primary_result,
        "structural_verification": structural.to_dict(),
        "determinism": {
            "trace_a_digest": duplicate_a.semantic_trace_digest,
            "trace_b_digest": duplicate_b.semantic_trace_digest,
            "memory_after_a_sha256": canonical_digest(
                duplicate_a.memory_after.to_dict()
            ),
            "memory_after_b_sha256": canonical_digest(
                duplicate_b.memory_after.to_dict()
            ),
            "passed": (
                duplicate_a.semantic_trace_digest
                == duplicate_b.semantic_trace_digest
                and duplicate_a.memory_after == duplicate_b.memory_after
            ),
        },
        "module_closure": closure,
        "isolation": guard.receipt(probes),
        "aggregate_metrics": None,
        "verdict": None,
    }


def _candidate_worker_main() -> int:
    global _WORKER_PROTOCOL_OUT
    _WORKER_PROTOCOL_OUT = sys.stdout
    try:
        request = _validate_worker_request(
            _worker_read_line(label="candidate worker request")
        )
        with contextlib.redirect_stdout(sys.stderr):
            result = _candidate_worker_run(request)
        _worker_emit(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "worker_result",
                "result": result,
            }
        )
        return 0
    except Exception as exc:
        _worker_emit(
            {
                "schema_version": WORKER_RPC_SCHEMA,
                "type": "worker_failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        return 2


_WORKER_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "trace",
        "operational_authority",
        "memory_after",
        "structural_verification",
        "determinism",
        "module_closure",
        "isolation",
        "aggregate_metrics",
        "verdict",
    }
)
_FIXED_AUTHORIZATION_COSTS = {
    "cycles": 1,
    "actions": 1,
    "external_requests": 0,
    "external_response_bytes": 0,
    "scratch_write_bytes": 0,
    "child_tasks": 0,
    "concurrent_child_tasks": 0,
}


def _worker_environment_response(
    *,
    session: str,
    call_id: int,
    result: Any,
) -> dict[str, Any]:
    return {
        "schema_version": WORKER_RPC_SCHEMA,
        "type": "environment_response",
        "session": session,
        "call_id": call_id,
        "ok": True,
        "result": copy.deepcopy(result),
        "error": None,
    }


def _worker_authority_response(
    *,
    call_id: int,
    result: Any,
) -> dict[str, Any]:
    return {
        "schema_version": WORKER_RPC_SCHEMA,
        "type": "authority_response",
        "session": "authority",
        "call_id": call_id,
        "ok": True,
        "result": copy.deepcopy(result),
        "error": None,
    }


def _authorization_witness_from_parent_response(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the exact full witness the worker must preserve.

    The parent records its own RPC result before sending it.  This evaluator
    implementation derives the candidate contract ID independently from those
    bytes and later compares the result with both the worker's operational
    list and the full trace lineage.
    """

    required = frozenset(
        {
            "action_id",
            "step_index",
            "granted",
            "reason",
            "authority_kind",
            "operational_evidence",
        }
    )
    if type(value) is not dict or frozenset(value) != required:
        raise EvaluationContractError("parent authorization response fields mismatch")
    identity_payload = {
        "action_id": value["action_id"],
        "authority_kind": value["authority_kind"],
        "granted": value["granted"],
        "operational_evidence": copy.deepcopy(value["operational_evidence"]),
        "reason": value["reason"],
        "step_index": value["step_index"],
    }
    return {
        "action_id": value["action_id"],
        "authority_kind": value["authority_kind"],
        "bearer_capability": False,
        "granted": value["granted"],
        "operational_evidence": copy.deepcopy(value["operational_evidence"]),
        "reason": value["reason"],
        "step_index": value["step_index"],
        "witness_id": (
            "authorization_witness_"
            f"{canonical_digest(identity_payload)[:32]}"
        ),
    }


def _write_worker_message(stream: Any, value: Mapping[str, Any]) -> None:
    stream.write(canonical_json_bytes(dict(value)) + b"\n")
    stream.flush()


def _candidate_trace_scoring_projection(
    call_log: Sequence[Mapping[str, Any]],
    *,
    policy: str,
    mechanic_index: int,
    episode_index: int,
    random_seed: int | None,
) -> dict[str, Any]:
    initial: Mapping[str, Any] | None = None
    current_observation: Mapping[str, Any] | None = None
    current_actions: Sequence[str] | None = None
    steps: list[dict[str, Any]] = []
    stop_reason: str | None = None
    success: bool | None = None
    for entry in call_log:
        operation = entry.get("operation")
        if operation == "observe":
            current_observation = copy.deepcopy(entry.get("observation"))
            if initial is None:
                initial = current_observation
        elif operation == "valid_actions":
            current_actions = tuple(entry.get("actions") or ())
        elif operation == "step":
            if current_observation is None or current_actions is None:
                raise EvaluationContractError("step lacks evaluator observation/action witnesses")
            result = entry.get("result")
            if type(result) is not dict:
                raise EvaluationContractError("step result witness missing")
            steps.append(
                {
                    "step_index": len(steps),
                    "observation": copy.deepcopy(dict(current_observation)),
                    "valid_actions": list(current_actions),
                    "selected_action": entry.get("action_id"),
                    "result": copy.deepcopy(result),
                }
            )
            current_observation = None
            current_actions = None
        elif operation == "stop":
            result = entry.get("result")
            if type(result) is not dict:
                raise EvaluationContractError("stop result witness missing")
            stop_reason = result.get("reason")
            success = result.get("success")
    if (
        type(initial) is not dict
        or type(stop_reason) is not str
        or type(success) is not bool
    ):
        raise EvaluationContractError("episode scoring projection incomplete")
    return {
        "policy": policy,
        "mechanic_index": mechanic_index,
        "episode_index": episode_index,
        "random_seed": random_seed,
        "initial_observation": copy.deepcopy(dict(initial)),
        "steps": steps,
        "stop_reason": stop_reason,
        "success": success,
    }


def _validate_worker_result_shape(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or frozenset(value) != _WORKER_RESULT_FIELDS
        or value.get("schema_version") != WORKER_RESULT_SCHEMA
        or value.get("aggregate_metrics") is not None
        or value.get("verdict") is not None
        or type(value.get("trace")) is not dict
        or type(value.get("operational_authority")) is not list
        or type(value.get("memory_after")) is not dict
    ):
        raise EvaluationContractError("candidate worker result fields mismatch")
    return copy.deepcopy(value)


_FULL_LINEAGE_STEP_FIELDS = frozenset(
    {
        "authorization",
        "cognitive_envelope",
        "cognitive_moment",
        "decision_receipt",
        "learned_edge_ref",
        "learning_proof",
        "perception",
        "post_observation",
        "pre_observation",
        "proposal",
        "proposal_proof",
        "selected_action",
        "step_index",
        "step_result",
        "valid_actions",
        "valid_actions_digest",
        "world_snapshot",
    }
)


def _cross_check_candidate_trace(
    result: Mapping[str, Any],
    *,
    environment_log: Sequence[Mapping[str, Any]],
    expected_goal_ref: str,
    expected_environment_seed: int,
    expected_policy_seed: int,
    expected_step_budget: int,
    expected_memory_before: Mapping[str, Any] | None,
    expected_lease_digest: str,
) -> dict[str, Any]:
    """Independently bind worker trace fields to evaluator and lease witnesses."""

    findings: list[str] = []
    trace = result.get("trace")
    semantic = trace.get("semantic_trace") if type(trace) is dict else None
    if type(semantic) is not dict:
        return {"passed": False, "findings": ["semantic trace missing"]}
    if trace.get("semantic_trace_digest") != canonical_digest(semantic):
        findings.append("semantic trace digest mismatch")
    goal = semantic.get("goal")
    if (
        type(goal) is not dict
        or type(goal.get("metadata")) is not dict
        or goal["metadata"].get("target_ref") != expected_goal_ref
        or not _independent_contract_identity(goal, "GoalIR")
    ):
        findings.append("GoalIR target is not evaluator target")
    if semantic.get("environment_seed") != expected_environment_seed:
        findings.append("environment seed mismatch")
    if semantic.get("policy_seed") != expected_policy_seed:
        findings.append("policy seed mismatch")
    if semantic.get("step_budget") != expected_step_budget:
        findings.append("step budget mismatch")
    canonical_empty_memory = {
        "action_sets": [],
        "attempts": [],
        "concepts_by_state": [],
        "schema_version": "atanor.gwip-policy-memory.v1",
        "target_state_digest": None,
        "transitions": [],
    }
    expected_memory = (
        canonical_empty_memory
        if expected_memory_before is None
        else copy.deepcopy(dict(expected_memory_before))
    )
    if semantic.get("memory_before") != expected_memory:
        findings.append("policy memory-before chain mismatch")
    if semantic.get("memory_after") != result.get("memory_after"):
        findings.append("policy memory-after result mismatch")
    steps = semantic.get("steps")
    if type(steps) is not list:
        findings.append("semantic steps missing")
        steps = []
    lineage_steps = trace.get("lineage_steps")
    if type(lineage_steps) is not list or len(lineage_steps) != len(steps):
        findings.append("complete lineage step census mismatch")
        lineage_steps = []
    projection = _candidate_trace_scoring_projection(
        environment_log,
        policy="candidate",
        mechanic_index=0,
        episode_index=0,
        random_seed=None,
    )
    witnessed_steps = projection["steps"]
    operational = result.get("operational_authority")
    if len(steps) != len(witnessed_steps) or len(operational) != len(steps):
        findings.append("trace/environment/authority step census mismatch")
    if not _SHA256.fullmatch(expected_lease_digest):
        findings.append("evaluator lease digest invalid")
    prior_snapshot: str | None = None
    for index, (step, witnessed) in enumerate(zip(steps, witnessed_steps)):
        if type(step) is not dict:
            findings.append(f"step {index} is not an object")
            continue
        actions = [
            {"action_id": action, "payload": {}}
            for action in witnessed["valid_actions"]
        ]
        actions_digest = canonical_digest(actions)
        observation_digest = canonical_digest(witnessed["observation"])
        selected = witnessed["selected_action"]
        step_result = step.get("step_result")
        expected_result = witnessed["result"]
        if (
            step.get("step_index") != index
            or step.get("pre_observation") != witnessed["observation"]
            or step.get("selected_action") != selected
            or step.get("valid_actions") != actions
            or step.get("valid_actions_digest") != actions_digest
            or type(step_result) is not dict
            or step_result.get("observation") != expected_result["observation"]
            or step_result.get("terminal") is not expected_result["terminal"]
            or step_result.get("success") is not expected_result["success"]
            or step_result.get("stop_reason") != expected_result["stop_reason"]
            or step.get("post_observation") != expected_result["observation"]
        ):
            findings.append(f"step {index} evaluator witness mismatch")
        proposal = step.get("proposal")
        decision = step.get("decision_receipt")
        snapshot = step.get("world_snapshot")
        expected_parent_snapshot = prior_snapshot
        if (
            type(proposal) is not dict
            or proposal.get("action_id") != selected
            or proposal.get("valid_actions_digest") != actions_digest
            or proposal.get("observation_digest") != observation_digest
        ):
            findings.append(f"step {index} proposal mismatch")
        snapshot_id = snapshot.get("contract_id") if type(snapshot) is dict else None
        snapshot_metadata = snapshot.get("metadata") if type(snapshot) is dict else None
        if (
            type(snapshot_metadata) is not dict
            or snapshot_metadata.get("observation_digest") != observation_digest
            or snapshot_metadata.get("valid_actions_digest") != actions_digest
            or snapshot.get("parent_snapshot_id") != prior_snapshot
        ):
            findings.append(f"step {index} WorldSnapshot mismatch")
        prior_snapshot = snapshot_id if type(snapshot_id) is str else prior_snapshot
        decision_metadata = decision.get("metadata") if type(decision) is dict else None
        proposed_action = decision.get("proposed_action") if type(decision) is dict else None
        if (
            type(decision_metadata) is not dict
            or type(proposed_action) is not dict
            or proposed_action.get("action_id") != selected
            or decision_metadata.get("observation_digest") != observation_digest
            or decision_metadata.get("valid_actions_digest") != actions_digest
            or decision_metadata.get("snapshot_id") != snapshot_id
            or decision.get("action_executed") is not False
            or decision.get("authoritative") is not False
        ):
            findings.append(f"step {index} DecisionReceipt mismatch")
        authority = step.get("authorization")
        operational_row = operational[index] if index < len(operational) else None
        evidence = (
            operational_row.get("operational_evidence")
            if type(operational_row) is dict
            else None
        )
        expected_counters = {
            **_ZERO_COUNTERS,
            "cycles": index + 1,
            "actions": index + 1,
        }
        if (
            type(authority) is not dict
            or authority.get("action_id") != selected
            or authority.get("step_index") != index
            or authority.get("granted") is not True
            or authority.get("authority_kind") != "externally_signed_run_lease"
            or type(operational_row) is not dict
            or operational_row.get("action_id") != selected
            or operational_row.get("step_index") != index
            or operational_row.get("granted") is not True
            or type(evidence) is not dict
            or evidence.get("action_class") != "interaction.step"
            or evidence.get("runner_id") != "general-interaction-loop-v1"
            or evidence.get("lease_id_sha256") != expected_lease_digest
            or evidence.get("counters") != expected_counters
        ):
            findings.append(f"step {index} direct RunLease witness mismatch")
        if index >= len(lineage_steps):
            continue
        full = lineage_steps[index]
        if type(full) is not dict or frozenset(full) != _FULL_LINEAGE_STEP_FIELDS:
            findings.append(f"step {index} complete lineage fields mismatch")
            continue
        for name in (
            "decision_receipt",
            "learned_edge_ref",
            "post_observation",
            "pre_observation",
            "proposal",
            "selected_action",
            "step_index",
            "step_result",
            "valid_actions",
            "valid_actions_digest",
            "world_snapshot",
        ):
            if full.get(name) != step.get(name):
                findings.append(f"step {index} lineage/semantic {name} mismatch")
        full_authority = full.get("authorization")
        if (
            type(full_authority) is not dict
            or any(
                full_authority.get(name) != authority.get(name)
                for name in (
                    "action_id",
                    "authority_kind",
                    "granted",
                    "reason",
                    "step_index",
                )
            )
            or full_authority != operational_row
        ):
            findings.append(f"step {index} full authority lineage mismatch")
        try:
            perception_raw = full["perception"]
            claim = perception_raw["claim"]
            snapshot_contract = full["world_snapshot"]
            envelope = full["cognitive_envelope"]
            moment = full["cognitive_moment"]
            proposal_proof = full["proposal_proof"]
            decision_contract = full["decision_receipt"]
            learning_proof = full["learning_proof"]
            expected_claim_source = (
                f"environment-observation:{observation_digest}"
            )
            expected_organ_digest = canonical_digest(
                {
                    "claim_id": claim["contract_id"],
                    "concepts": perception_raw["concepts"],
                    "scene_graph": perception_raw["scene_graph"],
                    "situation_summary": perception_raw["situation_summary"],
                }
            )
            if (
                type(perception_raw) is not dict
                or perception_raw.get("observation") != witnessed["observation"]
                or perception_raw.get("observation_digest")
                != observation_digest
                or type(claim) is not dict
                or claim.get("statement")
                != f"Environment observation sha256 {observation_digest}."
                or claim.get("tier") != "observed"
                or claim.get("source_refs") != [expected_claim_source]
                or claim.get("accepted_as_observed_fact") is not True
                or claim.get("metadata")
                != {
                    "observation_digest": observation_digest,
                    "perception": (
                        "deterministic_scene_graph_and_situation_tracker"
                    ),
                }
                or perception_raw.get("organ_digest")
                != expected_organ_digest
            ):
                findings.append(f"step {index} perception lineage mismatch")
            independent_contracts = (
                (claim, "ClaimEnvelope"),
                (full["world_snapshot"], "WorldSnapshot"),
                (full["cognitive_envelope"], "CognitiveEnvelope"),
                (full["cognitive_moment"], "CognitiveMoment"),
                (full["proposal_proof"], "ProofCandidate"),
                (full["decision_receipt"], "DecisionReceipt"),
                (full["learning_proof"], "ProofCandidate"),
            )
            if not all(
                _independent_contract_identity(raw, kind)
                for raw, kind in independent_contracts
            ):
                findings.append(
                    f"step {index} evaluator-owned contract identity mismatch"
                )

            proposal_payload = {
                "action_id": proposal["action_id"],
                "affordance_grounding": proposal["affordance_grounding"],
                "affordance_resonance": float(proposal["affordance_resonance"]),
                "deliberator_proof": proposal["deliberator_proof"],
                "observation_digest": proposal["observation_digest"],
                "strategy": proposal["strategy"],
                "transition_graph_path": proposal["transition_graph_path"],
                "valid_actions_digest": proposal["valid_actions_digest"],
            }
            expected_proposal_id = canonical_id("proposal", proposal_payload)[0]
            expected_edge = canonical_id(
                "transition_edge",
                {
                    "action_id": selected,
                    "from": observation_digest,
                    "to": canonical_digest(expected_result["observation"]),
                },
            )[0]
            target_claim = learning_proof["metadata"]["target_claim"]
            if not _independent_contract_identity(
                target_claim,
                "ClaimEnvelope",
            ):
                findings.append(
                    f"step {index} evaluator-owned target claim identity mismatch"
                )
            lineage_refs_ok = (
                proposal.get("proposal_id") == expected_proposal_id
                and snapshot_contract["observed_claim_ids"]
                == [claim["contract_id"]]
                and snapshot_contract["parent_snapshot_id"]
                == expected_parent_snapshot
                and snapshot_contract["metadata"].get("organ_digest")
                == perception_raw["organ_digest"]
                and envelope["session_id"] == "gwip:controlled"
                and envelope["explicit_user_goal_ids"]
                == [goal["contract_id"]]
                and envelope["world_snapshot_id"]
                == snapshot_contract["contract_id"]
                and moment["moment_index"] == index
                and moment["envelope_id"] == envelope["contract_id"]
                and moment["world_snapshot_id"]
                == snapshot_contract["contract_id"]
                and moment["selected_goal_id"] == goal["contract_id"]
                and moment["claim_ids"] == [claim["contract_id"]]
                and moment["proof_candidate_ids"]
                == [proposal_proof["contract_id"]]
                and proposal_proof["claim_id"] == claim["contract_id"]
                and proposal_proof["premise_claim_ids"]
                == [claim["contract_id"]]
                and proposal_proof["verifier_refs"]
                == [expected_proposal_id]
                and decision_contract["moment_id"] == moment["contract_id"]
                and decision_contract["selected_goal_id"]
                == goal["contract_id"]
                and decision_contract["input_claim_ids"]
                == [claim["contract_id"]]
                and decision_contract["proof_candidate_ids"]
                == [proposal_proof["contract_id"]]
                and full["learned_edge_ref"] == expected_edge
                and learning_proof["claim_id"] == target_claim["contract_id"]
                and learning_proof["premise_claim_ids"]
                == [claim["contract_id"]]
                and learning_proof["verifier_refs"] == [expected_edge]
                and target_claim["source_claim_ids"] == [claim["contract_id"]]
                and target_claim["metadata"].get("action_id") == selected
                and target_claim["metadata"].get("from_observation_digest")
                == observation_digest
                and target_claim["metadata"].get("to_observation_digest")
                == canonical_digest(expected_result["observation"])
            )
            if not lineage_refs_ok:
                findings.append(f"step {index} complete lineage reference mismatch")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            findings.append(
                f"step {index} complete lineage validation error:{type(exc).__name__}"
            )
    if semantic.get("success") is not projection["success"]:
        findings.append("terminal success mismatch")
    if semantic.get("stop_reason") != projection["stop_reason"]:
        findings.append("terminal stop reason mismatch")
    return {
        "passed": not findings,
        "findings": findings,
        "semantic_trace_digest": trace.get("semantic_trace_digest"),
        "memory_after_sha256": canonical_digest(result.get("memory_after")),
    }


def run_candidate_episode_worker(
    *,
    mechanic: HiddenMechanic,
    episode_index: int,
    candidate_root: Path,
    candidate_tree_before: Mapping[str, Any],
    lease_entry: Mapping[str, Any],
    policy_memory: Mapping[str, Any] | None,
    environment_seed: int,
    policy_seed: int,
    step_budget: int,
    expected_worker_sha256: str,
    timeout_seconds: int = 600,
    repository_root: Path = REPO,
) -> dict[str, Any]:
    """Run one candidate episode while authority and hidden state stay in parent."""

    from packages.autonomy_envelope.run_lease import (  # noqa: PLC0415
        GENERAL_INTERACTION_RUNNER_ID,
        RunLeaseBoundaryConfig,
        RunLeaseStore,
    )

    if type(mechanic) is not HiddenMechanic:
        raise EvaluationContractError("candidate episode requires exact hidden mechanic")
    if (
        not _SHA256.fullmatch(str(expected_worker_sha256))
        or hashlib.sha256(WORKER.read_bytes()).hexdigest()
        != expected_worker_sha256
    ):
        raise EvaluationContractError("candidate worker source binding mismatch")
    expected_parent_sources = _trusted_parent_source_records(
        candidate_tree_before
    )
    actual_parent_sources: list[dict[str, Any]] = []
    for module_name, relative in zip(
        (
            "packages.autonomy_envelope.run_lease",
            "packages.autonomy_envelope.operator_trust",
        ),
        TRUSTED_PARENT_SOURCE_PATHS,
    ):
        module = sys.modules.get(module_name)
        raw_path = getattr(module, "__file__", None)
        if type(raw_path) is not str:
            raise EvaluationContractError("trusted parent module path missing")
        module_path = Path(raw_path).resolve(strict=True)
        if (
            _path_within(module_path, Path(candidate_root).resolve(strict=True))
            or not _path_within(module_path, REPO.resolve(strict=True))
            or module_path.relative_to(REPO.resolve(strict=True)).as_posix()
            != relative
        ):
            raise EvaluationContractError(
                "parent authority imported from candidate/untrusted source"
            )
        raw_source = module_path.read_bytes()
        actual_parent_sources.append(
            {
                "path": relative,
                "size_bytes": len(raw_source),
                "sha256": hashlib.sha256(raw_source).hexdigest(),
            }
        )
    if actual_parent_sources != expected_parent_sources:
        raise EvaluationContractError(
            "parent authority bytes differ from sealed trusted source"
        )
    trusted_parent_source_sha256 = canonical_digest(actual_parent_sources)
    validated_lease = _validate_run_lease_entry(
        lease_entry,
        ordinal=(
            mechanic.evaluator_index * 3 + episode_index
        ),
        mechanic_index=mechanic.evaluator_index,
        episode_index=episode_index,
        repository_root=repository_root,
    )
    lease_document = validated_lease["lease_document"]
    live_context = validated_lease["live_context"]
    lease_id = lease_document["lease_id"]
    boundary = RunLeaseBoundaryConfig.from_external_file(
        validated_lease["boundary_config_path"],
        repository_root=repository_root,
    )
    store = RunLeaseStore(boundary)
    activation = store.activate(
        document=lease_document,
        live_context=live_context,
    )
    if activation.allowed is not True or activation.lease_id != lease_id:
        raise EvaluationContractError(f"RunLease activation failed: {activation.reason}")

    environments = {
        session: OpaqueFSTEnvironment(
            mechanic,
            episode_index=episode_index,
            step_budget=step_budget,
        )
        for session in ("primary", "replay", "determinism_a", "determinism_b")
    }
    expected_call_ids = {session: 0 for session in environments}
    authority_call_id = 0
    pending_authorization: tuple[str, int] | None = None
    authority_finished = False
    parent_authorizations: list[dict[str, Any]] = []
    parent_finish: dict[str, Any] | None = None
    environment_phase = "primary"
    sealed_primary_result: dict[str, Any] | None = None
    request = {
        "schema_version": WORKER_REQUEST_SCHEMA,
        "goal_ref": mechanic.goal_ref,
        "environment_seed": environment_seed,
        "policy_seed": policy_seed,
        "step_budget": step_budget,
        "session_id": "gwip:controlled",
        "policy_memory": (
            None if policy_memory is None else copy.deepcopy(dict(policy_memory))
        ),
    }
    with tempfile.TemporaryDirectory(prefix="atanor-gwip-runtime-") as raw_runtime:
        runtime_root = Path(raw_runtime).resolve(strict=True)
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
                in {
                    "APPDATA",
                    "COMSPEC",
                    "LOCALAPPDATA",
                    "PATH",
                    "PATHEXT",
                    "SYSTEMDRIVE",
                    "SYSTEMROOT",
                    "USERPROFILE",
                    "WINDIR",
                }
        }
        env.update(
            {
                "ATANOR_GWIP_CANDIDATE_ROOT": str(
                    Path(candidate_root).resolve(strict=True)
                ),
                "ATANOR_GWIP_RUNTIME_ROOT": str(runtime_root),
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "TEMP": str(runtime_root),
                "TMP": str(runtime_root),
            }
        )
        process = subprocess.Popen(
            [sys.executable, str(WORKER), "candidate-worker"],
            cwd=runtime_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        output_queue: queue.Queue[bytes | None] = queue.Queue()
        stderr_chunks: list[bytes] = []

        def read_stdout() -> None:
            while True:
                line = process.stdout.readline(_WORKER_MAX_LINE_BYTES + 1)
                if not line:
                    output_queue.put(None)
                    return
                output_queue.put(line)

        def read_stderr() -> None:
            while True:
                chunk = process.stderr.read(65536)
                if not chunk:
                    return
                stderr_chunks.append(chunk)

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        _write_worker_message(process.stdin, request)
        deadline = time.monotonic() + timeout_seconds
        worker_result: dict[str, Any] | None = None
        try:
            while worker_result is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise EvaluationContractError("candidate worker timed out")
                try:
                    raw_line = output_queue.get(timeout=remaining)
                except queue.Empty as exc:
                    raise EvaluationContractError("candidate worker timed out") from exc
                if raw_line is None:
                    raise EvaluationContractError("candidate worker exited without result")
                message = _strict_json_line(raw_line, label="candidate worker output")
                message_type = message.get("type")
                if (
                    message.get("schema_version") != WORKER_RPC_SCHEMA
                    or message_type
                    not in {
                        "environment_request",
                        "authority_request",
                        "primary_result",
                        "worker_result",
                        "worker_failure",
                    }
                ):
                    raise EvaluationContractError("candidate worker protocol message invalid")
                if message_type == "worker_failure":
                    raise EvaluationContractError(
                        "candidate worker failed: "
                        f"{message.get('error_type')}:{message.get('error')}"
                    )
                if message_type == "worker_result":
                    if (
                        environment_phase != "complete"
                        or sealed_primary_result is None
                        or pending_authorization is not None
                        or authority_finished is not True
                    ):
                        raise EvaluationContractError(
                            "candidate worker returned before all sealed phases completed"
                        )
                    worker_result = _validate_worker_result_shape(
                        message.get("result")
                    )
                    if any(
                        worker_result[field] != sealed_primary_result[field]
                        for field in _PRIMARY_RESULT_FIELDS
                    ):
                        raise EvaluationContractError(
                            "candidate primary result changed after auxiliary replay"
                        )
                    continue
                if message_type == "primary_result":
                    if (
                        frozenset(message)
                        != {
                            "schema_version",
                            "type",
                            "session",
                            "call_id",
                            "result",
                        }
                        or message.get("session") != "primary_result"
                        or message.get("call_id") != 0
                        or environment_phase != "await_primary_result"
                        or sealed_primary_result is not None
                    ):
                        raise EvaluationContractError(
                            "candidate primary result phase/binding invalid"
                        )
                    candidate_primary = message.get("result")
                    if (
                        type(candidate_primary) is not dict
                        or frozenset(candidate_primary) != _PRIMARY_RESULT_FIELDS
                        or type(candidate_primary.get("trace")) is not dict
                        or type(candidate_primary.get("operational_authority"))
                        is not list
                        or type(candidate_primary.get("memory_after")) is not dict
                    ):
                        raise EvaluationContractError(
                            "candidate primary result shape invalid"
                        )
                    sealed_primary_result = copy.deepcopy(candidate_primary)
                    environment_phase = "replay"
                    _write_worker_message(
                        process.stdin,
                        {
                            "schema_version": WORKER_RPC_SCHEMA,
                            "type": "primary_result_ack",
                            "session": "primary_result",
                            "call_id": 0,
                            "ok": True,
                            "result": {"sealed": True},
                            "error": None,
                        },
                    )
                    continue
                if message_type == "environment_request":
                    if frozenset(message) != {
                        "schema_version",
                        "type",
                        "session",
                        "call_id",
                        "operation",
                        "payload",
                    }:
                        raise EvaluationContractError("environment RPC fields mismatch")
                    session = message.get("session")
                    call_id = message.get("call_id")
                    operation = message.get("operation")
                    payload = message.get("payload")
                    if (
                        session not in environments
                        or session != environment_phase
                        or call_id != expected_call_ids[session]
                        or type(payload) is not dict
                    ):
                        raise EvaluationContractError("environment RPC binding mismatch")
                    expected_call_ids[session] += 1
                    environment = environments[session]
                    if operation == "reset" and frozenset(payload) == {"seed"}:
                        if payload["seed"] != environment_seed:
                            raise EvaluationContractError("environment reset seed mismatch")
                        rpc_result = environment.reset(payload["seed"])
                    elif operation == "observe" and not payload:
                        rpc_result = environment.observe()
                    elif operation == "valid_actions" and not payload:
                        rpc_result = list(environment.valid_actions())
                    elif operation == "step" and frozenset(payload) == {"action_id"}:
                        action_id = payload["action_id"]
                        if session == "primary":
                            if pending_authorization != (
                                action_id,
                                len(
                                    [
                                        item
                                        for item in environment.call_log
                                        if item["operation"] == "step"
                                    ]
                                ),
                            ):
                                raise EvaluationContractError(
                                    "environment step lacks matching parent authorization"
                                )
                            pending_authorization = None
                        rpc_result = environment.step(action_id)
                    elif operation == "stop" and frozenset(payload) == {"reason"}:
                        if session == "primary" and pending_authorization is not None:
                            raise EvaluationContractError(
                                "environment stopped with unconsumed authorization"
                            )
                        rpc_result = environment.stop(payload["reason"])
                        phase_audit = audit_environment_call_order(
                            environment.call_log,
                            step_budget=step_budget,
                        )
                        if phase_audit["passed"] is not True:
                            raise EvaluationContractError(
                                f"{session} environment phase order invalid"
                            )
                        if session == "primary":
                            environment_phase = "await_primary_finish"
                        elif session == "replay":
                            environment_phase = "determinism_a"
                        elif session == "determinism_a":
                            environment_phase = "determinism_b"
                        elif session == "determinism_b":
                            environment_phase = "complete"
                        else:
                            raise AssertionError("unknown environment phase")
                    else:
                        raise EvaluationContractError("environment RPC operation invalid")
                    _write_worker_message(
                        process.stdin,
                        _worker_environment_response(
                            session=session,
                            call_id=call_id,
                            result=rpc_result,
                        ),
                    )
                    continue

                if frozenset(message) != {
                    "schema_version",
                    "type",
                    "session",
                    "call_id",
                    "operation",
                    "payload",
                }:
                    raise EvaluationContractError("authority RPC fields mismatch")
                if (
                    message.get("session") != "authority"
                    or message.get("call_id") != authority_call_id
                    or type(message.get("payload")) is not dict
                ):
                    raise EvaluationContractError("authority RPC binding mismatch")
                call_id = authority_call_id
                authority_call_id += 1
                operation = message["operation"]
                payload = message["payload"]
                if operation == "authorize" and frozenset(payload) == {
                    "action_id",
                    "step_index",
                }:
                    if (
                        environment_phase != "primary"
                        or pending_authorization is not None
                        or authority_finished
                    ):
                        raise EvaluationContractError("RunLease authorization order invalid")
                    action_id = payload["action_id"]
                    step_index = payload["step_index"]
                    if type(action_id) is not str or type(step_index) is not int:
                        raise EvaluationContractError("RunLease authorization payload invalid")
                    authorization = store.authorize(
                        lease_id=lease_id,
                        runner_id=GENERAL_INTERACTION_RUNNER_ID,
                        action_class="interaction.step",
                        costs=_FIXED_AUTHORIZATION_COSTS,
                    )
                    if authorization.allowed is True:
                        pending_authorization = (action_id, step_index)
                    counters = dict(authorization.counters or {})
                    rpc_result = {
                        "action_id": action_id,
                        "step_index": step_index,
                        "granted": authorization.allowed is True,
                        "reason": authorization.reason,
                        "authority_kind": "externally_signed_run_lease",
                        "operational_evidence": {
                            "action_class": "interaction.step",
                            "counters": counters,
                            "lease_id_sha256": canonical_digest(lease_id),
                            "runner_id": GENERAL_INTERACTION_RUNNER_ID,
                        },
                    }
                    parent_authorizations.append(
                        _authorization_witness_from_parent_response(rpc_result)
                    )
                elif operation == "finish" and frozenset(payload) == {"reason"}:
                    if (
                        environment_phase != "await_primary_finish"
                        or pending_authorization is not None
                        or authority_finished
                    ):
                        raise EvaluationContractError("RunLease finish order invalid")
                    finished = store.finish(
                        lease_id=lease_id,
                        runner_id=GENERAL_INTERACTION_RUNNER_ID,
                        reason=payload["reason"],
                    )
                    authority_finished = True
                    environment_phase = "await_primary_result"
                    rpc_result = finished.to_dict()
                    parent_finish = copy.deepcopy(rpc_result)
                else:
                    raise EvaluationContractError("authority RPC operation invalid")
                _write_worker_message(
                    process.stdin,
                    _worker_authority_response(call_id=call_id, result=rpc_result),
                )
        except Exception:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            raise
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass
        remaining = max(0.1, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise EvaluationContractError("candidate worker did not exit") from exc
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        if return_code != 0:
            detail = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            raise EvaluationContractError(
                f"candidate worker exited {return_code}: {detail[-1000:]}"
            )
        runtime_entries = sorted(path.name for path in runtime_root.iterdir())
        if runtime_entries:
            raise EvaluationContractError("candidate worker wrote runtime files")
        if hashlib.sha256(WORKER.read_bytes()).hexdigest() != expected_worker_sha256:
            raise EvaluationContractError(
                "candidate worker source changed during episode"
            )

    assert worker_result is not None
    if parent_finish is None:
        raise EvaluationContractError("parent RunLease finish transcript missing")
    trace = worker_result["trace"]
    lineage_steps = trace.get("lineage_steps")
    if (
        worker_result["operational_authority"] != parent_authorizations
        or type(lineage_steps) is not list
        or [item.get("authorization") for item in lineage_steps]
        != parent_authorizations
        or trace.get("authority_finish") != parent_finish
    ):
        raise EvaluationContractError(
            "candidate authority lineage differs from parent-owned transcript"
        )
    authority_transcript_sha256 = canonical_digest(
        {
            "authorizations": parent_authorizations,
            "finish": parent_finish,
        }
    )
    source_after = bind_source_tree(candidate_root)
    if dict(candidate_tree_before) != source_after:
        raise EvaluationContractError("candidate source tree changed during worker run")
    primary_log = environments["primary"].call_log
    replay_log = environments["replay"].call_log
    determinism_a_log = environments["determinism_a"].call_log
    determinism_b_log = environments["determinism_b"].call_log
    call_audit = audit_environment_call_order(primary_log, step_budget=step_budget)
    if (
        not call_audit["passed"]
        or replay_log != primary_log
        or determinism_a_log != primary_log
        or determinism_b_log != primary_log
    ):
        raise EvaluationContractError("candidate environment replay/determinism audit failed")
    structural = worker_result["structural_verification"]
    if (
        type(structural) is not dict
        or structural.get("structural_replay_ok") is not True
        or structural.get("receipt_cross_check_ok") is not True
        or structural.get("environment_reexecution_ok") is not True
        or structural.get("fixture_authority_check_ok") is not True
        or structural.get("authority_independently_verified") is not False
        or structural.get("ok") is not False
    ):
        raise EvaluationContractError("candidate structural verifier evidence invalid")
    if (
        type(worker_result["determinism"]) is not dict
        or worker_result["determinism"].get("passed") is not True
        or worker_result["determinism"].get("trace_a_digest")
        != worker_result["determinism"].get("trace_b_digest")
        or worker_result["determinism"].get("memory_after_a_sha256")
        != canonical_digest(worker_result["memory_after"])
        or worker_result["determinism"].get("memory_after_b_sha256")
        != canonical_digest(worker_result["memory_after"])
        or type(worker_result["isolation"]) is not dict
        or worker_result["isolation"].get("passed") is not True
        or type(worker_result["module_closure"]) is not dict
        or worker_result["module_closure"].get("passed") is not True
    ):
        raise EvaluationContractError("candidate determinism/isolation evidence invalid")
    cross_check = _cross_check_candidate_trace(
        worker_result,
        environment_log=primary_log,
        expected_goal_ref=mechanic.goal_ref,
        expected_environment_seed=environment_seed,
        expected_policy_seed=policy_seed,
        expected_step_budget=step_budget,
        expected_memory_before=policy_memory,
        expected_lease_digest=canonical_digest(lease_id),
    )
    if not cross_check["passed"]:
        raise EvaluationContractError(
            "candidate trace independent cross-check failed: "
            + "; ".join(cross_check["findings"][:5])
        )
    status = store.status()
    runner = status.get("runners", {}).get(GENERAL_INTERACTION_RUNNER_ID)
    executed_steps = sum(
        1 for item in primary_log if item.get("operation") == "step"
    )
    expected_counters = {
        **_ZERO_COUNTERS,
        "cycles": executed_steps,
        "actions": executed_steps,
    }
    if (
        status.get("state_ok") is not True
        or type(runner) is not dict
        or runner.get("state_ok") is not True
        or runner.get("status") != "finished"
        or runner.get("lease_id") != lease_id
        or runner.get("authorization_count") != executed_steps
        or runner.get("counters") != expected_counters
        or runner.get("finish_reason")
        != worker_result["trace"]["semantic_trace"]["stop_reason"]
    ):
        raise EvaluationContractError("parent RunLease durable reconciliation failed")
    replay_activation = store.activate(
        document=lease_document,
        live_context=live_context,
    )
    if replay_activation.allowed is not False or replay_activation.reason != "run_lease_replay":
        raise EvaluationContractError("RunLease single-use replay control failed")
    sealed_ledger = verify_finished_run_lease_ledger(
        validated_lease,
        ordinal=(mechanic.evaluator_index * 3 + episode_index),
        mechanic_index=mechanic.evaluator_index,
        episode_index=episode_index,
        repository_root=repository_root,
    )
    if (
        sealed_ledger.get("state_ok") is not True
        or sealed_ledger.get("lease_id") != lease_id
        or sealed_ledger.get("authorization_count") != executed_steps
        or sealed_ledger.get("counters") != expected_counters
        or sealed_ledger.get("finish_reason")
        != worker_result["trace"]["semantic_trace"]["stop_reason"]
    ):
        raise EvaluationContractError(
            "finished RunLease ledger sealing failed"
        )
    scoring = _candidate_trace_scoring_projection(
        primary_log,
        policy="candidate",
        mechanic_index=mechanic.evaluator_index,
        episode_index=episode_index,
        random_seed=None,
    )
    return {
        "schema_version": "atanor.gwip-candidate-episode-evidence.v1",
        "scoring": scoring,
        "trace": worker_result["trace"],
        "operational_authority": worker_result["operational_authority"],
        "memory_before_sha256": canonical_digest(
            (
                {
                    "action_sets": [],
                    "attempts": [],
                    "concepts_by_state": [],
                    "schema_version": "atanor.gwip-policy-memory.v1",
                    "target_state_digest": None,
                    "transitions": [],
                }
                if policy_memory is None
                else dict(policy_memory)
            )
        ),
        "memory_after": worker_result["memory_after"],
        "memory_after_sha256": canonical_digest(worker_result["memory_after"]),
        "environment_call_log": primary_log,
        "replay_call_log": replay_log,
        "determinism_call_logs": {
            "a": determinism_a_log,
            "b": determinism_b_log,
        },
        "structural_verification": structural,
        "determinism": worker_result["determinism"],
        "trace_cross_check": cross_check,
        "module_closure": worker_result["module_closure"],
        "isolation": worker_result["isolation"],
        "parent_run_lease": {
            "lease_id_sha256": canonical_digest(lease_id),
            "activation_reason": activation.reason,
            "payload_sha256": activation.payload_sha256,
            "trusted_parent_source_sha256": trusted_parent_source_sha256,
            "authority_transcript_sha256": authority_transcript_sha256,
            "authorization_count": executed_steps,
            "final_counters": expected_counters,
            "finish_reason": runner["finish_reason"],
            "single_use_replay_reason": replay_activation.reason,
            "active_state_raw_sha256": sealed_ledger[
                "active_state_raw_sha256"
            ],
            "nonce_claim_raw_sha256": sealed_ledger[
                "nonce_claim_raw_sha256"
            ],
            "passed": True,
        },
        "source_tree_before_sha256": candidate_tree_before["tree_sha256"],
        "source_tree_after_sha256": source_after["tree_sha256"],
        "aggregate_metrics": None,
        "verdict": None,
    }


def run_control_episode(
    *,
    mechanic: HiddenMechanic,
    episode_index: int,
    policy: ReactivePolicy | RandomPolicy,
    policy_label: str,
    environment_seed: int,
    random_seed: int | None,
    step_budget: int,
) -> dict[str, Any]:
    """Execute an evaluator-owned control without candidate code or authority."""

    if policy_label not in {"reactive", "random"}:
        raise EvaluationContractError("control policy label invalid")
    if (policy_label == "random") is not (type(random_seed) is int):
        raise EvaluationContractError("control random seed binding invalid")
    environment = OpaqueFSTEnvironment(
        mechanic,
        episode_index=episode_index,
        step_budget=step_budget,
    )
    environment.reset(environment_seed)
    success = False
    stop_reason = "step_budget_exhausted"
    for _ in range(step_budget):
        observation = environment.observe()
        actions = environment.valid_actions()
        selected = policy.choose_action(observation, actions)
        result = environment.step(selected)
        if result["terminal"] or result["success"]:
            success = result["success"]
            stop_reason = result["stop_reason"] or "environment_terminal"
            break
    environment.stop(stop_reason)
    scoring = _candidate_trace_scoring_projection(
        environment.call_log,
        policy=policy_label,
        mechanic_index=mechanic.evaluator_index,
        episode_index=episode_index,
        random_seed=random_seed,
    )
    if scoring["success"] is not success:
        raise EvaluationContractError("control terminal witness mismatch")
    return {
        "schema_version": "atanor.gwip-control-episode-evidence.v1",
        "scoring": scoring,
        "environment_call_log": environment.call_log,
        "call_order": audit_environment_call_order(
            environment.call_log,
            step_budget=step_budget,
        ),
        "aggregate_metrics": None,
        "verdict": None,
    }


_SCORING_EPISODE_FIELDS = frozenset(
    {
        "policy",
        "mechanic_index",
        "episode_index",
        "random_seed",
        "initial_observation",
        "steps",
        "stop_reason",
        "success",
    }
)


def metric_from_raw_episode(
    value: Mapping[str, Any],
    *,
    mechanic: HiddenMechanic,
    step_budget: int,
) -> EpisodeMetric:
    """Re-simulate raw actions from the hidden table; ignore supplied metrics."""

    if type(value) is not dict or frozenset(value) != _SCORING_EPISODE_FIELDS:
        raise EvaluationContractError("raw scoring episode fields mismatch")
    episode_index = value.get("episode_index")
    if (
        value.get("mechanic_index") != mechanic.evaluator_index
        or type(episode_index) is not int
        or not 0 <= episode_index < len(mechanic.episodes)
        or value.get("policy") not in {"candidate", "reactive", "random"}
        or type(value.get("steps")) is not list
        or len(value["steps"]) > step_budget
        or type(value.get("stop_reason")) is not str
        or not value["stop_reason"]
        or type(value.get("success")) is not bool
    ):
        raise EvaluationContractError("raw scoring episode identity invalid")
    if value["policy"] == "random":
        if type(value.get("random_seed")) is not int:
            raise EvaluationContractError("raw random episode seed missing")
    elif value.get("random_seed") is not None:
        raise EvaluationContractError("non-random episode carries random seed")
    state = mechanic.episodes[episode_index].start_ref

    def observation(state_ref: str) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_SCHEMA,
            "state_ref": state_ref,
            "terminal": state_ref == mechanic.goal_ref,
        }

    if value.get("initial_observation") != observation(state):
        raise EvaluationContractError("raw episode initial observation mismatch")
    reached_terminal = False
    for index, row in enumerate(value["steps"]):
        if (
            type(row) is not dict
            or frozenset(row)
            != {
                "step_index",
                "observation",
                "valid_actions",
                "selected_action",
                "result",
            }
            or row.get("step_index") != index
            or row.get("observation") != observation(state)
            or row.get("valid_actions") != list(mechanic.action_refs)
            or row.get("selected_action") not in mechanic.action_refs
        ):
            raise EvaluationContractError(f"raw episode step {index} input mismatch")
        if reached_terminal:
            raise EvaluationContractError("raw episode continued after terminal")
        next_state = mechanic.transition(state, row["selected_action"])
        expected_observation = observation(next_state)
        terminal = next_state == mechanic.goal_ref
        expected_result = {
            "observation": expected_observation,
            "terminal": terminal,
            "success": terminal,
            "stop_reason": "goal_reached" if terminal else None,
        }
        if row.get("result") != expected_result:
            raise EvaluationContractError(f"raw episode step {index} result mismatch")
        state = next_state
        reached_terminal = terminal
    success = state == mechanic.goal_ref
    if value["success"] is not success:
        raise EvaluationContractError("raw episode success is not hidden-state result")
    if success and value["stop_reason"] != "goal_reached":
        raise EvaluationContractError("successful raw episode stop reason mismatch")
    if not success and len(value["steps"]) > step_budget:
        raise EvaluationContractError("raw episode exceeded step budget")
    optimum = mechanic.episodes[episode_index].optimal_steps
    executed = len(value["steps"])
    swae = episode_swae(
        success=success,
        optimal_steps=optimum,
        executed_steps=executed,
    )
    return EpisodeMetric(
        mechanic_index=mechanic.evaluator_index,
        episode_index=episode_index,
        success=success,
        optimal_steps=optimum,
        executed_steps=executed,
        swae=swae,
        stop_reason=value["stop_reason"],
    )


def _verify_control_choices(
    rows: Sequence[Mapping[str, Any]],
    *,
    mechanics: Sequence[HiddenMechanic],
    preregistration: Mapping[str, Any],
) -> None:
    reactive_rows = [
        row for row in rows if row.get("policy") == "reactive"
    ]
    expected_count = (
        preregistration["mechanic_count"]
        * preregistration["episodes_per_mechanic"]
    )
    if len(reactive_rows) != expected_count:
        raise EvaluationContractError("reactive raw episode census mismatch")
    for row in reactive_rows:
        for step in row["steps"]:
            expected = ReactivePolicy.choose_action(
                step["observation"],
                step["valid_actions"],
            )
            if step["selected_action"] != expected:
                raise EvaluationContractError("reactive raw choice mismatch")

    random_rows = [row for row in rows if row.get("policy") == "random"]
    if len(random_rows) != expected_count * len(preregistration["random_policy_seeds"]):
        raise EvaluationContractError("random raw episode census mismatch")
    index = {
        (
            row["mechanic_index"],
            row["random_seed"],
            row["episode_index"],
        ): row
        for row in random_rows
    }
    if len(index) != len(random_rows):
        raise EvaluationContractError("random raw episode identities duplicate")
    for mechanic in mechanics:
        for seed in preregistration["random_policy_seeds"]:
            policy = RandomPolicy(
                policy_seed=seed,
                mechanic_binding=mechanic.private_ref,
            )
            for episode_index in range(preregistration["episodes_per_mechanic"]):
                row = index.get((mechanic.evaluator_index, seed, episode_index))
                if row is None:
                    raise EvaluationContractError("random raw episode missing")
                for step in row["steps"]:
                    expected = policy.choose_action(
                        step["observation"],
                        step["valid_actions"],
                    )
                    if step["selected_action"] != expected:
                        raise EvaluationContractError("random raw choice mismatch")


def derive_metrics_from_raw_episodes(
    *,
    candidate_rows: Sequence[Mapping[str, Any]],
    reactive_rows: Sequence[Mapping[str, Any]],
    random_rows: Sequence[Mapping[str, Any]],
    mechanics: Sequence[HiddenMechanic],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently derive all aggregates and the no-go from raw action rows."""

    _validate_preregistration(preregistration)
    if len(mechanics) != preregistration["mechanic_count"]:
        raise EvaluationContractError("raw verifier mechanic census mismatch")
    expected = preregistration["candidate_episode_count"]
    if len(candidate_rows) != expected or len(reactive_rows) != expected:
        raise EvaluationContractError("candidate/reactive raw episode census mismatch")
    if len(random_rows) != expected * len(preregistration["random_policy_seeds"]):
        raise EvaluationContractError("random raw episode census mismatch")
    mechanic_by_index = {item.evaluator_index: item for item in mechanics}

    def metrics(rows: Sequence[Mapping[str, Any]], label: str) -> list[EpisodeMetric]:
        output: list[EpisodeMetric] = []
        seen: set[tuple[int, int]] = set()
        for row in rows:
            if row.get("policy") != label:
                raise EvaluationContractError(f"{label} raw row policy mismatch")
            mechanic_index = row.get("mechanic_index")
            if mechanic_index not in mechanic_by_index:
                raise EvaluationContractError(f"{label} raw mechanic missing")
            identity = (mechanic_index, row.get("episode_index"))
            if identity in seen:
                raise EvaluationContractError(f"{label} raw episode duplicate")
            seen.add(identity)
            output.append(
                metric_from_raw_episode(
                    row,
                    mechanic=mechanic_by_index[mechanic_index],
                    step_budget=preregistration["step_budget"],
                )
            )
        return output

    candidate_metrics = metrics(candidate_rows, "candidate")
    reactive_metrics = metrics(reactive_rows, "reactive")
    _verify_control_choices(
        [*reactive_rows, *random_rows],
        mechanics=mechanics,
        preregistration=preregistration,
    )
    random_by_seed: list[PolicyAggregate] = []
    random_metric_rows: list[dict[str, Any]] = []
    for seed in preregistration["random_policy_seeds"]:
        seed_rows = [row for row in random_rows if row.get("random_seed") == seed]
        seed_metrics = metrics(seed_rows, "random")
        aggregate = aggregate_mechanics(
            seed_metrics,
            mechanic_count=preregistration["mechanic_count"],
            episodes_per_mechanic=preregistration["episodes_per_mechanic"],
        )
        random_by_seed.append(aggregate)
        random_metric_rows.append(
            {
                "policy_seed": seed,
                "aggregate": aggregate.to_dict(),
            }
        )
    candidate_aggregate = aggregate_mechanics(
        candidate_metrics,
        mechanic_count=preregistration["mechanic_count"],
        episodes_per_mechanic=preregistration["episodes_per_mechanic"],
    )
    reactive_aggregate = aggregate_mechanics(
        reactive_metrics,
        mechanic_count=preregistration["mechanic_count"],
        episodes_per_mechanic=preregistration["episodes_per_mechanic"],
    )
    random_aggregate = average_random_aggregates(
        random_by_seed,
        preregistration=preregistration,
    )
    gate = score_efficiency_gate(
        candidate_aggregate,
        reactive_aggregate,
        random_aggregate,
        preregistration,
    )
    return {
        "candidate_episode_metrics": [asdict(item) for item in candidate_metrics],
        "reactive_episode_metrics": [asdict(item) for item in reactive_metrics],
        "random_seed_aggregates": random_metric_rows,
        "policy_metrics": {
            "candidate": candidate_aggregate.to_dict(),
            "reactive": reactive_aggregate.to_dict(),
            "random": random_aggregate.to_dict(),
        },
        "efficiency_gate": gate,
    }


_RAW_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "preregistration_binding",
        "seed_manifest_binding",
        "source_binding",
        "run_lease_plan_binding",
        "cohort_binding",
        "attempt_binding",
        "execution_order",
        "candidate_episodes",
        "reactive_episodes",
        "random_episodes",
        "source_audit",
        "aggregate_metrics",
        "verdict",
    }
)
_CANDIDATE_EPISODE_FIELDS = frozenset(
    {
        "schema_version",
        "scoring",
        "trace",
        "operational_authority",
        "memory_before_sha256",
        "memory_after",
        "memory_after_sha256",
        "environment_call_log",
        "replay_call_log",
        "determinism_call_logs",
        "structural_verification",
        "determinism",
        "trace_cross_check",
        "module_closure",
        "isolation",
        "parent_run_lease",
        "source_tree_before_sha256",
        "source_tree_after_sha256",
        "aggregate_metrics",
        "verdict",
    }
)
_CONTROL_EPISODE_FIELDS = frozenset(
    {
        "schema_version",
        "scoring",
        "environment_call_log",
        "call_order",
        "aggregate_metrics",
        "verdict",
    }
)


def _independent_contract_replay(trace: Mapping[str, Any]) -> bool:
    """Replay the complete cycle using evaluator-owned JSON rules only."""

    try:
        semantic = trace["semantic_trace"]
        lineage_steps = trace["lineage_steps"]
        goal = semantic["goal"]
        steps = semantic["steps"]
        if (
            type(semantic) is not dict
            or type(goal) is not dict
            or not _independent_contract_identity(goal, "GoalIR")
            or type(steps) is not list
            or type(lineage_steps) is not list
            or len(lineage_steps) != len(steps)
        ):
            return False
        for step, full in zip(semantic["steps"], lineage_steps):
            if (
                type(step) is not dict
                or type(full) is not dict
                or not _independent_contract_identity(
                    step["decision_receipt"],
                    "DecisionReceipt",
                )
                or not _independent_contract_identity(
                    step["world_snapshot"],
                    "WorldSnapshot",
                )
                or full["decision_receipt"] != step["decision_receipt"]
                or full["world_snapshot"] != step["world_snapshot"]
            ):
                return False
        raw_receipt = trace["cycle_receipt"]
        receipt_fields = {
            "action_authorized",
            "authoritative",
            "contract_type",
            "declared_effects",
            "entities",
            "events",
            "initial_state",
            "input_hash",
            "limitations",
            "observer_only",
            "output_hash",
            "permission_mutated",
            "promotion_mutated",
            "receipt_id",
            "request_cycle",
            "schema_version",
            "selected_route",
            "status",
            "terminal_state_hash",
            "truth_mutated",
        }
        if (
            type(raw_receipt) is not dict
            or set(raw_receipt) != receipt_fields
            or raw_receipt.get("schema_version")
            != "atanor.cognitive_core.m1.v1"
            or raw_receipt.get("contract_type") != "CycleReceipt"
            or raw_receipt.get("observer_only") is not True
            or any(
                raw_receipt.get(name) is not False
                for name in (
                    "action_authorized",
                    "authoritative",
                    "permission_mutated",
                    "promotion_mutated",
                    "truth_mutated",
                )
            )
        ):
            return False
        denied = semantic["denied_attempt"]
        status = (
            "completed"
            if semantic["success"]
            else "abstained"
            if semantic["stop_reason"] in {"no_valid_actions", "policy_abstained"}
            else "cancelled"
            if semantic["stop_reason"].startswith(
                ("step_budget", "run_lease", "operator_stop")
            )
            else "failed"
        )
        identity = {
            "environment_seed": semantic["environment_seed"],
            "goal_id": goal["contract_id"],
            "memory_before_digest": canonical_digest(semantic["memory_before"]),
            "policy_seed": semantic["policy_seed"],
            "reset_digest": canonical_digest(semantic["reset_result"]),
            "step_budget": semantic["step_budget"],
        }
        expected_request_id = canonical_id("gwip_request", identity)[0]
        expected_cycle_id = canonical_id("gwip_cycle", identity)[0]
        request = raw_receipt["request_cycle"]
        expected_input_observation_id = (
            "environment-observation:"
            + canonical_digest(steps[0]["pre_observation"])
            if steps
            else "environment-reset:" + canonical_digest(semantic["reset_result"])
        )
        request_fields = {
            "authoritative",
            "contract_type",
            "cycle_id",
            "input_observation_id",
            "observer_only",
            "parent_cycle_id",
            "request_id",
            "schema_version",
            "seed",
            "session_id",
        }
        if (
            type(request) is not dict
            or set(request) != request_fields
            or request.get("schema_version")
            != "atanor.cognitive_core.m1.v1"
            or request.get("contract_type") != "RequestCycle"
            or request.get("observer_only") is not True
            or request.get("authoritative") is not False
            or request.get("request_id") != expected_request_id
            or request.get("cycle_id") != expected_cycle_id
            or request.get("session_id") != "gwip:controlled"
            or request.get("seed") != semantic["policy_seed"]
            or request.get("input_observation_id")
            != expected_input_observation_id
            or request.get("parent_cycle_id") is not None
            or raw_receipt.get("input_hash") != canonical_digest(identity)
            or raw_receipt.get("status") != status
            or raw_receipt.get("output_hash")
            != canonical_digest(
                {
                    "status": status,
                    "step_count": len(steps),
                    "stop_reason": semantic["stop_reason"],
                    "success": semantic["success"],
                }
            )
            or raw_receipt.get("selected_route")
            != "generic_world_interaction"
            or raw_receipt.get("declared_effects")
            != (["environment_step_observed"] if steps else [])
            or raw_receipt.get("limitations")
            != [
                "decision_receipts_are_non_authoritative",
                "mechanism_only",
                "structural_replay_does_not_reexecute_environment",
            ]
            or raw_receipt.get("initial_state")
            != {"status": "running", "step_count": 0}
        ):
            return False

        entities = raw_receipt["entities"]
        if type(entities) is not list:
            return False
        expected_entity_count = 2 + 5 * len(steps) + (1 if denied else 0)
        if len(entities) != expected_entity_count:
            return False
        entity_fields = {
            "authoritative",
            "contract_type",
            "cycle_id",
            "kind",
            "legacy_ref",
            "observer_only",
            "occurrence_id",
            "ordinal",
            "payload",
            "payload_hash",
            "schema_version",
            "semantic_id",
        }
        seen_occurrence_ids: set[str] = set()
        for ordinal, entity in enumerate(entities):
            if (
                type(entity) is not dict
                or set(entity) != entity_fields
                or entity.get("schema_version")
                != "atanor.cognitive_core.m1.v1"
                or entity.get("contract_type") != "CanonicalEntityRef"
                or entity.get("observer_only") is not True
                or entity.get("authoritative") is not False
                or entity.get("cycle_id") != expected_cycle_id
                or entity.get("ordinal") != ordinal
                or type(entity.get("kind")) is not str
                or type(entity.get("payload")) is not dict
            ):
                return False
            payload_hash = canonical_digest(entity["payload"])
            semantic_id = canonical_id(
                f"sem_{entity['kind']}",
                {"kind": entity["kind"], "payload_hash": payload_hash},
            )[0]
            occurrence_id = canonical_id(
                f"occ_{entity['kind']}",
                {
                    "cycle_id": expected_cycle_id,
                    "kind": entity["kind"],
                    "ordinal": ordinal,
                    "payload_hash": payload_hash,
                },
            )[0]
            if (
                entity.get("payload_hash") != payload_hash
                or entity.get("semantic_id") != semantic_id
                or entity.get("occurrence_id") != occurrence_id
                or occurrence_id in seen_occurrence_ids
            ):
                return False
            seen_occurrence_ids.add(occurrence_id)
        cursor = 0
        goal_entity = entities[cursor]
        cursor += 1
        if goal_entity["kind"] != "goal" or goal_entity["payload"] != semantic["goal"]:
            return False
        phase_refs: list[tuple[str, list[str]]] = [
            ("ingress", [goal_entity["occurrence_id"]])
        ]
        expected_state: dict[str, Any] = {
            "status": "running",
            "step_count": 0,
            "goal_id": goal["contract_id"],
            "reset_digest": canonical_digest(semantic["reset_result"]),
        }
        for index, (step, full) in enumerate(zip(steps, lineage_steps)):
            observation_entity, plan_entity, action_entity, authorization_entity, learning_entity = (
                entities[cursor : cursor + 5]
            )
            cursor += 5
            perception = full["perception"]
            post_digest = canonical_digest(step["post_observation"])
            expected_payloads = (
                (
                    "observation",
                    {
                        "claim_id": perception["claim"]["contract_id"],
                        "observation_digest": perception["observation_digest"],
                        "snapshot_id": step["world_snapshot"]["contract_id"],
                        "valid_actions_digest": step["valid_actions_digest"],
                    },
                ),
                ("plan", step["proposal"]),
                (
                    "action",
                    {
                        "action_id": step["selected_action"],
                        "decision_receipt_id": step["decision_receipt"][
                            "contract_id"
                        ],
                        "proposal_id": step["proposal"]["proposal_id"],
                        "valid_actions_digest": step["valid_actions_digest"],
                    },
                ),
                (
                    "evaluation",
                    {
                        "action_occurrence_id": action_entity["occurrence_id"],
                        "authorization_witness_id": full["authorization"][
                            "witness_id"
                        ],
                        "granted": True,
                    },
                ),
                (
                    "learning_candidate",
                    {
                        "action_occurrence_id": action_entity["occurrence_id"],
                        "edge_ref": step["learned_edge_ref"],
                        "from_observation_digest": perception[
                            "observation_digest"
                        ],
                        "learning_proof_id": full["learning_proof"][
                            "contract_id"
                        ],
                        "to_observation_digest": post_digest,
                    },
                ),
            )
            for entity, (kind, payload) in zip(
                (
                    observation_entity,
                    plan_entity,
                    action_entity,
                    authorization_entity,
                    learning_entity,
                ),
                expected_payloads,
            ):
                if entity["kind"] != kind or entity["payload"] != payload:
                    return False
            phase_refs.extend(
                (
                    ("perception", [observation_entity["occurrence_id"]]),
                    (
                        "selection",
                        [
                            plan_entity["occurrence_id"],
                            action_entity["occurrence_id"],
                        ],
                    ),
                    (
                        "authorization_observation",
                        [authorization_entity["occurrence_id"]],
                    ),
                    (
                        "effect_observation",
                        [
                            action_entity["occurrence_id"],
                            learning_entity["occurrence_id"],
                        ],
                    ),
                    (
                        "learning_proposal",
                        [learning_entity["occurrence_id"]],
                    ),
                )
            )
            expected_state.update(
                {
                    "current_observation_digest": perception[
                        "observation_digest"
                    ],
                    "current_snapshot_id": step["world_snapshot"]["contract_id"],
                    "valid_actions_digest": step["valid_actions_digest"],
                    "decision_receipt_id": step["decision_receipt"][
                        "contract_id"
                    ],
                    "proposed_action_occurrence_id": action_entity[
                        "occurrence_id"
                    ],
                    "proposal_id": step["proposal"]["proposal_id"],
                    "authorization_witness_id": full["authorization"][
                        "witness_id"
                    ],
                    "last_action_occurrence_id": action_entity["occurrence_id"],
                    "post_observation_digest": post_digest,
                    "step_count": index + 1,
                    "latest_learning_edge_ref": step["learned_edge_ref"],
                }
            )
        denied_refs: list[str] = []
        if denied:
            denied_entity = entities[cursor]
            cursor += 1
            denied_payload = {
                "action_id": denied["proposal"]["action_id"],
                "executed": False,
                "reason": denied["reason"],
                "valid_actions_digest": denied["valid_actions_digest"],
            }
            if (
                denied_entity["kind"] != "evaluation"
                or denied_entity["payload"] != denied_payload
            ):
                return False
            denied_refs = [denied_entity["occurrence_id"]]
            phase_refs.append(("evaluation", denied_refs))
            expected_state.update(
                {
                    "denied_action_id": denied["proposal"]["action_id"],
                    "denial_reason": denied["reason"],
                }
            )
        terminal_entity = entities[cursor]
        if (
            cursor != len(entities) - 1
            or terminal_entity["kind"] != "episode"
            or terminal_entity["payload"]
            != {
                "status": status,
                "step_count": len(steps),
                "stop_reason": semantic["stop_reason"],
                "success": semantic["success"],
            }
        ):
            return False
        phase_refs.append(
            (
                "terminal",
                [*denied_refs, terminal_entity["occurrence_id"]],
            )
        )
        events = raw_receipt["events"]
        if type(events) is not list or len(events) != len(phase_refs):
            return False
        event_fields = {
            "authoritative",
            "contract_type",
            "cycle_id",
            "entity_occurrence_ids",
            "event_id",
            "metadata",
            "observer_only",
            "parent_event_id",
            "permission_mutated",
            "phase",
            "promotion_mutated",
            "schema_version",
            "sequence",
            "state_after_hash",
            "state_before_hash",
            "state_patch",
            "truth_mutated",
        }
        replayed_state = copy.deepcopy(raw_receipt["initial_state"])
        parent_event_id: str | None = None
        for sequence, (event, (phase, refs)) in enumerate(zip(events, phase_refs)):
            if (
                type(event) is not dict
                or set(event) != event_fields
                or event.get("schema_version")
                != "atanor.cognitive_core.m1.v1"
                or event.get("contract_type") != "CycleEvent"
                or event.get("observer_only") is not True
                or any(
                    event.get(name) is not False
                    for name in (
                        "authoritative",
                        "permission_mutated",
                        "promotion_mutated",
                        "truth_mutated",
                    )
                )
                or event.get("cycle_id") != expected_cycle_id
                or event.get("sequence") != sequence
                or event.get("parent_event_id") != parent_event_id
                or event.get("phase") != phase
                or event.get("entity_occurrence_ids") != refs
                or not set(refs) <= seen_occurrence_ids
                or event.get("state_before_hash")
                != canonical_digest(replayed_state)
            ):
                return False
            replayed_state = _apply_state_patch_independently(
                replayed_state,
                event.get("state_patch"),
            )
            if event.get("state_after_hash") != canonical_digest(replayed_state):
                return False
            event_payload = {
                "cycle_id": expected_cycle_id,
                "entity_occurrence_ids": refs,
                "metadata": event["metadata"],
                "parent_event_id": parent_event_id,
                "phase": phase,
                "sequence": sequence,
                "state_after_hash": event["state_after_hash"],
                "state_before_hash": event["state_before_hash"],
                "state_patch": event["state_patch"],
            }
            expected_event_id = canonical_id("cevent", event_payload)[0]
            if event.get("event_id") != expected_event_id:
                return False
            parent_event_id = expected_event_id
        expected_state.update(
            {
                "status": status,
                "stop_reason": semantic["stop_reason"],
                "success": semantic["success"],
            }
        )
        receipt_identity = {
            "declared_effects": raw_receipt["declared_effects"],
            "entities": entities,
            "events": events,
            "initial_state": raw_receipt["initial_state"],
            "input_hash": raw_receipt["input_hash"],
            "limitations": raw_receipt["limitations"],
            "output_hash": raw_receipt["output_hash"],
            "request_cycle": request,
            "selected_route": raw_receipt["selected_route"],
            "status": raw_receipt["status"],
            "terminal_state_hash": raw_receipt["terminal_state_hash"],
        }
        return (
            replayed_state == expected_state
            and raw_receipt["terminal_state_hash"]
            == canonical_digest(replayed_state)
            and raw_receipt["receipt_id"]
            == canonical_id("cycle", receipt_identity)[0]
            and replayed_state.get("step_count") == len(steps)
            and replayed_state.get("stop_reason") == semantic["stop_reason"]
            and replayed_state.get("success") is semantic["success"]
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _self_attestation_controls(
    episode: Mapping[str, Any],
    *,
    mechanic: HiddenMechanic,
    environment_seed: int,
    policy_seed: int,
    step_budget: int,
    memory_before: Mapping[str, Any] | None,
) -> bool:
    trace = episode["trace"]
    semantic = trace.get("semantic_trace")
    steps = semantic.get("steps") if type(semantic) is dict else None
    if type(steps) is not list or not steps:
        return False
    lease_digest = episode["parent_run_lease"]["lease_id_sha256"]

    forged_decision = copy.deepcopy(dict(episode))
    forged_semantic = forged_decision["trace"]["semantic_trace"]
    forged_semantic["steps"][0]["decision_receipt"]["proposed_action"][
        "action_id"
    ] = "invented-action"
    forged_decision["trace"]["semantic_trace_digest"] = canonical_digest(
        forged_semantic
    )
    decision_check = _cross_check_candidate_trace(
        forged_decision,
        environment_log=episode["environment_call_log"],
        expected_goal_ref=mechanic.goal_ref,
        expected_environment_seed=environment_seed,
        expected_policy_seed=policy_seed,
        expected_step_budget=step_budget,
        expected_memory_before=memory_before,
        expected_lease_digest=lease_digest,
    )

    forged_snapshot = copy.deepcopy(dict(episode))
    forged_semantic = forged_snapshot["trace"]["semantic_trace"]
    forged_semantic["steps"][0]["world_snapshot"]["metadata"][
        "valid_actions_digest"
    ] = "0" * 64
    forged_snapshot["trace"]["semantic_trace_digest"] = canonical_digest(
        forged_semantic
    )
    snapshot_check = _cross_check_candidate_trace(
        forged_snapshot,
        environment_log=episode["environment_call_log"],
        expected_goal_ref=mechanic.goal_ref,
        expected_environment_seed=environment_seed,
        expected_policy_seed=policy_seed,
        expected_step_budget=step_budget,
        expected_memory_before=memory_before,
        expected_lease_digest=lease_digest,
    )

    forged_authority = copy.deepcopy(dict(episode))
    forged_authority["operational_authority"][0]["operational_evidence"][
        "lease_id_sha256"
    ] = "0" * 64
    authority_check = _cross_check_candidate_trace(
        forged_authority,
        environment_log=episode["environment_call_log"],
        expected_goal_ref=mechanic.goal_ref,
        expected_environment_seed=environment_seed,
        expected_policy_seed=policy_seed,
        expected_step_budget=step_budget,
        expected_memory_before=memory_before,
        expected_lease_digest=lease_digest,
    )
    return (
        not decision_check["passed"]
        and not snapshot_check["passed"]
        and not authority_check["passed"]
    )


def verify_raw_evidence(
    raw: Mapping[str, Any],
    *,
    preregistration: Mapping[str, Any],
    preregistration_digest: str,
    seed_manifest_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    run_lease_plan_binding: Mapping[str, Any],
    run_lease_entries: Sequence[Mapping[str, Any]],
    mechanics: Sequence[HiddenMechanic],
    candidate_root: Path,
    attempt_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive hard gates, metrics, and verdict only from raw evidence."""

    _validate_preregistration(preregistration)
    if type(raw) is not dict or frozenset(raw) != _RAW_EVIDENCE_FIELDS:
        raise EvaluationContractError("raw evidence fields mismatch")
    if (
        raw.get("schema_version") != RAW_EVIDENCE_SCHEMA
        or raw.get("aggregate_metrics") is not None
        or raw.get("verdict") is not None
        or raw.get("preregistration_binding")
        != {
            "path": "data/eval/gwip_mechanism_prereg_v1.json",
            "raw_sha256": preregistration_digest,
        }
        or raw.get("seed_manifest_binding") != dict(seed_manifest_binding)
        or raw.get("source_binding") != dict(source_binding)
        or raw.get("run_lease_plan_binding") != dict(run_lease_plan_binding)
        or raw.get("attempt_binding") != dict(attempt_binding)
    ):
        raise EvaluationContractError("raw evidence independent binding mismatch")
    expected_attempt_binding = _expected_attempt_binding(
        seed_manifest_binding=seed_manifest_binding,
        source_binding=source_binding,
        run_lease_plan_binding=run_lease_plan_binding,
    )
    if dict(attempt_binding) != expected_attempt_binding:
        raise EvaluationContractError(
            "raw evidence attempt is not the frozen designated local claim"
        )
    expected_cohort = {
        "private_cohort_sha256": private_cohort_digest(mechanics),
        "mechanic_count": preregistration["mechanic_count"],
        "candidate_episode_count": preregistration["candidate_episode_count"],
    }
    if raw.get("cohort_binding") != expected_cohort:
        raise EvaluationContractError("raw evidence cohort binding mismatch")
    expected_order = [
        {
            "mechanic_index": index,
            "arm_order": list(counterbalanced_arm_order(index)),
        }
        for index in range(preregistration["mechanic_count"])
    ]
    if raw.get("execution_order") != expected_order:
        raise EvaluationContractError("raw evidence counterbalance order mismatch")
    candidate_episodes = raw.get("candidate_episodes")
    reactive_episodes = raw.get("reactive_episodes")
    random_episodes = raw.get("random_episodes")
    if (
        type(candidate_episodes) is not list
        or len(candidate_episodes) != preregistration["candidate_episode_count"]
        or type(reactive_episodes) is not list
        or len(reactive_episodes) != preregistration["candidate_episode_count"]
        or type(random_episodes) is not list
        or len(random_episodes)
        != preregistration["candidate_episode_count"]
        * len(preregistration["random_policy_seeds"])
        or len(run_lease_entries) != len(candidate_episodes)
    ):
        raise EvaluationContractError("raw evidence episode census mismatch")

    source_paths = [
        Path(candidate_root) / relative
        for relative in CANDIDATE_SOURCE_PATHS
    ]
    source_audit = audit_candidate_sources(
        source_paths,
        repository_root=Path(candidate_root),
    )
    if raw.get("source_audit") != source_audit:
        raise EvaluationContractError("raw source audit was not independently reproduced")
    actual_candidate_tree = bind_source_tree(candidate_root)
    actual_candidate_paths = {
        item["path"] for item in actual_candidate_tree["files"]
    }
    trusted_parent_records = _trusted_parent_source_records(
        actual_candidate_tree
    )
    trusted_parent_source_sha256 = canonical_digest(trusted_parent_records)
    evaluator_files = source_binding.get("evaluator", {}).get("files")
    evaluator_file_hashes = {
        item.get("path"): item.get("sha256")
        for item in evaluator_files
        if type(item) is dict
    } if type(evaluator_files) is list else {}
    if any(
        evaluator_file_hashes.get(item["path"]) != item["sha256"]
        for item in trusted_parent_records
    ):
        raise EvaluationContractError(
            "trusted parent authority is not evaluator-source bound"
        )

    mechanics_by_index = {item.evaluator_index: item for item in mechanics}
    empty_memory = {
        "action_sets": [],
        "attempts": [],
        "concepts_by_state": [],
        "schema_version": "atanor.gwip-policy-memory.v1",
        "target_state_digest": None,
        "transitions": [],
    }
    expected_memory: Mapping[str, Any] | None = None
    call_order_ok = True
    budget_ok = verify_step_budget_pre_mutation_denial(
        mechanics[0],
        episode_index=0,
        environment_seed=0,
        step_budget=preregistration["step_budget"],
    )
    run_lease_ok = True
    single_use_ok = True
    determinism_ok = True
    structural_ok = True
    reexecution_ok = True
    lineage_ok = True
    runtime_import_ok = True
    isolation_ok = True
    contract_replay_ok = True
    first_control_ok = False
    candidate_rows: list[dict[str, Any]] = []

    from packages.autonomy_envelope.run_lease import (  # noqa: PLC0415
        GENERAL_INTERACTION_RUNNER_ID,
        RunLeaseBoundaryConfig,
        RunLeaseStore,
    )

    for ordinal, (episode, lease_entry) in enumerate(
        zip(candidate_episodes, run_lease_entries)
    ):
        mechanic_index = ordinal // preregistration["episodes_per_mechanic"]
        episode_index = ordinal % preregistration["episodes_per_mechanic"]
        if episode_index == 0:
            expected_memory = None
        if (
            type(episode) is not dict
            or frozenset(episode) != _CANDIDATE_EPISODE_FIELDS
            or episode.get("schema_version")
            != "atanor.gwip-candidate-episode-evidence.v1"
            or episode.get("aggregate_metrics") is not None
            or episode.get("verdict") is not None
        ):
            raise EvaluationContractError("raw candidate episode fields mismatch")
        scoring = episode["scoring"]
        if (
            scoring.get("mechanic_index") != mechanic_index
            or scoring.get("episode_index") != episode_index
        ):
            raise EvaluationContractError("raw candidate episode order mismatch")
        reconstructed_scoring = _candidate_trace_scoring_projection(
            episode["environment_call_log"],
            policy="candidate",
            mechanic_index=mechanic_index,
            episode_index=episode_index,
            random_seed=None,
        )
        if scoring != reconstructed_scoring:
            raise EvaluationContractError(
                "candidate scoring is not its evaluator call-log projection"
            )
        expected_before = empty_memory if expected_memory is None else expected_memory
        if episode.get("memory_before_sha256") != canonical_digest(expected_before):
            raise EvaluationContractError("candidate mechanic memory chain broken")
        if episode.get("memory_after_sha256") != canonical_digest(
            episode.get("memory_after")
        ):
            raise EvaluationContractError("candidate memory-after digest mismatch")
        parent_lease = episode.get("parent_run_lease")
        if (
            type(parent_lease) is not dict
            or frozenset(parent_lease) != _PARENT_RUN_LEASE_FIELDS
            or parent_lease.get("trusted_parent_source_sha256")
            != trusted_parent_source_sha256
            or not _SHA256.fullmatch(
                str(parent_lease.get("active_state_raw_sha256"))
            )
            or not _SHA256.fullmatch(
                str(parent_lease.get("nonce_claim_raw_sha256"))
            )
        ):
            raise EvaluationContractError(
                "raw candidate parent RunLease evidence invalid"
            )
        lease_digest = parent_lease.get("lease_id_sha256")
        cross_check = _cross_check_candidate_trace(
            episode,
            environment_log=episode["environment_call_log"],
            expected_goal_ref=mechanics_by_index[mechanic_index].goal_ref,
            expected_environment_seed=episode_index,
            expected_policy_seed=CANDIDATE_POLICY_SEED,
            expected_step_budget=preregistration["step_budget"],
            expected_memory_before=expected_memory,
            expected_lease_digest=lease_digest,
        )
        lineage_ok = lineage_ok and cross_check["passed"]
        call_order_ok = call_order_ok and audit_environment_call_order(
            episode["environment_call_log"],
            step_budget=preregistration["step_budget"],
        )["passed"]
        budget_ok = budget_ok and len(scoring["steps"]) <= preregistration["step_budget"]
        reexecution_ok = (
            reexecution_ok
            and episode["environment_call_log"] == episode["replay_call_log"]
        )
        logs = episode.get("determinism_call_logs")
        determinism_ok = (
            determinism_ok
            and type(logs) is dict
            and logs.get("a") == episode["environment_call_log"]
            and logs.get("b") == episode["environment_call_log"]
            and episode["determinism"].get("passed") is True
            and episode["determinism"].get("memory_after_a_sha256")
            == episode["memory_after_sha256"]
            and episode["determinism"].get("memory_after_b_sha256")
            == episode["memory_after_sha256"]
        )
        structural = episode.get("structural_verification")
        structural_ok = (
            structural_ok
            and type(structural) is dict
            and structural.get("structural_replay_ok") is True
            and structural.get("receipt_cross_check_ok") is True
            and structural.get("environment_reexecution_ok") is True
        )
        contract_replay_ok = contract_replay_ok and _independent_contract_replay(
            episode["trace"]
        )
        closure = episode.get("module_closure")
        source_modules = (
            closure.get("source_modules", [])
            if type(closure) is dict
            else []
        )
        names = [
            item.get("module")
            for item in source_modules
            if type(item) is dict
        ]
        closure_schema_ok = (
            type(closure) is dict
            and frozenset(closure)
            == {
                "source_modules",
                "source_modules_sha256",
                "outside_candidate_root_modules",
                "passed",
            }
            and type(source_modules) is list
            and all(
                type(item) is dict
                and frozenset(item) == {"module", "path"}
                and type(item["module"]) is str
                and item["module"].startswith("packages")
                and item["path"] in actual_candidate_paths
                for item in source_modules
            )
            and source_modules
            == sorted(source_modules, key=lambda item: item["module"])
            and len(names) == len(set(names))
            and closure.get("source_modules_sha256")
            == canonical_digest(source_modules)
        )
        runtime_import_ok = (
            runtime_import_ok
            and closure_schema_ok
            and closure.get("passed") is True
            and not closure.get("outside_candidate_root_modules")
            and not any(_module_is_denied(str(name)) for name in names)
        )
        guard = episode.get("isolation")
        probes = guard.get("probes", {}) if type(guard) is dict else {}
        counts = (
            guard.get("blocked_event_counts", {})
            if type(guard) is dict
            else {}
        )
        guard_schema_ok = (
            type(guard) is dict
            and frozenset(guard)
            == {
                "schema_version",
                "kind",
                "probes",
                "blocked_event_counts",
                "passed",
            }
            and guard.get("schema_version")
            == "atanor.gwip-worker-guard.v1"
            and guard.get("kind")
            == "python_audit_guard_not_os_sandbox"
            and type(probes) is dict
            and frozenset(probes)
            == {
                "evaluator_main_hidden",
                "external_network_blocked",
                "udp_sendto_blocked",
                "child_process_blocked",
                "native_child_process_blocked",
                "native_library_loading_blocked",
                "native_file_access_blocked",
                "nonledger_write_blocked",
                "evaluator_workspace_read_blocked",
                "external_filesystem_enumeration_blocked",
            }
            and all(value is True for value in probes.values())
            and type(counts) is dict
            and frozenset(counts)
            == {"network", "child", "write", "workspace_read"}
            and all(type(value) is int and value >= 1 for value in counts.values())
        )
        isolation_ok = (
            isolation_ok
            and guard_schema_ok
            and guard.get("passed") is True
            and episode.get("source_tree_before_sha256")
            == actual_candidate_tree["tree_sha256"]
            and episode.get("source_tree_after_sha256")
            == actual_candidate_tree["tree_sha256"]
        )
        run_lease_ok = (
            run_lease_ok
            and parent_lease.get("passed") is True
            and parent_lease.get("authorization_count") == len(scoring["steps"])
            and parent_lease.get("final_counters")
            == {
                **_ZERO_COUNTERS,
                "cycles": len(scoring["steps"]),
                "actions": len(scoring["steps"]),
            }
        )
        single_use_ok = (
            single_use_ok
            and parent_lease.get("single_use_replay_reason") == "run_lease_replay"
        )
        validated_entry = _validate_run_lease_entry(
            lease_entry,
            ordinal=ordinal,
            mechanic_index=mechanic_index,
            episode_index=episode_index,
        )
        runner = verify_finished_run_lease_ledger(
            validated_entry,
            ordinal=ordinal,
            mechanic_index=mechanic_index,
            episode_index=episode_index,
            repository_root=REPO,
        )
        expected_parent_authorizations = [
            _authorization_witness_from_parent_response(
                {
                    "action_id": step["selected_action"],
                    "step_index": index,
                    "granted": True,
                    "reason": "run_lease_action_authorized",
                    "authority_kind": "externally_signed_run_lease",
                    "operational_evidence": {
                        "action_class": "interaction.step",
                        "counters": {
                            **_ZERO_COUNTERS,
                            "cycles": index + 1,
                            "actions": index + 1,
                        },
                        "lease_id_sha256": lease_digest,
                        "runner_id": GENERAL_INTERACTION_RUNNER_ID,
                    },
                }
            )
            for index, step in enumerate(scoring["steps"])
        ]
        expected_parent_finish = {
            "finished": True,
            "reason": "run_lease_finished",
            "lease_id": runner.get("lease_id"),
            "runner_id": GENERAL_INTERACTION_RUNNER_ID,
        }
        lineage_steps = episode["trace"].get("lineage_steps")
        parent_transcript_ok = (
            episode["operational_authority"]
            == expected_parent_authorizations
            and type(lineage_steps) is list
            and [
                item.get("authorization")
                for item in lineage_steps
                if type(item) is dict
            ]
            == expected_parent_authorizations
            and episode["trace"].get("authority_finish")
            == expected_parent_finish
            and parent_lease.get("authority_transcript_sha256")
            == canonical_digest(
                {
                    "authorizations": expected_parent_authorizations,
                    "finish": expected_parent_finish,
                }
            )
        )
        run_lease_ok = (
            run_lease_ok
            and parent_transcript_ok
            and runner.get("state_ok") is True
            and canonical_digest(runner.get("lease_id")) == lease_digest
            and runner.get("authorization_count") == len(scoring["steps"])
            and runner.get("counters") == parent_lease["final_counters"]
            and runner.get("finish_reason") == scoring["stop_reason"]
            and runner.get("active_state_raw_sha256")
            == parent_lease["active_state_raw_sha256"]
            and runner.get("nonce_claim_raw_sha256")
            == parent_lease["nonce_claim_raw_sha256"]
        )
        if ordinal == 0:
            first_control_ok = _self_attestation_controls(
                episode,
                mechanic=mechanics_by_index[mechanic_index],
                environment_seed=episode_index,
                policy_seed=CANDIDATE_POLICY_SEED,
                step_budget=preregistration["step_budget"],
                memory_before=expected_memory,
            )
        expected_memory = episode["memory_after"]
        candidate_rows.append(scoring)

    expected_reactive_episodes: list[dict[str, Any]] = []
    expected_random_episodes: list[dict[str, Any]] = []
    for mechanic in mechanics:
        for episode_index in range(
            preregistration["episodes_per_mechanic"]
        ):
            expected_reactive_episodes.append(
                run_control_episode(
                    mechanic=mechanic,
                    episode_index=episode_index,
                    policy=ReactivePolicy(),
                    policy_label="reactive",
                    environment_seed=episode_index,
                    random_seed=None,
                    step_budget=preregistration["step_budget"],
                )
            )
        for seed in preregistration["random_policy_seeds"]:
            random_policy = RandomPolicy(
                policy_seed=seed,
                mechanic_binding=mechanic.private_ref,
            )
            for episode_index in range(
                preregistration["episodes_per_mechanic"]
            ):
                expected_random_episodes.append(
                    run_control_episode(
                        mechanic=mechanic,
                        episode_index=episode_index,
                        policy=random_policy,
                        policy_label="random",
                        environment_seed=episode_index,
                        random_seed=seed,
                        step_budget=preregistration["step_budget"],
                    )
                )
    if list(reactive_episodes) != expected_reactive_episodes:
        raise EvaluationContractError(
            "reactive evidence differs from independent frozen-policy replay"
        )
    if list(random_episodes) != expected_random_episodes:
        raise EvaluationContractError(
            "random evidence differs from independent frozen-policy replay"
        )

    control_rows: list[dict[str, Any]] = []
    for wrapper, label in (
        (reactive_episodes, "reactive"),
        (random_episodes, "random"),
    ):
        for item in wrapper:
            if (
                type(item) is not dict
                or frozenset(item) != _CONTROL_EPISODE_FIELDS
                or item.get("schema_version")
                != "atanor.gwip-control-episode-evidence.v1"
                or item.get("aggregate_metrics") is not None
                or item.get("verdict") is not None
                or item.get("scoring", {}).get("policy") != label
            ):
                raise EvaluationContractError(f"raw {label} episode fields mismatch")
            scoring = item["scoring"]
            reconstructed_scoring = _candidate_trace_scoring_projection(
                item["environment_call_log"],
                policy=label,
                mechanic_index=scoring.get("mechanic_index"),
                episode_index=scoring.get("episode_index"),
                random_seed=scoring.get("random_seed"),
            )
            if scoring != reconstructed_scoring:
                raise EvaluationContractError(
                    f"{label} scoring is not its evaluator call-log projection"
                )
            control_rows.append(scoring)
            call_order_ok = call_order_ok and audit_environment_call_order(
                item["environment_call_log"],
                step_budget=preregistration["step_budget"],
            )["passed"]

    reactive_rows = [row for row in control_rows if row["policy"] == "reactive"]
    random_rows = [row for row in control_rows if row["policy"] == "random"]
    derived = derive_metrics_from_raw_episodes(
        candidate_rows=candidate_rows,
        reactive_rows=reactive_rows,
        random_rows=random_rows,
        mechanics=mechanics,
        preregistration=preregistration,
    )
    hard_gates = {
        "call_order_and_stop": call_order_ok,
        "step_budget_and_pre_mutation_denial": budget_ok,
        "run_lease_direct_authority": run_lease_ok,
        "run_lease_single_use_and_replay_rejection": single_use_ok,
        "semantic_reexecution_determinism": determinism_ok,
        "structural_cycle_replay": structural_ok and contract_replay_ok,
        "fresh_environment_reexecution": reexecution_ok,
        "complete_lineage": lineage_ok,
        "adversarial_self_attestation_rejection": first_control_ok,
        "candidate_domain_neutrality": source_audit["passed"],
        "candidate_runtime_import_closure": runtime_import_ok,
        "candidate_fixed_source_guard_controls": isolation_ok,
    }
    if frozenset(hard_gates) != frozenset(REQUIRED_HARD_GATES):
        raise AssertionError("raw verifier hard-gate implementation drift")
    hard_passed = all(hard_gates.values())
    verdict = (
        "MECHANISM_RED"
        if not hard_passed
        else "MECHANISM_GREEN"
        if derived["efficiency_gate"]["passed"]
        else "NO_GO"
    )
    return {
        "hard_gates": hard_gates,
        "hard_gates_passed": hard_passed,
        "derived": derived,
        "verdict": verdict,
        "capability_claim": False,
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
    }


def _aggregate_from_dict(value: Mapping[str, Any], label: str) -> PolicyAggregate:
    if type(value) is not dict or frozenset(value) != {
        "mechanic_swae",
        "mean_swae",
        "success_rate",
        "episode_count",
    }:
        raise EvaluationContractError(f"{label} aggregate fields mismatch")
    return PolicyAggregate(
        mechanic_swae=tuple(value["mechanic_swae"]),
        mean_swae=value["mean_swae"],
        success_rate=value["success_rate"],
        episode_count=value["episode_count"],
    )


def receipt_checksum(receipt: Mapping[str, Any]) -> str:
    payload = {
        key: copy.deepcopy(value)
        for key, value in receipt.items()
        if key != "checksum_sha256"
    }
    return canonical_digest(payload)


def _representative_from_raw(
    episode: Mapping[str, Any],
    mechanic: HiddenMechanic,
) -> EpisodeTrace:
    scoring = episode["scoring"]
    semantic = episode["trace"]["semantic_trace"]
    goal_id = semantic["goal"]["contract_id"]
    steps: list[TraceStep] = []
    for raw_step, operational in zip(
        semantic["steps"],
        episode["operational_authority"],
    ):
        steps.append(
            TraceStep(
                step_index=raw_step["step_index"],
                observation=raw_step["pre_observation"],
                valid_actions=tuple(
                    item["action_id"] for item in raw_step["valid_actions"]
                ),
                selected_action=raw_step["selected_action"],
                authority_reason=raw_step["authorization"]["reason"],
                authority_binding=operational["witness_id"],
                post_observation=raw_step["post_observation"],
                learned_edge_ref=raw_step["learned_edge_ref"],
                world_snapshot_ref=raw_step["world_snapshot"]["contract_id"],
                goal_ir_ref=goal_id,
                proposal_ref=raw_step["proposal"]["proposal_id"],
                decision_receipt_ref=raw_step["decision_receipt"]["contract_id"],
            )
        )
    return EpisodeTrace(
        policy="candidate",
        evaluator_mechanic_index=scoring["mechanic_index"],
        episode_index=scoring["episode_index"],
        goal_ref=mechanic.goal_ref,
        initial_observation=scoring["initial_observation"],
        steps=tuple(steps),
        stop_reason=scoring["stop_reason"],
        success=scoring["success"],
        optimal_steps=mechanic.episodes[scoring["episode_index"]].optimal_steps,
        semantic_trace_digest=episode["trace"]["semantic_trace_digest"],
    )


def build_one_shot_receipt(
    *,
    raw_evidence: Mapping[str, Any],
    raw_evidence_sha256: str,
    preregistration: Mapping[str, Any],
    preregistration_digest: str,
    seed_manifest_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    run_lease_plan_binding: Mapping[str, Any],
    run_lease_entries: Sequence[Mapping[str, Any]],
    mechanics: Sequence[HiddenMechanic],
    candidate_root: Path,
    attempt_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Build derived receipt only after replaying raw evidence independently."""

    if not _SHA256.fullmatch(raw_evidence_sha256):
        raise EvaluationContractError("raw evidence byte digest invalid")
    verified = verify_raw_evidence(
        raw_evidence,
        preregistration=preregistration,
        preregistration_digest=preregistration_digest,
        seed_manifest_binding=seed_manifest_binding,
        source_binding=source_binding,
        run_lease_plan_binding=run_lease_plan_binding,
        run_lease_entries=run_lease_entries,
        mechanics=mechanics,
        candidate_root=candidate_root,
        attempt_binding=attempt_binding,
    )
    representative = _representative_from_raw(
        raw_evidence["candidate_episodes"][0],
        mechanics[0],
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "raw_evidence_binding": {
            "schema_version": RAW_EVIDENCE_SCHEMA,
            "raw_sha256": raw_evidence_sha256,
            "canonical_sha256": canonical_digest(raw_evidence),
        },
        "preregistration_binding": copy.deepcopy(
            raw_evidence["preregistration_binding"]
        ),
        "seed_manifest_binding": copy.deepcopy(
            raw_evidence["seed_manifest_binding"]
        ),
        "source_binding": copy.deepcopy(raw_evidence["source_binding"]),
        "cohort_binding": copy.deepcopy(raw_evidence["cohort_binding"]),
        "hard_gates": verified["hard_gates"],
        "hard_gates_passed": verified["hard_gates_passed"],
        "policy_metrics": verified["derived"]["policy_metrics"],
        "efficiency_gate": verified["derived"]["efficiency_gate"],
        "representative_episode": representative.to_dict(),
        "representative_episode_text": render_episode(representative),
        "verdict": verified["verdict"],
        "capability_claim": False,
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
        "limitations": [
            "controlled mechanism discriminator only",
            "not an ARC or public benchmark result",
            "not E5 capability evidence",
            "production default remains unchanged",
            "reviewed fixed-source Python guard, not an OS sandbox",
            (
                "RunLease non-action resource counters are declared fixed "
                "costs, not OS observations"
            ),
            (
                "designated local attempt only; global uniqueness is not "
                "externally notarized"
            ),
        ],
    }
    receipt["checksum_sha256"] = receipt_checksum(receipt)
    return receipt


_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "raw_evidence_binding",
        "preregistration_binding",
        "seed_manifest_binding",
        "source_binding",
        "cohort_binding",
        "hard_gates",
        "hard_gates_passed",
        "policy_metrics",
        "efficiency_gate",
        "representative_episode",
        "representative_episode_text",
        "verdict",
        "capability_claim",
        "public_benchmark_claim",
        "production_activation_authorized",
        "limitations",
        "checksum_sha256",
    }
)


def verify_one_shot_receipt(
    value: Mapping[str, Any],
    *,
    raw_evidence: Mapping[str, Any],
    raw_evidence_sha256: str,
    preregistration: Mapping[str, Any],
    preregistration_digest: str,
    seed_manifest_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    run_lease_plan_binding: Mapping[str, Any],
    run_lease_entries: Sequence[Mapping[str, Any]],
    mechanics: Sequence[HiddenMechanic],
    candidate_root: Path,
    attempt_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject resealed receipts by rebuilding every derived field from raw."""

    try:
        expected = build_one_shot_receipt(
            raw_evidence=raw_evidence,
            raw_evidence_sha256=raw_evidence_sha256,
            preregistration=preregistration,
            preregistration_digest=preregistration_digest,
            seed_manifest_binding=seed_manifest_binding,
            source_binding=source_binding,
            run_lease_plan_binding=run_lease_plan_binding,
            run_lease_entries=run_lease_entries,
            mechanics=mechanics,
            candidate_root=candidate_root,
            attempt_binding=attempt_binding,
        )
    except (EvaluationContractError, OSError, KeyError, TypeError, ValueError) as exc:
        return {"valid": False, "verdict": None, "findings": [str(exc)]}
    if type(value) is not dict or frozenset(value) != _RECEIPT_FIELDS:
        return {"valid": False, "verdict": None, "findings": ["receipt fields mismatch"]}
    if dict(value) != expected:
        return {
            "valid": False,
            "verdict": None,
            "findings": ["receipt differs from raw-evidence recomputation"],
        }
    return {"valid": True, "verdict": expected["verdict"], "findings": []}


def write_once_json(path: Path, value: Mapping[str, Any]) -> None:
    """Exclusive-create one designated local artifact; never overwrite."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def verify_source_precedes_seed_manifest(
    candidate_commit: str,
    seed_manifest_commit: str,
    *,
    repository_root: Path = REPO,
) -> bool:
    """Require a strict git-ancestry edge from candidate seal to seed manifest."""

    if (
        not _GIT_COMMIT.fullmatch(candidate_commit)
        or not _GIT_COMMIT.fullmatch(seed_manifest_commit)
        or candidate_commit == seed_manifest_commit
    ):
        return False
    completed = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            candidate_commit,
            seed_manifest_commit,
        ],
        cwd=Path(repository_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    return completed.returncode == 0


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


def _expected_attempt_payload(
    *,
    seed_manifest_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    run_lease_plan_binding: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": ATTEMPT_SCHEMA,
        "seed_manifest_commit": seed_manifest_binding["commit"],
        "seed_manifest_raw_sha256": seed_manifest_binding["raw_sha256"],
        "candidate_source_sha256": source_binding["candidate"][
            "source_digest"
        ],
        "evaluator_source_sha256": source_binding["evaluator"][
            "source_digest"
        ],
        "run_lease_plan_raw_sha256": run_lease_plan_binding["raw_sha256"],
        "designated_local_attempt_claimed": True,
    }


def _expected_attempt_binding(
    *,
    seed_manifest_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    run_lease_plan_binding: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _expected_attempt_payload(
        seed_manifest_binding=seed_manifest_binding,
        source_binding=source_binding,
        run_lease_plan_binding=run_lease_plan_binding,
    )
    return {
        "path": FINAL_ATTEMPT.resolve().relative_to(REPO.resolve()).as_posix(),
        "raw_sha256": hashlib.sha256(_json_artifact_bytes(payload)).hexdigest(),
        "payload": payload,
    }


def _claim_final_attempt(
    *,
    seed_manifest_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    run_lease_plan_binding: Mapping[str, Any],
    path: Path = FINAL_ATTEMPT,
) -> dict[str, Any]:
    if Path(path).resolve() != FINAL_ATTEMPT.resolve():
        raise EvaluationContractError("final attempt path is not the frozen path")
    expected = _expected_attempt_binding(
        seed_manifest_binding=seed_manifest_binding,
        source_binding=source_binding,
        run_lease_plan_binding=run_lease_plan_binding,
    )
    payload = expected["payload"]
    write_once_json(path, payload)
    raw = Path(path).read_bytes()
    if raw != _json_artifact_bytes(payload):
        raise EvaluationContractError("final attempt bytes differ from frozen encoding")
    if hashlib.sha256(raw).hexdigest() != expected["raw_sha256"]:
        raise EvaluationContractError("final attempt binding mismatch")
    return expected


def run_final_once(
    *,
    seed_manifest_commit: str,
    run_lease_plan_path: Path,
    attempt_path: Path = FINAL_ATTEMPT,
    raw_evidence_path: Path = FINAL_RAW_EVIDENCE,
    receipt_path: Path = FINAL_RECEIPT,
) -> dict[str, Any]:
    """Run the designated sealed cohort; no global-notary claim is made."""

    if (
        Path(attempt_path).resolve() != FINAL_ATTEMPT.resolve()
        or Path(raw_evidence_path).resolve() != FINAL_RAW_EVIDENCE.resolve()
        or Path(receipt_path).resolve() != FINAL_RECEIPT.resolve()
    ):
        raise EvaluationContractError("run-final artifact paths are frozen")
    for path in (attempt_path, raw_evidence_path, receipt_path):
        if Path(path).exists():
            raise EvaluationContractError(
                f"designated local artifact already exists: {path}"
            )
    preregistration, preregistration_digest = load_preregistration()
    manifest, seed_binding = load_and_verify_seed_manifest(
        REPO / SEED_MANIFEST_RELATIVE_PATH,
        seed_manifest_commit=seed_manifest_commit,
    )
    lease_entries, plan_binding = load_run_lease_plan(
        run_lease_plan_path,
        preregistration=preregistration,
    )
    plan_binding = {
        **plan_binding,
        "verified_seed_source_binding": verify_run_lease_plan_seed_binding(
            lease_entries,
            seed_manifest_binding=seed_binding,
        ),
    }
    source_binding = {
        "candidate": seed_binding["candidate"],
        "evaluator": seed_binding["evaluator"],
    }
    with sealed_candidate_source(manifest["candidate_commit"]) as (
        candidate_root,
        candidate_tree_before,
    ):
        source_audit = audit_candidate_sources(
            [
                candidate_root / relative
                for relative in CANDIDATE_SOURCE_PATHS
            ],
            repository_root=candidate_root,
        )
        if not source_audit["passed"]:
            raise EvaluationContractError("sealed candidate domain audit failed")
        attempt_binding = _claim_final_attempt(
            seed_manifest_binding=seed_binding,
            source_binding=source_binding,
            run_lease_plan_binding=plan_binding,
            path=attempt_path,
        )
        mechanics = generate_hidden_mechanics(
            preregistration,
            generator_seed=manifest["generator_seed"],
            generator_nonce=manifest["generator_nonce"],
        )
        evaluator_hashes = {
            item["path"]: item["sha256"]
            for item in source_binding["evaluator"]["files"]
        }
        expected_worker_sha256 = evaluator_hashes[
            "scripts/gwip_mechanism_eval.py"
        ]
        candidate_episodes: list[dict[str, Any]] = []
        reactive_episodes: list[dict[str, Any]] = []
        random_episodes: list[dict[str, Any]] = []
        execution_order: list[dict[str, Any]] = []
        for mechanic in mechanics:
            arm_order = counterbalanced_arm_order(mechanic.evaluator_index)
            execution_order.append(
                {
                    "mechanic_index": mechanic.evaluator_index,
                    "arm_order": list(arm_order),
                }
            )
            for arm in arm_order:
                if arm == "candidate":
                    memory: Mapping[str, Any] | None = None
                    for episode_index in range(
                        preregistration["episodes_per_mechanic"]
                    ):
                        ordinal = (
                            mechanic.evaluator_index
                            * preregistration["episodes_per_mechanic"]
                            + episode_index
                        )
                        evidence = run_candidate_episode_worker(
                            mechanic=mechanic,
                            episode_index=episode_index,
                            candidate_root=candidate_root,
                            candidate_tree_before=candidate_tree_before,
                            lease_entry=lease_entries[ordinal],
                            policy_memory=memory,
                            environment_seed=episode_index,
                            policy_seed=manifest["candidate_policy_seed"],
                            step_budget=preregistration["step_budget"],
                            expected_worker_sha256=expected_worker_sha256,
                        )
                        candidate_episodes.append(evidence)
                        memory = evidence["memory_after"]
                elif arm == "reactive":
                    for episode_index in range(
                        preregistration["episodes_per_mechanic"]
                    ):
                        reactive_episodes.append(
                            run_control_episode(
                                mechanic=mechanic,
                                episode_index=episode_index,
                                policy=ReactivePolicy(),
                                policy_label="reactive",
                                environment_seed=episode_index,
                                random_seed=None,
                                step_budget=preregistration["step_budget"],
                            )
                        )
                elif arm == "random":
                    for seed in preregistration["random_policy_seeds"]:
                        policy = RandomPolicy(
                            policy_seed=seed,
                            mechanic_binding=mechanic.private_ref,
                        )
                        for episode_index in range(
                            preregistration["episodes_per_mechanic"]
                        ):
                            random_episodes.append(
                                run_control_episode(
                                    mechanic=mechanic,
                                    episode_index=episode_index,
                                    policy=policy,
                                    policy_label="random",
                                    environment_seed=episode_index,
                                    random_seed=seed,
                                    step_budget=preregistration["step_budget"],
                                )
                            )
                else:
                    raise AssertionError("unknown counterbalanced arm")
        if (
            not _git_working_paths_unchanged(
                manifest["candidate_commit"],
                ("packages",),
            )
            or bind_working_paths(EVALUATOR_SOURCE_PATHS)["files"]
            != source_binding["evaluator"]["files"]
        ):
            raise EvaluationContractError(
                "candidate/evaluator working source changed during final run"
            )
        raw_evidence = {
            "schema_version": RAW_EVIDENCE_SCHEMA,
            "preregistration_binding": {
                "path": "data/eval/gwip_mechanism_prereg_v1.json",
                "raw_sha256": preregistration_digest,
            },
            "seed_manifest_binding": seed_binding,
            "source_binding": source_binding,
            "run_lease_plan_binding": plan_binding,
            "cohort_binding": {
                "private_cohort_sha256": private_cohort_digest(mechanics),
                "mechanic_count": preregistration["mechanic_count"],
                "candidate_episode_count": preregistration[
                    "candidate_episode_count"
                ],
            },
            "attempt_binding": attempt_binding,
            "execution_order": execution_order,
            "candidate_episodes": candidate_episodes,
            "reactive_episodes": reactive_episodes,
            "random_episodes": random_episodes,
            "source_audit": source_audit,
            "aggregate_metrics": None,
            "verdict": None,
        }
        verify_raw_evidence(
            raw_evidence,
            preregistration=preregistration,
            preregistration_digest=preregistration_digest,
            seed_manifest_binding=seed_binding,
            source_binding=source_binding,
            run_lease_plan_binding=plan_binding,
            run_lease_entries=lease_entries,
            mechanics=mechanics,
            candidate_root=candidate_root,
            attempt_binding=attempt_binding,
        )
        write_once_json(raw_evidence_path, raw_evidence)
        raw_sha256 = hashlib.sha256(Path(raw_evidence_path).read_bytes()).hexdigest()
        receipt = build_one_shot_receipt(
            raw_evidence=raw_evidence,
            raw_evidence_sha256=raw_sha256,
            preregistration=preregistration,
            preregistration_digest=preregistration_digest,
            seed_manifest_binding=seed_binding,
            source_binding=source_binding,
            run_lease_plan_binding=plan_binding,
            run_lease_entries=lease_entries,
            mechanics=mechanics,
            candidate_root=candidate_root,
            attempt_binding=attempt_binding,
        )
        write_once_json(receipt_path, receipt)
        checked = verify_one_shot_receipt(
            receipt,
            raw_evidence=raw_evidence,
            raw_evidence_sha256=raw_sha256,
            preregistration=preregistration,
            preregistration_digest=preregistration_digest,
            seed_manifest_binding=seed_binding,
            source_binding=source_binding,
            run_lease_plan_binding=plan_binding,
            run_lease_entries=lease_entries,
            mechanics=mechanics,
            candidate_root=candidate_root,
            attempt_binding=attempt_binding,
        )
        if checked["valid"] is not True:
            raise EvaluationContractError("final receipt failed independent verification")
        return {
            "verdict": receipt["verdict"],
            "raw_evidence_path": str(Path(raw_evidence_path).resolve()),
            "raw_evidence_sha256": raw_sha256,
            "receipt_path": str(Path(receipt_path).resolve()),
            "receipt_checksum_sha256": receipt["checksum_sha256"],
        }


def verify_final_artifacts(
    *,
    seed_manifest_commit: str,
    run_lease_plan_path: Path,
    attempt_path: Path = FINAL_ATTEMPT,
    raw_evidence_path: Path = FINAL_RAW_EVIDENCE,
    receipt_path: Path = FINAL_RECEIPT,
) -> dict[str, Any]:
    """Reopen ledgers and regenerate the cohort before accepting final receipt."""

    if (
        Path(attempt_path).resolve() != FINAL_ATTEMPT.resolve()
        or Path(raw_evidence_path).resolve() != FINAL_RAW_EVIDENCE.resolve()
        or Path(receipt_path).resolve() != FINAL_RECEIPT.resolve()
    ):
        raise EvaluationContractError("verify-final artifact paths are frozen")
    preregistration, preregistration_digest = load_preregistration()
    manifest, seed_binding = load_and_verify_seed_manifest(
        REPO / SEED_MANIFEST_RELATIVE_PATH,
        seed_manifest_commit=seed_manifest_commit,
    )
    lease_entries, plan_binding = load_run_lease_plan(
        run_lease_plan_path,
        preregistration=preregistration,
    )
    plan_binding = {
        **plan_binding,
        "verified_seed_source_binding": verify_run_lease_plan_seed_binding(
            lease_entries,
            seed_manifest_binding=seed_binding,
        ),
    }
    raw = _load_json_object(Path(raw_evidence_path), "GWIP raw evidence")
    receipt = _load_json_object(Path(receipt_path), "GWIP receipt")
    attempt_payload = _load_json_object(Path(attempt_path), "GWIP attempt")
    source_binding = {
        "candidate": seed_binding["candidate"],
        "evaluator": seed_binding["evaluator"],
    }
    attempt_binding = _expected_attempt_binding(
        seed_manifest_binding=seed_binding,
        source_binding=source_binding,
        run_lease_plan_binding=plan_binding,
    )
    if (
        attempt_payload != attempt_binding["payload"]
        or Path(attempt_path).read_bytes()
        != _json_artifact_bytes(attempt_binding["payload"])
    ):
        raise EvaluationContractError("final attempt artifact binding mismatch")
    mechanics = generate_hidden_mechanics(
        preregistration,
        generator_seed=manifest["generator_seed"],
        generator_nonce=manifest["generator_nonce"],
    )
    with sealed_candidate_source(manifest["candidate_commit"]) as (
        candidate_root,
        _candidate_tree,
    ):
        return verify_one_shot_receipt(
            receipt,
            raw_evidence=raw,
            raw_evidence_sha256=hashlib.sha256(
                Path(raw_evidence_path).read_bytes()
            ).hexdigest(),
            preregistration=preregistration,
            preregistration_digest=preregistration_digest,
            seed_manifest_binding=seed_binding,
            source_binding=source_binding,
            run_lease_plan_binding=plan_binding,
            run_lease_entries=lease_entries,
            mechanics=mechanics,
            candidate_root=candidate_root,
            attempt_binding=attempt_binding,
        )


def _validation_summary() -> dict[str, Any]:
    preregistration, raw_digest = load_preregistration()
    return {
        "schema_version": "atanor.gwip-evaluator-validation.v1",
        "valid": True,
        "preregistration_raw_sha256": raw_digest,
        "mechanic_count": preregistration["mechanic_count"],
        "candidate_episode_count": preregistration["candidate_episode_count"],
        "final_seed_manifest_present": False,
        "final_cohort_executed": False,
        "note": (
            "Evaluator contract validated only. Candidate source must be sealed "
            "before a separate seed/nonce manifest is created."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["candidate-worker"]:
        return _candidate_worker_main()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "validate-prereg",
            "prepare-leases",
            "run-final",
            "verify-final",
        ),
        help="run-final requires a separately committed post-candidate manifest.",
    )
    parser.add_argument("--seed-manifest-commit")
    parser.add_argument("--run-lease-plan", type=Path)
    parser.add_argument("--external-root", type=Path)
    args = parser.parse_args(arguments)
    if args.command == "validate-prereg":
        print(json.dumps(_validation_summary(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare-leases":
        if (
            args.external_root is None
            or not args.seed_manifest_commit
        ):
            parser.error(
                "prepare-leases requires --external-root, "
                "and --seed-manifest-commit"
            )
        result = prepare_run_lease_plan(
            args.external_root,
            seed_manifest_commit=args.seed_manifest_commit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not args.seed_manifest_commit or args.run_lease_plan is None:
        parser.error(
            "run-final/verify-final require --seed-manifest-commit and "
            "--run-lease-plan"
        )
    if args.command == "run-final":
        result = run_final_once(
            seed_manifest_commit=args.seed_manifest_commit,
            run_lease_plan_path=args.run_lease_plan,
        )
    else:
        result = verify_final_artifacts(
            seed_manifest_commit=args.seed_manifest_commit,
            run_lease_plan_path=args.run_lease_plan,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
