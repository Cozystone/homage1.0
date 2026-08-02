"""Isolation and mechanism tests for the generic-predicate shadow lane.

These tests establish default-off dispatch, bounded nonblocking execution,
receipt continuity, and proof replay only.  They do not establish correctness,
benchmark lift, capability, E4, or E5.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import threading

import pytest

from packages.cognitive_core.canonical import canonical_digest
from packages.graph_scale.triple_store import TripleStore
from packages.reasoning_vm import science_candidate
from packages.reasoning_vm.deliberator import generic_predicate_shadow as shadow
from packages.reasoning_vm.deliberator import generic_predicate_staging
from packages.reasoning_vm.deliberator.generic_predicate_socket import (
    CompositePredicateSocket,
    GenericPredicateContext,
    PredicateStageSpec,
)
from packages.reasoning_vm.deliberator.relation_role_extractor import (
    RelationRoleExtractor,
    SpacyRelationRoleExtractor,
)


STEM = "What catalyst_signature is Zephyr?"
CHOICES = {"A": "amber", "B": "violet"}


@pytest.fixture(scope="module")
def extractor() -> SpacyRelationRoleExtractor:
    return SpacyRelationRoleExtractor()


def _tree_snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    rows: list[tuple[str, int, int, str]] = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.as_posix(),
    ):
        raw = path.read_bytes()
        stat = path.stat()
        rows.append(
            (
                path.relative_to(root).as_posix(),
                stat.st_size,
                stat.st_mtime_ns,
                hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(rows)


def _context(
    tmp_path: Path,
    rows: tuple[tuple[str, str, str], ...],
    subject: str = "Zephyr",
) -> tuple[GenericPredicateContext, Path]:
    root = tmp_path / "generic_predicate_shadow_stage"
    store = TripleStore(root)
    source_id = store.intern_source("shadow-fixture", "")
    for row_subject, predicate, object_value in rows:
        assert store.add(
            row_subject,
            predicate,
            object_value,
            source=source_id,
        )
    store.flush()
    store.rebuild_index()
    store.close()
    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="shadow-fixture",
                role="generic",
                root=root,
            ),
        ),
        max_facts_per_stage=16,
        max_rows_examined_per_stage=32,
    ) as socket:
        context = socket.context_for_subject(subject)
    return context, root


def _prepared(
    stem: str = STEM,
    choices: dict[str, str] | None = None,
) -> science_candidate.PreparedScienceInput:
    return science_candidate.prepare_science_input(
        stem,
        CHOICES if choices is None else choices,
    )


def _minimal_telemetry() -> shadow._ShadowTelemetry:
    return shadow._finish(
        shadow._empty_state(),
        status="ineligible",
        reason="prepared_input_not_exact",
    )


class _Poison:
    def __getattribute__(self, name):
        raise AssertionError(f"disabled shadow touched {name}")


def test_public_surface_is_submit_only_and_default_off_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def forbidden_dispatcher():
        calls.append(object())
        raise AssertionError("disabled shadow created a dispatcher")

    monkeypatch.delenv(shadow.ENV_NAME, raising=False)
    monkeypatch.setattr(shadow, "_live_dispatcher", forbidden_dispatcher)

    assert shadow.__all__ == ["submit"]
    assert shadow.submit(_Poison()) is False
    assert calls == []


@pytest.mark.parametrize(
    "value",
    ("0", "true", "TRUE", "01", " 1", "1 ", ""),
)
def test_only_exact_string_one_enables_submission(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    calls: list[object] = []

    class _Sink:
        def submit(self, item: object) -> bool:
            calls.append(item)
            return True

    item = _Poison()
    monkeypatch.setenv(shadow.ENV_NAME, value)
    monkeypatch.setattr(shadow, "_live_dispatcher", lambda: _Sink())

    assert shadow.submit(item) is False
    assert calls == []


def test_exact_string_one_enqueues_same_object_without_reading_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _Sink:
        def submit(self, item: object) -> bool:
            calls.append(item)
            return True

    item = _Poison()
    monkeypatch.setenv(shadow.ENV_NAME, "1")
    monkeypatch.setattr(shadow, "_live_dispatcher", lambda: _Sink())

    assert shadow.submit(item) is True
    assert len(calls) == 1
    assert calls[0] is item


def test_queue_is_capacity_64_nonblocking_and_daemonized() -> None:
    entered = threading.Event()
    release = threading.Event()
    observed: list[shadow._ShadowTelemetry] = []

    def blocked_worker(_item: object) -> shadow._ShadowTelemetry:
        entered.set()
        assert release.wait(5.0)
        return _minimal_telemetry()

    dispatcher = shadow._ShadowDispatcher(
        worker=blocked_worker,
        observer=observed.append,
    )
    assert dispatcher.submit(object()) is True
    assert entered.wait(2.0)

    # The worker holds one item while exactly 64 more fill the queue.
    assert all(dispatcher.submit(object()) for _ in range(64))
    assert dispatcher.submit(object()) is False
    saturated = dispatcher.snapshot()
    assert saturated["capacity"] == 64
    assert saturated["accepted"] == 65
    assert saturated["dropped"] == 1
    assert saturated["pending"] == 65
    assert saturated["daemon"] is True

    release.set()
    assert dispatcher.wait_idle(5.0)
    finished = dispatcher.snapshot()
    assert finished["completed"] == 65
    assert finished["pending"] == 0
    assert len(observed) == 65


def test_worker_and_observer_exceptions_are_contained() -> None:
    observed: list[shadow._ShadowTelemetry] = []

    def failing_worker(_item: object) -> shadow._ShadowTelemetry:
        raise OSError("secret worker detail")

    worker_dispatcher = shadow._ShadowDispatcher(
        worker=failing_worker,
        observer=observed.append,
        capacity=2,
    )
    assert worker_dispatcher.submit(object())
    assert worker_dispatcher.wait_idle(2.0)
    assert worker_dispatcher.snapshot()["worker_faults"] == 1
    assert len(observed) == 1
    assert observed[0].status == "observer_fault"
    assert observed[0].error_kind == "OSError"
    assert "secret worker detail" not in repr(observed[0])

    def failing_observer(_telemetry: shadow._ShadowTelemetry) -> None:
        raise RuntimeError("secret observer detail")

    observer_dispatcher = shadow._ShadowDispatcher(
        worker=lambda _item: _minimal_telemetry(),
        observer=failing_observer,
        capacity=2,
    )
    assert observer_dispatcher.submit(object())
    assert observer_dispatcher.submit(object())
    assert observer_dispatcher.wait_idle(2.0)
    metrics = observer_dispatcher.snapshot()
    assert metrics["completed"] == 2
    assert metrics["observer_faults"] == 2
    assert metrics["worker_faults"] == 0


def test_unsupported_input_reaches_exact_verified_proof_without_writes(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, root = _context(
        tmp_path,
        (("Zephyr", "catalyst_signature", "amber"),),
    )
    role_receipt = extractor.extract(STEM)
    prepared = _prepared()
    before = _tree_snapshot(root)

    assert prepared.route.status == "unsupported"
    monkeypatch.setattr(
        shadow,
        "_role_receipt_for",
        lambda stem: role_receipt,
    )
    monkeypatch.setattr(
        shadow,
        "_context_for_subject",
        lambda subject: context,
    )

    telemetry = shadow._process_item(prepared)

    assert _tree_snapshot(root) == before
    assert (
        telemetry.eligible,
        telemetry.role_extracted,
        telemetry.context_ready,
        telemetry.compiled,
        telemetry.engine_called,
        telemetry.fired,
        telemetry.proof_verified,
        telemetry.grounded,
    ) == (True, True, True, True, True, True, True, True)
    assert telemetry.status == "proof_verified"
    assert telemetry.reason == "exact_proof_replayed"
    assert telemetry.role_receipt is role_receipt
    assert telemetry.context_receipt is context
    assert telemetry.compiler_receipt is not None
    assert telemetry.proof_decision is not None
    assert telemetry.proof_receipt is telemetry.proof_decision.receipt
    assert telemetry.prepared_input_digest_sha256 == (
        prepared.input_digest_sha256
    )
    assert telemetry.prepared_choices_digest_sha256 == (
        prepared.choices_digest_sha256
    )
    assert telemetry.role_receipt_digest_sha256 == (
        role_receipt.receipt_digest_sha256
    )
    assert telemetry.context_digest_sha256 == context.context_digest_sha256
    assert telemetry.compiler_receipt_digest_sha256 == canonical_digest(
        telemetry.compiler_receipt.to_dict()
    )
    assert telemetry.proof_decision_digest_sha256 == canonical_digest(
        telemetry.proof_decision.to_dict()
    )
    assert telemetry.proof_receipt_digest_sha256 == (
        telemetry.proof_receipt.proof_digest_sha256
    )
    assert telemetry.proof_receipt.choice_key == "A"

    false_claims = (
        "answer_mutated",
        "network_accessed",
        "state_written",
        "answer_authority_established",
        "correctness_established",
        "capability_improvement_established",
        "e4_established",
        "e5_established",
        "external_authenticity_established",
        "independent_evaluation_established",
    )
    assert all(getattr(telemetry, name) is False for name in false_claims)
    with pytest.raises(FrozenInstanceError):
        telemetry.grounded = False
    with pytest.raises(FrozenInstanceError):
        prepared.stem = "tampered"


def test_selected_existing_lane_is_also_eligible_but_never_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stem = "What is the atomic number of oxygen?"
    prepared = _prepared(
        stem,
        {"A": "1", "B": "8", "C": "10"},
    )
    abstention = RelationRoleExtractor().extract(stem)
    monkeypatch.setattr(
        shadow,
        "_role_receipt_for",
        lambda _stem: abstention,
    )

    telemetry = shadow._process_item(prepared)

    assert prepared.route.status == "selected"
    assert prepared.route.lane == "atomic"
    assert telemetry.eligible is True
    assert telemetry.role_extracted is False
    assert telemetry.context_ready is False
    assert telemetry.engine_called is False
    assert telemetry.grounded is False
    assert telemetry.answer_authority_established is False


def test_compiler_abstention_preserves_receipt_and_never_calls_engine(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ = _context(
        tmp_path,
        (("Zephyr", "unmentioned_predicate", "amber"),),
    )
    role_receipt = extractor.extract(STEM)
    monkeypatch.setattr(
        shadow,
        "_role_receipt_for",
        lambda _stem: role_receipt,
    )
    monkeypatch.setattr(
        shadow,
        "_context_for_subject",
        lambda _subject: context,
    )

    telemetry = shadow._process_item(_prepared())

    assert telemetry.eligible is True
    assert telemetry.role_extracted is True
    assert telemetry.context_ready is True
    assert telemetry.compiled is False
    assert telemetry.engine_called is False
    assert telemetry.compiler_receipt is not None
    assert telemetry.compiler_receipt.compiled is False
    assert telemetry.compiler_receipt_digest_sha256 == canonical_digest(
        telemetry.compiler_receipt.to_dict()
    )
    assert telemetry.proof_decision is None
    assert telemetry.grounded is False


def test_engine_firing_is_not_conflated_with_proof_or_correctness(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ = _context(
        tmp_path,
        (("Zephyr", "catalyst_signature", "amber"),),
    )
    role_receipt = extractor.extract(STEM)
    monkeypatch.setattr(
        shadow,
        "_role_receipt_for",
        lambda _stem: role_receipt,
    )
    monkeypatch.setattr(
        shadow,
        "_context_for_subject",
        lambda _subject: context,
    )
    monkeypatch.setattr(
        generic_predicate_staging,
        "verify_generic_predicate_proof_receipt",
        lambda *args, **kwargs: False,
    )

    telemetry = shadow._process_item(_prepared())

    assert telemetry.engine_called is True
    assert telemetry.fired is True
    assert telemetry.proof_receipt is not None
    assert telemetry.proof_verified is False
    assert telemetry.grounded is False
    assert telemetry.correctness_established is False
    assert telemetry.capability_improvement_established is False
    assert telemetry.status == "proof_verification_failed"


def test_two_provable_choices_abstain_after_engine_call(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ = _context(
        tmp_path,
        (
            ("Zephyr", "catalyst_signature", "amber"),
            ("Zephyr", "catalyst_signature", "violet"),
        ),
    )
    role_receipt = extractor.extract(STEM)
    monkeypatch.setattr(
        shadow,
        "_role_receipt_for",
        lambda _stem: role_receipt,
    )
    monkeypatch.setattr(
        shadow,
        "_context_for_subject",
        lambda _subject: context,
    )

    telemetry = shadow._process_item(_prepared())

    assert telemetry.compiled is True
    assert telemetry.engine_called is True
    assert telemetry.fired is False
    assert telemetry.proof_verified is False
    assert telemetry.grounded is False
    assert telemetry.proof_decision is not None
    assert telemetry.proof_decision.reason == "proof_cardinality_not_one"
    assert telemetry.proof_receipt is None


def test_pipeline_exception_preserves_completed_prefix_and_hides_message(
    extractor: SpacyRelationRoleExtractor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role_receipt = extractor.extract(STEM)
    monkeypatch.setattr(
        shadow,
        "_role_receipt_for",
        lambda _stem: role_receipt,
    )

    def failing_context(_subject: str):
        raise OSError("private graph path and sensitive detail")

    monkeypatch.setattr(shadow, "_context_for_subject", failing_context)

    telemetry = shadow._process_item(_prepared())

    assert telemetry.status == "observer_fault"
    assert telemetry.error_kind == "OSError"
    assert telemetry.eligible is True
    assert telemetry.role_extracted is True
    assert telemetry.context_ready is False
    assert telemetry.compiled is False
    assert telemetry.engine_called is False
    assert telemetry.grounded is False
    assert "private graph path" not in repr(telemetry)


def test_grounded_cannot_diverge_from_proof_verified() -> None:
    state = shadow._empty_state()
    state["grounded"] = True
    with pytest.raises(ValueError, match="grounded"):
        shadow._finish(
            state,
            status="observer_fault",
            reason="observer_exception_contained",
        )
