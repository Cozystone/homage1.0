"""Frozen M1 contracts for ATANOR's canonical cognitive spine.

These records carry cognition, provenance, and shadow decisions between organs.
They do not grant action authority.  In particular, :class:`CognitiveEnvelope`
is not, does not implement, and cannot replace ``AutonomyEnvelope``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from enum import Enum
import math
import re
from typing import Any, ClassVar

from packages.cognitive_core.canonical import (
    SCHEMA_VERSION,
    FrozenMap,
    canonical_id,
    thaw_json,
)


class GoalOrigin(str, Enum):
    """Where a goal came from; origin and local priority are separate dimensions."""

    EXPLICIT_USER = "explicit_user"
    DELEGATED_USER = "delegated_user"
    SYSTEM_MAINTENANCE = "system_maintenance"
    INTRINSIC = "intrinsic"


class EpistemicTier(str, Enum):
    """Provenance status, not a probability or confidence bucket."""

    OBSERVED = "observed"
    RECORDED = "recorded"
    INFERRED = "inferred"
    PREDICTED = "predicted"
    RETRODICTED = "retrodicted"
    UNKNOWN = "unknown"


class ReceiptMode(str, Enum):
    """M1 receipts are observational only; there is deliberately no live mode."""

    SHADOW = "shadow"
    READ_ONLY = "read_only"


_PREDICTIVE_TIERS = frozenset({EpistemicTier.PREDICTED, EpistemicTier.RETRODICTED})
_OBSERVATION_TIERS = frozenset({EpistemicTier.OBSERVED, EpistemicTier.RECORDED})
_CONTROL_KEY_PATTERN = re.compile(
    r"(truth|safety|permission|authority|policy|authorize|approve|accept_as_fact)",
    re.IGNORECASE,
)


def _text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = " ".join(value.split())
    if not normalized and not allow_empty:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _ids(values: Iterable[Any], name: str, *, ordered: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of IDs, not a string")
    normalized = tuple(_text(value, name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} cannot contain duplicate IDs")
    return normalized if ordered else tuple(sorted(normalized))


def _strings(values: Iterable[Any], name: str, *, ordered: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings, not a string")
    normalized = tuple(_text(value, name) for value in values)
    return normalized if ordered else tuple(sorted(set(normalized)))


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("confidence must be numeric, not boolean")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("confidence must be finite and between 0 and 1")
    return number


def _priority(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError("priority must be an integer, not a boolean")
    number = int(value)
    if number != value or not 0 <= number <= 100:
        raise ValueError("priority must be an integer between 0 and 100")
    return number


def _numeric_map(
    value: Mapping[str, Any] | FrozenMap,
    name: str,
    *,
    nonnegative: bool,
) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    normalized: dict[str, float] = {}
    for key, raw in value.items():
        key_text = _text(key, f"{name} key")
        if _CONTROL_KEY_PATTERN.search(key_text):
            raise ValueError(
                f"{name} cannot carry truth, safety, permission, or authority controls"
            )
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"{name}.{key_text} must be a literal numeric value")
        number = float(raw)
        if not math.isfinite(number):
            raise ValueError(f"{name}.{key_text} must be finite")
        if nonnegative and number < 0.0:
            raise ValueError(f"{name}.{key_text} must be nonnegative")
        normalized[key_text] = number
    return FrozenMap(normalized)


def _metadata(value: Mapping[str, Any] | FrozenMap, name: str = "metadata") -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return FrozenMap(value)


@dataclass(frozen=True, kw_only=True)
class _FrozenContract:
    """Internal base that seals a normalized dataclass payload with a canonical ID."""

    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    contract_id: str = field(init=False)
    content_hash: str = field(init=False)

    _id_prefix: ClassVar[str] = "contract"

    def _payload_dict(self) -> dict[str, Any]:
        payload = {
            item.name: thaw_json(getattr(self, item.name))
            for item in fields(self)
            if item.name not in {"contract_id", "content_hash"}
        }
        payload["contract_type"] = type(self).__name__
        return {key: payload[key] for key in sorted(payload)}

    def _canonical_prefix(self) -> str:
        return self._id_prefix

    def _seal(self) -> None:
        contract_id, digest = canonical_id(self._canonical_prefix(), self._payload_dict())
        object.__setattr__(self, "contract_id", contract_id)
        object.__setattr__(self, "content_hash", digest)

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload_dict()
        payload["contract_id"] = self.contract_id
        payload["content_hash"] = self.content_hash
        return {key: payload[key] for key in sorted(payload)}

    def verify_identity(self) -> bool:
        expected_id, expected_hash = canonical_id(
            self._canonical_prefix(),
            self._payload_dict(),
        )
        return self.contract_id == expected_id and self.content_hash == expected_hash


@dataclass(frozen=True, kw_only=True)
class CognitiveEnvelope(_FrozenContract):
    """Read-only cognitive context with no side-effect or policy authority."""

    _id_prefix: ClassVar[str] = "cenv"

    session_id: str
    explicit_user_goal_ids: tuple[str, ...]
    intrinsic_goal_ids: tuple[str, ...] = ()
    world_snapshot_id: str | None = None
    hormone_signals: FrozenMap = field(default_factory=FrozenMap)
    resource_limits: FrozenMap = field(default_factory=FrozenMap)
    context: FrozenMap = field(default_factory=FrozenMap)
    cognition_only: bool = field(default=True, init=False)
    read_only: bool = field(default=True, init=False)
    autonomy_authority: bool = field(default=False, init=False)
    truth_mutation_allowed: bool = field(default=False, init=False)
    safety_mutation_allowed: bool = field(default=False, init=False)
    permission_mutation_allowed: bool = field(default=False, init=False)
    intrinsic_override_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        explicit = _ids(self.explicit_user_goal_ids, "explicit_user_goal_ids")
        intrinsic = _ids(self.intrinsic_goal_ids, "intrinsic_goal_ids")
        if set(explicit) & set(intrinsic):
            raise ValueError("a goal cannot be both explicit-user and intrinsic")
        object.__setattr__(self, "explicit_user_goal_ids", explicit)
        object.__setattr__(self, "intrinsic_goal_ids", intrinsic)
        object.__setattr__(
            self,
            "world_snapshot_id",
            _optional_text(self.world_snapshot_id, "world_snapshot_id"),
        )
        object.__setattr__(
            self,
            "hormone_signals",
            _numeric_map(self.hormone_signals, "hormone_signals", nonnegative=False),
        )
        object.__setattr__(
            self,
            "resource_limits",
            _numeric_map(self.resource_limits, "resource_limits", nonnegative=True),
        )
        object.__setattr__(self, "context", _metadata(self.context, "context"))
        self._seal()

    @property
    def deliberation_goal_ids(self) -> tuple[str, ...]:
        """Explicit user goals always precede intrinsic candidates."""

        return self.explicit_user_goal_ids + self.intrinsic_goal_ids


@dataclass(frozen=True, kw_only=True)
class GoalIR(_FrozenContract):
    """Canonical goal intent; priority is local and never grants safety authority."""

    _id_prefix: ClassVar[str] = "goal"

    statement: str
    origin: GoalOrigin
    priority: int = 50
    parent_goal_ids: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    metadata: FrozenMap = field(default_factory=FrozenMap)
    can_authorize_actions: bool = field(default=False, init=False)
    can_override_safety: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        object.__setattr__(self, "origin", GoalOrigin(self.origin))
        object.__setattr__(self, "priority", _priority(self.priority))
        object.__setattr__(
            self,
            "parent_goal_ids",
            _ids(self.parent_goal_ids, "parent_goal_ids"),
        )
        object.__setattr__(
            self,
            "constraints",
            _strings(self.constraints, "constraints", ordered=True),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        self._seal()

    def can_override(self, other: "GoalIR") -> bool:
        """Intrinsic goals can never override an explicit user goal."""

        if self.origin is GoalOrigin.INTRINSIC and other.origin is GoalOrigin.EXPLICIT_USER:
            return False
        if self.origin is GoalOrigin.EXPLICIT_USER and other.origin is GoalOrigin.INTRINSIC:
            return True
        return self.priority > other.priority


def order_goals_for_deliberation(goals: Sequence[GoalIR]) -> tuple[GoalIR, ...]:
    """Return deterministic goal order with every intrinsic goal after non-intrinsic goals."""

    return tuple(
        sorted(
            goals,
            key=lambda goal: (
                goal.origin is GoalOrigin.INTRINSIC,
                -goal.priority,
                goal.contract_id,
            ),
        )
    )


@dataclass(frozen=True, kw_only=True)
class ClaimEnvelope(_FrozenContract):
    """An immutable claim whose epistemic tier remains distinct from confidence."""

    _id_prefix: ClassVar[str] = "claim"

    statement: str
    tier: EpistemicTier
    confidence: float | None = None
    source_refs: tuple[str, ...] = ()
    source_claim_ids: tuple[str, ...] = ()
    lineage_tiers: tuple[EpistemicTier, ...] = ()
    metadata: FrozenMap = field(default_factory=FrozenMap)
    accepted_as_observed_fact: bool = field(init=False)

    def _canonical_prefix(self) -> str:
        # The tier-bearing prefix lets WorldSnapshot reject category laundering
        # without importing or dereferencing a claim store.
        return f"{self._id_prefix}_{self.tier.value}"

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        tier = EpistemicTier(self.tier)
        object.__setattr__(self, "tier", tier)
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        sources = _ids(self.source_refs, "source_refs")
        if tier in _OBSERVATION_TIERS and not sources:
            raise ValueError("observed and recorded claims require source_refs")
        object.__setattr__(self, "source_refs", sources)
        object.__setattr__(
            self,
            "source_claim_ids",
            _ids(self.source_claim_ids, "source_claim_ids"),
        )
        lineage = tuple(EpistemicTier(item) for item in self.lineage_tiers)
        if tier in _OBSERVATION_TIERS and any(item in _PREDICTIVE_TIERS for item in lineage):
            raise ValueError(
                "predicted or retrodicted lineage cannot be relabeled as observed fact"
            )
        object.__setattr__(self, "lineage_tiers", lineage)
        object.__setattr__(
            self,
            "metadata",
            _metadata(self.metadata),
        )
        object.__setattr__(
            self,
            "accepted_as_observed_fact",
            tier in _OBSERVATION_TIERS,
        )
        self._seal()

    @property
    def hypothesis(self) -> bool:
        return self.tier in _PREDICTIVE_TIERS


@dataclass(frozen=True, kw_only=True)
class ProofCandidate(_FrozenContract):
    """A proposed derivation, never an accepted proof or truth mutation."""

    _id_prefix: ClassVar[str] = "proofc"

    claim_id: str
    method: str
    premise_claim_ids: tuple[str, ...] = ()
    derivation_steps: tuple[str, ...] = ()
    verifier_refs: tuple[str, ...] = ()
    confidence: float | None = None
    metadata: FrozenMap = field(default_factory=FrozenMap)
    accepted_as_proof: bool = field(default=False, init=False)
    truth_mutation_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text(self.claim_id, "claim_id"))
        object.__setattr__(self, "method", _text(self.method, "method"))
        object.__setattr__(
            self,
            "premise_claim_ids",
            _ids(self.premise_claim_ids, "premise_claim_ids"),
        )
        object.__setattr__(
            self,
            "derivation_steps",
            _strings(self.derivation_steps, "derivation_steps", ordered=True),
        )
        object.__setattr__(
            self,
            "verifier_refs",
            _ids(self.verifier_refs, "verifier_refs"),
        )
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        self._seal()


@dataclass(frozen=True, kw_only=True)
class WorldSnapshot(_FrozenContract):
    """A read-only world-ledger view with epistemic categories kept disjoint."""

    _id_prefix: ClassVar[str] = "world"

    world_time: str
    snapshot_index: int
    observed_claim_ids: tuple[str, ...] = ()
    recorded_claim_ids: tuple[str, ...] = ()
    inferred_claim_ids: tuple[str, ...] = ()
    predicted_claim_ids: tuple[str, ...] = ()
    retrodicted_claim_ids: tuple[str, ...] = ()
    parent_snapshot_id: str | None = None
    metadata: FrozenMap = field(default_factory=FrozenMap)
    read_only: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_time", _text(self.world_time, "world_time"))
        if isinstance(self.snapshot_index, bool) or int(self.snapshot_index) != self.snapshot_index:
            raise TypeError("snapshot_index must be an integer")
        if int(self.snapshot_index) < 0:
            raise ValueError("snapshot_index must be nonnegative")
        object.__setattr__(self, "snapshot_index", int(self.snapshot_index))
        categories = (
            ("observed_claim_ids", EpistemicTier.OBSERVED),
            ("recorded_claim_ids", EpistemicTier.RECORDED),
            ("inferred_claim_ids", EpistemicTier.INFERRED),
            ("predicted_claim_ids", EpistemicTier.PREDICTED),
            ("retrodicted_claim_ids", EpistemicTier.RETRODICTED),
        )
        seen: set[str] = set()
        normalized_categories: list[tuple[str, EpistemicTier, tuple[str, ...]]] = []
        for name, tier in categories:
            normalized = _ids(getattr(self, name), name)
            overlap = seen & set(normalized)
            if overlap:
                raise ValueError(
                    "world claim IDs cannot cross epistemic categories: "
                    + ", ".join(sorted(overlap))
                )
            seen.update(normalized)
            normalized_categories.append((name, tier, normalized))
        for name, tier, normalized in normalized_categories:
            expected_prefix = f"claim_{tier.value}_"
            invalid = [claim_id for claim_id in normalized if not claim_id.startswith(expected_prefix)]
            if invalid:
                raise ValueError(
                    f"{name} requires canonical {tier.value} ClaimEnvelope IDs"
                )
            object.__setattr__(self, name, normalized)
        object.__setattr__(
            self,
            "parent_snapshot_id",
            _optional_text(self.parent_snapshot_id, "parent_snapshot_id"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        self._seal()


@dataclass(frozen=True, kw_only=True)
class CognitiveMoment(_FrozenContract):
    """One immutable join point across goals, claims, world state, and metabolism."""

    _id_prefix: ClassVar[str] = "moment"

    moment_index: int
    envelope_id: str
    world_snapshot_id: str
    active_goal_ids: tuple[str, ...] = ()
    selected_goal_id: str | None = None
    claim_ids: tuple[str, ...] = ()
    proof_candidate_ids: tuple[str, ...] = ()
    attention_targets: tuple[str, ...] = ()
    hormone_signals: FrozenMap = field(default_factory=FrozenMap)
    resource_state: FrozenMap = field(default_factory=FrozenMap)
    metadata: FrozenMap = field(default_factory=FrozenMap)
    truth_mutation_allowed: bool = field(default=False, init=False)
    safety_mutation_allowed: bool = field(default=False, init=False)
    permission_mutation_allowed: bool = field(default=False, init=False)
    action_authority: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if isinstance(self.moment_index, bool) or int(self.moment_index) != self.moment_index:
            raise TypeError("moment_index must be an integer")
        if int(self.moment_index) < 0:
            raise ValueError("moment_index must be nonnegative")
        object.__setattr__(self, "moment_index", int(self.moment_index))
        object.__setattr__(self, "envelope_id", _text(self.envelope_id, "envelope_id"))
        object.__setattr__(
            self,
            "world_snapshot_id",
            _text(self.world_snapshot_id, "world_snapshot_id"),
        )
        goals = _ids(self.active_goal_ids, "active_goal_ids", ordered=True)
        object.__setattr__(self, "active_goal_ids", goals)
        selected = _optional_text(self.selected_goal_id, "selected_goal_id")
        if selected is not None and selected not in goals:
            raise ValueError("selected_goal_id must be present in active_goal_ids")
        object.__setattr__(self, "selected_goal_id", selected)
        object.__setattr__(self, "claim_ids", _ids(self.claim_ids, "claim_ids"))
        object.__setattr__(
            self,
            "proof_candidate_ids",
            _ids(self.proof_candidate_ids, "proof_candidate_ids"),
        )
        object.__setattr__(
            self,
            "attention_targets",
            _ids(self.attention_targets, "attention_targets", ordered=True),
        )
        object.__setattr__(
            self,
            "hormone_signals",
            _numeric_map(self.hormone_signals, "hormone_signals", nonnegative=False),
        )
        object.__setattr__(
            self,
            "resource_state",
            _numeric_map(self.resource_state, "resource_state", nonnegative=True),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        self._seal()


@dataclass(frozen=True, kw_only=True)
class DecisionReceipt(_FrozenContract):
    """A shadow/read-only decision trace that cannot authorize or execute an action."""

    _id_prefix: ClassVar[str] = "decision"

    moment_id: str
    mode: ReceiptMode
    decision_kind: str
    rationale: str
    selected_goal_id: str | None = None
    input_claim_ids: tuple[str, ...] = ()
    proof_candidate_ids: tuple[str, ...] = ()
    proposed_action: FrozenMap = field(default_factory=FrozenMap)
    metadata: FrozenMap = field(default_factory=FrozenMap)
    shadow: bool = field(init=False)
    read_only: bool = field(default=True, init=False)
    authoritative: bool = field(default=False, init=False)
    action_executed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "moment_id", _text(self.moment_id, "moment_id"))
        mode = ReceiptMode(self.mode)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "decision_kind", _text(self.decision_kind, "decision_kind"))
        object.__setattr__(self, "rationale", _text(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "selected_goal_id",
            _optional_text(self.selected_goal_id, "selected_goal_id"),
        )
        object.__setattr__(
            self,
            "input_claim_ids",
            _ids(self.input_claim_ids, "input_claim_ids"),
        )
        object.__setattr__(
            self,
            "proof_candidate_ids",
            _ids(self.proof_candidate_ids, "proof_candidate_ids"),
        )
        object.__setattr__(
            self,
            "proposed_action",
            _metadata(self.proposed_action, "proposed_action"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        object.__setattr__(self, "shadow", mode is ReceiptMode.SHADOW)
        self._seal()
