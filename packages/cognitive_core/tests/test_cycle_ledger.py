from __future__ import annotations

import json
import threading

import pytest

from packages.cognitive_core import CycleLedger
from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.cognitive_core.cycle_ledger import CycleLedgerCapacityError
from packages.cognitive_core.tests.cycle_fixtures import make_receipt


def test_append_reopen_parent_chain_and_replay(tmp_path):
    path = tmp_path / "cycles.jsonl"
    root = make_receipt()
    child = make_receipt(
        cycle_id="cycle_test_child",
        request_id="request_test_child",
        parent_cycle_id=root.request_cycle.cycle_id,
    )
    ledger = CycleLedger(path)
    first = ledger.append(root)
    second = ledger.append(child)
    assert first["record_index"] == 0
    assert second["previous_record_hash"] == first["record_hash"]
    assert CycleLedger(path).verify()["record_count"] == 2
    assert [item.receipt_id for item in CycleLedger(path).receipts()] == [
        root.receipt_id,
        child.receipt_id,
    ]


def test_duplicate_and_child_before_parent_fail_closed(tmp_path):
    ledger = CycleLedger(tmp_path / "cycles.jsonl")
    root = make_receipt()
    ledger.append(root)
    with pytest.raises(ValueError, match="already exists"):
        ledger.append(root)

    orphan = make_receipt(
        cycle_id="cycle_orphan",
        request_id="request_orphan",
        parent_cycle_id="cycle_missing",
    )
    with pytest.raises(ValueError, match="parent cycle"):
        ledger.append(orphan)


def test_tamper_and_partial_trailing_record_are_detected(tmp_path):
    path = tmp_path / "cycles.jsonl"
    CycleLedger(path).append(make_receipt())
    original = path.read_bytes()
    parsed = json.loads(original)
    parsed["receipt"]["selected_route"] = "tampered"
    path.write_text(json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        CycleLedger(path).verify()

    path.write_bytes(original[:-1])
    with pytest.raises(ValueError, match="partial trailing"):
        CycleLedger(path).verify()


def test_concurrent_writers_serialize_without_lost_records(tmp_path):
    path = tmp_path / "cycles.jsonl"
    errors = []

    def append(index):
        try:
            CycleLedger(path).append(
                make_receipt(
                    cycle_id=f"cycle_concurrent_{index}",
                    request_id=f"request_concurrent_{index}",
                )
            )
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    threads = [threading.Thread(target=append, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert CycleLedger(path).verify()["record_count"] == 8


def test_configured_record_cap_is_atomic_across_concurrent_writers(tmp_path):
    path = tmp_path / "capped-cycles.jsonl"
    accepted = []
    saturated = []

    def append(index):
        try:
            CycleLedger(path, max_records=3).append(
                make_receipt(
                    cycle_id=f"cycle_capped_{index}",
                    request_id=f"request_capped_{index}",
                )
            )
            accepted.append(index)
        except CycleLedgerCapacityError:
            saturated.append(index)

    threads = [threading.Thread(target=append, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(accepted) == 3
    assert len(saturated) == 5
    assert CycleLedger(path, max_records=3).verify()["record_count"] == 3


def test_configured_byte_cap_fails_before_first_oversized_append(tmp_path):
    path = tmp_path / "byte-capped-cycles.jsonl"
    with pytest.raises(CycleLedgerCapacityError, match="byte limit"):
        CycleLedger(path, max_bytes=1).append(make_receipt())
    assert not path.exists() or path.read_bytes() == b""


def _rewrite_record(path, mutate):
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    payload = {key: value for key, value in record.items() if key != "record_hash"}
    record["record_hash"] = canonical_digest(payload)
    path.write_text(canonical_json(record) + "\n", encoding="utf-8")


def test_record_index_rejects_json_boolean_alias(tmp_path):
    path = tmp_path / "boolean-index.jsonl"
    CycleLedger(path).append(make_receipt())
    _rewrite_record(path, lambda record: record.__setitem__("record_index", False))
    with pytest.raises(ValueError, match="index"):
        CycleLedger(path).verify()


def test_rehashed_unknown_receipt_payload_is_not_silently_dropped(tmp_path):
    path = tmp_path / "unknown-receipt-field.jsonl"
    CycleLedger(path).append(make_receipt())

    def inject(record):
        record["receipt"]["unknown_raw_payload"] = "SECRET_MUST_NOT_SURVIVE"
        record["receipt"]["request_cycle"]["unknown_nested_payload"] = (
            "NESTED_SECRET_MUST_NOT_SURVIVE"
        )

    _rewrite_record(path, inject)
    with pytest.raises(ValueError, match="exact canonical reconstruction"):
        CycleLedger(path).verify()


def test_mapping_append_requires_an_exact_canonical_receipt(tmp_path):
    path = tmp_path / "mapping-append.jsonl"
    payload = make_receipt().to_dict()
    payload["unknown_raw_payload"] = "SECRET_MUST_NOT_BE_NORMALIZED"
    with pytest.raises(ValueError, match="exact canonical receipt"):
        CycleLedger(path).append(payload)

    payload = make_receipt().to_dict()
    payload.pop("action_authorized")
    with pytest.raises(ValueError, match="exact canonical receipt"):
        CycleLedger(path).append(payload)
    assert not path.exists()
