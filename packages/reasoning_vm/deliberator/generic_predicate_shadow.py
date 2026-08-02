"""Default-off, non-authoritative shadow lane for generic predicates.

The live answer path may submit an already frozen ``PreparedScienceInput``.
Submission is a bounded ``put_nowait`` operation and never waits for parsing,
graph access, compilation, or proof replay.  A daemon worker performs those
steps locally and records immutable diagnostic telemetry in memory.

This module intentionally has no package imports at module load time.  In
particular, when ``ATANOR_GENERIC_PREDICATE_SHADOW`` is anything other than the
exact string ``"1"``, :func:`submit` returns before touching the submitted
object or importing the parser, graph socket, compiler, or proof membrane.

The lane is an observer only:

* it never returns a choice or mutates an answer;
* its graph sockets are read-only and bounded;
* it performs no network access and writes no files;
* ``grounded`` means only that the independently replayed proof receipt
  verified; it is not correctness, capability, E4, E5, or answer authority.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import queue
import re
import threading
from typing import Any


ENV_NAME = "ATANOR_GENERIC_PREDICATE_SHADOW"
QUEUE_CAPACITY = 64
TELEMETRY_CAPACITY = 256
SCHEMA_VERSION = "atanor.deliberator.generic-predicate-shadow.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,191}\Z")


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _safe_error_kind(error: BaseException) -> str:
    name = type(error).__name__
    return name if name.isidentifier() and len(name) <= 64 else "Exception"


@dataclass(frozen=True, slots=True)
class _ShadowTelemetry:
    """One immutable shadow trace.

    Receipt objects are the exact frozen objects passed between the public
    compiler/socket/proof contracts.  Their canonical digests are retained
    beside them so diagnostics can detect accidental substitution.
    """

    schema_version: str
    status: str
    reason: str
    error_kind: str | None

    eligible: bool
    role_extracted: bool
    context_ready: bool
    compiled: bool
    engine_called: bool
    fired: bool
    proof_verified: bool
    grounded: bool

    prepared_input_digest_sha256: str | None
    prepared_choices_digest_sha256: str | None
    role_receipt_digest_sha256: str | None
    context_digest_sha256: str | None
    compiler_receipt_digest_sha256: str | None
    proof_decision_digest_sha256: str | None
    proof_receipt_digest_sha256: str | None

    role_receipt: object | None
    context_receipt: object | None
    compiler_receipt: object | None
    proof_decision: object | None
    proof_receipt: object | None

    answer_mutated: bool = False
    network_accessed: bool = False
    state_written: bool = False
    answer_authority_established: bool = False
    correctness_established: bool = False
    capability_improvement_established: bool = False
    e4_established: bool = False
    e5_established: bool = False
    external_authenticity_established: bool = False
    independent_evaluation_established: bool = False

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or type(self.status) is not str
            or _IDENTIFIER.fullmatch(self.status) is None
            or type(self.reason) is not str
            or _IDENTIFIER.fullmatch(self.reason) is None
            or (
                self.error_kind is not None
                and (
                    type(self.error_kind) is not str
                    or not self.error_kind.isidentifier()
                    or len(self.error_kind) > 64
                )
            )
        ):
            raise ValueError("generic predicate shadow telemetry is invalid")

        progression = (
            self.eligible,
            self.role_extracted,
            self.context_ready,
            self.compiled,
            self.engine_called,
            self.fired,
            self.proof_verified,
        )
        if any(type(value) is not bool for value in progression):
            raise ValueError("shadow progression flags must be exact booleans")
        if any(
            progression[index] and not progression[index - 1]
            for index in range(1, len(progression))
        ):
            raise ValueError("shadow progression cannot skip a stage")
        if type(self.grounded) is not bool or (
            self.grounded is not self.proof_verified
        ):
            raise ValueError("grounded must be exactly proof_verified")

        digests = (
            self.prepared_input_digest_sha256,
            self.prepared_choices_digest_sha256,
            self.role_receipt_digest_sha256,
            self.context_digest_sha256,
            self.compiler_receipt_digest_sha256,
            self.proof_decision_digest_sha256,
            self.proof_receipt_digest_sha256,
        )
        if any(value is not None and not _is_sha256(value) for value in digests):
            raise ValueError("shadow receipt digest is invalid")

        receipt_pairs = (
            (self.role_receipt, self.role_receipt_digest_sha256),
            (self.context_receipt, self.context_digest_sha256),
            (self.compiler_receipt, self.compiler_receipt_digest_sha256),
            (self.proof_decision, self.proof_decision_digest_sha256),
            (self.proof_receipt, self.proof_receipt_digest_sha256),
        )
        if any(
            (receipt is None) is not (digest is None)
            for receipt, digest in receipt_pairs
        ):
            raise ValueError("shadow receipt and digest must travel together")

        non_authority = (
            self.answer_mutated,
            self.network_accessed,
            self.state_written,
            self.answer_authority_established,
            self.correctness_established,
            self.capability_improvement_established,
            self.e4_established,
            self.e5_established,
            self.external_authenticity_established,
            self.independent_evaluation_established,
        )
        if any(type(value) is not bool or value for value in non_authority):
            raise ValueError("shadow telemetry cannot carry authority claims")
        if self.eligible is False and any(digest is not None for digest in digests):
            raise ValueError("ineligible telemetry cannot carry input receipts")
        if self.role_receipt is not None and self.eligible is not True:
            raise ValueError("role receipt requires an eligible input")
        if self.context_receipt is not None and self.role_extracted is not True:
            raise ValueError("context receipt requires extracted roles")
        if self.compiler_receipt is not None and self.context_ready is not True:
            raise ValueError("compiler receipt requires a ready context")
        if self.proof_decision is not None and self.engine_called is not True:
            raise ValueError("proof decision requires an engine call")
        if self.proof_receipt is not None and self.fired is not True:
            raise ValueError("proof receipt requires a firing")
        if self.proof_verified and self.proof_receipt is None:
            raise ValueError("verified proof telemetry lost its receipt")


def _empty_state() -> dict[str, Any]:
    return {
        "eligible": False,
        "role_extracted": False,
        "context_ready": False,
        "compiled": False,
        "engine_called": False,
        "fired": False,
        "proof_verified": False,
        "grounded": False,
        "prepared_input_digest_sha256": None,
        "prepared_choices_digest_sha256": None,
        "role_receipt_digest_sha256": None,
        "context_digest_sha256": None,
        "compiler_receipt_digest_sha256": None,
        "proof_decision_digest_sha256": None,
        "proof_receipt_digest_sha256": None,
        "role_receipt": None,
        "context_receipt": None,
        "compiler_receipt": None,
        "proof_decision": None,
        "proof_receipt": None,
    }


def _finish(
    state: dict[str, Any],
    *,
    status: str,
    reason: str,
    error_kind: str | None = None,
) -> _ShadowTelemetry:
    return _ShadowTelemetry(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason=reason,
        error_kind=error_kind,
        **state,
    )


_RUNTIME_LOCK = threading.Lock()
_ROLE_EXTRACTOR: Any | None = None
_SOCKET: Any | None = None


def _role_receipt_for(stem: str) -> object:
    """Load the pinned local dependency parser only inside the daemon."""

    global _ROLE_EXTRACTOR
    with _RUNTIME_LOCK:
        if _ROLE_EXTRACTOR is None:
            from packages.reasoning_vm.deliberator.relation_role_extractor import (
                SpacyRelationRoleExtractor,
            )

            _ROLE_EXTRACTOR = SpacyRelationRoleExtractor()
        extractor = _ROLE_EXTRACTOR
    return extractor.extract(stem)


def _open_default_socket() -> object:
    """Open the sealed B1/S1 siblings as one bounded read-only socket."""

    from packages.reasoning_vm.deliberator.generic_predicate_socket import (
        CompositePredicateSocket,
        PredicateStageSpec,
    )

    repository_root = Path(__file__).resolve().parents[3]
    entity_root = (
        repository_root
        / "data"
        / "graph_scale"
        / "staging_b1_wikidata"
    )
    literal_root = (
        repository_root
        / "data"
        / "graph_scale"
        / "staging_s1_wikidata_literals"
    )
    stages = (
        PredicateStageSpec(
            stage_id="b1-wikidata",
            role="entity",
            root=entity_root,
            manifest_name="B1_WIKIDATA_MANIFEST.json",
        ),
        PredicateStageSpec(
            stage_id="s1-wikidata-literal",
            role="literal",
            root=literal_root,
            manifest_name="S1_WIKIDATA_LITERAL_MANIFEST.json",
        ),
    )
    return CompositePredicateSocket.open(stages)


def _context_for_subject(subject: str) -> object:
    """Reuse one read-only composite socket on the single daemon worker."""

    global _SOCKET
    with _RUNTIME_LOCK:
        if _SOCKET is None:
            _SOCKET = _open_default_socket()
        socket = _SOCKET
    return socket.context_for_subject(subject)


def _process_item(prepared: object) -> _ShadowTelemetry:
    """Run one enabled item through public contracts, containing all failures."""

    state = _empty_state()
    try:
        from packages.cognitive_core.canonical import canonical_digest
        from packages.reasoning_vm.science_candidate import (
            PreparedScienceInput,
        )

        if type(prepared) is not PreparedScienceInput:
            return _finish(
                state,
                status="ineligible",
                reason="prepared_input_not_exact",
            )
        try:
            prepared.__post_init__()
        except Exception:
            return _finish(
                state,
                status="ineligible",
                reason="prepared_input_invalid",
            )

        # Eligibility deliberately includes both selected and unsupported
        # route decisions.  The lane observes compiler coverage; it does not
        # compete with or alter any existing lane.
        state["eligible"] = True
        state["prepared_input_digest_sha256"] = (
            prepared.input_digest_sha256
        )
        state["prepared_choices_digest_sha256"] = (
            prepared.choices_digest_sha256
        )

        role_receipt = _role_receipt_for(prepared.stem)
        role_digest = role_receipt.receipt_digest_sha256
        roles_extracted = bool(role_receipt.roles_extracted)
        state.update(
            {
                "role_receipt": role_receipt,
                "role_receipt_digest_sha256": role_digest,
                "role_extracted": roles_extracted,
            }
        )
        if not role_receipt.safe:
            return _finish(
                state,
                status="role_abstained",
                reason="role_receipt_not_safe",
            )
        if role_receipt.subject is None:
            return _finish(
                state,
                status="role_abstained",
                reason="role_subject_missing",
            )

        context = _context_for_subject(role_receipt.subject.text)
        context_digest = context.context_digest_sha256
        context_ready = bool(
            context.status == "ready" and context.complete
        )
        state.update(
            {
                "context_receipt": context,
                "context_digest_sha256": context_digest,
                "context_ready": context_ready,
            }
        )
        if not state["context_ready"]:
            return _finish(
                state,
                status="context_abstained",
                reason="predicate_context_not_ready",
            )

        from packages.reasoning_vm.deliberator.generic_predicate_goal import (
            compile_generic_predicate_goal,
        )

        compilation = compile_generic_predicate_goal(
            prepared.stem,
            prepared.choice_items,
            role_receipt=role_receipt,
            context=context,
        )
        compilation_digest = canonical_digest(
            compilation.to_dict()
        )
        compiled = bool(compilation.compiled)
        state.update(
            {
                "compiler_receipt": compilation,
                "compiler_receipt_digest_sha256": compilation_digest,
                "compiled": compiled,
            }
        )
        if not compilation.compiled:
            return _finish(
                state,
                status="compiler_abstained",
                reason=compilation.reason,
            )

        from packages.reasoning_vm.deliberator.generic_predicate_staging import (
            consume_generic_predicate_compilation,
            verify_generic_predicate_proof_receipt,
        )

        state["engine_called"] = True
        decision = consume_generic_predicate_compilation(
            prepared.stem,
            compilation,
            role_receipt=role_receipt,
            context=context,
            enabled=True,
        )
        decision_digest = canonical_digest(
            decision.to_dict()
        )
        fired = bool(decision.engine_fired)
        state.update(
            {
                "proof_decision": decision,
                "proof_decision_digest_sha256": decision_digest,
                "fired": fired,
            }
        )
        if not decision.engine_fired or decision.receipt is None:
            return _finish(
                state,
                status="proof_abstained",
                reason=decision.reason,
            )

        proof_receipt = decision.receipt
        proof_digest = proof_receipt.proof_digest_sha256
        state.update(
            {
                "proof_receipt": proof_receipt,
                "proof_receipt_digest_sha256": proof_digest,
            }
        )
        verified = verify_generic_predicate_proof_receipt(
            proof_receipt,
            prepared.stem,
            compilation,
            role_receipt=role_receipt,
            context=context,
        )
        state["proof_verified"] = bool(verified)
        state["grounded"] = bool(verified)
        return _finish(
            state,
            status=(
                "proof_verified"
                if verified
                else "proof_verification_failed"
            ),
            reason=(
                "exact_proof_replayed"
                if verified
                else "exact_proof_did_not_replay"
            ),
        )
    except Exception as error:
        # No exception, message, answer, or raw input escapes the observer.
        # If a phase had already completed, its immutable receipt remains in
        # the diagnostic trace.
        return _finish(
            state,
            status="observer_fault",
            reason="observer_exception_contained",
            error_kind=_safe_error_kind(error),
        )


_TELEMETRY_LOCK = threading.Lock()
_TELEMETRY: deque[_ShadowTelemetry] = deque(maxlen=TELEMETRY_CAPACITY)


def _publish_telemetry(telemetry: _ShadowTelemetry) -> None:
    if type(telemetry) is not _ShadowTelemetry:
        raise TypeError("exact shadow telemetry required")
    telemetry.__post_init__()
    with _TELEMETRY_LOCK:
        _TELEMETRY.append(telemetry)


class _ShadowDispatcher:
    """A bounded daemon queue whose overload and observer faults are isolated."""

    def __init__(
        self,
        *,
        worker: Callable[[object], _ShadowTelemetry] = _process_item,
        observer: Callable[[_ShadowTelemetry], None] = _publish_telemetry,
        capacity: int = QUEUE_CAPACITY,
    ) -> None:
        if not callable(worker) or not callable(observer):
            raise TypeError("shadow worker and observer must be callable")
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or capacity < 1
        ):
            raise ValueError("shadow queue capacity must be positive")
        self._worker = worker
        self._observer = observer
        self._queue: queue.Queue[object] = queue.Queue(maxsize=capacity)
        self._start_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._started = False
        self._thread: threading.Thread | None = None
        self._pending = 0
        self._accepted = 0
        self._completed = 0
        self._dropped = 0
        self._worker_faults = 0
        self._observer_faults = 0

    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._started:
                return
            thread = threading.Thread(
                target=self._run,
                name="atanor-generic-predicate-shadow",
                daemon=True,
            )
            thread.start()
            self._thread = thread
            self._started = True

    def _observe(self, telemetry: _ShadowTelemetry) -> None:
        try:
            self._observer(telemetry)
        except Exception:
            with self._state_lock:
                self._observer_faults += 1

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                try:
                    telemetry = self._worker(item)
                    if type(telemetry) is not _ShadowTelemetry:
                        raise TypeError(
                            "shadow worker returned a non-telemetry value"
                        )
                except Exception as error:
                    with self._state_lock:
                        self._worker_faults += 1
                    telemetry = _finish(
                        _empty_state(),
                        status="observer_fault",
                        reason="worker_exception_contained",
                        error_kind=_safe_error_kind(error),
                    )
                self._observe(telemetry)
            finally:
                with self._state_lock:
                    self._completed += 1
                    self._pending -= 1
                    if self._pending == 0:
                        self._idle.set()
                self._queue.task_done()

    def submit(self, item: object) -> bool:
        self._ensure_started()
        with self._state_lock:
            self._pending += 1
            self._idle.clear()
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            with self._state_lock:
                self._pending -= 1
                self._dropped += 1
                if self._pending == 0:
                    self._idle.set()
            return False
        with self._state_lock:
            self._accepted += 1
        return True

    def wait_idle(self, timeout_seconds: float) -> bool:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
        ):
            raise ValueError("timeout_seconds must be non-negative")
        return self._idle.wait(float(timeout_seconds))

    def snapshot(self) -> dict[str, int | bool]:
        with self._state_lock:
            thread = self._thread
            return {
                "accepted": self._accepted,
                "completed": self._completed,
                "dropped": self._dropped,
                "worker_faults": self._worker_faults,
                "observer_faults": self._observer_faults,
                "pending": self._pending,
                "capacity": self._queue.maxsize,
                "daemon": bool(thread is not None and thread.daemon),
            }


_DISPATCHER_LOCK = threading.Lock()
_DISPATCHER: _ShadowDispatcher | None = None


def _live_dispatcher() -> _ShadowDispatcher:
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = _ShadowDispatcher()
        return _DISPATCHER


def _telemetry_snapshot_for_tests() -> tuple[_ShadowTelemetry, ...]:
    with _TELEMETRY_LOCK:
        return tuple(_TELEMETRY)


def submit(prepared: object) -> bool:
    """Submit one frozen science input without reading it on the answer path.

    ``True`` means only that diagnostic work entered the bounded queue.  It is
    not a compiler, proof, correctness, or capability result.
    """

    if os.environ.get(ENV_NAME) != "1":
        return False
    try:
        return _live_dispatcher().submit(prepared)
    except Exception:
        return False


__all__ = ["submit"]
