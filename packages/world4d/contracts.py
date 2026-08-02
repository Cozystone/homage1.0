"""Frozen contracts for the default-off World4D shadow seam.

The contracts preserve the distinction between observation, prediction, and
retrodiction.  A bounded check may say that a proposal was not contradicted by
that check; it can never promote a hypothesis to fact or authorize live use.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import math
from typing import Any

from packages.cognitive_core.canonical import FrozenMap, canonical_id
from packages.cognitive_core.contracts import EpistemicTier


SCHEMA_VERSION = "atanor.world4d.shadow.v1"
MAX_TRAJECTORIES = 4
MAX_STEPS = 3
MAX_CHECKS = 8
MAX_METADATA_ITEMS = 16
MAX_METADATA_TEXT_BYTES = 512
MAX_RECEIPT_BYTES = 8 * 1024
SHADOW_RECEIPT_LIMITATIONS = (
    "default_off_sibling_observer",
    "shadow_output_ignored_by_answer_arbitration",
    "legacy_block_universe_bidder_remains_separate",
    "provider_effects_not_attested",
    "provider_isolation_not_enforced",
    "no_production_trace",
    "no_external_evaluator",
    "no_jepa_checkpoint_provider",
    "no_splatra_inference_provider",
    "no_e4_or_e5_claim",
)
SHADOW_ERROR_KINDS = frozenset({"provider_observation_error"})


class Direction(str, Enum):
    FORWARD = "forward"
    BACKWARD = "backward"


class CheckScope(str, Enum):
    PHYSICAL = "physical"
    TEMPORAL_LOGICAL = "temporal_logical"
    STATISTICAL = "statistical"


class CheckVerdict(str, Enum):
    NOT_RUN = "not_run"
    NOT_CONTRADICTED = "not_contradicted"
    CONTRADICTED = "contradicted"


class ProviderResultStatus(str, Enum):
    PROPOSED = "proposed"
    ABSTAINED = "abstained"
    QUARANTINED = "quarantined"


def _text(
    value: Any,
    name: str,
    *,
    optional: bool = False,
    maximum_text_bytes: int = MAX_METADATA_TEXT_BYTES,
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if len(value) > maximum_text_bytes:
        raise ValueError(
            f"{name} cannot exceed {maximum_text_bytes} UTF-8 bytes"
        )
    if len(value.encode("utf-8")) > maximum_text_bytes:
        raise ValueError(
            f"{name} cannot exceed {maximum_text_bytes} UTF-8 bytes"
        )
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    if len(normalized.encode("utf-8")) > maximum_text_bytes:
        raise ValueError(
            f"{name} cannot exceed {maximum_text_bytes} UTF-8 bytes"
        )
    return normalized


def _digest(value: Any, name: str, *, optional: bool = False) -> str | None:
    normalized = _text(value, name, optional=optional)
    if normalized is None:
        return None
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return normalized


def _integer(
    value: Any,
    name: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f"..{maximum}" if maximum is not None else " or greater"
        raise ValueError(f"{name} must be within {minimum}{suffix}")
    return value


def _confidence(value: Any, name: str = "confidence") -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number or null")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be finite and within [0, 1]")
    return number


def _strings(
    values: Iterable[Any],
    name: str,
    *,
    maximum_items: int = MAX_METADATA_ITEMS,
    maximum_text_bytes: int = MAX_METADATA_TEXT_BYTES,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable, not a string")
    normalized_values: list[str] = []
    for index, value in enumerate(values):
        if index >= maximum_items:
            raise ValueError(f"{name} cannot contain more than {maximum_items} items")
        normalized = str(_text(value, name))
        if len(normalized.encode("utf-8")) > maximum_text_bytes:
            raise ValueError(
                f"{name} items cannot exceed {maximum_text_bytes} UTF-8 bytes"
            )
        normalized_values.append(normalized)
    normalized = tuple(normalized_values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} cannot contain duplicates")
    return normalized


def _bounded_tuple(
    values: Iterable[Any],
    name: str,
    *,
    maximum_items: int,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable, not a string")
    result: list[Any] = []
    for index, value in enumerate(values):
        if index >= maximum_items:
            raise ValueError(
                f"{name} cannot contain more than {maximum_items} items"
            )
        result.append(value)
    return tuple(result)


def _utc(value: Any, name: str) -> str:
    normalized = str(_text(value, name))
    if not normalized.endswith("Z"):
        raise ValueError(f"{name} must end in Z")
    try:
        datetime.fromisoformat(normalized[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name} must be ISO-8601 UTC") from error
    return normalized


def _fixed(value: Any, expected: bool, name: str) -> None:
    if value is not expected:
        raise ValueError(f"{name} must be literal {expected!r}")


def _expect_keys(
    value: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    actual: set[str] = set()
    for index, key in enumerate(value):
        if index >= len(expected) + 1:
            raise ValueError(f"{name} contains too many keys")
        if not isinstance(key, str):
            raise TypeError(f"{name} keys must be strings")
        actual.add(key)
    if actual != expected:
        raise ValueError(
            f"{name} keys invalid: "
            f"missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _expect_schema(value: Mapping[str, Any], name: str) -> None:
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"{name} schema_version is unsupported")


@dataclass(frozen=True, kw_only=True)
class World4DRequest:
    request_id: str
    source_kind: str
    source_digest: str
    direction: Direction
    horizon: int = 3
    branch_limit: int = 4
    world_snapshot_id: str | None = None
    source_refs: Sequence[str] = ()
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    read_only: bool = field(default=True, init=False)
    truth_mutation_allowed: bool = field(default=False, init=False)
    action_authority: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "source_kind", _text(self.source_kind, "source_kind"))
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        object.__setattr__(self, "direction", Direction(self.direction))
        object.__setattr__(
            self,
            "horizon",
            _integer(self.horizon, "horizon", minimum=1, maximum=MAX_STEPS),
        )
        object.__setattr__(
            self,
            "branch_limit",
            _integer(
                self.branch_limit,
                "branch_limit",
                minimum=1,
                maximum=MAX_TRAJECTORIES,
            ),
        )
        object.__setattr__(
            self,
            "world_snapshot_id",
            _text(self.world_snapshot_id, "world_snapshot_id", optional=True),
        )
        object.__setattr__(self, "source_refs", _strings(self.source_refs, "source_refs"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_authority": self.action_authority,
            "branch_limit": self.branch_limit,
            "direction": self.direction.value,
            "horizon": self.horizon,
            "read_only": self.read_only,
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "source_digest": self.source_digest,
            "source_kind": self.source_kind,
            "source_refs": list(self.source_refs),
            "truth_mutation_allowed": self.truth_mutation_allowed,
            "world_snapshot_id": self.world_snapshot_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DRequest":
        _expect_keys(
            value,
            {
                "action_authority",
                "branch_limit",
                "direction",
                "horizon",
                "read_only",
                "request_id",
                "schema_version",
                "source_digest",
                "source_kind",
                "source_refs",
                "truth_mutation_allowed",
                "world_snapshot_id",
            },
            "world4d request",
        )
        _expect_schema(value, "world4d request")
        _fixed(value["read_only"], True, "read_only")
        _fixed(value["truth_mutation_allowed"], False, "truth_mutation_allowed")
        _fixed(value["action_authority"], False, "action_authority")
        return cls(
            request_id=value["request_id"],
            source_kind=value["source_kind"],
            source_digest=value["source_digest"],
            direction=Direction(value["direction"]),
            horizon=value["horizon"],
            branch_limit=value["branch_limit"],
            world_snapshot_id=value["world_snapshot_id"],
            source_refs=value["source_refs"],
        )


@dataclass(frozen=True, kw_only=True)
class World4DProviderDescriptor:
    provider_id: str
    provider_version: str
    input_kind: str
    source_refs: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        object.__setattr__(
            self,
            "provider_version",
            _text(self.provider_version, "provider_version"),
        )
        object.__setattr__(self, "input_kind", _text(self.input_kind, "input_kind"))
        object.__setattr__(self, "source_refs", _strings(self.source_refs, "source_refs"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_kind": self.input_kind,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "source_refs": list(self.source_refs),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DProviderDescriptor":
        _expect_keys(
            value,
            {"input_kind", "provider_id", "provider_version", "source_refs"},
            "world4d provider descriptor",
        )
        return cls(
            provider_id=value["provider_id"],
            provider_version=value["provider_version"],
            input_kind=value["input_kind"],
            source_refs=value["source_refs"],
        )


@dataclass(frozen=True, kw_only=True)
class World4DCheck:
    check_id: str
    scope: CheckScope
    verdict: CheckVerdict
    details_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _text(self.check_id, "check_id"))
        object.__setattr__(self, "scope", CheckScope(self.scope))
        object.__setattr__(self, "verdict", CheckVerdict(self.verdict))
        object.__setattr__(
            self,
            "details_digest",
            _digest(self.details_digest, "details_digest", optional=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "details_digest": self.details_digest,
            "scope": self.scope.value,
            "verdict": self.verdict.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DCheck":
        _expect_keys(
            value,
            {"check_id", "details_digest", "scope", "verdict"},
            "world4d check",
        )
        return cls(
            check_id=value["check_id"],
            scope=CheckScope(value["scope"]),
            verdict=CheckVerdict(value["verdict"]),
            details_digest=value["details_digest"],
        )


@dataclass(frozen=True, kw_only=True)
class World4DStep:
    step_index: int
    state_digest: str
    confidence: float | None
    tier: EpistemicTier
    hypothesis: bool = field(default=True, init=False)
    accepted_as_fact: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_index",
            _integer(
                self.step_index,
                "step_index",
                minimum=1,
                maximum=MAX_STEPS,
            ),
        )
        object.__setattr__(self, "state_digest", _digest(self.state_digest, "state_digest"))
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        tier = EpistemicTier(self.tier)
        if tier not in {EpistemicTier.PREDICTED, EpistemicTier.RETRODICTED}:
            raise ValueError("world4d steps must be predicted or retrodicted")
        object.__setattr__(self, "tier", tier)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_as_fact": self.accepted_as_fact,
            "confidence": self.confidence,
            "hypothesis": self.hypothesis,
            "state_digest": self.state_digest,
            "step_index": self.step_index,
            "tier": self.tier.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DStep":
        _expect_keys(
            value,
            {
                "accepted_as_fact",
                "confidence",
                "hypothesis",
                "state_digest",
                "step_index",
                "tier",
            },
            "world4d step",
        )
        _fixed(value["hypothesis"], True, "hypothesis")
        _fixed(value["accepted_as_fact"], False, "accepted_as_fact")
        return cls(
            step_index=value["step_index"],
            state_digest=value["state_digest"],
            confidence=value["confidence"],
            tier=EpistemicTier(value["tier"]),
        )


@dataclass(frozen=True, kw_only=True)
class World4DTrajectory:
    branch_id: str
    initial_state_digest: str
    steps: Sequence[World4DStep]
    checks: Sequence[World4DCheck]
    quarantined: bool = False
    authoritative: bool = field(default=False, init=False)
    eligible_for_live_use: bool = field(default=False, init=False)
    truth_mutation_allowed: bool = field(default=False, init=False)
    training_mutation_allowed: bool = field(default=False, init=False)
    trajectory_id: str = field(init=False)

    def __post_init__(self) -> None:
        branch_id = _text(self.branch_id, "branch_id")
        initial_state_digest = _digest(
            self.initial_state_digest,
            "initial_state_digest",
        )
        steps = _bounded_tuple(
            self.steps,
            "steps",
            maximum_items=MAX_STEPS,
        )
        checks = _bounded_tuple(
            self.checks,
            "checks",
            maximum_items=MAX_CHECKS,
        )
        if not 1 <= len(steps) <= MAX_STEPS:
            raise ValueError(f"trajectory must contain 1..{MAX_STEPS} steps")
        if not all(isinstance(item, World4DStep) for item in steps):
            raise TypeError("steps must contain World4DStep values")
        if [item.step_index for item in steps] != list(range(1, len(steps) + 1)):
            raise ValueError("trajectory step indexes must be contiguous from one")
        if not all(isinstance(item, World4DCheck) for item in checks):
            raise TypeError("checks must contain World4DCheck values")
        if len({item.check_id for item in checks}) != len(checks):
            raise ValueError("trajectory checks cannot contain duplicate IDs")
        if not isinstance(self.quarantined, bool):
            raise TypeError("quarantined must be a literal boolean")
        if any(item.verdict is CheckVerdict.CONTRADICTED for item in checks) and not self.quarantined:
            raise ValueError("a contradicted trajectory must be quarantined")
        trajectory_id, _ = canonical_id(
            "world4d_trajectory",
            {
                "branch_id": branch_id,
                "checks": [item.to_dict() for item in checks],
                "initial_state_digest": initial_state_digest,
                "quarantined": self.quarantined,
                "steps": [item.to_dict() for item in steps],
            },
        )
        object.__setattr__(self, "branch_id", branch_id)
        object.__setattr__(self, "initial_state_digest", initial_state_digest)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "checks", checks)
        object.__setattr__(self, "trajectory_id", trajectory_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "branch_id": self.branch_id,
            "checks": [item.to_dict() for item in self.checks],
            "eligible_for_live_use": self.eligible_for_live_use,
            "initial_state_digest": self.initial_state_digest,
            "quarantined": self.quarantined,
            "steps": [item.to_dict() for item in self.steps],
            "training_mutation_allowed": self.training_mutation_allowed,
            "trajectory_id": self.trajectory_id,
            "truth_mutation_allowed": self.truth_mutation_allowed,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DTrajectory":
        _expect_keys(
            value,
            {
                "authoritative",
                "branch_id",
                "checks",
                "eligible_for_live_use",
                "initial_state_digest",
                "quarantined",
                "steps",
                "training_mutation_allowed",
                "trajectory_id",
                "truth_mutation_allowed",
            },
            "world4d trajectory",
        )
        fixed = {
            "authoritative": False,
            "eligible_for_live_use": False,
            "training_mutation_allowed": False,
            "truth_mutation_allowed": False,
        }
        for name, expected in fixed.items():
            _fixed(value[name], expected, name)
        trajectory = cls(
            branch_id=value["branch_id"],
            initial_state_digest=value["initial_state_digest"],
            steps=tuple(World4DStep.from_dict(item) for item in value["steps"]),
            checks=tuple(World4DCheck.from_dict(item) for item in value["checks"]),
            quarantined=value["quarantined"],
        )
        if value["trajectory_id"] != trajectory.trajectory_id:
            raise ValueError("world4d trajectory ID does not match content")
        return trajectory


@dataclass(frozen=True, kw_only=True)
class World4DProviderResult:
    provider_id: str
    provider_version: str
    status: ProviderResultStatus
    trajectories: Sequence[World4DTrajectory]
    limitations: Sequence[str] = ()
    model_artifact_digest: str | None = None
    authoritative: bool = field(default=False, init=False)
    eligible_for_live_use: bool = field(default=False, init=False)
    result_id: str = field(init=False)

    def __post_init__(self) -> None:
        provider_id = _text(self.provider_id, "provider_id")
        provider_version = _text(self.provider_version, "provider_version")
        status = ProviderResultStatus(self.status)
        trajectories = _bounded_tuple(
            self.trajectories,
            "trajectories",
            maximum_items=MAX_TRAJECTORIES,
        )
        if not all(isinstance(item, World4DTrajectory) for item in trajectories):
            raise TypeError("trajectories must contain World4DTrajectory values")
        if len({item.branch_id for item in trajectories}) != len(trajectories):
            raise ValueError("provider trajectories cannot reuse branch IDs")
        if status is ProviderResultStatus.PROPOSED and not trajectories:
            raise ValueError("proposed provider result requires trajectories")
        if status is ProviderResultStatus.PROPOSED and any(
            item.quarantined for item in trajectories
        ):
            raise ValueError("proposed provider result cannot contain quarantine")
        if status is ProviderResultStatus.ABSTAINED and trajectories:
            raise ValueError("abstained provider result cannot contain trajectories")
        if status is ProviderResultStatus.QUARANTINED and (
            not trajectories or not all(item.quarantined for item in trajectories)
        ):
            raise ValueError("quarantined result requires only quarantined trajectories")
        limitations = _strings(self.limitations, "limitations")
        artifact = _digest(
            self.model_artifact_digest,
            "model_artifact_digest",
            optional=True,
        )
        result_id, _ = canonical_id(
            "world4d_provider_result",
            {
                "limitations": limitations,
                "model_artifact_digest": artifact,
                "provider_id": provider_id,
                "provider_version": provider_version,
                "status": status.value,
                "trajectories": [item.to_dict() for item in trajectories],
            },
        )
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "provider_version", provider_version)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "trajectories", trajectories)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(self, "model_artifact_digest", artifact)
        object.__setattr__(self, "result_id", result_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "eligible_for_live_use": self.eligible_for_live_use,
            "limitations": list(self.limitations),
            "model_artifact_digest": self.model_artifact_digest,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "result_id": self.result_id,
            "status": self.status.value,
            "trajectories": [item.to_dict() for item in self.trajectories],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DProviderResult":
        _expect_keys(
            value,
            {
                "authoritative",
                "eligible_for_live_use",
                "limitations",
                "model_artifact_digest",
                "provider_id",
                "provider_version",
                "result_id",
                "status",
                "trajectories",
            },
            "world4d provider result",
        )
        _fixed(value["authoritative"], False, "authoritative")
        _fixed(value["eligible_for_live_use"], False, "eligible_for_live_use")
        result = cls(
            provider_id=value["provider_id"],
            provider_version=value["provider_version"],
            status=ProviderResultStatus(value["status"]),
            trajectories=tuple(
                World4DTrajectory.from_dict(item)
                for item in value["trajectories"]
            ),
            limitations=value["limitations"],
            model_artifact_digest=value["model_artifact_digest"],
        )
        if value["result_id"] != result.result_id:
            raise ValueError("world4d provider result ID does not match content")
        return result


@dataclass(frozen=True, kw_only=True)
class World4DShadowReceipt:
    request_digest: str
    provider_descriptor_digest: str
    provider_result_digest: str | None
    provider_status: str
    trajectory_count: int
    step_count: int
    check_summary: Mapping[str, Any] | FrozenMap
    created_at_utc: str
    model_artifact_digest: str | None = None
    error_kind: str | None = None
    limitations: Sequence[str] = ()
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    mode: str = field(default="shadow", init=False)
    observer_only: bool = field(default=True, init=False)
    adapter_answer_influenced: bool = field(default=False, init=False)
    adapter_output_applied: bool = field(default=False, init=False)
    provider_effects_attested: bool = field(default=False, init=False)
    provider_isolation_enforced: bool = field(default=False, init=False)
    capability_claims: tuple[str, ...] = field(default=(), init=False)
    e4_claimed: bool = field(default=False, init=False)
    e5_claimed: bool = field(default=False, init=False)
    receipt_id: str = field(init=False)

    def __post_init__(self) -> None:
        request_digest = _digest(self.request_digest, "request_digest")
        descriptor_digest = _digest(
            self.provider_descriptor_digest,
            "provider_descriptor_digest",
        )
        result_digest = _digest(
            self.provider_result_digest,
            "provider_result_digest",
            optional=True,
        )
        artifact_digest = _digest(
            self.model_artifact_digest,
            "model_artifact_digest",
            optional=True,
        )
        provider_status = _text(self.provider_status, "provider_status")
        allowed_statuses = {
            status.value for status in ProviderResultStatus
        } | {"error"}
        if provider_status not in allowed_statuses:
            raise ValueError("provider_status is not a frozen World4D status")
        trajectory_count = _integer(
            self.trajectory_count,
            "trajectory_count",
            minimum=0,
            maximum=MAX_TRAJECTORIES,
        )
        step_count = _integer(
            self.step_count,
            "step_count",
            minimum=0,
            maximum=MAX_TRAJECTORIES * MAX_STEPS,
        )
        expected_summary_keys = {verdict.value for verdict in CheckVerdict}
        if not isinstance(self.check_summary, Mapping):
            raise TypeError("check_summary must be a mapping")
        raw_summary: dict[str, Any] = {}
        for index, (key, value) in enumerate(self.check_summary.items()):
            if index >= len(expected_summary_keys):
                raise ValueError("check_summary exceeds the frozen verdict keys")
            raw_summary[key] = value
        if set(raw_summary) != expected_summary_keys:
            raise ValueError("check_summary must contain the frozen verdict keys")
        clean_summary = {
            key: _integer(
                raw_summary[key],
                f"check_summary.{key}",
                minimum=0,
                maximum=MAX_TRAJECTORIES * MAX_CHECKS,
            )
            for key in sorted(expected_summary_keys)
        }
        check_count = sum(clean_summary.values())
        if check_count > trajectory_count * MAX_CHECKS:
            raise ValueError("check_summary exceeds the trajectory-bound check count")
        check_summary = FrozenMap(clean_summary)
        created_at_utc = _utc(self.created_at_utc, "created_at_utc")
        error_kind = _text(self.error_kind, "error_kind", optional=True)
        limitations = _strings(self.limitations, "limitations")
        if error_kind is not None and error_kind not in SHADOW_ERROR_KINDS:
            raise ValueError("error_kind must use a frozen privacy-safe code")
        if any(
            limitation not in SHADOW_RECEIPT_LIMITATIONS
            for limitation in limitations
        ):
            raise ValueError("shadow receipt limitations must use frozen codes")
        if provider_status == "error":
            if (
                result_digest is not None
                or trajectory_count
                or step_count
                or check_count
                or error_kind is None
            ):
                raise ValueError("error receipts cannot carry provider output")
        else:
            if result_digest is None:
                raise ValueError("non-error receipts require a provider result digest")
            if error_kind is not None:
                raise ValueError("non-error receipts cannot carry error_kind")
            if provider_status == ProviderResultStatus.ABSTAINED.value:
                if trajectory_count or step_count or check_count:
                    raise ValueError(
                        "abstained receipts cannot count provider output"
                    )
            elif (
                provider_status == ProviderResultStatus.PROPOSED.value
                and clean_summary[CheckVerdict.CONTRADICTED.value] != 0
            ):
                raise ValueError(
                    "proposed receipts cannot report contradicted checks"
                )
            elif (
                trajectory_count < 1
                or step_count < trajectory_count
                or step_count > trajectory_count * MAX_STEPS
            ):
                raise ValueError(
                    "proposed or quarantined receipt counts are inconsistent"
                )
        receipt_id, _ = canonical_id(
            "world4d_shadow_receipt",
            {
                "check_summary": check_summary,
                "created_at_utc": created_at_utc,
                "error_kind": error_kind,
                "limitations": limitations,
                "model_artifact_digest": artifact_digest,
                "provider_descriptor_digest": descriptor_digest,
                "provider_result_digest": result_digest,
                "provider_status": provider_status,
                "request_digest": request_digest,
                "step_count": step_count,
                "trajectory_count": trajectory_count,
            },
        )
        object.__setattr__(self, "request_digest", request_digest)
        object.__setattr__(self, "provider_descriptor_digest", descriptor_digest)
        object.__setattr__(self, "provider_result_digest", result_digest)
        object.__setattr__(self, "model_artifact_digest", artifact_digest)
        object.__setattr__(self, "provider_status", provider_status)
        object.__setattr__(self, "trajectory_count", trajectory_count)
        object.__setattr__(self, "step_count", step_count)
        object.__setattr__(self, "check_summary", check_summary)
        object.__setattr__(self, "created_at_utc", created_at_utc)
        object.__setattr__(self, "error_kind", error_kind)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(self, "receipt_id", receipt_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_answer_influenced": self.adapter_answer_influenced,
            "adapter_output_applied": self.adapter_output_applied,
            "capability_claims": list(self.capability_claims),
            "check_summary": self.check_summary.to_dict(),
            "created_at_utc": self.created_at_utc,
            "e4_claimed": self.e4_claimed,
            "e5_claimed": self.e5_claimed,
            "error_kind": self.error_kind,
            "limitations": list(self.limitations),
            "mode": self.mode,
            "model_artifact_digest": self.model_artifact_digest,
            "observer_only": self.observer_only,
            "provider_effects_attested": self.provider_effects_attested,
            "provider_isolation_enforced": self.provider_isolation_enforced,
            "provider_descriptor_digest": self.provider_descriptor_digest,
            "provider_result_digest": self.provider_result_digest,
            "provider_status": self.provider_status,
            "receipt_id": self.receipt_id,
            "request_digest": self.request_digest,
            "schema_version": self.schema_version,
            "step_count": self.step_count,
            "trajectory_count": self.trajectory_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "World4DShadowReceipt":
        _expect_keys(
            value,
            {
                "adapter_answer_influenced",
                "adapter_output_applied",
                "capability_claims",
                "check_summary",
                "created_at_utc",
                "e4_claimed",
                "e5_claimed",
                "error_kind",
                "limitations",
                "mode",
                "model_artifact_digest",
                "observer_only",
                "provider_descriptor_digest",
                "provider_effects_attested",
                "provider_isolation_enforced",
                "provider_result_digest",
                "provider_status",
                "receipt_id",
                "request_digest",
                "schema_version",
                "step_count",
                "trajectory_count",
            },
            "world4d shadow receipt",
        )
        _expect_schema(value, "world4d shadow receipt")
        fixed = {
            "adapter_answer_influenced": False,
            "adapter_output_applied": False,
            "e4_claimed": False,
            "e5_claimed": False,
            "observer_only": True,
            "provider_effects_attested": False,
            "provider_isolation_enforced": False,
        }
        for name, expected in fixed.items():
            _fixed(value[name], expected, name)
        if value["mode"] != "shadow":
            raise ValueError("world4d receipt mode must be shadow")
        if value["capability_claims"] != []:
            raise ValueError("world4d shadow receipt cannot carry capability claims")
        receipt = cls(
            request_digest=value["request_digest"],
            provider_descriptor_digest=value["provider_descriptor_digest"],
            provider_result_digest=value["provider_result_digest"],
            provider_status=value["provider_status"],
            trajectory_count=value["trajectory_count"],
            step_count=value["step_count"],
            check_summary=value["check_summary"],
            created_at_utc=value["created_at_utc"],
            model_artifact_digest=value["model_artifact_digest"],
            error_kind=value["error_kind"],
            limitations=value["limitations"],
        )
        if value["receipt_id"] != receipt.receipt_id:
            raise ValueError("world4d shadow receipt ID does not match content")
        return receipt
