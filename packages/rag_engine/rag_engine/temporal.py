from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any


DATE_KEYS = (
    "timestamp",
    "created_at",
    "updated_at",
    "published_at",
    "source_timestamp",
    "source_created_at",
    "date",
    "year",
)

ISO_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})(?:[-/.](0?[1-9]|1[0-2])(?:[-/.](0?[1-9]|[12]\d|3[01]))?)?\b")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_temporal_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        integer = int(value)
        if 1900 <= integer <= 2200:
            return datetime(integer, 1, 1, tzinfo=timezone.utc)
        if integer > 10_000_000:
            try:
                return datetime.fromtimestamp(integer, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    match = ISO_PATTERN.search(text)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return datetime(year, 1, 1, tzinfo=timezone.utc)


def payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in DATE_KEYS:
            parsed = parse_temporal_value(metadata.get(key))
            if parsed:
                return parsed
    for key in DATE_KEYS:
        parsed = parse_temporal_value(payload.get(key))
        if parsed:
            return parsed
    raw_text = str(payload.get("raw_text") or payload.get("text") or payload.get("snippet") or "")
    return parse_temporal_value(raw_text)


def temporal_decay_multiplier(timestamp: datetime | None, *, now: datetime | None = None, half_life_days: float = 730.0) -> float:
    if not timestamp:
        return 0.72
    reference = now or utc_now()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (reference - timestamp).total_seconds() / 86_400.0)
    half_life_days = max(1.0, float(half_life_days))
    return max(0.05, min(1.35, math.exp(-math.log(2.0) * age_days / half_life_days)))


def apply_temporal_weights(
    payloads: list[dict[str, Any]],
    *,
    hash_weights: dict[str, float] | None = None,
    now: datetime | None = None,
    half_life_days: float = 730.0,
) -> list[dict[str, Any]]:
    if not payloads:
        return []
    reference = now or utc_now()
    hash_weights = hash_weights or {}
    timestamps = [payload_timestamp(payload) for payload in payloads]
    dated = [stamp for stamp in timestamps if stamp is not None]
    newest = max(dated) if dated else None
    oldest = min(dated) if dated else None
    temporal_collision = bool(newest and oldest and newest.year != oldest.year)
    weighted: list[dict[str, Any]] = []
    for index, payload in enumerate(payloads):
        payload_copy = dict(payload)
        metadata = dict(payload_copy.get("metadata") or {})
        stamp = timestamps[index]
        decay = temporal_decay_multiplier(stamp, now=reference, half_life_days=half_life_days)
        base_weight = float(hash_weights.get(str(payload_copy.get("hash_key") or ""), payload_copy.get("weight") or 1.0))
        if stamp and newest and stamp == newest:
            potentiation = 1.25
        elif stamp and newest:
            year_gap = max(0, newest.year - stamp.year)
            potentiation = max(0.25, 1.0 - year_gap * 0.08)
        else:
            potentiation = 0.82
        combined = max(0.0001, base_weight * decay * potentiation)
        temporal = {
            "timestamp": stamp.isoformat().replace("+00:00", "Z") if stamp else None,
            "year": stamp.year if stamp else None,
            "base_weight": round(base_weight, 6),
            "decay_multiplier": round(decay, 6),
            "potentiation_multiplier": round(potentiation, 6),
            "combined_weight": round(combined, 6),
            "collision_detected": temporal_collision,
            "collision_policy": "preserve_all_prioritize_latest" if temporal_collision else "single_temporal_band",
        }
        metadata["temporal"] = temporal
        payload_copy["metadata"] = metadata
        payload_copy["temporal"] = temporal
        payload_copy["temporal_weight"] = temporal["combined_weight"]
        weighted.append(payload_copy)
    weighted.sort(
        key=lambda item: (
            -float(item.get("temporal_weight") or 0.0),
            str((item.get("temporal") or {}).get("timestamp") or ""),
            str(item.get("hash_key") or ""),
        )
    )
    for rank, payload in enumerate(weighted, start=1):
        payload["temporal_rank"] = rank
        temporal = dict(payload.get("temporal") or {})
        temporal["rank"] = rank
        payload["temporal"] = temporal
        metadata = dict(payload.get("metadata") or {})
        metadata["temporal"] = temporal
        payload["metadata"] = metadata
    return weighted
