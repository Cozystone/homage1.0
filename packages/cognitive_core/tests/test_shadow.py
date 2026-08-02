from __future__ import annotations

import json

import pytest

from packages.cognitive_core import (
    CognitiveMoment,
    DecisionReceipt,
    ReceiptMode,
    ShadowObserver,
)


class RecordingLedger:
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(record)


class FailingLedger:
    def append(self, record):
        raise OSError("simulated ledger outage")


class PoisonInput:
    def __getattribute__(self, name):
        raise AssertionError("disabled observer accessed its input")


def _moment_and_receipt(*, metadata=None):
    moment = CognitiveMoment(
        moment_index=3,
        envelope_id="cenv:shadow",
        world_snapshot_id="world:shadow",
        active_goal_ids=("goal:user",),
        selected_goal_id="goal:user",
        metadata=metadata or {},
    )
    receipt = DecisionReceipt(
        moment_id=moment.contract_id,
        mode=ReceiptMode.SHADOW,
        decision_kind="candidate_selection",
        rationale="Inspect token sk-this-is-a-secret-value without exposing it.",
        selected_goal_id="goal:user",
        metadata={
            "password": "cleartext-password",
            "nested": {"authorization": "Bearer abcdefghijklmnopqrstuvwxyz"},
        },
    )
    return moment, receipt


def test_shadow_observer_is_default_off_and_performs_no_input_or_ledger_access():
    ledger = RecordingLedger()
    observer = ShadowObserver(ledger=ledger)
    assert observer.enabled is False
    assert observer.observe(PoisonInput(), PoisonInput()) is False
    assert observer.fault_count == 0
    assert observer.records == ()
    assert ledger.records == []


def test_truthy_string_cannot_enable_shadow_observation():
    with pytest.raises(TypeError, match="literal boolean"):
        ShadowObserver(enabled="false")


def test_enabled_observer_records_only_bounded_redacted_shadow_data():
    ledger = RecordingLedger()
    observer = ShadowObserver(
        enabled=True,
        ledger=ledger,
        max_records=2,
        max_chars=80,
        max_items=16,
    )
    moment, receipt = _moment_and_receipt()

    for index in range(3):
        assert observer.observe(
            moment,
            receipt,
            extra={
                "api_key": f"raw-key-{index}",
                "note": "Bearer another-long-secret-token",
            },
        )

    assert len(observer.records) == 2
    assert len(ledger.records) == 2
    assert observer.ledger_write_count == 2
    serialized = json.dumps(observer.records, ensure_ascii=False, sort_keys=True)
    assert "cleartext-password" not in serialized
    assert "raw-key-" not in serialized
    assert "another-long-secret-token" not in serialized
    assert "this-is-a-secret-value" not in serialized
    assert "[REDACTED]" in serialized

    detached = observer.records[0]
    detached["event"] = "mutated"
    assert observer.records[0]["event"] == "cognitive_shadow_observation"


def test_enabled_observer_contains_ledger_and_input_failures():
    moment, receipt = _moment_and_receipt()
    observer = ShadowObserver(enabled=True, ledger=FailingLedger())
    assert observer.observe(moment, receipt) is False
    assert observer.fault_count == 1

    assert observer.observe(object(), object()) is False
    assert observer.fault_count == 2


def test_observer_rejects_receipt_for_a_different_moment_without_raising():
    moment, _ = _moment_and_receipt()
    wrong = DecisionReceipt(
        moment_id="moment:different",
        mode=ReceiptMode.READ_ONLY,
        decision_kind="candidate",
        rationale="This belongs to another moment.",
    )
    observer = ShadowObserver(enabled=True)
    assert observer.observe(moment, wrong) is False
    assert observer.fault_count == 1
    assert observer.records == ()


def test_oversize_record_collapses_to_a_bounded_redacted_summary():
    moment, receipt = _moment_and_receipt(metadata={"large": "x" * 5_000})
    observer = ShadowObserver(
        enabled=True,
        max_record_bytes=512,
        max_chars=5_000,
    )
    assert observer.observe(moment, receipt)
    record = observer.records[0]
    assert record["record_truncated"] is True
    assert set(record) == {
        "schema_version",
        "event",
        "moment_id",
        "receipt_id",
        "record_truncated",
        "redacted_record_hash",
    }
    assert len(json.dumps(record).encode("utf-8")) <= 512


def test_nonfinite_shadow_telemetry_is_redacted_not_serialized_as_nan():
    moment, receipt = _moment_and_receipt()
    observer = ShadowObserver(enabled=True)

    assert observer.observe(moment, receipt, extra={"hormone": float("nan")})
    serialized = json.dumps(
        observer.records[0],
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )
    assert "NONFINITE_REDACTED" in serialized
