"""Default-off World4D shadow adapter and bounded receipt sink."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import threading
from typing import Any, Iterator
import uuid

from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.cognitive_core.contracts import EpistemicTier
from packages.world4d.block_universe_provider import (
    BlockUniverseQuery,
    BlockUniverseShadowProvider,
)
from packages.world4d.contracts import (
    MAX_RECEIPT_BYTES,
    SHADOW_RECEIPT_LIMITATIONS,
    CheckVerdict,
    Direction,
    World4DProviderDescriptor,
    World4DProviderResult,
    World4DRequest,
    World4DShadowReceipt,
)
from packages.world4d.provider import ReceiptSink, World4DProvider


SHADOW_ENV = "ATANOR_WORLD4D_SHADOW"
SHADOW_LEDGER_RELATIVE = Path("reports") / "world4d-shadow" / "temporal_queries.jsonl"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEDGER_SCHEMA = "atanor.world4d.shadow-ledger.v1"
MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_LEDGER_RECORDS = 100_000

_PATH_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _PATH_LOCK_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ValueError("world4d lock path cannot be a symlink")
    with _path_lock(path):
        with path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":  # pragma: no cover - exercised on Windows desktop
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


def _strict_json(line: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            line.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("world4d ledger record is not strict JSON") from error
    if not isinstance(value, dict):
        raise ValueError("world4d ledger record must be an object")
    return value


def _validate_records(raw: bytes) -> tuple[list[dict[str, Any]], set[str], str | None]:
    if len(raw) > MAX_LEDGER_BYTES:
        raise ValueError("world4d ledger exceeds its bounded size")
    if not raw:
        return [], set(), None
    if not raw.endswith(b"\n"):
        raise ValueError("world4d ledger has a partial trailing record")
    lines = raw.splitlines()
    if len(lines) > MAX_LEDGER_RECORDS:
        raise ValueError("world4d ledger exceeds its record limit")
    records: list[dict[str, Any]] = []
    receipt_ids: set[str] = set()
    previous_hash: str | None = None
    expected_keys = {
        "previous_record_hash",
        "receipt",
        "receipt_hash",
        "record_hash",
        "record_index",
        "schema",
    }
    for index, line in enumerate(lines):
        if not line:
            raise ValueError("world4d ledger cannot contain blank records")
        record = _strict_json(line)
        if set(record) != expected_keys:
            raise ValueError("world4d ledger record has unexpected fields")
        if record["schema"] != LEDGER_SCHEMA:
            raise ValueError("unsupported world4d ledger schema")
        if type(record["record_index"]) is not int or record["record_index"] != index:
            raise ValueError("world4d ledger indexes are not contiguous")
        if record["previous_record_hash"] != previous_hash:
            raise ValueError("world4d ledger hash-chain parent does not match")
        payload = {key: record[key] for key in record if key != "record_hash"}
        expected_hash = canonical_digest(payload)
        if record["record_hash"] != expected_hash:
            raise ValueError("world4d ledger record hash does not match")
        if canonical_json(record).encode("utf-8") != line:
            raise ValueError("world4d ledger record is not canonically encoded")
        raw_receipt = record["receipt"]
        if not isinstance(raw_receipt, dict):
            raise ValueError("world4d ledger receipt must be an object")
        receipt_bytes = canonical_json(raw_receipt).encode("utf-8")
        if len(receipt_bytes) > MAX_RECEIPT_BYTES:
            raise ValueError("world4d receipt exceeds 8 KiB")
        if record["receipt_hash"] != canonical_digest(raw_receipt):
            raise ValueError("world4d receipt hash does not match")
        receipt = World4DShadowReceipt.from_dict(raw_receipt)
        if receipt.to_dict() != raw_receipt:
            raise ValueError("world4d receipt is not canonically normalized")
        if receipt.receipt_id in receipt_ids:
            raise ValueError("world4d ledger contains a duplicate receipt")
        receipt_ids.add(receipt.receipt_id)
        previous_hash = expected_hash
        records.append(record)
    return records, receipt_ids, previous_hash


class JsonlReceiptSink:
    """Append-only, hash-chained local observer sink."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def _read(self) -> bytes:
        if not self.path.exists():
            return b""
        if self.path.is_symlink():
            raise ValueError("world4d ledger path cannot be a symlink")
        with self.path.open("rb") as handle:
            return handle.read(MAX_LEDGER_BYTES + 1)

    def append(self, receipt: World4DShadowReceipt) -> dict[str, Any]:
        if not isinstance(receipt, World4DShadowReceipt):
            raise TypeError("receipt must be World4DShadowReceipt")
        receipt_dict = receipt.to_dict()
        if len(canonical_json(receipt_dict).encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise ValueError("world4d receipt exceeds 8 KiB")
        with _exclusive_file_lock(self.lock_path):
            if self.path.exists() and self.path.is_symlink():
                raise ValueError("world4d ledger path cannot be a symlink")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records, receipt_ids, previous_hash = _validate_records(self._read())
            if receipt.receipt_id in receipt_ids:
                raise ValueError("world4d receipt already exists")
            payload = {
                "previous_record_hash": previous_hash,
                "receipt": receipt_dict,
                "receipt_hash": canonical_digest(receipt_dict),
                "record_index": len(records),
                "schema": LEDGER_SCHEMA,
            }
            record = {**payload, "record_hash": canonical_digest(payload)}
            line = canonical_json(record).encode("utf-8") + b"\n"
            current_size = self.path.stat().st_size if self.path.exists() else 0
            if current_size + len(line) > MAX_LEDGER_BYTES:
                raise ValueError("world4d ledger append would exceed its size limit")
            with self.path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return record

    def records(self) -> tuple[dict[str, Any], ...]:
        with _exclusive_file_lock(self.lock_path):
            records, _, _ = _validate_records(self._read())
        return tuple(json.loads(canonical_json(record)) for record in records)

    def receipts(self) -> tuple[World4DShadowReceipt, ...]:
        return tuple(
            World4DShadowReceipt.from_dict(record["receipt"])
            for record in self.records()
        )

    def verify(self) -> dict[str, Any]:
        with _exclusive_file_lock(self.lock_path):
            records, receipt_ids, final_hash = _validate_records(self._read())
        return {
            "final_record_hash": final_hash,
            "record_count": len(records),
            "receipt_count": len(receipt_ids),
            "schema": LEDGER_SCHEMA,
            "valid": True,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _safe_error_kind(_error: BaseException) -> str:
    return "provider_observation_error"


def _check_summary(result: World4DProviderResult) -> dict[str, int]:
    summary = {verdict.value: 0 for verdict in CheckVerdict}
    for trajectory in result.trajectories:
        for check in trajectory.checks:
            summary[check.verdict.value] += 1
    return summary


class World4DShadowAdapter:
    """Ignore provider output after telemetry; provider effects stay unattested."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        provider_factory: Callable[[], World4DProvider],
        sink: ReceiptSink | None = None,
    ) -> None:
        if type(enabled) is not bool:
            raise TypeError("enabled must be a literal boolean")
        if not callable(provider_factory):
            raise TypeError("provider_factory must be callable")
        self.enabled = enabled
        self._provider_factory = provider_factory
        self._sink = sink
        self.fault_count = 0

    def _receipt(
        self,
        *,
        request_digest: str,
        descriptor_digest: str,
        result: World4DProviderResult | None,
        provider_status: str,
        error_kind: str | None,
    ) -> World4DShadowReceipt:
        trajectories = result.trajectories if result is not None else ()
        return World4DShadowReceipt(
            request_digest=request_digest,
            provider_descriptor_digest=descriptor_digest,
            provider_result_digest=(
                canonical_digest(result.to_dict()) if result is not None else None
            ),
            provider_status=provider_status,
            trajectory_count=len(trajectories),
            step_count=sum(len(item.steps) for item in trajectories),
            check_summary=(
                _check_summary(result)
                if result is not None
                else {verdict.value: 0 for verdict in CheckVerdict}
            ),
            created_at_utc=_utc_now(),
            model_artifact_digest=(
                result.model_artifact_digest if result is not None else None
            ),
            error_kind=error_kind,
            limitations=SHADOW_RECEIPT_LIMITATIONS,
        )

    def observe(
        self,
        request_factory: Callable[[], World4DRequest],
        payload_factory: Callable[[], object],
    ) -> World4DShadowReceipt | None:
        """Run only when enabled, contain faults, and never return provider output."""

        if not self.enabled:
            return None
        request_digest = canonical_digest({"state": "request_unavailable"})
        descriptor_digest = canonical_digest({"state": "provider_unavailable"})
        try:
            request = request_factory()
            if not isinstance(request, World4DRequest):
                raise TypeError("request_factory must return World4DRequest")
            request_digest = canonical_digest(request.to_dict())
            provider = self._provider_factory()
            if not isinstance(provider, World4DProvider):
                raise TypeError("provider_factory must return World4DProvider")
            descriptor = provider.descriptor
            if not isinstance(descriptor, World4DProviderDescriptor):
                raise TypeError("provider descriptor must be World4DProviderDescriptor")
            descriptor_digest = canonical_digest(descriptor.to_dict())
            payload = payload_factory()
            result = provider.propose(request, payload)
            if not isinstance(result, World4DProviderResult):
                raise TypeError("provider must return World4DProviderResult")
            if (
                result.provider_id != descriptor.provider_id
                or result.provider_version != descriptor.provider_version
            ):
                raise ValueError(
                    "provider result identity does not match its descriptor"
                )
            expected_tier = (
                EpistemicTier.PREDICTED
                if request.direction is Direction.FORWARD
                else EpistemicTier.RETRODICTED
            )
            if any(
                step.tier is not expected_tier
                for trajectory in result.trajectories
                for step in trajectory.steps
            ):
                raise ValueError(
                    "provider result epistemic tier does not match request direction"
                )
            receipt = self._receipt(
                request_digest=request_digest,
                descriptor_digest=descriptor_digest,
                result=result,
                provider_status=result.status.value,
                error_kind=None,
            )
        except Exception as error:
            self.fault_count += 1
            receipt = self._receipt(
                request_digest=request_digest,
                descriptor_digest=descriptor_digest,
                result=None,
                provider_status="error",
                error_kind=_safe_error_kind(error),
            )
        try:
            if self._sink is not None:
                self._sink.append(receipt)
        except Exception:
            self.fault_count += 1
            return None
        return receipt


def shadow_enabled() -> bool:
    return os.environ.get(SHADOW_ENV, "0") == "1"


def _observe_enabled_temporal_query(query: BlockUniverseQuery) -> bool:
    source_digest = canonical_digest(query.question)
    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=BlockUniverseShadowProvider,
        sink=JsonlReceiptSink(PROJECT_ROOT / SHADOW_LEDGER_RELATIVE),
    )
    receipt = adapter.observe(
        lambda: World4DRequest(
            request_id=f"world4d_request_{uuid.uuid4().hex}",
            source_kind="temporal_text_query",
            source_digest=source_digest,
            direction=query.direction,
            horizon=3,
            branch_limit=4,
            source_refs=(
                "packages/cgsr/cgsr/response_workspace.py",
                "packages/temporal_reasoning/block_universe.py",
            ),
        ),
        lambda: query,
    )
    return receipt is not None


def _observe_temporal_query_shadow_sync(
    *,
    question: str,
    direction: str | Direction,
    anchor_terms: tuple[str, ...] = (),
) -> bool:
    """Blocking diagnostic helper; live answer paths must use submission."""

    if not shadow_enabled():
        return False
    try:
        query = BlockUniverseQuery(
            question=question,
            direction=Direction(direction),
            anchor_terms=anchor_terms,
        )
        return _observe_enabled_temporal_query(query)
    except Exception:
        return False


MAX_DISPATCH_QUEUE = 64


class World4DShadowDispatcher:
    """Bounded daemon worker that keeps shadow work off the answer path."""

    def __init__(
        self,
        *,
        worker: Callable[[BlockUniverseQuery], bool] = _observe_enabled_temporal_query,
        capacity: int = MAX_DISPATCH_QUEUE,
    ) -> None:
        if not callable(worker):
            raise TypeError("worker must be callable")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self._worker = worker
        self._queue: queue.Queue[BlockUniverseQuery] = queue.Queue(maxsize=capacity)
        self._start_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._started = False
        self._pending = 0
        self._accepted = 0
        self._completed = 0
        self._dropped = 0
        self._failed = 0
        self._faults = 0

    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._started:
                return
            thread = threading.Thread(
                target=self._run,
                name="atanor-world4d-shadow",
                daemon=True,
            )
            thread.start()
            self._started = True

    def _run(self) -> None:
        while True:
            query = self._queue.get()
            try:
                observed = self._worker(query)
                if observed is not True:
                    with self._state_lock:
                        self._failed += 1
            except Exception:
                with self._state_lock:
                    self._faults += 1
            finally:
                with self._state_lock:
                    self._completed += 1
                    self._pending -= 1
                    if self._pending == 0:
                        self._idle.set()
                self._queue.task_done()

    def submit(self, query: BlockUniverseQuery) -> bool:
        if not isinstance(query, BlockUniverseQuery):
            raise TypeError("query must be BlockUniverseQuery")
        self._ensure_started()
        with self._state_lock:
            self._pending += 1
            self._idle.clear()
        try:
            self._queue.put_nowait(query)
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
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds,
            (int, float),
        ):
            raise TypeError("timeout_seconds must be numeric")
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds < 0:
            raise ValueError("timeout_seconds must be finite and non-negative")
        return self._idle.wait(float(timeout_seconds))

    def snapshot(self) -> dict[str, int]:
        with self._state_lock:
            return {
                "accepted": self._accepted,
                "completed": self._completed,
                "dropped": self._dropped,
                "failed": self._failed,
                "faults": self._faults,
                "pending": self._pending,
            }


_DISPATCHER_LOCK = threading.Lock()
_DISPATCHER: World4DShadowDispatcher | None = None


def _live_dispatcher() -> World4DShadowDispatcher:
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = World4DShadowDispatcher()
        return _DISPATCHER


def submit_temporal_query_shadow(
    *,
    question: str,
    direction: str | Direction,
    anchor_terms: tuple[str, ...] = (),
) -> bool:
    """Non-blocking live submission; overload drops telemetry, never answers."""

    if not shadow_enabled():
        return False
    try:
        query = BlockUniverseQuery(
            question=question,
            direction=Direction(direction),
            anchor_terms=anchor_terms,
        )
        return _live_dispatcher().submit(query)
    except Exception:
        return False


def wait_for_temporal_shadow_idle(timeout_seconds: float = 5.0) -> bool:
    """Controlled-test/diagnostic helper; never called by the answer path."""

    with _DISPATCHER_LOCK:
        dispatcher = _DISPATCHER
    return True if dispatcher is None else dispatcher.wait_idle(timeout_seconds)
