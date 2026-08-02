"""Bounded, default-off observation of the live ``ContinuousSelf.step`` boundary.

This module records only detached primitive projection digests.  It neither
controls the legacy step nor attests its internal failures, persistence,
background effects, action authority, or shared-state safety.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import math
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any
import uuid

from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.cognitive_core.cycle import (
    CanonicalEntityRef,
    CycleEvent,
    CyclePhase,
    CycleReceipt,
    CycleStatus,
    EntityKind,
    RequestCycle,
)
from packages.cognitive_core.cycle_ledger import (
    CycleLedger,
    CycleLedgerCapacityError,
)
from packages.continuous_self.self_state import Observation, SelfState


CONTINUOUS_SELF_SHADOW_ENV = "ATANOR_CONTINUOUS_SELF_CYCLE_SHADOW"
CONTINUOUS_SELF_SAMPLE_EVERY = 30
CONTINUOUS_SELF_QUEUE_CAPACITY = 8
CONTINUOUS_SELF_LEDGER_MAX_RECORDS = 256
CONTINUOUS_SELF_LEDGER_MAX_BYTES = 4 * 1024 * 1024
CONTINUOUS_SELF_PROJECTION_SCHEMA = "atanor.continuous-self.digest-projection.v1"

_ALLOWED_MODES = frozenset(
    {
        "waking",
        "observing",
        "curious",
        "learning",
        "reflecting",
        "resting",
        "attending",
    }
)
_MAX_COUNT = 1_000_000
_MAX_INTEGER = (1 << 63) - 1
_LIMITATIONS = (
    "legacy_internal_failures_not_observed",
    "legacy_effect_set_not_enumerated",
    "legacy_truth_mutation_unattested",
    "legacy_permission_mutation_unattested",
    "legacy_promotion_mutation_unattested",
    "persistence_success_not_observed",
    "background_effect_completion_not_observed",
    "external_action_authority_unattested",
    "projection_hash_not_live_or_persisted_state",
    "observer_projection_not_shared_state_authority",
    "projection_digests_not_privacy_proof",
    "legacy_step_seed_uncontrolled",
    "continuous_parent_linkage_unavailable",
    "cross_process_self_state_consistency_unresolved",
    "unlocked_background_state_mutation_unresolved",
    "observer_sampling_may_skip_cycles",
    "observer_overload_or_quota_may_drop_telemetry",
)


def continuous_self_shadow_enabled() -> bool:
    """Only the cognitive master flag plus this exact organ flag enable it."""

    return (
        os.environ.get("ATANOR_COGNITIVE_SHADOW", "0") == "1"
        and os.environ.get(CONTINUOUS_SELF_SHADOW_ENV, "0") == "1"
    )


def _strict_bool(value: Any) -> bool | None:
    return value if type(value) is bool else None


def _strict_int(
    value: Any,
    *,
    minimum: int = 0,
    maximum: int = _MAX_INTEGER,
) -> int | None:
    if type(value) is not int or not minimum <= value <= maximum:
        return None
    return value


def _unit_number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        return None
    return round(number, 6)


def _bounded_collection_length(value: Any) -> int | None:
    if type(value) not in (list, tuple):
        return None
    return min(len(value), _MAX_COUNT)


def _mode(value: Any) -> str:
    if type(value) is str and value in _ALLOWED_MODES:
        return value
    return "other"


def _plain_attributes(
    value: Any,
    expected_type: type[Observation] | type[SelfState],
) -> dict[str, Any]:
    """Read only an exact trusted dataclass instance, never a proxy or subclass."""

    if type(value) is not expected_type:
        raise TypeError(f"projection requires exact {expected_type.__name__}")
    attributes = object.__getattribute__(value, "__dict__")
    if type(attributes) is not dict:
        raise TypeError("projection source must have a plain instance dictionary")
    return attributes


def _state_projection(state: Any) -> dict[str, Any]:
    """Return the exact primitive allowlist; never call ``to_public`` or ``asdict``."""

    attributes = _plain_attributes(state, SelfState)
    return {
        "collection_lengths": {
            "goals": _bounded_collection_length(attributes.get("goals")),
            "narrative": _bounded_collection_length(
                attributes.get("narrative")
            ),
            "open_threads": _bounded_collection_length(
                attributes.get("open_threads")
            ),
            "parked_questions": _bounded_collection_length(
                attributes.get("parked_questions")
            ),
            "self_model": _bounded_collection_length(
                attributes.get("self_model")
            ),
            "vitals_history": _bounded_collection_length(
                attributes.get("vitals_history")
            ),
        },
        "introspection": {
            "introspective_pressure": _unit_number(
                attributes.get("introspective_pressure")
            ),
            "last_research_tick": _strict_int(
                attributes.get("last_research_tick")
            ),
            "research_miss_count": _strict_int(
                attributes.get("research_miss_count")
            ),
            "self_inquiry_count": _strict_int(
                attributes.get("self_inquiry_count")
            ),
            "self_question_open": _strict_bool(
                attributes.get("self_question_open")
            ),
        },
        "mode": _mode(attributes.get("mode")),
        "projection_schema": CONTINUOUS_SELF_PROJECTION_SCHEMA,
        "resumed_count": _strict_int(attributes.get("resumed_count")),
        "ticks": _strict_int(attributes.get("ticks")),
        "vitals": {
            "attention": _unit_number(attributes.get("attention")),
            "curiosity": _unit_number(attributes.get("curiosity")),
            "energy": _unit_number(attributes.get("energy")),
            "uncertainty": _unit_number(attributes.get("uncertainty")),
            "valence": _unit_number(attributes.get("valence")),
        },
    }


def _observation_projection(observation: Any) -> dict[str, Any]:
    attributes = _plain_attributes(observation, Observation)
    return {
        "concepts_delta": _strict_int(attributes.get("concepts_delta")),
        "deficit_count": _strict_int(attributes.get("deficit_count")),
        "learning_active": _strict_bool(attributes.get("learning_active")),
        "person_unfamiliar": _strict_bool(
            attributes.get("person_unfamiliar")
        ),
        "projection_schema": CONTINUOUS_SELF_PROJECTION_SCHEMA,
        "relations_delta": _strict_int(attributes.get("relations_delta")),
        "resource_pressure": _unit_number(
            attributes.get("resource_pressure")
        ),
        "uncertainty_signal": _unit_number(
            attributes.get("uncertainty_signal")
        ),
        "user_present": _strict_bool(attributes.get("user_present")),
    }


def project_continuous_self_state(state: Any) -> FrozenMap:
    """Public test/audit helper returning only the fixed detached allowlist."""

    return FrozenMap(_state_projection(state))


def project_continuous_self_observation(observation: Any) -> FrozenMap:
    """Public test/audit helper returning only the fixed detached allowlist."""

    return FrozenMap(_observation_projection(observation))


def continuous_self_projection_digest(value: Mapping[str, Any]) -> str:
    return canonical_digest(FrozenMap(value))


def _make_receipt(
    *,
    observation_digest: str,
    before_state_digest: str,
    after_state_digest: str,
    legacy_returned: bool,
) -> CycleReceipt:
    nonce = uuid.uuid4().hex
    request_id = f"continuous_self_step_{nonce}"
    cycle_id = f"continuous_self_cycle_{uuid.uuid4().hex}"
    observation = CanonicalEntityRef(
        kind=EntityKind.OBSERVATION,
        cycle_id=cycle_id,
        ordinal=0,
        payload=FrozenMap(
            {
                "projection_schema": CONTINUOUS_SELF_PROJECTION_SCHEMA,
                "projection_sha256": observation_digest,
                "raw_observation_stored": False,
            }
        ),
        legacy_ref="packages.continuous_self.loop.ContinuousSelf.step.observation",
    )
    episode = CanonicalEntityRef(
        kind=EntityKind.EPISODE,
        cycle_id=cycle_id,
        ordinal=1,
        payload=FrozenMap(
            {
                "boundary": "before_step_locked",
                "projection_schema": CONTINUOUS_SELF_PROJECTION_SCHEMA,
                "raw_state_stored": False,
                "state_projection_sha256": before_state_digest,
            }
        ),
        legacy_ref="packages.continuous_self.loop.ContinuousSelf.state",
    )
    evaluation = CanonicalEntityRef(
        kind=EntityKind.EVALUATION,
        cycle_id=cycle_id,
        ordinal=2,
        payload=FrozenMap(
            {
                "external_evaluator": False,
                "legacy_effects_attested": False,
                "outcome": (
                    "legacy_step_returned"
                    if legacy_returned
                    else "legacy_step_did_not_return"
                ),
                "projection_schema": CONTINUOUS_SELF_PROJECTION_SCHEMA,
                "raw_state_stored": False,
                "state_projection_sha256": after_state_digest,
            }
        ),
    )
    request_cycle = RequestCycle(
        request_id=request_id,
        cycle_id=cycle_id,
        session_id="continuous_self_session_unbound",
        parent_cycle_id=None,
        seed=0,
        input_observation_id=observation.occurrence_id,
    )
    initial_state = FrozenMap(
        {
            "observer_projection": "continuous_self_digest_v1",
            "status": "created",
        }
    )
    ingress, running_state = CycleEvent.transition(
        cycle_id=cycle_id,
        sequence=0,
        phase=CyclePhase.INGRESS,
        parent_event_id=None,
        entity_occurrence_ids=(
            observation.occurrence_id,
            episode.occurrence_id,
        ),
        state_before=initial_state,
        state_patch={
            "set": {
                "before_state_projection_sha256": before_state_digest,
                "observation_projection_sha256": observation_digest,
                "status": "running",
            },
            "delete": [],
        },
        metadata={
            "observer_only": True,
            "sample_every": CONTINUOUS_SELF_SAMPLE_EVERY,
        },
    )
    terminal, terminal_state = CycleEvent.transition(
        cycle_id=cycle_id,
        sequence=1,
        phase=CyclePhase.TERMINAL,
        parent_event_id=ingress.event_id,
        entity_occurrence_ids=(evaluation.occurrence_id,),
        state_before=running_state,
        state_patch={
            "set": {
                "after_state_projection_sha256": after_state_digest,
                "legacy_outcome": (
                    "returned" if legacy_returned else "did_not_return"
                ),
                "receipt_scope": "observer_only",
                "status": "completed" if legacy_returned else "failed",
            },
            "delete": [],
        },
        metadata={
            "external_action_authority_attested": False,
            "legacy_internal_failures_observed": False,
            "observer_only": True,
            "persistence_success_observed": False,
        },
    )
    return CycleReceipt(
        request_cycle=request_cycle,
        status=(
            CycleStatus.COMPLETED if legacy_returned else CycleStatus.FAILED
        ),
        entities=(observation, episode, evaluation),
        events=(ingress, terminal),
        initial_state=initial_state,
        terminal_state_hash=terminal.state_after_hash,
        input_hash=observation_digest,
        output_hash=after_state_digest if legacy_returned else None,
        selected_route="observer.continuous_self.step_boundary",
        declared_effects=("observer_ledger_append",),
        limitations=_LIMITATIONS,
    )


class ContinuousSelfReceiptDispatcher:
    """One nonblocking worker for one dedicated, atomically capped ledger."""

    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path.resolve(strict=False)
        self._queue: queue.Queue[CycleReceipt] = queue.Queue(
            maxsize=CONTINUOUS_SELF_QUEUE_CAPACITY
        )
        self._condition = threading.Condition()
        self._started = False
        self._saturated = False
        self._accepted = 0
        self._completed = 0
        self._dropped = 0
        self._failed = 0
        self._pending = 0

    def _ensure_worker_locked(self) -> None:
        if self._started:
            return
        worker = threading.Thread(
            target=self._run,
            name="atanor-continuous-self-shadow",
            daemon=True,
        )
        worker.start()
        self._started = True

    def submit(self, receipt: CycleReceipt) -> bool:
        with self._condition:
            if self._saturated:
                self._dropped += 1
                return False
            try:
                self._ensure_worker_locked()
            except BaseException:
                self._failed += 1
                return False
            try:
                self._queue.put_nowait(receipt)
            except queue.Full:
                self._dropped += 1
                return False
            self._accepted += 1
            self._pending += 1
            return True

    def _run(self) -> None:
        while True:
            receipt = self._queue.get()
            try:
                CycleLedger(
                    self.ledger_path,
                    max_bytes=CONTINUOUS_SELF_LEDGER_MAX_BYTES,
                    max_records=CONTINUOUS_SELF_LEDGER_MAX_RECORDS,
                ).append(receipt)
            except CycleLedgerCapacityError:
                with self._condition:
                    self._saturated = True
                    self._failed += 1
            except BaseException:
                with self._condition:
                    self._failed += 1
            else:
                with self._condition:
                    self._completed += 1
            finally:
                with self._condition:
                    self._pending -= 1
                    self._condition.notify_all()
                self._queue.task_done()

    def stats(self) -> dict[str, int | bool]:
        with self._condition:
            return {
                "accepted": self._accepted,
                "completed": self._completed,
                "dropped": self._dropped,
                "failed": self._failed,
                "pending": self._pending,
                "queue_capacity": CONTINUOUS_SELF_QUEUE_CAPACITY,
                "saturated": self._saturated,
            }

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._condition:
            while self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return False
                self._condition.wait(remaining)
            return True


_DISPATCHERS_LOCK = threading.Lock()
_DISPATCHERS: dict[str, ContinuousSelfReceiptDispatcher] = {}


def _dispatcher_for(path: Path) -> ContinuousSelfReceiptDispatcher:
    resolved = path.resolve(strict=False)
    key = os.path.normcase(str(resolved))
    with _DISPATCHERS_LOCK:
        dispatcher = _DISPATCHERS.get(key)
        if dispatcher is None:
            dispatcher = ContinuousSelfReceiptDispatcher(resolved)
            _DISPATCHERS[key] = dispatcher
        return dispatcher


def continuous_self_dispatcher_stats(
    ledger_path: str | os.PathLike[str] | Path,
) -> dict[str, int | bool]:
    return _dispatcher_for(Path(ledger_path)).stats()


def wait_for_continuous_self_shadow(
    ledger_path: str | os.PathLike[str] | Path,
    *,
    timeout: float = 5.0,
) -> bool:
    return _dispatcher_for(Path(ledger_path)).wait_until_idle(timeout)


class DisabledContinuousSelfCycleSpan:
    """No-op methods deliberately ignore all state and observation arguments."""

    enabled = False
    sampled = False
    fault_count = 0

    def capture_before_locked(self, _state: Any, _observation: Any) -> bool:
        return False

    def capture_after_locked(self, _state: Any) -> bool:
        return False

    def finish(self, *, legacy_returned: bool) -> bool:
        _ = legacy_returned
        return False


_DISABLED_SPAN = DisabledContinuousSelfCycleSpan()


class ContinuousSelfCycleSpan:
    """A one-shot detached span; every public method is exception-contained."""

    enabled = True

    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path.resolve(strict=False)
        self.sampled = False
        self.fault_count = 0
        self._closed = False
        self._observation_digest: str | None = None
        self._before_state_digest: str | None = None
        self._after_state_digest: str | None = None
        self._lock = threading.Lock()

    def _fault(self) -> None:
        self.fault_count += 1
        self._closed = True

    def capture_before_locked(self, state: Any, observation: Any) -> bool:
        with self._lock:
            if self._closed or self._before_state_digest is not None:
                return False
            try:
                state_projection = project_continuous_self_state(state)
                tick = state_projection["ticks"]
                if type(tick) is not int or tick % CONTINUOUS_SELF_SAMPLE_EVERY:
                    self._closed = True
                    return False
                observation_projection = project_continuous_self_observation(
                    observation
                )
                self._before_state_digest = continuous_self_projection_digest(
                    state_projection
                )
                self._observation_digest = continuous_self_projection_digest(
                    observation_projection
                )
                self.sampled = True
                return True
            except BaseException:
                self._fault()
                return False

    def capture_after_locked(self, state: Any) -> bool:
        with self._lock:
            if self._closed or not self.sampled:
                return False
            try:
                projection = project_continuous_self_state(state)
                self._after_state_digest = continuous_self_projection_digest(
                    projection
                )
                return True
            except BaseException:
                self._fault()
                return False

    def finish(self, *, legacy_returned: bool) -> bool:
        if type(legacy_returned) is not bool:
            with self._lock:
                if not self._closed:
                    self._fault()
            return False
        with self._lock:
            if self._closed or not self.sampled:
                return False
            self._closed = True
            observation_digest = self._observation_digest
            before_state_digest = self._before_state_digest
            after_state_digest = self._after_state_digest
        if (
            observation_digest is None
            or before_state_digest is None
            or after_state_digest is None
        ):
            self.fault_count += 1
            return False
        try:
            receipt = _make_receipt(
                observation_digest=observation_digest,
                before_state_digest=before_state_digest,
                after_state_digest=after_state_digest,
                legacy_returned=legacy_returned,
            )
            return _dispatcher_for(self.ledger_path).submit(receipt)
        except BaseException:
            self.fault_count += 1
            return False


def begin_continuous_self_cycle_shadow(
    ledger_path_factory: Callable[[], str | os.PathLike[str] | Path],
) -> DisabledContinuousSelfCycleSpan | ContinuousSelfCycleSpan:
    """Begin lazily so the disabled path does not inspect owner state or paths."""

    if not continuous_self_shadow_enabled():
        return _DISABLED_SPAN
    try:
        return ContinuousSelfCycleSpan(Path(ledger_path_factory()))
    except BaseException:
        return _DISABLED_SPAN
