"""Frozen design, cohort generator, and metrics for the GWIP capability pilot.

This module is evaluator-owned.  It is deliberately standard-library only and
does not import the candidate or any candidate-side verifier.  It does not
create a seed, persist an artifact, run an episode, or consume the one allowed
final attempt.  A later sealed evaluator may call the pure functions here with
the post-evaluator seed and nonce.

The only capability family represented here is the preregistered four-action
integer-affine transition family across moduli 13, 17, and 19.  A positive
verdict is therefore limited to that pilot and is not an ARC or production
claim.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import copy
import hashlib
from itertools import permutations
import json
import math
from pathlib import Path
import random
import re
from typing import Any


REPO = Path(__file__).resolve().parents[1]
PREREGISTRATION_PATH = REPO / "data" / "eval" / "gwip_capability_prereg_v1.json"
PREREG_SCHEMA = "atanor.gwip-capability-prereg.v1"
RULE_IR_SCHEMA = "atanor.gwip-feature-rule.v1"

SOURCE_ARM = "source_candidate"
REACTIVE_ARM = "source_reactive"
RANDOM_ARM = "source_random"
MATCHED_WARM_ARM = "matched_warm"
COLD_ARM = "cold"
MISMATCHED_WARM_ARM = "mismatched_warm"
TARGET_ARMS = (MATCHED_WARM_ARM, COLD_ARM, MISMATCHED_WARM_ARM)

REGISTER_PATH = "/features/registers/0"
CONTEXT_PATH = "/features/context/modulus"

SEALED_CANDIDATE_MAX_RULE_AST_DEPTH = 6
SEALED_CANDIDATE_MAX_RULE_HYPOTHESES = 64
PRIOR_MECHANISM_COUNT = 48
PRIOR_MECHANISM_STATE_MINIMUM = 8
PRIOR_MECHANISM_STATE_MAXIMUM = 12
COUNTERFACTUAL_CELL_COUNT = 19 * 4

_SHA256 = re.compile(r"[0-9a-f]{64}")


class CapabilityDesignError(ValueError):
    """Raised when frozen design or independently derived evidence is invalid."""


FROZEN_PREREGISTRATION: dict[str, Any] = {
    "schema_version": PREREG_SCHEMA,
    "mechanism_candidate_base_commit": (
        "84e63520a2f59df62faaa5dbc74e0bfbb99deabd"
    ),
    "candidate_package_allowlist": [
        "packages/fusion_loop/interactive.py",
        "packages/fusion_loop/interactive_organs.py",
        "packages/fusion_loop/tests/test_interactive_loop.py",
        "packages/fusion_loop/tests/test_interactive_rule_transfer.py",
    ],
    "pair_count": 64,
    "source_modulus": 13,
    "target_modulus": 17,
    "counterfactual_modulus": 19,
    "action_count": 4,
    "support_episodes_per_pair": 4,
    "target_episodes_per_arm": 4,
    "target_arms": list(TARGET_ARMS),
    "candidate_episode_count": 1024,
    "step_budget": 24,
    "coefficient_generator_minimum": -3,
    "coefficient_generator_maximum": 3,
    "coefficient_search_minimum": -6,
    "coefficient_search_maximum": 6,
    "minimum_distinct_rule_inputs": 3,
    "prequential_confirmation_required": True,
    "rule_ir_schema": RULE_IR_SCHEMA,
    "rule_metadata_key": "transition_rule_hypotheses",
    "random_policy_seeds": list(range(32)),
    "bootstrap_resamples": 10_000,
    "bootstrap_seed": 2026072702,
    "minimum_one_sided_lcb": 0.0,
    "fresh_success_minimum": 0.9,
    "fresh_success_minimum_lift": 0.05,
    "rule_precision_minimum": 1.0,
    "rule_coverage_minimum": 0.9,
    "rule_counterfactual_minimum": 8,
    "rule_discovered_pair_minimum": 45,
    "rule_discovery_median_action_maximum": 32,
    "rule_discovery_p75_action_maximum": 64,
    "rule_discovery_censor_action": 97,
    "fresh_normalized_regret_maximum": 0.45,
    "fresh_normalized_regret_minimum_reduction": 0.1,
    "transfer_success_minimum": 0.7,
    "transfer_success_minimum_lift": 0.1,
    "transfer_normalized_regret_maximum": 0.5,
    "transfer_normalized_regret_minimum_reduction": 0.1,
    "transfer_score_minimum": 0.1,
    "worker_concurrency": 4,
    "lease_ttl_seconds": 3600,
    "lease_issue_to_activation_max_seconds": 120,
    "worker_timeout_seconds": 1200,
    "lease_finish_and_seal_max_seconds": 120,
    "candidate_source_must_precede_evaluator": True,
    "candidate_and_evaluator_must_precede_seed_manifest": True,
    "candidate_may_read_evaluator_or_seed": False,
    "target_episode_learning_allowed": False,
    "production_default_on": False,
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


_TARGET_ARM_PERMUTATIONS = (
    (MATCHED_WARM_ARM, COLD_ARM, MISMATCHED_WARM_ARM),
    (MATCHED_WARM_ARM, MISMATCHED_WARM_ARM, COLD_ARM),
    (COLD_ARM, MATCHED_WARM_ARM, MISMATCHED_WARM_ARM),
    (COLD_ARM, MISMATCHED_WARM_ARM, MATCHED_WARM_ARM),
    (MISMATCHED_WARM_ARM, MATCHED_WARM_ARM, COLD_ARM),
    (MISMATCHED_WARM_ARM, COLD_ARM, MATCHED_WARM_ARM),
)
_TARGET_ARM_CODES = {
    MATCHED_WARM_ARM: 0,
    COLD_ARM: 1,
    MISMATCHED_WARM_ARM: 2,
}


def _freeze_json(value: Any) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise CapabilityDesignError("canonical JSON cannot contain non-finite floats")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            if type(key) is not str or not key:
                raise CapabilityDesignError("canonical JSON keys must be non-empty strings")
            result[key] = _freeze_json(value[key])
        return result
    if isinstance(value, (list, tuple)):
        return [_freeze_json(item) for item in value]
    raise CapabilityDesignError(
        f"unsupported canonical JSON type: {type(value).__name__}"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        _freeze_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_preregistration(value: Mapping[str, Any]) -> None:
    if type(value) is not dict or value != FROZEN_PREREGISTRATION:
        raise CapabilityDesignError(
            "capability preregistration differs from the frozen exact contract"
        )
    if (
        value["candidate_episode_count"]
        != value["pair_count"]
        * (
            value["support_episodes_per_pair"]
            + len(value["target_arms"]) * value["target_episodes_per_arm"]
        )
    ):
        raise CapabilityDesignError("candidate episode census is inconsistent")
    if (
        value["counterfactual_modulus"] * value["action_count"]
        != COUNTERFACTUAL_CELL_COUNT
    ):
        raise CapabilityDesignError("counterfactual cell census is inconsistent")
    if value["rule_discovery_censor_action"] != (
        value["support_episodes_per_pair"] * value["step_budget"] + 1
    ):
        raise CapabilityDesignError("rule-discovery censor is inconsistent")


def load_preregistration(
    path: Path = PREREGISTRATION_PATH,
) -> tuple[dict[str, Any], str]:
    resolved = Path(path).resolve(strict=True)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapabilityDesignError(f"capability preregistration unreadable: {exc}") from exc
    _validate_preregistration(value)
    return copy.deepcopy(value), hashlib.sha256(resolved.read_bytes()).hexdigest()


def _validate_generator_input(value: str, label: str) -> None:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z0-9._:-]{16,512}", value) is None
    ):
        raise CapabilityDesignError(
            f"{label} must be a bounded canonical opaque token"
        )


def _derived_int(*parts: str) -> int:
    if not parts or any(type(item) is not str for item in parts):
        raise CapabilityDesignError("derived integer parts must be strings")
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).digest()
    return int.from_bytes(digest, "big", signed=False)


def _opaque_ref(kind: str, secret: str, *parts: object) -> str:
    material = canonical_json(
        {
            "domain": "atanor.gwip.capability.opaque.v1",
            "kind": kind,
            "secret": secret,
            "parts": [str(item) for item in parts],
        }
    )
    return f"{kind}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


@dataclass(frozen=True)
class AffineProgram:
    multiplier: int
    offset: int

    def __post_init__(self) -> None:
        if type(self.multiplier) is not int or type(self.offset) is not int:
            raise CapabilityDesignError("affine coefficients must be exact integers")
        if self.multiplier == 0:
            raise CapabilityDesignError("affine multiplier cannot be zero")
        if not (-3 <= self.multiplier <= 3 and -3 <= self.offset <= 3):
            raise CapabilityDesignError("generator coefficient is outside [-3,3]")
        if self.multiplier == 1 and self.offset == 0:
            raise CapabilityDesignError("identity program is forbidden")

    @property
    def is_nonzero_translation(self) -> bool:
        return self.multiplier == 1 and self.offset != 0

    def apply(self, value: int, modulus: int) -> int:
        if type(value) is not int or type(modulus) is not int or modulus <= 1:
            raise CapabilityDesignError("affine application requires exact integers")
        return (self.multiplier * value + self.offset) % modulus

    def private_dict(self) -> dict[str, int]:
        return {"multiplier": self.multiplier, "offset": self.offset}


@dataclass(frozen=True)
class CapabilityAction:
    action_index: int
    action_ref: str
    payload_cue: str
    payload_signature: str
    program: AffineProgram

    def __post_init__(self) -> None:
        if type(self.action_index) is not int or not 0 <= self.action_index < 4:
            raise CapabilityDesignError("action index is outside the frozen census")
        if type(self.action_ref) is not str or not self.action_ref:
            raise CapabilityDesignError("action ref must be non-empty")
        if type(self.payload_cue) is not str or not self.payload_cue:
            raise CapabilityDesignError("payload cue must be non-empty")
        expected = canonical_digest(self.payload)
        if self.payload_signature != expected:
            raise CapabilityDesignError("action payload signature is not canonical")

    @property
    def payload(self) -> dict[str, str]:
        return {"semantic_cue": self.payload_cue}

    def public_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_ref, "payload": self.payload}

    def private_dict(self) -> dict[str, Any]:
        return {
            "action_index": self.action_index,
            "action_ref": self.action_ref,
            "payload": self.payload,
            "payload_signature": self.payload_signature,
            "program": self.program.private_dict(),
        }


@dataclass(frozen=True)
class CapabilityTransition:
    before_value: int
    state_ref: str
    action_index: int
    action_ref: str
    after_value: int
    next_state_ref: str
    edge_ref: str
    transition_tuple_digest: str

    def private_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityEpisode:
    episode_index: int
    start_value: int
    start_ref: str
    goal_value: int
    goal_ref: str
    optimal_steps: int
    oracle_action_indices: tuple[int, ...]
    oracle_action_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.episode_index) is not int or not 0 <= self.episode_index < 4:
            raise CapabilityDesignError("episode index is outside the frozen census")
        if self.start_ref == self.goal_ref or self.start_value == self.goal_value:
            raise CapabilityDesignError("capability episodes must be nontrivial")
        if (
            type(self.optimal_steps) is not int
            or self.optimal_steps <= 0
            or self.optimal_steps > 24
            or len(self.oracle_action_indices) != self.optimal_steps
            or len(self.oracle_action_refs) != self.optimal_steps
        ):
            raise CapabilityDesignError("episode oracle path is inconsistent")

    def private_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["oracle_action_indices"] = list(self.oracle_action_indices)
        value["oracle_action_refs"] = list(self.oracle_action_refs)
        return value


@dataclass(frozen=True)
class CapabilityEnvironment:
    pair_index: int
    environment_kind: str
    modulus: int
    private_ref: str
    schema_version: str
    state_refs: tuple[str, ...]
    actions: tuple[CapabilityAction, ...]
    action_presentation_order: tuple[int, ...]
    transitions: tuple[CapabilityTransition, ...]
    episodes: tuple[CapabilityEpisode, ...]

    def __post_init__(self) -> None:
        if self.environment_kind not in {"source", "target", "counterfactual"}:
            raise CapabilityDesignError("environment kind is invalid")
        expected_modulus = {
            "source": 13,
            "target": 17,
            "counterfactual": 19,
        }[self.environment_kind]
        if self.modulus != expected_modulus:
            raise CapabilityDesignError("environment modulus is not frozen")
        if len(self.state_refs) != self.modulus or len(set(self.state_refs)) != self.modulus:
            raise CapabilityDesignError("environment state census is invalid")
        if len(self.actions) != 4 or len({item.action_ref for item in self.actions}) != 4:
            raise CapabilityDesignError("environment action census is invalid")
        if self.action_presentation_order not in tuple(permutations(range(4))):
            raise CapabilityDesignError(
                "environment action presentation is not a permutation"
            )
        if len(self.transitions) != self.modulus * len(self.actions):
            raise CapabilityDesignError("environment transition census is invalid")
        expected_episode_count = 0 if self.environment_kind == "counterfactual" else 4
        if len(self.episodes) != expected_episode_count:
            raise CapabilityDesignError("environment episode census is invalid")

    def state_ref_for_value(self, value: int) -> str:
        if type(value) is not int or not 0 <= value < self.modulus:
            raise CapabilityDesignError("state value is outside environment")
        return self.state_refs[value]

    def value_for_state_ref(self, state_ref: str) -> int:
        try:
            return self.state_refs.index(state_ref)
        except ValueError as exc:
            raise CapabilityDesignError("state ref is outside environment") from exc

    def action_for_ref(self, action_ref: str) -> CapabilityAction:
        for action in self.actions:
            if action.action_ref == action_ref:
                return action
        raise CapabilityDesignError("action ref is outside environment")

    def transition(self, state_ref: str, action_ref: str) -> str:
        for edge in self.transitions:
            if edge.state_ref == state_ref and edge.action_ref == action_ref:
                return edge.next_state_ref
        raise CapabilityDesignError("state/action pair is outside environment")

    def observation(
        self,
        state_ref: str,
        *,
        goal_ref: str,
    ) -> dict[str, Any]:
        value = self.value_for_state_ref(state_ref)
        self.value_for_state_ref(goal_ref)
        return {
            "schema_version": self.schema_version,
            "state_ref": state_ref,
            "features": {
                "registers": [value],
                "context": {"modulus": self.modulus},
            },
            "terminal": state_ref == goal_ref,
        }

    def observation_ref(
        self,
        state_ref: str,
        *,
        goal_ref: str,
    ) -> str:
        observation = self.observation(state_ref, goal_ref=goal_ref)
        return "observation_" + canonical_digest(
            {
                "environment_ref": self.private_ref,
                "observation": observation,
                "goal_ref": goal_ref,
            }
        )[:32]

    def public_actions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            self.actions[index].public_dict()
            for index in self.action_presentation_order
        )

    def goal_metadata(self, episode_index: int) -> dict[str, Any]:
        if type(episode_index) is not int or not 0 <= episode_index < len(self.episodes):
            raise CapabilityDesignError("episode index is outside environment")
        return {
            "target_constraints": [
                {
                    "path": REGISTER_PATH,
                    "op": "eq",
                    "value": self.episodes[episode_index].goal_value,
                }
            ]
        }

    def private_dict(self) -> dict[str, Any]:
        return {
            "pair_index": self.pair_index,
            "environment_kind": self.environment_kind,
            "modulus": self.modulus,
            "private_ref": self.private_ref,
            "schema_version": self.schema_version,
            "state_refs": list(self.state_refs),
            "actions": [item.private_dict() for item in self.actions],
            "action_presentation_order": list(
                self.action_presentation_order
            ),
            "transitions": [item.private_dict() for item in self.transitions],
            "episodes": [item.private_dict() for item in self.episodes],
        }


@dataclass(frozen=True)
class CapabilityPair:
    pair_index: int
    private_ref: str
    programs: tuple[AffineProgram, ...]
    payload_cues: tuple[str, ...]
    source: CapabilityEnvironment
    target: CapabilityEnvironment
    counterfactual: CapabilityEnvironment

    def private_dict(self) -> dict[str, Any]:
        return {
            "pair_index": self.pair_index,
            "private_ref": self.private_ref,
            "programs": [item.private_dict() for item in self.programs],
            "payload_cues": list(self.payload_cues),
            "source": self.source.private_dict(),
            "target": self.target.private_dict(),
            "counterfactual": self.counterfactual.private_dict(),
        }


def _shortest_action_indices(
    *,
    programs: Sequence[AffineProgram],
    modulus: int,
    start_value: int,
    goal_value: int,
) -> tuple[int, ...]:
    if start_value == goal_value:
        return ()
    queue: deque[tuple[int, tuple[int, ...]]] = deque([(start_value, ())])
    visited = {start_value}
    while queue:
        value, path = queue.popleft()
        for index, program in enumerate(programs):
            after = program.apply(value, modulus)
            next_path = path + (index,)
            if after == goal_value:
                return next_path
            if after not in visited:
                visited.add(after)
                queue.append((after, next_path))
    raise CapabilityDesignError("translation-backed environment is unexpectedly disconnected")


def _build_programs(pair_secret: str) -> tuple[AffineProgram, ...]:
    rng = random.Random(_derived_int("gwip-capability-programs-v1", pair_secret))
    translation_offsets = [-3, -2, -1, 1, 2, 3]
    translation = AffineProgram(1, rng.choice(translation_offsets))
    nontranslations = [
        AffineProgram(multiplier, offset)
        for multiplier in (-3, -2, -1, 2, 3)
        for offset in range(-3, 4)
    ]
    rng.shuffle(nontranslations)
    programs = [translation, *nontranslations[:3]]
    rng.shuffle(programs)
    if (
        len(set(programs)) != 4
        or sum(item.is_nonzero_translation for item in programs) != 1
    ):
        raise AssertionError("program generator violated the frozen shape")
    return tuple(programs)


def _build_environment(
    *,
    pair_index: int,
    pair_secret: str,
    environment_kind: str,
    modulus: int,
    programs: tuple[AffineProgram, ...],
    payload_cues: tuple[str, ...],
    action_presentation_order: tuple[int, ...],
) -> CapabilityEnvironment:
    env_secret = canonical_digest(
        {
            "domain": "atanor.gwip.capability.environment.v1",
            "pair_secret": pair_secret,
            "environment_kind": environment_kind,
        }
    )
    private_ref = _opaque_ref("capenv", env_secret, pair_index, environment_kind)
    schema_version = _opaque_ref(
        "schema", env_secret, pair_index, environment_kind
    )
    state_refs = tuple(
        _opaque_ref("state", env_secret, pair_index, environment_kind, value)
        for value in range(modulus)
    )
    actions = tuple(
        CapabilityAction(
            action_index=index,
            action_ref=_opaque_ref(
                "action", env_secret, pair_index, environment_kind, index
            ),
            payload_cue=payload_cues[index],
            payload_signature=canonical_digest(
                {"semantic_cue": payload_cues[index]}
            ),
            program=programs[index],
        )
        for index in range(4)
    )
    transitions: list[CapabilityTransition] = []
    for before in range(modulus):
        for action in actions:
            after = action.program.apply(before, modulus)
            tuple_payload = {
                "state_ref": state_refs[before],
                "action_ref": action.action_ref,
                "next_state_ref": state_refs[after],
            }
            tuple_digest = canonical_digest(tuple_payload)
            transitions.append(
                CapabilityTransition(
                    before_value=before,
                    state_ref=state_refs[before],
                    action_index=action.action_index,
                    action_ref=action.action_ref,
                    after_value=after,
                    next_state_ref=state_refs[after],
                    edge_ref="transition_" + canonical_digest(
                        {
                            "environment_ref": private_ref,
                            "tuple": tuple_payload,
                        }
                    )[:32],
                    transition_tuple_digest=tuple_digest,
                )
            )

    episodes: list[CapabilityEpisode] = []
    if environment_kind != "counterfactual":
        episode_rng = random.Random(
            _derived_int("gwip-capability-episodes-v1", env_secret)
        )
        starts = list(range(modulus))
        goals = list(range(modulus))
        episode_rng.shuffle(starts)
        episode_rng.shuffle(goals)
        selected_starts = starts[:4]
        selected_goals: list[int] = []
        remaining_goals = goals[:]
        for start in selected_starts:
            choice = next(item for item in remaining_goals if item != start)
            selected_goals.append(choice)
            remaining_goals.remove(choice)
        for episode_index, (start, goal) in enumerate(
            zip(selected_starts, selected_goals)
        ):
            oracle_indices = _shortest_action_indices(
                programs=programs,
                modulus=modulus,
                start_value=start,
                goal_value=goal,
            )
            episodes.append(
                CapabilityEpisode(
                    episode_index=episode_index,
                    start_value=start,
                    start_ref=state_refs[start],
                    goal_value=goal,
                    goal_ref=state_refs[goal],
                    optimal_steps=len(oracle_indices),
                    oracle_action_indices=oracle_indices,
                    oracle_action_refs=tuple(
                        actions[index].action_ref for index in oracle_indices
                    ),
                )
            )
    return CapabilityEnvironment(
        pair_index=pair_index,
        environment_kind=environment_kind,
        modulus=modulus,
        private_ref=private_ref,
        schema_version=schema_version,
        state_refs=state_refs,
        actions=actions,
        action_presentation_order=action_presentation_order,
        transitions=tuple(transitions),
        episodes=tuple(episodes),
    )


def _build_action_presentation_orders(
    pair_secret: str,
) -> dict[str, tuple[int, ...]]:
    """Choose three pairwise position-deranged presentation orders.

    Merely choosing three different permutations would leave a second,
    unintended transfer signal: an action could keep the same public ordinal
    in two environments.  Rotations of one hidden random base permutation
    guarantee that no public position carries the same latent program across
    source, target, or counterfactual environments.
    """

    choices = list(permutations(range(4)))
    rng = random.Random(
        _derived_int(
            "gwip-capability-action-presentation-v1",
            pair_secret,
        )
    )
    base = choices[rng.randrange(len(choices))]
    selected = tuple(
        base[offset:] + base[:offset]
        for offset in (0, 1, 2)
    )
    if (
        len(set(selected)) != 3
        or any(
            left[position] == right[position]
            for left_index, left in enumerate(selected)
            for right in selected[left_index + 1 :]
            for position in range(4)
        )
    ):
        raise AssertionError(
            "action presentation orders are not pairwise position-deranged"
        )
    return dict(
        zip(
            ("source", "target", "counterfactual"),
            selected,
            strict=True,
        )
    )


def _validate_capability_pairs(
    pairs: Sequence[CapabilityPair],
    preregistration: Mapping[str, Any],
) -> None:
    if len(pairs) != preregistration["pair_count"]:
        raise CapabilityDesignError("capability pair census mismatch")
    if [item.pair_index for item in pairs] != list(range(len(pairs))):
        raise CapabilityDesignError("capability pair indices are not contiguous")
    pair_refs: set[str] = set()
    all_cues: set[str] = set()
    all_environment_refs: set[str] = set()
    all_state_refs: set[str] = set()
    all_action_refs: set[str] = set()
    all_edge_refs: set[str] = set()
    all_observation_refs: set[str] = set()
    all_tuple_digests: set[str] = set()
    for pair in pairs:
        if pair.private_ref in pair_refs:
            raise CapabilityDesignError("duplicate pair ref")
        pair_refs.add(pair.private_ref)
        if len(pair.programs) != 4 or len(set(pair.programs)) != 4:
            raise CapabilityDesignError("pair program census mismatch")
        if sum(item.is_nonzero_translation for item in pair.programs) != 1:
            raise CapabilityDesignError("pair does not have exactly one translation")
        if len(pair.payload_cues) != 4 or len(set(pair.payload_cues)) != 4:
            raise CapabilityDesignError("pair payload cue census mismatch")
        if set(pair.payload_cues) & all_cues:
            raise CapabilityDesignError("payload cues must be unique across pairs")
        all_cues.update(pair.payload_cues)
        environments = (pair.source, pair.target, pair.counterfactual)
        for environment in environments:
            if environment.private_ref in all_environment_refs:
                raise CapabilityDesignError("duplicate environment ref")
            all_environment_refs.add(environment.private_ref)
            if set(environment.state_refs) & all_state_refs:
                raise CapabilityDesignError("state refs overlap across environments")
            all_state_refs.update(environment.state_refs)
            action_refs = {item.action_ref for item in environment.actions}
            if action_refs & all_action_refs:
                raise CapabilityDesignError("action refs overlap across environments")
            all_action_refs.update(action_refs)
            edge_refs = {item.edge_ref for item in environment.transitions}
            if edge_refs & all_edge_refs:
                raise CapabilityDesignError("edge refs overlap across environments")
            all_edge_refs.update(edge_refs)
            tuple_digests = {
                item.transition_tuple_digest for item in environment.transitions
            }
            if tuple_digests & all_tuple_digests:
                raise CapabilityDesignError(
                    "transition tuple digests overlap across environments"
                )
            all_tuple_digests.update(tuple_digests)
            for episode in environment.episodes:
                for state_ref in environment.state_refs:
                    ref = environment.observation_ref(
                        state_ref, goal_ref=episode.goal_ref
                    )
                    if ref in all_observation_refs:
                        raise CapabilityDesignError(
                            "observation refs overlap across environments/episodes"
                        )
                    all_observation_refs.add(ref)
        for index in range(4):
            source_action = pair.source.actions[index]
            target_action = pair.target.actions[index]
            counterfactual_action = pair.counterfactual.actions[index]
            if not (
                source_action.program
                == target_action.program
                == counterfactual_action.program
                == pair.programs[index]
            ):
                raise CapabilityDesignError("program alignment mismatch")
            if not (
                source_action.payload
                == target_action.payload
                == counterfactual_action.payload
            ):
                raise CapabilityDesignError("payload alignment mismatch")
            if len(
                {
                    source_action.action_ref,
                    target_action.action_ref,
                    counterfactual_action.action_ref,
                }
            ) != 3:
                raise CapabilityDesignError("environment action IDs are not disjoint")
        presentation_signatures = {
            tuple(
                canonical_digest(item["payload"])
                for item in environment.public_actions()
            )
            for environment in environments
        }
        if len(presentation_signatures) != 3:
            raise CapabilityDesignError(
                "environment action presentation orders are not distinct"
            )
        for left_index, left in enumerate(environments):
            left_order = left.action_presentation_order
            for right in environments[left_index + 1 :]:
                right_order = right.action_presentation_order
                if any(
                    left_order[position] == right_order[position]
                    for position in range(4)
                ):
                    raise CapabilityDesignError(
                        "environment action presentation leaks a latent "
                        "program through its public ordinal"
                    )


def generate_capability_pairs(
    preregistration: Mapping[str, Any],
    *,
    generator_seed: str,
    generator_nonce: str,
) -> tuple[CapabilityPair, ...]:
    """Pure post-seal generator; it never creates or persists a final seed."""

    _validate_preregistration(preregistration)
    _validate_generator_input(generator_seed, "generator_seed")
    _validate_generator_input(generator_nonce, "generator_nonce")
    pairs: list[CapabilityPair] = []
    for pair_index in range(preregistration["pair_count"]):
        pair_secret = canonical_digest(
            {
                "domain": "atanor.gwip.capability-pair.v1",
                "generator_seed": generator_seed,
                "generator_nonce": generator_nonce,
                "pair_index": pair_index,
            }
        )
        programs = _build_programs(pair_secret)
        presentation_orders = _build_action_presentation_orders(pair_secret)
        payload_cues = tuple(
            _opaque_ref("cue", pair_secret, pair_index, index)
            for index in range(4)
        )
        pairs.append(
            CapabilityPair(
                pair_index=pair_index,
                private_ref=_opaque_ref("cappair", pair_secret, pair_index),
                programs=programs,
                payload_cues=payload_cues,
                source=_build_environment(
                    pair_index=pair_index,
                    pair_secret=pair_secret,
                    environment_kind="source",
                    modulus=preregistration["source_modulus"],
                    programs=programs,
                    payload_cues=payload_cues,
                    action_presentation_order=presentation_orders["source"],
                ),
                target=_build_environment(
                    pair_index=pair_index,
                    pair_secret=pair_secret,
                    environment_kind="target",
                    modulus=preregistration["target_modulus"],
                    programs=programs,
                    payload_cues=payload_cues,
                    action_presentation_order=presentation_orders["target"],
                ),
                counterfactual=_build_environment(
                    pair_index=pair_index,
                    pair_secret=pair_secret,
                    environment_kind="counterfactual",
                    modulus=preregistration["counterfactual_modulus"],
                    programs=programs,
                    payload_cues=payload_cues,
                    action_presentation_order=presentation_orders[
                        "counterfactual"
                    ],
                ),
            )
        )
    result = tuple(pairs)
    _validate_capability_pairs(result, preregistration)
    return result


def private_cohort_digest(pairs: Sequence[CapabilityPair]) -> str:
    if (
        len(pairs) != FROZEN_PREREGISTRATION["pair_count"]
        or [item.pair_index for item in pairs] != list(range(len(pairs)))
    ):
        raise CapabilityDesignError("capability cohort is empty or non-contiguous")
    return canonical_digest([item.private_dict() for item in pairs])


def target_arm_order(pair_index: int) -> tuple[str, str, str]:
    if type(pair_index) is not int or pair_index < 0:
        raise CapabilityDesignError("pair index must be a nonnegative exact integer")
    return _TARGET_ARM_PERMUTATIONS[pair_index % 6]


def support_semantic_ordinal(pair_index: int, episode_index: int) -> int:
    if (
        type(pair_index) is not int
        or not 0 <= pair_index < 64
        or type(episode_index) is not int
        or not 0 <= episode_index < 4
    ):
        raise CapabilityDesignError("support semantic coordinates are invalid")
    return pair_index * 4 + episode_index


def target_semantic_ordinal(
    pair_index: int,
    arm: str,
    start_index: int,
) -> int:
    if (
        type(pair_index) is not int
        or not 0 <= pair_index < 64
        or arm not in _TARGET_ARM_CODES
        or type(start_index) is not int
        or not 0 <= start_index < 4
    ):
        raise CapabilityDesignError("target semantic coordinates are invalid")
    return 256 + pair_index * 12 + _TARGET_ARM_CODES[arm] * 4 + start_index


def candidate_schedule_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for pair_index in range(64):
        for episode_index in range(4):
            rows.append(
                {
                    "ordinal": support_semantic_ordinal(pair_index, episode_index),
                    "phase": "support",
                    "pair_index": pair_index,
                    "arm": SOURCE_ARM,
                    "episode_index": episode_index,
                }
            )
    for pair_index in range(64):
        for arm in TARGET_ARMS:
            for start_index in range(4):
                rows.append(
                    {
                        "ordinal": target_semantic_ordinal(
                            pair_index, arm, start_index
                        ),
                        "phase": "target",
                        "pair_index": pair_index,
                        "arm": arm,
                        "episode_index": start_index,
                    }
                )
    rows.sort(key=lambda item: item["ordinal"])
    if [item["ordinal"] for item in rows] != list(range(1024)):
        raise AssertionError("semantic schedule is not contiguous")
    return tuple(rows)


@dataclass(frozen=True)
class PriorMechanismNonoverlapInput:
    """Evaluator-supplied inventory regenerated from the sealed mechanism run."""

    cohort_binding: str
    private_mechanic_refs: frozenset[str]
    state_tokens: frozenset[str]
    action_tokens: frozenset[str]
    payload_cues: frozenset[str]
    start_tokens: frozenset[str]
    goal_tokens: frozenset[str]
    observation_tokens: frozenset[str]
    transition_edge_tokens: frozenset[str]
    transition_tuple_digests: frozenset[str]
    state_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.cohort_binding) is not str or not _SHA256.fullmatch(
            self.cohort_binding
        ):
            raise CapabilityDesignError("prior cohort binding must be SHA-256")
        if (
            len(self.private_mechanic_refs) != PRIOR_MECHANISM_COUNT
            or len(self.state_counts) != PRIOR_MECHANISM_COUNT
            or any(
                type(item) is not int
                or not PRIOR_MECHANISM_STATE_MINIMUM
                <= item
                <= PRIOR_MECHANISM_STATE_MAXIMUM
                for item in self.state_counts
            )
        ):
            raise CapabilityDesignError(
                "prior inventory does not describe the frozen 48-mechanic cohort"
            )
        for name in (
            "private_mechanic_refs",
            "state_tokens",
            "action_tokens",
            "payload_cues",
            "start_tokens",
            "goal_tokens",
            "observation_tokens",
            "transition_edge_tokens",
            "transition_tuple_digests",
        ):
            values = getattr(self, name)
            if any(type(item) is not str or not item for item in values):
                raise CapabilityDesignError(f"prior {name} contains an invalid token")
        if (
            len(self.observation_tokens) != sum(self.state_counts)
            or not self.transition_edge_tokens
        ):
            raise CapabilityDesignError(
                "prior observation/transition-edge inventory is incomplete"
            )


def build_prior_mechanism_nonoverlap_input(
    private_mechanics: Sequence[Mapping[str, Any]],
    *,
    cohort_binding: str,
    payload_cues: Sequence[str] = (),
) -> PriorMechanismNonoverlapInput:
    """Normalize independently regenerated mechanism private dictionaries.

    ``private_mechanics`` must come from the sealed mechanism evaluator.  This
    helper normalizes values but does not claim to verify the git/manifest
    provenance; the final evaluator must establish that binding before calling.
    """

    if len(private_mechanics) != PRIOR_MECHANISM_COUNT:
        raise CapabilityDesignError("prior mechanism count mismatch")
    private_refs: set[str] = set()
    states: set[str] = set()
    actions: set[str] = set()
    starts: set[str] = set()
    goals: set[str] = set()
    observations: set[str] = set()
    learned_edges: set[str] = set()
    tuple_digests: set[str] = set()
    counts: list[int] = []
    for expected_index, raw in enumerate(private_mechanics):
        if type(raw) is not dict:
            raise CapabilityDesignError("prior private mechanic must be an exact mapping")
        if raw.get("evaluator_index") != expected_index:
            raise CapabilityDesignError("prior mechanic indices are not contiguous")
        private_ref = raw.get("private_ref")
        state_refs = raw.get("state_refs")
        action_refs = raw.get("action_refs")
        transitions = raw.get("transitions")
        episodes = raw.get("episodes")
        goal_ref = raw.get("goal_ref")
        if (
            type(private_ref) is not str
            or type(state_refs) is not list
            or type(action_refs) is not list
            or type(transitions) is not list
            or type(episodes) is not list
            or type(goal_ref) is not str
            or len(set(state_refs)) != len(state_refs)
            or len(set(action_refs)) != len(action_refs)
        ):
            raise CapabilityDesignError("prior mechanic private shape is invalid")
        private_refs.add(private_ref)
        states.update(state_refs)
        actions.update(action_refs)
        goals.add(goal_ref)
        counts.append(len(state_refs))
        observation_digests: dict[str, str] = {}
        for state_ref in state_refs:
            observation = {
                "schema_version": "atanor.gwip-opaque-observation.v1",
                "state_ref": state_ref,
                "terminal": state_ref == goal_ref,
            }
            observation_digest = canonical_digest(observation)
            observation_digests[state_ref] = observation_digest
            observations.add(observation_digest)
        for episode in episodes:
            if type(episode) is not dict or type(episode.get("start_ref")) is not str:
                raise CapabilityDesignError("prior episode shape is invalid")
            starts.add(episode["start_ref"])
        for edge in transitions:
            if type(edge) is not dict or set(edge) != {
                "state_ref",
                "action_ref",
                "next_state_ref",
            }:
                raise CapabilityDesignError("prior transition shape is invalid")
            tuple_digests.add(canonical_digest(edge))
            before_digest = observation_digests[edge["state_ref"]]
            after_digest = observation_digests[edge["next_state_ref"]]
            learned_edges.add(
                "transition_edge_"
                + canonical_digest(
                    {
                        "action_id": edge["action_ref"],
                        "from": before_digest,
                        "to": after_digest,
                    }
                )[:32]
            )
    return PriorMechanismNonoverlapInput(
        cohort_binding=cohort_binding,
        private_mechanic_refs=frozenset(private_refs),
        state_tokens=frozenset(states),
        action_tokens=frozenset(actions),
        payload_cues=frozenset(payload_cues),
        start_tokens=frozenset(starts),
        goal_tokens=frozenset(goals),
        observation_tokens=frozenset(observations),
        transition_edge_tokens=frozenset(learned_edges),
        transition_tuple_digests=frozenset(tuple_digests),
        state_counts=tuple(counts),
    )


def capability_nonoverlap_inventory(
    pairs: Sequence[CapabilityPair],
) -> dict[str, frozenset[str] | tuple[int, ...]]:
    private_refs: set[str] = set()
    states: set[str] = set()
    actions: set[str] = set()
    cues: set[str] = set()
    starts: set[str] = set()
    goals: set[str] = set()
    observations: set[str] = set()
    edges: set[str] = set()
    tuples: set[str] = set()
    state_counts: list[int] = []
    for pair in pairs:
        private_refs.add(pair.private_ref)
        cues.update(pair.payload_cues)
        for environment in (pair.source, pair.target, pair.counterfactual):
            private_refs.add(environment.private_ref)
            states.update(environment.state_refs)
            actions.update(item.action_ref for item in environment.actions)
            starts.update(item.start_ref for item in environment.episodes)
            goals.update(item.goal_ref for item in environment.episodes)
            tuples.update(item.transition_tuple_digest for item in environment.transitions)
            state_counts.append(len(environment.state_refs))
            for episode in environment.episodes:
                observation_digests = {
                    state_ref: canonical_digest(
                        environment.observation(
                            state_ref,
                            goal_ref=episode.goal_ref,
                        )
                    )
                    for state_ref in environment.state_refs
                }
                observations.update(observation_digests.values())
                for transition in environment.transitions:
                    edges.add(
                        "transition_edge_"
                        + canonical_digest(
                            {
                                "action_id": transition.action_ref,
                                "from": observation_digests[
                                    transition.state_ref
                                ],
                                "to": observation_digests[
                                    transition.next_state_ref
                                ],
                            }
                        )[:32]
                    )
    return {
        "private_mechanic_refs": frozenset(private_refs),
        "state_tokens": frozenset(states),
        "action_tokens": frozenset(actions),
        "payload_cues": frozenset(cues),
        "start_tokens": frozenset(starts),
        "goal_tokens": frozenset(goals),
        "observation_tokens": frozenset(observations),
        "transition_edge_tokens": frozenset(edges),
        "transition_tuple_digests": frozenset(tuples),
        "state_counts": tuple(state_counts),
    }


def audit_prior_mechanism_nonoverlap(
    pairs: Sequence[CapabilityPair],
    prior: PriorMechanismNonoverlapInput,
) -> dict[str, Any]:
    current = capability_nonoverlap_inventory(pairs)
    categories = (
        "private_mechanic_refs",
        "state_tokens",
        "action_tokens",
        "payload_cues",
        "start_tokens",
        "goal_tokens",
        "observation_tokens",
        "transition_edge_tokens",
    )
    prior_union: set[str] = set()
    current_union: set[str] = set()
    for name in categories:
        prior_union.update(getattr(prior, name))
        current_union.update(current[name])
    token_overlap = sorted(prior_union & current_union)
    tuple_overlap = sorted(
        prior.transition_tuple_digests & current["transition_tuple_digests"]
    )
    state_count_overlap = sorted(
        {
            item
            for item in current["state_counts"]
            if PRIOR_MECHANISM_STATE_MINIMUM
            <= item
            <= PRIOR_MECHANISM_STATE_MAXIMUM
        }
    )
    findings: list[str] = []
    if token_overlap:
        findings.append("prior/current opaque token overlap")
    if tuple_overlap:
        findings.append("prior/current transition tuple digest overlap")
    if state_count_overlap:
        findings.append("capability state count overlaps prior range 8--12")
    return {
        "schema_version": "atanor.gwip-capability-nonoverlap-audit.v1",
        "prior_cohort_binding": prior.cohort_binding,
        "passed": not findings,
        "findings": findings,
        "token_overlap": token_overlap,
        "transition_tuple_digest_overlap": tuple_overlap,
        "state_count_overlap": state_count_overlap,
        "prior_mechanic_count": len(prior.private_mechanic_refs),
        "capability_pair_count": len(pairs),
    }


def _pointer_tokens(path: str) -> tuple[str, ...]:
    if type(path) is not str or not path.startswith("/") or path == "/":
        raise CapabilityDesignError("JSON pointer must be a non-root absolute path")
    result: list[str] = []
    for encoded in path[1:].split("/"):
        decoded = ""
        index = 0
        while index < len(encoded):
            if encoded[index] != "~":
                decoded += encoded[index]
                index += 1
            else:
                if index + 1 >= len(encoded) or encoded[index + 1] not in {"0", "1"}:
                    raise CapabilityDesignError("JSON pointer escape is invalid")
                decoded += "~" if encoded[index + 1] == "0" else "/"
                index += 2
        recoded = decoded.replace("~", "~0").replace("/", "~1")
        if recoded != encoded or (
            decoded.isdigit() and len(decoded) > 1 and decoded.startswith("0")
        ):
            raise CapabilityDesignError("JSON pointer is not canonical")
        result.append(decoded)
    return tuple(result)


def _pointer_get(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for token in _pointer_tokens(path):
        if isinstance(current, Mapping):
            if token not in current:
                raise CapabilityDesignError(f"missing JSON pointer: {path}")
            current = current[token]
        elif isinstance(current, (list, tuple)):
            if not token.isdigit() or int(token) >= len(current):
                raise CapabilityDesignError(f"missing JSON pointer: {path}")
            current = current[int(token)]
        else:
            raise CapabilityDesignError(f"missing JSON pointer: {path}")
    return current


def project_evaluator_features(observation: Mapping[str, Any]) -> dict[str, int]:
    """Independently project exact integer leaves below ``/features`` only."""

    if not isinstance(observation, Mapping):
        raise CapabilityDesignError("observation must be a mapping")
    features = observation.get("features")
    if not isinstance(features, (Mapping, list, tuple)):
        raise CapabilityDesignError("observation has no structured /features root")
    result: dict[str, int] = {}

    def visit(item: Any, path: str) -> None:
        if type(item) is int:
            result[path] = item
        elif isinstance(item, Mapping):
            for key in sorted(item):
                if type(key) is not str:
                    raise CapabilityDesignError("feature keys must be strings")
                escaped = key.replace("~", "~0").replace("/", "~1")
                visit(item[key], f"{path}/{escaped}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}/{index}")

    visit(features, "/features")
    return result


def _expression_depth(expression: Mapping[str, Any]) -> int:
    args = expression.get("args")
    if not args:
        return 1
    return 1 + max(_expression_depth(item) for item in args)


def _validate_expression(
    raw: Any,
    *,
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CapabilityDesignError("rule expression must be an exact mapping")
    expression = copy.deepcopy(raw)
    op = expression.get("op")
    if op in {"var", "copy"}:
        if set(expression) != {"op", "path"}:
            raise CapabilityDesignError(f"{op} expression fields mismatch")
        path = expression["path"]
        _pointer_tokens(path)
        if not path.startswith("/features/"):
            raise CapabilityDesignError("rule variables must remain below /features")
    elif op == "const":
        value = expression.get("value")
        if set(expression) != {"op", "value"} or type(value) is not int:
            raise CapabilityDesignError("const requires one exact integer")
        if not (
            preregistration["coefficient_search_minimum"]
            <= value
            <= preregistration["coefficient_search_maximum"]
        ):
            raise CapabilityDesignError("rule constant exceeds frozen search bound")
    elif op in {"add", "mul", "mod"}:
        args = expression.get("args")
        if set(expression) != {"op", "args"} or type(args) is not list or len(args) != 2:
            raise CapabilityDesignError(f"{op} requires exactly two args")
        expression["args"] = [
            _validate_expression(item, preregistration=preregistration)
            for item in args
        ]
    else:
        raise CapabilityDesignError("rule expression operation is outside grammar")
    if _expression_depth(expression) > SEALED_CANDIDATE_MAX_RULE_AST_DEPTH:
        raise CapabilityDesignError("rule expression exceeds sealed AST depth")
    return expression


def validate_rule_ir_independently(
    raw: Mapping[str, Any],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse Rule IR without calling candidate-side parsing or verification."""

    _validate_preregistration(preregistration)
    if type(raw) is not dict or set(raw) != {
        "schema_version",
        "action_signature",
        "input_path",
        "output_path",
        "context_path",
        "expression",
        "support_edge_refs",
        "hypothesis",
    }:
        raise CapabilityDesignError("rule IR fields mismatch")
    if raw["schema_version"] != preregistration["rule_ir_schema"]:
        raise CapabilityDesignError("rule IR schema mismatch")
    if type(raw["action_signature"]) is not str or not _SHA256.fullmatch(
        raw["action_signature"]
    ):
        raise CapabilityDesignError("rule action signature is invalid")
    if (
        raw["input_path"] != REGISTER_PATH
        or raw["output_path"] != REGISTER_PATH
        or raw["context_path"] != CONTEXT_PATH
    ):
        raise CapabilityDesignError("rule paths do not match evaluator-owned feature paths")
    refs = raw["support_edge_refs"]
    if (
        type(refs) is not list
        or len(refs) < preregistration["minimum_distinct_rule_inputs"]
        or len(set(refs)) != len(refs)
        or any(type(item) is not str or not item for item in refs)
    ):
        raise CapabilityDesignError("rule support refs are not distinct and bounded")
    if raw["hypothesis"] is not True:
        raise CapabilityDesignError("rule must remain marked as a hypothesis")
    normalized = copy.deepcopy(raw)
    normalized["expression"] = _validate_expression(
        raw["expression"], preregistration=preregistration
    )
    return normalized


def _evaluate_expression(
    expression: Mapping[str, Any],
    projection: Mapping[str, int],
) -> int:
    op = expression["op"]
    if op in {"var", "copy"}:
        value = projection.get(expression["path"])
        if type(value) is not int:
            raise CapabilityDesignError("rule variable is not an exact projected integer")
        return value
    if op == "const":
        return expression["value"]
    left = _evaluate_expression(expression["args"][0], projection)
    right = _evaluate_expression(expression["args"][1], projection)
    if op == "add":
        return left + right
    if op == "mul":
        return left * right
    if op == "mod":
        if right <= 0:
            raise CapabilityDesignError("rule modulus must be positive")
        return left % right
    raise AssertionError("validated expression has an unknown operation")


def evaluate_rule_ir_independently(
    raw: Mapping[str, Any],
    observation: Mapping[str, Any],
    preregistration: Mapping[str, Any],
) -> dict[str, int]:
    rule = validate_rule_ir_independently(raw, preregistration)
    projection = project_evaluator_features(observation)
    prediction = _evaluate_expression(rule["expression"], projection)
    return {rule["output_path"]: prediction}


@dataclass(frozen=True)
class CounterfactualRuleCheck:
    valid: bool
    correct_predictions: int
    prediction_count: int
    eligible_count: int
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise CapabilityDesignError("counterfactual validity must be literal boolean")
        for value, label in (
            (self.correct_predictions, "correct_predictions"),
            (self.prediction_count, "prediction_count"),
            (self.eligible_count, "eligible_count"),
        ):
            if type(value) is not int or value < 0:
                raise CapabilityDesignError(f"{label} must be a nonnegative exact integer")
        if (
            self.correct_predictions > self.prediction_count
            or self.prediction_count > self.eligible_count
            or self.eligible_count != COUNTERFACTUAL_CELL_COUNT
        ):
            raise CapabilityDesignError("counterfactual counts are inconsistent")
        if any(type(item) is not str or not item for item in self.findings):
            raise CapabilityDesignError("counterfactual finding is invalid")

    @property
    def precision(self) -> float:
        return (
            self.correct_predictions / self.prediction_count
            if self.prediction_count
            else 0.0
        )

    @property
    def coverage(self) -> float:
        return self.prediction_count / self.eligible_count

    def qualifies(self, preregistration: Mapping[str, Any]) -> bool:
        _validate_preregistration(preregistration)
        return (
            self.valid
            and self.correct_predictions == self.prediction_count
            and self.precision >= preregistration["rule_precision_minimum"]
            and self.coverage >= preregistration["rule_coverage_minimum"]
            and self.prediction_count
            >= preregistration["rule_counterfactual_minimum"]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "correct_predictions": self.correct_predictions,
            "prediction_count": self.prediction_count,
            "eligible_count": self.eligible_count,
            "precision": self.precision,
            "coverage": self.coverage,
            "findings": list(self.findings),
        }


def score_counterfactual_rule_set(
    raw_rules: Sequence[Mapping[str, Any]],
    *,
    pair: CapabilityPair,
    preregistration: Mapping[str, Any],
) -> CounterfactualRuleCheck:
    """Execute candidate-carried rules on all 76 hidden modulus-19 cells."""

    _validate_preregistration(preregistration)
    if isinstance(raw_rules, (str, bytes)) or not isinstance(raw_rules, Sequence):
        return CounterfactualRuleCheck(
            False, 0, 0, COUNTERFACTUAL_CELL_COUNT, ("rule set is not a sequence",)
        )
    if len(raw_rules) > SEALED_CANDIDATE_MAX_RULE_HYPOTHESES:
        return CounterfactualRuleCheck(
            False,
            0,
            0,
            COUNTERFACTUAL_CELL_COUNT,
            ("rule set exceeds sealed candidate bound",),
        )
    normalized: dict[str, dict[str, Any]] = {}
    findings: list[str] = []
    for index, raw in enumerate(raw_rules):
        try:
            rule = validate_rule_ir_independently(raw, preregistration)
        except CapabilityDesignError as exc:
            findings.append(f"rule[{index}] invalid: {exc}")
            continue
        signature = rule["action_signature"]
        if signature in normalized:
            findings.append(f"duplicate action signature at rule[{index}]")
            continue
        normalized[signature] = rule
    if findings:
        return CounterfactualRuleCheck(
            False, 0, 0, COUNTERFACTUAL_CELL_COUNT, tuple(findings)
        )
    expected_signatures = {
        item.payload_signature for item in pair.counterfactual.actions
    }
    if not set(normalized) <= expected_signatures:
        return CounterfactualRuleCheck(
            False,
            0,
            0,
            COUNTERFACTUAL_CELL_COUNT,
            ("rule action signature is not evaluator-owned",),
        )
    correct = 0
    predicted = 0
    environment = pair.counterfactual
    for before in range(environment.modulus):
        state_ref = environment.state_ref_for_value(before)
        observation = environment.observation(
            state_ref,
            goal_ref=environment.state_ref_for_value((before + 1) % environment.modulus),
        )
        for action in environment.actions:
            rule = normalized.get(action.payload_signature)
            if rule is None:
                continue
            try:
                output = evaluate_rule_ir_independently(
                    rule, observation, preregistration
                )[REGISTER_PATH]
            except CapabilityDesignError as exc:
                return CounterfactualRuleCheck(
                    False,
                    0,
                    0,
                    COUNTERFACTUAL_CELL_COUNT,
                    (f"rule execution failed: {exc}",),
                )
            predicted += 1
            if output == action.program.apply(before, environment.modulus):
                correct += 1
    return CounterfactualRuleCheck(
        True, correct, predicted, COUNTERFACTUAL_CELL_COUNT
    )


class ReactiveControl:
    """Frozen stateless reactive control, identical to the mechanism policy."""

    @staticmethod
    def choose_action(
        observation: Mapping[str, Any],
        valid_action_refs: Sequence[str],
    ) -> str:
        actions = tuple(valid_action_refs)
        if not actions or any(type(item) is not str or not item for item in actions):
            raise CapabilityDesignError("reactive control requires action refs")
        observation_digest = canonical_digest(dict(observation))
        return min(
            actions,
            key=lambda action: hashlib.sha256(
                (observation_digest + action).encode("utf-8")
            ).hexdigest(),
        )


class RandomControl:
    """Frozen uniform control bound independently to one capability pair."""

    def __init__(self, *, policy_seed: int, pair_binding: str) -> None:
        if type(policy_seed) is not int:
            raise CapabilityDesignError("random seed must be an exact integer")
        if type(pair_binding) is not str or not pair_binding:
            raise CapabilityDesignError("random control pair binding is required")
        self._rng = random.Random(
            _derived_int(
                "gwip-random-control-v1",
                str(policy_seed),
                pair_binding,
            )
        )

    def choose_action(
        self,
        observation: Mapping[str, Any],
        valid_action_refs: Sequence[str],
    ) -> str:
        del observation
        actions = tuple(valid_action_refs)
        if not actions or any(type(item) is not str or not item for item in actions):
            raise CapabilityDesignError("random control requires action refs")
        return actions[self._rng.randrange(len(actions))]


def normalized_regret(
    *,
    success: bool,
    optimal_steps: int,
    executed_steps: int,
    step_budget: int,
) -> float:
    if type(success) is not bool:
        raise CapabilityDesignError("success must be a literal boolean")
    if (
        type(step_budget) is not int
        or step_budget <= 0
        or type(optimal_steps) is not int
        or not 0 < optimal_steps < step_budget
        or type(executed_steps) is not int
        or not 0 <= executed_steps <= step_budget
    ):
        raise CapabilityDesignError("regret counts are outside the frozen domain")
    if not success:
        return 1.0
    if executed_steps < optimal_steps:
        raise CapabilityDesignError("successful episode beats evaluator oracle")
    return (executed_steps - optimal_steps) / (step_budget - optimal_steps)


def utility_from_regret(regret: float) -> float:
    if type(regret) not in (int, float) or not math.isfinite(regret):
        raise CapabilityDesignError("regret must be finite")
    value = float(regret)
    if not 0.0 <= value <= 1.0:
        raise CapabilityDesignError("regret must lie in [0,1]")
    return 1.0 - value


@dataclass(frozen=True)
class EpisodeOutcome:
    pair_index: int
    episode_index: int
    success: bool
    optimal_steps: int
    executed_steps: int
    step_budget: int = 24

    def __post_init__(self) -> None:
        if (
            type(self.pair_index) is not int
            or not 0 <= self.pair_index < 64
            or type(self.episode_index) is not int
            or not 0 <= self.episode_index < 4
            or self.step_budget
            != FROZEN_PREREGISTRATION["step_budget"]
        ):
            raise CapabilityDesignError("episode coordinates are invalid")
        normalized_regret(
            success=self.success,
            optimal_steps=self.optimal_steps,
            executed_steps=self.executed_steps,
            step_budget=self.step_budget,
        )

    @property
    def regret(self) -> float:
        return normalized_regret(
            success=self.success,
            optimal_steps=self.optimal_steps,
            executed_steps=self.executed_steps,
            step_budget=self.step_budget,
        )

    @property
    def utility(self) -> float:
        return utility_from_regret(self.regret)


@dataclass(frozen=True)
class RuleCheckpoint:
    cumulative_action: int
    counterfactual: CounterfactualRuleCheck

    def __post_init__(self) -> None:
        if type(self.cumulative_action) is not int or not 0 <= self.cumulative_action <= 96:
            raise CapabilityDesignError("rule checkpoint action is outside support budget")


@dataclass(frozen=True)
class PairRuleEvidence:
    pair_index: int
    checkpoints: tuple[RuleCheckpoint, ...]
    final_checkpoint: RuleCheckpoint

    def __post_init__(self) -> None:
        if type(self.pair_index) is not int or not 0 <= self.pair_index < 64:
            raise CapabilityDesignError("rule-evidence pair index is invalid")
        actions = [item.cumulative_action for item in self.checkpoints]
        if actions != sorted(set(actions)):
            raise CapabilityDesignError("rule checkpoints must be strictly chronological")
        if actions and actions[-1] > self.final_checkpoint.cumulative_action:
            raise CapabilityDesignError("rule checkpoint follows final support state")


def nearest_rank_percentile(values: Sequence[int | float], quantile: float) -> float:
    if not values or type(quantile) not in (int, float) or not 0 < quantile <= 1:
        raise CapabilityDesignError("nearest-rank percentile input is invalid")
    numeric = [float(item) for item in values]
    if any(not math.isfinite(item) for item in numeric):
        raise CapabilityDesignError("percentile values must be finite")
    numeric.sort()
    rank = math.ceil(float(quantile) * len(numeric))
    return numeric[rank - 1]


def paired_bootstrap_lcb(
    deltas: Sequence[float],
    *,
    resamples: int,
    seed: int,
) -> float:
    if (
        not deltas
        or type(resamples) is not int
        or resamples <= 0
        or type(seed) is not int
    ):
        raise CapabilityDesignError("bootstrap inputs are invalid")
    values = tuple(float(item) for item in deltas)
    if any(not math.isfinite(item) for item in values):
        raise CapabilityDesignError("bootstrap deltas must be finite")
    rng = random.Random(seed)
    count = len(values)
    means = [
        sum(values[rng.randrange(count)] for _ in range(count)) / count
        for _ in range(resamples)
    ]
    means.sort()
    return means[math.ceil(0.05 * resamples) - 1]


def _episode_pair_values(
    outcomes: Sequence[EpisodeOutcome],
    *,
    value: str,
) -> tuple[float, ...]:
    expected = {(pair, episode) for pair in range(64) for episode in range(4)}
    actual = {(item.pair_index, item.episode_index) for item in outcomes}
    if len(outcomes) != 256 or actual != expected:
        raise CapabilityDesignError("episode outcome census is not 64x4")
    grouped: list[list[float]] = [[] for _ in range(64)]
    for item in outcomes:
        if value == "success":
            grouped[item.pair_index].append(float(item.success))
        elif value == "regret":
            grouped[item.pair_index].append(item.regret)
        elif value == "utility":
            grouped[item.pair_index].append(item.utility)
        else:
            raise AssertionError("unknown episode metric")
    return tuple(sum(rows) / len(rows) for rows in grouped)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise CapabilityDesignError("cannot average an empty sequence")
    return sum(values) / len(values)


def _comparison(
    candidate: Sequence[float],
    baseline: Sequence[float],
    *,
    minimum_delta: float,
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    if len(candidate) != 64 or len(baseline) != 64:
        raise CapabilityDesignError("paired comparison must have 64 pair units")
    deltas = tuple(left - right for left, right in zip(candidate, baseline))
    delta = _mean(deltas)
    lcb = paired_bootstrap_lcb(
        deltas,
        resamples=preregistration["bootstrap_resamples"],
        seed=preregistration["bootstrap_seed"],
    )
    return {
        "mean_delta": delta,
        "one_sided_95pct_lcb": lcb,
        "minimum_delta": minimum_delta,
        "minimum_lcb": preregistration["minimum_one_sided_lcb"],
        "passed": (
            delta >= minimum_delta
            and lcb > preregistration["minimum_one_sided_lcb"]
        ),
    }


def derive_rule_discovery(
    evidence: Sequence[PairRuleEvidence],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_preregistration(preregistration)
    if (
        len(evidence) != 64
        or {item.pair_index for item in evidence} != set(range(64))
    ):
        raise CapabilityDesignError("rule evidence census is not 64 pairs")
    censor = preregistration["rule_discovery_censor_action"]
    actions: list[int] = []
    discovered = 0
    final_valid = 0
    for pair in sorted(evidence, key=lambda item: item.pair_index):
        final_passes = pair.final_checkpoint.counterfactual.qualifies(
            preregistration
        )
        if final_passes:
            final_valid += 1
        qualifying = [
            item.cumulative_action
            for item in pair.checkpoints
            if item.counterfactual.qualifies(preregistration)
        ]
        if final_passes and qualifying:
            discovered += 1
            actions.append(min(qualifying))
        else:
            actions.append(censor)
    median = nearest_rank_percentile(actions, 0.5)
    p75 = nearest_rank_percentile(actions, 0.75)
    passed = (
        discovered >= preregistration["rule_discovered_pair_minimum"]
        and median <= preregistration["rule_discovery_median_action_maximum"]
        and p75 <= preregistration["rule_discovery_p75_action_maximum"]
    )
    return {
        "schema_version": "atanor.gwip-rule-discovery-metrics.v1",
        "pair_count": 64,
        "counterfactual_cells_per_pair": COUNTERFACTUAL_CELL_COUNT,
        "discovered_pair_count": discovered,
        "final_valid_pair_count": final_valid,
        "censored_pair_count": 64 - discovered,
        "discovery_actions": actions,
        "median_discovery_action_nearest_rank": median,
        "p75_discovery_action_nearest_rank": p75,
        "thresholds": {
            "precision_minimum": preregistration["rule_precision_minimum"],
            "coverage_minimum": preregistration["rule_coverage_minimum"],
            "counterfactual_minimum": preregistration[
                "rule_counterfactual_minimum"
            ],
            "discovered_pair_minimum": preregistration[
                "rule_discovered_pair_minimum"
            ],
            "median_action_maximum": preregistration[
                "rule_discovery_median_action_maximum"
            ],
            "p75_action_maximum": preregistration[
                "rule_discovery_p75_action_maximum"
            ],
            "censor_action": censor,
        },
        "passed": passed,
    }


def _average_random_pair_values(
    random_outcomes: Mapping[int, Sequence[EpisodeOutcome]],
    *,
    value: str,
    preregistration: Mapping[str, Any],
) -> tuple[float, ...]:
    expected_seeds = tuple(preregistration["random_policy_seeds"])
    if (
        type(random_outcomes) is not dict
        or set(random_outcomes) != set(expected_seeds)
    ):
        raise CapabilityDesignError("random-control seed census mismatch")
    per_seed = [
        _episode_pair_values(random_outcomes[seed], value=value)
        for seed in expected_seeds
    ]
    return tuple(
        sum(rows[pair] for rows in per_seed) / len(per_seed)
        for pair in range(64)
    )


def derive_capability_metrics(
    *,
    candidate_support: Sequence[EpisodeOutcome],
    reactive_support: Sequence[EpisodeOutcome],
    random_support: Mapping[int, Sequence[EpisodeOutcome]],
    target_outcomes: Mapping[str, Sequence[EpisodeOutcome]],
    rule_evidence: Sequence[PairRuleEvidence],
    hard_gates: Mapping[str, bool],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive all frozen metrics and the conjunctive capability verdict."""

    _validate_preregistration(preregistration)
    if type(hard_gates) is not dict or set(hard_gates) != set(REQUIRED_HARD_GATES):
        raise CapabilityDesignError("hard-gate names differ from frozen mechanism gates")
    if any(type(value) is not bool for value in hard_gates.values()):
        raise CapabilityDesignError("hard-gate values must be literal booleans")
    if type(target_outcomes) is not dict or set(target_outcomes) != set(TARGET_ARMS):
        raise CapabilityDesignError("target arm census mismatch")

    candidate_success = _episode_pair_values(candidate_support, value="success")
    reactive_success = _episode_pair_values(reactive_support, value="success")
    random_success = _average_random_pair_values(
        random_support, value="success", preregistration=preregistration
    )
    candidate_regret = _episode_pair_values(candidate_support, value="regret")
    reactive_regret = _episode_pair_values(reactive_support, value="regret")
    random_regret = _average_random_pair_values(
        random_support, value="regret", preregistration=preregistration
    )

    fresh_success_comparisons = {
        "reactive": _comparison(
            candidate_success,
            reactive_success,
            minimum_delta=preregistration["fresh_success_minimum_lift"],
            preregistration=preregistration,
        ),
        "random": _comparison(
            candidate_success,
            random_success,
            minimum_delta=preregistration["fresh_success_minimum_lift"],
            preregistration=preregistration,
        ),
    }
    fresh_success = {
        "candidate_mean": _mean(candidate_success),
        "reactive_mean": _mean(reactive_success),
        "random_32_seed_mean": _mean(random_success),
        "candidate_minimum": preregistration["fresh_success_minimum"],
        "comparisons": fresh_success_comparisons,
    }
    fresh_success["passed"] = (
        fresh_success["candidate_mean"] >= preregistration["fresh_success_minimum"]
        and all(item["passed"] for item in fresh_success_comparisons.values())
    )

    fresh_regret_comparisons = {
        "reactive": _comparison(
            reactive_regret,
            candidate_regret,
            minimum_delta=preregistration[
                "fresh_normalized_regret_minimum_reduction"
            ],
            preregistration=preregistration,
        ),
        "random": _comparison(
            random_regret,
            candidate_regret,
            minimum_delta=preregistration[
                "fresh_normalized_regret_minimum_reduction"
            ],
            preregistration=preregistration,
        ),
    }
    fresh_regret = {
        "candidate_mean": _mean(candidate_regret),
        "reactive_mean": _mean(reactive_regret),
        "random_32_seed_mean": _mean(random_regret),
        "candidate_maximum": preregistration[
            "fresh_normalized_regret_maximum"
        ],
        "comparisons": fresh_regret_comparisons,
    }
    fresh_regret["passed"] = (
        fresh_regret["candidate_mean"]
        <= preregistration["fresh_normalized_regret_maximum"]
        and all(item["passed"] for item in fresh_regret_comparisons.values())
    )

    target_success = {
        arm: _episode_pair_values(target_outcomes[arm], value="success")
        for arm in TARGET_ARMS
    }
    target_regret = {
        arm: _episode_pair_values(target_outcomes[arm], value="regret")
        for arm in TARGET_ARMS
    }
    target_utility = {
        arm: _episode_pair_values(target_outcomes[arm], value="utility")
        for arm in TARGET_ARMS
    }
    transfer_success_comparisons = {
        control: _comparison(
            target_success[MATCHED_WARM_ARM],
            target_success[control],
            minimum_delta=preregistration["transfer_success_minimum_lift"],
            preregistration=preregistration,
        )
        for control in (COLD_ARM, MISMATCHED_WARM_ARM)
    }
    transfer_regret_comparisons = {
        control: _comparison(
            target_regret[control],
            target_regret[MATCHED_WARM_ARM],
            minimum_delta=preregistration[
                "transfer_normalized_regret_minimum_reduction"
            ],
            preregistration=preregistration,
        )
        for control in (COLD_ARM, MISMATCHED_WARM_ARM)
    }
    transfer_score_comparisons = {
        control: _comparison(
            target_utility[MATCHED_WARM_ARM],
            target_utility[control],
            minimum_delta=preregistration["transfer_score_minimum"],
            preregistration=preregistration,
        )
        for control in (COLD_ARM, MISMATCHED_WARM_ARM)
    }
    transfer = {
        "success_means": {
            arm: _mean(target_success[arm]) for arm in TARGET_ARMS
        },
        "regret_means": {
            arm: _mean(target_regret[arm]) for arm in TARGET_ARMS
        },
        "utility_means": {
            arm: _mean(target_utility[arm]) for arm in TARGET_ARMS
        },
        "success_comparisons": transfer_success_comparisons,
        "regret_comparisons": transfer_regret_comparisons,
        "score_comparisons": transfer_score_comparisons,
        "thresholds": {
            "success_minimum": preregistration["transfer_success_minimum"],
            "success_lift_minimum": preregistration[
                "transfer_success_minimum_lift"
            ],
            "regret_maximum": preregistration[
                "transfer_normalized_regret_maximum"
            ],
            "regret_reduction_minimum": preregistration[
                "transfer_normalized_regret_minimum_reduction"
            ],
            "score_minimum": preregistration["transfer_score_minimum"],
        },
    }
    transfer["passed"] = (
        transfer["success_means"][MATCHED_WARM_ARM]
        >= preregistration["transfer_success_minimum"]
        and transfer["regret_means"][MATCHED_WARM_ARM]
        <= preregistration["transfer_normalized_regret_maximum"]
        and all(item["passed"] for item in transfer_success_comparisons.values())
        and all(item["passed"] for item in transfer_regret_comparisons.values())
        and all(item["passed"] for item in transfer_score_comparisons.values())
    )

    rule_discovery = derive_rule_discovery(rule_evidence, preregistration)
    metric_passes = {
        "fresh_success": fresh_success["passed"],
        "rule_discovery": rule_discovery["passed"],
        "fresh_regret": fresh_regret["passed"],
        "transfer": transfer["passed"],
    }
    hard_gates_passed = all(hard_gates.values())
    all_metrics_passed = all(metric_passes.values())
    if not hard_gates_passed:
        verdict = "CAPABILITY_RED"
    elif all_metrics_passed:
        verdict = "CAPABILITY_GREEN"
    else:
        verdict = "NO_GO"
    explanatory_sublabel = (
        "FRESH_REPLICATION_ONLY"
        if verdict == "NO_GO"
        and fresh_success["passed"]
        and fresh_regret["passed"]
        and (not rule_discovery["passed"] or not transfer["passed"])
        else None
    )
    return {
        "schema_version": "atanor.gwip-capability-metrics.v1",
        "bootstrap": {
            "unit": "pair",
            "resamples": preregistration["bootstrap_resamples"],
            "seed": preregistration["bootstrap_seed"],
            "one_sided_lcb": "nearest_rank_5pct",
        },
        "hard_gates": dict(hard_gates),
        "hard_gates_passed": hard_gates_passed,
        "fresh_success": fresh_success,
        "rule_discovery": rule_discovery,
        "fresh_regret": fresh_regret,
        "transfer": transfer,
        "metric_sections_passed": metric_passes,
        "all_metrics_passed": all_metrics_passed,
        "verdict": verdict,
        "explanatory_sublabel": explanatory_sublabel,
        "capability_claim": verdict == "CAPABILITY_GREEN",
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
    }


def select_human_exemplar(
    candidate_support: Sequence[EpisodeOutcome],
) -> tuple[int, int]:
    """Frozen best-efficiency selector; rendering remains evaluator-owned."""

    _episode_pair_values(candidate_support, value="regret")
    successful = [item for item in candidate_support if item.success]
    if not successful:
        return (0, 0)
    selected = min(
        successful,
        key=lambda item: (
            item.regret,
            item.executed_steps,
            item.pair_index,
            item.episode_index,
        ),
    )
    return selected.pair_index, selected.episode_index


__all__ = [
    "AffineProgram",
    "CapabilityAction",
    "CapabilityDesignError",
    "CapabilityEnvironment",
    "CapabilityEpisode",
    "CapabilityPair",
    "CapabilityTransition",
    "COLD_ARM",
    "CONTEXT_PATH",
    "COUNTERFACTUAL_CELL_COUNT",
    "CounterfactualRuleCheck",
    "EpisodeOutcome",
    "FROZEN_PREREGISTRATION",
    "MATCHED_WARM_ARM",
    "MISMATCHED_WARM_ARM",
    "PairRuleEvidence",
    "PriorMechanismNonoverlapInput",
    "REACTIVE_ARM",
    "REGISTER_PATH",
    "REQUIRED_HARD_GATES",
    "RULE_IR_SCHEMA",
    "RandomControl",
    "ReactiveControl",
    "RuleCheckpoint",
    "SOURCE_ARM",
    "TARGET_ARMS",
    "audit_prior_mechanism_nonoverlap",
    "build_prior_mechanism_nonoverlap_input",
    "candidate_schedule_rows",
    "canonical_digest",
    "canonical_json",
    "capability_nonoverlap_inventory",
    "derive_capability_metrics",
    "derive_rule_discovery",
    "evaluate_rule_ir_independently",
    "generate_capability_pairs",
    "load_preregistration",
    "nearest_rank_percentile",
    "normalized_regret",
    "paired_bootstrap_lcb",
    "private_cohort_digest",
    "project_evaluator_features",
    "score_counterfactual_rule_set",
    "select_human_exemplar",
    "support_semantic_ordinal",
    "target_arm_order",
    "target_semantic_ordinal",
    "utility_from_regret",
    "validate_rule_ir_independently",
]
