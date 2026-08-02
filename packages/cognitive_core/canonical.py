"""Deterministic, immutable JSON values for the M1 cognitive contracts.

This module is intentionally standard-library only.  Contract identity is derived
from canonical JSON rather than process identity, timestamps, or Python hashes.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from enum import Enum
import hashlib
import json
import math
from typing import Any


SCHEMA_VERSION = "atanor.cognitive_core.m1.v1"


class FrozenMap(Mapping[str, Any]):
    """A small immutable mapping with deterministic key order and deep-frozen values."""

    __slots__ = ("_items", "_lookup")

    def __init__(self, value: Mapping[str, Any] | None = None) -> None:
        source = value or {}
        if not isinstance(source, Mapping):
            raise TypeError("FrozenMap requires a mapping")
        items: list[tuple[str, Any]] = []
        for key, item in source.items():
            if not isinstance(key, str) or not key:
                raise ValueError("canonical mapping keys must be non-empty strings")
            items.append((key, freeze_json(item)))
        items.sort(key=lambda pair: pair[0])
        self._items = tuple(items)
        self._lookup = dict(items)

    def __getitem__(self, key: str) -> Any:
        return self._lookup[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __repr__(self) -> str:
        return f"FrozenMap({dict(self._items)!r})"

    def to_dict(self) -> dict[str, Any]:
        return {key: thaw_json(value) for key, value in self._items}


def freeze_json(value: Any) -> Any:
    """Deep-freeze a JSON-shaped value and reject unstable or non-finite values."""

    if isinstance(value, Enum):
        return freeze_json(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical values cannot contain NaN or infinity")
        return value
    if isinstance(value, FrozenMap):
        return value
    if isinstance(value, Mapping):
        return FrozenMap(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if isinstance(value, (set, frozenset)):
        frozen = [freeze_json(item) for item in value]
        return tuple(sorted(frozen, key=canonical_json))
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def thaw_json(value: Any) -> Any:
    """Return a detached, JSON-serializable representation of a frozen value."""

    if isinstance(value, FrozenMap):
        return value.to_dict()
    if isinstance(value, Enum):
        return thaw_json(value.value)
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    if isinstance(value, list):
        return [thaw_json(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): thaw_json(value[key]) for key in sorted(value)}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return thaw_json(to_dict())
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a value with stable ordering and no insignificant whitespace."""

    return json.dumps(
        thaw_json(freeze_json(value)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    """Return a stable SHA-256 digest of a canonical JSON value."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_id(prefix: str, value: Any) -> tuple[str, str]:
    """Return ``(stable_id, full_digest)`` for a contract payload."""

    if not prefix or any(char.isspace() for char in prefix):
        raise ValueError("canonical ID prefix must be non-empty and contain no whitespace")
    digest = canonical_digest(value)
    return f"{prefix}_{digest[:32]}", digest
