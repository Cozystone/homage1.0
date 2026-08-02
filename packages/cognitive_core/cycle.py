"""Occurrence-level contracts for the default-off canonical cognitive spine.

The records in this module are observational.  They can describe a proposal,
evaluation, or observed effect, but they cannot authorize an action, promote a
learning candidate, mutate truth, or replace the autonomy membrane.

Two identities are deliberately distinct:

* ``semantic_id`` identifies the canonical kind + payload.
* ``occurrence_id`` identifies one appearance of that semantic payload in one
  cycle and ordinal position.

That distinction prevents repeated observations from collapsing into one event
while still allowing semantically identical payloads to be recognized.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from packages.cognitive_core.canonical import (
    SCHEMA_VERSION,
    FrozenMap,
    canonical_digest,
    canonical_id,
    freeze_json,
    thaw_json,
)


class EntityKind(str, Enum):
    OBSERVATION = "observation"
    PROPOSITION = "proposition"
    EPISODE = "episode"
    GOAL = "goal"
    PLAN = "plan"
    ACTION = "action"
    EVALUATION = "evaluation"
    LEARNING_CANDIDATE = "learning_candidate"


class CyclePhase(str, Enum):
    INGRESS = "ingress"
    PERCEPTION = "perception"
    DELIBERATION = "deliberation"
    SELECTION = "selection"
    AUTHORIZATION_OBSERVATION = "authorization_observation"
    EFFECT_OBSERVATION = "effect_observation"
    EVALUATION = "evaluation"
    LEARNING_PROPOSAL = "learning_proposal"
    TERMINAL = "terminal"


class CycleStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    ABSTAINED = "abstained"
    CANCELLED = "cancelled"


def _text(value: Any, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _ids(values: Iterable[Any], name: str, *, ordered: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable, not a string")
    normalized = tuple(str(_text(value, name)) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} cannot contain duplicates")
    return normalized if ordered else tuple(sorted(normalized))


def _digest(value: Any, name: str) -> str:
    normalized = str(_text(value, name))
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return normalized


def _optional_digest(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _digest(value, name)


def _frozen_map(value: Mapping[str, Any] | FrozenMap, name: str) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return FrozenMap(value)


def _state_hash(value: Mapping[str, Any] | FrozenMap) -> str:
    return canonical_digest(value)


def apply_state_patch(
    state: Mapping[str, Any] | FrozenMap,
    patch: Mapping[str, Any] | FrozenMap,
) -> FrozenMap:
    """Apply the cycle reducer's deterministic root-level set/delete patch.

    The deliberately small reducer is sufficient for a shared observer
    projection and easy for an external verifier to reimplement.
    """

    current = thaw_json(freeze_json(state))
    raw_patch = thaw_json(freeze_json(patch))
    if not isinstance(current, dict) or not isinstance(raw_patch, dict):
        raise TypeError("state and patch must be mappings")
    if set(raw_patch) - {"set", "delete"}:
        raise ValueError("state patch supports only 'set' and 'delete'")
    setters = raw_patch.get("set", {})
    deleters = raw_patch.get("delete", [])
    if not isinstance(setters, dict):
        raise TypeError("state patch 'set' must be a mapping")
    if isinstance(deleters, (str, bytes)) or not isinstance(deleters, list):
        raise TypeError("state patch 'delete' must be a list")
    normalized_delete: list[str] = []
    for key in deleters:
        normalized = _text(key, "state patch delete key")
        assert isinstance(normalized, str)
        if normalized in normalized_delete:
            raise ValueError("state patch delete keys cannot repeat")
        normalized_delete.append(normalized)
    overlap = set(setters) & set(normalized_delete)
    if overlap:
        raise ValueError("state patch cannot set and delete the same key")
    for key in normalized_delete:
        current.pop(key, None)
    for key, value in setters.items():
        normalized = _text(key, "state patch set key")
        assert isinstance(normalized, str)
        current[normalized] = thaw_json(freeze_json(value))
    return FrozenMap(current)


@dataclass(frozen=True, kw_only=True)
class CanonicalEntityRef:
    """A semantic value plus one occurrence in a cycle."""

    kind: EntityKind
    cycle_id: str
    ordinal: int
    payload: FrozenMap
    legacy_ref: str | None = None
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    semantic_id: str = field(init=False)
    occurrence_id: str = field(init=False)
    payload_hash: str = field(init=False)
    observer_only: bool = field(default=True, init=False)
    authoritative: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        kind = EntityKind(self.kind)
        cycle_id = _text(self.cycle_id, "cycle_id")
        ordinal = _integer(self.ordinal, "ordinal")
        payload = _frozen_map(self.payload, "payload")
        legacy_ref = _text(self.legacy_ref, "legacy_ref", optional=True)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "cycle_id", cycle_id)
        object.__setattr__(self, "ordinal", ordinal)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "legacy_ref", legacy_ref)
        payload_hash = canonical_digest(payload)
        semantic_id, _ = canonical_id(
            f"sem_{kind.value}",
            {"kind": kind.value, "payload_hash": payload_hash},
        )
        occurrence_id, _ = canonical_id(
            f"occ_{kind.value}",
            {
                "cycle_id": cycle_id,
                "kind": kind.value,
                "ordinal": ordinal,
                "payload_hash": payload_hash,
            },
        )
        object.__setattr__(self, "payload_hash", payload_hash)
        object.__setattr__(self, "semantic_id", semantic_id)
        object.__setattr__(self, "occurrence_id", occurrence_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "contract_type": type(self).__name__,
            "cycle_id": self.cycle_id,
            "kind": self.kind.value,
            "legacy_ref": self.legacy_ref,
            "observer_only": self.observer_only,
            "occurrence_id": self.occurrence_id,
            "ordinal": self.ordinal,
            "payload": self.payload.to_dict(),
            "payload_hash": self.payload_hash,
            "schema_version": self.schema_version,
            "semantic_id": self.semantic_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CanonicalEntityRef":
        if not isinstance(value, Mapping):
            raise TypeError("entity must be a mapping")
        if value.get("schema_version") not in (None, SCHEMA_VERSION):
            raise ValueError("unsupported entity schema_version")
        for name, expected in (("observer_only", True), ("authoritative", False)):
            if name in value and value[name] is not expected:
                raise ValueError(f"entity {name} must be the literal value {expected!r}")
        entity = cls(
            kind=EntityKind(value["kind"]),
            cycle_id=value["cycle_id"],
            ordinal=value["ordinal"],
            payload=value.get("payload", {}),
            legacy_ref=value.get("legacy_ref"),
        )
        for name in ("semantic_id", "occurrence_id", "payload_hash"):
            if name in value and value[name] != getattr(entity, name):
                raise ValueError(f"entity {name} does not match canonical content")
        return entity


@dataclass(frozen=True, kw_only=True)
class RequestCycle:
    """Server-created identity and immutable ingress for one request cycle."""

    request_id: str
    cycle_id: str
    session_id: str
    seed: int
    input_observation_id: str
    parent_cycle_id: str | None = None
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    observer_only: bool = field(default=True, init=False)
    authoritative: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for name in ("request_id", "cycle_id", "session_id", "input_observation_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "seed", _integer(self.seed, "seed"))
        object.__setattr__(
            self,
            "parent_cycle_id",
            _text(self.parent_cycle_id, "parent_cycle_id", optional=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "contract_type": type(self).__name__,
            "cycle_id": self.cycle_id,
            "input_observation_id": self.input_observation_id,
            "observer_only": self.observer_only,
            "parent_cycle_id": self.parent_cycle_id,
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "seed": self.seed,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RequestCycle":
        if not isinstance(value, Mapping):
            raise TypeError("request cycle must be a mapping")
        for name, expected in (("observer_only", True), ("authoritative", False)):
            if name in value and value[name] is not expected:
                raise ValueError(f"request cycle {name} must be {expected!r}")
        return cls(
            request_id=value["request_id"],
            cycle_id=value["cycle_id"],
            session_id=value["session_id"],
            seed=value["seed"],
            input_observation_id=value["input_observation_id"],
            parent_cycle_id=value.get("parent_cycle_id"),
        )


@dataclass(frozen=True, kw_only=True)
class CycleEvent:
    """One ordered transition in the observer's pure shared-state projection."""

    cycle_id: str
    sequence: int
    phase: CyclePhase
    parent_event_id: str | None
    entity_occurrence_ids: tuple[str, ...]
    state_before_hash: str
    state_after_hash: str
    state_patch: FrozenMap
    metadata: FrozenMap = field(default_factory=FrozenMap)
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    event_id: str = field(init=False)
    observer_only: bool = field(default=True, init=False)
    authoritative: bool = field(default=False, init=False)
    truth_mutated: bool = field(default=False, init=False)
    permission_mutated: bool = field(default=False, init=False)
    promotion_mutated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cycle_id", _text(self.cycle_id, "cycle_id"))
        object.__setattr__(self, "sequence", _integer(self.sequence, "sequence"))
        object.__setattr__(self, "phase", CyclePhase(self.phase))
        object.__setattr__(
            self,
            "parent_event_id",
            _text(self.parent_event_id, "parent_event_id", optional=True),
        )
        object.__setattr__(
            self,
            "entity_occurrence_ids",
            _ids(self.entity_occurrence_ids, "entity_occurrence_ids"),
        )
        object.__setattr__(
            self,
            "state_before_hash",
            _digest(self.state_before_hash, "state_before_hash"),
        )
        object.__setattr__(
            self,
            "state_after_hash",
            _digest(self.state_after_hash, "state_after_hash"),
        )
        object.__setattr__(self, "state_patch", _frozen_map(self.state_patch, "state_patch"))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata, "metadata"))
        event_id, _ = canonical_id(
            "cevent",
            {
                "cycle_id": self.cycle_id,
                "entity_occurrence_ids": self.entity_occurrence_ids,
                "metadata": self.metadata,
                "parent_event_id": self.parent_event_id,
                "phase": self.phase.value,
                "sequence": self.sequence,
                "state_after_hash": self.state_after_hash,
                "state_before_hash": self.state_before_hash,
                "state_patch": self.state_patch,
            },
        )
        object.__setattr__(self, "event_id", event_id)

    @classmethod
    def transition(
        cls,
        *,
        cycle_id: str,
        sequence: int,
        phase: CyclePhase,
        parent_event_id: str | None,
        entity_occurrence_ids: Sequence[str],
        state_before: Mapping[str, Any] | FrozenMap,
        state_patch: Mapping[str, Any] | FrozenMap,
        metadata: Mapping[str, Any] | FrozenMap | None = None,
    ) -> tuple["CycleEvent", FrozenMap]:
        before = FrozenMap(state_before)
        patch = FrozenMap(state_patch)
        after = apply_state_patch(before, patch)
        return (
            cls(
                cycle_id=cycle_id,
                sequence=sequence,
                phase=phase,
                parent_event_id=parent_event_id,
                entity_occurrence_ids=tuple(entity_occurrence_ids),
                state_before_hash=_state_hash(before),
                state_after_hash=_state_hash(after),
                state_patch=patch,
                metadata=FrozenMap(metadata or {}),
            ),
            after,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "contract_type": type(self).__name__,
            "cycle_id": self.cycle_id,
            "entity_occurrence_ids": list(self.entity_occurrence_ids),
            "event_id": self.event_id,
            "metadata": self.metadata.to_dict(),
            "observer_only": self.observer_only,
            "parent_event_id": self.parent_event_id,
            "permission_mutated": self.permission_mutated,
            "phase": self.phase.value,
            "promotion_mutated": self.promotion_mutated,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "state_after_hash": self.state_after_hash,
            "state_before_hash": self.state_before_hash,
            "state_patch": self.state_patch.to_dict(),
            "truth_mutated": self.truth_mutated,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CycleEvent":
        if not isinstance(value, Mapping):
            raise TypeError("cycle event must be a mapping")
        fixed = {
            "observer_only": True,
            "authoritative": False,
            "truth_mutated": False,
            "permission_mutated": False,
            "promotion_mutated": False,
        }
        for name, expected in fixed.items():
            if name in value and value[name] is not expected:
                raise ValueError(f"cycle event {name} must be {expected!r}")
        event = cls(
            cycle_id=value["cycle_id"],
            sequence=value["sequence"],
            phase=CyclePhase(value["phase"]),
            parent_event_id=value.get("parent_event_id"),
            entity_occurrence_ids=tuple(value.get("entity_occurrence_ids", ())),
            state_before_hash=value["state_before_hash"],
            state_after_hash=value["state_after_hash"],
            state_patch=value.get("state_patch", {}),
            metadata=value.get("metadata", {}),
        )
        if "event_id" in value and value["event_id"] != event.event_id:
            raise ValueError("cycle event ID does not match canonical content")
        return event


@dataclass(frozen=True, kw_only=True)
class CycleReceipt:
    """Terminal, replayable, non-authoritative receipt for one cognitive cycle."""

    request_cycle: RequestCycle
    status: CycleStatus
    entities: tuple[CanonicalEntityRef, ...]
    events: tuple[CycleEvent, ...]
    initial_state: FrozenMap
    terminal_state_hash: str
    input_hash: str
    output_hash: str | None
    selected_route: str | None = None
    declared_effects: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    receipt_id: str = field(init=False)
    observer_only: bool = field(default=True, init=False)
    authoritative: bool = field(default=False, init=False)
    action_authorized: bool = field(default=False, init=False)
    truth_mutated: bool = field(default=False, init=False)
    permission_mutated: bool = field(default=False, init=False)
    promotion_mutated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.request_cycle, RequestCycle):
            raise TypeError("request_cycle must be a RequestCycle")
        object.__setattr__(self, "status", CycleStatus(self.status))
        entities = tuple(self.entities)
        events = tuple(self.events)
        if not all(isinstance(item, CanonicalEntityRef) for item in entities):
            raise TypeError("entities must contain CanonicalEntityRef values")
        if not all(isinstance(item, CycleEvent) for item in events):
            raise TypeError("events must contain CycleEvent values")
        occurrence_ids = [item.occurrence_id for item in entities]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("cycle entities cannot contain duplicate occurrence IDs")
        if any(item.cycle_id != self.request_cycle.cycle_id for item in entities):
            raise ValueError("every entity must belong to the request cycle")
        if not events:
            raise ValueError("a terminal cycle receipt requires at least one event")
        expected_parent: str | None = None
        expected_sequence = 0
        seen_occurrences = set(occurrence_ids)
        for event in events:
            if event.cycle_id != self.request_cycle.cycle_id:
                raise ValueError("every event must belong to the request cycle")
            if event.sequence != expected_sequence:
                raise ValueError("cycle event sequence must be contiguous from zero")
            if event.parent_event_id != expected_parent:
                raise ValueError("cycle event parent linkage is not a single ordered chain")
            unknown = set(event.entity_occurrence_ids) - seen_occurrences
            if unknown:
                raise ValueError("cycle event references unknown entity occurrences")
            expected_parent = event.event_id
            expected_sequence += 1
        if events[-1].phase is not CyclePhase.TERMINAL:
            raise ValueError("the final cycle event must use the terminal phase")
        initial_state = _frozen_map(self.initial_state, "initial_state")
        terminal_state_hash = _digest(self.terminal_state_hash, "terminal_state_hash")
        input_hash = _digest(self.input_hash, "input_hash")
        output_hash = _optional_digest(self.output_hash, "output_hash")
        selected_route = _text(self.selected_route, "selected_route", optional=True)
        declared_effects = _ids(self.declared_effects, "declared_effects", ordered=True)
        limitations = _ids(self.limitations, "limitations", ordered=True)
        if events[0].state_before_hash != _state_hash(initial_state):
            raise ValueError("first event does not begin at initial_state")
        for previous, current in zip(events, events[1:]):
            if previous.state_after_hash != current.state_before_hash:
                raise ValueError("adjacent event state hashes do not link")
        if events[-1].state_after_hash != terminal_state_hash:
            raise ValueError("terminal_state_hash does not match the final event")
        replayed_state = initial_state
        for event in events:
            replayed_state = apply_state_patch(replayed_state, event.state_patch)
        if replayed_state.to_dict().get("status") != self.status.value:
            raise ValueError(
                "cycle receipt status does not match replayed terminal state status"
            )
        object.__setattr__(self, "entities", entities)
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "initial_state", initial_state)
        object.__setattr__(self, "terminal_state_hash", terminal_state_hash)
        object.__setattr__(self, "input_hash", input_hash)
        object.__setattr__(self, "output_hash", output_hash)
        object.__setattr__(self, "selected_route", selected_route)
        object.__setattr__(self, "declared_effects", declared_effects)
        object.__setattr__(self, "limitations", limitations)
        receipt_id, _ = canonical_id(
            "cycle",
            {
                "declared_effects": declared_effects,
                "entities": [item.to_dict() for item in entities],
                "events": [item.to_dict() for item in events],
                "initial_state": initial_state,
                "input_hash": input_hash,
                "limitations": limitations,
                "output_hash": output_hash,
                "request_cycle": self.request_cycle.to_dict(),
                "selected_route": selected_route,
                "status": self.status.value,
                "terminal_state_hash": terminal_state_hash,
            },
        )
        object.__setattr__(self, "receipt_id", receipt_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_authorized": self.action_authorized,
            "authoritative": self.authoritative,
            "contract_type": type(self).__name__,
            "declared_effects": list(self.declared_effects),
            "entities": [item.to_dict() for item in self.entities],
            "events": [item.to_dict() for item in self.events],
            "initial_state": self.initial_state.to_dict(),
            "input_hash": self.input_hash,
            "limitations": list(self.limitations),
            "observer_only": self.observer_only,
            "output_hash": self.output_hash,
            "permission_mutated": self.permission_mutated,
            "promotion_mutated": self.promotion_mutated,
            "receipt_id": self.receipt_id,
            "request_cycle": self.request_cycle.to_dict(),
            "schema_version": self.schema_version,
            "selected_route": self.selected_route,
            "status": self.status.value,
            "terminal_state_hash": self.terminal_state_hash,
            "truth_mutated": self.truth_mutated,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CycleReceipt":
        if not isinstance(value, Mapping):
            raise TypeError("cycle receipt must be a mapping")
        fixed = {
            "observer_only": True,
            "authoritative": False,
            "action_authorized": False,
            "truth_mutated": False,
            "permission_mutated": False,
            "promotion_mutated": False,
        }
        for name, expected in fixed.items():
            if name in value and value[name] is not expected:
                raise ValueError(f"cycle receipt {name} must be {expected!r}")
        receipt = cls(
            request_cycle=RequestCycle.from_dict(value["request_cycle"]),
            status=CycleStatus(value["status"]),
            entities=tuple(
                CanonicalEntityRef.from_dict(item) for item in value.get("entities", ())
            ),
            events=tuple(CycleEvent.from_dict(item) for item in value.get("events", ())),
            initial_state=value.get("initial_state", {}),
            terminal_state_hash=value["terminal_state_hash"],
            input_hash=value["input_hash"],
            output_hash=value.get("output_hash"),
            selected_route=value.get("selected_route"),
            declared_effects=tuple(value.get("declared_effects", ())),
            limitations=tuple(value.get("limitations", ())),
        )
        if "receipt_id" in value and value["receipt_id"] != receipt.receipt_id:
            raise ValueError("cycle receipt ID does not match canonical content")
        return receipt
