"""Append-only, hash-chained storage for canonical cycle receipts.

The ledger is intentionally a separate observer store.  It never writes to the
knowledge graph, self state, permission store, promotion manifests, or benchmark
evidence.  Validation replays every receipt before an append is accepted.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
from typing import Any, BinaryIO, Iterator

from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.cognitive_core.cycle import CycleReceipt
from packages.cognitive_core.replay import replay_cycle


LEDGER_SCHEMA = "atanor.cognitive_core.cycle-ledger.v1"
MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_LEDGER_RECORDS = 100_000

_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


class CycleLedgerCapacityError(ValueError):
    """The configured ledger quota is exhausted or already exceeded."""


def _path_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(line: bytes) -> dict[str, Any]:
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("ledger record is not UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("ledger record is not strict JSON") from error
    if not isinstance(value, dict):
        raise ValueError("ledger record must be a JSON object")
    return value


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    """Cross-process one-byte lock with a process-local guard."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists() and lock_path.is_symlink():
        raise ValueError("cycle ledger lock path cannot be a symlink")
    local_lock = _path_lock(lock_path)
    with local_lock:
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":  # pragma: no cover - exercised on Windows CI/desktop
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised on POSIX CI
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _record_without_hash(
    *,
    index: int,
    previous_record_hash: str | None,
    receipt: CycleReceipt,
) -> dict[str, Any]:
    receipt_dict = receipt.to_dict()
    return {
        "previous_record_hash": previous_record_hash,
        "receipt": receipt_dict,
        "receipt_hash": canonical_digest(receipt_dict),
        "record_index": index,
        "schema": LEDGER_SCHEMA,
    }


def _validate_records(
    raw: bytes,
) -> tuple[list[dict[str, Any]], set[str], set[str], str | None]:
    if len(raw) > MAX_LEDGER_BYTES:
        raise ValueError("cycle ledger exceeds the bounded size limit")
    if not raw:
        return [], set(), set(), None
    if not raw.endswith(b"\n"):
        raise ValueError("cycle ledger has a partial trailing record")
    lines = raw.splitlines()
    if len(lines) > MAX_LEDGER_RECORDS:
        raise ValueError("cycle ledger exceeds the bounded record limit")

    records: list[dict[str, Any]] = []
    receipt_ids: set[str] = set()
    cycle_ids: set[str] = set()
    previous_hash: str | None = None
    for index, line in enumerate(lines):
        if not line:
            raise ValueError("cycle ledger cannot contain blank records")
        record = _strict_json(line)
        if set(record) != {
            "previous_record_hash",
            "receipt",
            "receipt_hash",
            "record_hash",
            "record_index",
            "schema",
        }:
            raise ValueError("cycle ledger record has unexpected or missing fields")
        if record["schema"] != LEDGER_SCHEMA:
            raise ValueError("unsupported cycle ledger schema")
        if type(record["record_index"]) is not int or record["record_index"] != index:
            raise ValueError("cycle ledger record index is not contiguous")
        if record["previous_record_hash"] != previous_hash:
            raise ValueError("cycle ledger hash-chain parent does not match")
        payload = {key: record[key] for key in record if key != "record_hash"}
        expected_hash = canonical_digest(payload)
        if record["record_hash"] != expected_hash:
            raise ValueError("cycle ledger record hash does not match content")
        if canonical_json(record).encode("utf-8") != line:
            raise ValueError("cycle ledger record is not canonically encoded")
        raw_receipt = record["receipt"]
        receipt = CycleReceipt.from_dict(raw_receipt)
        if canonical_json(receipt.to_dict()) != canonical_json(raw_receipt):
            raise ValueError(
                "cycle ledger receipt is not an exact canonical reconstruction"
            )
        replay_cycle(receipt)
        if record["receipt_hash"] != canonical_digest(receipt.to_dict()):
            raise ValueError("cycle ledger receipt hash does not match content")
        if receipt.receipt_id in receipt_ids:
            raise ValueError("cycle ledger contains a duplicate receipt ID")
        cycle_id = receipt.request_cycle.cycle_id
        if cycle_id in cycle_ids:
            raise ValueError("cycle ledger contains a duplicate cycle ID")
        parent_cycle_id = receipt.request_cycle.parent_cycle_id
        if parent_cycle_id is not None and parent_cycle_id not in cycle_ids:
            raise ValueError("cycle ledger child appears before its parent cycle")
        receipt_ids.add(receipt.receipt_id)
        cycle_ids.add(cycle_id)
        previous_hash = expected_hash
        records.append(record)
    return records, receipt_ids, cycle_ids, previous_hash


class CycleLedger:
    """Validated append-only JSONL receipt ledger."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        max_bytes: int = MAX_LEDGER_BYTES,
        max_records: int = MAX_LEDGER_RECORDS,
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")
        if isinstance(max_records, bool) or not isinstance(max_records, int):
            raise TypeError("max_records must be an integer")
        if not 1 <= max_bytes <= MAX_LEDGER_BYTES:
            raise ValueError(
                f"max_bytes must be between 1 and {MAX_LEDGER_BYTES}"
            )
        if not 1 <= max_records <= MAX_LEDGER_RECORDS:
            raise ValueError(
                f"max_records must be between 1 and {MAX_LEDGER_RECORDS}"
            )
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.max_bytes = max_bytes
        self.max_records = max_records

    def _read_bytes(self) -> bytes:
        if not self.path.exists():
            return b""
        if self.path.is_symlink():
            raise ValueError("cycle ledger path cannot be a symlink")
        with self.path.open("rb") as handle:
            return handle.read(self.max_bytes + 1)

    def _validate_configured_bytes(self, raw: bytes) -> None:
        if len(raw) > self.max_bytes:
            raise CycleLedgerCapacityError(
                "cycle ledger exceeds its configured byte limit"
            )

    def _validate_configured_records(
        self,
        records: list[dict[str, Any]],
    ) -> None:
        if len(records) > self.max_records:
            raise CycleLedgerCapacityError(
                "cycle ledger exceeds its configured record limit"
            )

    def append(self, value: CycleReceipt | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(value, CycleReceipt):
            receipt = value
        else:
            receipt = CycleReceipt.from_dict(value)
            if canonical_json(receipt.to_dict()) != canonical_json(value):
                raise ValueError(
                    "cycle ledger append input is not an exact canonical receipt"
                )
        replay_cycle(receipt)
        with _exclusive_file_lock(self.lock_path):
            if self.path.exists() and self.path.is_symlink():
                raise ValueError("cycle ledger path cannot be a symlink")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            raw = self._read_bytes()
            self._validate_configured_bytes(raw)
            records, receipt_ids, cycle_ids, previous_hash = _validate_records(raw)
            self._validate_configured_records(records)
            if len(records) >= self.max_records:
                raise CycleLedgerCapacityError(
                    "cycle ledger append would exceed its configured record limit"
                )
            if receipt.receipt_id in receipt_ids:
                raise ValueError("cycle receipt already exists in the ledger")
            if receipt.request_cycle.cycle_id in cycle_ids:
                raise ValueError("cycle ID already exists in the ledger")
            parent_cycle_id = receipt.request_cycle.parent_cycle_id
            if parent_cycle_id is not None and parent_cycle_id not in cycle_ids:
                raise ValueError("parent cycle must be present before the child")
            payload = _record_without_hash(
                index=len(records),
                previous_record_hash=previous_hash,
                receipt=receipt,
            )
            record = {**payload, "record_hash": canonical_digest(payload)}
            line = canonical_json(record).encode("utf-8") + b"\n"
            current_size = self.path.stat().st_size if self.path.exists() else 0
            if current_size + len(line) > self.max_bytes:
                raise CycleLedgerCapacityError(
                    "cycle ledger append would exceed its configured byte limit"
                )
            with self.path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return record

    def records(self) -> tuple[dict[str, Any], ...]:
        with _exclusive_file_lock(self.lock_path):
            raw = self._read_bytes()
            self._validate_configured_bytes(raw)
            records, _, _, _ = _validate_records(raw)
            self._validate_configured_records(records)
        return tuple(json.loads(canonical_json(record)) for record in records)

    def receipts(self) -> tuple[CycleReceipt, ...]:
        return tuple(CycleReceipt.from_dict(record["receipt"]) for record in self.records())

    def verify(self) -> dict[str, Any]:
        with _exclusive_file_lock(self.lock_path):
            raw = self._read_bytes()
            self._validate_configured_bytes(raw)
            records, receipt_ids, cycle_ids, final_hash = _validate_records(raw)
            self._validate_configured_records(records)
        return {
            "schema": LEDGER_SCHEMA,
            "valid": True,
            "record_count": len(records),
            "receipt_count": len(receipt_ids),
            "cycle_count": len(cycle_ids),
            "final_record_hash": final_hash,
        }
