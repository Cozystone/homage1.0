"""Default-off, exception-isolated shadow observation for cognitive contracts.

The observer has no filesystem or network implementation.  An optional structural
ledger sink may receive already-redacted, size-bounded records only when explicitly
enabled.  Shadow records never authorize or execute decisions.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any, Protocol, runtime_checkable

from packages.cognitive_core.canonical import SCHEMA_VERSION
from packages.cognitive_core.contracts import CognitiveMoment, DecisionReceipt


_SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_SECRET_PREFIX = re.compile(r"\b(?:sk|pk|key)-[A-Za-z0-9_-]{8,}", re.IGNORECASE)


@runtime_checkable
class ShadowLedger(Protocol):
    """Structural sink; implementations receive a detached redacted record."""

    def append(self, record: Mapping[str, Any]) -> Any:  # pragma: no cover - protocol
        ...


def _redact_text(value: str, max_chars: int) -> str:
    redacted = _BEARER.sub("Bearer [REDACTED]", value)
    redacted = _SECRET_PREFIX.sub("[REDACTED]", redacted)
    if len(redacted) > max_chars:
        return redacted[:max_chars] + "...[TRUNCATED]"
    return redacted


def _redact(
    value: Any,
    *,
    max_chars: int,
    max_items: int,
    max_depth: int,
    depth: int = 0,
) -> Any:
    if depth >= max_depth:
        return "[DEPTH_LIMIT]"
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        items = sorted(value.items(), key=lambda pair: str(pair[0]))
        for key, item in items[:max_items]:
            key_text = str(key)
            output[key_text] = (
                "[REDACTED]"
                if _SENSITIVE_KEY.search(key_text)
                else _redact(
                    item,
                    max_chars=max_chars,
                    max_items=max_items,
                    max_depth=max_depth,
                    depth=depth + 1,
                )
            )
        if len(items) > max_items:
            output["_truncated_fields"] = len(items) - max_items
        return output
    if isinstance(value, (list, tuple)):
        output = [
            _redact(
                item,
                max_chars=max_chars,
                max_items=max_items,
                max_depth=max_depth,
                depth=depth + 1,
            )
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            output.append({"_truncated_items": len(value) - max_items})
        return output
    if isinstance(value, str):
        return _redact_text(value, max_chars)
    if isinstance(value, float) and not math.isfinite(value):
        return "[NONFINITE_REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(repr(value), max_chars)


class ShadowObserver:
    """Observe read-only receipts without ever entering a live decision path."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        ledger: ShadowLedger | None = None,
        max_records: int = 128,
        max_record_bytes: int = 16_384,
        max_chars: int = 512,
        max_items: int = 64,
        max_depth: int = 6,
    ) -> None:
        if type(enabled) is not bool:
            raise TypeError("enabled must be a literal boolean")
        if isinstance(max_records, bool) or max_records <= 0:
            raise ValueError("max_records must be positive")
        if isinstance(max_record_bytes, bool) or max_record_bytes < 512:
            raise ValueError("max_record_bytes must be at least 512")
        if (
            any(isinstance(value, bool) for value in (max_chars, max_items, max_depth))
            or max_chars <= 0
            or max_items <= 0
            or max_depth <= 0
        ):
            raise ValueError("redaction bounds must be positive")
        self.enabled = enabled
        self._ledger = ledger
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._max_ledger_writes = int(max_records)
        self._ledger_write_count = 0
        self._max_record_bytes = int(max_record_bytes)
        self._max_chars = int(max_chars)
        self._max_items = int(max_items)
        self._max_depth = int(max_depth)
        self._fault_count = 0

    @property
    def fault_count(self) -> int:
        return self._fault_count

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(record) for record in self._records)

    @property
    def ledger_write_count(self) -> int:
        return self._ledger_write_count

    def observe(
        self,
        moment: CognitiveMoment,
        receipt: DecisionReceipt,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> bool:
        """Record one shadow observation.

        Disabled means an immediate return before any input or ledger access.  When
        enabled, every exception is contained and reported only through ``False`` and
        ``fault_count`` so the observer cannot perturb the live caller.
        """

        if not self.enabled:
            return False
        try:
            if not isinstance(moment, CognitiveMoment):
                raise TypeError("moment must be a CognitiveMoment")
            if not isinstance(receipt, DecisionReceipt):
                raise TypeError("receipt must be a DecisionReceipt")
            if not receipt.read_only or receipt.authoritative or receipt.action_executed:
                raise ValueError("shadow observer accepts read-only, non-authoritative receipts")
            if receipt.moment_id != moment.contract_id:
                raise ValueError("receipt.moment_id must match the observed moment")

            raw = {
                "schema_version": SCHEMA_VERSION,
                "event": "cognitive_shadow_observation",
                "moment": moment.to_dict(),
                "receipt": receipt.to_dict(),
                "extra": dict(extra or {}),
            }
            record = _redact(
                raw,
                max_chars=self._max_chars,
                max_items=self._max_items,
                max_depth=self._max_depth,
            )
            serialized = json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(serialized) > self._max_record_bytes:
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "event": "cognitive_shadow_observation",
                    "moment_id": moment.contract_id,
                    "receipt_id": receipt.contract_id,
                    "record_truncated": True,
                    "redacted_record_hash": hashlib.sha256(serialized).hexdigest(),
                }
            self._records.append(record)
            if (
                self._ledger is not None
                and self._ledger_write_count < self._max_ledger_writes
            ):
                self._ledger_write_count += 1
                self._ledger.append(deepcopy(record))
            return True
        except Exception:
            self._fault_count += 1
            return False
